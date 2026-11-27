from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from core import mfa
from core.models import AuditEvent, Invitation, Role, User
from people.models import Staff

from .conftest import PASSWORD


def test_login_returns_tokens_and_profile(anon, make_user, school):
    make_user("admin@t.edu", "inst_admin", school)
    r = anon.post("/api/auth/login/", {"email": "ADMIN@t.edu", "password": PASSWORD}, format="json")
    assert r.status_code == 200
    assert r.data["access"] and r.data["refresh"]
    assert r.data["user"]["role"] == "inst_admin"
    assert r.data["user"]["tenant"]["type"] == "school"
    assert "students.manage" in r.data["user"]["permissions"]
    assert AuditEvent.objects.filter(action="auth.login").exists()


def test_login_wrong_password_uses_structured_error(anon, make_user, school):
    make_user("admin@t.edu", "inst_admin", school)
    r = anon.post("/api/auth/login/", {"email": "admin@t.edu", "password": "wrong"}, format="json")
    assert r.status_code == 401
    assert r.data["code"] == "invalid_credentials"
    assert r.data["message"] == "Invalid email or password."


def test_login_validation_errors_are_per_field(anon):
    r = anon.post("/api/auth/login/", {"email": "not-an-email"}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "validation_error"
    assert "password" in r.data["fields"] and "email" in r.data["fields"]


def test_inactive_and_suspended_accounts_cannot_log_in(anon, make_user, school):
    make_user("off@t.edu", "inst_admin", school, is_active=False)
    assert anon.post("/api/auth/login/", {"email": "off@t.edu", "password": PASSWORD}, format="json").status_code == 401
    make_user("on@t.edu", "inst_admin", school)
    school.status = "suspended"
    school.save()
    r = anon.post("/api/auth/login/", {"email": "on@t.edu", "password": PASSWORD}, format="json")
    assert r.status_code == 401 and r.data["code"] == "tenant_suspended"


def test_mfa_required_when_enabled(anon, make_user, school):
    secret = mfa.new_secret()
    make_user("mfa@t.edu", "principal", school, mfa_enabled=True, mfa_secret=secret)
    r = anon.post("/api/auth/login/", {"email": "mfa@t.edu", "password": PASSWORD}, format="json")
    assert r.status_code == 401 and r.data["code"] == "mfa_required"
    r = anon.post("/api/auth/login/", {"email": "mfa@t.edu", "password": PASSWORD, "otp": "000000"}, format="json")
    assert r.status_code == 401
    r = anon.post("/api/auth/login/", {"email": "mfa@t.edu", "password": PASSWORD, "otp": mfa.totp_now(secret)},
                  format="json")
    assert r.status_code == 200


def test_me_requires_authentication(anon, client_for, make_user, school):
    assert anon.get("/api/auth/me/").status_code == 401
    u = make_user("t@t.edu", "class_teacher", school)
    assert client_for(u).get("/api/auth/me/").data["email"] == "t@t.edu"


def test_password_reset_does_not_reveal_accounts(anon, make_user, school):
    make_user("real@t.edu", "principal", school)
    a = anon.post("/api/auth/password-reset/", {"email": "real@t.edu"}, format="json")
    b = anon.post("/api/auth/password-reset/", {"email": "nobody@t.edu"}, format="json")
    assert a.status_code == b.status_code == 200
    assert a.data == b.data
    assert len(mail.outbox) == 1 and "reset-password?uid=" in mail.outbox[0].body


def test_password_reset_confirm(anon, make_user, school):
    u = make_user("real@t.edu", "principal", school)
    uid, token = urlsafe_base64_encode(force_bytes(u.pk)), default_token_generator.make_token(u)
    weak = anon.post("/api/auth/password-reset/confirm/", {"uid": uid, "token": token, "new_password": "123"},
                     format="json")
    assert weak.status_code == 400 and "new_password" in weak.data["fields"]
    ok = anon.post("/api/auth/password-reset/confirm/", {"uid": uid, "token": token, "new_password": "N3w-Secret!x"},
                   format="json")
    assert ok.status_code == 200
    u.refresh_from_db()
    assert u.check_password("N3w-Secret!x")
    reused = anon.post("/api/auth/password-reset/confirm/", {"uid": uid, "token": token, "new_password": "Other-9!pass"},
                       format="json")
    assert reused.status_code == 400  # single-use token


def test_staff_invitation_flow(client_for, anon, make_user, school):
    admin = make_user("admin@t.edu", "inst_admin", school)
    r = client_for(admin).post("/api/invitations/", {"email": "new.teacher@t.edu", "role": "class_teacher"},
                               format="json")
    assert r.status_code == 201
    inv = Invitation.objects.get(email="new.teacher@t.edu")
    assert anon.get(f"/api/auth/invitations/{inv.token}/").data["institution"] == "Test School"
    r = anon.post("/api/auth/invitations/accept/", {"token": inv.token, "first_name": "Nia", "last_name": "Teach",
                                                    "new_password": "Teach-3r!pass"}, format="json")
    assert r.status_code == 201 and r.data["access"]
    user = User.objects.get(email="new.teacher@t.edu")
    assert user.tenant == school and user.role.code == "class_teacher"
    assert Staff.objects.filter(user=user).exists()
    again = anon.post("/api/auth/invitations/accept/", {"token": inv.token, "first_name": "X", "last_name": "Y",
                                                        "new_password": "Teach-3r!pass"}, format="json")
    assert again.status_code == 400


def test_cannot_invite_role_from_other_institution_type(client_for, make_user, school):
    admin = make_user("admin@t.edu", "inst_admin", school)
    r = client_for(admin).post("/api/invitations/", {"email": "x@t.edu", "role": "lecturer"}, format="json")
    assert r.status_code == 400 and "role" in r.data["fields"]
    r = client_for(admin).post("/api/invitations/", {"email": "x@t.edu", "role": "super_admin"}, format="json")
    assert r.status_code == 400


def test_teacher_cannot_invite_staff(client_for, make_user, school):
    teacher = make_user("t@t.edu", "class_teacher", school)
    r = client_for(teacher).post("/api/invitations/", {"email": "x@t.edu", "role": "class_teacher"}, format="json")
    assert r.status_code == 403


def test_user_cannot_change_own_role(client_for, make_user, school):
    admin = make_user("admin@t.edu", "inst_admin", school)
    r = client_for(admin).patch(f"/api/users/{admin.id}/", {"role": "principal"}, format="json")
    assert r.status_code == 400
    assert Role.objects.get(code="inst_admin") == User.objects.get(pk=admin.pk).role


def test_profile_edit_and_password_change(anon, client_for, make_user, school):
    u = make_user("p@t.edu", "class_teacher", school)
    c = client_for(u)
    r = c.patch("/api/auth/me/", {"first_name": "Amina", "phone": "+255700000001", "email": "x@evil.com"}, format="json")
    assert r.status_code == 200 and r.data["first_name"] == "Amina" and r.data["email"] == "p@t.edu"
    assert c.patch("/api/auth/me/", {"first_name": ""}, format="json").status_code == 400

    bad = c.post("/api/auth/password/", {"current_password": "wrong", "new_password": "Str0ng-pass!42"}, format="json")
    assert bad.status_code == 400 and "current_password" in bad.data["fields"]
    weak = c.post("/api/auth/password/", {"current_password": PASSWORD, "new_password": "123"}, format="json")
    assert weak.status_code == 400 and "new_password" in weak.data["fields"]
    ok = c.post("/api/auth/password/", {"current_password": PASSWORD, "new_password": "Str0ng-pass!42"}, format="json")
    assert ok.status_code == 200 and ok.data["access"]
    assert anon.post("/api/auth/login/", {"email": "p@t.edu", "password": "Str0ng-pass!42"}, format="json").status_code == 200
    assert AuditEvent.objects.filter(action="auth.password_changed", actor=u).exists()


def test_mfa_disable_needs_code_or_password(client_for, make_user, school):
    secret = mfa.new_secret()
    u = make_user("m2@t.edu", "principal", school, mfa_enabled=True, mfa_secret=secret)
    c = client_for(u)
    assert c.delete("/api/auth/mfa/", {"code": "000000"}, format="json").status_code == 400
    assert c.delete("/api/auth/mfa/", {"code": mfa.totp_now(secret)}, format="json").data["mfa_enabled"] is False
    u.refresh_from_db()
    assert not u.mfa_enabled and not u.mfa_secret


def test_failed_login_is_audited(anon, make_user, school):
    make_user("f@t.edu", "class_teacher", school)
    assert anon.post("/api/auth/login/", {"email": "f@t.edu", "password": "nope"}, format="json").status_code == 401
    assert AuditEvent.objects.filter(action="auth.login_failed").exists()


def test_invited_staff_gets_unused_staff_number(anon, make_user, school):
    """Staff numbers continue after the highest one, even when earlier numbers are not contiguous."""
    from core.models import Invitation, Role
    from people.models import Person, Staff
    for no in ("STF-0001", "STF-0009"):
        p = Person.objects.create(tenant=school, first_name="A", last_name=no, email=f"{no}@t.edu")
        Staff.objects.create(tenant=school, person=p, staff_no=no, job_title="Teacher")
    inv = Invitation.objects.create(tenant=school, email="new@t.edu", role=Role.objects.get(code="class_teacher"))
    r = anon.post("/api/auth/invitations/accept/", {"token": inv.token, "first_name": "Nano", "last_name": "Bani",
                                                     "new_password": "Str0ng-pass!42"}, format="json")
    assert r.status_code == 201
    assert Staff.objects.get(user__email="new@t.edu").staff_no == "STF-0010"


def test_token_fork_gives_independent_session(anon, make_user, school):
    """A new tab forks its own session: logging out in one tab leaves the other signed in."""
    make_user("tab@t.edu", "principal", school)
    first = anon.post("/api/auth/login/", {"email": "tab@t.edu", "password": PASSWORD}, format="json").data
    fork = anon.post("/api/auth/token/fork/", {"refresh": first["refresh"]}, format="json")
    assert fork.status_code == 200 and fork.data["refresh"] != first["refresh"]
    anon.credentials(HTTP_AUTHORIZATION=f"Bearer {first['access']}")
    assert anon.post("/api/auth/logout/", {"refresh": first["refresh"]}, format="json").status_code == 204
    anon.credentials()
    assert anon.post("/api/auth/token/refresh/", {"refresh": first["refresh"]}, format="json").status_code == 401
    assert anon.post("/api/auth/token/refresh/", {"refresh": fork.data["refresh"]}, format="json").status_code == 200
    assert anon.post("/api/auth/token/fork/", {"refresh": "junk"}, format="json").status_code == 401


def test_portal_invite_reports_whether_the_email_was_sent(client_for, make_user, make_student, school, settings):
    from django.core import mail
    admin = client_for(make_user("adm@s.edu", "inst_admin", school))
    student = make_student(school, email="pupil.mail@example.com")
    url = f"/api/students/{student.id}/portal-account/"

    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    settings.SHOW_INVITE_LINKS = False
    off = admin.post(url)
    assert off.status_code == 201 and off.data["email_sent"] is False
    assert "does not send emails" in off.data["message"] and off.data["invite_link"]  # staff must pass it on

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    again = admin.post(url)  # same pending invitation, now really emailed
    assert again.data["email_sent"] is True and again.data["invite_link"] is None
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["pupil.mail@example.com"]
