"""
Plugs the school module into the shared services without the shared code knowing about classes,
terms or promotion:

* admissions: the grade applied for is validated, and enrolment places the pupil in a class
* people:     class and subject teachers see the pupils they teach
* reports:    school dashboard metrics (attendance, pass rates)
* enrollment: withdrawing or transferring a pupil ends their class placement
* seed:       demo grade levels, classes, timetables, attendance, marks and published report cards
"""
import random
from datetime import date, time, timedelta
from decimal import Decimal

from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from admissions.hooks import register_enrollment_handler, register_target_validator
from admissions.models import AcademicPeriod, Enrollment
from core.exceptions import BusinessRuleViolation
from people.scoping import register_student_scope
from reports.views import register_dashboard_provider
from seed import hooks as seed_hooks

from . import services
from .models import (
    ClassAssignment,
    ClassPlacement,
    ClassSection,
    GradeLevel,
    PromotionDecision,
    PupilAttendance,
    SchoolAssessment,
    SchoolMark,
    SchoolTimetable,
    Subject,
    TermResult,
)


# --------------------------------------------------------------------------- admissions
@register_target_validator("school")
def validate_grade(tenant, target_id):
    level = GradeLevel.objects.filter(tenant=tenant, pk=target_id).first()
    if level is None:
        raise ValidationError({"target_id": ["Choose a grade level offered by this school."]})
    return level.name


@register_enrollment_handler("school")
def place_new_pupil(request, application, student, data):
    """Approved applicant -> enrolled pupil placed in a class for the intake (or current) year."""
    tenant = student.tenant
    if not GradeLevel.objects.filter(tenant=tenant).exists():
        return application.requested_level, ""  # classes not configured yet
    if data.get("section"):
        section = ClassSection.objects.filter(tenant=tenant, pk=data["section"]).first()
        if section is None:
            raise ValidationError({"section": ["Class not found."]})
    else:
        year = application.intake_period if application.intake_period and \
            application.intake_period.kind == "academic_year" else services.current_year(tenant)
        level = (GradeLevel.objects.filter(tenant=tenant, pk=application.target_id).first()
                 or GradeLevel.objects.filter(tenant=tenant, name__iexact=application.requested_level).first())
        candidates = [s for s in ClassSection.objects.filter(tenant=tenant, grade_level=level, academic_year=year)
                      if services.pupils_in(s).count() < s.capacity] if level and year else []
        if not candidates:
            raise BusinessRuleViolation(
                f"No {application.requested_level} class with free places. Choose a class for the pupil.",
                code="class_required", fields={"section": ["Required."]})
        section = min(candidates, key=lambda s: services.pupils_in(s).count())
    services.place_student(student, section, user=request.user, request=request)
    return section.grade_level.name, section.name


# --------------------------------------------------------------------------- visibility
@register_student_scope
def teaching_scope(user):
    if user.role_code in ("class_teacher", "subject_teacher"):
        return Q(class_placements__status="active") & (
            Q(class_placements__section__homeroom_teacher=user) |
            Q(class_placements__section__assignments__teacher=user))
    return None


@receiver(post_save, sender=Enrollment)
def end_placement_on_exit(sender, instance, raw=False, **kwargs):
    if raw:  # loading a data dump: placements are loaded as they were
        return
    if instance.status in ("withdrawn", "transferred"):
        services.end_placements(instance.student, instance.end_date)


# --------------------------------------------------------------------------- dashboard
@register_dashboard_provider("school")
def dashboard(tenant):
    today = timezone.localdate()
    todays = PupilAttendance.objects.filter(tenant=tenant, date=today, lesson__isnull=True)
    n = todays.count()
    present = todays.filter(status__in=["present", "late"]).count()
    pass_mark = services.policy(tenant, "pass_mark")
    by_term = []
    for term in AcademicPeriod.objects.filter(tenant=tenant, kind="term", start_date__lte=today).order_by(
            "start_date"):
        rate = services.pass_rate(TermResult.objects.filter(term=term), pass_mark)
        if rate is not None:
            by_term.append({"label": term.name.replace("Term ", "T"), "value": rate})
    return {
        "stats": {"attendance_today": round(100 * present / n, 1) if n else None,
                  "pass_rate": by_term[-1]["value"] if by_term else None},
        "attendance_trend": services.weekly_attendance(tenant),
        "pass_rate_by_term": by_term,
    }


# --------------------------------------------------------------------------- demo data
def _reset(tenants):
    for model in (PromotionDecision, TermResult, SchoolMark, SchoolAssessment, PupilAttendance, SchoolTimetable,
                  ClassPlacement, ClassAssignment, ClassSection, Subject, GradeLevel):
        model.objects.filter(tenant__in=tenants).delete()


SUBJECTS = [("MATH", "Mathematics"), ("ENG", "English"), ("KIS", "Kiswahili"), ("SCI", "Science"),
            ("SST", "Social Studies")]
PERIODS = [(time(8, 0), time(8, 50)), (time(9, 0), time(9, 50)), (time(10, 20), time(11, 10)),
           (time(11, 20), time(12, 10)), (time(14, 0), time(14, 50))]
EXTRA_TEACHERS = [("kiswahili@sunrise.edu", "Halima", "Said", "KIS"), ("science@sunrise.edu", "John", "Mutiso", "SCI"),
                  ("social@sunrise.edu", "Esther", "Wafula", "SST")]


def seed(cmd, *, school, university):  # noqa: C901 - linear demo script
    from core.models import User
    from people.models import Person, Staff, Student

    t = school
    rng = random.Random(1234)
    today = timezone.localdate()
    users = {u.email: u for u in User.objects.filter(tenant=t)}
    principal, mary, peter = users["principal@sunrise.edu"], users["teacher@sunrise.edu"], users["subject@sunrise.edu"]
    teachers = {"MATH": peter, "ENG": mary}
    for i, (email, first, last, code) in enumerate(EXTRA_TEACHERS, start=10):
        u = cmd._user(email, first, last, "subject_teacher", t)
        p = Person.objects.create(tenant=t, first_name=first, last_name=last, email=email)
        Staff.objects.create(tenant=t, person=p, user=u, staff_no=f"STF-{i:04d}", job_title=f"{code} Teacher")
        teachers[code] = u

    year = AcademicPeriod.objects.get(tenant=t, kind="academic_year", is_current=True)
    terms = list(year.children.filter(kind="term").order_by("start_date"))
    AcademicPeriod.objects.create(tenant=t, name="2027", kind="academic_year", start_date=date(2027, 1, 4),
                                  end_date=date(2027, 12, 10))
    levels = [GradeLevel.objects.create(tenant=t, name=f"Grade {g}", order=g, is_final=g == 8) for g in range(1, 9)]
    subjects = {code: Subject.objects.create(tenant=t, code=code, name=name) for code, name in SUBJECTS}

    # Classes 1A..8B. Lessons follow a rotating pattern, so a teacher who takes a subject in five
    # consecutive classes (here Grades 3B-5B, which include Grade 4A) never has two lessons at once.
    sections = []
    for level in levels:
        for name in ("A", "B"):
            sections.append(ClassSection.objects.create(
                tenant=t, grade_level=level, academic_year=year, name=name, capacity=35, room=f"Room {level.order}{name}",
                homeroom_teacher=mary if (level.order, name) == (4, "A") else None))
    lessons = []
    for k, section in enumerate(sections):
        staffed = 5 <= k <= 9
        for j, (code, _) in enumerate(SUBJECTS):
            a = ClassAssignment.objects.create(tenant=t, section=section, subject=subjects[code],
                                               teacher=teachers[code] if staffed else None)
            for d in range(5):
                p = (j + k + d) % 5
                lessons.append(SchoolTimetable(tenant=t, assignment=a, day=d, period_no=p + 1,
                                               start_time=PERIODS[p][0], end_time=PERIODS[p][1], room=section.room))
    SchoolTimetable.objects.bulk_create(lessons)

    by_label = {(s.grade_level.name, s.name): s for s in sections}
    pupils = list(Student.objects.filter(tenant=t).select_related("person"))
    for s in pupils:
        section = by_label[(s.current_level, s.current_section)]
        ClassPlacement.objects.create(tenant=t, student=s, section=section, start_date=year.start_date)
    members = {s.id: [p for p in pupils if (p.current_level, p.current_section) ==
                      (s.grade_level.name, s.name)] for s in sections}

    # Daily attendance for every school day so far this year (today too, except Grade 4A for the demo).
    brian = next(p for p in pupils if p.user and p.user.email == "pupil@sunrise.edu")
    records = []
    for term in terms:
        end = min(term.end_date, today)
        for day in services.school_days_between(term.start_date, end):
            for section in sections:
                if day == today and section == by_label[("Grade 4", "A")]:
                    continue
                for p in members[section.id]:
                    roll = rng.random()
                    st = "present" if roll < 0.92 else "late" if roll < 0.95 else "absent" if roll < 0.98 else "excused"
                    if p == brian and day in (today - timedelta(days=d) for d in (6, 7)):
                        st = "absent"
                    records.append(PupilAttendance(
                        tenant=t, student=p, section=section, date=day, status=st, recorded_by=principal,
                        reason="Medical appointment" if st == "excused" else "",
                        guardian_notified=st == "absent"))
    PupilAttendance.objects.bulk_create(records, batch_size=2000)

    # Homework, quizzes and exams with marks. Terms 1-2 are finalized and published; Term 3 is complete
    # except Grade 4A Mathematics' exam (entered by the maths teacher in the demo).
    ability = {p.id: rng.gauss(66, 12) for p in pupils}
    marks = []
    for term in terms:
        for section in sections:
            for code, _ in SUBJECTS:
                teacher = teachers[code] if 5 <= sections.index(section) <= 9 else principal
                items = [("Homework 1", "homework", 10, 20, 14), ("Quiz", "quiz", 20, 30, 35),
                         ("End of term exam", "exam", 70, 100, (term.end_date - term.start_date).days - 7)]
                for name, kind, weight, max_score, offset in items:
                    a = SchoolAssessment.objects.create(
                        tenant=t, section=section, subject=subjects[code], term=term, name=name, kind=kind,
                        weight=weight, max_score=max_score, due_date=term.start_date + timedelta(days=offset),
                        created_by=teacher)
                    if term == terms[-1] and kind == "exam" and code == "MATH" and \
                            section == by_label[("Grade 4", "A")]:
                        continue
                    for p in members[section.id]:
                        pct = max(0.15, min(1.0, rng.gauss(ability[p.id], 9) / 100))
                        marks.append(SchoolMark(tenant=t, assessment=a, student=p, recorded_by=teacher,
                                                score=(Decimal(str(round(pct, 3))) * max_score).quantize(Decimal("0.5"))))
            if term == terms[-1]:
                for code in ("MATH", "ENG"):  # ungraded practice homework due next week, for the family portal
                    SchoolAssessment.objects.create(
                        tenant=t, section=section, subject=subjects[code], term=term, kind="homework", weight=0,
                        name=f"Practice worksheet ({subjects[code].name})", max_score=10,
                        due_date=today + timedelta(days=5), created_by=teachers[code] if 5 <= sections.index(
                            section) <= 9 else principal,
                        description="Complete the worksheet handed out in class.")
    SchoolMark.objects.bulk_create(marks, batch_size=2000)
    for term in terms[:-1]:
        if term.end_date >= today:
            continue
        for section in sections:
            services.finalize_results(section, term, user=principal)
            TermResult.objects.filter(section=section, term=term).update(
                teacher_remark="Keep up the steady effort.", principal_remark="Good progress this term.")
            services.publish_results(section, term, user=principal)
    cmd.stdout.write(f"  Sunrise Academy classes: {len(sections)} classes, {len(lessons)} lessons, "
                     f"{len(records)} attendance marks, {len(marks)} marks")


seed_hooks.HOOKS.append(seed)
seed_hooks.RESET_HOOKS.append(_reset)
