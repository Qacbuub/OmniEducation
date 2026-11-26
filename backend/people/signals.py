from django.dispatch import receiver

from core.models import User
from core.numbering import next_code
from core.rbac import SELF_SERVICE_ROLES
from core.views import user_joined

from .models import Guardian, Person, Staff, Student


@receiver(user_joined, sender=User)
def link_profile(sender, user, **kwargs):
    """When an invited user activates their account, link it to the matching profile."""
    if not user.tenant_id:
        return
    tenant = user.tenant
    if user.role_code in SELF_SERVICE_ROLES:
        model = Guardian if user.role_code == "guardian" else Student
        profile = model.objects.filter(tenant=tenant, person__email__iexact=user.email, user__isnull=True).first()
        if profile:
            profile.user = user
            profile.save(update_fields=["user"])
        return
    if Staff.objects.filter(user=user).exists():
        return
    person = Person.objects.create(tenant=tenant, first_name=user.first_name, last_name=user.last_name,
                                   email=user.email)
    Staff.objects.create(tenant=tenant, person=person, user=user,
                         staff_no=next_code(Staff.objects.filter(tenant=tenant), "staff_no", "STF-", 4),
                         job_title=user.role.name)
