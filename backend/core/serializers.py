from django.conf import settings
from django.contrib.auth import password_validation
from django.db import transaction
from rest_framework import serializers

from .models import AuditEvent, Invitation, Role, Tenant, User
from .rbac import role_allowed_for_tenant


class TenantSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "type", "currency", "accent_color", "logo"]


class MeSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="role_code", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True, default=None)
    tenant = TenantSummarySerializer(read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "phone", "role", "role_name", "tenant",
                  "permissions", "mfa_enabled", "last_login"]

    def get_permissions(self, obj):
        return sorted(obj.permission_codes())


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """What people may change about their own account (email and role are managed by admins)."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone"]
        extra_kwargs = {"first_name": {"required": True, "allow_blank": False},
                        "last_name": {"required": True, "allow_blank": False}}


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)
    otp = serializers.CharField(required=False, allow_blank=True, max_length=6)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class SetPasswordMixin(serializers.Serializer):
    new_password = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate_new_password(self, value):
        password_validation.validate_password(value, user=self.context.get("user"))
        return value


class ChangePasswordSerializer(SetPasswordMixin):
    current_password = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate_current_password(self, value):
        if not self.context["user"].check_password(value):
            raise serializers.ValidationError("Your current password is incorrect.")
        return value


class PasswordResetConfirmSerializer(SetPasswordMixin):
    uid = serializers.CharField()
    token = serializers.CharField()


class InvitationAcceptSerializer(SetPasswordMixin):
    token = serializers.CharField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)


def invite_link(invitation, force=False):
    """The accept link, only where settings allow showing it (local demo with console email), or when `force`
    is set because the email could not be sent and the inviting staff member must pass the link on."""
    if not (force or getattr(settings, "SHOW_INVITE_LINKS", False)):
        return None
    return f"{settings.FRONTEND_URL}/accept-invitation?token={invitation.token}"


class InvitationSerializer(serializers.ModelSerializer):
    role = serializers.SlugRelatedField(slug_field="code", queryset=Role.objects.all())
    role_name = serializers.CharField(source="role.name", read_only=True)
    status = serializers.CharField(read_only=True)
    invited_by = serializers.EmailField(source="invited_by.email", read_only=True, default=None)
    tenant = serializers.PrimaryKeyRelatedField(read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True, default=None)
    invite_link = serializers.SerializerMethodField()

    class Meta:
        model = Invitation
        fields = ["id", "email", "first_name", "last_name", "role", "role_name", "status", "invited_by", "tenant",
                  "tenant_name", "expires_at", "accepted_at", "created_at", "invite_link"]
        read_only_fields = ["expires_at", "accepted_at", "created_at"]

    def get_invite_link(self, obj) -> str | None:
        return invite_link(obj) if obj.accepted_at is None else None

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_role(self, role):
        tenant = self.context["request"].user.tenant
        if role.code in ("guardian", "pupil", "student"):
            raise serializers.ValidationError("Portal accounts for guardians and students are created from their profiles.")
        if not role_allowed_for_tenant(role.code, tenant.type):
            raise serializers.ValidationError(f"The {role.name} role is not available for this institution type.")
        return role


class TenantSerializer(serializers.ModelSerializer):
    students = serializers.IntegerField(read_only=True, default=0)
    staff = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "type", "status", "plan", "domain", "contact_email", "contact_phone",
                  "address", "city", "country", "currency", "timezone", "accent_color", "students", "staff",
                  "created_at"]
        read_only_fields = ["slug", "type", "domain", "created_at"]


class TenantCreateSerializer(serializers.ModelSerializer):
    """Platform admin provisions an institution and invites its first administrator in one step."""

    admin_email = serializers.EmailField(write_only=True)
    admin_first_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    admin_last_name = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "type", "plan", "city", "country", "contact_email", "currency",
                  "timezone", "admin_email", "admin_first_name", "admin_last_name"]

    def validate_admin_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    @transaction.atomic
    def create(self, validated):
        admin = {k: validated.pop(k, "") for k in ("admin_email", "admin_first_name", "admin_last_name")}
        tenant = Tenant.objects.create(**validated)
        self.invitation = Invitation.objects.create(
            tenant=tenant, email=admin["admin_email"], first_name=admin["admin_first_name"],
            last_name=admin["admin_last_name"], role=Role.objects.get(code="inst_admin"),
            invited_by=self.context["request"].user,
        )
        return tenant


class TenantSettingsSerializer(serializers.ModelSerializer):
    """Institution admins edit their own tenant's branding and academic settings."""

    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "type", "contact_email", "contact_phone", "address", "city", "country",
                  "logo", "accent_color", "currency", "timezone", "student_id_prefix", "grading_scale", "policies"]
        read_only_fields = ["slug", "type"]

    def validate_grading_scale(self, scale):
        if not isinstance(scale, list) or not scale:
            raise serializers.ValidationError("Provide at least one grading band.")
        mins = []
        for band in scale:
            if not isinstance(band, dict) or not {"min", "grade", "points"} <= band.keys():
                raise serializers.ValidationError("Each band needs min, grade and points.")
            if not 0 <= float(band["min"]) <= 100 or not 0 <= float(band["points"]) <= 5:
                raise serializers.ValidationError("min must be 0–100 and points 0–5.")
            mins.append(float(band["min"]))
        if 0 not in mins:
            raise serializers.ValidationError("One band must start at 0 so every score has a grade.")
        if len(set(mins)) != len(mins):
            raise serializers.ValidationError("Two bands cannot start at the same score.")
        return sorted(scale, key=lambda b: float(b["min"]), reverse=True)

    def validate_policies(self, policies):
        if not isinstance(policies, dict):
            raise serializers.ValidationError("Policies must be an object.")
        for key, value in policies.items():
            if isinstance(value, (int, float)) and value < 0:
                raise serializers.ValidationError(f"{key} cannot be negative.")
        if policies.get("min_credits", 0) > policies.get("max_credits", 10**6):
            raise serializers.ValidationError("min_credits cannot exceed max_credits.")
        return policies


class StaffUserSerializer(serializers.ModelSerializer):
    role = serializers.SlugRelatedField(slug_field="code", queryset=Role.objects.all())
    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "phone", "role", "role_name", "is_active", "last_login"]
        read_only_fields = ["email", "last_login"]

    def validate_role(self, role):
        request = self.context["request"]
        if self.instance and self.instance.pk == request.user.pk and role != request.user.role:
            raise serializers.ValidationError("You cannot change your own role.")
        if not role_allowed_for_tenant(role.code, request.user.tenant.type):
            raise serializers.ValidationError("This role is not available for this institution type.")
        return role

    def validate_is_active(self, value):
        request = self.context["request"]
        if self.instance and self.instance.pk == request.user.pk and not value:
            raise serializers.ValidationError("You cannot deactivate your own account.")
        return value


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ["id", "action", "actor_email", "target_type", "target_id", "target_repr", "changes",
                  "ip_address", "created_at"]
