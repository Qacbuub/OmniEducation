import csv
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from core.audit import log_event
from core.exceptions import BusinessRuleViolation
from core.permissions import AUTHENTICATED, IsTenantUser, RolePermission
from core.tenancy import TenantScopedViewSetMixin
from people.models import Student
from people.scoping import visible_students
from reports.pdf import BrandedDocument, mm

from . import services
from .models import FeePlan, Invoice, Payment
from .serializers import (
    DiscountSerializer,
    FeePlanSerializer,
    InvoiceCreateSerializer,
    InvoiceSerializer,
    IssueFromPlanSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
    ReasonSerializer,
)


def money(v, currency):
    return f"{currency} {Decimal(v):,.2f}"


class FeePlanViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = FeePlan.objects.prefetch_related("items").select_related("period")
    serializer_class = FeePlanSerializer
    required_perms = {"list": "fees.view", "retrieve": "fees.view", "*": "fees.manage"}
    filterset_fields = ["period", "is_active", "applies_to"]
    search_fields = ["name", "applies_to"]
    audit_name = "fee_plan"

    def perform_destroy(self, instance):
        if instance.invoices.exists():
            raise BusinessRuleViolation("A fee plan with invoices cannot be deleted; deactivate it instead.",
                                        code="plan_in_use")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        """Bill every matching active student (or the given students) for this plan. Already-billed students are skipped."""
        plan = self.get_object()
        s = IssueFromPlanSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        if not plan.is_active:
            raise BusinessRuleViolation("This fee plan is inactive.", code="plan_inactive")
        students = s.validated_data.get("students")
        if not students:
            qs = Student.objects.filter(tenant=self.tenant, status=Student.Status.ACTIVE)
            if plan.applies_to:
                qs = qs.filter(current_level=plan.applies_to)
            students = list(qs.select_related("person"))
        already = set(Invoice.objects.filter(fee_plan=plan).exclude(status="void").values_list("student_id", flat=True))
        lines = [{"description": i.description, "amount": i.amount} for i in plan.items.all()]
        created = []
        for student in students:
            if student.id in already:
                continue
            inv = services.create_invoice(tenant=self.tenant, student=student, lines=lines, fee_plan=plan,
                                          period=plan.period, due_date=s.validated_data.get("due_date"),
                                          user=request.user, request=request)
            created.append(inv.number)
        return Response({"issued": len(created), "skipped": len(students) - len(created), "invoices": created},
                         status=status.HTTP_201_CREATED)


class InvoiceViewSet(TenantScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Finance staff see every invoice; guardians and students see only their own (or linked children's)."""

    serializer_class = InvoiceSerializer
    required_perms = {"list": AUTHENTICATED, "retrieve": AUTHENTICATED, "pay_online": AUTHENTICATED,
                      "create": "fees.manage", "void": "fees.manage", "discount": "fees.manage"}
    filterset_fields = ["status", "student", "fee_plan", "period"]
    search_fields = ["number", "student__student_no", "student__person__first_name", "student__person__last_name"]
    ordering_fields = ["issue_date", "due_date", "balance", "total"]

    def get_queryset(self):
        user = self.request.user
        qs = Invoice.objects.filter(tenant=user.tenant).select_related("student__person").prefetch_related(
            "lines", "payments__received_by", "payments__student__person")
        if not user.has_perm_code("fees.view"):
            qs = qs.filter(student__in=visible_students(user)).exclude(status="draft")
        return qs

    def create(self, request, *args, **kwargs):
        s = InvoiceCreateSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        d = s.validated_data
        inv = services.create_invoice(tenant=self.tenant, student=d["student"], lines=d["lines"],
                                      due_date=d.get("due_date"), period=d.get("period"),
                                      discount_amount=d["discount_amount"], discount_reason=d["discount_reason"],
                                      notes=d["notes"], user=request.user, request=request)
        return Response(InvoiceSerializer(inv).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        s = ReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        inv = services.void_invoice(invoice=self.get_object(), reason=s.validated_data["reason"], user=request.user,
                                    request=request)
        return Response(InvoiceSerializer(inv).data)

    @action(detail=True, methods=["post"])
    def discount(self, request, pk=None):
        s = DiscountSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        inv = services.apply_discount(invoice=self.get_object(), amount=s.validated_data["amount"],
                                      reason=s.validated_data["reason"], user=request.user, request=request)
        return Response(InvoiceSerializer(inv).data)

    @action(detail=True, methods=["post"], url_path="pay-online")
    def pay_online(self, request, pk=None):
        """MOCK online payment for guardians/students. No card data is requested, sent or stored."""
        inv = self.get_object()
        payment = services.record_payment(invoice=inv, amount=request.data.get("amount"), method="mock_online",
                                          reference=f"MOCK-{timezone.now():%Y%m%d%H%M%S}",
                                          notes="Mock payment – no real money moved", user=request.user,
                                          request=request)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentViewSet(TenantScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = PaymentSerializer
    required_perms = {"list": AUTHENTICATED, "retrieve": AUTHENTICATED, "receipt": AUTHENTICATED,
                      "create": "payments.record"}
    filterset_fields = ["method", "student", "invoice"]
    search_fields = ["receipt_no", "reference", "invoice__number", "student__student_no"]

    def get_queryset(self):
        user = self.request.user
        qs = Payment.objects.filter(tenant=user.tenant).select_related("invoice", "student__person", "received_by")
        if not user.has_perm_code("fees.view"):
            qs = qs.filter(student__in=visible_students(user))
        return qs

    def create(self, request, *args, **kwargs):
        s = PaymentCreateSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        d = s.validated_data
        payment = services.record_payment(invoice=d["invoice"], amount=d["amount"], method=d["method"],
                                          reference=d["reference"], notes=d["notes"], user=request.user,
                                          request=request)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def receipt(self, request, pk=None):
        p = self.get_object()
        inv, cur = p.invoice, p.invoice.currency
        doc = BrandedDocument("Payment Receipt", self.tenant.name,
                              subtitle=f"Receipt for {p.student.person.full_name} ({p.student.student_no})",
                              reference=p.receipt_no)
        doc.key_values([("Student", p.student.person.full_name), ("Student No", p.student.student_no),
                        ("Invoice", inv.number), ("Method", p.get_method_display()),
                        ("Paid on", f"{p.paid_at:%d %b %Y %H:%M}"), ("Reference", p.reference),
                        ("Received by", p.received_by.email if p.received_by else "Online")])
        doc.heading("Invoice summary")
        rows = [[line.description, money(line.amount, cur)] for line in inv.lines.all()]
        if inv.discount_amount:
            rows.append([f"Discount: {inv.discount_reason}", f"-{money(inv.discount_amount, cur)}"])
        rows.append(["Invoice total", money(inv.total, cur)])
        doc.table(["Description", "Amount"], rows, col_widths=[120 * mm, 60 * mm], align_right=(1,))
        doc.total_box("Amount paid", money(p.amount, cur))
        doc.total_box("Balance remaining", money(inv.balance, cur))
        if p.method == Payment.Method.MOCK_ONLINE:
            doc.stamp("MOCK PAYMENT – NOT REAL MONEY")
        else:
            doc.stamp("PAID IN FULL" if inv.balance == 0 else "PARTIAL PAYMENT RECEIVED")
        log_event("receipt.downloaded", request=request, target=p)
        response = HttpResponse(doc.render(), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{p.receipt_no}.pdf"'
        return response


class ArrearsView(APIView):
    """Outstanding balances per student, with ageing buckets. ?export=csv downloads a CSV."""

    permission_classes = [IsTenantUser, RolePermission]
    required_perms = {"get": "fees.view"}

    def get(self, request):
        tenant = request.user.tenant
        today = timezone.localdate()
        open_inv = Invoice.objects.filter(tenant=tenant, status__in=["issued", "partial"], balance__gt=0)
        rows = (open_inv.values("student_id", "student__student_no", "student__person__first_name",
                                "student__person__last_name", "student__current_level")
                .annotate(outstanding=Sum("balance"), invoices=Count("id"),
                          overdue=Sum("balance", filter=Q(due_date__lt=today)))
                .order_by("-outstanding"))
        results = [{
            "student_id": r["student_id"], "student_no": r["student__student_no"],
            "name": f'{r["student__person__first_name"]} {r["student__person__last_name"]}',
            "level": r["student__current_level"], "invoices": r["invoices"],
            "outstanding": r["outstanding"], "overdue": r["overdue"] or Decimal("0"),
        } for r in rows]
        buckets = {"current": Decimal("0"), "1_30": Decimal("0"), "31_60": Decimal("0"), "over_60": Decimal("0")}
        for inv in open_inv.only("balance", "due_date"):
            days = (today - inv.due_date).days
            key = "current" if days <= 0 else "1_30" if days <= 30 else "31_60" if days <= 60 else "over_60"
            buckets[key] += inv.balance
        if request.query_params.get("export") == "csv":
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="arrears.csv"'
            w = csv.writer(response)
            w.writerow(["Student No", "Name", "Level", "Invoices", "Outstanding", "Overdue"])
            for r in results:
                w.writerow([r["student_no"], r["name"], r["level"], r["invoices"], r["outstanding"], r["overdue"]])
            return response
        totals = Invoice.objects.filter(tenant=tenant).exclude(status__in=["void", "draft"]).aggregate(
            billed=Sum("total"), collected=Sum("amount_paid"), outstanding=Sum("balance"))
        return Response({"currency": tenant.currency, "totals": {k: v or Decimal("0") for k, v in totals.items()},
                         "ageing": buckets, "results": results})
