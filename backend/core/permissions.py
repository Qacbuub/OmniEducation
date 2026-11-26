from rest_framework.permissions import BasePermission

AUTHENTICATED = "__authenticated__"  # any signed-in user of the tenant


class IsPlatformAdmin(BasePermission):
    message = "Only platform administrators can do this."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_platform_admin)


class IsTenantUser(BasePermission):
    """The user must belong to an active (or trial) institution. Platform admins are refused here,
    so they cannot browse private student records."""

    message = "This action requires an institution account."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.tenant_id and u.tenant.status != "suspended")


class IsSchoolTenant(BasePermission):
    message = "This feature is only available to school (K-12) institutions."

    def has_permission(self, request, view):
        return bool(request.user.tenant_id and request.user.tenant.is_school)


class IsUniversityTenant(BasePermission):
    message = "This feature is only available to university institutions."

    def has_permission(self, request, view):
        return bool(request.user.tenant_id and request.user.tenant.is_university)


class RolePermission(BasePermission):
    """
    Checks `view.required_perms`, a dict of {action: permission code | tuple of codes | AUTHENTICATED}.
    "*" is the fallback. An action with no entry is denied (secure by default).
    Holding ANY of the listed codes is enough.
    """

    message = "Your role does not allow this action."

    def has_permission(self, request, view):
        perms = getattr(view, "required_perms", None)
        if perms is None:
            return True
        action = getattr(view, "action", None) or request.method.lower()
        needed = perms.get(action, perms.get("*"))
        if needed is None:
            return False
        if needed == AUTHENTICATED:
            return True
        if isinstance(needed, str):
            needed = (needed,)
        return request.user.has_perm_code(*needed)
