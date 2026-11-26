from datetime import date

from django.db.models import F, Q
from django.http import Http404, HttpResponse
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admissions.models import AcademicPeriod
from comms.services import save_generated_pdf
from core.audit import log_event
from core.exceptions import BusinessRuleViolation
from core.permissions import AUTHENTICATED, IsSchoolTenant, IsTenantUser, RolePermission
from core.tenancy import TenantScopedViewSetMixin
from finance.models import Invoice
from people.models import Student
from people.scoping import visible_students

from . import services
from .models import (
    ClassAssignment,
    ClassPlacement,
    ClassSection,
    GradeLevel,
    PromotionDecision,
    PupilAttendance,
    SchoolAssessment,
    SchoolTimetable,
    Subject,
    TermResult,
)
from .pdf import report_card_pdf
from .serializers import (
    AssessmentSerializer,
    AssignmentSerializer,
    AttendanceRegisterSerializer,
    AttendanceSerializer,
    DecideSerializer,
    GradeLevelSerializer,
    LessonSerializer,
    MarkSerializer,
    MarksSerializer,
    PlacementSerializer,
    PlaceSerializer,
    PromotionSerializer,
    SectionSerializer,
    SectionTermSerializer,
    SubjectSerializer,
    TermResultSerializer,
)

SCHOOL_PERMS = [IsAuthenticated, IsTenantUser, IsSchoolTenant, RolePermission]


class SchoolViewSet(TenantScopedViewSetMixin):
    permission_classes = SCHOOL_PERMS


def manage_perms(code="school.classes.manage", **extra):
    return {"list": AUTHENTICATED, "retrieve": AUTHENTICATED, "*": code, **extra}


def can_see_class(user, section):
    return (user.has_perm_code("students.view", "school.classes.manage")
            or section.homeroom_teacher_id == user.id or services.teaches(user, section))


def get_section(request, pk):
    section = ClassSection.objects.filter(tenant=request.user.tenant, pk=pk).select_related(
        "grade_level", "academic_year", "homeroom_teacher").first()
    if section is None:
        raise ValidationError({"section": ["Class not found."]})
    return section


def get_term(request, pk):
    term = AcademicPeriod.objects.filter(tenant=request.user.tenant, pk=pk, kind="term").first()
    if term is None:
        raise ValidationError({"term": ["Term not found."]})
    return term


def parse_date(value, field="date"):
    try:
        return date.fromisoformat(value) if value else timezone.localdate()
    except ValueError:
        raise ValidationError({field: ["Use YYYY-MM-DD."]})


# --------------------------------------------------------------------------- structure
class GradeLevelViewSet(SchoolViewSet, viewsets.ModelViewSet):
    serializer_class = GradeLevelSerializer
    queryset = GradeLevel.objects.all()
    required_perms = manage_perms()

    def perform_destroy(self, instance):
        if instance.sections.exists():
            raise BusinessRuleViolation("Classes exist for this grade level.", code="in_use")
        super().perform_destroy(instance)


class SubjectViewSet(SchoolViewSet, viewsets.ModelViewSet):
    serializer_class = SubjectSerializer
    queryset = Subject.objects.all()
    required_perms = manage_perms()
    search_fields = ["name", "code"]

    def perform_destroy(self, instance):
        if instance.assignments.exists():
            raise BusinessRuleViolation("This subject is allocated to classes.", code="in_use")
        super().perform_destroy(instance)


class SectionViewSet(SchoolViewSet, viewsets.ModelViewSet):
    """Class sections (e.g. Grade 4A) with roster, placement, timetable and results views."""

    serializer_class = SectionSerializer
    queryset = ClassSection.objects.select_related("grade_level", "academic_year", "homeroom_teacher") \
        .prefetch_related("assignments__subject", "assignments__teacher")
    required_perms = manage_perms(mine=AUTHENTICATED, roster=AUTHENTICATED, timetable=AUTHENTICATED,
                                  results_preview=AUTHENTICATED, place="school.classes.manage")
    filterset_fields = ["grade_level", "academic_year", "homeroom_teacher"]
    audit_name = "class_section"

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("current") == "1":
            qs = qs.filter(academic_year__is_current=True)
        return qs

    def perform_destroy(self, instance):
        if instance.placements.exists():
            raise BusinessRuleViolation("Pupils have been placed in this class.", code="in_use")
        super().perform_destroy(instance)

    def _visible(self):
        section = self.get_object()
        if not can_see_class(self.request.user, section):
            raise PermissionDenied("You don't teach this class.")
        return section

    @action(detail=False)
    def mine(self, request):
        """Classes the signed-in teacher is homeroom teacher of or teaches a subject in (current year)."""
        qs = self.get_queryset().filter(academic_year__is_current=True).filter(
            Q(homeroom_teacher=request.user) | Q(assignments__teacher=request.user)).distinct()
        data = self.get_serializer(qs, many=True).data
        for row in data:
            row["is_homeroom"] = row["homeroom_teacher"] == request.user.id
            row["my_subjects"] = [a for a in row["assignments"] if a["teacher"] == request.user.id]
        return Response(data)

    @action(detail=True)
    def roster(self, request, pk=None):
        section = self._visible()
        pupils = services.pupils_in(section).prefetch_related("guardian_links__guardian__person")
        today = timezone.localdate()
        marks = {a.student_id: a.status for a in PupilAttendance.objects.filter(section=section, date=today,
                                                                                lesson__isnull=True)}
        term = services.term_for_date(section, today)
        out = []
        for p in pupils:
            g = next(iter(sorted(p.guardian_links.all(), key=lambda link: not link.is_primary)), None)
            att = services.attendance_summary(p, term.start_date if term else None, today)
            out.append({"id": p.id, "student_no": p.student_no, "first_name": p.person.first_name,
                        "last_name": p.person.last_name, "gender": p.person.gender,
                        "guardian": g.guardian.person.full_name if g else None,
                        "guardian_phone": g.guardian.person.phone if g else None,
                        "today": marks.get(p.id), "term_attendance_rate": att["attendance_rate"],
                        "term_absences": att["absent"]})
        return Response({"section": SectionSerializer(section, context={"request": request}).data, "pupils": out})

    @action(detail=True, methods=["post"])
    def place(self, request, pk=None):
        section = self.get_object()
        s = PlaceSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        student = Student.objects.filter(tenant=request.user.tenant, pk=s.validated_data["student"]).first()
        if student is None:
            raise ValidationError({"student": ["Pupil not found."]})
        placement = services.place_student(student, section, user=request.user, request=request)
        return Response(PlacementSerializer(placement).data, status=status.HTTP_201_CREATED)

    @action(detail=True)
    def timetable(self, request, pk=None):
        section = self.get_object()
        if not (can_see_class(request.user, section) or visible_students(request.user).filter(
                class_placements__section=section, class_placements__status="active").exists()):
            raise PermissionDenied("You can't view this class's timetable.")
        return Response(LessonSerializer(services.lessons_for(section), many=True).data)

    @action(detail=True, url_path="results-preview")
    def results_preview(self, request, pk=None):
        """Live weighted averages for a term, before finalization, plus what is still missing."""
        section = self._visible()
        term = get_term(request, request.query_params.get("term")) if request.query_params.get("term") \
            else services.current_term(request.user.tenant)
        if term is None:
            raise ValidationError({"term": ["Choose a term."]})
        results, missing = services.compute_results(section, term)
        final = TermResult.objects.filter(section=section, term=term)
        return Response({
            "term": {"id": term.id, "name": term.name}, "state": (
                "published" if final.filter(status="published").exists() else
                "finalized" if final.exists() else "open"),
            "missing": missing[:100], "missing_count": len(missing),
            "rows": [{"student": r["student"].id, "name": r["student"].person.full_name,
                      "student_no": r["student"].student_no, "subjects": r["subjects"], "average": r["average"],
                      "grade": r["grade"], "position": r.get("position")} for r in results],
        })


class AssignmentViewSet(SchoolViewSet, viewsets.ModelViewSet):
    serializer_class = AssignmentSerializer
    queryset = ClassAssignment.objects.select_related("section__grade_level", "subject", "teacher")
    required_perms = manage_perms()
    filterset_fields = ["section", "subject", "teacher"]
    audit_name = "subject_allocation"

    def perform_update(self, serializer):
        old_teacher = serializer.instance.teacher_id
        super().perform_update(serializer)
        a = serializer.instance
        if a.teacher_id != old_teacher and a.teacher_id:
            for lesson in a.lessons.all():  # the new teacher must be free for every lesson of the allocation
                services.check_timetable(a, lesson.day, lesson.start_time, lesson.end_time, exclude_id=lesson.id)


class PlacementViewSet(SchoolViewSet, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = PlacementSerializer
    required_perms = {"list": AUTHENTICATED}
    filterset_fields = ["student", "section", "status"]

    def get_queryset(self):
        return ClassPlacement.objects.filter(student__in=visible_students(self.request.user)).select_related(
            "student__person", "section__grade_level", "section__academic_year")


class TimetableViewSet(SchoolViewSet, viewsets.ModelViewSet):
    serializer_class = LessonSerializer
    queryset = SchoolTimetable.objects.select_related("assignment__subject", "assignment__teacher",
                                                      "assignment__section__grade_level")
    required_perms = manage_perms(mine=AUTHENTICATED)
    filterset_fields = ["assignment__section", "assignment__teacher", "day"]
    audit_name = "lesson"

    def perform_create(self, serializer):
        d = serializer.validated_data
        services.check_timetable(d["assignment"], d["day"], d["start_time"], d["end_time"], d.get("room", ""))
        super().perform_create(serializer)

    def perform_update(self, serializer):
        i, d = serializer.instance, serializer.validated_data
        services.check_timetable(d.get("assignment", i.assignment), d.get("day", i.day),
                                 d.get("start_time", i.start_time), d.get("end_time", i.end_time),
                                 d.get("room", i.room), exclude_id=i.id)
        super().perform_update(serializer)

    @action(detail=False)
    def mine(self, request):
        """The signed-in teacher's weekly lessons, or a pupil's class timetable."""
        user = request.user
        year = services.current_year(user.tenant)
        if user.role_code == "pupil":
            student = getattr(user, "student_profile", None)
            p = services.active_placement(student, year) if student else None
            lessons = services.lessons_for(p.section) if p else []
        else:
            lessons = services.teacher_lessons(user, year)
        return Response(LessonSerializer(lessons, many=True).data)


# --------------------------------------------------------------------------- attendance
class AttendanceViewSet(SchoolViewSet, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AttendanceSerializer
    required_perms = {"list": AUTHENTICATED, "register": "school.attendance.record",
                      "sheet": AUTHENTICATED, "summary": AUTHENTICATED}
    filterset_fields = ["student", "section", "date", "status", "lesson"]

    def get_queryset(self):
        qs = PupilAttendance.objects.filter(student__in=visible_students(self.request.user)).select_related(
            "student__person", "section__grade_level", "lesson__assignment__subject")
        if self.request.query_params.get("daily") == "1":
            qs = qs.filter(lesson__isnull=True)
        return qs

    def _lesson(self, request, lesson_id):
        if not lesson_id:
            return None
        lesson = SchoolTimetable.objects.filter(tenant=request.user.tenant, pk=lesson_id).select_related(
            "assignment").first()
        if lesson is None:
            raise ValidationError({"lesson": ["Lesson not found."]})
        return lesson

    @action(detail=False)
    def sheet(self, request):
        """The register for a class on a date (daily, or one lesson), with any marks already taken."""
        section = get_section(request, request.query_params.get("section"))
        if not can_see_class(request.user, section):
            raise PermissionDenied("You don't teach this class.")
        day = parse_date(request.query_params.get("date"))
        lesson = self._lesson(request, request.query_params.get("lesson"))
        existing = {a.student_id: a for a in PupilAttendance.objects.filter(section=section, date=day, lesson=lesson)}
        lessons_today = [lesson_ for lesson_ in services.lessons_for(section) if lesson_.day == day.weekday()]
        return Response({
            "section": {"id": section.id, "label": section.label}, "date": day,
            "lesson": LessonSerializer(lesson).data if lesson else None,
            "lessons_today": LessonSerializer(lessons_today, many=True).data,
            "can_record": services.can_record_attendance(request.user, section, lesson),
            "rows": [{"student": p.id, "name": p.person.full_name, "student_no": p.student_no,
                      "status": existing[p.id].status if p.id in existing else None,
                      "reason": existing[p.id].reason if p.id in existing else ""}
                     for p in services.pupils_in(section)],
        })

    @action(detail=False, methods=["post"])
    def register(self, request):
        s = AttendanceRegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        section = get_section(request, s.validated_data["section"])
        lesson = self._lesson(request, s.validated_data.get("lesson"))
        saved = services.record_attendance(section, day=s.validated_data["date"], rows=s.validated_data["records"],
                                           user=request.user, lesson=lesson, request=request)
        return Response({"saved": len(saved), "absent": sum(r.status == "absent" for r in saved)})

    @action(detail=False)
    def summary(self, request):
        """Attendance summary for one pupil (?student=) or every pupil in a class (?section=), for a term."""
        term_id = request.query_params.get("term")
        term = get_term(request, term_id) if term_id else services.current_term(request.user.tenant)
        start, end = (term.start_date, term.end_date) if term else (None, None)
        if request.query_params.get("student"):
            value = request.query_params["student"]
            if value == "me":
                student = getattr(request.user, "student_profile", None)
                if student is None:
                    raise ValidationError({"student": ["Choose a pupil."]})
            else:
                if not value.isdigit():
                    raise ValidationError({"student": ["Choose a pupil."]})
                student = visible_students(request.user).filter(pk=int(value)).first()
                if student is None:
                    raise Http404
            return Response({"term": term.name if term else None, **services.attendance_summary(student, start, end)})
        section = get_section(request, request.query_params.get("section"))
        if not can_see_class(request.user, section):
            raise PermissionDenied("You don't teach this class.")
        rows = [{"student": p.id, "name": p.person.full_name, **services.attendance_summary(p, start, end)}
                for p in services.pupils_in(section)]
        rates = [r["attendance_rate"] for r in rows if r["attendance_rate"] is not None]
        return Response({"term": term.name if term else None, "class_rate": round(sum(rates) / len(rates), 1)
                         if rates else None, "rows": rows})


# --------------------------------------------------------------------------- homework, quizzes, exams and marks
class AssessmentViewSet(SchoolViewSet, viewsets.ModelViewSet):
    serializer_class = AssessmentSerializer
    queryset = SchoolAssessment.objects.select_related("section__grade_level", "subject", "term")
    required_perms = {"list": AUTHENTICATED, "retrieve": AUTHENTICATED, "marks": AUTHENTICATED,
                      "*": "school.marks.enter"}
    filterset_fields = ["section", "subject", "term", "kind"]
    ordering_fields = ["due_date", "name"]

    def get_queryset(self):
        u = self.request.user
        qs = super().get_queryset()
        if u.has_perm_code("students.view", "school.results.publish"):
            return qs
        if u.has_perm_code("school.marks.enter"):
            return qs.filter(Q(section__homeroom_teacher=u) | Q(section__assignments__teacher=u,
                                                                section__assignments__subject=F("subject"))
                             ).distinct()
        # Pupils and guardians see the homework and tests set for their (children's) classes.
        return qs.filter(section__placements__student__in=visible_students(u),
                         section__placements__status="active").distinct()

    def _check(self, section, subject):
        if not services.can_enter_marks(self.request.user, section, subject):
            raise PermissionDenied("You don't teach this subject in this class.")

    def perform_create(self, serializer):
        d = serializer.validated_data
        self._check(d["section"], d["subject"])
        if services.results_locked(d["section"], d["term"]):
            raise BusinessRuleViolation("Results for that term are finalized.", code="results_finalized")
        obj = serializer.save(tenant=self.tenant, created_by=self.request.user)
        log_event("assessment.created", request=self.request, target=obj,
                  changes={"name": obj.name, "kind": obj.kind, "weight": str(obj.weight)})
        if obj.kind == "homework" or obj.due_date:
            from comms.services import notify
            users = []
            for p in services.pupils_in(obj.section):
                users.extend(services.family_of(p))
            notify(users, f"New {obj.get_kind_display().lower()}: {obj.subject}",
                   f"{obj.name}" + (f", due {obj.due_date:%a %d %b}" if obj.due_date else ""), kind="homework",
                   link="/school/assignments")

    def perform_update(self, serializer):
        i = serializer.instance
        self._check(i.section, serializer.validated_data.get("subject", i.subject))
        services.ensure_marks_editable(i)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._check(instance.section, instance.subject)
        services.ensure_marks_editable(instance)
        super().perform_destroy(instance)

    @action(detail=True, methods=["get", "post"])
    def marks(self, request, pk=None):
        a = self.get_object()
        if request.method == "POST":
            s = MarksSerializer(data=request.data)
            s.is_valid(raise_exception=True)
            n = services.save_marks(a, s.validated_data["marks"], user=request.user, request=request)
            return Response({"saved": n})
        if not services.can_enter_marks(request.user, a.section, a.subject) and \
                not request.user.has_perm_code("students.view"):
            # Families only see marks once the term's report card is published.
            published = TermResult.objects.filter(section=a.section, term=a.term, status="published").exists()
            if not published:
                return Response({"assessment": AssessmentSerializer(a).data, "rows": []})
            qs = a.marks.filter(student__in=visible_students(request.user))
            return Response({"assessment": AssessmentSerializer(a).data,
                             "rows": MarkSerializer(qs.select_related("student__person"), many=True).data})
        marks = {m.student_id: m for m in a.marks.all()}
        return Response({
            "assessment": AssessmentSerializer(a).data, "locked": services.results_locked(a.section, a.term),
            "rows": [{"student": p.id, "name": p.person.full_name, "student_no": p.student_no,
                      "score": marks[p.id].score if p.id in marks else None,
                      "remarks": marks[p.id].remarks if p.id in marks else ""} for p in services.pupils_in(a.section)],
        })


# --------------------------------------------------------------------------- results and report cards
class TermResultViewSet(SchoolViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                        viewsets.GenericViewSet):
    serializer_class = TermResultSerializer
    required_perms = {"list": AUTHENTICATED, "retrieve": AUTHENTICATED, "report_card": AUTHENTICATED,
                      "update": AUTHENTICATED, "partial_update": AUTHENTICATED,
                      "finalize": "school.results.publish", "publish": "school.results.publish",
                      "reopen": "school.results.publish"}
    filterset_fields = ["section", "term", "student", "status"]
    audit_name = "term_result"

    def get_queryset(self):
        return services.visible_results(self.request.user)

    def perform_update(self, serializer):
        r, d, u = serializer.instance, serializer.validated_data, self.request.user
        if r.status == "published":
            raise BusinessRuleViolation("Remarks can't be changed after the report card is published.",
                                        code="already_published")
        if "teacher_remark" in d and r.section.homeroom_teacher_id != u.id and \
                not u.has_perm_code("school.results.publish"):
            raise PermissionDenied("Only the class teacher writes the class teacher's remark.")
        if "principal_remark" in d and not u.has_perm_code("school.results.publish"):
            raise PermissionDenied("Only the principal writes the principal's remark.")
        super().perform_update(serializer)

    def _section_term(self, request):
        s = SectionTermSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return get_section(request, s.validated_data["section"]), get_term(request, s.validated_data["term"])

    @action(detail=False, methods=["post"])
    def finalize(self, request):
        section, term = self._section_term(request)
        created = services.finalize_results(section, term, user=request.user, request=request)
        return Response({"finalized": len(created)}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def publish(self, request):
        section, term = self._section_term(request)
        return Response({"published": services.publish_results(section, term, user=request.user, request=request)})

    @action(detail=False, methods=["post"])
    def reopen(self, request):
        section, term = self._section_term(request)
        return Response({"reopened": services.reopen_results(section, term, user=request.user, request=request)})

    @action(detail=True, url_path="report-card")
    def report_card(self, request, pk=None):
        result = self.get_object()
        staff = request.user.has_perm_code("students.view", "school.results.publish") or \
            result.section.homeroom_teacher_id == request.user.id
        if result.status != "published" and not staff:
            raise Http404
        pdf = report_card_pdf(result)
        student = result.student
        save_generated_pdf(tenant=request.user.tenant, kind="report_card",
                           title=f"Report card {result.term.name} – {student.person.full_name}", pdf_bytes=pdf,
                           student=student, user=request.user)
        log_event("document.generated.report_card", request=request, target=student,
                  changes={"term": result.term.name})
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{student.student_no}-report-card.pdf"'
        return response


# --------------------------------------------------------------------------- promotion
class PromotionViewSet(SchoolViewSet, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = PromotionSerializer
    required_perms = {"list": AUTHENTICATED, "recommendations": "school.promotion.decide",
                      "decide": "school.promotion.decide"}
    filterset_fields = ["section", "decision", "academic_year", "student"]

    def get_queryset(self):
        return PromotionDecision.objects.filter(student__in=visible_students(self.request.user)).select_related(
            "student__person", "from_level", "to_level", "section__grade_level", "decided_by")

    @action(detail=False)
    def recommendations(self, request):
        section = get_section(request, request.query_params.get("section"))
        decided = {d.student_id: d for d in PromotionDecision.objects.filter(section=section)}
        pupils = list(services.pupils_in(section))
        pupils += [d.student for d in decided.values() if d.student not in pupils]
        rows = []
        for p in pupils:
            rec = services.year_record(p, section)
            d = decided.get(p.id)
            rows.append({"student": p.id, "name": p.person.full_name, "student_no": p.student_no, **rec,
                         "decision": PromotionSerializer(d).data if d else None})
        nxt = section.grade_level.next_level()
        return Response({"section": section.label, "is_final_grade": section.grade_level.is_final,
                         "next_level": nxt.name if nxt else None, "rows": rows})

    @action(detail=False, methods=["post"])
    def decide(self, request):
        s = DecideSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        section = get_section(request, s.validated_data["section"])
        student = Student.objects.filter(tenant=request.user.tenant, pk=s.validated_data["student"]).first()
        if student is None:
            raise ValidationError({"student": ["Pupil not found."]})
        d = services.decide_promotion(student, section, s.validated_data["decision"], user=request.user,
                                      reason=s.validated_data.get("reason", ""), request=request)
        return Response(PromotionSerializer(d).data, status=status.HTTP_201_CREATED)


# --------------------------------------------------------------------------- guardian / pupil portal
class ChildrenView(APIView):
    """Guardian portal: each linked child's class, attendance, homework, published results and fees.
    Pupils get the same view of themselves."""

    permission_classes = SCHOOL_PERMS

    def get(self, request):
        u = request.user
        if u.role_code == "guardian":
            children = Student.objects.filter(tenant=u.tenant, guardian_links__guardian__user=u).distinct()
        elif u.role_code == "pupil":
            children = Student.objects.filter(tenant=u.tenant, user=u)
        else:
            raise PermissionDenied("The family portal is for parents, guardians and pupils.")
        year, term = services.current_year(u.tenant), services.current_term(u.tenant)
        today = timezone.localdate()
        out = []
        for child in children.select_related("person"):
            p = services.active_placement(child, year)
            section = p.section if p else None
            homework = (SchoolAssessment.objects.filter(section=section, due_date__gte=today)
                        .select_related("subject", "term", "section__grade_level").order_by("due_date")[:8]
                        if section else [])
            results = TermResult.objects.filter(student=child, status="published").select_related("term", "section")
            balance = sum((i.balance for i in Invoice.objects.filter(student=child)
                           .exclude(status__in=["void", "draft"])), start=0)
            out.append({
                "id": child.id, "student_no": child.student_no, "name": child.person.full_name,
                "status": child.status, "level": child.current_level,
                "class": section.label if section else None,
                "class_teacher": section.homeroom_teacher.get_full_name() if section and section.homeroom_teacher
                else None,
                "attendance": services.attendance_summary(child, term.start_date if term else None, today),
                "recent_absences": AttendanceSerializer(
                    PupilAttendance.objects.filter(student=child, status__in=["absent", "excused"])
                    .select_related("student__person", "section__grade_level", "lesson__assignment__subject")[:5],
                    many=True).data,
                "homework": AssessmentSerializer(homework, many=True).data,
                "results": [{"id": r.id, "term": r.term.name, "class": r.section.label, "average": r.average,
                             "grade": r.grade, "position": r.position, "class_size": r.class_size}
                            for r in results],
                "fee_balance": balance,
            })
        return Response(out)
