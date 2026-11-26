"""
Plugs the university module into the shared services without the shared code knowing about
programs, credits or transcripts:

* admissions: the program applied for is validated, and matriculation creates the academic standing
* people:     lecturers see students in their sections; advisers see their advisees
* reports:    university dashboard metrics
* seed:       demo faculties, programs, courses, semesters, sections, registrations and grades
"""
import random
from datetime import date, time, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from admissions.hooks import register_enrollment_handler, register_target_validator
from core.exceptions import BusinessRuleViolation
from people.scoping import register_student_scope
from reports.views import register_dashboard_provider
from seed import hooks as seed_hooks

from .models import (
    AcademicStanding,
    AssessmentScore,
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
    OfferingMeeting,
    Program,
    Semester,
    TranscriptEntry,
    UniversityAssessment,
    UniversityGrade,
)


# --------------------------------------------------------------------------- admissions
@register_target_validator("university")
def validate_program(tenant, target_id):
    program = Program.objects.filter(tenant=tenant, pk=target_id, is_active=True).first()
    if program is None:
        raise ValidationError({"target_id": ["Choose a program offered by this university."]})
    return program.name


def _program_for(tenant, application, data):
    program_id = data.get("program") or application.target_id
    if program_id:
        program = Program.objects.filter(tenant=tenant, pk=program_id, is_active=True).first()
        if program is None:
            raise ValidationError({"program": ["Choose a program offered by this university."]})
        return program
    return Program.objects.filter(tenant=tenant, name__iexact=application.requested_level, is_active=True).first()


@register_enrollment_handler("university")
def matriculate(request, application, student, data):
    """Accepted offer -> matriculated student in a program (with curriculum and optional adviser)."""
    tenant = student.tenant
    program = _program_for(tenant, application, data)
    if program is None:
        if Program.objects.filter(tenant=tenant).exists():
            raise BusinessRuleViolation("Choose the program the student is matriculating into.",
                                        code="program_required", fields={"program": ["Required."]})
        return application.requested_level, "Year 1"  # catalogue not configured yet
    adviser = None
    if data.get("adviser"):
        from core.models import User
        adviser = User.objects.filter(tenant=tenant, pk=data["adviser"], role__code="adviser").first()
    AcademicStanding.objects.create(tenant=tenant, student=student, program=program,
                                    curriculum=program.current_curriculum(), adviser=adviser,
                                    matriculated_on=timezone.localdate())
    return program.name, "Year 1"


# --------------------------------------------------------------------------- student visibility
@register_student_scope
def teaching_scope(user):
    if user.role_code == "lecturer":
        return Q(course_registrations__offering__lecturer=user,
                 course_registrations__status__in=CourseRegistration.ACTIVE)
    if user.role_code == "adviser":
        return Q(academic_standing__adviser=user)
    return None


# --------------------------------------------------------------------------- dashboard
@register_dashboard_provider("university")
def dashboard(tenant):
    sem = Semester.objects.filter(tenant=tenant, period__is_current=True).first()
    regs = CourseRegistration.objects.filter(tenant=tenant, status__in=CourseRegistration.ACTIVE)
    if sem:
        regs = regs.filter(offering__semester=sem)
    standings = AcademicStanding.objects.filter(tenant=tenant, student__status="active")
    avg = standings.exclude(cgpa__isnull=True).aggregate(a=Avg("cgpa"))["a"]
    demand = []
    if sem:
        offerings = (CourseOffering.objects.filter(semester=sem).exclude(status="cancelled")
                     .annotate(n=Count("registrations", filter=Q(registrations__status__in=["pending", "approved"])))
                     .select_related("course").order_by("-n")[:6])
        demand = [{"label": f"{o.course.code}-{o.section} {o.course.title}", "value": o.n, "capacity": o.capacity}
                  for o in offerings]
    bands = [("<2.0", 0, 2), ("2.0–2.49", 2, 2.5), ("2.5–2.99", 2.5, 3), ("3.0–3.49", 3, 3.5), ("3.5–4.0", 3.5, 4.01)]
    cgpas = [float(c) for c in standings.exclude(cgpa__isnull=True).values_list("cgpa", flat=True)]
    gpa_dist = [{"label": label, "value": sum(lo <= c < hi for c in cgpas)} for label, lo, hi in bands]
    completion = []
    for year in sorted(set(standings.values_list("year_of_study", flat=True))):
        rows = standings.filter(year_of_study=year).select_related("program")
        pct = [100 * r.credits_earned / r.program.total_credits_required for r in rows]
        completion.append({"label": f"Year {year}", "value": round(sum(pct) / len(pct)) if pct else 0})
    return {
        "stats": {"registrations": regs.count(), "avg_cgpa": round(avg, 2) if avg is not None else None,
                  "on_probation": standings.filter(standing="probation").count(),
                  "students": standings.count() or None},
        "course_demand": demand,
        "gpa_distribution": gpa_dist,
        "credit_completion": completion,
    }


# --------------------------------------------------------------------------- demo data
def _reset(tenants):
    entries = TranscriptEntry.objects.filter(tenant__in=tenants)
    while entries.exists():  # newest amendments first (they protect the entries they supersede)
        entries.filter(superseded_by__isnull=True).delete()
    for model in (GraduationClearance, GradeApproval, AssessmentScore, UniversityGrade, UniversityAssessment,
                  CourseRegistration, AcademicStanding, OfferingMeeting, CourseOffering, Semester, CurriculumCourse,
                  Curriculum, CoursePrerequisite, Course, Program, Department, Faculty):
        model.objects.filter(tenant__in=tenants).delete()


CATALOG = {
    # dept code: (faculty code, department name)
    "CS": ("COMP", "Computer Science"), "CY": ("COMP", "Cybersecurity"), "FN": ("BUS", "Finance"),
    "EC": ("BUS", "Economics"), "EE": ("ENG", "Electrical Engineering"),
}
FACULTIES = {"COMP": "Faculty of Computing", "BUS": "Faculty of Business & Economics", "ENG": "Faculty of Engineering"}
COURSES = [
    # code, title, credits, level, dept, prerequisites
    ("CS101", "Introduction to Programming", 3, 100, "CS", []),
    ("MATH101", "Calculus I", 3, 100, "CS", []),
    ("ENG101", "Academic Writing", 3, 100, "EC", []),
    ("CS102", "Programming II", 3, 100, "CS", ["CS101"]),
    ("CS201", "Data Structures", 4, 200, "CS", ["CS102"]),
    ("CS205", "Discrete Mathematics", 3, 200, "CS", ["MATH101"]),
    ("MATH201", "Linear Algebra", 3, 200, "CS", ["MATH101"]),
    ("CS210", "Database Systems", 3, 200, "CS", ["CS201"]),
    ("CS220", "Web Development", 3, 200, "CS", ["CS101"]),
    ("CS301", "Algorithms", 4, 300, "CS", ["CS201", "CS205"]),
    ("CY110", "Introduction to Cybersecurity", 3, 100, "CY", []),
    ("CY210", "Network Security", 3, 200, "CY", ["CY110"]),
    ("FN101", "Principles of Accounting", 3, 100, "FN", []),
    ("FN220", "Corporate Finance", 3, 200, "FN", ["FN101"]),
    ("EC101", "Microeconomics", 3, 100, "EC", []),
    ("EC102", "Macroeconomics", 3, 100, "EC", ["EC101"]),
    ("EE130", "Circuits I", 4, 100, "EE", ["MATH101"]),
    ("EE230", "Circuits II", 4, 200, "EE", ["EE130"]),
]
PROGRAM_DEFS = {
    # program name: (code, dept, core courses by year, electives)
    "BSc Computer Science": ("BSCS", "CS", {1: ["CS101", "MATH101", "ENG101", "CS102"],
                                            2: ["CS201", "CS205", "MATH201", "CS210"], 3: ["CS301"]},
                             ["CS220", "CY110", "CY210"]),
    "BSc Cybersecurity": ("BSCY", "CY", {1: ["CS101", "CY110", "MATH101", "ENG101"], 2: ["CY210", "CS102", "CS201"]},
                          ["CS220", "CS205"]),
    "BBA Finance": ("BBAF", "FN", {1: ["FN101", "EC101", "ENG101", "MATH101"], 2: ["FN220", "EC102"]},
                    ["CS101"]),
    "BEng Electrical Engineering": ("BEEE", "EE", {1: ["MATH101", "EE130", "ENG101", "CS101"],
                                                   2: ["EE230", "MATH201"]}, ["CS102"]),
    "BA Economics": ("BAEC", "EC", {1: ["EC101", "ENG101", "MATH101", "EC102"], 2: ["FN101", "FN220"]}, ["CS101"]),
}
SLOTS = [(d, (h, 0)) for h in (8, 10, 12, 14, 16, 18) for d in ((0, 2), (1, 3), (4,))]  # 18 non-overlapping slots


def seed(cmd, *, school, university):  # noqa: C901 - linear demo script
    from core.models import User
    from people.models import Person, Staff, Student

    from . import services

    t = university
    rng = random.Random(4242)
    today = timezone.localdate()
    users = {u.email: u for u in User.objects.filter(tenant=t)}
    dean, hod, registrar = users["dean@omniu.edu"], users["hod@omniu.edu"], users["registrar@omniu.edu"]
    adviser, lecturer = users["adviser@omniu.edu"], users["lecturer@omniu.edu"]
    lecturers = [lecturer]
    for i, (first, last) in enumerate((("Ruth", "Mwangi"), ("Tom", "Becker")), start=2):
        u = cmd._user(f"lecturer{i}@omniu.edu", first, last, "lecturer", t)
        p = Person.objects.create(tenant=t, first_name=first, last_name=last, email=u.email)
        Staff.objects.create(tenant=t, person=p, user=u, staff_no=f"STF-{20 + i:04d}", job_title="Lecturer")
        lecturers.append(u)

    faculties = {code: Faculty.objects.create(tenant=t, code=code, name=name, dean=dean if code == "COMP" else None)
                 for code, name in FACULTIES.items()}
    depts = {code: Department.objects.create(tenant=t, code=code, name=name, faculty=faculties[fac],
                                             head=hod if code == "CS" else None)
             for code, (fac, name) in CATALOG.items()}
    courses = {}
    for code, title, credits, level, dept, _ in COURSES:
        courses[code] = Course.objects.create(tenant=t, code=code, title=title, credit_hours=credits, level=level,
                                              department=depts[dept])
    for code, *_, prereqs in COURSES:
        for p in prereqs:
            CoursePrerequisite.objects.create(tenant=t, course=courses[code], prerequisite=courses[p])
    programs = {}
    for name, (code, dept, core, electives) in PROGRAM_DEFS.items():
        prog = Program.objects.create(tenant=t, name=name, code=code, department=depts[dept],
                                      award="BEng" if code == "BEEE" else ("BA" if code == "BAEC" else
                                                                         ("BBA" if code == "BBAF" else "BSc")),
                                      total_credits_required=120)
        cur = Curriculum.objects.create(tenant=t, program=prog, version="2025", effective_from=date(2025, 8, 1),
                                        elective_credits_required=9, is_current=True)
        for year, codes in core.items():
            for i, c in enumerate(codes):
                CurriculumCourse.objects.create(tenant=t, curriculum=cur, course=courses[c], category="core",
                                                recommended_year=year, recommended_semester=1 + i % 2)
        for c in electives:
            CurriculumCourse.objects.create(tenant=t, curriculum=cur, course=courses[c], category="elective",
                                            recommended_year=2)
        programs[name] = prog

    # Semesters: last year's two semesters (graded history) and this year's.
    from admissions.models import AcademicPeriod
    periods = {p.name: p for p in AcademicPeriod.objects.filter(tenant=t)}
    last_year = AcademicPeriod.objects.create(tenant=t, name="2025/26", kind="academic_year",
                                              start_date=date(2025, 8, 25), end_date=date(2026, 7, 31))
    p1 = AcademicPeriod.objects.create(tenant=t, name="Semester 1 2025/26", kind="semester", parent=last_year,
                                       start_date=date(2025, 8, 25), end_date=date(2025, 12, 19))
    p2 = AcademicPeriod.objects.create(tenant=t, name="Semester 2 2025/26", kind="semester", parent=last_year,
                                       start_date=date(2026, 1, 12), end_date=date(2026, 5, 15))
    cur_period, next_period = periods["Semester 1 2026/27"], periods["Semester 2 2026/27"]

    def semester(period, reg_start, reg_end, add_drop):
        return Semester.objects.create(tenant=t, period=period, registration_start=reg_start,
                                       registration_end=reg_end, add_drop_end=add_drop,
                                       grades_due=period.end_date + timedelta(days=10))

    s1 = semester(p1, date(2025, 8, 1), date(2025, 8, 29), date(2025, 9, 12))
    s2 = semester(p2, date(2026, 1, 2), date(2026, 1, 16), date(2026, 1, 30))
    # Keep the current semester's add/drop window open for the demo (at least 3 weeks from seeding).
    add_drop = max(date(2026, 11, 28), today + timedelta(days=21))
    cur = semester(cur_period, min(date(2026, 8, 10), today), add_drop, add_drop)
    semester(next_period, date(2026, 12, 1), date(2027, 1, 15), date(2027, 1, 29))

    slot_counter = {}

    def offering(sem, code, capacity=40, lecturer_user=None, section="A"):
        o = CourseOffering.objects.create(tenant=t, course=courses[code], semester=sem, section=section,
                                          capacity=capacity, lecturer=lecturer_user or rng.choice(lecturers))
        n = slot_counter[sem.id] = slot_counter.get(sem.id, -1) + 1
        days, (h, m) = SLOTS[n % len(SLOTS)]
        for d in days:
            OfferingMeeting.objects.create(tenant=t, offering=o, day=d, start_time=time(h, m),
                                           end_time=time(h + 1, m + 30), room=f"{courses[code].department.code}-"
                                                                             f"{100 + o.id}")
        return o

    # Matriculate every demo student into their program.
    students = list(Student.objects.filter(tenant=t).select_related("person"))
    for s in students:
        prog = programs.get(s.current_level)
        year = int((s.current_section or "Year 1").split()[-1])
        AcademicStanding.objects.create(
            tenant=t, student=s, program=prog, curriculum=prog.current_curriculum(), year_of_study=year,
            adviser=adviser if prog.code in ("BSCS", "BSCY") else None,
            matriculated_on=date(today.year - year + 1 if today.month >= 8 else today.year - year, 8, 24))

    # Past semesters: approved grades for every student in Year 2+ (first-year courses of their program).
    kevin = next(s for s in students if s.user and s.user.email == "student@omniu.edu")
    kevin_scores = {"CS101": 92, "MATH101": 81, "ENG101": 77, "CS102": 76, "CY110": 86}
    past = {}
    for sem, idx in ((s1, (0, 1, 2)), (s2, (3,))):
        for s in students:
            standing = s.academic_standing
            if standing.year_of_study < 2:
                continue
            core1 = PROGRAM_DEFS[standing.program.name][2][1]
            codes = [core1[i] for i in idx]
            if s == kevin and sem == s2:
                codes = ["CS102", "CY110"]
            for code in codes:
                key = (sem.id, code)
                if key not in past:
                    past[key] = offering(sem, code, capacity=200)
                o = past[key]
                o.status = "closed"
                o.save(update_fields=["status"])
                reg = CourseRegistration.objects.create(tenant=t, student=s, offering=o, status="approved",
                                                        requested_by=s.user or registrar, decided_by=registrar,
                                                        decided_at=timezone.now())
                score = kevin_scores.get(code) if s == kevin else max(25, min(99, round(rng.gauss(71, 14))))
                letter, points = services.grade_band(t, score)
                approver = hod if o.course.department_id == depts["CS"].id else registrar
                UniversityGrade.objects.create(tenant=t, registration=reg, total_score=score, letter=letter,
                                               grade_points=points, status="approved", submitted_by=o.lecturer,
                                               submitted_at=timezone.now(), approved_by=approver,
                                               approved_at=timezone.now())
                TranscriptEntry.objects.create(tenant=t, student=s, registration=reg, course=o.course, semester=sem,
                                               course_code=o.course.code, course_title=o.course.title,
                                               credit_hours=o.course.credit_hours, total_score=score, letter=letter,
                                               grade_points=points, approved_by=approver)
    for o in {o.id: o for o in past.values()}.values():
        GradeApproval.objects.create(tenant=t, offering=o, action="submitted", actor=o.lecturer)
        GradeApproval.objects.create(tenant=t, offering=o, action="approved",
                                     actor=hod if o.course.department_id == depts["CS"].id else registrar)
    for s in students:
        services.recompute_standing(s)

    # Current semester sections.
    current = {}
    for code in ("CS101", "MATH101", "ENG101", "CY110", "FN101", "EC101", "EE130", "CS201", "CS205", "MATH201",
                 "CS210", "CS220", "CY210", "FN220", "EC102", "EE230", "CS102"):
        lect = lecturer if code in ("CS201", "CS205", "CS220") else rng.choice(lecturers[1:])
        current[code] = offering(cur, code, capacity={"CY210": 6, "CS201": 45}.get(code, 40), lecturer_user=lect)

    # Register current students the same way the API does (all rules checked), then approve.
    registered = 0
    for s in students:
        standing = s.academic_standing
        core = PROGRAM_DEFS[standing.program.name][2]
        wanted = core.get(1) if standing.year_of_study == 1 else core.get(2, [])
        if s == kevin:
            wanted = ["CS201", "CS205", "MATH201"]
        for code in wanted:
            o = current.get(code)
            if o is None:
                continue
            try:
                services.check_registration(s, o, today=today)
            except BusinessRuleViolation:
                continue
            CourseRegistration.objects.create(tenant=t, student=s, offering=o, status="approved",
                                              requested_by=s.user or registrar, decided_by=adviser
                                              if standing.adviser_id else registrar, decided_at=timezone.now(),
                                              attempt_no=services.current_entries(s).filter(course=o.course).count() + 1)
            registered += 1
    # A few requests waiting for the adviser.
    for s in [s for s in students if s.academic_standing.adviser_id and s != kevin][:4]:
        try:
            services.check_registration(s, current["CS220"], today=today)
        except BusinessRuleViolation:
            continue
        CourseRegistration.objects.create(tenant=t, student=s, offering=current["CS220"], status="pending",
                                          requested_by=s.user or registrar)

    # Gradebook demo: CS201 has partial scores (draft); CS205 is complete and submitted for the HOD to approve.
    def assessments(o):
        return [UniversityAssessment.objects.create(tenant=t, offering=o, name=n, kind=k, weight=w, max_score=m,
                                                    due_date=cur_period.start_date + timedelta(days=d))
                for n, k, w, m, d in (("Assignment 1", "assignment", 15, 20, 21), ("Midterm exam", "midterm", 25, 50, 49),
                                      ("Group project", "project", 20, 100, 84), ("Final exam", "exam", 40, 100, 112))]

    for code, complete in (("CS201", False), ("CS205", True)):
        o = current[code]
        items = assessments(o)
        regs = list(o.registrations.filter(status="approved"))
        for r in regs:
            for a in (items if complete else items[:2]):
                pct = max(0.2, min(1.0, rng.gauss(0.72, 0.14)))
                AssessmentScore.objects.create(tenant=t, assessment=a, registration=r, recorded_by=o.lecturer,
                                               score=(Decimal(str(round(pct, 2))) * a.max_score).quantize(Decimal("0.5")))
        if complete and regs:
            services.submit_grades(o, user=o.lecturer)

    cmd.stdout.write(f"  Omni University catalogue: {len(courses)} courses, {len(programs)} programs, "
                     f"{len(current)} sections this semester, {registered} registrations")


seed_hooks.HOOKS.append(seed)
seed_hooks.RESET_HOOKS.append(_reset)
