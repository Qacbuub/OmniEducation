import re

from django.utils import timezone
from rest_framework import serializers

from core.tenancy import TenantModelSerializer, TenantPrimaryKeyRelatedField

from .hooks import TARGET_VALIDATORS
from .models import AcademicPeriod, Application, Enrollment


PHONE_RE = re.compile(r"\+?[0-9][0-9 ()\-]{6,19}")
GENDERS = [("female", "Female"), ("male", "Male"), ("other", "Other")]


class AcademicPeriodSerializer(TenantModelSerializer):
    parent = TenantPrimaryKeyRelatedField(queryset=AcademicPeriod.objects.all(), required=False, allow_null=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)

    class Meta:
        model = AcademicPeriod
        fields = ["id", "name", "kind", "parent", "parent_name", "start_date", "end_date", "is_current"]
        read_only_fields = ["is_current"]  # use the set-current action
        validators = []

    def validate(self, attrs):
        tenant = self.context["request"].user.tenant
        instance = AcademicPeriod(tenant=tenant, **{**self._current(), **attrs})
        instance.clean()  # raises Django ValidationError -> structured 400
        dup = AcademicPeriod.objects.filter(tenant=tenant, kind=instance.kind, name=instance.name)
        if self.instance:
            dup = dup.exclude(pk=self.instance.pk)
        if dup.exists():
            raise serializers.ValidationError({"name": ["A period with this name already exists."]})
        return attrs

    def _current(self):
        if not self.instance:
            return {}
        return {f: getattr(self.instance, f) for f in ("name", "kind", "parent", "start_date", "end_date")}


class ApplicationSerializer(TenantModelSerializer):
    intake_period = TenantPrimaryKeyRelatedField(queryset=AcademicPeriod.objects.all(), required=False, allow_null=True)
    allowed_transitions = serializers.SerializerMethodField()
    reviewed_by = serializers.EmailField(source="reviewed_by.email", read_only=True, default=None)
    full_name = serializers.CharField(read_only=True)
    student_id = serializers.IntegerField(source="student.id", read_only=True, default=None)
    document_count = serializers.SerializerMethodField()
    gender = serializers.ChoiceField(choices=GENDERS, required=False, allow_blank=True)
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = ["id", "application_no", "reference_code", "status", "source", "full_name", "first_name",
                  "middle_name", "last_name", "date_of_birth", "national_id", "gender", "email", "phone", "address",
                  "previous_school", "requested_level", "target_id", "intake_period", "guardian_name",
                  "guardian_relationship", "guardian_phone", "guardian_email", "submitted_at", "reviewed_by",
                  "reviewed_at", "decision_notes", "allowed_transitions", "student_id", "document_count", "photo_url"]
        read_only_fields = ["application_no", "reference_code", "status", "source", "submitted_at",
                            "reviewed_at", "decision_notes"]
        validators = []
        extra_kwargs = {"requested_level": {"required": False}}  # filled from target_id when that is given

    def get_allowed_transitions(self, obj):
        return obj.allowed_transitions()

    def get_document_count(self, obj):
        return obj.documents.count()

    def get_photo_url(self, obj) -> str | None:
        return f"/api/admissions/{obj.pk}/photo/?v={int(obj.updated_at.timestamp())}" if obj.photo else None

    def validate_date_of_birth(self, value):
        if value >= timezone.localdate():
            raise serializers.ValidationError("Date of birth must be in the past.")
        return value

    def validate(self, attrs):
        tenant = self.context.get("tenant") or self.context["request"].user.tenant
        # A complete record is needed before an applicant can become a student, so every
        # application (staff or online) must carry full personal and contact details.
        required = ["gender", "phone", "address", "guardian_name", "guardian_relationship", "guardian_phone"]
        value = lambda f: attrs.get(f, getattr(self.instance, f, None))  # noqa: E731 - partial updates
        errors = {}
        for f in required:
            if value(f) in (None, ""):
                who = "guardian" if tenant.is_school else "next of kin / emergency contact"
                errors[f] = [f"Required ({who} details)." if f.startswith("guardian") else "Required."]
        for f in ("phone", "guardian_phone"):
            v = value(f)
            if v and errors.get(f) is None and not PHONE_RE.fullmatch(v.strip()):
                errors[f] = ["Enter a valid phone number, e.g. +255 712 345 678."]
        if errors:
            raise serializers.ValidationError(errors)
        validator = TARGET_VALIDATORS.get(tenant.type)
        target_id = attrs.get("target_id")
        if validator and target_id is not None:
            attrs["requested_level"] = validator(tenant, target_id)  # raises ValidationError if invalid
        if not (attrs.get("requested_level") or getattr(self.instance, "requested_level", "")):
            what = "grade level" if tenant.is_school else "program"
            raise serializers.ValidationError({"requested_level": [f"Choose the {what} you are applying for."]})
        email = attrs.get("email")
        if email and not self.instance:
            open_dup = Application.objects.filter(tenant=tenant, email__iexact=email).exclude(
                status__in=["rejected", "withdrawn", "offer_declined", "enrolled"])
            if open_dup.exists():
                raise serializers.ValidationError({"email": ["There is already an open application for this email."]})
        return attrs


class DecisionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Application.Status.choices)
    notes = serializers.CharField(required=False, allow_blank=True)


class EnrollmentSerializer(TenantModelSerializer):
    period_name = serializers.CharField(source="period.name", read_only=True, default=None)
    student_name = serializers.CharField(source="student.person.full_name", read_only=True)
    recorded_by = serializers.EmailField(source="recorded_by.email", read_only=True, default=None)

    class Meta:
        model = Enrollment
        fields = ["id", "student", "student_name", "period", "period_name", "level_label", "section_label",
                  "status", "start_date", "end_date", "reason", "recorded_by", "created_at"]
        read_only_fields = fields  # changed only through workflow actions


class StatusChangeSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
    effective_date = serializers.DateField(required=False)
    destination = serializers.CharField(max_length=200, required=False, allow_blank=True)


class EnrollBillingSerializer(serializers.Serializer):
    """Optional first invoice when a student is enrolled: a fee plan, or one-off items (finance staff only)."""

    mode = serializers.ChoiceField(choices=["none", "plan", "custom"], default="none")
    plan = serializers.IntegerField(required=False)
    items = serializers.ListField(child=serializers.DictField(), required=False)
    due_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs["mode"] == "plan" and not attrs.get("plan"):
            raise serializers.ValidationError({"plan": ["Choose a fee plan."]})
        if attrs["mode"] == "custom":
            items = [i for i in attrs.get("items") or [] if str(i.get("description", "")).strip() or i.get("amount")]
            if not items:
                raise serializers.ValidationError({"items": ["Add at least one fee item."]})
            for i in items:
                if not str(i.get("description", "")).strip():
                    raise serializers.ValidationError({"items": ["Every fee item needs a description."]})
            attrs["items"] = [{"description": str(i["description"]).strip()[:150], "amount": i.get("amount")}
                              for i in items]
        return attrs
