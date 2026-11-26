"""Write docs/roles.md: the role/permission matrix, generated from core/rbac.py (the single source of truth).

Run from the backend folder:  python scripts/generate_roles.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

from core.rbac import PERMISSIONS, ROLES, SELF_SERVICE_ROLES  # noqa: E402

GROUPS = [("Platform", "platform."), ("Institution", ("tenant.", "staff.", "calendar.", "announcements.", "audit.",
                                                    "reports.")),
          ("Students & admissions", ("students.", "admissions.", "documents.")), ("Finance", ("fees.", "payments.")),
          ("School (K-12)", "school."), ("University", "uni.")]
SCHOOL = ["inst_admin", "principal", "registrar", "finance_officer", "class_teacher", "subject_teacher", "guardian",
          "pupil"]
UNIVERSITY = ["inst_admin", "registrar", "dean", "dept_head", "lecturer", "adviser", "finance_officer", "student"]
SHORT = {"inst_admin": "Inst. admin", "principal": "Principal", "registrar": "Registrar", "finance_officer": "Finance",
         "class_teacher": "Class teacher", "subject_teacher": "Subject teacher", "guardian": "Parent", "pupil": "Pupil",
         "dean": "Dean", "dept_head": "Dept. head", "lecturer": "Lecturer", "adviser": "Adviser", "student": "Student"}

SCOPE = {
    "super_admin": "All institutions' settings, plans and administrators. **No access to student records.**",
    "inst_admin": "Everything in their own institution.",
    "registrar": "Every student in the institution; admissions, records, transcripts, registration overrides.",
    "finance_officer": "Every student's fees, invoices and payments (read-only student details).",
    "principal": "Every pupil, class and result in the school.",
    "class_teacher": "Pupils in their homeroom class and in classes where they teach a subject.",
    "subject_teacher": "Pupils in the classes where they teach a subject; marks only for their own subjects.",
    "guardian": "Only their linked children: attendance, results, report cards, fees, payments.",
    "pupil": "Only themselves: timetable, homework, published report cards, fees.",
    "dean": "Every student record (read-only); programmes and curricula; approves submitted grades.",
    "dept_head": "Every student record (read-only); courses, sections and lecturers; approves submitted grades.",
    "lecturer": "Students registered in their own sections; gradebook for those sections only.",
    "adviser": "Their advisees: records, registration approvals, standing.",
    "student": "Only themselves: registration, timetable, marks, transcript, degree audit, fees.",
}


def table(role_codes):
    head = "| Permission | " + " | ".join(SHORT[r] for r in role_codes) + " |"
    rows = [head, "|" + "---|" * (len(role_codes) + 1)]
    for title, prefix in GROUPS:
        codes = [c for c in PERMISSIONS if c.startswith(prefix)]
        codes = [c for c in codes if any(c in ROLES[r][2] for r in role_codes)]
        if not codes:
            continue
        rows.append(f"| **{title}** |" + " |" * len(role_codes))
        for c in codes:
            marks = " | ".join("✓" if c in ROLES[r][2] else "" for r in role_codes)
            rows.append(f"| `{c}`<br><sub>{PERMISSIONS[c]}</sub> | {marks} |")
    return "\n".join(rows)


out = f"""# Roles and permissions

Generated from [`backend/core/rbac.py`](../backend/core/rbac.py) with `python scripts/generate_roles.py`, so this
matrix is exactly what the server enforces. {len(ROLES)} roles, {len(PERMISSIONS)} permissions.

## How access is decided

Every API request passes three checks, all on the server:

1. **Signed in** – a valid JWT access token (30 minutes; refresh tokens rotate and are revoked on sign-out).
2. **Permission** – each endpoint action declares the permission it needs (`required_perms`). An action that
   declares nothing is **denied by default**.
3. **Data scope** – the query itself is filtered to the user's institution (tenant) and, for teaching and
   self-service roles, to the records they are linked to. Another institution's records, or a student you are not
   linked to, return **404 – not found**, so their existence is not revealed.

Self-service roles ({", ".join(SHORT.get(r, r) for r in sorted(SELF_SERVICE_ROLES))}) hold no institution-wide
permissions at all; everything they see comes from scope rules.

## Data scope by role

| Role | Sees |
|---|---|
""" + "\n".join(f"| {ROLES[r][0]} | {SCOPE[r]} |" for r in ROLES) + f"""

## School (K-12) roles

{table(SCHOOL)}

## University roles

{table(UNIVERSITY)}

## Platform role

| Permission | Platform super admin |
|---|---|
| `platform.manage_tenants`<br><sub>{PERMISSIONS["platform.manage_tenants"]}</sub> | ✓ |

## Rules that sit on top of permissions

- **Separation of duties:** lecturers submit grades; only a department head, dean or registrar can approve them,
  and approved grades are locked. Finance can issue invoices but cannot edit grades or student records.
- **Billing at enrolment:** anyone who can enrol may bill a standard fee plan; a one-off custom amount needs
  `fees.manage`.
- **Teachers** can mark attendance and enter marks only for classes and subjects assigned to them, and only
  until results are finalized.
- **Advisers** approve registrations only for their own advisees.
- **Guardians** reach a child only through a guardian link created by the school.
- **Invitations** can only grant roles that belong to the institution's mode (school roles in a school,
  university roles in a university); nobody can invite a platform super admin.
- **Every change** (create, update, delete, decisions, payments, exports, downloads, sign-ins) is written to the
  append-only audit log.
"""
with open(os.path.join(BACKEND, "..", "docs", "roles.md"), "w", encoding="utf-8") as f:
    f.write(out)
print("written", len(out))
