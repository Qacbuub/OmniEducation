import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admissions.models import AcademicPeriod, Enrollment
from comms.services import notify, save_generated_pdf
from core.audit import log_event
from core.exceptions import BusinessRuleViolation
from core.permissions import AUTHENTICATED, IsTenantUser, IsUniversityTenant, RolePermission
from core.tenancy import TenantScopedViewSetMixin, jsonable
from people.models import Student
from people.scoping import visible_students

from . import services
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
    LectureAttendance,
    OfferingMeeting,
    Program,
    Semester,
    UniversityAssessment,
    UniversityGrade,
)
from .pdf import transcript_pdf
from .serializers import (
    AmendSerializer,
    AssessmentSerializer,
    ClearanceSerializer,
    CourseOfferingSerializer,
    CoursePrerequisiteSerializer,
    CourseSerializer,
    CurriculumCourseSerializer,
    CurriculumSerializer,
    DecisionSerializer,
    DepartmentSerializer,
    FacultySerializer,
    GradeApprovalSerializer,
    GradeSerializer,
    MeetingSerializer,
    ProgramSerializer,
    RegistrationCreateSerializer,
    RegistrationSerializer,
    ScoresSerializer,
    SemesterSerializer,
    StandingSerializer,
    TranscriptEntrySerializer,
)

UNI_PERMS = [IsAuthenticated, IsTenantUser, IsUniversityTenant, RolePermission]


class UniViewSet(TenantScopedViewSetMixin):
    permission_classes = UNI_PERMS


def catalog_perms(code):
    return {"list": AUTHENTICATED, "retrieve": AUTHENTICATED, "*": code}


# --------------------------------------------------------------------------- helpers
def student_from_param(request, value):
    """Resolve a student id (or 'me') the requesting user is allowed to see."""
    if value in (None, "", "me"):
        student = getattr(request.user, "student_profile", None)
        if student is None:
            raise ValidationError({"student": ["Choose a student."]})
        return student
    try:
        pk = int(value)
    except (TypeError, ValueError):
        raise Http404
    student = visible_students(request.user).filter(pk=pk).first()
    if student is None:
        raise Http404
    return student


def registration_scope(user):
    """Registrations a user may see."""
    qs = CourseRegistration.objects.filter(tenant=user.tenant)
    if user.has_perm_code("students.view"):
        return qs
    cond = Q(student__user=user) | Q(offering__lecturer=user) | Q(student__academic_standing__adviser=user)
    return qs.filter(cond)


def can_manage_registration(user, student):
    if student.user_id == user.id:
        return True
    if not user.has_perm_code("uni.registration.approve"):
        return False
    if user.role_code == "adviser":
        return AcademicStanding.objects.filter(student=student, adviser=user).exists()
    return True


def can_view_gradebook(user, offering):
    return (offering.lecturer_id == user.id or services.can_approve(user, offering)
            or user.has_perm_code("uni.offerings.manage"))


def current_semester(tenant):
    return Semester.objects.filter(tenant=tenant, period__is_current=True).select_related("period").first()


# --------------------------------------------------------------------------- catalogue
class FacultyViewSet(UniViewSet, viewsets.ModelViewSet):
    serializer_class = FacultySerializer
    queryset = Faculty.objects.select_related("dean")
    required_perms = catalog_perms("uni.programs.manage")
    search_fields = ["name", "code"]

    def perform_destroy(self, instance):
        if instance.departments.exists():
            raise BusinessRuleViolation("Remove or move this faculty's departments first.", code="in_use")
        super().perform_destroy(instance)


class DepartmentViewSet(UniViewSet, viewsets.ModelViewSet):
    serializer_class = DepartmentSerializer
    queryset = Department.objects.select_related("faculty", "head")
    required_perms = catalog_perms("uni.programs.manage")
    filterset_fields = ["faculty"]
    search_fields = ["name", "code"]

    def perform_destroy(self, instance):
        if instance.programs.exists() or instance.courses.exists():
            raise BusinessRuleViolation("This department still has programs or courses.", code="in_use")
        super().perform_destroy(instance)


class ProgramViewSet(UniViewSet, viewsets.ModelViewSet):
    serializer_class = ProgramSerializer
    queryset = Program.objects.select_related("department__faculty")
    required_perms = catalog_perms("uni.programs.manage")
    filterset_fields = ["department", "department__faculty", "is_active"]
    search_fields = ["name", "code"]

    def perform_destroy(self, instance):
        if instance.students.exists():
            raise BusinessRuleViolation("Students are enrolled in this program; deactivate it instead.",
                                        code="in_use")
        super().perform_destroy(instance)


class CourseViewSet(UniViewSet, viewsets.ModelViewSet):
    serializer_class = CourseSerializer
    queryset = Course.objects.select_related("department").prefetch_related("prerequisite_links__prerequisite")
    required_perms = catalog_perms("uni.programs.manage")
    filterset_fields = ["department", "level", "is_active"]
    search_fields = ["code", "title"]
    ordering_fields = ["code", "title", "level"]

    def perform_destroy(self, instance):
        if instance.offerings.exists():
            raise BusinessRuleViolation("This course has been offered; deactivate it instead.", code="in_use")
        super().perform_destroy(instance)


class PrerequisiteViewSet(UniViewSet, viewsets.ModelViewSet):
    serializer_class = CoursePrerequisiteSerializer
    queryset = (CoursePrerequisite.objects.select_related("course", "prerequisite")
                .order_by("course__code", "prerequisite__code"))
    required_perms = catalog_perms("uni.programs.manage")
    filterset_fields = ["course", "prerequisite"]


class CurriculumViewSet(UniViewSet, viewsets.ModelViewSet):
    serializer_class = CurriculumSerializer
    queryset = Curriculum.objects.select_related("program").prefetch_related("items__course")
    required_perms = catalog_perms("uni.programs.manage")
    filterset_fields = ["program", "is_current"]

    @transaction.atomic
    def perform_create(self, serializer):
        if serializer.validated_data.get("is_current", True):
            Curriculum.objects.filter(program=serializer.validated_data["program"], is_current=True).update(
                is_current=False)
        super().perform_create(serializer)

    @transaction.atomic
    def perform_update(self, serializer):
        if serializer.validated_data.get("is_current"):
            Curriculum.objects.filter(program=serializer.instance.program, is_current=True).exclude(
                pk=serializer.instance.pk).update(is_current=False)
        super().perform_update(serializer)


class CurriculumCourseViewSet(UniViewSet, viewsets.ModelViewSet):
    serializer_class = CurriculumCourseSerializer
    queryset = CurriculumCourse.objects.select_related("course", "curriculum")
    required_perms = catalog_perms("uni.programs.manage")
    filterset_fields = ["curriculum", "category"]


# --------------------------------------------------------------------------- semesters and sections
class SemesterViewSet(UniViewSet, viewsets.ModelViewSet):
    serializer_class = SemesterSerializer
    queryset = Semester.objects.select_related("period")
    required_perms = {**catalog_perms("uni.offerings.manage"), "current": AUTHENTICATED}

    def perform_create(self, serializer):
        period = serializer.validated_data["period"]
        if Semester.objects.filter(period=period).exists():
            raise ValidationError({"period": ["Registration settings already exist for this semester."]})
        super().perform_create(serializer)

    @action(detail=False)
    def current(self, request):
        sem = current_semester(request.user.tenant)
        if sem is None:
            raise Http404
        return Response(SemesterSerializer(sem).data)


class OfferingViewSet(UniViewSet, viewsets.ModelViewSet):
    serializer_class = CourseOfferingSerializer
    queryset = CourseOffering.objects.select_related("course__department", "semester__period", "lecturer") \
        .prefetch_related("meetings")
    required_perms = {**catalog_perms("uni.offerings.manage"), "mine": AUTHENTICATED, "roster": AUTHENTICATED,
                      "gradebook": AUTHENTICATED, "scores": "uni.grades.submit", "submit_grades": "uni.grades.submit",
                      "approve_grades": "uni.grades.approve", "return_grades": "uni.grades.approve",
                      "history": AUTHENTICATED, "attendance": AUTHENTICATED}
    filterset_fields = ["semester", "course", "lecturer", "status", "course__department"]
    search_fields = ["course__code", "course__title"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("current") == "1":
            qs = qs.filter(semester__period__is_current=True)
        return qs

    def _save(self, serializer, create):
        meetings = serializer.validated_data.pop("meetings", None)
        with transaction.atomic():
            if create:
                obj = serializer.save(tenant=self.tenant)
            else:
                obj = serializer.save()
            if meetings is not None or not create:
                data = meetings if meetings is not None else [
                    {"day": m.day, "start_time": m.start_time, "end_time": m.end_time, "room": m.room}
                    for m in obj.meetings.all()]
                services.check_offering_schedule(obj, data, exclude_offering_id=obj.pk)
                if meetings is not None:
                    obj.meetings.all().delete()
                    OfferingMeeting.objects.bulk_create(
                        [OfferingMeeting(tenant=self.tenant, offering=obj, **m) for m in meetings])
        log_event(f"offering.{'created' if create else 'updated'}", request=self.request, target=obj,
                  changes={"lecturer": obj.lecturer_id, "capacity": obj.capacity,
                           "meetings": len(meetings) if meetings is not None else None})
        return obj

    def perform_create(self, serializer):
        self._save(serializer, create=True)

    def perform_update(self, serializer):
        self._save(serializer, create=False)

    def perform_destroy(self, instance):
        if instance.registrations.exists():
            raise BusinessRuleViolation("Students have registered; cancel the section instead.", code="in_use")
        super().perform_destroy(instance)

    @action(detail=False)
    def mine(self, request):
        """Sections taught by the signed-in lecturer."""
        qs = self.get_queryset().filter(lecturer=request.user)
        return Response(self.get_serializer(qs, many=True).data)

    def _gradebook_offering(self, request):
        offering = self.get_object()
        if not can_view_gradebook(request.user, offering):
            raise PermissionDenied("You don't teach or moderate this section.")
        return offering

    @action(detail=True)
    def roster(self, request, pk=None):
        offering = self._gradebook_offering(request)
        regs = offering.registrations.filter(status__in=CourseRegistration.ACTIVE).select_related(
            "student__person", "offering__course", "offering__semester__period", "offering__lecturer")
        return Response(RegistrationSerializer(regs, many=True, context={"request": request}).data)

    @action(detail=True)
    def gradebook(self, request, pk=None):
        offering = self._gradebook_offering(request)
        assessments = list(offering.assessments.all())
        regs = (offering.registrations.filter(status="approved").select_related("student__person")
                .prefetch_related("scores"))
        grades = {g.registration_id: g for g in UniversityGrade.objects.filter(registration__offering=offering)}
        rows = []
        for r in regs:
            scores = {s.assessment_id: s.score for s in r.scores.all()}
            total = services.compute_total(r, assessments)
            g = grades.get(r.id)
            letter = g.letter if g else (services.grade_band(offering.tenant, total)[0] if total is not None else None)
            rows.append({"registration": r.id, "student_id": r.student_id, "student_no": r.student.student_no,
                         "name": r.student.person.full_name, "scores": {str(k): v for k, v in scores.items()},
                         "total": g.total_score if g else total, "letter": letter,
                         "grade_status": g.status if g else "not_started", "grade_id": g.id if g else None})
        weight = sum(a.weight for a in assessments)
        return Response({
            "offering": CourseOfferingSerializer(offering, context={"request": request}).data,
            "assessments": AssessmentSerializer(assessments, many=True).data,
            "weight_total": weight, "state": services.offering_grade_state(offering),
            "can_edit": offering.lecturer_id == request.user.id
                        and services.offering_grade_state(offering) not in ("submitted", "approved"),
            "can_approve": services.can_approve(request.user, offering) and offering.lecturer_id != request.user.id,
            "rows": rows,
            "history": GradeApprovalSerializer(offering.grade_approvals.select_related("actor")[:20], many=True).data,
        })

    @action(detail=True, methods=["get", "post"])
    def attendance(self, request, pk=None):
        """Class attendance for one day: GET ?date= gives the roster with that day's marks and each student's
        rate so far; POST {date, records: [{registration, status, note}]} saves it (assigned lecturer or registrar)."""
        offering = self._gradebook_offering(request)
        can_edit = offering.lecturer_id == request.user.id or request.user.has_perm_code("uni.offerings.manage")
        raw = request.data.get("date") if request.method == "POST" else request.query_params.get("date")
        try:
            day = datetime.date.fromisoformat(raw) if raw else timezone.localdate()
        except ValueError:
            raise ValidationError({"date": ["Use the format YYYY-MM-DD."]})
        regs = list(offering.registrations.filter(status="approved").select_related("student__person")
                    .order_by("student__person__last_name", "student__person__first_name"))
        if request.method == "POST":
            if not can_edit:
                raise PermissionDenied("Only the section's lecturer or the registrar can record attendance.")
            period = offering.semester.period
            if day > timezone.localdate():
                raise ValidationError({"date": ["Attendance can't be recorded for a future date."]})
            if not (period.start_date <= day <= period.end_date):
                raise ValidationError({"date": [f"Pick a date inside {period.name} "
                                                f"({period.start_date} to {period.end_date})."]})
            records = request.data.get("records")
            if not isinstance(records, list) or not records:
                raise ValidationError({"records": ["Send at least one student."]})
            by_id = {r.id: r for r in regs}
            valid = set(LectureAttendance.Status.values)
            saved = absent = 0
            with transaction.atomic():
                for item in records:
                    reg = by_id.get(int(item.get("registration") or 0))
                    st = item.get("status")
                    if reg is None:
                        raise ValidationError({"records": ["A student is not registered in this section."]})
                    if st not in valid:
                        raise ValidationError({"records": [f"Unknown status '{st}'."]})
                    LectureAttendance.objects.update_or_create(
                        tenant=offering.tenant, registration=reg, date=day,
                        defaults={"offering": offering, "status": st, "note": str(item.get("note", ""))[:200],
                                  "recorded_by": request.user})
                    saved += 1
                    if st == LectureAttendance.Status.ABSENT and reg.student.user_id:
                        absent += 1
                        notify([reg.student.user], f"Absent from {offering.course.code}",
                               f"You were marked absent from {offering.course.code} {offering.course.title} on {day}.",
                               kind="attendance", link="/university/my-courses")
            log_event("lecture_attendance.recorded", request=request, target=offering,
                      changes={"date": str(day), "saved": saved})
        marks = {a.registration_id: a for a in LectureAttendance.objects.filter(offering=offering, date=day)}
        totals = {}
        for row in (LectureAttendance.objects.filter(offering=offering).values("registration_id", "status")
                    .annotate(n=Count("id"))):
            totals.setdefault(row["registration_id"], {})[row["status"]] = row["n"]
        rows = []
        for r in regs:
            t = totals.get(r.id, {})
            held = sum(t.values())
            counted = held - t.get("excused", 0)  # excused absences don't lower the rate
            attended = t.get("present", 0) + t.get("late", 0)
            a = marks.get(r.id)
            rows.append({"registration": r.id, "student_no": r.student.student_no, "name": r.student.person.full_name,
                         "status": a.status if a else None, "note": a.note if a else "",
                         "absences": t.get("absent", 0), "sessions": held,
                         "rate": round(attended * 100 / counted) if counted else None})
        dates = list(LectureAttendance.objects.filter(offering=offering).values_list("date", flat=True)
                     .distinct().order_by("-date")[:12])
        return Response({"date": day, "can_edit": can_edit, "recorded": bool(marks), "rows": rows,
                         "recent_dates": dates,
                         "meeting_days": sorted({m.day for m in offering.meetings.all()})})

    @action(detail=True, methods=["post"])
    def scores(self, request, pk=None):
        offering = self.get_object()
        s = ScoresSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        n = services.save_scores(offering, s.validated_data["scores"], user=request.user)
        log_event("scores.recorded", request=request, target=offering, changes={"rows": n})
        return Response({"saved": n})

    @action(detail=True, methods=["post"], url_path="submit-grades")
    def submit_grades(self, request, pk=None):
        offering = self.get_object()
        regs = services.submit_grades(offering, user=request.user, request=request)
        return Response({"submitted": len(regs), "state": services.offering_grade_state(offering)})

    @action(detail=True, methods=["post"], url_path="approve-grades")
    def approve_grades(self, request, pk=None):
        s = DecisionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        grades = services.moderate_grades(self.get_object(), user=request.user, approve=True,
                                          notes=s.validated_data.get("notes", ""), request=request)
        return Response({"approved": len(grades)})

    @action(detail=True, methods=["post"], url_path="return-grades")
    def return_grades(self, request, pk=None):
        s = DecisionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        grades = services.moderate_grades(self.get_object(), user=request.user, approve=False,
                                          notes=s.validated_data.get("notes", ""), request=request)
        return Response({"returned": len(grades)})


# --------------------------------------------------------------------------- registration
class RegistrationViewSet(UniViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = RegistrationSerializer
    required_perms = {"list": AUTHENTICATED, "retrieve": AUTHENTICATED, "create": AUTHENTICATED,
                      "drop": AUTHENTICATED, "approve": "uni.registration.approve",
                      "reject": "uni.registration.approve", "summary": AUTHENTICATED, "coursework": AUTHENTICATED}
    filterset_fields = ["student", "offering", "status", "offering__semester"]
    search_fields = ["student__person__first_name", "student__person__last_name", "student__student_no",
                     "offering__course__code"]

    def get_queryset(self):
        qs = registration_scope(self.request.user).select_related(
            "student__person", "offering__course", "offering__semester__period", "offering__lecturer", "grade")
        if self.request.query_params.get("current") == "1":
            qs = qs.filter(offering__semester__period__is_current=True)
        return qs

    def create(self, request, *args, **kwargs):
        s = RegistrationCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        student = student_from_param(request, s.validated_data.get("student"))
        if not can_manage_registration(request.user, student):
            raise PermissionDenied("You can't register courses for this student.")
        offering = CourseOffering.objects.filter(tenant=request.user.tenant,
                                                 pk=s.validated_data["offering"]).first()
        if offering is None:
            raise ValidationError({"offering": ["Section not found."]})
        reg = services.register(student, offering, user=request.user, request=request)
        return Response(RegistrationSerializer(reg, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)

    def _decide(self, request, approve):
        reg = self.get_object()
        if not can_manage_registration(request.user, reg.student) or reg.student.user_id == request.user.id:
            raise PermissionDenied("You can only decide registrations for your own advisees.")
        s = DecisionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        reg = services.decide_registration(reg, approve=approve, user=request.user,
                                           notes=s.validated_data.get("notes", ""), request=request)
        return Response(RegistrationSerializer(reg, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._decide(request, True)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._decide(request, False)

    @action(detail=True, methods=["post"])
    def drop(self, request, pk=None):
        reg = self.get_object()
        if not can_manage_registration(request.user, reg.student):
            raise PermissionDenied("You can't drop courses for this student.")
        s = DecisionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        reg = services.drop_registration(reg, user=request.user, reason=s.validated_data.get("notes", ""),
                                         request=request)
        return Response(RegistrationSerializer(reg, context={"request": request}).data)

    @action(detail=False)
    def summary(self, request):
        """Credit load and limits for one student in the current (or given) semester."""
        student = student_from_param(request, request.query_params.get("student"))
        sem_id = request.query_params.get("semester")
        sem = (Semester.objects.filter(tenant=request.user.tenant, pk=sem_id).first() if sem_id
               else current_semester(request.user.tenant))
        if sem is None:
            raise Http404
        regs = services._active_regs(student, sem)
        load = sum(r.offering.course.credit_hours for r in regs)
        today = timezone.localdate()
        standing = getattr(student, "academic_standing", None)
        return Response({
            "student_id": student.id, "semester": SemesterSerializer(sem).data,
            "credits": load, "min_credits": services.policy(student.tenant, "min_credits"),
            "max_credits": services.credit_limit(student), "below_minimum":
                load < int(services.policy(student.tenant, "min_credits")),
            "window_open": sem.window_open(today), "add_drop_open": today <= sem.add_drop_end,
            "standing": standing.standing if standing else None,
            "cgpa": standing.cgpa if standing else None,
            "pending": sum(1 for r in regs if r.status == "pending"),
        })


    @action(detail=False)
    def coursework(self, request):
        """A student's courses this semester with each assessment, the score so far and the running total.

        Letter grades appear only once they are approved; until then the student sees their marks.
        """
        student = student_from_param(request, request.query_params.get("student"))
        sem_id = request.query_params.get("semester")
        sem = (Semester.objects.filter(tenant=request.user.tenant, pk=sem_id).first() if sem_id
               else current_semester(request.user.tenant))
        if sem is None:
            raise Http404
        regs = (CourseRegistration.objects.filter(student=student, offering__semester=sem, status__in=["approved", "pending"])
                .select_related("offering__course", "offering__lecturer", "grade").prefetch_related("scores",
                                                                                                   "offering__assessments", "attendance"))
        courses = []
        for r in regs:
            assessments = list(r.offering.assessments.all())
            scores = {sc.assessment_id: sc.score for sc in r.scores.all()}
            earned = sum((Decimal(scores[a.id]) / Decimal(a.max_score) * Decimal(a.weight)
                          for a in assessments if a.id in scores), Decimal(0))
            marked = sum((Decimal(a.weight) for a in assessments if a.id in scores), Decimal(0))
            grade = getattr(r, "grade", None)
            approved = grade is not None and grade.status == "approved"
            seen = {}
            for a in r.attendance.all():
                seen[a.status] = seen.get(a.status, 0) + 1
            held = sum(seen.values())
            counted = held - seen.get("excused", 0)
            courses.append({
                "attendance": {"sessions": held, "absences": seen.get("absent", 0), "late": seen.get("late", 0),
                               "excused": seen.get("excused", 0),
                               "rate": round((seen.get("present", 0) + seen.get("late", 0)) * 100 / counted)
                               if counted else None},
                "registration": r.id, "status": r.status, "course_code": r.offering.course.code,
                "course_title": r.offering.course.title, "credit_hours": r.offering.course.credit_hours,
                "section": r.offering.section,
                "lecturer": r.offering.lecturer.get_full_name() if r.offering.lecturer else None,
                "assessments": [{"id": a.id, "name": a.name, "kind": a.kind, "weight": a.weight, "max_score": a.max_score,
                                 "due_date": a.due_date, "score": scores.get(a.id)} for a in assessments],
                "weight_total": sum((Decimal(a.weight) for a in assessments), Decimal(0)),
                "weight_marked": services.q2(marked), "earned": services.q2(earned),
                "percent_so_far": services.q2(earned / marked * 100) if marked else None,
                "grade_status": grade.status if grade else "in_progress",
                "letter": grade.letter if approved else None,
                "grade_points": grade.grade_points if approved else None,
            })
        return Response({"student_id": student.id, "student_name": student.person.full_name,
                         "semester": SemesterSerializer(sem).data, "courses": courses})


# --------------------------------------------------------------------------- assessments and grades
class AssessmentViewSet(UniViewSet, viewsets.ModelViewSet):
    serializer_class = AssessmentSerializer
    queryset = UniversityAssessment.objects.select_related("offering")
    required_perms = {"list": AUTHENTICATED, "retrieve": AUTHENTICATED, "*": "uni.grades.submit"}
    filterset_fields = ["offering"]

    def get_queryset(self):
        u = self.request.user
        qs = super().get_queryset()
        if u.has_perm_code("uni.grades.approve", "uni.offerings.manage"):
            return qs
        return qs.filter(Q(offering__lecturer=u) | Q(offering__registrations__student__user=u,
                                                     offering__registrations__status="approved")).distinct()

    def _check(self, offering):
        if offering.lecturer_id != self.request.user.id:
            raise PermissionDenied("Only the assigned lecturer can change assessments for this section.")
        services.ensure_scores_editable(offering)

    def perform_create(self, serializer):
        self._check(serializer.validated_data["offering"])
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._check(serializer.instance.offering)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._check(instance.offering)
        super().perform_destroy(instance)


class GradeViewSet(UniViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = GradeSerializer
    required_perms = {"list": AUTHENTICATED, "retrieve": AUTHENTICATED, "amend": AUTHENTICATED}
    filterset_fields = ["status", "registration__offering", "registration__student"]

    def get_queryset(self):
        qs = UniversityGrade.objects.filter(registration__in=registration_scope(self.request.user)).select_related(
            "registration__student__person", "registration__offering__course")
        if self.request.user.role_code == "student":
            qs = qs.filter(status="approved")
        return qs

    @action(detail=True, methods=["post"])
    def amend(self, request, pk=None):
        grade = self.get_object()
        s = AmendSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        grade = services.amend_grade(grade, user=request.user, total_score=s.validated_data["total_score"],
                                     reason=s.validated_data["reason"], request=request)
        return Response(GradeSerializer(grade).data)


class GradeApprovalQueueView(APIView):
    """Sections whose grades are waiting for the signed-in user's approval, plus recent decisions."""

    permission_classes = UNI_PERMS
    required_perms = {"get": "uni.grades.approve"}

    def get(self, request):
        tenant = request.user.tenant
        submitted = (CourseOffering.objects.filter(tenant=tenant, registrations__grade__status="submitted")
                     .distinct().select_related("course__department__faculty", "semester__period", "lecturer")
                     .prefetch_related("meetings"))
        pending = [o for o in submitted if services.can_approve(request.user, o) and o.lecturer_id != request.user.id]
        history = GradeApproval.objects.filter(tenant=tenant).select_related("offering__course", "actor")[:30]
        return Response({
            "pending": CourseOfferingSerializer(pending, many=True, context={"request": request}).data,
            "history": GradeApprovalSerializer(history, many=True).data,
        })


# --------------------------------------------------------------------------- student records
def _require_record_access(request, student):
    u = request.user
    allowed = (student.user_id == u.id or u.has_perm_code("students.view")
               or AcademicStanding.objects.filter(student=student, adviser=u).exists())
    if not allowed:
        raise PermissionDenied("You can't view this student's academic record.")


class TranscriptView(APIView):
    permission_classes = UNI_PERMS

    def get(self, request, student_id):
        student = student_from_param(request, student_id)
        _require_record_access(request, student)
        s = services.academic_summary(student)
        standing = getattr(student, "academic_standing", None)
        return Response({
            "student": {"id": student.id, "student_no": student.student_no, "name": student.person.full_name,
                        "program": standing.program.name if standing else student.current_level,
                        "year_of_study": standing.year_of_study if standing else None,
                        "status": student.status, "standing": standing.standing if standing else None},
            "cgpa": s["cgpa"], "credits_attempted": s["credits_attempted"], "credits_earned": s["credits_earned"],
            "repeat_policy": services.policy(student.tenant, "repeat_policy"),
            "semesters": [{
                "semester_id": sem["semester_id"], "semester": sem["semester"], "credits": sem["credits"],
                "gpa": sem["gpa"], "cgpa_to_date": sem["cgpa_to_date"],
                "entries": [{**TranscriptEntrySerializer(e).data, "counts": e.id in s["counted_ids"]}
                            for e in sem["entries"]],
            } for sem in s["semesters"]],
        })


class TranscriptPdfView(APIView):
    permission_classes = UNI_PERMS

    def get(self, request, student_id):
        student = student_from_param(request, student_id)
        _require_record_access(request, student)
        official = request.user.has_perm_code("uni.transcripts.issue")
        pdf = transcript_pdf(student, services.academic_summary(student), official=official)
        kind_title = "Official transcript" if official else "Unofficial transcript"
        save_generated_pdf(tenant=request.user.tenant, kind="transcript",
                           title=f"{kind_title} – {student.person.full_name}", pdf_bytes=pdf, student=student,
                           user=request.user)
        log_event("document.generated.transcript", request=request, target=student, changes={"official": official})
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{student.student_no}-transcript.pdf"'
        return response


class DegreeAuditView(APIView):
    permission_classes = UNI_PERMS

    def get(self, request, student_id):
        student = student_from_param(request, student_id)
        _require_record_access(request, student)
        return Response(services.degree_audit(student))


class TimetableView(APIView):
    """Weekly timetable: a student's registered sections, or the sections a lecturer teaches."""

    permission_classes = UNI_PERMS

    def get(self, request):
        tenant = request.user.tenant
        sem_id = request.query_params.get("semester")
        sem = Semester.objects.filter(tenant=tenant, pk=sem_id).first() if sem_id else current_semester(tenant)
        if sem is None:
            return Response({"semester": None, "meetings": []})
        if request.query_params.get("student") or request.user.role_code == "student":
            student = student_from_param(request, request.query_params.get("student"))
            _require_record_access(request, student)
            offerings = CourseOffering.objects.filter(semester=sem, registrations__student=student,
                                                      registrations__status__in=CourseRegistration.ACTIVE)
            owner = student.person.full_name
        else:
            offerings = CourseOffering.objects.filter(semester=sem, lecturer=request.user)
            owner = request.user.get_full_name()
        meetings = (OfferingMeeting.objects.filter(offering__in=offerings).select_related(
            "offering__course", "offering__lecturer").order_by("day", "start_time"))
        return Response({
            "semester": SemesterSerializer(sem).data, "owner": owner,
            "meetings": [{**MeetingSerializer(m).data, "offering": m.offering_id,
                          "course_code": m.offering.course.code, "course_title": m.offering.course.title,
                          "section": m.offering.section,
                          "lecturer": m.offering.lecturer.get_full_name() if m.offering.lecturer else None}
                         for m in meetings],
        })


class StandingViewSet(UniViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                      viewsets.GenericViewSet):
    serializer_class = StandingSerializer
    required_perms = {"list": AUTHENTICATED, "retrieve": AUTHENTICATED, "update": "students.manage",
                      "partial_update": "students.manage"}
    filterset_fields = ["student", "program", "standing", "adviser", "year_of_study"]
    search_fields = ["student__person__first_name", "student__person__last_name", "student__student_no"]
    audit_name = "academic_standing"

    def get_queryset(self):
        u = self.request.user
        qs = AcademicStanding.objects.filter(tenant=u.tenant).select_related("student__person", "program", "adviser")
        if u.has_perm_code("students.view"):
            return qs
        return qs.filter(Q(student__user=u) | Q(adviser=u))


class ClearanceViewSet(UniViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                       viewsets.GenericViewSet):
    serializer_class = ClearanceSerializer
    required_perms = {"list": AUTHENTICATED, "retrieve": AUTHENTICATED, "create": AUTHENTICATED,
                      "clear": "uni.clearance.manage", "reject": "uni.clearance.manage"}
    filterset_fields = ["status", "student"]

    def get_queryset(self):
        u = self.request.user
        qs = GraduationClearance.objects.filter(tenant=u.tenant).select_related("student__person", "decided_by")
        if u.has_perm_code("uni.clearance.manage", "students.view"):
            return qs
        return qs.filter(Q(student__user=u) | Q(student__academic_standing__adviser=u))

    def create(self, request, *args, **kwargs):
        student = student_from_param(request, request.data.get("student"))
        if student.user_id != request.user.id and not request.user.has_perm_code("uni.clearance.manage"):
            raise PermissionDenied("You can't request clearance for this student.")
        if GraduationClearance.objects.filter(student=student, status="pending").exists():
            raise BusinessRuleViolation("A clearance request is already pending.", code="duplicate_clearance")
        if student.status == Student.Status.GRADUATED:
            raise BusinessRuleViolation("This student has already graduated.", code="already_graduated")
        audit = services.degree_audit(student)
        if not audit["eligible"]:
            unmet = [c["label"] for c in audit["checks"] if not c["met"]]
            raise BusinessRuleViolation(f"Not yet eligible to graduate: {'; '.join(unmet)}.",
                                        code="not_eligible", fields={"unmet": unmet})
        c = GraduationClearance.objects.create(
            tenant=request.user.tenant, student=student, requested_by=request.user,
            audit_snapshot=jsonable({k: audit[k] for k in ("cgpa", "credits_earned", "credits_required", "checks")}),
            finance_balance=services.outstanding_balance(student))
        log_event("clearance.requested", request=request, target=student)
        return Response(ClearanceSerializer(c).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def clear(self, request, pk=None):
        c = self.get_object()
        if c.status != "pending":
            raise BusinessRuleViolation("Only pending requests can be decided.", code="not_pending")
        student = c.student
        audit = services.degree_audit(student)
        if not audit["eligible"]:
            raise BusinessRuleViolation("The student no longer meets the graduation requirements.",
                                        code="not_eligible")
        balance = services.outstanding_balance(student)
        if balance > 0:
            raise BusinessRuleViolation(f"Finance hold: {balance} is still outstanding.", code="fees_outstanding",
                                        fields={"balance": [str(balance)]})
        c.status, c.decided_by, c.decided_at = "cleared", request.user, timezone.now()
        c.notes = request.data.get("notes", "")[:500]
        c.finance_balance = balance
        c.save()
        today = timezone.localdate()
        Enrollment.objects.filter(student=student, status="active").update(status="graduated", end_date=today,
                                                                           reason="Graduated")
        student.status = Student.Status.GRADUATED
        student.save(update_fields=["status"])
        log_event("clearance.cleared", request=request, target=student, changes={"cgpa": str(audit["cgpa"])})
        if student.user_id:
            from comms.services import notify
            notify([student.user], "Graduation clearance approved", "Congratulations, you are cleared to graduate.",
                   kind="general")
        return Response(ClearanceSerializer(c).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        c = self.get_object()
        if c.status != "pending":
            raise BusinessRuleViolation("Only pending requests can be decided.", code="not_pending")
        notes = (request.data.get("notes") or "").strip()
        if not notes:
            raise ValidationError({"notes": ["Give a reason."]})
        c.status, c.decided_by, c.decided_at, c.notes = "rejected", request.user, timezone.now(), notes[:500]
        c.save()
        log_event("clearance.rejected", request=request, target=c.student, changes={"notes": notes})
        return Response(ClearanceSerializer(c).data)


class CatalogStatsView(APIView):
    """Counts for the programs & courses screen."""

    permission_classes = UNI_PERMS

    def get(self, request):
        t = request.user.tenant
        return Response({
            "faculties": Faculty.objects.filter(tenant=t).count(),
            "departments": Department.objects.filter(tenant=t).count(),
            "programs": Program.objects.filter(tenant=t, is_active=True).count(),
            "courses": Course.objects.filter(tenant=t, is_active=True).count(),
            "semesters": list(Semester.objects.filter(tenant=t).select_related("period")
                              .annotate(n=Count("offerings")).values("id", "period__name", "n")),
            "current_period": AcademicPeriod.objects.filter(tenant=t, kind="semester", is_current=True)
            .values_list("name", flat=True).first(),
        })
