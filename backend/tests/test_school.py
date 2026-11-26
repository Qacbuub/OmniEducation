"""School (K-12) module: classes, timetable, attendance, marks, term results, report cards, promotion."""
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from admissions.models import AcademicPeriod, Enrollment
from comms.models import Notification
from core.models import Tenant
from school import services
from school.models import (
    ClassAssignment,
    ClassPlacement,
    ClassSection,
    GradeLevel,
    PupilAttendance,
    SchoolAssessment,
    SchoolMark,
    SchoolTimetable,
    Subject,
    TermResult,
)

TODAY = timezone.localdate()


def last_weekday(d):
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


SCHOOL_DAY = last_weekday(TODAY)


@pytest.fixture
def sch(school, make_user):
    """Grades 1-3 (3 is final), Maths and English, a current year with a past and a current term."""
    t = school
    staff = {r: make_user(f"{r}@s.edu", r, t) for r in ("inst_admin", "principal", "class_teacher",
                                                         "subject_teacher", "finance_officer")}
    staff["other_teacher"] = make_user("other@s.edu", "subject_teacher", t)
    staff["guardian"] = make_user("parent@s.edu", "guardian", t)
    year = AcademicPeriod.objects.create(tenant=t, name="This year", kind="academic_year", is_current=True,
                                         start_date=TODAY - timedelta(days=200), end_date=TODAY + timedelta(days=60))
    t1 = AcademicPeriod.objects.create(tenant=t, name="Term 1", kind="term", parent=year,
                                       start_date=year.start_date, end_date=TODAY - timedelta(days=60))
    t2 = AcademicPeriod.objects.create(tenant=t, name="Term 2", kind="term", parent=year, is_current=True,
                                       start_date=min(TODAY - timedelta(days=40), SCHOOL_DAY - timedelta(days=10)),
                                       end_date=TODAY + timedelta(days=50))
    nxt = AcademicPeriod.objects.create(tenant=t, name="Next year", kind="academic_year",
                                        start_date=year.end_date + timedelta(days=20),
                                        end_date=year.end_date + timedelta(days=300))
    levels = [GradeLevel.objects.create(tenant=t, name=f"Grade {i}", order=i, is_final=i == 3) for i in (1, 2, 3)]
    subj = {c: Subject.objects.create(tenant=t, code=c, name=n) for c, n in (("MATH", "Mathematics"),
                                                                           ("ENG", "English"))}
    g1a = ClassSection.objects.create(tenant=t, grade_level=levels[0], academic_year=year, name="A", capacity=30,
                                      homeroom_teacher=staff["class_teacher"])
    g3a = ClassSection.objects.create(tenant=t, grade_level=levels[2], academic_year=year, name="A",
                                      homeroom_teacher=staff["class_teacher"])
    for sec in (g1a, g3a):
        ClassAssignment.objects.create(tenant=t, section=sec, subject=subj["MATH"], teacher=staff["subject_teacher"])
        ClassAssignment.objects.create(tenant=t, section=sec, subject=subj["ENG"], teacher=staff["class_teacher"])
    return {"t": t, "staff": staff, "year": year, "t1": t1, "t2": t2, "next": nxt, "levels": levels, "subj": subj,
            "g1a": g1a, "g3a": g3a}


@pytest.fixture
def pupil_in(sch, make_student, make_user, link_guardian):
    def _p(section=None, first="Pat", with_login=False, guardian=False):
        section = section or sch["g1a"]
        user = make_user(f"{first.lower()}@s.edu", "pupil", sch["t"]) if with_login else None
        s = make_student(sch["t"], first=first, level=section.grade_level.name, user=user)
        ClassPlacement.objects.create(tenant=sch["t"], student=s, section=section, start_date=sch["year"].start_date)
        Enrollment.objects.create(tenant=sch["t"], student=s, period=sch["year"], level_label=section.grade_level.name,
                                  section_label=section.name, start_date=sch["year"].start_date)
        if guardian:
            link_guardian(s, sch["staff"]["guardian"])
        return s
    return _p


def full_marks(sch, section, term, scores):
    """scores: {student: (math_pct, eng_pct)} -> one exam per subject, all marked."""
    for i, code in enumerate(("MATH", "ENG")):
        a = SchoolAssessment.objects.create(tenant=sch["t"], section=section, subject=sch["subj"][code], term=term,
                                            name="Exam", kind="exam", weight=100, max_score=100)
        for student, pcts in scores.items():
            SchoolMark.objects.create(tenant=sch["t"], assessment=a, student=student, score=pcts[i])


def finalize_year(sch, section, scores):
    for term in (sch["t1"], sch["t2"]):
        full_marks(sch, section, term, scores)
        services.finalize_results(section, term, user=sch["staff"]["principal"])


# --------------------------------------------------------------------------- end-to-end
def test_school_end_to_end(client_for, sch, anon, link_guardian):
    """Admit pupil -> class -> attendance -> assessments -> report card -> promotion -> guardian views results."""
    admin = client_for(sch["staff"]["inst_admin"])
    principal = client_for(sch["staff"]["principal"])
    teacher = client_for(sch["staff"]["class_teacher"])
    maths = client_for(sch["staff"]["subject_teacher"])

    # Admission for Grade 1 -> approved -> enrolled and placed in Grade 1A automatically.
    r = anon.post(f"/api/public/{sch['t'].slug}/apply/", {
        "first_name": "Liam", "last_name": "Otieno", "date_of_birth": "2019-05-05", "email": "liam@example.com",
        "requested_level": "x", "target_id": sch["levels"][0].id, "guardian_name": "Jane Otieno",
        "guardian_phone": "+254711000000", "guardian_email": "parent@s.edu", "guardian_relationship": "mother",
        "gender": "male", "phone": "+255712000111", "address": "12 Main St"}, format="json")
    assert r.status_code == 201, r.data
    app_id = admin.get("/api/admissions/").data["results"][0]["id"]
    for st in ("under_review", "approved"):
        assert admin.post(f"/api/admissions/{app_id}/decide/", {"status": st}, format="json").status_code == 200
    r = admin.post(f"/api/admissions/{app_id}/enroll/", {}, format="json")
    assert r.status_code == 201, r.data
    from people.models import Student
    liam = Student.objects.get(pk=r.data["student_id"])
    assert liam.current_level == "Grade 1" and liam.current_section == "A"
    assert services.active_placement(liam).section == sch["g1a"]
    link_guardian(liam, sch["staff"]["guardian"])  # parent portal account

    # Daily register by the class teacher: Liam absent -> guardian notified.
    r = teacher.post("/api/schools/attendance/register/", {"section": sch["g1a"].id, "date": str(SCHOOL_DAY),
                                                           "records": [{"student": liam.id, "status": "absent"}]},
                     format="json")
    assert r.status_code == 200 and r.data["absent"] == 1
    assert Notification.objects.filter(user=sch["staff"]["guardian"], kind="attendance").exists()

    # Teachers set and mark assessments for both terms (only their own subjects).
    for term in (sch["t1"], sch["t2"]):
        for client, code, score in ((maths, "MATH", 72), (teacher, "ENG", 64)):
            a = client.post("/api/schools/assessments/", {
                "section": sch["g1a"].id, "subject": sch["subj"][code].id, "term": term.id, "name": "Exam",
                "kind": "exam", "weight": 100, "max_score": 100}, format="json")
            assert a.status_code == 201, a.data
            m = client.post(f"/api/schools/assessments/{a.data['id']}/marks/",
                            {"marks": [{"student": liam.id, "score": score}]}, format="json")
            assert m.status_code == 200
    wrong = maths.post("/api/schools/assessments/", {"section": sch["g1a"].id, "subject": sch["subj"]["ENG"].id,
                                                     "term": sch["t2"].id, "name": "X", "weight": 10}, format="json")
    assert wrong.status_code == 403

    # Promotion is refused until results are finalized.
    r = principal.post("/api/schools/promotions/decide/", {"student": liam.id, "section": sch["g1a"].id,
                                                           "decision": "promote"}, format="json")
    assert r.status_code == 400 and r.data["code"] == "results_not_finalized"

    # Principal finalizes and publishes; guardian can then see the report card.
    guardian = client_for(sch["staff"]["guardian"])
    for term in (sch["t1"], sch["t2"]):
        body = {"section": sch["g1a"].id, "term": term.id}
        assert principal.post("/api/schools/results/finalize/", body, format="json").status_code == 201
        assert guardian.get("/api/schools/results/").data["count"] == (0 if term == sch["t1"] else 1)
        assert principal.post("/api/schools/results/publish/", body, format="json").status_code == 200
    results = guardian.get("/api/schools/results/").data["results"]
    assert len(results) == 2 and results[0]["average"] == "68.00" and results[0]["position"] == 1
    pdf = guardian.get(f"/api/schools/results/{results[1]['id']}/report-card/")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert liam.documents.filter(kind="report_card").exists()

    # Promote: Grade 1 -> Grade 2 for next year, with enrollment history kept.
    r = principal.post("/api/schools/promotions/decide/", {"student": liam.id, "section": sch["g1a"].id,
                                                           "decision": "promote"}, format="json")
    assert r.status_code == 201 and r.data["to_level_name"] == "Grade 2"
    liam.refresh_from_db()
    assert liam.current_level == "Grade 2"
    history = list(liam.enrollments.order_by("id").values_list("status", "level_label"))
    assert history == [("promoted", "Grade 1"), ("active", "Grade 2")]
    assert liam.enrollments.get(status="active").period == sch["next"]

    # Guardian portal shows the child, attendance and published results.
    kids = guardian.get("/api/schools/children/").data
    assert kids[0]["name"] == liam.person.full_name and len(kids[0]["results"]) == 2
    assert kids[0]["attendance"]["absent"] == 1


# --------------------------------------------------------------------------- classes and timetable
def test_class_capacity_and_moving_keeps_history(client_for, sch, pupil_in, make_student):
    admin = client_for(sch["staff"]["inst_admin"])
    g1b = ClassSection.objects.create(tenant=sch["t"], grade_level=sch["levels"][0], academic_year=sch["year"],
                                      name="B", capacity=1)
    p = pupil_in()
    r = admin.post(f"/api/schools/classes/{g1b.id}/place/", {"student": p.id}, format="json")
    assert r.status_code == 201
    assert list(ClassPlacement.objects.filter(student=p).values_list("status", flat=True)) == ["active", "moved"]
    p.refresh_from_db()
    assert p.current_section == "B"
    other = make_student(sch["t"], first="Q")
    full = admin.post(f"/api/schools/classes/{g1b.id}/place/", {"student": other.id}, format="json")
    assert full.status_code == 400 and full.data["code"] == "class_full"
    again = admin.post(f"/api/schools/classes/{g1b.id}/place/", {"student": p.id}, format="json")
    assert again.data["code"] == "already_placed"
    assert client_for(sch["staff"]["class_teacher"]).post(f"/api/schools/classes/{g1b.id}/place/",
                                                          {"student": other.id}, format="json").status_code == 403


def test_timetable_conflicts(client_for, sch):
    admin = client_for(sch["staff"]["inst_admin"])
    math1, eng1 = ClassAssignment.objects.filter(section=sch["g1a"]).order_by("subject__code").reverse()
    math3 = ClassAssignment.objects.get(section=sch["g3a"], subject__code="MATH")
    base = {"day": 0, "period_no": 1, "start_time": "08:00", "end_time": "08:50"}
    assert admin.post("/api/schools/timetable/", {**base, "assignment": math1.id, "room": "R1"},
                      format="json").status_code == 201
    r = admin.post("/api/schools/timetable/", {**base, "assignment": eng1.id}, format="json")
    assert r.status_code == 400 and r.data["code"] == "class_timetable_conflict"
    r = admin.post("/api/schools/timetable/", {**base, "assignment": math3.id}, format="json")
    assert r.status_code == 400 and r.data["code"] == "teacher_timetable_conflict"
    eng3 = ClassAssignment.objects.get(section=sch["g3a"], subject__code="ENG")
    eng3.teacher = sch["staff"]["other_teacher"]
    eng3.save()
    r = admin.post("/api/schools/timetable/", {**base, "assignment": eng3.id, "room": "r1"}, format="json")
    assert r.status_code == 400 and r.data["code"] == "room_conflict"
    ok = admin.post("/api/schools/timetable/", {**base, "assignment": eng3.id, "room": "R2"}, format="json")
    assert ok.status_code == 201
    assert len(client_for(sch["staff"]["subject_teacher"]).get("/api/schools/timetable/mine/").data) == 1


# --------------------------------------------------------------------------- attendance
def test_attendance_rules(client_for, sch, pupil_in):
    p = pupil_in()
    teacher = client_for(sch["staff"]["class_teacher"])
    maths = client_for(sch["staff"]["subject_teacher"])
    body = {"section": sch["g1a"].id, "date": str(SCHOOL_DAY), "records": [{"student": p.id, "status": "present"}]}
    r = maths.post("/api/schools/attendance/register/", body, format="json")
    assert r.status_code == 400 and r.data["code"] == "not_your_class"  # daily register is the class teacher's
    assert teacher.post("/api/schools/attendance/register/", body, format="json").status_code == 200
    future = teacher.post("/api/schools/attendance/register/", {**body, "date": str(TODAY + timedelta(days=1))},
                          format="json")
    assert future.data["code"] == "future_date"
    saturday = SCHOOL_DAY - timedelta(days=SCHOOL_DAY.weekday() + 2)
    if saturday >= sch["year"].start_date:
        assert teacher.post("/api/schools/attendance/register/", {**body, "date": str(saturday)},
                            format="json").data["code"] == "not_a_school_day"
    excused = teacher.post("/api/schools/attendance/register/",
                           {**body, "records": [{"student": p.id, "status": "excused"}]}, format="json")
    assert excused.data["code"] == "invalid_attendance"
    outsider = pupil_in(sch["g3a"], first="Out")
    r = teacher.post("/api/schools/attendance/register/", {**body, "records": [{"student": outsider.id,
                                                                                "status": "present"}]}, format="json")
    assert r.data["code"] == "invalid_attendance"
    # Per-lesson attendance by the subject teacher, for that day's lesson only.
    math = ClassAssignment.objects.get(section=sch["g1a"], subject__code="MATH")
    lesson = SchoolTimetable.objects.create(tenant=sch["t"], assignment=math, day=SCHOOL_DAY.weekday(), period_no=2,
                                            start_time=time(9, 0), end_time=time(9, 50))
    r = maths.post("/api/schools/attendance/register/", {**body, "lesson": lesson.id,
                                                         "records": [{"student": p.id, "status": "late"}]},
                   format="json")
    assert r.status_code == 200
    assert PupilAttendance.objects.filter(student=p, date=SCHOOL_DAY).count() == 2  # daily + lesson
    wrong_day = SchoolTimetable.objects.create(tenant=sch["t"], assignment=math, day=(SCHOOL_DAY.weekday() + 1) % 5,
                                               period_no=3, start_time=time(10, 0), end_time=time(10, 50))
    r = maths.post("/api/schools/attendance/register/", {**body, "lesson": wrong_day.id}, format="json")
    assert r.data["code"] == "wrong_lesson_day"


def test_absence_notifies_guardian_once_and_alerts_staff(client_for, sch, pupil_in):
    t = sch["t"]
    t.policies = {**t.policies, "attendance_alert_absences": 2}
    t.save()
    p = pupil_in(guardian=True)
    teacher = client_for(sch["staff"]["class_teacher"])
    days = [d for d in services.school_days_between(sch["t2"].start_date, SCHOOL_DAY)][-2:]
    for d in days:
        for _ in range(2):  # re-saving the same absence doesn't notify twice
            teacher.post("/api/schools/attendance/register/", {"section": sch["g1a"].id, "date": str(d), "records": [
                {"student": p.id, "status": "absent"}]}, format="json")
    assert Notification.objects.filter(user=sch["staff"]["guardian"], kind="attendance").count() == 2
    assert Notification.objects.filter(user=sch["staff"]["principal"], title__startswith="Attendance alert").exists()
    summary = client_for(sch["staff"]["guardian"]).get(f"/api/schools/attendance/summary/?student={p.id}").data
    assert summary["absent"] == 2 and summary["attendance_rate"] == 0


# --------------------------------------------------------------------------- marks and results
def test_weighted_results_positions_and_ties(sch, pupil_in):
    a, b, c = pupil_in(first="Ann"), pupil_in(first="Ben"), pupil_in(first="Cy")
    t2, sec = sch["t2"], sch["g1a"]
    hw = SchoolAssessment.objects.create(tenant=sch["t"], section=sec, subject=sch["subj"]["MATH"], term=t2,
                                         name="HW", weight=25, max_score=20)
    ex = SchoolAssessment.objects.create(tenant=sch["t"], section=sec, subject=sch["subj"]["MATH"], term=t2,
                                         name="Exam", weight=75, max_score=100)
    en = SchoolAssessment.objects.create(tenant=sch["t"], section=sec, subject=sch["subj"]["ENG"], term=t2,
                                         name="Exam", weight=100, max_score=50)
    SchoolAssessment.objects.create(tenant=sch["t"], section=sec, subject=sch["subj"]["ENG"], term=t2,
                                    name="Practice", weight=0)  # ungraded homework never blocks results
    for s, (h, e, g) in {a: (20, 80, 40), b: (10, 60, 35), c: (20, 80, 40)}.items():
        for asmt, score in ((hw, h), (ex, e), (en, g)):
            SchoolMark.objects.create(tenant=sch["t"], assessment=asmt, student=s, score=score)
    results, missing = services.compute_results(sec, t2)
    assert not missing
    r = {x["student"]: x for x in results}
    assert r[a]["subjects"][0]["average"] == "80.00" or r[a]["subjects"][1]["average"] == "85.00"
    math_avg = next(s for s in r[a]["subjects"] if s["code"] == "MATH")["average"]
    assert math_avg == "85.00"  # 20/20*25 + 80/100*75
    assert r[a]["average"] == Decimal("82.50") and r[a]["grade"] == "A"
    assert r[a]["position"] == r[c]["position"] == 1 and r[b]["position"] == 3


def test_finalize_requires_complete_marks_then_locks(client_for, sch, pupil_in):
    a, b = pupil_in(first="Ann"), pupil_in(first="Ben")
    principal = client_for(sch["staff"]["principal"])
    maths = client_for(sch["staff"]["subject_teacher"])
    full_marks(sch, sch["g1a"], sch["t2"], {a: (70, 70)})  # Ben has no marks yet
    body = {"section": sch["g1a"].id, "term": sch["t2"].id}
    r = principal.post("/api/schools/results/finalize/", body, format="json")
    assert r.status_code == 400 and r.data["code"] == "marks_incomplete" and len(r.data["fields"]["missing"]) == 2
    for asmt in SchoolAssessment.objects.filter(section=sch["g1a"], term=sch["t2"]):
        SchoolMark.objects.create(tenant=sch["t"], assessment=asmt, student=b, score=40)
    assert client_for(sch["staff"]["class_teacher"]).post("/api/schools/results/finalize/", body,
                                                          format="json").status_code == 403
    assert principal.post("/api/schools/results/finalize/", body, format="json").status_code == 201
    assert principal.post("/api/schools/results/finalize/", body, format="json").data["code"] == "already_finalized"
    asmt = SchoolAssessment.objects.get(section=sch["g1a"], term=sch["t2"], subject__code="MATH")
    locked = maths.post(f"/api/schools/assessments/{asmt.id}/marks/", {"marks": [{"student": b.id, "score": 99}]},
                        format="json")
    assert locked.status_code == 400 and locked.data["code"] == "results_finalized"
    # Reopen is possible until publication.
    assert principal.post("/api/schools/results/reopen/", body, format="json").status_code == 200
    assert maths.post(f"/api/schools/assessments/{asmt.id}/marks/", {"marks": [{"student": b.id, "score": 55}]},
                      format="json").status_code == 200
    principal.post("/api/schools/results/finalize/", body, format="json")
    assert principal.post("/api/schools/results/publish/", body, format="json").status_code == 200
    assert principal.post("/api/schools/results/reopen/", body, format="json").data["code"] == "already_published"


def test_teachers_only_mark_their_own_subject_and_class(client_for, sch, pupil_in):
    p = pupil_in()
    other_section = ClassSection.objects.create(tenant=sch["t"], grade_level=sch["levels"][1],
                                                academic_year=sch["year"], name="A")
    c = client_for(sch["staff"]["subject_teacher"])
    r = c.post("/api/schools/assessments/", {"section": other_section.id, "subject": sch["subj"]["MATH"].id,
                                             "term": sch["t2"].id, "name": "Quiz", "weight": 10}, format="json")
    assert r.status_code == 403
    a = SchoolAssessment.objects.create(tenant=sch["t"], section=sch["g1a"], subject=sch["subj"]["ENG"],
                                        term=sch["t2"], name="Essay", weight=10)
    r = c.post(f"/api/schools/assessments/{a.id}/marks/", {"marks": [{"student": p.id, "score": 5}]}, format="json")
    assert r.status_code == 404  # another teacher's subject isn't even visible
    with pytest.raises(Exception) as e:
        services.save_marks(a, [{"student": p.id, "score": 5}], user=sch["staff"]["subject_teacher"])
    assert e.value.rule_code == "not_your_subject"
    too_high = client_for(sch["staff"]["class_teacher"]).post(
        f"/api/schools/assessments/{a.id}/marks/", {"marks": [{"student": p.id, "score": 101}]}, format="json")
    assert too_high.data["code"] == "invalid_marks"
    bad_term = client_for(sch["staff"]["class_teacher"]).post("/api/schools/assessments/", {
        "section": sch["g1a"].id, "subject": sch["subj"]["ENG"].id, "term": sch["year"].id, "name": "X"},
        format="json")
    assert bad_term.status_code == 400


def test_remarks_by_role(client_for, sch, pupil_in):
    p = pupil_in()
    full_marks(sch, sch["g1a"], sch["t2"], {p: (60, 60)})
    services.finalize_results(sch["g1a"], sch["t2"], user=sch["staff"]["principal"])
    r = TermResult.objects.get(student=p)
    teacher = client_for(sch["staff"]["class_teacher"])
    assert teacher.patch(f"/api/schools/results/{r.id}/", {"teacher_remark": "Works hard"},
                         format="json").status_code == 200
    assert teacher.patch(f"/api/schools/results/{r.id}/", {"principal_remark": "x"}, format="json").status_code == 403
    assert client_for(sch["staff"]["subject_teacher"]).patch(f"/api/schools/results/{r.id}/",
                                                             {"teacher_remark": "x"}, format="json").status_code == 403


# --------------------------------------------------------------------------- promotion
def test_promotion_rules(client_for, sch, pupil_in):
    weak, strong = pupil_in(first="Weak"), pupil_in(first="Strong")
    finalize_year(sch, sch["g1a"], {weak: (30, 40), strong: (80, 90)})
    principal = client_for(sch["staff"]["principal"])
    recs = {r["student"]: r for r in principal.get(
        f"/api/schools/promotions/recommendations/?section={sch['g1a'].id}").data["rows"]}
    assert recs[weak.id]["recommended"] == "repeat" and recs[strong.id]["recommended"] == "promote"
    body = {"section": sch["g1a"].id}
    r = principal.post("/api/schools/promotions/decide/", {**body, "student": weak.id, "decision": "promote"},
                       format="json")
    assert r.status_code == 400 and r.data["code"] == "reason_required"
    r = principal.post("/api/schools/promotions/decide/", {**body, "student": strong.id, "decision": "complete"},
                       format="json")
    assert r.data["code"] == "invalid_decision"  # Grade 1 is not the final grade
    r = principal.post("/api/schools/promotions/decide/", {**body, "student": weak.id, "decision": "repeat"},
                       format="json")
    assert r.status_code == 201
    weak.refresh_from_db()
    assert weak.current_level == "Grade 1" and weak.enrollments.filter(status="repeated").exists()
    again = principal.post("/api/schools/promotions/decide/", {**body, "student": weak.id, "decision": "repeat"},
                           format="json")
    assert again.data["code"] == "already_decided"
    assert client_for(sch["staff"]["class_teacher"]).post(
        "/api/schools/promotions/decide/", {**body, "student": strong.id, "decision": "promote"},
        format="json").status_code == 403


def test_final_grade_completes_school(client_for, sch, pupil_in):
    p = pupil_in(sch["g3a"])
    finalize_year(sch, sch["g3a"], {p: (75, 75)})
    principal = client_for(sch["staff"]["principal"])
    r = principal.post("/api/schools/promotions/decide/", {"student": p.id, "section": sch["g3a"].id,
                                                           "decision": "promote"}, format="json")
    assert r.data["code"] == "invalid_decision"
    r = principal.post("/api/schools/promotions/decide/", {"student": p.id, "section": sch["g3a"].id,
                                                           "decision": "complete"}, format="json")
    assert r.status_code == 201
    p.refresh_from_db()
    assert p.status == "completed" and p.enrollments.get().status == "completed"


def test_withdrawal_ends_class_placement(client_for, sch, pupil_in):
    p = pupil_in()
    e = p.enrollments.get()
    r = client_for(sch["staff"]["inst_admin"]).post(f"/api/enrollments/{e.id}/transfer/",
                                                    {"reason": "Moved city", "destination": "Hill School"},
                                                    format="json")
    assert r.status_code == 200
    assert not ClassPlacement.objects.filter(student=p, status="active").exists()
    assert p not in services.pupils_in(sch["g1a"])


# --------------------------------------------------------------------------- visibility and isolation
def test_families_see_only_their_children_and_published_results(client_for, sch, pupil_in):
    mine = pupil_in(first="Mine", guardian=True, with_login=True)
    other = pupil_in(first="Other")
    full_marks(sch, sch["g1a"], sch["t2"], {mine: (70, 70), other: (50, 50)})
    services.finalize_results(sch["g1a"], sch["t2"], user=sch["staff"]["principal"])
    guardian, pupil = client_for(sch["staff"]["guardian"]), client_for(mine.user)
    r = TermResult.objects.get(student=mine)
    assert guardian.get("/api/schools/results/").data["count"] == 0  # finalized, not yet published
    assert guardian.get(f"/api/schools/results/{r.id}/report-card/").status_code == 404
    asmt = SchoolAssessment.objects.filter(section=sch["g1a"]).first()
    assert guardian.get(f"/api/schools/assessments/{asmt.id}/marks/").data["rows"] == []
    services.publish_results(sch["g1a"], sch["t2"], user=sch["staff"]["principal"])
    assert guardian.get("/api/schools/results/").data["count"] == 1
    assert pupil.get("/api/schools/results/").data["results"][0]["student"] == mine.id
    rows = guardian.get(f"/api/schools/assessments/{asmt.id}/marks/").data["rows"]
    assert [x["student"] for x in rows] == [mine.id]
    other_r = TermResult.objects.get(student=other)
    assert guardian.get(f"/api/schools/results/{other_r.id}/").status_code == 404
    assert [c["id"] for c in guardian.get("/api/schools/children/").data] == [mine.id]
    assert guardian.post("/api/schools/attendance/register/", {}, format="json").status_code == 403
    assert client_for(sch["staff"]["finance_officer"]).get("/api/schools/children/").status_code == 403


def test_teachers_see_only_pupils_they_teach(client_for, sch, pupil_in):
    a = pupil_in(first="Ann")
    third = ClassSection.objects.create(tenant=sch["t"], grade_level=sch["levels"][1], academic_year=sch["year"],
                                        name="Z")
    b = pupil_in(third, first="Ben")
    c = client_for(sch["staff"]["subject_teacher"])
    assert c.get(f"/api/students/{a.id}/").status_code == 200
    assert c.get(f"/api/students/{b.id}/").status_code == 404
    assert c.get(f"/api/schools/classes/{third.id}/roster/").status_code == 403
    assert len(c.get("/api/schools/classes/mine/").data) == 2  # Grade 1A and 3A


def test_universities_and_other_schools_are_refused(client_for, sch, university, make_user):
    reg = make_user("reg@u.edu", "registrar", university)
    assert client_for(reg).get("/api/schools/classes/").status_code == 403
    other = Tenant.objects.create(name="Other School", slug="othersch", type="school", status="active")
    outsider = make_user("admin@other.edu", "inst_admin", other)
    oc = client_for(outsider)
    assert oc.get(f"/api/schools/classes/{sch['g1a'].id}/").status_code == 404
    assert oc.get("/api/schools/classes/").data["count"] == 0
    r = oc.post("/api/schools/classes/", {"grade_level": sch["levels"][0].id, "academic_year": sch["year"].id,
                                          "name": "C"}, format="json")
    assert r.status_code == 400


def test_dashboard_has_attendance_and_pass_rates(client_for, sch, pupil_in):
    a, b = pupil_in(first="Ann"), pupil_in(first="Ben")
    finalize_year(sch, sch["g1a"], {a: (80, 80), b: (30, 30)})
    teacher = client_for(sch["staff"]["class_teacher"])
    teacher.post("/api/schools/attendance/register/", {"section": sch["g1a"].id, "date": str(SCHOOL_DAY), "records": [
        {"student": a.id, "status": "present"}, {"student": b.id, "status": "absent"}]}, format="json")
    d = client_for(sch["staff"]["principal"]).get("/api/schools/dashboard/").data
    assert d["stats"]["pass_rate"] == 50.0 and [x["value"] for x in d["pass_rate_by_term"]] == [50.0, 50.0]
    assert d["attendance_trend"][-1]["value"] == 50.0
    if SCHOOL_DAY == TODAY:
        assert d["stats"]["attendance_today"] == 50.0


def test_school_enrollment_without_free_class_needs_a_choice(client_for, sch):
    from admissions.models import Application
    admin = client_for(sch["staff"]["inst_admin"])
    app = Application.objects.create(tenant=sch["t"], first_name="Z", last_name="Q", date_of_birth=date(2018, 1, 1),
                                     email="z@q.com", requested_level="Grade 2", guardian_name="G Q",
                                     guardian_phone="1", status="approved")
    r = admin.post(f"/api/admissions/{app.id}/enroll/", {}, format="json")
    assert r.status_code == 400 and r.data["code"] == "class_required"
    assert not app.__class__.objects.get(pk=app.id).status == "enrolled"


def test_teacher_clash_on_reallocation_is_rolled_back(client_for, sch):
    """Giving a subject to a teacher who is already busy at that time is refused and nothing changes."""
    from datetime import time

    from school.models import ClassAssignment, SchoolTimetable
    t = sch["t"]
    g1_math = ClassAssignment.objects.get(section=sch["g1a"], subject=sch["subj"]["MATH"])  # subject_teacher
    g3_eng = ClassAssignment.objects.get(section=sch["g3a"], subject=sch["subj"]["ENG"])     # class_teacher
    SchoolTimetable.objects.create(tenant=t, assignment=g1_math, day=0, period_no=1, start_time=time(8), end_time=time(9))
    SchoolTimetable.objects.create(tenant=t, assignment=g3_eng, day=0, period_no=1, start_time=time(8), end_time=time(9))
    r = client_for(sch["staff"]["principal"]).patch(f"/api/schools/allocations/{g3_eng.id}/",
                                                   {"teacher": sch["staff"]["subject_teacher"].id}, format="json")
    assert r.status_code == 400 and r.data["code"] == "teacher_timetable_conflict"
    g3_eng.refresh_from_db()
    assert g3_eng.teacher == sch["staff"]["class_teacher"]  # the failed change was rolled back
