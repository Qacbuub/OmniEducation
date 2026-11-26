from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.dispatch import Signal
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

from . import emails, mfa
from .audit import log_event
from .models import AuditEvent, Invitation, Tenant, User
from .permissions import AUTHENTICATED, IsPlatformAdmin, IsTenantUser, RolePermission
from .serializers import (
    AuditEventSerializer,
    ChangePasswordSerializer,
    InvitationAcceptSerializer,
    InvitationSerializer,
    LoginSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileUpdateSerializer,
    StaffUserSerializer,
    TenantCreateSerializer,
    TenantSerializer,
    TenantSettingsSerializer,
)

# Sent after an invited user sets their password; the people app creates their staff profile.
user_joined = Signal()


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role_code
    refresh["tenant"] = user.tenant_id
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


# --------------------------------------------------------------------------- auth
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(request=LoginSerializer, responses={200: MeSerializer})
    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = s.validated_data["email"].lower()
        user = authenticate(request, email=email, password=s.validated_data["password"])
        if user is None:
            log_event("auth.login_failed", request=request, changes={"email": email})
            # Returned (not raised) so the request transaction commits and the failed attempt stays audited.
            return Response({"code": "invalid_credentials", "message": "Invalid email or password.", "fields": {}},
                            status=status.HTTP_401_UNAUTHORIZED)
        if user.tenant_id and user.tenant.status == Tenant.Status.SUSPENDED:
            raise AuthenticationFailed("This institution's account is suspended.", code="tenant_suspended")
        if user.mfa_enabled:
            otp = s.validated_data.get("otp")
            if not otp:
                return Response({"code": "mfa_required", "message": "Enter the 6-digit code from your authenticator app.",
                                 "fields": {}}, status=status.HTTP_401_UNAUTHORIZED)
            if not mfa.verify(user.mfa_secret, otp):
                raise AuthenticationFailed("The authentication code is incorrect.", code="mfa_invalid")
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        log_event("auth.login", request=request, actor=user, target=user)
        return Response({**issue_tokens(user), "user": MeSerializer(user).data})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            RefreshToken(request.data.get("refresh", "")).blacklist()
        except TokenError:
            pass  # already invalid: logging out is still successful
        log_event("auth.logout", request=request, target=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TokenForkView(APIView):
    """Give a new browser tab its own session, started from a valid refresh token of the same browser.

    Unlike a refresh, the original token stays valid, so signing out in one tab does not sign out the other.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        try:
            token = RefreshToken(request.data.get("refresh", ""))
            user = User.objects.get(pk=token["user_id"], is_active=True)
        except (TokenError, KeyError, User.DoesNotExist):
            raise AuthenticationFailed("Session expired. Please sign in again.", code="token_not_valid")
        if user.tenant_id and user.tenant.status == Tenant.Status.SUSPENDED:
            raise AuthenticationFailed("This institution is suspended.", code="tenant_suspended")
        return Response(issue_tokens(user))


class MeView(generics.RetrieveAPIView):
    """The signed-in account. PATCH updates name and phone only."""

    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    @extend_schema(request=ProfileUpdateSerializer, responses=MeSerializer)
    def patch(self, request):
        s = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        before = {f: getattr(request.user, f) for f in s.validated_data}
        s.save()
        log_event("auth.profile_updated", request=request, target=request.user,
                  changes={f: [before[f], v] for f, v in s.validated_data.items() if before[f] != v})
        return Response(MeSerializer(request.user).data)


class ChangePasswordView(APIView):
    """Change your own password (needs the current one). Other sessions are signed out."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_change"

    @extend_schema(request=ChangePasswordSerializer)
    def post(self, request):
        s = ChangePasswordSerializer(data=request.data, context={"user": request.user})
        s.is_valid(raise_exception=True)
        request.user.set_password(s.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        for token in OutstandingToken.objects.filter(user=request.user):
            BlacklistedToken.objects.get_or_create(token=token)
        log_event("auth.password_changed", request=request, target=request.user)
        return Response({"message": "Password changed.", **issue_tokens(request.user)})


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"
    GENERIC = "If an account exists for that email, a reset link has been sent."

    @extend_schema(request=PasswordResetRequestSerializer)
    def post(self, request):
        s = PasswordResetRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = User.objects.filter(email=s.validated_data["email"].lower(), is_active=True).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            emails.send_password_reset(user, uid, default_token_generator.make_token(user))
            log_event("auth.password_reset_requested", request=request, actor=user, target=user)
        # Same answer either way, so the endpoint can't be used to discover accounts.
        return Response({"message": self.GENERIC})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=PasswordResetConfirmSerializer)
    def post(self, request):
        try:
            uid = force_str(urlsafe_base64_decode(request.data.get("uid", "")))
            user = User.objects.get(pk=uid, is_active=True)
        except (ValueError, TypeError, OverflowError, User.DoesNotExist):
            user = None
        if user is None or not default_token_generator.check_token(user, request.data.get("token", "")):
            raise ValidationError({"token": ["This reset link is invalid or has expired."]})
        s = PasswordResetConfirmSerializer(data=request.data, context={"user": user})
        s.is_valid(raise_exception=True)
        user.set_password(s.validated_data["new_password"])
        user.save(update_fields=["password"])
        # Sign the user out everywhere.
        for t in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=t)
        log_event("auth.password_reset", request=request, actor=user, target=user)
        return Response({"message": "Your password has been reset. You can now sign in."})


class InvitationLookupView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        inv = get_object_or_404(Invitation, token=token)
        if inv.status != "pending":
            raise ValidationError({"token": [f"This invitation has {inv.status}."]})
        return Response({"email": inv.email, "first_name": inv.first_name, "last_name": inv.last_name,
                         "role": inv.role.name, "institution": inv.tenant.name if inv.tenant else None})


class InvitationAcceptView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=InvitationAcceptSerializer)
    @transaction.atomic
    def post(self, request):
        inv = Invitation.objects.select_for_update().filter(token=request.data.get("token", "")).first()
        if inv is None or inv.status != "pending":
            raise ValidationError({"token": ["This invitation is invalid, expired or already used."]})
        s = InvitationAcceptSerializer(data=request.data, context={"user": User(email=inv.email)})
        s.is_valid(raise_exception=True)
        if User.objects.filter(email=inv.email).exists():
            raise ValidationError({"token": ["An account with this email already exists."]})
        user = User.objects.create_user(
            email=inv.email, password=s.validated_data["new_password"], tenant=inv.tenant, role=inv.role,
            first_name=s.validated_data["first_name"], last_name=s.validated_data["last_name"],
        )
        inv.accepted_at = timezone.now()
        inv.save(update_fields=["accepted_at"])
        user_joined.send(sender=User, user=user)
        log_event("invitation.accepted", request=request, actor=user, tenant=inv.tenant, target=inv)
        return Response({**issue_tokens(user), "user": MeSerializer(user).data}, status=status.HTTP_201_CREATED)


class MfaSetupView(APIView):
    """Start MFA enrolment (returns a secret + otpauth URI), then confirm with a valid code."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        secret = mfa.new_secret()
        return Response({"secret": secret, "otpauth_uri": mfa.provisioning_uri(secret, request.user.email)})

    def post(self, request):
        secret = request.data.get("secret", "")
        if not mfa.verify(secret, request.data.get("code", "")):
            raise ValidationError({"code": ["The code is incorrect. Check your authenticator app's clock."]})
        request.user.mfa_secret, request.user.mfa_enabled = secret, True
        request.user.save(update_fields=["mfa_secret", "mfa_enabled"])
        log_event("auth.mfa_enabled", request=request, target=request.user)
        return Response({"mfa_enabled": True})

    def delete(self, request):
        """Turn MFA off; needs a current code (or the password) so a stolen session cannot do it."""
        user = request.user
        code, password = request.data.get("code", ""), request.data.get("password", "")
        if not user.mfa_enabled:
            return Response({"mfa_enabled": False})
        if not (mfa.verify(user.mfa_secret, code) or (password and user.check_password(password))):
            raise ValidationError({"code": ["Enter a current code from your authenticator app, or your password."]})
        user.mfa_secret, user.mfa_enabled = "", False
        user.save(update_fields=["mfa_secret", "mfa_enabled"])
        log_event("auth.mfa_disabled", request=request, target=user)
        return Response({"mfa_enabled": False})


# --------------------------------------------------------------------------- platform
def _tenant_queryset():
    from people.models import Student

    students = Student.objects.filter(tenant=OuterRef("pk")).order_by().values("tenant").annotate(c=Count("id")).values("c")
    return Tenant.objects.annotate(
        students=Coalesce(Subquery(students, output_field=IntegerField()), 0),
        staff=Count("users", distinct=True),
    )


class TenantViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                    mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Platform administration of institutions. Platform admins never see student records here."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    search_fields = ["name", "slug", "city", "country"]
    filterset_fields = ["type", "status", "plan"]
    ordering_fields = ["name", "created_at"]

    def get_queryset(self):
        return _tenant_queryset().order_by("name")

    def get_serializer_class(self):
        return TenantCreateSerializer if self.action == "create" else TenantSerializer

    def create(self, request, *args, **kwargs):
        s = TenantCreateSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        tenant = s.save()
        emails.send_invitation(s.invitation)
        log_event("tenant.created", request=request, tenant=tenant, target=tenant, changes={"type": tenant.type})
        log_event("invitation.sent", request=request, tenant=tenant, target=s.invitation,
                  changes={"email": s.invitation.email, "role": "inst_admin"})
        return Response(TenantSerializer(_tenant_queryset().get(pk=tenant.pk)).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        tenant = serializer.save()
        log_event("tenant.updated", request=self.request, tenant=tenant, target=tenant,
                  changes={k: str(v) for k, v in serializer.validated_data.items()})

    @action(detail=True, methods=["post"], url_path="invite-admin")
    def invite_admin(self, request, pk=None):
        """Re-invite / add another administrator for an institution."""
        from .models import Role

        tenant = self.get_object()
        email = str(request.data.get("email", "")).strip().lower()
        if "@" not in email:
            raise ValidationError({"email": ["Enter a valid email address."]})
        if User.objects.filter(email=email).exists():
            raise ValidationError({"email": ["A user with this email already exists."]})
        inv = Invitation.objects.create(tenant=tenant, email=email, role=Role.objects.get(code="inst_admin"),
                                        invited_by=request.user)
        emails.send_invitation(inv)
        log_event("invitation.sent", request=request, tenant=tenant, target=inv, changes={"email": inv.email})
        return Response(InvitationSerializer(inv).data, status=status.HTTP_201_CREATED)


class PlatformInvitationListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = InvitationSerializer
    queryset = Invitation.objects.filter(role__code="inst_admin").select_related("role", "invited_by", "tenant")


class PlatformStatsView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        tenants = Tenant.objects.all()
        recent = AuditEvent.objects.filter(Q(action__startswith="tenant.") | Q(action="invitation.sent"))
        return Response({
            "institutions": tenants.count(),
            "schools": tenants.filter(type="school").count(),
            "universities": tenants.filter(type="university").count(),
            "active_users": User.objects.filter(is_active=True).count(),
            "pending_invitations": sum(1 for i in Invitation.objects.filter(accepted_at__isnull=True) if i.status == "pending"),
            "recent_activity": [
                {"id": e.id, "action": e.action, "actor": e.actor_email, "target": e.target_repr,
                 "at": e.created_at.strftime("%Y-%m-%d %H:%M")}
                for e in recent.order_by("-created_at")[:10]
            ],
        })


class PlatformAuditView(generics.ListAPIView):
    """Platform-level actions only (institution provisioning, invitations)."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = AuditEventSerializer
    search_fields = ["action", "actor_email", "target_repr"]

    def get_queryset(self):
        return AuditEvent.objects.filter(action__regex=r"^(tenant|invitation)\.")


# --------------------------------------------------------------------------- institution
class CurrentTenantView(generics.RetrieveUpdateAPIView):
    """GET: any institution user (branding). PATCH: institution admins only."""

    serializer_class = TenantSettingsSerializer
    permission_classes = [IsAuthenticated, IsTenantUser, RolePermission]
    required_perms = {"get": AUTHENTICATED, "put": "tenant.manage_settings", "patch": "tenant.manage_settings"}

    def get_object(self):
        return self.request.user.tenant

    def perform_update(self, serializer):
        tenant = serializer.save()
        log_event("tenant.settings_updated", request=self.request, target=tenant,
                  changes={k: str(v)[:200] for k, v in serializer.validated_data.items()})


class InvitationViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin,
                        viewsets.GenericViewSet):
    """Institution admins invite staff (teachers, lecturers, finance officers, ...)."""

    serializer_class = InvitationSerializer
    permission_classes = [IsAuthenticated, IsTenantUser, RolePermission]
    required_perms = {"*": "staff.manage"}

    def get_queryset(self):
        return Invitation.objects.filter(tenant=self.request.user.tenant).select_related("role", "invited_by")

    def perform_create(self, serializer):
        inv = serializer.save(tenant=self.request.user.tenant, invited_by=self.request.user)
        emails.send_invitation(inv)
        log_event("invitation.sent", request=self.request, target=inv, changes={"email": inv.email, "role": inv.role.code})

    def perform_destroy(self, instance):
        if instance.accepted_at:
            raise ValidationError({"detail": ["An accepted invitation cannot be revoked; deactivate the user instead."]})
        log_event("invitation.revoked", request=self.request, target=instance)
        instance.delete()


class StaffUserViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                       viewsets.GenericViewSet):
    """User accounts within the institution (role changes and deactivation)."""

    serializer_class = StaffUserSerializer
    permission_classes = [IsAuthenticated, IsTenantUser, RolePermission]
    required_perms = {"list": "staff.view", "retrieve": "staff.view", "update": "staff.manage",
                      "partial_update": "staff.manage"}
    search_fields = ["email", "first_name", "last_name"]
    filterset_fields = {"role__code": ["exact"], "is_active": ["exact"]}

    def get_queryset(self):
        return User.objects.filter(tenant=self.request.user.tenant).select_related("role")

    def perform_update(self, serializer):
        before = {"role": serializer.instance.role_code, "is_active": serializer.instance.is_active}
        user = serializer.save()
        log_event("user.updated", request=self.request, target=user,
                  changes={"before": before, "after": {"role": user.role_code, "is_active": user.is_active}})


class AuditLogView(generics.ListAPIView):
    serializer_class = AuditEventSerializer
    permission_classes = [IsAuthenticated, IsTenantUser, RolePermission]
    required_perms = {"get": "audit.view"}
    search_fields = ["action", "actor_email", "target_repr"]
    filterset_fields = {"action": ["exact", "startswith"], "target_type": ["exact"], "target_id": ["exact"]}

    def get_queryset(self):
        return AuditEvent.objects.filter(tenant=self.request.user.tenant)
