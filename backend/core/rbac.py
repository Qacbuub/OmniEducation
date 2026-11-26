"""
Role-based access control definitions.

Roles and permissions are stored in the database (Role, Permission) and synced from this
module after every migrate, so this file is the single source of truth for the role matrix.
"""

PERMISSIONS = {
    # Platform
    "platform.manage_tenants": "Create institutions, plans, domains and tenant administrators",
    # Institution administration
    "tenant.manage_settings": "Edit institution branding, grading scales and policies",
    "staff.view": "View staff profiles",
    "staff.manage": "Create staff, assign roles and send invitations",
    "calendar.manage": "Manage academic years, terms and semesters",
    "announcements.manage": "Publish announcements",
    "audit.view": "View the institution audit log",
    "reports.view": "View dashboards and reports",
    # Students and admissions
    "students.view": "View all student records in the institution",
    "students.manage": "Create and edit student records",
    "admissions.view": "View applications",
    "admissions.manage": "Review, approve, reject and enroll applicants",
    "documents.manage": "Upload and generate documents for any student",
    # Finance
    "fees.view": "View fee plans, invoices and balances",
    "fees.manage": "Create fee plans, invoices and discounts",
    "payments.record": "Record payments and issue receipts",
    # School (K-12)
    "school.classes.manage": "Manage grade levels, sections, subjects, allocations and timetables",
    "school.attendance.record": "Record attendance for assigned classes",
    "school.marks.enter": "Enter marks for assigned subjects",
    "school.results.publish": "Finalize term results and publish report cards",
    "school.promotion.decide": "Promote, repeat, transfer or graduate pupils",
    # University
    "uni.programs.manage": "Manage faculties, departments, programs, curricula and courses",
    "uni.offerings.manage": "Manage semesters, course sections and lecturer assignments",
    "uni.registration.approve": "Approve course registrations and overrides",
    "uni.grades.submit": "Enter and submit grades for assigned sections",
    "uni.grades.approve": "Moderate and approve submitted grades",
    "uni.transcripts.issue": "Issue official transcripts",
    "uni.clearance.manage": "Run degree audits and graduation clearance",
}

_ADMIN_BASE = [
    "tenant.manage_settings", "staff.view", "staff.manage", "calendar.manage", "announcements.manage",
    "audit.view", "reports.view", "students.view", "students.manage", "admissions.view",
    "admissions.manage", "documents.manage", "fees.view",
]

ROLES = {
    # code: (name, scope, permissions)
    "super_admin": ("Platform Super Admin", "platform", ["platform.manage_tenants"]),
    "inst_admin": ("Institution Admin", "shared", _ADMIN_BASE + [
        "fees.manage", "school.classes.manage", "school.promotion.decide",
        "uni.programs.manage", "uni.offerings.manage"]),
    "registrar": ("Registrar", "shared", _ADMIN_BASE + [
        "uni.offerings.manage", "uni.registration.approve", "uni.transcripts.issue",
        "uni.clearance.manage", "uni.grades.approve"]),
    "finance_officer": ("Finance Officer", "shared", [
        "students.view", "fees.view", "fees.manage", "payments.record", "reports.view"]),
    # School
    "principal": ("Principal", "school", [
        "staff.view", "calendar.manage", "announcements.manage", "audit.view", "reports.view",
        "students.view", "students.manage", "admissions.view", "admissions.manage", "documents.manage",
        "fees.view", "school.classes.manage", "school.attendance.record", "school.marks.enter",
        "school.results.publish", "school.promotion.decide"]),
    "class_teacher": ("Class Teacher", "school", ["school.attendance.record", "school.marks.enter"]),
    "subject_teacher": ("Subject Teacher", "school", ["school.attendance.record", "school.marks.enter"]),
    "guardian": ("Parent / Guardian", "school", []),
    "pupil": ("Pupil", "school", []),
    # University
    "dean": ("Dean", "university", [
        "staff.view", "announcements.manage", "reports.view", "students.view", "admissions.view",
        "uni.programs.manage", "uni.grades.approve"]),
    "dept_head": ("Department Head", "university", [
        "staff.view", "reports.view", "students.view", "uni.programs.manage", "uni.offerings.manage",
        "uni.grades.approve"]),
    "lecturer": ("Lecturer", "university", ["uni.grades.submit"]),
    "adviser": ("Academic Adviser", "university", ["uni.registration.approve"]),
    "student": ("Student", "university", []),
}

# Roles that only see their own (or linked) records rather than the whole institution.
SELF_SERVICE_ROLES = {"guardian", "pupil", "student"}

SCHOOL_ROLES = {code for code, (_, scope, _) in ROLES.items() if scope in ("school", "shared")}
UNIVERSITY_ROLES = {code for code, (_, scope, _) in ROLES.items() if scope in ("university", "shared")}


def role_allowed_for_tenant(role_code, tenant_type):
    if role_code == "super_admin":
        return False
    return role_code in (SCHOOL_ROLES if tenant_type == "school" else UNIVERSITY_ROLES)


def sync_roles():
    """Create/update Permission and Role rows from the definitions above."""
    from .models import Permission, Role

    perms = {}
    for code, description in PERMISSIONS.items():
        perms[code], _ = Permission.objects.update_or_create(code=code, defaults={"description": description})
    Permission.objects.exclude(code__in=PERMISSIONS.keys()).delete()
    for code, (name, scope, perm_codes) in ROLES.items():
        role, _ = Role.objects.update_or_create(code=code, defaults={"name": name, "scope": scope})
        role.permissions.set([perms[c] for c in perm_codes])
