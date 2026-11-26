"""Finance business rules. All money changes go through these functions."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from comms.services import notify
from core.audit import log_event
from core.exceptions import BusinessRuleViolation
from core.models import Tenant

from .models import Invoice, InvoiceLine, Payment


def to_money(value, field="amount"):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise BusinessRuleViolation("Enter a valid amount.", code="invalid_amount",
                                    fields={field: ["Invalid amount."]}) from None
    if not amount.is_finite():
        raise BusinessRuleViolation("Enter a valid amount.", code="invalid_amount", fields={field: ["Invalid amount."]})
    return amount


def _lock_tenant(tenant):
    """Serialise number generation (invoice / receipt numbers) per tenant."""
    Tenant.objects.select_for_update().get(pk=tenant.pk)


@transaction.atomic
def create_invoice(*, tenant, student, lines, due_date=None, fee_plan=None, period=None,
                   discount_amount=0, discount_reason="", notes="", user=None, request=None):
    if student.tenant_id != tenant.id:
        raise BusinessRuleViolation("Student not found.", code="not_found")
    if not lines:
        raise BusinessRuleViolation("An invoice needs at least one line.", code="invoice_no_lines")
    if fee_plan and Invoice.objects.filter(student=student, fee_plan=fee_plan).exclude(status="void").exists():
        raise BusinessRuleViolation(f"{student.person.full_name} has already been invoiced for {fee_plan.name}.",
                                    code="duplicate_invoice")
    clean_lines = []
    for line in lines:
        amount = to_money(line["amount"])
        if amount <= 0:
            raise BusinessRuleViolation("Each invoice line must be greater than zero.", code="invalid_amount")
        clean_lines.append((line["description"], amount))
    subtotal = sum((a for _, a in clean_lines), Decimal("0"))
    discount = to_money(discount_amount or 0, "discount_amount")
    if discount < 0 or discount > subtotal:
        raise BusinessRuleViolation("The discount must be between 0 and the invoice subtotal.",
                                    code="invalid_discount", fields={"discount_amount": ["Out of range."]})
    if discount > 0 and not discount_reason:
        raise BusinessRuleViolation("Give a reason for the discount or scholarship.", code="discount_reason_required",
                                    fields={"discount_reason": ["Required when a discount is applied."]})
    issue_date = timezone.localdate()
    due_date = due_date or issue_date + timedelta(days=fee_plan.due_days if fee_plan else 30)
    if due_date < issue_date:
        raise BusinessRuleViolation("The due date cannot be before the issue date.", code="invalid_due_date",
                                    fields={"due_date": ["Must be today or later."]})

    _lock_tenant(tenant)
    invoice = Invoice.objects.create(
        tenant=tenant, number=Invoice.next_number(tenant), student=student, fee_plan=fee_plan, period=period,
        issue_date=issue_date, due_date=due_date, currency=tenant.currency, discount_amount=discount,
        discount_reason=discount_reason, notes=notes, created_by=user)
    InvoiceLine.objects.bulk_create(
        [InvoiceLine(tenant=tenant, invoice=invoice, description=d, amount=a) for d, a in clean_lines])
    invoice.recalculate()
    invoice.save()
    log_event("invoice.issued", request=request, actor=user, tenant=tenant, target=invoice,
              changes={"total": str(invoice.total), "student": student.student_no})
    return invoice


@transaction.atomic
def record_payment(*, invoice, amount, method, reference="", notes="", user=None, request=None):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)  # no double-spend under concurrency
    amount = to_money(amount)
    if invoice.status in (Invoice.Status.VOID, Invoice.Status.DRAFT):
        raise BusinessRuleViolation(f"Payments cannot be posted to a {invoice.status} invoice.",
                                    code="invoice_not_payable")
    if amount <= 0:
        raise BusinessRuleViolation("The payment amount must be greater than zero.", code="invalid_amount",
                                    fields={"amount": ["Must be greater than zero."]})
    if amount > invoice.balance:
        raise BusinessRuleViolation(
            f"The payment ({amount}) is more than the outstanding balance ({invoice.balance}).",
            code="overpayment", fields={"amount": [f"Maximum is {invoice.balance}."]})
    if method not in Payment.Method.values:
        raise BusinessRuleViolation("Choose a valid payment method.", code="invalid_method",
                                    fields={"method": ["Invalid choice."]})
    _lock_tenant(invoice.tenant)
    payment = Payment.objects.create(
        tenant=invoice.tenant, receipt_no=Payment.next_receipt_no(invoice.tenant), invoice=invoice,
        student=invoice.student, amount=amount, method=method, reference=reference, notes=notes, received_by=user)
    invoice.recalculate()
    invoice.save()
    log_event("payment.recorded", request=request, actor=user, tenant=invoice.tenant, target=payment,
              changes={"invoice": invoice.number, "amount": str(amount), "method": method,
                       "balance_after": str(invoice.balance)})
    guardians = [link.guardian.user for link in invoice.student.guardian_links.select_related("guardian__user")]
    notify([*guardians, invoice.student.user], f"Payment received – {payment.receipt_no}",
           f"{invoice.currency} {amount} received for {invoice.number}. Balance: {invoice.currency} {invoice.balance}.",
           kind="fee")
    return payment


@transaction.atomic
def void_invoice(*, invoice, reason, user=None, request=None):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.payments.exists():
        raise BusinessRuleViolation("An invoice with payments cannot be voided.", code="invoice_has_payments")
    if invoice.status == Invoice.Status.VOID:
        raise BusinessRuleViolation("This invoice is already void.", code="already_void")
    invoice.status, invoice.balance = Invoice.Status.VOID, Decimal("0")
    invoice.notes = f"VOID: {reason}"[:255]
    invoice.save()
    log_event("invoice.voided", request=request, actor=user, tenant=invoice.tenant, target=invoice,
              changes={"reason": reason})
    return invoice


@transaction.atomic
def apply_discount(*, invoice, amount, reason, user=None, request=None):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    amount = to_money(amount, "discount_amount")
    if invoice.status in (Invoice.Status.VOID, Invoice.Status.PAID):
        raise BusinessRuleViolation(f"A {invoice.status} invoice cannot be discounted.", code="invoice_locked")
    if not reason:
        raise BusinessRuleViolation("Give a reason for the discount or scholarship.", code="discount_reason_required",
                                    fields={"reason": ["Required."]})
    if amount < 0 or amount > invoice.subtotal - invoice.amount_paid:
        raise BusinessRuleViolation("The discount cannot exceed the unpaid part of the invoice.",
                                    code="invalid_discount", fields={"amount": ["Out of range."]})
    before = invoice.discount_amount
    invoice.discount_amount, invoice.discount_reason = amount, reason
    invoice.recalculate()
    invoice.save()
    log_event("invoice.discounted", request=request, actor=user, tenant=invoice.tenant, target=invoice,
              changes={"before": str(before), "after": str(amount), "reason": reason})
    return invoice
