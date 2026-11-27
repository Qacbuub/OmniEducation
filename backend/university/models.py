"""
University (higher-education) data model.

Kept separate from the K-12 module: courses, credits, semesters and transcripts live here, while
identity, students, admissions, fees and documents are reused from the shared apps.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import TenantScopedModel


# --------------------------------------------------------------------------- academic structure
class Faculty(TenantScopedModel):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=12)
    dean = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="faculties_led")

    class Meta:
        verbose_name_plural = "faculties"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="unique_faculty_code")]

    def __str__(self):
        return self.name


class Department(TenantScopedModel):
    faculty = models.ForeignKey(Faculty, on_delete=models.PROTECT, related_name="departments")
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=12)
    head = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="departments_led")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="unique_department_code")]

    def __str__(self):
        return self.name


class Program(TenantScopedModel):
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="programs")
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=16)
    award = models.CharField(max_length=40, default="Bachelor's degree")
    duration_years = models.PositiveSmallIntegerField(default=4, validators=[MinValueValidator(1),
                                                                            MaxValueValidator(8)])
    total_credits_required = models.PositiveSmallIntegerField(default=120, validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="unique_program_code")]

    def __str__(self):
        return self.name

    def current_curriculum(self):
        return self.curricula.filter(is_current=True).first() or self.curricula.order_by("-effective_from").first()


class Course(TenantScopedModel):
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="courses")
    code = models.CharField(max_length=16)
    title = models.CharField(max_length=200)
    credit_hours = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    level = models.PositiveSmallIntegerField(default=100, help_text="100 = first-year course, 200 = second-year, …")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="unique_course_code")]

    def __str__(self):
        return f"{self.code} {self.title}"


class CoursePrerequisite(TenantScopedModel):
    """`course` requires a passing result in `prerequisite` (at least `min_grade_points`)."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="prerequisite_links")
    prerequisite = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="required_for")
    min_grade_points = models.DecimalField(max_digits=3, decimal_places=2, default=1.0,
                                           validators=[MinValueValidator(0), MaxValueValidator(4)])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["course", "prerequisite"], name="unique_prerequisite")]

    def __str__(self):
        return f"{self.course.code} requires {self.prerequisite.code}"

    def clean(self):
        if self.course_id and self.course_id == self.prerequisite_id:
            raise ValidationError({"prerequisite": "A course cannot be its own prerequisite."})
        # Reject cycles: the new prerequisite must not (directly or indirectly) require this course.
        seen, frontier = set(), {self.prerequisite_id}
        while frontier:
            if self.course_id in frontier:
                raise ValidationError({"prerequisite": "This would create a circular prerequisite chain."})
            seen |= frontier
            frontier = set(CoursePrerequisite.objects.filter(course_id__in=frontier)
                           .values_list("prerequisite_id", flat=True)) - seen


class Curriculum(TenantScopedModel):
    """A versioned list of the courses a program requires (curriculum mapping)."""

    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="curricula")
    version = models.CharField(max_length=20)
    effective_from = models.DateField()
    elective_credits_required = models.PositiveSmallIntegerField(default=0)
    is_current = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "curricula"
        ordering = ["program__name", "-effective_from"]
        constraints = [
            models.UniqueConstraint(fields=["program", "version"], name="unique_curriculum_version"),
            models.UniqueConstraint(fields=["program"], condition=models.Q(is_current=True),
                                    name="one_current_curriculum_per_program"),
        ]

    def __str__(self):
        return f"{self.program.code} curriculum {self.version}"


class CurriculumCourse(TenantScopedModel):
    class Category(models.TextChoices):
        CORE = "core"
        ELECTIVE = "elective"

    curriculum = models.ForeignKey(Curriculum, on_delete=models.CASCADE, related_name="items")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="curriculum_items")
    category = models.CharField(max_length=10, choices=Category.choices, default=Category.CORE)
    recommended_year = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1),
                                                                              MaxValueValidator(8)])
    recommended_semester = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1),
                                                                                  MaxValueValidator(3)])

    class Meta:
        ordering = ["recommended_year", "recommended_semester", "course__code"]
        constraints = [models.UniqueConstraint(fields=["curriculum", "course"], name="unique_curriculum_course")]


# --------------------------------------------------------------------------- semesters and sections
class Semester(TenantScopedModel):
    """Registration settings for one semester (an AcademicPeriod of kind 'semester')."""

    period = models.OneToOneField("admissions.AcademicPeriod", on_delete=models.CASCADE, related_name="semester")
    registration_start = models.DateField()
    registration_end = models.DateField()
    add_drop_end = models.DateField(help_text="Last day students may add or drop courses")
    grades_due = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-period__start_date"]

    def __str__(self):
        return self.period.name

    def clean(self):
        if self.period_id and self.period.kind != "semester":
            raise ValidationError({"period": "Choose an academic period of kind 'semester'."})
        if self.registration_start and self.registration_end and self.registration_end < self.registration_start:
            raise ValidationError({"registration_end": "Registration must end after it starts."})
        if self.add_drop_end and self.registration_start and self.add_drop_end < self.registration_start:
            raise ValidationError({"add_drop_end": "The add/drop deadline must be after registration opens."})

    def window_open(self, today):
        return self.registration_start <= today <= self.add_drop_end


class CourseOffering(TenantScopedModel):
    """A section of a course taught in a semester."""

    class Status(models.TextChoices):
        OPEN = "open"
        CLOSED = "closed"
        CANCELLED = "cancelled"

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="offerings")
    semester = models.ForeignKey(Semester, on_delete=models.PROTECT, related_name="offerings")
    section = models.CharField(max_length=8, default="A")
    lecturer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="sections_taught")
    capacity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(1000)])
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ["course__code", "section"]
        constraints = [models.UniqueConstraint(fields=["semester", "course", "section"],
                                               name="unique_course_section")]

    def __str__(self):
        return f"{self.course.code}-{self.section} ({self.semester})"


class OfferingMeeting(TenantScopedModel):
    """A weekly class meeting. Used for timetables and conflict detection."""

    DAYS = [(0, "Mon"), (1, "Tue"), (2, "Wed"), (3, "Thu"), (4, "Fri"), (5, "Sat"), (6, "Sun")]

    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="meetings")
    day = models.PositiveSmallIntegerField(choices=DAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["day", "start_time"]

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "End time must be after the start time."})

    def overlaps(self, other):
        return self.day == other.day and self.start_time < other.end_time and other.start_time < self.end_time

    def __str__(self):
        return f"{self.get_day_display()} {self.start_time:%H:%M}-{self.end_time:%H:%M}"


# --------------------------------------------------------------------------- registration
class AcademicStanding(TenantScopedModel):
    """A matriculated student's program, adviser and cached GPA figures (recomputed from the transcript)."""

    class Standing(models.TextChoices):
        GOOD = "good", "Good standing"
        PROBATION = "probation", "Academic probation"

    student = models.OneToOneField("people.Student", on_delete=models.CASCADE, related_name="academic_standing")
    program = models.ForeignKey(Program, on_delete=models.PROTECT, related_name="students")
    curriculum = models.ForeignKey(Curriculum, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    adviser = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="advisees")
    year_of_study = models.PositiveSmallIntegerField(default=1)
    matriculated_on = models.DateField()
    cgpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    credits_attempted = models.PositiveIntegerField(default=0)
    credits_earned = models.PositiveIntegerField(default=0)
    standing = models.CharField(max_length=12, choices=Standing.choices, default=Standing.GOOD)

    class Meta:
        ordering = ["student__person__last_name"]

    def __str__(self):
        return f"{self.student} – {self.program.code}"


class CourseRegistration(TenantScopedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        APPROVED = "approved"
        REJECTED = "rejected"
        DROPPED = "dropped"

    ACTIVE = ("pending", "approved")

    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="course_registrations")
    offering = models.ForeignKey(CourseOffering, on_delete=models.PROTECT, related_name="registrations")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempt_no = models.PositiveSmallIntegerField(default=1)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_notes = models.CharField(max_length=255, blank=True)
    dropped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["offering__course__code"]
        constraints = [models.UniqueConstraint(fields=["student", "offering"],
                                               condition=models.Q(status__in=["pending", "approved"]),
                                               name="one_active_registration_per_section")]

    def __str__(self):
        return f"{self.student} in {self.offering}"


# --------------------------------------------------------------------------- assessment and grades
class UniversityAssessment(TenantScopedModel):
    class Kind(models.TextChoices):
        ASSIGNMENT = "assignment"
        QUIZ = "quiz"
        MIDTERM = "midterm"
        PROJECT = "project"
        LAB = "lab"
        EXAM = "exam", "Final exam"

    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="assessments")
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.ASSIGNMENT)
    weight = models.DecimalField(max_digits=5, decimal_places=2,
                                 validators=[MinValueValidator(0.01), MaxValueValidator(100)],
                                 help_text="Percentage of the final course mark")
    max_score = models.DecimalField(max_digits=6, decimal_places=2, default=100, validators=[MinValueValidator(1)])
    due_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["due_date", "id"]

    def __str__(self):
        return f"{self.offering.course.code} {self.name}"


class LectureAttendance(TenantScopedModel):
    """A registered student's attendance at one class meeting of a section, recorded by the lecturer."""

    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        EXCUSED = "excused", "Excused"

    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="attendance")
    registration = models.ForeignKey(CourseRegistration, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)
    note = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")

    class Meta:
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["registration", "date"], name="uniq_lecture_attendance_day")]
        indexes = [models.Index(fields=["offering", "date"])]

    def __str__(self):
        return f"{self.registration_id} {self.date} {self.status}"


class AssessmentScore(TenantScopedModel):
    assessment = models.ForeignKey(UniversityAssessment, on_delete=models.CASCADE, related_name="scores")
    registration = models.ForeignKey(CourseRegistration, on_delete=models.CASCADE, related_name="scores")
    score = models.DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(0)])
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["assessment", "registration"], name="unique_score")]


class UniversityGrade(TenantScopedModel):
    """Final course grade for one registration. Locked once approved; changes go through amendments."""

    class Status(models.TextChoices):
        DRAFT = "draft"
        SUBMITTED = "submitted"
        RETURNED = "returned", "Returned for correction"
        APPROVED = "approved"

    registration = models.OneToOneField(CourseRegistration, on_delete=models.CASCADE, related_name="grade")
    total_score = models.DecimalField(max_digits=5, decimal_places=2)
    letter = models.CharField(max_length=3)
    grade_points = models.DecimalField(max_digits=3, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["registration__student__person__last_name"]


class GradeApproval(TenantScopedModel):
    """Append-only moderation history for a section's grades (submit, return, approve, amend)."""

    class Action(models.TextChoices):
        SUBMITTED = "submitted"
        RETURNED = "returned"
        APPROVED = "approved"
        AMENDED = "amended"

    offering = models.ForeignKey(CourseOffering, on_delete=models.PROTECT, related_name="grade_approvals")
    grade = models.ForeignKey(UniversityGrade, null=True, blank=True, on_delete=models.PROTECT,
                              related_name="history")  # set for single-grade amendments
    action = models.CharField(max_length=10, choices=Action.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.CharField(max_length=500, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Grade approval history is append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Grade approval history is append-only.")


class TranscriptEntry(TenantScopedModel):
    """
    Immutable record of an approved grade. An amendment adds a new entry that supersedes the old one,
    so the full history is kept. Course details are copied so later catalogue edits don't rewrite history.
    """

    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="transcript_entries")
    registration = models.ForeignKey(CourseRegistration, on_delete=models.PROTECT, related_name="transcript_entries")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="+")
    semester = models.ForeignKey(Semester, on_delete=models.PROTECT, related_name="+")
    course_code = models.CharField(max_length=16)
    course_title = models.CharField(max_length=200)
    credit_hours = models.PositiveSmallIntegerField()
    total_score = models.DecimalField(max_digits=5, decimal_places=2)
    letter = models.CharField(max_length=3)
    grade_points = models.DecimalField(max_digits=3, decimal_places=2)
    attempt_no = models.PositiveSmallIntegerField(default=1)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    supersedes = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT,
                                      related_name="superseded_by")
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["semester__period__start_date", "course_code", "id"]
        verbose_name_plural = "transcript entries"

    def __str__(self):
        return f"{self.student} {self.course_code} {self.letter}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Transcript entries are immutable. Record an amendment instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Transcript entries are immutable.")


class GraduationClearance(TenantScopedModel):
    class Status(models.TextChoices):
        PENDING = "pending"
        CLEARED = "cleared"
        REJECTED = "rejected"

    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="graduation_clearances")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    audit_snapshot = models.JSONField(default=dict, blank=True)
    finance_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["student"], condition=models.Q(status="pending"),
                                               name="one_pending_clearance_per_student")]
