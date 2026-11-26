"""
School (K-12) data model.

Kept separate from the university module: grade levels, class sections, terms, attendance, marks,
report cards and promotion live here. Identity, students, guardians, admissions, fees and documents are
reused from the shared apps.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import TenantScopedModel


class GradeLevel(TenantScopedModel):
    """Grade 1, Grade 2, … ordered; pupils in the final level complete school instead of being promoted."""

    name = models.CharField(max_length=40)
    order = models.PositiveSmallIntegerField()
    is_final = models.BooleanField(default=False, help_text="Pupils who pass this level complete school")

    class Meta:
        ordering = ["order"]
        constraints = [models.UniqueConstraint(fields=["tenant", "name"], name="unique_grade_name"),
                       models.UniqueConstraint(fields=["tenant", "order"], name="unique_grade_order")]

    def __str__(self):
        return self.name

    def next_level(self):
        return GradeLevel.objects.filter(tenant=self.tenant, order__gt=self.order).order_by("order").first()


class Subject(TenantScopedModel):
    name = models.CharField(max_length=80)
    code = models.CharField(max_length=12)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="unique_subject_code")]

    def __str__(self):
        return self.name


class ClassSection(TenantScopedModel):
    """A class (e.g. Grade 4A) for one academic year, with a homeroom (class) teacher."""

    grade_level = models.ForeignKey(GradeLevel, on_delete=models.PROTECT, related_name="sections")
    academic_year = models.ForeignKey("admissions.AcademicPeriod", on_delete=models.PROTECT, related_name="+")
    name = models.CharField(max_length=10, default="A")
    homeroom_teacher = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                         related_name="homerooms")
    capacity = models.PositiveSmallIntegerField(default=40, validators=[MinValueValidator(1), MaxValueValidator(200)])
    room = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["grade_level__order", "name"]
        constraints = [models.UniqueConstraint(fields=["academic_year", "grade_level", "name"],
                                               name="unique_class_section")]

    def __str__(self):
        return self.label

    @property
    def label(self):
        return f"{self.grade_level.name}{self.name}"

    def clean(self):
        if self.academic_year_id and self.academic_year.kind != "academic_year":
            raise ValidationError({"academic_year": "Choose an academic year."})

    def terms(self):
        return self.academic_year.children.filter(kind="term").order_by("start_date")


class ClassAssignment(TenantScopedModel):
    """Subject allocation: who teaches which subject to a class."""

    section = models.ForeignKey(ClassSection, on_delete=models.CASCADE, related_name="assignments")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="assignments")
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="subject_assignments")
    weekly_lessons = models.PositiveSmallIntegerField(default=5, validators=[MaxValueValidator(20)])

    class Meta:
        ordering = ["subject__name"]
        constraints = [models.UniqueConstraint(fields=["section", "subject"], name="unique_subject_per_section")]

    def __str__(self):
        return f"{self.section} {self.subject}"


class ClassPlacement(TenantScopedModel):
    """A pupil belongs to one class section per academic year (history kept when they move)."""

    class Status(models.TextChoices):
        ACTIVE = "active"
        MOVED = "moved", "Moved to another class"
        ENDED = "ended"

    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="class_placements")
    section = models.ForeignKey(ClassSection, on_delete=models.PROTECT, related_name="placements")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    placed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-start_date", "-id"]
        constraints = [models.UniqueConstraint(fields=["student", "section"], condition=models.Q(status="active"),
                                               name="one_active_placement_per_section")]

    def __str__(self):
        return f"{self.student} in {self.section}"


class SchoolTimetable(TenantScopedModel):
    """A weekly lesson slot for a class."""

    DAYS = [(0, "Mon"), (1, "Tue"), (2, "Wed"), (3, "Thu"), (4, "Fri")]

    assignment = models.ForeignKey(ClassAssignment, on_delete=models.CASCADE, related_name="lessons")
    day = models.PositiveSmallIntegerField(choices=DAYS)
    period_no = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["day", "period_no"]

    def __str__(self):
        return f"{self.assignment} {self.get_day_display()} P{self.period_no}"

    @property
    def section(self):
        return self.assignment.section

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "End time must be after the start time."})

    def overlaps(self, other):
        return self.day == other.day and self.start_time < other.end_time and other.start_time < self.end_time


class PupilAttendance(TenantScopedModel):
    """Daily register (lesson empty) or per-lesson attendance (lesson set)."""

    class Status(models.TextChoices):
        PRESENT = "present"
        ABSENT = "absent"
        LATE = "late"
        EXCUSED = "excused", "Excused absence"

    ABSENT_STATUSES = ("absent", "excused")

    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="attendance")
    section = models.ForeignKey(ClassSection, on_delete=models.PROTECT, related_name="attendance")
    date = models.DateField(db_index=True)
    lesson = models.ForeignKey(SchoolTimetable, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="attendance")
    status = models.CharField(max_length=10, choices=Status.choices)
    reason = models.CharField(max_length=120, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    guardian_notified = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date", "student__person__last_name"]
        constraints = [
            models.UniqueConstraint(fields=["student", "date"], condition=models.Q(lesson__isnull=True),
                                    name="one_daily_mark_per_pupil"),
            models.UniqueConstraint(fields=["student", "date", "lesson"], condition=models.Q(lesson__isnull=False),
                                    name="one_lesson_mark_per_pupil"),
        ]


class SchoolAssessment(TenantScopedModel):
    """Homework, quizzes, tests, projects and exams for one subject in one class and term."""

    class Kind(models.TextChoices):
        HOMEWORK = "homework"
        QUIZ = "quiz"
        TEST = "test", "Class test"
        PROJECT = "project"
        EXAM = "exam"

    section = models.ForeignKey(ClassSection, on_delete=models.CASCADE, related_name="assessments")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="+")
    term = models.ForeignKey("admissions.AcademicPeriod", on_delete=models.PROTECT, related_name="+")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.HOMEWORK)
    description = models.TextField(blank=True)
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=10,
                                 validators=[MinValueValidator(0), MaxValueValidator(100)],
                                 help_text="Relative weight within the subject's term result (0 = not graded)")
    max_score = models.DecimalField(max_digits=6, decimal_places=2, default=100, validators=[MinValueValidator(1)])
    due_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["due_date", "id"]

    def __str__(self):
        return f"{self.section} {self.subject.code} {self.name}"

    def clean(self):
        if self.term_id and self.term.kind != "term":
            raise ValidationError({"term": "Choose a term."})
        if self.term_id and self.section_id and self.term.parent_id != self.section.academic_year_id:
            raise ValidationError({"term": "The term must belong to the class's academic year."})


class SchoolMark(TenantScopedModel):
    assessment = models.ForeignKey(SchoolAssessment, on_delete=models.CASCADE, related_name="marks")
    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="school_marks")
    score = models.DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(0)])
    remarks = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["assessment", "student"], name="unique_mark")]


class TermResult(TenantScopedModel):
    """A pupil's computed result for one term: weighted subject averages, position and remarks."""

    class Status(models.TextChoices):
        FINALIZED = "finalized"   # marks locked, not yet visible to families
        PUBLISHED = "published"   # report card released to guardians and pupils

    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="term_results")
    section = models.ForeignKey(ClassSection, on_delete=models.PROTECT, related_name="term_results")
    term = models.ForeignKey("admissions.AcademicPeriod", on_delete=models.PROTECT, related_name="+")
    subjects = models.JSONField(default=list)  # [{subject_id, code, name, average, grade, points, remark}]
    average = models.DecimalField(max_digits=5, decimal_places=2)
    grade = models.CharField(max_length=3)
    position = models.PositiveSmallIntegerField(null=True, blank=True)
    class_size = models.PositiveSmallIntegerField(default=0)
    days_present = models.PositiveSmallIntegerField(default=0)
    days_absent = models.PositiveSmallIntegerField(default=0)
    teacher_remark = models.CharField(max_length=300, blank=True)
    principal_remark = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.FINALIZED)
    finalized_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    finalized_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["term__start_date", "position"]
        constraints = [models.UniqueConstraint(fields=["student", "term"], name="one_result_per_pupil_term")]

    def __str__(self):
        return f"{self.student} {self.term} {self.average}"


class PromotionDecision(TenantScopedModel):
    class Decision(models.TextChoices):
        PROMOTE = "promote"
        REPEAT = "repeat"
        COMPLETE = "complete", "Completed school"

    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="promotion_decisions")
    section = models.ForeignKey(ClassSection, on_delete=models.PROTECT, related_name="promotion_decisions")
    academic_year = models.ForeignKey("admissions.AcademicPeriod", on_delete=models.PROTECT, related_name="+")
    decision = models.CharField(max_length=10, choices=Decision.choices)
    from_level = models.ForeignKey(GradeLevel, on_delete=models.PROTECT, related_name="+")
    to_level = models.ForeignKey(GradeLevel, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    year_average = models.DecimalField(max_digits=5, decimal_places=2)
    recommended = models.CharField(max_length=10, choices=Decision.choices)
    reason = models.CharField(max_length=300, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["student", "academic_year"], name="one_decision_per_year")]

    def __str__(self):
        return f"{self.student}: {self.decision}"
