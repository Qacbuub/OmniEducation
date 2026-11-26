from django.db import connection
from django.db.models import Q
from django.http import FileResponse
from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from core.audit import log_event
from core.models import Role, User
from core.permissions import AUTHENTICATED
from core.tenancy import (
    TenantModelSerializer,
    TenantPrimaryKeyRelatedField,
    TenantScopedViewSetMixin,
)
from people.models import Student
from people.scoping import visible_students

from .models import Announcement, Document, Notification
from .services import notify, validate_upload


# ------------------------------------------------------------------ notifications
class NotificationSerializer(serializers.ModelSerializer):
    read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ["id", "title", "body", "kind", "link", "read", "read_at", "created_at"]

    def get_read(self, obj):
        return obj.read_at is not None


class NotificationViewSet(TenantScopedViewSetMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """A user's own notifications only."""

    serializer_class = NotificationSerializer
    required_perms = {"*": AUTHENTICATED}
    filterset_fields = ["kind"]

    def get_queryset(self):
        return Notification.objects.filter(tenant=self.request.user.tenant, user=self.request.user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data["unread"] = self.get_queryset().filter(read_at__isnull=True).count()
        return response

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        n = self.get_object()
        n.read_at = n.read_at or timezone.now()
        n.save(update_fields=["read_at"])
        return Response(NotificationSerializer(n).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        count = self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({"marked_read": count})


# ------------------------------------------------------------------ announcements
class AnnouncementSerializer(TenantModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = ["id", "title", "body", "audience_roles", "pinned", "author_name", "created_at"]

    def get_author_name(self, obj):
        return obj.author.get_full_name() if obj.author else None

    def validate_audience_roles(self, roles):
        valid = set(Role.objects.values_list("code", flat=True)) - {"super_admin"}
        bad = [r for r in roles if r not in valid]
        if bad:
            raise serializers.ValidationError(f"Unknown roles: {', '.join(bad)}")
        return roles


class AnnouncementViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = AnnouncementSerializer
    queryset = Announcement.objects.select_related("author")
    required_perms = {"list": AUTHENTICATED, "retrieve": AUTHENTICATED, "*": "announcements.manage"}
    search_fields = ["title", "body"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.has_perm_code("announcements.manage"):
            return qs
        role = self.request.user.role_code
        if connection.features.supports_json_field_contains:  # PostgreSQL
            return qs.filter(Q(audience_roles=[]) | Q(audience_roles__contains=[role]))
        # SQLite and others can't do JSON "contains": filter the (few) announcements in Python instead.
        ids = [a.pk for a in qs.select_related(None).only("pk", "audience_roles") if not a.audience_roles or role in a.audience_roles]
        return qs.filter(pk__in=ids)

    def perform_create(self, serializer):
        ann = serializer.save(tenant=self.tenant, author=self.request.user)
        audience = User.objects.filter(tenant=self.tenant, is_active=True).exclude(pk=self.request.user.pk)
        if ann.audience_roles:
            audience = audience.filter(role__code__in=ann.audience_roles)
        notify(audience, ann.title, ann.body[:300], kind="announcement", link="/announcements")
        log_event("announcement.published", request=self.request, target=ann,
                  changes={"audience": ann.audience_roles or "everyone"})


# ------------------------------------------------------------------ documents
class DocumentSerializer(TenantModelSerializer):
    student = TenantPrimaryKeyRelatedField(queryset=Student.objects.all(), required=False, allow_null=True)
    file = serializers.FileField(write_only=True, validators=[validate_upload])
    uploaded_by = serializers.EmailField(source="uploaded_by.email", read_only=True, default=None)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ["id", "kind", "title", "file", "original_name", "size", "student", "application", "generated",
                  "uploaded_by", "download_url", "created_at"]
        read_only_fields = ["original_name", "size", "generated", "application"]

    def get_download_url(self, obj):
        return f"/api/documents/{obj.pk}/download/"


class DocumentViewSet(TenantScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                      mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Files are served only through /download/, after the same visibility check as the student record."""

    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    required_perms = {"list": AUTHENTICATED, "retrieve": AUTHENTICATED, "download": AUTHENTICATED,
                      "create": "documents.manage", "destroy": "documents.manage"}
    filterset_fields = ["kind", "student", "application"]
    search_fields = ["title", "original_name"]

    def get_queryset(self):
        user = self.request.user
        qs = Document.objects.filter(tenant=user.tenant).select_related("uploaded_by")
        if user.has_perm_code("documents.manage", "admissions.view"):
            return qs
        return qs.filter(student__in=visible_students(user))

    def perform_create(self, serializer):
        f = serializer.validated_data["file"]
        if not serializer.validated_data.get("student"):
            raise ValidationError({"student": ["Choose the student this document belongs to."]})
        doc = serializer.save(tenant=self.tenant, uploaded_by=self.request.user, original_name=f.name, size=f.size)
        log_event("document.uploaded", request=self.request, target=doc, changes={"kind": doc.kind})

    def perform_destroy(self, instance):
        if instance.generated:
            raise ValidationError({"detail": ["Official generated documents cannot be deleted."]})
        log_event("document.deleted", request=self.request, target=instance)
        instance.file.delete(save=False)
        instance.delete()

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        doc = self.get_object()
        log_event("document.downloaded", request=request, target=doc)
        return FileResponse(doc.file.open("rb"), as_attachment=True, filename=doc.original_name or doc.file.name)

