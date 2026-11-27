import csv

from django.db import transaction
from django.db.models import DecimalField, OuterRef, Prefetch, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404, HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core import emails
from core.audit import log_event
from core.models import Invitation, Role, User
from core.serializers import invite_link
from core.permissions import AUTHENTICATED
from core.tenancy import TenantScopedViewSetMixin

from .models import EmergencyContact, Guardian, GuardianLink, Staff
from .scoping import visible_students
from .serializers import (
    EmergencyContactSerializer,
    GuardianLinkSerializer,
    GuardianSerializer,
    StaffSerializer,
    StudentDetailSerializer,
    StudentListSerializer,
)


PHOTO_MAX_BYTES = 3 * 1024 * 1024


def sniff_image(f):
    """Accept only real JPEG/PNG files (checked by content, not by name) under the size limit."""
    if f is None:
        raise ValidationError({"photo": ["Choose a photo to upload."]})
    if f.size > PHOTO_MAX_BYTES:
        raise ValidationError({"photo": ["Photos must be under 3 MB."]})
    head = f.read(8)
    f.seek(0)
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    raise ValidationError({"photo": ["Use a JPG or PNG image."]})


def _with_balance(qs):
    from finance.models import Invoice

    owed = (Invoice.objects.filter(student=OuterRef("pk")).exclude(status__in=["void", "draft"]).order_by()
            .values("student").annotate(t=Sum("balance")).values("t"))
    return qs.annotate(balance=Coalesce(Subquery(owed, output_field=DecimalField(max_digits=12, decimal_places=2)),
                                        Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))))


def _invite_portal_user(request, profile, role_code):
    """Create a pending invitation so a guardian / pupil / student can set a password."""
    email = (profile.person.email or "").lower()
    if profile.user_id:
        raise ValidationError({"detail": ["This person already has a portal account."]})
    if not email:
        raise ValidationError({"email": ["Add an email address to the profile first."]})
    if User.objects.filter(email=email).exists():
        raise ValidationError({"email": ["A user with this email already exists."]})
    pending = Invitation.objects.filter(tenant=request.user.tenant, email=email, accepted_at__isnull=True,
                                        expires_at__gt=timezone.now()).first()
    if pending:  # clicking "invite" again re-sends the same invitation instead of piling up new ones
        sent = emails.send_invitation(pending)
        return Response(_invite_result(pending, email, sent, resent=True))
    inv = Invitation.objects.create(tenant=request.user.tenant, email=email, role=Role.objects.get(code=role_code),
                                    first_name=profile.person.first_name, last_name=profile.person.last_name,
                                    invited_by=request.user)
    sent = emails.send_invitation(inv)
    log_event("portal_account.invited", request=request, target=profile,
              changes={"email": email, "role": role_code, "emailed": sent})
    return Response(_invite_result(inv, email, sent), status=status.HTTP_201_CREATED)


def _invite_result(inv, email, sent, resent=False):
    """Tell staff honestly whether the email went out; if it did not, give them the link to pass on."""
    if sent:
        message = f"Invitation {'re-sent' if resent else 'emailed'} to {email}."
    elif not emails.emails_enabled():
        message = f"Invitation created for {email}. This server does not send emails, so share the sign-up link."
    else:
        message = (f"Invitation created for {email}, but the email could not be sent. "
                   "Share the sign-up link, or try again later.")
    return {"message": message, "email_sent": sent, "invite_link": invite_link(inv, force=not sent)}


class StudentViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    audit_name = "student"
    required_perms = {
        "list": AUTHENTICATED, "retrieve": AUTHENTICATED,  # narrowed by visible_students()
        "create": "students.manage", "update": "students.manage", "partial_update": "students.manage",
        "destroy": "students.manage", "export": "students.view", "portal_account": "students.manage",
        "photo": AUTHENTICATED, "upload_photo": "students.manage", "remove_photo": "students.manage",
    }
    search_fields = ["student_no", "person__first_name", "person__last_name", "person__email"]
    filterset_fields = ["status", "current_level", "current_section"]
    ordering_fields = ["student_no", "person__last_name", "admission_date"]

    def get_queryset(self):
        qs = visible_students(self.request.user).prefetch_related(
            Prefetch("guardian_links", queryset=GuardianLink.objects.select_related("guardian__person")))
        return _with_balance(qs)

    def get_serializer_class(self):
        return StudentListSerializer if self.action in ("list", "export") else StudentDetailSerializer

    def perform_create(self, serializer):
        obj = serializer.save()
        log_event("student.created", request=self.request, target=obj, changes={"student_no": obj.student_no})

    def perform_destroy(self, instance):
        # Students are never hard-deleted: history, grades and invoices depend on them.
        raise ValidationError({"detail": ["Students cannot be deleted. Use withdrawal or transfer instead."]})

    @action(detail=False, methods=["get"])
    def export(self, request):
        qs = self.filter_queryset(self.get_queryset())
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="students.csv"'
        writer = csv.writer(response)
        writer.writerow(["Student No", "First name", "Last name", "Level", "Section", "Status", "Balance"])
        for s in qs:
            writer.writerow([s.student_no, s.person.first_name, s.person.last_name, s.current_level,
                             s.current_section, s.status, s.balance])
        log_event("student.exported", request=request, changes={"rows": qs.count()})
        return response

    # ------------------------------------------------------------------ photo
    @action(detail=True, methods=["get"], parser_classes=[MultiPartParser, FormParser])
    def photo(self, request, pk=None):
        """The student's photo, for anyone allowed to see the student record."""
        student = self.get_object()
        if not student.photo:
            raise Http404("No photo.")
        ctype = "image/png" if student.photo.name.endswith(".png") else "image/jpeg"
        response = FileResponse(student.photo.open("rb"), content_type=ctype)
        response["Cache-Control"] = "private, max-age=86400"
        return response

    @photo.mapping.post
    def upload_photo(self, request, pk=None):
        student = self.get_object()
        f = request.FILES.get("photo")
        kind = sniff_image(f)
        old = student.photo.name if student.photo else None
        student.photo.save(f"photo.{kind}", f, save=False)
        student.save(update_fields=["photo", "updated_at"])
        if old:
            student.photo.storage.delete(old)
        log_event("student.photo_updated", request=request, target=student)
        return Response(StudentDetailSerializer(student, context={"request": request}).data)

    @photo.mapping.delete
    def remove_photo(self, request, pk=None):
        student = self.get_object()
        if student.photo:
            student.photo.delete(save=False)
            student.photo = ""
            student.save(update_fields=["photo", "updated_at"])
            log_event("student.photo_removed", request=request, target=student)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="portal-account")
    def portal_account(self, request, pk=None):
        student = self.get_object()
        return _invite_portal_user(request, student, "pupil" if request.user.tenant.is_school else "student")


class GuardianViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Guardian.objects.select_related("person")
    serializer_class = GuardianSerializer
    required_perms = {"*": "students.manage", "list": "students.view", "retrieve": "students.view"}
    search_fields = ["person__first_name", "person__last_name", "person__email", "person__phone"]

    def perform_create(self, serializer):
        obj = serializer.save()
        log_event("guardian.created", request=self.request, target=obj)

    @action(detail=True, methods=["post"], url_path="portal-account")
    def portal_account(self, request, pk=None):
        return _invite_portal_user(request, self.get_object(), "guardian")


class GuardianLinkViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = GuardianLink.objects.select_related("guardian__person", "student__person")
    serializer_class = GuardianLinkSerializer
    required_perms = {"*": "students.manage", "list": "students.view", "retrieve": "students.view"}
    filterset_fields = ["student", "guardian"]

    @transaction.atomic
    def perform_create(self, serializer):
        link = serializer.save(tenant=self.tenant)
        if link.is_primary:
            GuardianLink.objects.filter(student=link.student).exclude(pk=link.pk).update(is_primary=False)
        log_event("guardian_link.created", request=self.request, target=link,
                  changes={"guardian": link.guardian_id, "student": link.student_id})


class EmergencyContactViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = EmergencyContact.objects.all()
    serializer_class = EmergencyContactSerializer
    required_perms = {"*": "students.manage", "list": "students.view", "retrieve": "students.view"}
    filterset_fields = ["student"]


class StaffViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Staff.objects.select_related("person", "user__role")
    serializer_class = StaffSerializer
    required_perms = {"*": "staff.manage", "list": "staff.view", "retrieve": "staff.view"}
    search_fields = ["staff_no", "person__first_name", "person__last_name", "job_title", "department"]
    filterset_fields = ["status", "department"]
