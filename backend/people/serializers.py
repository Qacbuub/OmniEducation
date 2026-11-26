from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from core.tenancy import TenantModelSerializer, TenantPrimaryKeyRelatedField

from .models import EmergencyContact, Guardian, GuardianLink, Person, Staff, Student

PERSON_FIELDS = ["first_name", "middle_name", "last_name", "date_of_birth", "national_id", "gender", "email", "phone", "address"]


class PersonFieldsMixin(serializers.Serializer):
    """Flattens Person fields onto Student / Guardian / Staff serializers."""

    first_name = serializers.CharField(source="person.first_name", max_length=100)
    middle_name = serializers.CharField(source="person.middle_name", max_length=100, required=False, allow_blank=True)
    last_name = serializers.CharField(source="person.last_name", max_length=100)
    date_of_birth = serializers.DateField(source="person.date_of_birth", required=False, allow_null=True)
    national_id = serializers.CharField(source="person.national_id", max_length=40, required=False, allow_blank=True)
    gender = serializers.ChoiceField(source="person.gender", choices=Person.Gender.choices, required=False)
    email = serializers.EmailField(source="person.email", required=False, allow_blank=True)
    phone = serializers.CharField(source="person.phone", max_length=40, required=False, allow_blank=True)
    address = serializers.CharField(source="person.address", max_length=255, required=False, allow_blank=True)

    def validate(self, attrs):
        dob = attrs.get("person", {}).get("date_of_birth")
        if dob and dob > timezone.localdate():
            raise serializers.ValidationError({"date_of_birth": ["Date of birth cannot be in the future."]})
        return attrs

    def _save_person(self, instance, person_data, tenant):
        if instance is None:
            return Person.objects.create(tenant=tenant, **person_data)
        for k, v in person_data.items():
            setattr(instance.person, k, v)
        instance.person.save()
        return instance.person


class EmergencyContactSerializer(TenantModelSerializer):
    student = TenantPrimaryKeyRelatedField(queryset=Student.objects.all())

    class Meta:
        model = EmergencyContact
        fields = ["id", "student", "name", "relationship", "phone", "email", "is_primary"]


class GuardianSummarySerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="guardian.id")
    link_id = serializers.IntegerField(source="id")
    name = serializers.CharField(source="guardian.person.full_name")
    phone = serializers.CharField(source="guardian.person.phone")
    email = serializers.CharField(source="guardian.person.email")
    has_portal_account = serializers.SerializerMethodField()

    class Meta:
        model = GuardianLink
        fields = ["id", "link_id", "name", "relationship", "is_primary", "phone", "email", "has_portal_account"]

    def get_has_portal_account(self, link):
        return link.guardian.user_id is not None


class StudentListSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source="person.first_name")
    last_name = serializers.CharField(source="person.last_name")
    level = serializers.CharField(source="current_level")
    section = serializers.CharField(source="current_section")
    guardian = serializers.SerializerMethodField()
    balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, default=0, coerce_to_string=False)
    cgpa = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = ["id", "student_no", "first_name", "last_name", "level", "section", "guardian", "status",
                  "balance", "cgpa"]

    def get_guardian(self, obj):
        links = getattr(obj, "_prefetched_objects_cache", {}).get("guardian_links")
        links = links if links is not None else obj.guardian_links.select_related("guardian__person")
        primary = sorted(links, key=lambda link: not link.is_primary)
        return primary[0].guardian.person.full_name if primary else None

    def get_cgpa(self, obj):
        # Provided by the university module's academic-standing record when present.
        standing = getattr(obj, "academic_standing", None)
        return f"{standing.cgpa:.2f}" if standing and standing.cgpa is not None else None


class StudentDetailSerializer(PersonFieldsMixin, TenantModelSerializer):
    student_no = serializers.CharField(read_only=True)
    level = serializers.CharField(source="current_level", read_only=True)
    section = serializers.CharField(source="current_section", read_only=True)
    guardians = GuardianSummarySerializer(source="guardian_links", many=True, read_only=True)
    emergency_contacts = EmergencyContactSerializer(many=True, read_only=True)
    has_portal_account = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = ["id", "student_no", *PERSON_FIELDS, "status", "admission_date", "level", "section",
                  "guardians", "emergency_contacts", "has_portal_account", "photo_url", "created_at", "updated_at"]
        read_only_fields = ["status"]  # changed only through enrollment workflows

    def get_has_portal_account(self, obj):
        return obj.user_id is not None

    def get_photo_url(self, obj) -> str | None:
        # Versioned by updated_at so browsers refetch after a change.
        return f"/api/students/{obj.pk}/photo/?v={int(obj.updated_at.timestamp())}" if obj.photo else None

    @transaction.atomic
    def create(self, validated):
        tenant = validated.pop("tenant", None) or self.context["request"].user.tenant
        person = self._save_person(None, validated.pop("person"), tenant)
        return Student.objects.create(tenant=tenant, person=person, student_no=Student.next_student_no(tenant), **validated)

    @transaction.atomic
    def update(self, instance, validated):
        self._save_person(instance, validated.pop("person", {}), instance.tenant)
        return super().update(instance, validated)


class GuardianSerializer(PersonFieldsMixin, TenantModelSerializer):
    children = serializers.SerializerMethodField()
    has_portal_account = serializers.SerializerMethodField()

    class Meta:
        model = Guardian
        fields = ["id", *PERSON_FIELDS, "occupation", "children", "has_portal_account"]

    def get_children(self, obj):
        return [{"id": link.student_id, "name": link.student.person.full_name, "student_no": link.student.student_no,
                 "relationship": link.relationship} for link in obj.links.select_related("student__person")]

    def get_has_portal_account(self, obj):
        return obj.user_id is not None

    @transaction.atomic
    def create(self, validated):
        tenant = validated.pop("tenant", None) or self.context["request"].user.tenant
        person = self._save_person(None, validated.pop("person"), tenant)
        return Guardian.objects.create(tenant=tenant, person=person, **validated)

    @transaction.atomic
    def update(self, instance, validated):
        self._save_person(instance, validated.pop("person", {}), instance.tenant)
        return super().update(instance, validated)


class GuardianLinkSerializer(TenantModelSerializer):
    guardian = TenantPrimaryKeyRelatedField(queryset=Guardian.objects.all())
    student = TenantPrimaryKeyRelatedField(queryset=Student.objects.all())

    class Meta:
        model = GuardianLink
        fields = ["id", "guardian", "student", "relationship", "is_primary", "receives_notifications"]
        validators = []  # duplicate check below gives a clearer message

    def validate(self, attrs):
        guardian = attrs.get("guardian", getattr(self.instance, "guardian", None))
        student = attrs.get("student", getattr(self.instance, "student", None))
        dup = GuardianLink.objects.filter(guardian=guardian, student=student)
        if self.instance:
            dup = dup.exclude(pk=self.instance.pk)
        if dup.exists():
            raise serializers.ValidationError("This guardian is already linked to this student.")
        return attrs


class StaffSerializer(PersonFieldsMixin, TenantModelSerializer):
    role = serializers.CharField(source="user.role.code", read_only=True, default=None)
    account_email = serializers.EmailField(source="user.email", read_only=True, default=None)

    class Meta:
        model = Staff
        fields = ["id", "staff_no", *PERSON_FIELDS, "job_title", "department", "hire_date", "status", "role",
                  "account_email"]

    def validate_staff_no(self, value):
        tenant = self.context["request"].user.tenant
        qs = Staff.objects.filter(tenant=tenant, staff_no=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This staff number is already in use.")
        return value

    @transaction.atomic
    def create(self, validated):
        tenant = validated.pop("tenant", None) or self.context["request"].user.tenant
        person = self._save_person(None, validated.pop("person"), tenant)
        return Staff.objects.create(tenant=tenant, person=person, **validated)

    @transaction.atomic
    def update(self, instance, validated):
        self._save_person(instance, validated.pop("person", {}), instance.tenant)
        return super().update(instance, validated)
