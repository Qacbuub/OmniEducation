from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Sum
from rest_framework import serializers

from core.tenancy import TenantModelSerializer

from .models import (
    AcademicStanding,
    Course,
    CourseOffering,
    CoursePrerequisite,
    CourseRegistration,
    Curriculum,
    CurriculumCourse,
    Department,
    Faculty,
    GradeApproval,
    GraduationClearance,
    OfferingMeeting,
    Program,
    Semester,
    TranscriptEntry,
    UniversityAssessment,
    UniversityGrade,
)


class ModelCleanMixin:
    """Run the model's clean() so database-level rules are reported as field errors."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        instance = self.instance or self.Meta.model()
        for k, v in attrs.items():
            if not isinstance(self.fields.get(k), serializers.ListSerializer):
                setattr(instance, k, v)
        if request is not None and not instance.tenant_id:
            instance.tenant = request.user.tenant
        try:
            instance.clean()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict if hasattr(e, "message_dict") else e.messages)
        return attrs


def _name(user):
    return user.get_full_name() if user else None


class FacultySerializer(ModelCleanMixin, TenantModelSerializer):
    dean_name = serializers.SerializerMethodField()
    department_count = serializers.IntegerField(source="departments.count", read_only=True)

    class Meta:
        model = Faculty
        fields = ["id", "name", "code", "dean", "dean_name", "department_count"]

    def get_dean_name(self, obj) -> str | None:
        return _name(obj.dean)

    def validate_dean(self, user):
        if user and user.role_code not in ("dean", "inst_admin", "registrar"):
            raise serializers.ValidationError("The dean must be a user with the Dean role.")
        return user


class DepartmentSerializer(ModelCleanMixin, TenantModelSerializer):
    faculty_name = serializers.CharField(source="faculty.name", read_only=True)
    head_name = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ["id", "faculty", "faculty_name", "name", "code", "head", "head_name"]

    def get_head_name(self, obj) -> str | None:
        return _name(obj.head)

    def validate_head(self, user):
        if user and user.role_code != "dept_head":
            raise serializers.ValidationError("The head must be a user with the Department Head role.")
        return user


class ProgramSerializer(ModelCleanMixin, TenantModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    faculty_name = serializers.CharField(source="department.faculty.name", read_only=True)
    student_count = serializers.SerializerMethodField()
    current_curriculum = serializers.SerializerMethodField()

    class Meta:
        model = Program
        fields = ["id", "department", "department_name", "faculty_name", "name", "code", "award", "duration_years",
                  "total_credits_required", "is_active", "student_count", "current_curriculum"]

    def get_student_count(self, obj) -> int:
        return obj.students.filter(student__status="active").count()

    def get_current_curriculum(self, obj) -> dict | None:
        c = obj.current_curriculum()
        return {"id": c.id, "version": c.version} if c else None


class PrerequisiteSummarySerializer(serializers.ModelSerializer):
    code = serializers.CharField(source="prerequisite.code")
    title = serializers.CharField(source="prerequisite.title")

    class Meta:
        model = CoursePrerequisite
        fields = ["id", "prerequisite", "code", "title", "min_grade_points"]


class CourseSerializer(ModelCleanMixin, TenantModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    prerequisites = PrerequisiteSummarySerializer(source="prerequisite_links", many=True, read_only=True)

    class Meta:
        model = Course
        fields = ["id", "department", "department_name", "code", "title", "credit_hours", "level", "description",
                  "is_active", "prerequisites"]

    def validate_code(self, value):
        return value.strip().upper()


class CoursePrerequisiteSerializer(ModelCleanMixin, TenantModelSerializer):
    course_code = serializers.CharField(source="course.code", read_only=True)
    prerequisite_code = serializers.CharField(source="prerequisite.code", read_only=True)

    class Meta:
        model = CoursePrerequisite
        fields = ["id", "course", "course_code", "prerequisite", "prerequisite_code", "min_grade_points"]
        validators = []  # duplicate pairs are reported by validate()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        qs = CoursePrerequisite.objects.filter(course=attrs.get("course"), prerequisite=attrs.get("prerequisite"))
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"prerequisite": ["This prerequisite is already set."]})
        return attrs


class CurriculumCourseSerializer(ModelCleanMixin, TenantModelSerializer):
    code = serializers.CharField(source="course.code", read_only=True)
    title = serializers.CharField(source="course.title", read_only=True)
    credits = serializers.IntegerField(source="course.credit_hours", read_only=True)

    class Meta:
        model = CurriculumCourse
        fields = ["id", "curriculum", "course", "code", "title", "credits", "category", "recommended_year",
                  "recommended_semester"]
        validators = []

    def validate(self, attrs):
        attrs = super().validate(attrs)
        qs = CurriculumCourse.objects.filter(curriculum=attrs.get("curriculum"), course=attrs.get("course"))
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"course": ["This course is already in the curriculum."]})
        return attrs


class CurriculumSerializer(ModelCleanMixin, TenantModelSerializer):
    program_name = serializers.CharField(source="program.name", read_only=True)
    items = CurriculumCourseSerializer(many=True, read_only=True)
    core_credits = serializers.SerializerMethodField()

    class Meta:
        model = Curriculum
        fields = ["id", "program", "program_name", "version", "effective_from", "elective_credits_required",
                  "is_current", "core_credits", "items"]
        validators = []

    def get_core_credits(self, obj) -> int:
        return obj.items.filter(category="core").aggregate(t=Sum("course__credit_hours"))["t"] or 0

    def validate(self, attrs):
        attrs = super().validate(attrs)
        program = attrs.get("program") or (self.instance and self.instance.program)
        version = attrs.get("version") or (self.instance and self.instance.version)
        qs = Curriculum.objects.filter(program=program, version=version)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"version": ["This program already has a curriculum with that version."]})
        return attrs


class SemesterSerializer(ModelCleanMixin, TenantModelSerializer):
    name = serializers.CharField(source="period.name", read_only=True)
    start_date = serializers.DateField(source="period.start_date", read_only=True)
    end_date = serializers.DateField(source="period.end_date", read_only=True)
    is_current = serializers.BooleanField(source="period.is_current", read_only=True)
    offering_count = serializers.IntegerField(source="offerings.count", read_only=True)

    class Meta:
        model = Semester
        fields = ["id", "period", "name", "start_date", "end_date", "is_current", "registration_start",
                  "registration_end", "add_drop_end", "grades_due", "offering_count"]


class MeetingSerializer(serializers.ModelSerializer):
    day_name = serializers.CharField(source="get_day_display", read_only=True)

    class Meta:
        model = OfferingMeeting
        fields = ["id", "day", "day_name", "start_time", "end_time", "room"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError({"end_time": ["End time must be after the start time."]})
        return attrs


class CourseOfferingSerializer(TenantModelSerializer):
    course_code = serializers.CharField(source="course.code", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    credit_hours = serializers.IntegerField(source="course.credit_hours", read_only=True)
    department_name = serializers.CharField(source="course.department.name", read_only=True)
    semester_name = serializers.CharField(source="semester.period.name", read_only=True)
    lecturer_name = serializers.SerializerMethodField()
    meetings = MeetingSerializer(many=True, required=False)
    enrolled = serializers.SerializerMethodField()
    seats_left = serializers.SerializerMethodField()
    grade_status = serializers.SerializerMethodField()

    class Meta:
        model = CourseOffering
        fields = ["id", "course", "course_code", "course_title", "credit_hours", "department_name", "semester",
                  "semester_name", "section", "lecturer", "lecturer_name", "capacity", "status", "meetings",
                  "enrolled", "seats_left", "grade_status"]

    def get_lecturer_name(self, obj) -> str | None:
        return _name(obj.lecturer)

    def _enrolled(self, obj):
        if not hasattr(obj, "_enrolled_cache"):
            obj._enrolled_cache = obj.registrations.filter(status__in=CourseRegistration.ACTIVE).count()
        return obj._enrolled_cache

    def get_enrolled(self, obj) -> int:
        return self._enrolled(obj)

    def get_seats_left(self, obj) -> int:
        return max(0, obj.capacity - self._enrolled(obj))

    def get_grade_status(self, obj) -> str:
        from .services import offering_grade_state
        return offering_grade_state(obj)

    def validate_lecturer(self, user):
        if user and user.role_code != "lecturer":
            raise serializers.ValidationError("Choose a user with the Lecturer role.")
        return user

    def validate(self, attrs):
        if self.instance and "capacity" in attrs and attrs["capacity"] < self._enrolled(self.instance):
            raise serializers.ValidationError(
                {"capacity": [f"{self._enrolled(self.instance)} students are already registered."]})
        course = attrs.get("course") or (self.instance and self.instance.course)
        semester = attrs.get("semester") or (self.instance and self.instance.semester)
        section = attrs.get("section") or (self.instance.section if self.instance else "A")
        qs = CourseOffering.objects.filter(course=course, semester=semester, section=section)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"section": [f"Section {section} of this course already exists."]})
        return attrs


class RegistrationSerializer(serializers.ModelSerializer):
    student_no = serializers.CharField(source="student.student_no", read_only=True)
    student_name = serializers.CharField(source="student.person.full_name", read_only=True)
    course_code = serializers.CharField(source="offering.course.code", read_only=True)
    course_title = serializers.CharField(source="offering.course.title", read_only=True)
    credit_hours = serializers.IntegerField(source="offering.course.credit_hours", read_only=True)
    section = serializers.CharField(source="offering.section", read_only=True)
    semester = serializers.IntegerField(source="offering.semester_id", read_only=True)
    semester_name = serializers.CharField(source="offering.semester.period.name", read_only=True)
    lecturer_name = serializers.SerializerMethodField()
    grade = serializers.SerializerMethodField()

    class Meta:
        model = CourseRegistration
        fields = ["id", "student", "student_no", "student_name", "offering", "course_code", "course_title",
                  "credit_hours", "section", "semester", "semester_name", "lecturer_name", "status", "attempt_no",
                  "decision_notes", "decided_at", "created_at", "grade"]

    def get_lecturer_name(self, obj) -> str | None:
        return _name(obj.offering.lecturer)

    def get_grade(self, obj) -> dict | None:
        g = getattr(obj, "grade", None)
        if g is None or g.status != "approved":
            # Students only see grades once approved; staff see the workflow state.
            request = self.context.get("request")
            if g is None or (request and request.user.role_code == "student"):
                return None
        return {"letter": g.letter, "points": g.grade_points, "total": g.total_score, "status": g.status}


class RegistrationCreateSerializer(serializers.Serializer):
    offering = serializers.IntegerField()
    student = serializers.IntegerField(required=False)


class DecisionSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, max_length=255)


class AssessmentSerializer(TenantModelSerializer):
    class Meta:
        model = UniversityAssessment
        fields = ["id", "offering", "name", "kind", "weight", "max_score", "due_date"]

    def validate(self, attrs):
        offering = attrs.get("offering") or self.instance.offering
        if self.instance and "offering" in attrs and attrs["offering"] != self.instance.offering:
            raise serializers.ValidationError({"offering": ["An assessment cannot be moved to another section."]})
        others = offering.assessments.exclude(pk=self.instance.pk if self.instance else None)
        total = sum(a.weight for a in others) + attrs.get("weight", self.instance.weight if self.instance else 0)
        if total > 100:
            raise serializers.ValidationError({"weight": [f"Weights would total {total}%; the maximum is 100%."]})
        return attrs


class ScoreRowSerializer(serializers.Serializer):
    assessment = serializers.IntegerField()
    registration = serializers.IntegerField()
    score = serializers.DecimalField(max_digits=6, decimal_places=2)


class ScoresSerializer(serializers.Serializer):
    scores = ScoreRowSerializer(many=True, allow_empty=False)


class GradeSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="registration.student.person.full_name", read_only=True)
    student_no = serializers.CharField(source="registration.student.student_no", read_only=True)
    course_code = serializers.CharField(source="registration.offering.course.code", read_only=True)
    offering = serializers.IntegerField(source="registration.offering_id", read_only=True)

    class Meta:
        model = UniversityGrade
        fields = ["id", "registration", "offering", "student_name", "student_no", "course_code", "total_score",
                  "letter", "grade_points", "status", "submitted_at", "approved_at"]


class AmendSerializer(serializers.Serializer):
    total_score = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal(0),
                                           max_value=Decimal(100))
    reason = serializers.CharField(max_length=255)


class GradeApprovalSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    course_code = serializers.CharField(source="offering.course.code", read_only=True)
    section = serializers.CharField(source="offering.section", read_only=True)

    class Meta:
        model = GradeApproval
        fields = ["id", "offering", "course_code", "section", "grade", "action", "actor_name", "notes", "details",
                  "created_at"]

    def get_actor_name(self, obj) -> str | None:
        return _name(obj.actor)


class TranscriptEntrySerializer(serializers.ModelSerializer):
    semester_name = serializers.CharField(source="semester.period.name", read_only=True)

    class Meta:
        model = TranscriptEntry
        fields = ["id", "registration", "course_code", "course_title", "credit_hours", "letter", "grade_points",
                  "total_score", "attempt_no", "semester", "semester_name", "reason", "created_at"]


class StandingSerializer(TenantModelSerializer):
    student_no = serializers.CharField(source="student.student_no", read_only=True)
    student_name = serializers.CharField(source="student.person.full_name", read_only=True)
    program_name = serializers.CharField(source="program.name", read_only=True)
    adviser_name = serializers.SerializerMethodField()

    class Meta:
        model = AcademicStanding
        fields = ["id", "student", "student_no", "student_name", "program", "program_name", "curriculum", "adviser",
                  "adviser_name", "year_of_study", "matriculated_on", "cgpa", "credits_attempted", "credits_earned",
                  "standing"]
        read_only_fields = ["student", "matriculated_on", "cgpa", "credits_attempted", "credits_earned", "standing"]

    def get_adviser_name(self, obj) -> str | None:
        return _name(obj.adviser)

    def validate_adviser(self, user):
        if user and user.role_code != "adviser":
            raise serializers.ValidationError("Choose a user with the Academic Adviser role.")
        return user

    def validate(self, attrs):
        program = attrs.get("program") or self.instance.program
        curriculum = attrs.get("curriculum")
        if curriculum and curriculum.program_id != program.id:
            raise serializers.ValidationError({"curriculum": ["This curriculum belongs to another program."]})
        return attrs


class ClearanceSerializer(serializers.ModelSerializer):
    student_no = serializers.CharField(source="student.student_no", read_only=True)
    student_name = serializers.CharField(source="student.person.full_name", read_only=True)
    decided_by_name = serializers.SerializerMethodField()

    class Meta:
        model = GraduationClearance
        fields = ["id", "student", "student_no", "student_name", "status", "audit_snapshot", "finance_balance",
                  "decided_by_name", "decided_at", "notes", "created_at"]
        read_only_fields = fields

    def get_decided_by_name(self, obj) -> str | None:
        return _name(obj.decided_by)
