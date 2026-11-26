from datetime import date

import pytest
from rest_framework.test import APIClient

from admissions.models import AcademicPeriod
from core.models import Role, Tenant, User
from core.rbac import sync_roles
from people.models import Guardian, GuardianLink, Person, Student

PASSWORD = "Str0ng-Pass!2026"


@pytest.fixture(autouse=True)
def roles(db):
    sync_roles()


@pytest.fixture
def school(db):
    return Tenant.objects.create(name="Test School", slug="tschool", type="school", status="active")


@pytest.fixture
def university(db):
    return Tenant.objects.create(name="Test University", slug="tuni", type="university", status="active",
                                 currency="USD")


@pytest.fixture
def make_user(db):
    def _make(email, role, tenant=None, **extra):
        return User.objects.create_user(email=email, password=PASSWORD, role=Role.objects.get(code=role),
                                        tenant=tenant, first_name=email.split("@")[0].title(), last_name="Test", **extra)
    return _make


@pytest.fixture
def make_student(db):
    def _make(tenant, first="Pat", last="Pupil", level="Grade 4", user=None, email=""):
        person = Person.objects.create(tenant=tenant, first_name=first, last_name=last, date_of_birth=date(2015, 1, 1),
                                       email=email)
        return Student.objects.create(tenant=tenant, person=person, user=user, current_level=level,
                                      student_no=Student.next_student_no(tenant))
    return _make


@pytest.fixture
def link_guardian(db):
    def _link(student, user):
        person = Person.objects.create(tenant=student.tenant, first_name=user.first_name, last_name="Guardian",
                                       email=user.email)
        g = Guardian.objects.create(tenant=student.tenant, person=person, user=user)
        GuardianLink.objects.create(tenant=student.tenant, guardian=g, student=student, is_primary=True)
        return g
    return _link


@pytest.fixture
def client_for():
    def _client(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c
    return _client


@pytest.fixture
def anon():
    return APIClient()


@pytest.fixture
def school_year(school):
    return AcademicPeriod.objects.create(tenant=school, name="2026", kind="academic_year",
                                         start_date=date(2026, 1, 5), end_date=date(2026, 12, 11), is_current=True)
