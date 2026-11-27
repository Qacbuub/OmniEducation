from datetime import date

from admissions.models import Application, Enrollment
from people.models import GuardianLink, Student

APPLICANT = {"first_name": "Liam", "last_name": "Otieno", "date_of_birth": "2019-05-05", "email": "liam@example.com",
             "requested_level": "Grade 1", "guardian_name": "Jane Otieno", "guardian_phone": "+254711000000",
             "guardian_relationship": "mother", "gender": "male", "phone": "+254711000001",
             "address": "Plot 4, Nairobi"}


def test_public_online_application(anon, school):
    r = anon.post(f"/api/public/{school.slug}/apply/", APPLICANT, format="json")
    assert r.status_code == 201 and r.data["reference_code"]
    status = anon.get(f"/api/public/{school.slug}/applications/{r.data['reference_code']}/")
    assert status.data["status"] == "submitted"
    dup = anon.post(f"/api/public/{school.slug}/apply/", APPLICANT, format="json")
    assert dup.status_code == 400 and "email" in dup.data["fields"]


def test_application_requires_full_details(anon, school):
    data = {k: v for k, v in APPLICANT.items() if k not in ("gender", "phone", "address")}
    r = anon.post(f"/api/public/{school.slug}/apply/", {**data, "guardian_phone": "abc"}, format="json")
    assert r.status_code == 400
    assert {"gender", "phone", "address", "guardian_phone"} <= set(r.data["fields"])


def test_school_application_requires_guardian(anon, school):
    data = {**APPLICANT, "guardian_name": "", "guardian_phone": ""}
    r = anon.post(f"/api/public/{school.slug}/apply/", data, format="json")
    assert r.status_code == 400 and "guardian_name" in r.data["fields"]


def test_school_admission_workflow_end_to_end(client_for, make_user, school, school_year):
    """Applicant -> approved admission -> enrolled pupil with guardian link and enrollment history."""
    admin = make_user("admin@s.edu", "inst_admin", school)
    c = client_for(admin)
    app = c.post("/api/admissions/", {**APPLICANT, "intake_period": school_year.id}, format="json").data

    early = c.post(f"/api/admissions/{app['id']}/enroll/", {}, format="json")
    assert early.status_code == 400 and early.data["code"] == "invalid_transition"
    skip = c.post(f"/api/admissions/{app['id']}/decide/", {"status": "approved"}, format="json")
    assert skip.status_code == 400  # must be reviewed first
    assert c.post(f"/api/admissions/{app['id']}/decide/", {"status": "under_review"}, format="json").status_code == 200
    r = c.post(f"/api/admissions/{app['id']}/decide/", {"status": "approved", "notes": "Interview passed"},
               format="json")
    assert r.data["status"] == "approved"

    r = c.post(f"/api/admissions/{app['id']}/enroll/", {}, format="json")
    assert r.status_code == 201
    student = Student.objects.get(pk=r.data["student_id"])
    assert student.student_no.startswith(f"{school.student_id_prefix}-")
    assert student.current_level == "Grade 1"
    assert GuardianLink.objects.filter(student=student, is_primary=True).exists()
    assert Enrollment.objects.filter(student=student, status="active", period=school_year).exists()
    assert Application.objects.get(pk=app["id"]).status == "enrolled"
    again = c.post(f"/api/admissions/{app['id']}/enroll/", {}, format="json")
    assert again.status_code == 400  # cannot enroll twice


def test_university_requires_offer_acceptance_before_matriculation(client_for, make_user, university):
    registrar = make_user("reg@u.edu", "registrar", university)
    c = client_for(registrar)
    app = c.post("/api/admissions/", {"first_name": "Sofia", "last_name": "Reyes", "date_of_birth": "2007-02-02",
                                      "email": "sofia@example.com", "requested_level": "BSc Computer Science",
                                      "gender": "female", "phone": "+255712000222", "address": "Dar es Salaam",
                                      "guardian_name": "Maria Reyes", "guardian_relationship": "mother",
                                      "guardian_phone": "+255712000333"},
                 format="json").data
    c.post(f"/api/admissions/{app['id']}/decide/", {"status": "under_review"}, format="json")
    bad = c.post(f"/api/admissions/{app['id']}/decide/", {"status": "approved"}, format="json")
    assert bad.status_code == 400  # universities make offers, not approvals
    c.post(f"/api/admissions/{app['id']}/decide/", {"status": "offered"}, format="json")
    assert c.post(f"/api/admissions/{app['id']}/enroll/", {}, format="json").status_code == 400
    c.post(f"/api/admissions/{app['id']}/decide/", {"status": "offer_accepted"}, format="json")
    assert c.post(f"/api/admissions/{app['id']}/enroll/", {}, format="json").status_code == 201


def test_teacher_cannot_decide_applications(client_for, make_user, school):
    teacher = make_user("t@s.edu", "class_teacher", school)
    app = Application.objects.create(tenant=school, first_name="A", last_name="B", date_of_birth=date(2019, 1, 1),
                                     email="a@b.c", requested_level="Grade 1", guardian_name="G", guardian_phone="1")
    r = client_for(teacher).post(f"/api/admissions/{app.id}/decide/", {"status": "under_review"}, format="json")
    assert r.status_code == 403


def test_withdrawal_ends_enrollment(client_for, make_user, make_student, school, school_year):
    admin = make_user("admin@s.edu", "inst_admin", school)
    s = make_student(school)
    e = Enrollment.objects.create(tenant=school, student=s, period=school_year, level_label="Grade 4",
                                  start_date=date(2026, 1, 5))
    r = client_for(admin).post(f"/api/enrollments/{e.id}/withdraw/", {"reason": "Family relocated"}, format="json")
    assert r.status_code == 200 and r.data["status"] == "withdrawn"
    s.refresh_from_db()
    assert s.status == "withdrawn"
    again = client_for(admin).post(f"/api/enrollments/{e.id}/transfer/", {"reason": "x"}, format="json")
    assert again.status_code == 400


def test_academic_period_rules(client_for, make_user, school, school_year):
    admin = make_user("admin@s.edu", "inst_admin", school)
    c = client_for(admin)
    sem = c.post("/api/academic-periods/", {"name": "Sem 1", "kind": "semester", "parent": school_year.id,
                                            "start_date": "2026-01-10", "end_date": "2026-04-01"}, format="json")
    assert sem.status_code == 400  # schools use terms
    outside = c.post("/api/academic-periods/", {"name": "Term X", "kind": "term", "parent": school_year.id,
                                                "start_date": "2025-12-01", "end_date": "2026-03-01"}, format="json")
    assert outside.status_code == 400
    ok = c.post("/api/academic-periods/", {"name": "Term 1", "kind": "term", "parent": school_year.id,
                                           "start_date": "2026-01-05", "end_date": "2026-04-02"}, format="json")
    assert ok.status_code == 201


PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82")


def _approved_app(c, school_year, **extra):
    app = c.post("/api/admissions/", {**APPLICANT, "intake_period": school_year.id, **extra}, format="json").data
    for s in ("under_review", "approved"):
        assert c.post(f"/api/admissions/{app['id']}/decide/", {"status": s}, format="json").status_code == 200
    return app


def test_enrol_with_photo_and_fee_plan(client_for, make_user, school, school_year, tmp_path, settings):
    """The applicant photo becomes the student photo, and a fee plan is billed in the same step."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from finance.models import FeePlan, FeePlanItem, Invoice
    settings.MEDIA_ROOT = tmp_path
    registrar = make_user("reg@s.edu", "registrar", school)
    c = client_for(registrar)
    app = _approved_app(c, school_year)
    up = c.post(f"/api/admissions/{app['id']}/photo/", {"photo": SimpleUploadedFile("p.png", PNG)}, format="multipart")
    assert up.status_code == 200 and up.data["photo_url"]
    plan = FeePlan.objects.create(tenant=school, name="Term 1 – Grade 1", applies_to="Grade 1")
    FeePlanItem.objects.create(tenant=school, plan=plan, description="Tuition", amount="15000")
    FeePlanItem.objects.create(tenant=school, plan=plan, description="Lunch", amount="4500")

    opts = c.get(f"/api/admissions/{app['id']}/billing-options/").data
    assert opts["can_bill_custom"] is False and opts["plans"][0]["matches"] and opts["plans"][0]["total"] == "19500.00"
    custom = c.post(f"/api/admissions/{app['id']}/enroll/",
                    {"billing": {"mode": "custom", "items": [{"description": "Registration", "amount": 500}]}},
                    format="json")
    assert custom.status_code == 400 and custom.data["code"] == "permission_denied"  # finance staff only
    assert not Student.objects.filter(application_id=app["id"]).exists()  # nothing half-done

    r = c.post(f"/api/admissions/{app['id']}/enroll/", {"billing": {"mode": "plan", "plan": plan.id}}, format="json")
    assert r.status_code == 201 and r.data["invoice_total"] == "19500.00"
    student = Student.objects.get(pk=r.data["student_id"])
    assert student.photo and student.photo.read() == PNG
    assert Invoice.objects.get(number=r.data["invoice"]).student == student


def test_finance_admin_can_bill_custom_amount_at_enrolment(client_for, make_user, school, school_year):
    from finance.models import Invoice
    admin = client_for(make_user("adm2@s.edu", "inst_admin", school))
    app = _approved_app(admin, school_year, email="mia@example.com", first_name="Mia")
    bad = admin.post(f"/api/admissions/{app['id']}/enroll/",
                     {"billing": {"mode": "custom", "items": [{"description": "Uniform", "amount": -5}]}}, format="json")
    assert bad.status_code == 400 and not Student.objects.filter(application_id=app["id"]).exists()
    r = admin.post(f"/api/admissions/{app['id']}/enroll/",
                   {"billing": {"mode": "custom", "items": [{"description": "Registration fee", "amount": "5000"},
                                                            {"description": "Uniform", "amount": "3000"}]}},
                   format="json")
    assert r.status_code == 201
    inv = Invoice.objects.get(number=r.data["invoice"])
    assert inv.total == 8000 and [ln.description for ln in inv.lines.all()] == ["Registration fee", "Uniform"]


def test_public_school_form_lists_grade_levels(anon, school):
    from school.models import GradeLevel
    g = GradeLevel.objects.create(tenant=school, name="Grade 1", order=1)
    form = anon.get(f"/api/public/{school.slug}/apply/").data
    assert form["institution"] == school.name and form["options"] == [{"id": g.id, "name": "Grade 1"}]
    r = anon.post(f"/api/public/{school.slug}/apply/", {**APPLICANT, "target_id": g.id}, format="json")
    assert r.status_code == 201
    status = anon.get(f"/api/public/{school.slug}/applications/{r.data['reference_code']}/").data
    assert status["requested_level"] == "Grade 1" and status["can_upload"] and not status["can_respond"]
    assert anon.get(f"/api/public/{school.slug}/applications/NOPE123/").status_code == 404


def test_applicant_adds_photo_and_documents_until_decided(anon, client_for, make_user, school, tmp_path, settings):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from tests.test_people_photo import PNG
    settings.MEDIA_ROOT = tmp_path
    ref = anon.post(f"/api/public/{school.slug}/apply/", APPLICANT, format="json").data["reference_code"]
    base = f"/api/public/{school.slug}/applications/{ref}/"
    fake = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
    assert anon.post(base + "photo/", {"photo": fake}, format="multipart").status_code == 400
    ok = anon.post(base + "photo/", {"photo": SimpleUploadedFile("me.png", PNG, content_type="image/png")},
                   format="multipart")
    assert ok.status_code == 201 and ok.data["has_photo"] is True
    # An applicant cannot label their upload as an official document such as a receipt.
    doc = anon.post(base + "documents/", {"file": SimpleUploadedFile("r.pdf", b"%PDF-1.4"), "kind": "receipt"},
                    format="multipart")
    assert doc.status_code == 201
    app = Application.objects.get(reference_code=ref)
    assert app.documents.get().kind == "supporting"
    admin = client_for(make_user("adm@s.edu", "inst_admin", school))
    admin.post(f"/api/admissions/{app.id}/decide/", {"status": "rejected"}, format="json")
    late = anon.post(base + "documents/", {"file": SimpleUploadedFile("late.pdf", b"%PDF-1.4")}, format="multipart")
    assert late.status_code == 404
    assert anon.get(base).data["can_upload"] is False


def test_staff_correct_an_applications_details(client_for, make_user, school):
    admin = client_for(make_user("adm@s.edu", "inst_admin", school))
    app = admin.post("/api/admissions/", APPLICANT, format="json").data
    r = admin.patch(f"/api/admissions/{app['id']}/", {**APPLICANT, "last_name": "Otieno-Kamau",
                                                       "phone": "+254700123456"}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["full_name"].endswith("Otieno-Kamau") and r.data["requested_level"] == "Grade 1"
    bad = admin.patch(f"/api/admissions/{app['id']}/", {"phone": "call me"}, format="json")
    assert bad.status_code == 400 and "phone" in bad.data["fields"]
