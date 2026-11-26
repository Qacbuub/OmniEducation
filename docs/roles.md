# Roles and permissions

Generated from [`backend/core/rbac.py`](../backend/core/rbac.py) with `python scripts/generate_roles.py`, so this
matrix is exactly what the server enforces. 14 roles, 28 permissions.

## How access is decided

Every API request passes three checks, all on the server:

1. **Signed in** – a valid JWT access token (30 minutes; refresh tokens rotate and are revoked on sign-out).
2. **Permission** – each endpoint action declares the permission it needs (`required_perms`). An action that
   declares nothing is **denied by default**.
3. **Data scope** – the query itself is filtered to the user's institution (tenant) and, for teaching and
   self-service roles, to the records they are linked to. Another institution's records, or a student you are not
   linked to, return **404 – not found**, so their existence is not revealed.

Self-service roles (Parent, Pupil, Student) hold no institution-wide
permissions at all; everything they see comes from scope rules.

## Data scope by role

| Role | Sees |
|---|---|
| Platform Super Admin | All institutions' settings, plans and administrators. **No access to student records.** |
| Institution Admin | Everything in their own institution. |
| Registrar | Every student in the institution; admissions, records, transcripts, registration overrides. |
| Finance Officer | Every student's fees, invoices and payments (read-only student details). |
| Principal | Every pupil, class and result in the school. |
| Class Teacher | Pupils in their homeroom class and in classes where they teach a subject. |
| Subject Teacher | Pupils in the classes where they teach a subject; marks only for their own subjects. |
| Parent / Guardian | Only their linked children: attendance, results, report cards, fees, payments. |
| Pupil | Only themselves: timetable, homework, published report cards, fees. |
| Dean | Every student record (read-only); programmes and curricula; approves submitted grades. |
| Department Head | Every student record (read-only); courses, sections and lecturers; approves submitted grades. |
| Lecturer | Students registered in their own sections; gradebook for those sections only. |
| Academic Adviser | Their advisees: records, registration approvals, standing. |
| Student | Only themselves: registration, timetable, marks, transcript, degree audit, fees. |

## School (K-12) roles

| Permission | Inst. admin | Principal | Registrar | Finance | Class teacher | Subject teacher | Parent | Pupil |
|---|---|---|---|---|---|---|---|---|
| **Institution** | | | | | | | | |
| `tenant.manage_settings`<br><sub>Edit institution branding, grading scales and policies</sub> | ✓ |  | ✓ |  |  |  |  |  |
| `staff.view`<br><sub>View staff profiles</sub> | ✓ | ✓ | ✓ |  |  |  |  |  |
| `staff.manage`<br><sub>Create staff, assign roles and send invitations</sub> | ✓ |  | ✓ |  |  |  |  |  |
| `calendar.manage`<br><sub>Manage academic years, terms and semesters</sub> | ✓ | ✓ | ✓ |  |  |  |  |  |
| `announcements.manage`<br><sub>Publish announcements</sub> | ✓ | ✓ | ✓ |  |  |  |  |  |
| `audit.view`<br><sub>View the institution audit log</sub> | ✓ | ✓ | ✓ |  |  |  |  |  |
| `reports.view`<br><sub>View dashboards and reports</sub> | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| **Students & admissions** | | | | | | | | |
| `students.view`<br><sub>View all student records in the institution</sub> | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| `students.manage`<br><sub>Create and edit student records</sub> | ✓ | ✓ | ✓ |  |  |  |  |  |
| `admissions.view`<br><sub>View applications</sub> | ✓ | ✓ | ✓ |  |  |  |  |  |
| `admissions.manage`<br><sub>Review, approve, reject and enroll applicants</sub> | ✓ | ✓ | ✓ |  |  |  |  |  |
| `documents.manage`<br><sub>Upload and generate documents for any student</sub> | ✓ | ✓ | ✓ |  |  |  |  |  |
| **Finance** | | | | | | | | |
| `fees.view`<br><sub>View fee plans, invoices and balances</sub> | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| `fees.manage`<br><sub>Create fee plans, invoices and discounts</sub> | ✓ |  |  | ✓ |  |  |  |  |
| `payments.record`<br><sub>Record payments and issue receipts</sub> |  |  |  | ✓ |  |  |  |  |
| **School (K-12)** | | | | | | | | |
| `school.classes.manage`<br><sub>Manage grade levels, sections, subjects, allocations and timetables</sub> | ✓ | ✓ |  |  |  |  |  |  |
| `school.attendance.record`<br><sub>Record attendance for assigned classes</sub> |  | ✓ |  |  | ✓ | ✓ |  |  |
| `school.marks.enter`<br><sub>Enter marks for assigned subjects</sub> |  | ✓ |  |  | ✓ | ✓ |  |  |
| `school.results.publish`<br><sub>Finalize term results and publish report cards</sub> |  | ✓ |  |  |  |  |  |  |
| `school.promotion.decide`<br><sub>Promote, repeat, transfer or graduate pupils</sub> | ✓ | ✓ |  |  |  |  |  |  |
| **University** | | | | | | | | |
| `uni.programs.manage`<br><sub>Manage faculties, departments, programs, curricula and courses</sub> | ✓ |  |  |  |  |  |  |  |
| `uni.offerings.manage`<br><sub>Manage semesters, course sections and lecturer assignments</sub> | ✓ |  | ✓ |  |  |  |  |  |
| `uni.registration.approve`<br><sub>Approve course registrations and overrides</sub> |  |  | ✓ |  |  |  |  |  |
| `uni.grades.approve`<br><sub>Moderate and approve submitted grades</sub> |  |  | ✓ |  |  |  |  |  |
| `uni.transcripts.issue`<br><sub>Issue official transcripts</sub> |  |  | ✓ |  |  |  |  |  |
| `uni.clearance.manage`<br><sub>Run degree audits and graduation clearance</sub> |  |  | ✓ |  |  |  |  |  |

## University roles

| Permission | Inst. admin | Registrar | Dean | Dept. head | Lecturer | Adviser | Finance | Student |
|---|---|---|---|---|---|---|---|---|
| **Institution** | | | | | | | | |
| `tenant.manage_settings`<br><sub>Edit institution branding, grading scales and policies</sub> | ✓ | ✓ |  |  |  |  |  |  |
| `staff.view`<br><sub>View staff profiles</sub> | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| `staff.manage`<br><sub>Create staff, assign roles and send invitations</sub> | ✓ | ✓ |  |  |  |  |  |  |
| `calendar.manage`<br><sub>Manage academic years, terms and semesters</sub> | ✓ | ✓ |  |  |  |  |  |  |
| `announcements.manage`<br><sub>Publish announcements</sub> | ✓ | ✓ | ✓ |  |  |  |  |  |
| `audit.view`<br><sub>View the institution audit log</sub> | ✓ | ✓ |  |  |  |  |  |  |
| `reports.view`<br><sub>View dashboards and reports</sub> | ✓ | ✓ | ✓ | ✓ |  |  | ✓ |  |
| **Students & admissions** | | | | | | | | |
| `students.view`<br><sub>View all student records in the institution</sub> | ✓ | ✓ | ✓ | ✓ |  |  | ✓ |  |
| `students.manage`<br><sub>Create and edit student records</sub> | ✓ | ✓ |  |  |  |  |  |  |
| `admissions.view`<br><sub>View applications</sub> | ✓ | ✓ | ✓ |  |  |  |  |  |
| `admissions.manage`<br><sub>Review, approve, reject and enroll applicants</sub> | ✓ | ✓ |  |  |  |  |  |  |
| `documents.manage`<br><sub>Upload and generate documents for any student</sub> | ✓ | ✓ |  |  |  |  |  |  |
| **Finance** | | | | | | | | |
| `fees.view`<br><sub>View fee plans, invoices and balances</sub> | ✓ | ✓ |  |  |  |  | ✓ |  |
| `fees.manage`<br><sub>Create fee plans, invoices and discounts</sub> | ✓ |  |  |  |  |  | ✓ |  |
| `payments.record`<br><sub>Record payments and issue receipts</sub> |  |  |  |  |  |  | ✓ |  |
| **School (K-12)** | | | | | | | | |
| `school.classes.manage`<br><sub>Manage grade levels, sections, subjects, allocations and timetables</sub> | ✓ |  |  |  |  |  |  |  |
| `school.promotion.decide`<br><sub>Promote, repeat, transfer or graduate pupils</sub> | ✓ |  |  |  |  |  |  |  |
| **University** | | | | | | | | |
| `uni.programs.manage`<br><sub>Manage faculties, departments, programs, curricula and courses</sub> | ✓ |  | ✓ | ✓ |  |  |  |  |
| `uni.offerings.manage`<br><sub>Manage semesters, course sections and lecturer assignments</sub> | ✓ | ✓ |  | ✓ |  |  |  |  |
| `uni.registration.approve`<br><sub>Approve course registrations and overrides</sub> |  | ✓ |  |  |  | ✓ |  |  |
| `uni.grades.submit`<br><sub>Enter and submit grades for assigned sections</sub> |  |  |  |  | ✓ |  |  |  |
| `uni.grades.approve`<br><sub>Moderate and approve submitted grades</sub> |  | ✓ | ✓ | ✓ |  |  |  |  |
| `uni.transcripts.issue`<br><sub>Issue official transcripts</sub> |  | ✓ |  |  |  |  |  |  |
| `uni.clearance.manage`<br><sub>Run degree audits and graduation clearance</sub> |  | ✓ |  |  |  |  |  |  |

## Platform role

| Permission | Platform super admin |
|---|---|
| `platform.manage_tenants`<br><sub>Create institutions, plans, domains and tenant administrators</sub> | ✓ |

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
