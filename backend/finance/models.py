from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.models import TenantScopedModel
from core.numbering import next_code

MONEY = {"max_digits": 12, "decimal_places": 2}
POSITIVE = [MinValueValidator(Decimal("0.01"))]


class FeePlan(TenantScopedModel):
    """Fee structure for a grade/program and term/semester (e.g. 'Grade 4 – Term 3 2026')."""

    name = models.CharField(max_length=150)
    period = models.ForeignKey("admissions.AcademicPeriod", null=True, blank=True, on_delete=models.PROTECT,
                               related_name="+")
    applies_to = models.CharField(max_length=120, blank=True, help_text="Grade level or program; blank = everyone")
    due_days = models.PositiveIntegerField(default=30)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def total(self):
        return sum((i.amount for i in self.items.all()), Decimal("0"))


class FeePlanItem(TenantScopedModel):
    plan = models.ForeignKey(FeePlan, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=150)
    amount = models.DecimalField(**MONEY, validators=POSITIVE)

    class Meta:
        ordering = ["id"]


class Invoice(TenantScopedModel):
    class Status(models.TextChoices):
        DRAFT = "draft"
        ISSUED = "issued"
        PARTIAL = "partial"
        PAID = "paid"
        VOID = "void"

    number = models.CharField(max_length=32)
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="invoices")
    fee_plan = models.ForeignKey(FeePlan, null=True, blank=True, on_delete=models.PROTECT, related_name="invoices")
    period = models.ForeignKey("admissions.AcademicPeriod", null=True, blank=True, on_delete=models.PROTECT,
                               related_name="+")
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    currency = models.CharField(max_length=3)
    subtotal = models.DecimalField(**MONEY, default=0)
    discount_amount = models.DecimalField(**MONEY, default=0)
    discount_reason = models.CharField(max_length=150, blank=True)  # e.g. "Merit scholarship 25%"
    total = models.DecimalField(**MONEY, default=0)
    amount_paid = models.DecimalField(**MONEY, default=0)
    balance = models.DecimalField(**MONEY, default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ISSUED)
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-issue_date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_invoice_number"),
            # A student is billed once per fee plan (prevents double billing on bulk issue).
            models.UniqueConstraint(fields=["student", "fee_plan"], condition=~models.Q(status="void"),
                                    name="one_invoice_per_student_plan"),
            models.CheckConstraint(condition=models.Q(balance__gte=0), name="invoice_balance_not_negative"),
            models.CheckConstraint(condition=models.Q(discount_amount__gte=0), name="invoice_discount_not_negative"),
        ]

    def __str__(self):
        return self.number

    @property
    def is_overdue(self):
        return self.balance > 0 and self.status in ("issued", "partial") and self.due_date < timezone.localdate()

    def recalculate(self):
        """Derive totals and status from lines, discount and payments. Call before saving."""
        self.subtotal = sum((line.amount for line in self.lines.all()), Decimal("0"))
        self.total = max(self.subtotal - self.discount_amount, Decimal("0"))
        self.amount_paid = sum((p.amount for p in self.payments.all()), Decimal("0"))
        self.balance = max(self.total - self.amount_paid, Decimal("0"))
        if self.status not in (self.Status.VOID, self.Status.DRAFT):
            if self.balance == 0:
                self.status = self.Status.PAID
            elif self.amount_paid > 0:
                self.status = self.Status.PARTIAL
            else:
                self.status = self.Status.ISSUED

    @staticmethod
    def next_number(tenant):
        year = timezone.localdate().year
        return next_code(Invoice.objects.filter(tenant=tenant), "number", f"INV-{year}-", 5)


class InvoiceLine(TenantScopedModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=150)
    amount = models.DecimalField(**MONEY, validators=POSITIVE)

    class Meta:
        ordering = ["id"]


class Payment(TenantScopedModel):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BANK_TRANSFER = "bank_transfer", "Bank transfer"
        MOBILE_MONEY = "mobile_money", "Mobile money"
        MOCK_ONLINE = "mock_online", "Online (MOCK – no real payment processed)"

    receipt_no = models.CharField(max_length=32)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(**MONEY, validators=POSITIVE)
    method = models.CharField(max_length=20, choices=Method.choices)
    reference = models.CharField(max_length=80, blank=True)
    paid_at = models.DateTimeField(default=timezone.now)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-paid_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "receipt_no"], name="unique_receipt_no"),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_amount_positive"),
        ]

    def __str__(self):
        return self.receipt_no

    @staticmethod
    def next_receipt_no(tenant):
        year = timezone.localdate().year
        return next_code(Payment.objects.filter(tenant=tenant), "receipt_no", f"RCT-{year}-", 5)
