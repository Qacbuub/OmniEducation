from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from core.tenancy import TenantModelSerializer

from .models import (
    ClassAssignment,
    ClassPlacement,
    ClassSection,
    GradeLevel,
    PromotionDecision,
    PupilAttendance,
    SchoolAssessment,
    SchoolMark,
    SchoolTimetable,
    Subject,
    TermResult,
)


def _name(user):
    return user.get_full_name() if user else None


class CleanMixin:
    """Run model.clean() so model-level rules come back as field errors."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.instance or self.Meta.model()
        for k, v in attrs.items():
            setattr(instance, k, v)
        request = self.context.get("request")
        if request is not None and not instance.tenant_id:
            instance.tenant = request.user.tenant
        try:
            instance.clean()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict if hasattr(e, "message_dict") else e.messages)
        return attrs


class GradeLevelSerializer(TenantModelSerializer):
    class Meta:
        model = GradeLevel
        fields = ["id", "name", "order", "is_final"]


class SubjectSerializer(TenantModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "name", "code"]

    def validate_code(self, v):
        return v.strip().upper()


class AssignmentSerializer(TenantModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    subject_code = serializers.CharField(source="subject.code", read_only=True)
    teacher_name = serializers.SerializerMethodField()
    section_label = serializers.CharField(source="section.label", read_only=True)

    class Meta:
        model = ClassAssignment
        fields = ["id", "section", "section_label", "subject", "subject_name", "subject_code", "teacher",
                  "teacher_name", "weekly_lessons"]
        validators = []

    def get_teacher_name(self, obj) -> str | None:
        return _name(obj.teacher)

    def validate_teacher(self, user):
        if user and user.role_code not in ("class_teacher", "subject_teacher", "principal"):
            raise serializers.ValidationError("Choose a teacher.")
        return user

    def validate(self, attrs):
        section = attrs.get("section") or self.instance.section
        subject = attrs.get("subject") or self.instance.subject
        qs = ClassAssignment.objects.filter(section=section, subject=subject)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"subject": [f"{subject} is already allocated to {section}."]})
        return attrs


class SectionSerializer(CleanMixin, TenantModelSerializer):
    label = serializers.CharField(read_only=True)
    grade_name = serializers.CharField(source="grade_level.name", read_only=True)
    year_name = serializers.CharField(source="academic_year.name", read_only=True)
    homeroom_teacher_name = serializers.SerializerMethodField()
    pupil_count = serializers.SerializerMethodField()
    assignments = AssignmentSerializer(many=True, read_only=True)

    class Meta:
        model = ClassSection
        fields = ["id", "label", "grade_level", "grade_name", "academic_year", "year_name", "name",
                  "homeroom_teacher", "homeroom_teacher_name", "capacity", "room", "pupil_count", "assignments"]
        validators = []

    def get_homeroom_teacher_name(self, obj) -> str | None:
        return _name(obj.homeroom_teacher)

    def get_pupil_count(self, obj) -> int:
        return obj.placements.filter(status="active", student__status="active").count()

    def validate_homeroom_teacher(self, user):
        if user and user.role_code != "class_teacher":
            raise serializers.ValidationError("The homeroom teacher must have the Class Teacher role.")
        return user

    def validate(self, attrs):
        attrs = super().validate(attrs)
        g = attrs.get("grade_level") or self.instance.grade_level
        y = attrs.get("academic_year") or self.instance.academic_year
        n = attrs.get("name") or (self.instance.name if self.instance else "A")
        qs = ClassSection.objects.filter(grade_level=g, academic_year=y, name=n)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"name": [f"{g}{n} already exists for {y}."]})
        return attrs


class PlacementSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.person.full_name", read_only=True)
    student_no = serializers.CharField(source="student.student_no", read_only=True)
    section_label = serializers.CharField(source="section.label", read_only=True)
    year_name = serializers.CharField(source="section.academic_year.name", read_only=True)

    class Meta:
        model = ClassPlacement
        fields = ["id", "student", "student_no", "student_name", "section", "section_label", "year_name", "status",
                  "start_date", "end_date"]


class PlaceSerializer(serializers.Serializer):
    student = serializers.IntegerField()


class LessonSerializer(TenantModelSerializer):
    day_name = serializers.CharField(source="get_day_display", read_only=True)
    subject_name = serializers.CharField(source="assignment.subject.name", read_only=True)
    subject_code = serializers.CharField(source="assignment.subject.code", read_only=True)
    teacher_name = serializers.SerializerMethodField()
    section = serializers.IntegerField(source="assignment.section_id", read_only=True)
    section_label = serializers.CharField(source="assignment.section.label", read_only=True)

    class Meta:
        model = SchoolTimetable
        fields = ["id", "assignment", "section", "section_label", "subject_name", "subject_code", "teacher_name",
                  "day", "day_name", "period_no", "start_time", "end_time", "room"]

    def get_teacher_name(self, obj) -> str | None:
        return _name(obj.assignment.teacher)

    def validate(self, attrs):
        start = attrs.get("start_time") or self.instance.start_time
        end = attrs.get("end_time") or self.instance.end_time
        if end <= start:
            raise serializers.ValidationError({"end_time": ["End time must be after the start time."]})
        return attrs


class AttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.person.full_name", read_only=True)
    student_no = serializers.CharField(source="student.student_no", read_only=True)
    section_label = serializers.CharField(source="section.label", read_only=True)
    lesson_subject = serializers.CharField(source="lesson.assignment.subject.name", read_only=True, default=None)

    class Meta:
        model = PupilAttendance
        fields = ["id", "student", "student_no", "student_name", "section", "section_label", "date", "lesson",
                  "lesson_subject", "status", "reason", "guardian_notified"]


class AttendanceRowSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    status = serializers.ChoiceField(choices=PupilAttendance.Status.choices)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=120)


class AttendanceRegisterSerializer(serializers.Serializer):
    section = serializers.IntegerField()
    date = serializers.DateField()
    lesson = serializers.IntegerField(required=False, allow_null=True)
    records = AttendanceRowSerializer(many=True, allow_empty=False)


class AssessmentSerializer(CleanMixin, TenantModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    section_label = serializers.CharField(source="section.label", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    marked = serializers.SerializerMethodField()

    class Meta:
        model = SchoolAssessment
        fields = ["id", "section", "section_label", "subject", "subject_name", "term", "term_name", "name", "kind",
                  "description", "weight", "max_score", "due_date", "marked"]

    def get_marked(self, obj) -> int:
        return obj.marks.count()


class MarkSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.person.full_name", read_only=True)

    class Meta:
        model = SchoolMark
        fields = ["id", "assessment", "student", "student_name", "score", "remarks"]


class MarkRowSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    score = serializers.DecimalField(max_digits=6, decimal_places=2)
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=200)


class MarksSerializer(serializers.Serializer):
    marks = MarkRowSerializer(many=True, allow_empty=False)


class TermResultSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.person.full_name", read_only=True)
    student_no = serializers.CharField(source="student.student_no", read_only=True)
    section_label = serializers.CharField(source="section.label", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)

    class Meta:
        model = TermResult
        fields = ["id", "student", "student_no", "student_name", "section", "section_label", "term", "term_name",
                  "subjects", "average", "grade", "position", "class_size", "days_present", "days_absent",
                  "teacher_remark", "principal_remark", "status", "finalized_at", "published_at"]
        read_only_fields = [f for f in fields if f not in ("teacher_remark", "principal_remark")]


class SectionTermSerializer(serializers.Serializer):
    section = serializers.IntegerField()
    term = serializers.IntegerField()


class PromotionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.person.full_name", read_only=True)
    from_level_name = serializers.CharField(source="from_level.name", read_only=True)
    to_level_name = serializers.CharField(source="to_level.name", read_only=True, default=None)
    section_label = serializers.CharField(source="section.label", read_only=True)
    decided_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PromotionDecision
        fields = ["id", "student", "student_name", "section", "section_label", "decision", "from_level_name",
                  "to_level_name", "year_average", "recommended", "reason", "decided_by_name", "created_at"]

    def get_decided_by_name(self, obj) -> str | None:
        return _name(obj.decided_by)


class DecideSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    section = serializers.IntegerField()
    decision = serializers.ChoiceField(choices=PromotionDecision.Decision.choices)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=300)
