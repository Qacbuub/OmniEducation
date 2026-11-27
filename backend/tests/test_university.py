"""University module: catalogue, registration rules, grading workflow, GPA/CGPA, transcript, clearance."""
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from admissions.models import AcademicPeriod, Application
from finance import services as fin
from university import services
from university.models import (
    AcademicStanding,
    Course,
    CourseOffering,
    CoursePrerequisite,
    CourseRegistration,
    Curriculum,
    CurriculumCourse,
    Department,
    Faculty,
    OfferingMeeting,
    Program,
    Semester,
    TranscriptEntry,
    UniversityAssessment,
)

TODAY = timezone.localdate()


@pytest.fixture
def uni(university, make_user):
    """A small configured university: CS department, program, courses, current semester, staff."""
    t = university
    staff = {r: make_user(f"{r}@u.edu", r, t) for r in ("registrar", "dean", "dept_head", "lecturer", "adviser")}
    staff["lecturer2"] = make_user("lecturer2@u.edu", "lecturer", t)
    fac = Faculty.objects.create(tenant=t, name="Computing", code="COMP", dean=staff["dean"])
    cs = Department.objects.create(tenant=t, faculty=fac, name="Computer Science", code="CS", head=staff["dept_head"])
    other = Department.objects.create(tenant=t, faculty=fac, name="Mathematics", code="MA")
    prog = Program.objects.create(tenant=t, department=cs, name="BSc Computer Science", code="BSCS",
                                  total_credits_required=9)
    c = {code: Course.objects.create(tenant=t, department=cs if code != "MA101" else other, code=code,
                                     title=f"Course {code}", credit_hours=3)
         for code in ("CS101", "CS102", "CS201", "MA101", "CS299")}
    CoursePrerequisite.objects.create(tenant=t, course=c["CS102"], prerequisite=c["CS101"])
    cur = Curriculum.objects.create(tenant=t, program=prog, version="2026", effective_from=date(2026, 1, 1),
                                    elective_credits_required=3)
    for code in ("CS101", "CS102"):
        CurriculumCourse.objects.create(tenant=t, curriculum=cur, course=c[code], category="core")
    CurriculumCourse.objects.create(tenant=t, curriculum=cur, course=c["MA101"], category="elective")
    year = AcademicPeriod.objects.create(tenant=t, name="Year", kind="academic_year", start_date=TODAY - timedelta(400),
                                         end_date=TODAY + timedelta(200), is_current=True)
    past_p = AcademicPeriod.objects.create(tenant=t, name="Past semester", kind="semester", parent=year,
                                           start_date=TODAY - timedelta(300), end_date=TODAY - timedelta(200))
    now_p = AcademicPeriod.objects.create(tenant=t, name="This semester", kind="semester", parent=year,
                                          start_date=TODAY - timedelta(30), end_date=TODAY + timedelta(90),
                                          is_current=True)
    past = Semester.objects.create(tenant=t, period=past_p, registration_start=past_p.start_date,
                                   registration_end=past_p.start_date + timedelta(10),
                                   add_drop_end=past_p.start_date + timedelta(20))
    sem = Semester.objects.create(tenant=t, period=now_p, registration_start=TODAY - timedelta(40),
                                  registration_end=TODAY + timedelta(5), add_drop_end=TODAY + timedelta(10))
    return {"t": t, "staff": staff, "prog": prog, "cur": cur, "c": c, "sem": sem, "past": past, "cs": cs,
            "other": other, "year": year}


def section(uni, code, *, day=0, start=8, capacity=30, lecturer="lecturer", sem=None, room="", name="A"):
    o = CourseOffering.objects.create(tenant=uni["t"], course=uni["c"][code], semester=sem or uni["sem"],
                                      capacity=capacity, section=name, lecturer=uni["staff"][lecturer] if lecturer else None)
    OfferingMeeting.objects.create(tenant=uni["t"], offering=o, day=day, start_time=time(start, 0),
                                   end_time=time(start + 1, 30), room=room)
    return o


@pytest.fixture
def matriculate(uni, make_student, make_user):
    def _m(first="Kim", email=None, with_user=True, adviser=True):
        user = make_user(email or f"{first.lower()}@u.edu", "student", uni["t"]) if with_user else None
        s = make_student(uni["t"], first=first, level="BSc Computer Science", user=user)
        AcademicStanding.objects.create(tenant=uni["t"], student=s, program=uni["prog"], curriculum=uni["cur"],
                                        adviser=uni["staff"]["adviser"] if adviser else None, matriculated_on=TODAY)
        return s
    return _m


def grade_past(uni, student, code, score, sem=None, attempt=1):
    """Give a student an approved past result (registration + transcript entry)."""
    sem = sem or uni["past"]
    o = CourseOffering.objects.filter(semester=sem, course=uni["c"][code]).first() or CourseOffering.objects.create(
        tenant=uni["t"], course=uni["c"][code], semester=sem, capacity=100, section=f"P{attempt}")
    reg = CourseRegistration.objects.create(tenant=uni["t"], student=student, offering=o, status="approved",
                                            attempt_no=attempt)
    letter, points = services.grade_band(uni["t"], score)
    TranscriptEntry.objects.create(tenant=uni["t"], student=student, registration=reg, course=o.course, semester=sem,
                                   course_code=o.course.code, course_title=o.course.title,
                                   credit_hours=o.course.credit_hours, total_score=score, letter=letter,
                                   grade_points=points, attempt_no=attempt)
    services.recompute_standing(student)
    return reg


# --------------------------------------------------------------------------- end-to-end
def test_university_end_to_end(client_for, uni, anon):
    """Configure program/courses -> admit -> register -> prerequisites -> approve grades -> GPA -> transcript."""
    registrar = client_for(uni["staff"]["registrar"])
    hod = client_for(uni["staff"]["dept_head"])
    lect = client_for(uni["staff"]["lecturer"])

    # Configure a new course with a prerequisite and a section with a timetable.
    r = hod.post("/api/universities/courses/", {"department": uni["cs"].id, "code": "cs150", "title": "Web Basics",
                                                "credit_hours": 3, "level": 100}, format="json")
    assert r.status_code == 201 and r.data["code"] == "CS150"
    r = hod.post("/api/universities/prerequisites/", {"course": r.data["id"], "prerequisite": uni["c"]["CS101"].id},
                 format="json")
    assert r.status_code == 201
    r = registrar.post("/api/universities/offerings/", {
        "course": uni["c"]["CS101"].id, "semester": uni["sem"].id, "section": "A", "capacity": 25,
        "lecturer": uni["staff"]["lecturer"].id,
        "meetings": [{"day": 0, "start_time": "09:00", "end_time": "10:30", "room": "LT1"},
                     {"day": 2, "start_time": "09:00", "end_time": "10:30", "room": "LT1"}]}, format="json")
    assert r.status_code == 201, r.data
    cs101 = r.data["id"]

    # Admission: apply online for the program -> offer -> accept -> matriculate.
    app = anon.post(f"/api/public/{uni['t'].slug}/apply/", {
        "first_name": "Ada", "last_name": "Lovelace", "date_of_birth": "2006-12-10", "email": "ada@example.com",
        "requested_level": "x", "target_id": uni["prog"].id, "gender": "male", "phone": "+255712000111", "address": "12 Main St", "national_id": "T-1234567",
        "guardian_name": "Byron L", "guardian_relationship": "father", "guardian_phone": "+255712000999"}, format="json")
    assert app.status_code == 201, app.data
    app_id = registrar.get("/api/admissions/").data["results"][0]["id"]
    for st in ("under_review", "offered"):
        assert registrar.post(f"/api/admissions/{app_id}/decide/", {"status": st}, format="json").status_code == 200
    # The applicant accepts the offer online with their private reference code.
    ref = f"/api/public/{uni['t'].slug}/applications/{app.data['reference_code']}/"
    assert anon.get(ref).data["can_respond"] is True
    r = anon.post(ref + "respond/", {"decision": "accept"}, format="json")
    assert r.status_code == 200 and r.data["status"] == "offer_accepted" and r.data["can_respond"] is False
    again = anon.post(ref + "respond/", {"decision": "decline"}, format="json")
    assert again.status_code == 400 and again.data["code"] == "invalid_transition"
    r = registrar.post(f"/api/admissions/{app_id}/enroll/", {"adviser": uni["staff"]["adviser"].id}, format="json")
    assert r.status_code == 201, r.data
    student_id = r.data["student_id"]
    standing = AcademicStanding.objects.get(student_id=student_id)
    assert standing.program == uni["prog"] and standing.curriculum == uni["cur"]

    # Register: prerequisite rule blocks CS102; CS101 goes to the adviser, who approves it.
    from people.models import Student
    ada = Student.objects.get(pk=student_id)
    assert (ada.person.national_id, ada.person.gender, ada.person.phone) == ("T-1234567", "male", "+255712000111")
    assert ada.guardian_links.get().relationship == "father"  # next of kin carried onto the record
    cs102 = section(uni, "CS102", day=1)
    adviser = client_for(uni["staff"]["adviser"])
    bad = adviser.post("/api/universities/registrations/", {"student": student_id, "offering": cs102.id},
                       format="json")
    assert bad.status_code == 400 and bad.data["code"] == "prerequisite_not_met"
    ok = adviser.post("/api/universities/registrations/", {"student": student_id, "offering": cs101}, format="json")
    assert ok.status_code == 201 and ok.data["status"] == "approved"  # staff registrations are pre-approved

    # Lecturer: assessments (must total 100%), scores, submit.
    a1 = lect.post("/api/universities/assessments/", {"offering": cs101, "name": "Coursework", "kind": "assignment",
                                                      "weight": 40, "max_score": 50}, format="json").data
    too_much = lect.post("/api/universities/assessments/", {"offering": cs101, "name": "Exam", "kind": "exam",
                                                            "weight": 70}, format="json")
    assert too_much.status_code == 400
    a2 = lect.post("/api/universities/assessments/", {"offering": cs101, "name": "Exam", "kind": "exam",
                                                      "weight": 60}, format="json").data
    reg_id = ok.data["id"]
    r = lect.post(f"/api/universities/offerings/{cs101}/scores/", {"scores": [
        {"assessment": a1["id"], "registration": reg_id, "score": 45},
        {"assessment": a2["id"], "registration": reg_id, "score": 80}]}, format="json")
    assert r.status_code == 200
    gb = lect.get(f"/api/universities/offerings/{cs101}/gradebook/").data
    assert Decimal(str(gb["rows"][0]["total"])) == Decimal("84.00")  # 45/50*40 + 80/100*60
    cw = adviser.get("/api/universities/registrations/coursework/", {"student": student_id}).data
    course = next(c for c in cw["courses"] if c["course_code"] == "CS101")
    assert course["earned"] == Decimal("84.00") and course["letter"] is None  # marks visible, grade not yet
    assert [a["score"] for a in course["assessments"]] == [Decimal("45.00"), Decimal("80.00")]
    assert lect.post(f"/api/universities/offerings/{cs101}/submit-grades/").status_code == 200

    # HOD sees the section in the approval queue and approves; transcript & GPA appear.
    assert hod.get("/api/universities/grade-approvals/").data["pending"][0]["id"] == cs101
    assert hod.post(f"/api/universities/offerings/{cs101}/approve-grades/", {}, format="json").status_code == 200
    t = registrar.get(f"/api/universities/transcripts/{student_id}/").data
    assert t["cgpa"] == Decimal("3.30") and t["credits_earned"] == 3  # 84 -> B+ (3.3)
    assert t["semesters"][0]["entries"][0]["letter"] == "B+"
    cw = adviser.get("/api/universities/registrations/coursework/", {"student": student_id}).data
    assert next(c for c in cw["courses"] if c["course_code"] == "CS101")["letter"] == "B+"
    pdf = registrar.get(f"/api/universities/transcripts/{student_id}/pdf/")
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf" and pdf.content[:4] == b"%PDF"
    assert ada.documents.filter(kind="transcript").exists()
    # CS102 is now allowed because CS101 was passed.
    assert services.check_registration(ada, cs102) == 1


# --------------------------------------------------------------------------- registration rules
def test_student_self_registration_needs_adviser_approval(client_for, uni, matriculate):
    s = matriculate()
    o = section(uni, "CS101")
    me = client_for(s.user)
    r = me.post("/api/universities/registrations/", {"offering": o.id}, format="json")
    assert r.status_code == 201 and r.data["status"] == "pending"
    assert me.post(f"/api/universities/registrations/{r.data['id']}/approve/").status_code == 403
    other_adviser = client_for(uni["staff"]["lecturer2"])
    assert other_adviser.post(f"/api/universities/registrations/{r.data['id']}/approve/").status_code == 403
    r2 = client_for(uni["staff"]["adviser"]).post(f"/api/universities/registrations/{r.data['id']}/approve/",
                                                  {"notes": "OK"}, format="json")
    assert r2.status_code == 200 and r2.data["status"] == "approved"


def test_duplicate_registration_rejected(client_for, uni, matriculate):
    s = matriculate()
    a, b = section(uni, "CS101", day=0), section(uni, "CS101", day=1, name="B", lecturer="lecturer2")
    c = client_for(s.user)
    assert c.post("/api/universities/registrations/", {"offering": a.id}, format="json").status_code == 201
    for o in (a, b):
        r = c.post("/api/universities/registrations/", {"offering": o.id}, format="json")
        assert r.status_code == 400 and r.data["code"] == "duplicate_registration"


def test_over_capacity_rejected(client_for, uni, matriculate):
    o = section(uni, "CS101", capacity=1)
    first, second = matriculate("Ann"), matriculate("Ben")
    assert client_for(first.user).post("/api/universities/registrations/", {"offering": o.id},
                                       format="json").status_code == 201
    r = client_for(second.user).post("/api/universities/registrations/", {"offering": o.id}, format="json")
    assert r.status_code == 400 and r.data["code"] == "section_full"


def test_timetable_conflict_rejected(client_for, uni, matriculate):
    s = matriculate()
    a = section(uni, "CS101", day=0, start=9)
    b = section(uni, "MA101", day=0, start=10, lecturer="lecturer2")  # 10:00 overlaps 9:00-10:30
    c = client_for(s.user)
    c.post("/api/universities/registrations/", {"offering": a.id}, format="json")
    r = c.post("/api/universities/registrations/", {"offering": b.id}, format="json")
    assert r.status_code == 400 and r.data["code"] == "timetable_conflict"


def test_credit_limit_and_overload(uni, matriculate):
    t = uni["t"]
    t.policies = {**t.policies, "max_credits": 6, "overload_max_credits": 9, "overload_min_cgpa": 3.5}
    t.save()
    s = matriculate()
    s.tenant.refresh_from_db()
    for i, code in enumerate(("CS101", "MA101")):
        CourseRegistration.objects.create(tenant=t, student=s, offering=section(uni, code, day=i), status="approved")
    third = section(uni, "CS299", day=3)
    with pytest.raises(Exception) as e:
        services.check_registration(s, third)
    assert e.value.rule_code == "credit_limit_exceeded"
    # A strong CGPA unlocks the overload limit.
    grade_past(uni, s, "CS201", 95)
    s.refresh_from_db()
    assert services.check_registration(s, third) == 1


def test_add_drop_window(client_for, uni, matriculate):
    s = matriculate()
    o = section(uni, "CS101")
    c = client_for(s.user)
    reg = c.post("/api/universities/registrations/", {"offering": o.id}, format="json").data
    sem = uni["sem"]
    sem.add_drop_end = TODAY - timedelta(days=1)
    sem.save()
    r = c.post(f"/api/universities/registrations/{reg['id']}/drop/", {}, format="json")
    assert r.status_code == 400 and r.data["code"] == "add_drop_closed"
    r = c.post("/api/universities/registrations/", {"offering": section(uni, "MA101", day=2).id}, format="json")
    assert r.status_code == 400 and r.data["code"] == "registration_closed"


def test_drop_within_window_frees_seat(client_for, uni, matriculate):
    s = matriculate()
    o = section(uni, "CS101", capacity=1)
    c = client_for(s.user)
    reg = c.post("/api/universities/registrations/", {"offering": o.id}, format="json").data
    assert c.post(f"/api/universities/registrations/{reg['id']}/drop/", {}, format="json").data["status"] == "dropped"
    other = matriculate("Zed")
    assert client_for(other.user).post("/api/universities/registrations/", {"offering": o.id},
                                       format="json").status_code == 201


def test_passed_course_cannot_be_repeated_but_failed_can(uni, matriculate):
    s = matriculate()
    grade_past(uni, s, "CS101", 85)
    grade_past(uni, s, "MA101", 30)
    with pytest.raises(Exception) as e:
        services.check_registration(s, section(uni, "CS101"))
    assert e.value.rule_code == "course_already_passed"
    assert services.check_registration(s, section(uni, "MA101", day=2, lecturer="lecturer2")) == 2  # 2nd attempt


def test_lecturer_and_room_double_booking_rejected(client_for, uni):
    c = client_for(uni["staff"]["registrar"])
    section(uni, "CS101", day=0, start=9, room="LT1")
    base = {"semester": uni["sem"].id, "capacity": 20, "section": "A"}
    clash = c.post("/api/universities/offerings/", {**base, "course": uni["c"]["CS102"].id,
                                                    "lecturer": uni["staff"]["lecturer"].id,
                                                    "meetings": [{"day": 0, "start_time": "10:00",
                                                                  "end_time": "11:00", "room": "LT9"}]}, format="json")
    assert clash.status_code == 400 and clash.data["code"] == "lecturer_schedule_conflict"
    room = c.post("/api/universities/offerings/", {**base, "course": uni["c"]["CS102"].id,
                                                   "lecturer": uni["staff"]["lecturer2"].id,
                                                   "meetings": [{"day": 0, "start_time": "10:00",
                                                                 "end_time": "11:00", "room": "lt1"}]}, format="json")
    assert room.status_code == 400 and room.data["code"] == "room_conflict"
    assert not CourseOffering.objects.filter(course=uni["c"]["CS102"]).exists()  # rolled back


def test_prerequisite_cycles_and_self_reference_rejected(client_for, uni):
    c = client_for(uni["staff"]["dept_head"])
    r = c.post("/api/universities/prerequisites/", {"course": uni["c"]["CS101"].id,
                                                    "prerequisite": uni["c"]["CS102"].id}, format="json")
    assert r.status_code == 400 and "prerequisite" in r.data["fields"]  # CS102 already requires CS101
    r = c.post("/api/universities/prerequisites/", {"course": uni["c"]["CS101"].id,
                                                    "prerequisite": uni["c"]["CS101"].id}, format="json")
    assert r.status_code == 400


# --------------------------------------------------------------------------- grades
@pytest.fixture
def graded_section(uni, matriculate):
    s = matriculate()
    o = section(uni, "CS101")
    reg = CourseRegistration.objects.create(tenant=uni["t"], student=s, offering=o, status="approved")
    a = UniversityAssessment.objects.create(tenant=uni["t"], offering=o, name="Final", kind="exam", weight=100)
    services.save_scores(o, [{"assessment": a.id, "registration": reg.id, "score": 72}], user=uni["staff"]["lecturer"])
    return s, o, reg, a


def test_only_assigned_lecturer_enters_and_submits(client_for, uni, graded_section):
    s, o, reg, a = graded_section
    other = client_for(uni["staff"]["lecturer2"])
    r = other.post(f"/api/universities/offerings/{o.id}/scores/",
                   {"scores": [{"assessment": a.id, "registration": reg.id, "score": 99}]}, format="json")
    assert r.status_code == 400 and r.data["code"] == "not_assigned_lecturer"
    assert other.get(f"/api/universities/offerings/{o.id}/gradebook/").status_code == 403
    assert client_for(s.user).post(f"/api/universities/offerings/{o.id}/submit-grades/").status_code == 403


def test_scores_locked_after_submission_and_unauthorised_approvals(client_for, uni, graded_section):
    s, o, reg, a = graded_section
    lect = client_for(uni["staff"]["lecturer"])
    assert lect.post(f"/api/universities/offerings/{o.id}/submit-grades/").status_code == 200
    r = lect.post(f"/api/universities/offerings/{o.id}/scores/",
                  {"scores": [{"assessment": a.id, "registration": reg.id, "score": 100}]}, format="json")
    assert r.status_code == 400 and r.data["code"] == "grades_locked"
    assert lect.post(f"/api/universities/offerings/{o.id}/approve-grades/").status_code == 403  # no permission
    # A department head may only approve courses of their own department.
    uni["cs"].head = None
    uni["cs"].save()
    r = client_for(uni["staff"]["dept_head"]).post(f"/api/universities/offerings/{o.id}/approve-grades/")
    assert r.status_code == 400 and r.data["code"] == "not_authorised_to_approve"
    # Returning requires a reason, then the lecturer can correct and resubmit.
    reg_client = client_for(uni["staff"]["registrar"])
    assert reg_client.post(f"/api/universities/offerings/{o.id}/return-grades/").status_code == 400
    assert reg_client.post(f"/api/universities/offerings/{o.id}/return-grades/", {"notes": "Check exam"},
                           format="json").status_code == 200
    assert lect.post(f"/api/universities/offerings/{o.id}/scores/",
                     {"scores": [{"assessment": a.id, "registration": reg.id, "score": 75}]},
                     format="json").status_code == 200
    assert lect.post(f"/api/universities/offerings/{o.id}/submit-grades/").status_code == 200
    assert reg_client.post(f"/api/universities/offerings/{o.id}/approve-grades/").status_code == 200
    assert TranscriptEntry.objects.get(student=s).letter == "B"


def test_approved_grades_immutable_except_registrar_amendment(client_for, uni, graded_section):
    s, o, reg, a = graded_section
    services.submit_grades(o, user=uni["staff"]["lecturer"])
    services.moderate_grades(o, user=uni["staff"]["dept_head"], approve=True)
    grade = reg.grade
    grade.refresh_from_db()
    lect = client_for(uni["staff"]["lecturer"])
    r = lect.post(f"/api/universities/grades/{grade.id}/amend/", {"total_score": 95, "reason": "x"}, format="json")
    assert r.status_code == 400 and r.data["code"] == "unauthorised_grade_change"
    first = TranscriptEntry.objects.get(student=s)
    with pytest.raises(ValidationError):
        first.save()
    with pytest.raises(ValidationError):
        first.delete()
    r = client_for(uni["staff"]["registrar"]).post(f"/api/universities/grades/{grade.id}/amend/",
                                                   {"total_score": 91, "reason": "Re-mark after appeal"},
                                                   format="json")
    assert r.status_code == 200 and r.data["letter"] == "A"
    entries = TranscriptEntry.objects.filter(student=s).order_by("id")
    assert entries.count() == 2 and entries[1].supersedes_id == entries[0].id  # history kept
    assert services.academic_summary(s)["cgpa"] == Decimal("4.00")
    from core.models import AuditEvent
    assert AuditEvent.objects.filter(action="grade.amended").exists()


def test_students_cannot_see_unapproved_grades(client_for, uni, graded_section):
    s, o, reg, a = graded_section
    services.submit_grades(o, user=uni["staff"]["lecturer"])
    me = client_for(s.user)
    assert me.get("/api/universities/grades/").data["count"] == 0
    assert me.get("/api/universities/registrations/").data["results"][0]["grade"] is None


# --------------------------------------------------------------------------- GPA, standing, audit, clearance
def test_gpa_cgpa_repeat_policy_and_probation(uni, matriculate):
    s = matriculate()
    grade_past(uni, s, "CS101", 92)                       # A  4.0 x3
    grade_past(uni, s, "MA101", 40)                       # F  0.0 x3
    st = AcademicStanding.objects.get(student=s)
    assert st.cgpa == Decimal("2.00") and st.credits_earned == 3 and st.standing == "good"
    grade_past(uni, s, "CS102", 55)                       # D  1.0 x3 -> (12+0+3)/9 = 1.67
    st.refresh_from_db()
    assert st.cgpa == Decimal("1.67") and st.standing == "probation"
    grade_past(uni, s, "MA101", 78, sem=uni["sem"], attempt=2)  # repeat: B 3.0 replaces F
    st.refresh_from_db()
    assert st.cgpa == Decimal("2.67") and st.credits_earned == 9 and st.standing == "good"
    summary = services.academic_summary(s)
    assert len(summary["entries"]) == 4 and len(summary["counted_ids"]) == 3
    assert summary["semesters"][0]["gpa"] == Decimal("1.67")  # semester GPA counts every attempt in that term


def test_degree_audit_and_graduation_clearance(client_for, uni, matriculate):
    s = matriculate()
    registrar = client_for(uni["staff"]["registrar"])
    r = client_for(s.user).post("/api/universities/clearances/", {}, format="json")
    assert r.status_code == 400 and r.data["code"] == "not_eligible"
    for code in ("CS101", "CS102", "MA101"):
        grade_past(uni, s, code, 80)
    audit = registrar.get(f"/api/universities/degree-audit/{s.id}/").data
    assert audit["eligible"] and audit["credits_earned"] == 9
    # Outstanding fees block clearance.
    inv = fin.create_invoice(tenant=uni["t"], student=s, lines=[{"description": "Tuition", "amount": 500}],
                             due_date=TODAY + timedelta(days=5))
    req = client_for(s.user).post("/api/universities/clearances/", {}, format="json")
    assert req.status_code == 201
    hold = registrar.post(f"/api/universities/clearances/{req.data['id']}/clear/", {}, format="json")
    assert hold.status_code == 400 and hold.data["code"] == "fees_outstanding"
    fin.record_payment(invoice=inv, amount=500, method="cash", user=uni["staff"]["registrar"])
    done = registrar.post(f"/api/universities/clearances/{req.data['id']}/clear/", {}, format="json")
    assert done.status_code == 200 and done.data["status"] == "cleared"
    s.refresh_from_db()
    assert s.status == "graduated"


# --------------------------------------------------------------------------- isolation and permissions
def test_school_users_and_other_universities_are_refused(client_for, uni, school, make_user, matriculate):
    teacher = make_user("t@s.edu", "class_teacher", school)
    assert client_for(teacher).get("/api/universities/courses/").status_code == 403
    from core.models import Tenant
    other = Tenant.objects.create(name="Other U", slug="otheru", type="university", status="active")
    outsider = make_user("reg@other.edu", "registrar", other)
    o = section(uni, "CS101")
    oc = client_for(outsider)
    assert oc.get(f"/api/universities/offerings/{o.id}/").status_code == 404
    assert oc.get("/api/universities/offerings/").data["count"] == 0
    s = matriculate()
    assert oc.get(f"/api/universities/transcripts/{s.id}/").status_code == 404
    r = oc.post("/api/universities/offerings/", {"course": uni["c"]["CS101"].id, "semester": uni["sem"].id,
                                                 "capacity": 5}, format="json")
    assert r.status_code == 400  # foreign keys from another tenant are rejected


def test_record_visibility_by_role(client_for, uni, matriculate):
    a, b = matriculate("Ann"), matriculate("Ben", adviser=False)
    o = section(uni, "CS101")
    CourseRegistration.objects.create(tenant=uni["t"], student=a, offering=o, status="approved")
    CourseRegistration.objects.create(tenant=uni["t"], student=b, offering=section(uni, "MA101", day=3,
                                                                                    lecturer="lecturer2"),
                                      status="approved")
    assert client_for(a.user).get("/api/universities/registrations/").data["count"] == 1
    assert client_for(a.user).get(f"/api/universities/transcripts/{b.id}/").status_code == 404
    lect = client_for(uni["staff"]["lecturer"])
    assert {r["student"] for r in lect.get("/api/universities/registrations/").data["results"]} == {a.id}
    assert lect.get(f"/api/students/{a.id}/").status_code == 200   # teaches Ann
    assert lect.get(f"/api/students/{b.id}/").status_code == 404   # doesn't teach Ben
    adviser = client_for(uni["staff"]["adviser"])
    assert adviser.get(f"/api/universities/degree-audit/{a.id}/").status_code == 200
    assert adviser.get(f"/api/universities/degree-audit/{b.id}/").status_code == 404
    # Students can't register someone else.
    r = client_for(a.user).post("/api/universities/registrations/", {"student": b.id, "offering": o.id},
                                format="json")
    assert r.status_code in (403, 404)


def test_catalogue_is_read_only_for_lecturers_and_students(client_for, uni, matriculate):
    s = matriculate()
    for user in (uni["staff"]["lecturer"], s.user):
        c = client_for(user)
        assert c.get("/api/universities/programs/").status_code == 200
        r = c.post("/api/universities/courses/", {"department": uni["cs"].id, "code": "X1", "title": "X",
                                                  "credit_hours": 3}, format="json")
        assert r.status_code == 403


def test_dashboard_includes_university_metrics(client_for, uni, matriculate):
    s = matriculate()
    grade_past(uni, s, "CS101", 40)
    CourseRegistration.objects.create(tenant=uni["t"], student=s, offering=section(uni, "MA101"), status="approved")
    d = client_for(uni["staff"]["registrar"]).get("/api/universities/dashboard/").data
    assert d["stats"]["registrations"] == 1 and d["stats"]["on_probation"] == 1
    assert d["course_demand"][0]["capacity"] == 30 and sum(b["value"] for b in d["gpa_distribution"]) == 1


def test_semester_settings_validation(uni):
    sem = Semester(tenant=uni["t"], period=uni["year"], registration_start=TODAY, registration_end=TODAY,
                   add_drop_end=TODAY)
    with pytest.raises(ValidationError):
        sem.clean()
    sem = Semester(tenant=uni["t"], period=uni["sem"].period, registration_start=TODAY,
                   registration_end=TODAY - timedelta(1), add_drop_end=TODAY)
    with pytest.raises(ValidationError):
        sem.clean()


def test_public_form_lists_programs_and_offer_can_be_declined(uni, anon, client_for):
    form = anon.get(f"/api/public/{uni['t'].slug}/apply/").data
    assert form["type"] == "university" and uni["prog"].id in [o["id"] for o in form["options"]]
    assert uni["t"].slug in [i["slug"] for i in anon.get("/api/public/institutions/").data]
    app = anon.post(f"/api/public/{uni['t'].slug}/apply/", {
        "first_name": "Grace", "last_name": "Hopper", "date_of_birth": "2006-12-09", "email": "grace@example.com",
        "target_id": uni["prog"].id, "gender": "female", "phone": "+255712000222", "address": "1 Navy Rd",
        "guardian_name": "W Murray", "guardian_relationship": "father", "guardian_phone": "+255712000333"},
        format="json")
    assert app.status_code == 201, app.data
    ref = f"/api/public/{uni['t'].slug}/applications/{app.data['reference_code'].lower()}/"
    early = anon.post(ref + "respond/", {"decision": "accept"}, format="json")
    assert early.status_code == 400  # no offer yet
    registrar = client_for(uni["staff"]["registrar"])
    app_id = Application.objects.get(reference_code=app.data["reference_code"]).id
    for st in ("under_review", "offered"):
        registrar.post(f"/api/admissions/{app_id}/decide/", {"status": st}, format="json")
    assert anon.post(ref + "respond/", {"decision": "maybe"}, format="json").status_code == 400
    r = anon.post(ref + "respond/", {"decision": "decline"}, format="json")
    assert r.status_code == 200 and r.data["status"] == "offer_declined"
