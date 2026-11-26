"""
Dashboards and generated student documents.

Dashboards combine shared data (students, fees, calendar) with figures supplied by the school or
university module through DASHBOARD_PROVIDERS, so each module owns its own metrics.
"""
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.http import Http404, HttpResponse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admissions.models import AcademicPeriod, Enrollment
from comms.services import save_generated_pdf
from core.audit import log_event
from core.exceptions import BusinessRuleViolation
from core.permissions import (
    IsSchoolTenant,
    IsTenantUser,
    IsUniversityTenant,
    RolePermission,
)
from finance.models import Invoice
from people.models import Student
from people.scoping import visible_students

from .pdf import BrandedDocument, student_id_card

# tenant_type -> fn(tenant) -> dict merged into the dashboard response
DASHBOARD_PROVIDERS = {}


def register_dashboard_provider(tenant_type):
    def deco(fn):
        DASHBOARD_PROVIDERS[tenant_type] = fn
        return fn
    return deco


def _fees(tenant):
    agg = Invoice.objects.filter(tenant=tenant).exclude(status__in=["void", "draft"]).aggregate(
        collected=Sum("amount_paid"), outstanding=Sum("balance"))
    return agg["collected"] or Decimal("0"), agg["outstanding"] or Decimal("0")


def _upcoming(tenant):
    today = timezone.localdate()
    periods = AcademicPeriod.objects.filter(tenant=tenant, end_date__gte=today).order_by("start_date")[:3]
    return [{"title": f"{p.name} {'ends' if p.start_date <= today else 'starts'}",
             "meta": f"{(p.end_date if p.start_date <= today else p.start_date):%a %d %b %Y}"} for p in periods]


def _current(tenant, kind):
    return AcademicPeriod.objects.filter(tenant=tenant, kind=kind, is_current=True).first()


class SchoolDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsTenantUser, IsSchoolTenant, RolePermission]
    required_perms = {"get": "reports.view"}

    def get(self, request):
        tenant = request.user.tenant
        active = Student.objects.filter(tenant=tenant, status=Student.Status.ACTIVE)
        collected, outstanding = _fees(tenant)
        by_level = active.values("current_level").annotate(n=Count("id")).order_by("current_level")
        term = _current(tenant, AcademicPeriod.Kind.TERM)
        data = {
            "term": term.name if term else "No current term",
            "currency": tenant.currency,
            "stats": {"pupils": active.count(), "attendance_today": None, "fees_collected": collected,
                      "fees_outstanding": outstanding, "pass_rate": None},
            "enrollment_by_grade": [{"label": r["current_level"] or "Unplaced", "value": r["n"]} for r in by_level],
            "attendance_trend": [],
            "pass_rate_by_term": [],
            "fee_collection": [{"label": "Collected", "value": collected}, {"label": "Outstanding", "value": outstanding}],
            "upcoming": _upcoming(tenant),
        }
        provider = DASHBOARD_PROVIDERS.get("school")
        if provider:
            extra = provider(tenant)
            data["stats"].update(extra.pop("stats", {}))
            data.update(extra)
        return Response(data)


class UniversityDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsTenantUser, IsUniversityTenant, RolePermission]
    required_perms = {"get": "reports.view"}

    def get(self, request):
        tenant = request.user.tenant
        active = Student.objects.filter(tenant=tenant, status=Student.Status.ACTIVE)
        _, outstanding = _fees(tenant)
        by_program = active.values("current_level").annotate(n=Count("id")).order_by("-n")
        semester = _current(tenant, AcademicPeriod.Kind.SEMESTER)
        data = {
            "semester": semester.name if semester else "No current semester",
            "currency": tenant.currency,
            "stats": {"students": active.count(), "registrations": 0, "avg_cgpa": None,
                      "fee_arrears": outstanding, "on_probation": 0},
            "enrollment_by_program": [{"label": r["current_level"] or "Undeclared", "value": r["n"]} for r in by_program],
            "course_demand": [],
            "gpa_distribution": [],
            "credit_completion": [],
            "upcoming": _upcoming(tenant),
        }
        provider = DASHBOARD_PROVIDERS.get("university")
        if provider:
            extra = provider(tenant)
            data["stats"].update(extra.pop("stats", {}))
            data.update(extra)
        return Response(data)


class _StudentDocumentView(APIView):
    """Generates an official PDF for one student, saves a copy to their documents and returns it."""

    permission_classes = [IsAuthenticated, IsTenantUser]

    def get_student(self, request, pk):
        student = visible_students(request.user).filter(pk=pk).first()
        if student is None:
            raise Http404
        is_self_or_guardian = (student.user_id == request.user.id
                               or student.guardian_links.filter(guardian__user=request.user).exists())
        if not (request.user.has_perm_code("documents.manage", "students.manage") or is_self_or_guardian):
            raise PermissionDenied("You can't generate documents for this student.")
        return student

    def respond(self, request, student, kind, title, pdf_bytes):
        save_generated_pdf(tenant=request.user.tenant, kind=kind, title=title, pdf_bytes=pdf_bytes, student=student,
                           user=request.user)
        log_event(f"document.generated.{kind}", request=request, target=student)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{student.student_no}-{kind}.pdf"'
        return response


class StudentIdCardView(_StudentDocumentView):
    def get(self, request, pk):
        student = self.get_student(request, pk)
        if student.status != Student.Status.ACTIVE:
            raise BusinessRuleViolation("ID cards are only issued to active students.", code="student_not_active")
        tenant = request.user.tenant
        level = " · ".join(p for p in (student.current_level, student.current_section) if p)
        today = timezone.localdate()
        valid = date(today.year + (1 if today.month >= 8 else 0), 8, 31)
        pdf = student_id_card(institution=tenant.name, name=student.person.full_name, student_no=student.student_no,
                              level=level or "—", valid_until=valid,
                              mode_label="School" if tenant.is_school else "University",
                              photo=_photo_bytes(student))
        return self.respond(request, student, "id_card", f"Student ID – {student.person.full_name}", pdf)


def _photo_bytes(student):
    if not student.photo:
        return None
    try:
        with student.photo.open("rb") as f:
            return f.read()
    except OSError:
        return None


class EnrollmentLetterView(_StudentDocumentView):
    def get(self, request, pk):
        student = self.get_student(request, pk)
        tenant = request.user.tenant
        enrollment = student.enrollments.filter(status=Enrollment.Status.ACTIVE).select_related("period").first()
        if enrollment is None:
            raise BusinessRuleViolation("This student has no active enrollment.", code="no_active_enrollment")
        doc = BrandedDocument("Enrollment Verification Letter", tenant.name, reference=student.student_no,
                              subtitle="To whom it may concern")
        what = "pupil" if tenant.is_school else "student"
        level = enrollment.level_label + (f", {enrollment.section_label}" if enrollment.section_label else "")
        doc.paragraph(
            f"This is to certify that <b>{student.person.full_name}</b> (student number <b>{student.student_no}</b>) "
            f"is a registered {what} at <b>{tenant.name}</b>, enrolled in <b>{level}</b>"
            f"{' for ' + enrollment.period.name if enrollment.period else ''}, with effect from "
            f"{enrollment.start_date:%d %B %Y}. Their current status is <b>{student.status}</b>.")
        doc.paragraph("This letter is issued at the request of the student for official purposes.")
        doc.key_values([("Date of birth", student.person.date_of_birth and f"{student.person.date_of_birth:%d %b %Y}"),
                        ("Admitted", f"{student.admission_date:%d %b %Y}")])
        doc.signature("Registrar / Head of Institution")
        return self.respond(request, student, "enrollment_letter", f"Enrollment letter – {student.person.full_name}",
                            doc.render())
