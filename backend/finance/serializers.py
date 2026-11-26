from rest_framework import serializers

from admissions.models import AcademicPeriod
from core.tenancy import TenantModelSerializer, TenantPrimaryKeyRelatedField
from people.models import Student

from .models import FeePlan, FeePlanItem, Invoice, InvoiceLine, Payment


class FeePlanItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeePlanItem
        fields = ["id", "description", "amount"]


class FeePlanSerializer(TenantModelSerializer):
    items = FeePlanItemSerializer(many=True)
    period = TenantPrimaryKeyRelatedField(queryset=AcademicPeriod.objects.all(), required=False, allow_null=True)
    period_name = serializers.CharField(source="period.name", read_only=True, default=None)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, coerce_to_string=False)
    invoices_issued = serializers.SerializerMethodField()

    class Meta:
        model = FeePlan
        fields = ["id", "name", "period", "period_name", "applies_to", "due_days", "is_active", "items", "total",
                  "invoices_issued"]

    def get_invoices_issued(self, obj):
        return obj.invoices.exclude(status="void").count()

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("Add at least one fee item.")
        return items

    def create(self, validated):
        items = validated.pop("items")
        plan = FeePlan.objects.create(**validated)
        FeePlanItem.objects.bulk_create([FeePlanItem(tenant=plan.tenant, plan=plan, **i) for i in items])
        return plan

    def update(self, plan, validated):
        items = validated.pop("items", None)
        if items is not None and plan.invoices.exclude(status="void").exists():
            raise serializers.ValidationError({"items": ["Items cannot change after invoices have been issued."]})
        plan = super().update(plan, validated)
        if items is not None:
            plan.items.all().delete()
            FeePlanItem.objects.bulk_create([FeePlanItem(tenant=plan.tenant, plan=plan, **i) for i in items])
        return plan


class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = ["id", "description", "amount"]


class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)
    student_name = serializers.CharField(source="student.person.full_name", read_only=True)
    received_by = serializers.EmailField(source="received_by.email", read_only=True, default=None)
    method_label = serializers.CharField(source="get_method_display", read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "receipt_no", "invoice", "invoice_number", "student", "student_name", "amount", "method",
                  "method_label", "reference", "paid_at", "received_by", "notes"]


class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    student_name = serializers.CharField(source="student.person.full_name", read_only=True)
    student_no = serializers.CharField(source="student.student_no", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invoice
        fields = ["id", "number", "student", "student_name", "student_no", "fee_plan", "period", "issue_date",
                  "due_date", "currency", "subtotal", "discount_amount", "discount_reason", "total", "amount_paid",
                  "balance", "status", "is_overdue", "notes", "lines", "payments"]


class InvoiceCreateSerializer(serializers.Serializer):
    student = TenantPrimaryKeyRelatedField(queryset=Student.objects.all())
    lines = InvoiceLineSerializer(many=True)
    due_date = serializers.DateField(required=False)
    period = TenantPrimaryKeyRelatedField(queryset=AcademicPeriod.objects.all(), required=False, allow_null=True)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    discount_reason = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class IssueFromPlanSerializer(serializers.Serializer):
    students = TenantPrimaryKeyRelatedField(queryset=Student.objects.all(), many=True, required=False)
    due_date = serializers.DateField(required=False)


class PaymentCreateSerializer(serializers.Serializer):
    invoice = TenantPrimaryKeyRelatedField(queryset=Invoice.objects.all())
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    method = serializers.ChoiceField(choices=[c for c in Payment.Method.choices if c[0] != "mock_online"])
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class DiscountSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reason = serializers.CharField(max_length=150)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200)
