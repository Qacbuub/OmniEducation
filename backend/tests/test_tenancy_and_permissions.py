"""Security: tenant isolation and role restrictions (acceptance test 'Security' in the brief)."""
from django.core import mail

from core.models import AuditEvent, Invitation, Tenant, User
from tests.test_finance import _invoice, _pay


def test_cross_tenant_student_access_is_not_found(client_for, make_user, make_student, school, university):
    uni_student = make_student(university, "Uni", "Student", "BSc CS")
    school_admin = make_user("admin@s.edu", "inst_admin", school)
    c = client_for(school_admin)
    assert c.get(f"/api/students/{uni_student.id}/").status_code == 404
    assert c.patch(f"/api/students/{uni_student.id}/", {"first_name": "Hacked"}, format="json").status_code == 404
    ids = [s["id"] for s in c.get("/api/students/").data["results"]]
    assert uni_student.id not in ids


def test_cannot_reference_other_tenants_records(client_for, make_user, make_student, school, university):
    """Foreign keys in request bodies are tenant-checked too, not just URLs."""
    uni_student = make_student(university)
    admin = make_user("admin@s.edu", "inst_admin", school)
    finance = make_user("fin@s.edu", "finance_officer", school)
    r = client_for(admin).post("/api/emergency-contacts/", {"student": uni_student.id, "name": "X",
                                                             "relationship": "aunt", "phone": "1"}, format="json")
    assert r.status_code == 400 and "student" in r.data["fields"]
    r = client_for(finance).post("/api/fees/invoices/", {"student": uni_student.id,
                                                          "lines": [{"description": "Fee", "amount": "10"}]},
                                 format="json")
    assert r.status_code == 400 and "student" in r.data["fields"]


def test_tenant_is_taken_from_the_user_not_the_body(client_for, make_user, school, university):
    admin = make_user("admin@s.edu", "inst_admin", school)
    r = client_for(admin).post("/api/students/", {"first_name": "A", "last_name": "B", "tenant": university.id},
                               format="json")
    assert r.status_code == 201
    from people.models import Student

    assert Student.objects.get(pk=r.data["id"]).tenant == school


def test_platform_admin_cannot_browse_student_records(client_for, make_user, make_student, school):
    make_student(school)
    platform = make_user("root@omni.app", "super_admin")
    assert client_for(platform).get("/api/students/").status_code == 403


def test_platform_admin_creates_institution_and_invites_admin(client_for, make_user):
    platform = make_user("root@omni.app", "super_admin")
    r = client_for(platform).post("/api/tenants/", {"name": "New School", "slug": "new-school", "type": "school",
                                                    "admin_email": "head@new.edu"}, format="json")
    assert r.status_code == 201
    t = Tenant.objects.get(slug="new-school")
    assert t.grading_scale and t.policies["pass_mark"] == 50
    assert Invitation.objects.filter(tenant=t, email="head@new.edu", role__code="inst_admin").exists()
    assert any("head@new.edu" in m.to for m in mail.outbox)
    assert AuditEvent.objects.filter(action="tenant.created", tenant=t).exists()


def test_platform_admin_deletes_institution_with_all_its_data(client_for, make_user, make_student, school, university):
    from people.models import Student

    platform = client_for(make_user("root@omni.app", "super_admin"))
    admin = make_user("admin@s.edu", "inst_admin", school)
    pupil = make_student(school)
    other = make_student(university)
    inv = _invoice(client_for(admin), pupil)  # invoices and payments protect students: deletion must still work
    _pay(client_for(admin), inv["id"], "40")

    # Only platform admins, and only with the exact name typed.
    assert client_for(admin).delete(f"/api/tenants/{school.id}/", {"confirm_name": school.name},
                                    format="json").status_code == 403
    wrong = platform.delete(f"/api/tenants/{school.id}/", {"confirm_name": "sunrise"}, format="json")
    assert wrong.status_code == 400 and Tenant.objects.filter(pk=school.pk).exists()

    r = platform.delete(f"/api/tenants/{school.id}/", {"confirm_name": f"  {school.name.lower()} ",
                                                         "reason": "Test institution"}, format="json")
    assert r.status_code == 200 and r.data["rows_deleted"] > 0
    assert not Tenant.objects.filter(pk=school.pk).exists()
    assert not Student.objects.filter(pk=pupil.pk).exists() and not User.objects.filter(email="admin@s.edu").exists()
    assert Student.objects.filter(pk=other.pk).exists()  # other institutions are untouched
    assert AuditEvent.objects.filter(action="tenant.deleted", tenant=None, changes__name=school.name,
                                     changes__reason="Test institution").exists()


def test_only_platform_admin_can_create_institutions(client_for, make_user, school):
    admin = make_user("admin@s.edu", "inst_admin", school)
    r = client_for(admin).post("/api/tenants/", {"name": "X", "slug": "xxx", "type": "school",
                                                 "admin_email": "a@x.edu"}, format="json")
    assert r.status_code == 403


def test_school_user_cannot_use_university_dashboard(client_for, make_user, school):
    principal = make_user("p@s.edu", "principal", school)
    assert client_for(principal).get("/api/schools/dashboard/").status_code == 200
    assert client_for(principal).get("/api/universities/dashboard/").status_code == 403


def test_teacher_cannot_create_or_edit_students(client_for, make_user, make_student, school):
    teacher = make_user("t@s.edu", "class_teacher", school)
    s = make_student(school)
    c = client_for(teacher)
    assert c.post("/api/students/", {"first_name": "A", "last_name": "B"}, format="json").status_code == 403
    assert c.patch(f"/api/students/{s.id}/", {"first_name": "Z"}, format="json").status_code == 403


def test_guardian_sees_only_linked_children(client_for, make_user, make_student, link_guardian, school):
    mine = make_student(school, "My", "Child")
    other = make_student(school, "Other", "Child")
    parent = make_user("parent@s.edu", "guardian", school)
    link_guardian(mine, parent)
    c = client_for(parent)
    ids = [s["id"] for s in c.get("/api/students/").data["results"]]
    assert ids == [mine.id]
    assert c.get(f"/api/students/{other.id}/").status_code == 404
    assert c.get(f"/api/students/{mine.id}/").status_code == 200


def test_pupil_sees_only_self(client_for, make_user, make_student, school):
    pupil_user = make_user("kid@s.edu", "pupil", school)
    me = make_student(school, user=pupil_user)
    make_student(school, "Someone", "Else")
    ids = [s["id"] for s in client_for(pupil_user).get("/api/students/").data["results"]]
    assert ids == [me.id]


def test_students_with_history_are_withdrawn_not_deleted(client_for, make_user, make_student, school):
    from people.models import Person, Student
    from tests.test_finance import _invoice, _pay

    admin = client_for(make_user("admin@s.edu", "inst_admin", school))
    fin = client_for(make_user("fin@s.edu", "finance_officer", school))
    paid = make_student(school, "Has", "History")
    assert _pay(fin, _invoice(fin, paid)["id"], "10").status_code == 201
    r = admin.delete(f"/api/students/{paid.id}/")
    assert r.status_code == 400 and r.data["code"] == "has_history" and "Withdrawn" in r.data["message"]
    assert Student.objects.filter(pk=paid.pk).exists()

    # A profile created by mistake (no history; an unpaid invoice is fine) is removed with its account.
    kid = make_user("oops@s.edu", "pupil", school)
    oops = make_student(school, "Made", "Mistake", user=kid)
    _invoice(fin, oops)
    person_id = oops.person_id
    assert admin.delete(f"/api/students/{oops.id}/").status_code == 204
    assert not Student.objects.filter(pk=oops.pk).exists() and not Person.objects.filter(pk=person_id).exists()
    assert not User.objects.filter(email="oops@s.edu").exists()
    assert client_for(make_user("t@s.edu", "class_teacher", school)).delete(
        f"/api/students/{paid.id}/").status_code == 403


def test_staff_application_and_platform_invitation_deletes(client_for, make_user, school):
    from admissions.models import AcademicPeriod, Application
    from people.models import Person, Staff
    from school.models import ClassSection, GradeLevel

    def profile(user, no):
        p = Person.objects.create(tenant=school, first_name=user.first_name, last_name="Test", email=user.email)
        return Staff.objects.create(tenant=school, person=p, user=user, staff_no=no)

    admin_user = make_user("admin@s.edu", "inst_admin", school)
    admin = client_for(admin_user)
    teacher = make_user("teach@s.edu", "class_teacher", school)
    staff = profile(teacher, "STF-0002")
    year = AcademicPeriod.objects.create(tenant=school, name="2026", kind="academic_year",
                                         start_date="2026-01-01", end_date="2026-12-31", is_current=True)
    g = GradeLevel.objects.create(tenant=school, name="Grade 1", order=1)
    sec = ClassSection.objects.create(tenant=school, grade_level=g, academic_year=year, name="A",
                                      homeroom_teacher=teacher)
    assert admin.delete(f"/api/staff/{staff.id}/").status_code == 204
    assert not User.objects.filter(email="teach@s.edu").exists()
    sec.refresh_from_db()
    assert sec.homeroom_teacher is None  # the class stays, now without a class teacher
    own = profile(admin_user, "STF-0001")
    assert admin.delete(f"/api/staff/{own.id}/").data["code"] == "self_delete"

    from tests.test_admissions import APPLICANT
    app_id = admin.post("/api/admissions/", APPLICANT, format="json").data["id"]
    assert admin.delete(f"/api/admissions/{app_id}/", {"reason": "Duplicate"}, format="json").status_code == 204
    assert AuditEvent.objects.get(action="application.deleted").changes["reason"] == "Duplicate"
    assert not Application.objects.filter(pk=app_id).exists()

    platform = client_for(make_user("root@omni.app", "super_admin"))
    t = platform.post("/api/tenants/", {"name": "Tmp School", "slug": "tmp-school", "type": "school",
                                        "admin_email": "head@tmp.edu"}, format="json").data
    inv = Invitation.objects.get(email="head@tmp.edu")
    assert admin.delete(f"/api/platform/invitations/{inv.id}/").status_code == 403
    assert platform.delete(f"/api/platform/invitations/{inv.id}/").status_code == 204
    assert not Invitation.objects.filter(pk=inv.pk).exists() and t["id"]


def test_deleting_a_record_still_in_use_explains_why(client_for, make_user, school):
    from admissions.models import AcademicPeriod
    from school.models import ClassSection, GradeLevel

    admin = client_for(make_user("admin@s.edu", "inst_admin", school))
    year = AcademicPeriod.objects.create(tenant=school, name="2026", kind="academic_year",
                                         start_date="2026-01-01", end_date="2026-12-31", is_current=True)
    g = GradeLevel.objects.create(tenant=school, name="Grade 1", order=1)
    ClassSection.objects.create(tenant=school, grade_level=g, academic_year=year, name="A")
    r = admin.delete(f"/api/academic-periods/{year.id}/")
    assert r.status_code == 409 and r.data["code"] == "in_use" and "class section" in r.data["message"], r.data
    assert AcademicPeriod.objects.filter(pk=year.pk).exists()
    assert not AuditEvent.objects.filter(action__endswith=".deleted").exists()  # rolled back with the delete


def test_audit_log_is_tenant_scoped_and_immutable(client_for, make_user, school, university):
    admin = make_user("admin@s.edu", "inst_admin", school)
    uni_admin = make_user("admin@u.edu", "inst_admin", university)
    client_for(admin).post("/api/students/", {"first_name": "A", "last_name": "B"}, format="json")
    events = client_for(uni_admin).get("/api/audit/").data["results"]
    assert all(e["action"] != "student.created" for e in events)
    assert any(e["action"] == "student.created" for e in client_for(admin).get("/api/audit/").data["results"])
    event = AuditEvent.objects.filter(action="student.created").first()
    event.action = "tampered"
    import pytest
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ValidationError):
        event.delete()


def test_teacher_cannot_view_audit_log(client_for, make_user, school):
    teacher = make_user("t@s.edu", "class_teacher", school)
    assert client_for(teacher).get("/api/audit/").status_code == 403
