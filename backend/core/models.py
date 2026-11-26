import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

SCHOOL_GRADING_SCALE = [
    {"min": 80, "grade": "A", "points": 4.0, "remark": "Excellent"},
    {"min": 70, "grade": "B", "points": 3.0, "remark": "Very good"},
    {"min": 60, "grade": "C", "points": 2.0, "remark": "Good"},
    {"min": 50, "grade": "D", "points": 1.0, "remark": "Pass"},
    {"min": 0, "grade": "E", "points": 0.0, "remark": "Fail"},
]
UNIVERSITY_GRADING_SCALE = [
    {"min": 90, "grade": "A", "points": 4.0},
    {"min": 85, "grade": "A-", "points": 3.7},
    {"min": 80, "grade": "B+", "points": 3.3},
    {"min": 75, "grade": "B", "points": 3.0},
    {"min": 70, "grade": "B-", "points": 2.7},
    {"min": 65, "grade": "C+", "points": 2.3},
    {"min": 60, "grade": "C", "points": 2.0},
    {"min": 50, "grade": "D", "points": 1.0},
    {"min": 0, "grade": "F", "points": 0.0},
]
# Configurable policy defaults (documented in docs/business-rules.md).
SCHOOL_POLICIES = {"pass_mark": 50, "promotion_min_average": 50, "attendance_alert_absences": 3}
UNIVERSITY_POLICIES = {
    "min_credits": 12, "max_credits": 21, "overload_max_credits": 24, "overload_min_cgpa": 3.5,
    "probation_cgpa": 2.0, "graduation_min_cgpa": 2.0, "pass_grade_points": 1.0,
    "repeat_policy": "latest_attempt",
}


class Tenant(models.Model):
    """An institution. Every institution-owned row references exactly one tenant."""

    class Type(models.TextChoices):
        SCHOOL = "school", "School (K-12)"
        UNIVERSITY = "university", "University"

    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    class Plan(models.TextChoices):
        STARTER = "Starter", "Starter"
        STANDARD = "Standard", "Standard"
        ENTERPRISE = "Enterprise", "Enterprise"

    name = models.CharField(max_length=200)
    slug = models.SlugField(
        max_length=30, unique=True,
        validators=[RegexValidator(r"^[a-z0-9-]{3,30}$", "3–30 lowercase letters, numbers or hyphens.")],
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIAL)
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.STARTER)
    domain = models.CharField(max_length=255, blank=True)
    # Contact & branding
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    logo = models.FileField(upload_to="tenant-logos/", blank=True)
    accent_color = models.CharField(
        max_length=7, default="#00AEFF", validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Use a hex colour like #00AEFF.")]
    )
    # Academic settings
    currency = models.CharField(max_length=3, default="KES")
    timezone = models.CharField(max_length=64, default="Africa/Nairobi")
    student_id_prefix = models.CharField(max_length=8, blank=True)
    grading_scale = models.JSONField(default=list, blank=True)
    policies = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_school(self):
        return self.type == self.Type.SCHOOL

    @property
    def is_university(self):
        return self.type == self.Type.UNIVERSITY

    def save(self, *args, **kwargs):
        if not self.grading_scale:
            self.grading_scale = SCHOOL_GRADING_SCALE if self.is_school else UNIVERSITY_GRADING_SCALE
        defaults = SCHOOL_POLICIES if self.is_school else UNIVERSITY_POLICIES
        self.policies = {**defaults, **(self.policies or {})}
        if not self.student_id_prefix:
            self.student_id_prefix = self.slug[:4].upper()
        if not self.domain:
            self.domain = f"{self.slug}.omniedu.app"
        super().save(*args, **kwargs)

    def policy(self, key):
        defaults = SCHOOL_POLICIES if self.is_school else UNIVERSITY_POLICIES
        return (self.policies or {}).get(key, defaults.get(key))

    def grade_for(self, score):
        """Map a percentage score to the tenant's grading-scale band."""
        for band in sorted(self.grading_scale, key=lambda b: b["min"], reverse=True):
            if float(score) >= band["min"]:
                return band
        return self.grading_scale[-1]


class TenantScopedModel(models.Model):
    """Abstract base for every institution-owned table."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="+", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Permission(models.Model):
    code = models.CharField(max_length=64, unique=True)
    description = models.CharField(max_length=255)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class Role(models.Model):
    class Scope(models.TextChoices):
        PLATFORM = "platform"
        SHARED = "shared"
        SCHOOL = "school"
        UNIVERSITY = "university"

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=64)
    scope = models.CharField(max_length=16, choices=Scope.choices)
    permissions = models.ManyToManyField(Permission, blank=True, related_name="roles")

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True)
        extra.setdefault("role", Role.objects.filter(code="super_admin").first())
        return self._create(email, password, **extra)


class User(AbstractUser):
    """Shared identity. Platform super admins have no tenant; everyone else belongs to exactly one."""

    username = None
    email = models.EmailField(unique=True)
    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.CASCADE, related_name="users")
    role = models.ForeignKey(Role, null=True, on_delete=models.PROTECT, related_name="users")
    phone = models.CharField(max_length=40, blank=True)
    # MFA-ready: a TOTP secret can be enrolled per user; login checks it when enabled.
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.CharField(max_length=64, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        if self.role_id and self.role.code == "super_admin" and self.tenant_id:
            raise ValidationError("Platform super admins cannot belong to an institution.")
        if self.role_id and self.role.code != "super_admin" and not self.tenant_id:
            raise ValidationError("Institution users must belong to an institution.")

    @property
    def role_code(self):
        return self.role.code if self.role_id else None

    @property
    def is_platform_admin(self):
        return self.role_code == "super_admin"

    def permission_codes(self):
        if not hasattr(self, "_perm_cache"):
            self._perm_cache = set(self.role.permissions.values_list("code", flat=True)) if self.role_id else set()
        return self._perm_cache

    def has_perm_code(self, *codes):
        return bool(self.permission_codes() & set(codes))


def _invite_token():
    return secrets.token_urlsafe(32)


def _invite_expiry():
    return timezone.now() + timedelta(days=7)


class Invitation(models.Model):
    """Single-use invitation for a tenant administrator or staff member to set their password."""

    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    token = models.CharField(max_length=64, unique=True, default=_invite_token)
    invited_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    expires_at = models.DateTimeField(default=_invite_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def status(self):
        if self.accepted_at:
            return "accepted"
        return "expired" if self.expires_at < timezone.now() else "pending"


class AuditEvent(models.Model):
    """Append-only activity log. Rows can't be updated or deleted through the ORM."""

    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor_email = models.EmailField(blank=True)
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    target_repr = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Audit events are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events are immutable.")
