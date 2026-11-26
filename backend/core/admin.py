from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import AuditEvent, Invitation, Permission, Role, Tenant, User


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ["name", "type", "status", "plan", "created_at"]
    list_filter = ["type", "status", "plan"]
    search_fields = ["name", "slug"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "tenant", "role", "is_active"]
    list_filter = ["role", "tenant", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "phone", "tenant", "role")}),
        ("Security", {"fields": ("is_active", "is_staff", "is_superuser", "mfa_enabled")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2", "tenant", "role")}),)


admin.site.register(Role)
admin.site.register(Permission)
admin.site.register(Invitation)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "tenant", "actor_email", "action", "target_repr"]
    list_filter = ["action", "tenant"]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
