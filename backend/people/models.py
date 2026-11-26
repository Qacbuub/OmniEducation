import uuid

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from core.models import Tenant, TenantScopedModel


class Person(TenantScopedModel):
    """Shared identity details for students, guardians and staff."""

    class Gender(models.TextChoices):
        FEMALE = "female"
        MALE = "male"
        OTHER = "other"
        UNDISCLOSED = "undisclosed"

    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    national_id = models.CharField("ID / birth certificate no.", max_length=40, blank=True)
    gender = models.CharField(max_length=16, choices=Gender.choices, default=Gender.UNDISCLOSED)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        indexes = [models.Index(fields=["tenant", "last_name", "first_name"])]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return " ".join(p for p in (self.first_name, self.middle_name, self.last_name) if p)


def student_photo_path(instance, filename):
    # Random names: photos are never guessable and are only served through the permission-checked API.
    ext = ".png" if filename.lower().endswith(".png") else ".jpg"
    return f"photos/{instance.tenant_id}/{uuid.uuid4().hex}{ext}"


class Student(TenantScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "active"
        SUSPENDED = "suspended"
        WITHDRAWN = "withdrawn"
        TRANSFERRED = "transferred"
        COMPLETED = "completed"   # K-12 completion
        GRADUATED = "graduated"   # university graduation

    person = models.OneToOneField(Person, on_delete=models.PROTECT, related_name="student")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="student_profile")
    student_no = models.CharField(max_length=32)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    admission_date = models.DateField(default=timezone.localdate)
    # Denormalised labels maintained by the school/university modules for fast lists and search.
    current_level = models.CharField(max_length=120, blank=True, help_text="Grade level or program")
    current_section = models.CharField(max_length=60, blank=True, help_text="Class section or year of study")
    application = models.OneToOneField("admissions.Application", null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name="student")
    photo = models.FileField(upload_to=student_photo_path, blank=True)

    class Meta:
        ordering = ["person__last_name", "person__first_name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "student_no"], name="unique_student_no_per_tenant")]

    def __str__(self):
        return f"{self.person.full_name} ({self.student_no})"

    @staticmethod
    def next_student_no(tenant):
        """PREFIX-YEAR-NNNN, sequential per tenant and year. Locks the tenant row to avoid duplicates."""
        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=tenant.pk)
            year = timezone.localdate().year
            prefix = f"{tenant.student_id_prefix}-{year}-"
            last = (Student.objects.filter(tenant=tenant, student_no__startswith=prefix)
                    .order_by("-student_no").values_list("student_no", flat=True).first())
            seq = int(last.rsplit("-", 1)[1]) + 1 if last else 1
            return f"{prefix}{seq:04d}"


class EmergencyContact(TenantScopedModel):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="emergency_contacts")
    name = models.CharField(max_length=150)
    relationship = models.CharField(max_length=60)
    phone = models.CharField(max_length=40)
    email = models.EmailField(blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "name"]


class Guardian(TenantScopedModel):
    person = models.OneToOneField(Person, on_delete=models.PROTECT, related_name="guardian")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="guardian_profile")
    occupation = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["person__last_name", "person__first_name"]

    def __str__(self):
        return self.person.full_name


class GuardianLink(TenantScopedModel):
    """A guardian may view only the students they are linked to."""

    guardian = models.ForeignKey(Guardian, on_delete=models.CASCADE, related_name="links")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="guardian_links")
    relationship = models.CharField(max_length=40, default="parent")
    is_primary = models.BooleanField(default=False)
    receives_notifications = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["guardian", "student"], name="unique_guardian_student")]
        ordering = ["-is_primary"]


class Staff(TenantScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "active"
        ON_LEAVE = "on_leave"
        LEFT = "left"

    person = models.OneToOneField(Person, on_delete=models.PROTECT, related_name="staff")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="staff_profile")
    staff_no = models.CharField(max_length=32)
    job_title = models.CharField(max_length=120, blank=True)
    department = models.CharField(max_length=120, blank=True)
    hire_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        verbose_name_plural = "staff"
        ordering = ["person__last_name", "person__first_name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "staff_no"], name="unique_staff_no_per_tenant")]

    def __str__(self):
        return f"{self.person.full_name} ({self.job_title})"
