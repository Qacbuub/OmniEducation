"""
Which students a user may see.

* Roles with `students.view` see every student in their institution.
* Guardians see only linked children; pupils/students see only themselves.
* Teaching roles see the students they teach. The school and university modules register
  providers for this, so K-12 class logic and university section logic stay separate.
"""
from django.db.models import Q

from .models import Student

# Each provider: fn(user) -> Q | None. Registered by the school / university apps.
STUDENT_SCOPE_PROVIDERS = []


def register_student_scope(fn):
    STUDENT_SCOPE_PROVIDERS.append(fn)
    return fn


def visible_students(user):
    qs = Student.objects.filter(tenant=user.tenant).select_related("person")
    if user.has_perm_code("students.view"):
        return qs
    conditions = Q(user=user) | Q(guardian_links__guardian__user=user)
    for provider in STUDENT_SCOPE_PROVIDERS:
        extra = provider(user)
        if extra is not None:
            conditions |= extra
    return qs.filter(conditions).distinct()


def can_view_student(user, student):
    return visible_students(user).filter(pk=student.pk).exists()
