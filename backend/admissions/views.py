from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from comms.models import Document
from comms.services import notify, notify_permission_holders, validate_upload
from core.audit import log_event
from core.emails import send_notification_email
from core.exceptions import BusinessRuleViolation
from core.models import Tenant
from core.permissions import AUTHENTICATED
from core.tenancy import TenantScopedViewSetMixin
from finance import services as finance
from finance.models import FeePlan
from people.models import Guardian, GuardianLink, Person, Student
from people.scoping import visible_students
from people.views import sniff_image

from .hooks import ENROLLMENT_HANDLERS
from .models import AcademicPeriod, Application, Enrollment
from .serializers import (
    AcademicPeriodSerializer,
    ApplicationSerializer,
    DecisionSerializer,
    EnrollBillingSerializer,
    EnrollmentSerializer,
    StatusChangeSerializer,
)


class AcademicPeriodViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = AcademicPeriod.objects.select_related("parent")
    serializer_class = AcademicPeriodSerializer
    required_perms = {"list": AUTHENTICATED, "retrieve": AUTHENTICATED, "*": "calendar.manage"}
    filterset_fields = ["kind", "parent", "is_current"]
    audit_name = "academic_period"

    @action(detail=True, methods=["post"], url_path="set-current")
    @transaction.atomic
    def set_current(self, request, pk=None):
        period = self.get_object()
        AcademicPeriod.objects.filter(tenant=self.tenant, kind=period.kind, is_current=True).update(is_current=False)
        period.is_current = True
        period.save(update_fields=["is_current"])
        log_event("academic_period.set_current", request=request, target=period)
        return Response(AcademicPeriodSerializer(period, context={"request": request}).data)


# ------------------------------------------------------------------ public online application
class PublicApplicationView(APIView):
    """Online application form for an institution (no login). Throttled per IP."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    def get_tenant(self, slug):
        return get_object_or_404(Tenant.objects.exclude(status=Tenant.Status.SUSPENDED), slug=slug)

    def get(self, request, slug):
        tenant = self.get_tenant(slug)
        intakes = AcademicPeriod.objects.filter(tenant=tenant, end_date__gte=timezone.localdate()).exclude(
            kind=AcademicPeriod.Kind.TERM)
        return Response({"institution": tenant.name, "type": tenant.type,
                         "intakes": [{"id": p.id, "name": p.name} for p in intakes]})

    def post(self, request, slug):
        tenant = self.get_tenant(slug)
        s = ApplicationSerializer(data=request.data, context={"request": request, "tenant": tenant})
        s.is_valid(raise_exception=True)
        app = s.save(tenant=tenant, source="online")
        notify_permission_holders(tenant, "admissions.manage", "New admission application",
                                  f"{app.full_name} applied for {app.requested_level}.", kind="admission",
                                  link=f"/admissions/{app.id}")
        send_notification_email(app, f"Application received – {tenant.name}",
                                f"Dear {app.first_name},\n\nWe received your application {app.application_no}. "
                                f"Your status reference is {app.reference_code}.")
        log_event("application.submitted", tenant=tenant, target=app, request=None)
        return Response({"application_no": app.application_no, "reference_code": app.reference_code},
                        status=status.HTTP_201_CREATED)


class PublicApplicationStatusView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    def get(self, request, slug, reference):
        app = get_object_or_404(Application, tenant__slug=slug, reference_code=reference.upper())
        return Response({"application_no": app.application_no, "status": app.status,
                         "requested_level": app.requested_level})


class PublicApplicationDocumentView(APIView):
    """Applicants attach supporting documents using their private reference code."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, slug, reference):
        app = get_object_or_404(Application, tenant__slug=slug, reference_code=reference.upper(),
                                status__in=["submitted", "under_review"])
        f = request.FILES.get("file")
        if not f:
            raise ValidationError({"file": ["Choose a file to upload."]})
        validate_upload(f)
        if app.documents.count() >= 10:
            raise BusinessRuleViolation("An application can have at most 10 documents.", code="too_many_documents")
        kind = request.data.get("kind", Document.Kind.SUPPORTING)
        if kind not in Document.Kind.values:
            kind = Document.Kind.SUPPORTING
        doc = Document.objects.create(tenant=app.tenant, application=app, kind=kind, file=f,
                                      title=request.data.get("title") or f.name, original_name=f.name, size=f.size)
        log_event("application.document_uploaded", tenant=app.tenant, target=doc)
        return Response({"id": doc.id, "title": doc.title}, status=status.HTTP_201_CREATED)


# ------------------------------------------------------------------ staff review workflow
class ApplicationViewSet(TenantScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                         mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Application.objects.select_related("reviewed_by", "intake_period")
    serializer_class = ApplicationSerializer
    required_perms = {"list": "admissions.view", "retrieve": "admissions.view", "photo": "admissions.view",
                      "billing_options": "admissions.view", "*": "admissions.manage"}
    filterset_fields = ["status", "intake_period", "source"]
    search_fields = ["application_no", "first_name", "last_name", "email", "requested_level"]
    ordering_fields = ["submitted_at", "last_name"]
    audit_name = "application"

    def perform_create(self, serializer):
        app = serializer.save(tenant=self.tenant, source="staff")
        log_event("application.created", request=self.request, target=app)

    def perform_update(self, serializer):
        if serializer.instance.status not in ("submitted", "under_review"):
            raise BusinessRuleViolation("Applications can only be edited before a decision is made.",
                                        code="application_locked")
        super().perform_update(serializer)

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        """Move an application along its workflow: review, approve/offer, reject, accept/decline offer, withdraw."""
        app = self.get_object()
        s = DecisionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        new = s.validated_data["status"]
        if new == "enrolled":
            raise BusinessRuleViolation("Use the enroll action to enroll an applicant.", code="use_enroll")
        if not app.can_transition(new):
            raise BusinessRuleViolation(
                f"An application that is '{app.status}' cannot move to '{new}'. "
                f"Allowed: {', '.join(app.allowed_transitions()) or 'none'}.", code="invalid_transition")
        old = app.status
        app.status = new
        app.decision_notes = s.validated_data.get("notes", app.decision_notes)
        app.reviewed_by, app.reviewed_at = request.user, timezone.now()
        app.save()
        log_event("application.status_changed", request=request, target=app, changes={"from": old, "to": new})
        if new in ("approved", "offered", "rejected"):
            messages = {
                "approved": "Congratulations! Your application has been approved.",
                "offered": "Congratulations! You have received an offer of admission.",
                "rejected": "We regret that we cannot offer you a place at this time.",
            }
            send_notification_email(app, f"Application {app.application_no} update", messages[new])
        return Response(ApplicationSerializer(app, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def enroll(self, request, pk=None):
        """Approved applicant -> enrolled pupil (school) / accepted offer -> matriculated student (university).

        Optional `billing`: {"mode": "plan", "plan": id} bills a fee plan straight away; {"mode": "custom",
        "items": [{description, amount}]} bills one-off amounts (needs fees.manage). Everything happens in one
        transaction: if the invoice fails, the student is not enrolled either.
        """
        app = Application.objects.select_for_update().get(pk=self.get_object().pk)
        if not app.can_transition("enrolled"):
            needed = "approved" if self.tenant.is_school else "offer_accepted"
            raise BusinessRuleViolation(f"Only {needed.replace('_', ' ')} applications can be enrolled.",
                                        code="invalid_transition")
        billing = EnrollBillingSerializer(data=request.data.get("billing") or {"mode": "none"})
        billing.is_valid(raise_exception=True)
        billing = billing.validated_data
        if billing["mode"] == "custom" and not request.user.has_perm_code("fees.manage"):
            raise BusinessRuleViolation("Only finance staff can bill a custom amount. Choose a fee plan instead.",
                                        code="permission_denied")
        person = Person.objects.create(
            tenant=self.tenant, first_name=app.first_name, middle_name=app.middle_name, last_name=app.last_name,
            date_of_birth=app.date_of_birth, national_id=app.national_id, gender=app.gender or "undisclosed",
            email=app.email, phone=app.phone,
            address=app.address)
        student = Student.objects.create(tenant=self.tenant, person=person, application=app,
                                         student_no=Student.next_student_no(self.tenant))
        if app.guardian_name:
            first, _, last = app.guardian_name.partition(" ")
            gperson = Person.objects.create(tenant=self.tenant, first_name=first, last_name=last or "-",
                                            phone=app.guardian_phone, email=app.guardian_email)
            guardian = Guardian.objects.create(tenant=self.tenant, person=gperson)
            GuardianLink.objects.create(tenant=self.tenant, guardian=guardian, student=student,
                                        relationship=app.guardian_relationship or "parent", is_primary=True)
        Document.objects.filter(application=app).update(student=student)

        handler = ENROLLMENT_HANDLERS.get(self.tenant.type)
        if handler:
            level, section = handler(request, app, student, request.data)
        else:
            level, section = app.requested_level, ""
        student.current_level, student.current_section = level, section
        Enrollment.objects.create(tenant=self.tenant, student=student, period=app.intake_period, level_label=level,
                                  section_label=section, reason="Admitted", recorded_by=request.user)
        if app.photo:  # the photo taken at admission becomes the student's photo
            student.photo.save(app.photo.name.rsplit("/", 1)[-1], app.photo.file, save=False)
        student.save(update_fields=["current_level", "current_section", "photo"])
        invoice = self._bill_new_student(request, student, billing)
        app.status = Application.Status.ENROLLED
        app.save(update_fields=["status"])
        log_event("application.enrolled", request=request, target=app,
                  changes={"student_no": student.student_no, "invoice": invoice.number if invoice else None})
        send_notification_email(app, f"Welcome to {self.tenant.name}",
                                f"You are now enrolled. Your student number is {student.student_no}.")
        return Response({"student_id": student.id, "student_no": student.student_no,
                         "invoice": invoice.number if invoice else None,
                         "invoice_total": str(invoice.total) if invoice else None}, status=status.HTTP_201_CREATED)

    def _bill_new_student(self, request, student, billing):
        if billing["mode"] == "plan":
            plan = FeePlan.objects.filter(tenant=self.tenant, pk=billing["plan"], is_active=True).first()
            if plan is None:
                raise BusinessRuleViolation("That fee plan is not available.", code="plan_not_found",
                                            fields={"plan": ["Choose an active fee plan."]})
            lines = [{"description": i.description, "amount": i.amount} for i in plan.items.all()]
            return finance.create_invoice(tenant=self.tenant, student=student, lines=lines, fee_plan=plan,
                                          period=plan.period, due_date=billing.get("due_date"),
                                          user=request.user, request=request)
        if billing["mode"] == "custom":
            return finance.create_invoice(tenant=self.tenant, student=student, lines=billing["items"],
                                          due_date=billing.get("due_date"), notes="Billed at enrolment",
                                          user=request.user, request=request)
        return None

    @action(detail=True, url_path="billing-options")
    def billing_options(self, request, pk=None):
        """Fee plans that fit this applicant (their grade/program, or everyone), for the enrol step."""
        app = self.get_object()
        plans = (FeePlan.objects.filter(tenant=self.tenant, is_active=True).prefetch_related("items")
                 .order_by("-created_at"))
        level = app.requested_level
        return Response({
            "currency": self.tenant.currency,
            "can_bill_custom": request.user.has_perm_code("fees.manage"),
            "plans": [{"id": p.id, "name": p.name, "applies_to": p.applies_to, "period": str(p.period or ""),
                       "total": str(sum(i.amount for i in p.items.all())),
                       "items": [{"description": i.description, "amount": str(i.amount)} for i in p.items.all()],
                       "matches": not p.applies_to or p.applies_to == level} for p in plans],
        })

    # ------------------------------------------------------------------ applicant photo
    @action(detail=True, methods=["get"], parser_classes=[MultiPartParser, FormParser])
    def photo(self, request, pk=None):
        app = self.get_object()
        if not app.photo:
            raise Http404("No photo.")
        ctype = "image/png" if app.photo.name.endswith(".png") else "image/jpeg"
        return FileResponse(app.photo.open("rb"), content_type=ctype)

    @photo.mapping.post
    def upload_photo(self, request, pk=None):
        app = self.get_object()
        f = request.FILES.get("photo")
        kind = sniff_image(f)
        old = app.photo.name if app.photo else None
        app.photo.save(f"photo.{kind}", f, save=False)
        app.save(update_fields=["photo", "updated_at"])
        if old:
            app.photo.storage.delete(old)
        log_event("application.photo_updated", request=request, target=app)
        return Response(ApplicationSerializer(app, context={"request": request}).data)


class EnrollmentViewSet(TenantScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    """Read-only enrollment history plus withdrawal and transfer-out workflows."""

    serializer_class = EnrollmentSerializer
    required_perms = {"list": AUTHENTICATED, "retrieve": AUTHENTICATED, "*": "students.manage"}
    filterset_fields = ["student", "status", "period"]

    def get_queryset(self):
        return Enrollment.objects.filter(student__in=visible_students(self.request.user)).select_related(
            "student__person", "period", "recorded_by")

    def _end_active(self, request, new_status, student_status):
        s = StatusChangeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        enrollment = self.get_object()
        if enrollment.status != Enrollment.Status.ACTIVE:
            raise BusinessRuleViolation("Only an active enrollment can be changed.", code="enrollment_not_active")
        when = s.validated_data.get("effective_date") or timezone.localdate()
        if when < enrollment.start_date:
            raise ValidationError({"effective_date": ["Cannot be before the enrollment started."]})
        reason = s.validated_data["reason"]
        if s.validated_data.get("destination"):
            reason = f"{reason} → {s.validated_data['destination']}"
        enrollment.status, enrollment.end_date, enrollment.reason = new_status, when, reason
        enrollment.save()
        enrollment.student.status = student_status
        enrollment.student.save(update_fields=["status"])
        log_event(f"student.{new_status}", request=request, target=enrollment.student, changes={"reason": reason})
        guardians = [link.guardian.user for link in enrollment.student.guardian_links.select_related("guardian__user")]
        notify(guardians, f"{enrollment.student.person.full_name}: {new_status}", reason, kind="enrollment")
        return Response(EnrollmentSerializer(enrollment).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def withdraw(self, request, pk=None):
        return self._end_active(request, Enrollment.Status.WITHDRAWN, Student.Status.WITHDRAWN)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def transfer(self, request, pk=None):
        return self._end_active(request, Enrollment.Status.TRANSFERRED, Student.Status.TRANSFERRED)
