import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TenantScopedModel
from core.numbering import next_code


class AcademicPeriod(TenantScopedModel):
    """Academic years plus their terms (schools) or semesters (universities)."""

    class Kind(models.TextChoices):
        ACADEMIC_YEAR = "academic_year", "Academic year"
        TERM = "term", "Term"
        SEMESTER = "semester", "Semester"

    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "kind", "name"], name="unique_period_name"),
            models.UniqueConstraint(fields=["tenant", "kind"], condition=models.Q(is_current=True),
                                    name="one_current_period_per_kind"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError({"end_date": "End date must be after the start date."})
        if self.kind == self.Kind.TERM and not self.tenant.is_school:
            raise ValidationError({"kind": "Terms are used by schools. Universities use semesters."})
        if self.kind == self.Kind.SEMESTER and not self.tenant.is_university:
            raise ValidationError({"kind": "Semesters are used by universities. Schools use terms."})
        if self.kind == self.Kind.ACADEMIC_YEAR and self.parent_id:
            raise ValidationError({"parent": "An academic year cannot have a parent."})
        if self.kind != self.Kind.ACADEMIC_YEAR:
            if not self.parent_id or self.parent.kind != self.Kind.ACADEMIC_YEAR:
                raise ValidationError({"parent": "Choose the academic year this period belongs to."})
            if self.start_date < self.parent.start_date or self.end_date > self.parent.end_date:
                raise ValidationError({"start_date": "The period must fall inside its academic year."})


def applicant_photo_path(instance, filename):
    import uuid
    ext = ".png" if filename.lower().endswith(".png") else ".jpg"
    return f"photos/{instance.tenant_id}/{uuid.uuid4().hex}{ext}"


class Application(TenantScopedModel):
    class Status(models.TextChoices):
        SUBMITTED = "submitted"
        UNDER_REVIEW = "under_review"
        APPROVED = "approved"            # school: admission approved
        OFFERED = "offered"              # university: offer made
        OFFER_ACCEPTED = "offer_accepted"
        OFFER_DECLINED = "offer_declined"
        REJECTED = "rejected"
        WITHDRAWN = "withdrawn"
        ENROLLED = "enrolled"            # school: enrolled pupil; university: matriculated

    # Allowed workflow transitions per institution type.
    SCHOOL_FLOW = {
        "submitted": {"under_review", "rejected", "withdrawn"},
        "under_review": {"approved", "rejected", "withdrawn"},
        "approved": {"enrolled", "withdrawn"},
        "withdrawn": {"under_review"},  # reopen an application withdrawn by mistake
    }
    UNIVERSITY_FLOW = {
        "submitted": {"under_review", "rejected", "withdrawn"},
        "under_review": {"offered", "rejected", "withdrawn"},
        "offered": {"offer_accepted", "offer_declined"},
        "offer_accepted": {"enrolled", "withdrawn"},
        "withdrawn": {"under_review"},  # reopen an application withdrawn by mistake
    }

    application_no = models.CharField(max_length=32)
    reference_code = models.CharField(max_length=16, unique=True, editable=False)  # applicant status lookup
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    source = models.CharField(max_length=10, choices=[("online", "Online"), ("staff", "Staff")], default="online")
    # Applicant
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    national_id = models.CharField("ID / birth certificate no.", max_length=40, blank=True)
    photo = models.FileField(upload_to=applicant_photo_path, blank=True)
    gender = models.CharField(max_length=16, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)
    previous_school = models.CharField(max_length=200, blank=True)
    # What they apply for: a grade level (school) or a program (university). `target_id` is
    # validated by the matching module; `requested_level` keeps a readable label.
    requested_level = models.CharField(max_length=120)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    intake_period = models.ForeignKey(AcademicPeriod, null=True, blank=True, on_delete=models.SET_NULL)
    # Guardian (required for K-12)
    guardian_name = models.CharField(max_length=150, blank=True)
    guardian_relationship = models.CharField(max_length=40, blank=True)
    guardian_phone = models.CharField(max_length=40, blank=True)
    guardian_email = models.EmailField(blank=True)
    # Review
    submitted_at = models.DateTimeField(default=timezone.now)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        constraints = [models.UniqueConstraint(fields=["tenant", "application_no"], name="unique_application_no")]

    def __str__(self):
        return f"{self.application_no} {self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return " ".join(p for p in (self.first_name, self.middle_name, self.last_name) if p)

    def flow(self):
        return self.SCHOOL_FLOW if self.tenant.is_school else self.UNIVERSITY_FLOW

    def allowed_transitions(self):
        return sorted(self.flow().get(self.status, set()))

    def can_transition(self, new_status):
        return new_status in self.flow().get(self.status, set())

    def save(self, *args, **kwargs):
        if not self.reference_code:
            self.reference_code = secrets.token_hex(5).upper()
        if not self.application_no:
            year = timezone.localdate().year
            self.application_no = next_code(Application.objects.filter(tenant=self.tenant), "application_no",
                                            f"APP-{year}-", 5)
        super().save(*args, **kwargs)


class Enrollment(TenantScopedModel):
    """Enrollment history: one row per placement (year/class or semester/program)."""

    class Status(models.TextChoices):
        ACTIVE = "active"
        PROMOTED = "promoted"
        REPEATED = "repeated"
        TRANSFERRED = "transferred"
        WITHDRAWN = "withdrawn"
        COMPLETED = "completed"
        GRADUATED = "graduated"

    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="enrollments")
    period = models.ForeignKey(AcademicPeriod, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    level_label = models.CharField(max_length=120)
    section_label = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-start_date", "-id"]
        constraints = [models.UniqueConstraint(fields=["student"], condition=models.Q(status="active"),
                                               name="one_active_enrollment_per_student")]

    def __str__(self):
        return f"{self.student} – {self.level_label} ({self.status})"
