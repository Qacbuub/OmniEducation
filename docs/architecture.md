# Architecture

OmniEducation is one multi-tenant web platform for **schools (K-12)** and **universities**. Each institution is a
*tenant*: its own users, students, academic structure, fees, branding and audit log, isolated from every other
institution on the server side.

| Layer | Technology |
|---|---|
| Frontend | React 19 single-page app, Vite, React Router 7 |
| API | Django 5.2 + Django REST Framework, SimpleJWT, drf-spectacular (OpenAPI) |
| Database | PostgreSQL (16 or newer; SQLite only as a local fallback) |
| Web server | Nginx in front of Gunicorn; Docker Compose for a reproducible deployment |
| Documents | ReportLab (report cards, transcripts, ID cards, letters, receipts) |
| Email | Django email over SMTP (Gmail App password locally); console output in development |

Diagrams below are [Mermaid](https://mermaid.js.org/) and render on GitHub. Detailed tables:
[data-model.md](data-model.md). Roles: [roles.md](roles.md). Business rules: [school.md](school.md),
[university.md](university.md). Deployment: [deployment.md](deployment.md). Limitations: [limitations.md](limitations.md).

---

## 1. System overview

```mermaid
flowchart LR
    subgraph Users["People (browser)"]
        PA[Platform admin]
        IA[Institution staff<br/>admin, principal, registrar,<br/>finance, dean, HOD]
        T[Teachers & lecturers<br/>advisers]
        F[Pupils, students<br/>parents]
    end

    subgraph Server["Server"]
        NG[Nginx<br/>TLS, static files,<br/>login rate limit]
        SPA[React app<br/>built files]
        API[Django REST API<br/>on Gunicorn]
        DB[(PostgreSQL)]
        FS[(Uploads<br/>photos, documents)]
    end

    SMTP[SMTP / Gmail]

    PA & IA & T & F -->|HTTPS| NG
    NG -->|/| SPA
    NG -->|/api, /admin| API
    API --> DB
    API --> FS
    API -->|invitations, resets,<br/>notifications| SMTP
```

* The browser loads the React app once, then talks to the API with JSON over `/api/…`.
* Nginx never serves student photos or documents directly: they are streamed by the API after a permission check.
* In development, Vite (port 5173) plays Nginx's role and proxies `/api` to Django on port 8000.

## 2. Backend structure: a shared core with two pluggable modules

The brief requires K-12 logic (classes, terms, promotion) to stay separate from university logic (courses, credits,
semesters, transcripts). Shared apps own everything common; the two academic modules plug in through **hook
registries**, so the shared code never imports school- or university-specific code.

```mermaid
flowchart TB
    subgraph Shared["Shared foundation"]
        core["core<br/>tenants, users, roles & permissions,<br/>JWT login + MFA, invitations, audit log,<br/>tenant isolation"]
        people["people<br/>persons, students, guardians,<br/>emergency contacts, staff, photos"]
        admissions["admissions<br/>academic calendar, application pipeline,<br/>enrollment history"]
        finance["finance<br/>fee plans, invoices, discounts,<br/>payments, receipts, arrears"]
        comms["comms<br/>notifications, announcements,<br/>documents"]
        reports["reports<br/>dashboards, branded PDFs"]
    end

    subgraph School["school (K-12)"]
        s1["grade levels, classes, subjects,<br/>timetable, attendance, marks,<br/>term results, report cards, promotion"]
    end

    subgraph Uni["university"]
        u1["faculties, departments, programs, curricula,<br/>courses & prerequisites, semesters, sections,<br/>registration, grades & approval, transcript,<br/>standing, degree audit, clearance"]
    end

    School -- "ENROLLMENT_HANDLERS<br/>place pupil in a class" --> admissions
    Uni -- "ENROLLMENT_HANDLERS<br/>matriculate into a program" --> admissions
    School -- "register_student_scope<br/>teachers see their classes" --> people
    Uni -- "register_student_scope<br/>lecturers & advisers" --> people
    School -- "register_dashboard_provider" --> reports
    Uni -- "register_dashboard_provider" --> reports
    finance --> people
    admissions --> people
    people --> core
    finance --> core
    comms --> core
```

| Hook | Defined in | Used for |
|---|---|---|
| `TARGET_VALIDATORS`, `ENROLLMENT_HANDLERS` | `admissions/hooks.py` | What an applicant applies for, and what "enrol" means (class placement vs. program matriculation) |
| `register_student_scope` | `people/scoping.py` | Which students a teacher, lecturer or adviser may see |
| `register_dashboard_provider` | `reports/views.py` | Mode-specific dashboard numbers and charts |
| `seed.hooks` | `seed/hooks.py` | Demo data for each module |

Business rules live in **service functions** (`finance/services.py`, `school/services.py`,
`university/services.py`), not in views or serializers, so the API, the admin and the seed command all go through
the same checks. A broken rule raises `BusinessRuleViolation`, which the API returns as
`{"code", "message", "fields"}` with HTTP 400.

## 3. Request lifecycle and security checks

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser (React)
    participant N as Nginx
    participant A as DRF view
    participant P as Permission check
    participant Q as Tenant-scoped query
    participant S as Service (business rules)
    participant D as PostgreSQL
    participant L as Audit log

    B->>N: POST /api/universities/grades/approve  (Bearer JWT)
    N->>A: proxy (adds X-Forwarded-For / Proto)
    A->>A: authenticate JWT, load user + tenant
    A->>P: required_perms["approve"] = "uni.grades.approve"
    P-->>A: allowed (otherwise 403)
    A->>Q: queryset filtered by user.tenant (+ teaching scope)
    Q-->>A: object, or 404 if it belongs to another tenant
    A->>S: approve_grades(...)  inside one database transaction
    S->>D: validate rules, write changes
    S->>L: append audit event (who, what, before/after, IP)
    S-->>A: result
    A-->>B: 200 JSON  (or 400 {code, message, fields})
```

Every request is one database transaction (`ATOMIC_REQUESTS`): if any rule fails part-way, nothing from that request
is kept.

### Security controls

| Concern | Control |
|---|---|
| Tenant isolation | Every tenant-owned model inherits `TenantScopedModel`; every viewset uses `TenantScopedViewSetMixin`, which filters by the signed-in user's tenant. The tenant comes from the login, never from the request body. Foreign keys in request bodies are checked against the tenant too. Cross-tenant access returns 404. |
| Authorization | Role → permission matrix in `core/rbac.py` (see [roles.md](roles.md)); each action declares `required_perms`; undeclared actions are denied. Teaching and self-service scopes filter rows. |
| Authentication | JWT access tokens (30 min) + rotating refresh tokens, blacklisted on sign-out and on password change. Each browser tab keeps its own session. Optional TOTP two-factor sign-in. |
| Brute force | Login and password-reset throttling in Django, plus an Nginx rate limit on the login endpoint. |
| Passwords | Django's PBKDF2 hashing and password validators; reset links are single-use and expire in 1 hour; the reset endpoint never reveals whether an email exists. |
| Accounts | Staff, parents and students join by invitation (expiring token); roles allowed per institution mode. |
| Files | Photos are checked by content (real JPG/PNG only, 3 MB); documents by type (.pdf, .docx, .jpg, .png) and size (5 MB). All are stored under random names and served only through permission-checked endpoints; only institution logos are public. |
| Public application | `/api/public/…` needs no sign-in and is rate-limited per IP. It shows only institution names and what can be applied for. An applicant sees their own application only with its private 10-character reference code, can add a photo and documents only before a decision, cannot label an upload as an official document, and can only accept or decline an open offer. |
| Audit | Append-only `AuditEvent` (cannot be edited or deleted): sign-ins, failed sign-ins, data changes with before/after values, decisions, payments, exports, downloads. |
| Payments | Mock only: no card data is collected or stored; mock receipts are labelled as such. |
| Transport & headers | HTTPS via Nginx, HSTS and secure cookies in production, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`. |

## 4. Data model overview

The core relationships across the platform (all tables: [data-model.md](data-model.md)):

```mermaid
erDiagram
    Tenant ||--o{ User : "has"
    Role ||--o{ User : "grants permissions to"
    Tenant ||--o{ Person : "owns"
    Person ||--o| Student : "is"
    Person ||--o| Guardian : "is"
    Person ||--o| Staff : "is"
    User |o--o| Student : "portal account"
    User |o--o| Guardian : "portal account"
    User |o--o| Staff : "account"
    Guardian ||--o{ GuardianLink : ""
    Student ||--o{ GuardianLink : "linked children"
    Student ||--o{ EmergencyContact : ""
    Tenant ||--o{ AcademicPeriod : "years, terms, semesters"
    Application |o--o| Student : "becomes on enrolment"
    Student ||--o{ Enrollment : "history"
    AcademicPeriod ||--o{ Enrollment : ""
    Student ||--o{ Invoice : "billed"
    FeePlan ||--o{ Invoice : "issued from"
    Invoice ||--o{ Payment : "paid by"

    Student ||--o{ ClassPlacement : "school: in a class"
    ClassSection ||--o{ ClassPlacement : ""
    ClassSection ||--o{ ClassAssignment : "subject + teacher"
    Student ||--o{ TermResult : "report card per term"

    Program ||--o{ Curriculum : "versions"
    Student ||--o| AcademicStanding : "university: program, CGPA, adviser"
    Course ||--o{ CourseOffering : "sections per semester"
    Student ||--o{ CourseRegistration : ""
    CourseOffering ||--o{ CourseRegistration : ""
    CourseRegistration ||--o| UniversityGrade : ""
    Student ||--o{ TranscriptEntry : "immutable record"
```

Design choices:

* **Person** holds personal data once; a person can be a student, a guardian and/or staff member.
* **Enrollment** is history, never overwritten: admission, promotion, repeat, transfer, withdrawal, graduation.
* **TranscriptEntry** and **GradeApproval** are append-only; an amended grade *supersedes* the old entry.
* **Invoice** balances are recalculated from lines, discounts and payments; payments lock the invoice row
  (`select_for_update`) so two cashiers cannot over-collect.
* Human-readable numbers (student, staff, application, invoice, receipt) continue from the highest number used.

## 5. Main workflows

### Admission (shared pipeline, mode-specific ending)

```mermaid
stateDiagram-v2
    [*] --> submitted: online or staff application
    submitted --> under_review
    under_review --> approved: school
    under_review --> offered: university
    offered --> offer_accepted
    offered --> offer_declined
    approved --> enrolled: place in class (+ optional first invoice)
    offer_accepted --> enrolled: matriculate (+ optional first invoice)
    submitted --> rejected
    under_review --> rejected
    submitted --> withdrawn
    under_review --> withdrawn
    approved --> withdrawn
    offer_accepted --> withdrawn
    withdrawn --> under_review: reopen
    enrolled --> [*]
```

### University grades: separation of duties

```mermaid
stateDiagram-v2
    [*] --> draft: lecturer enters assessment scores
    draft --> submitted: lecturer submits section
    submitted --> returned: HOD / dean / registrar returns
    returned --> submitted: lecturer corrects and resubmits
    submitted --> approved: HOD / dean / registrar approves
    approved --> [*]: transcript entry written, GPA and standing recalculated
```

### School term results

```mermaid
stateDiagram-v2
    [*] --> marks: teachers enter marks and attendance
    marks --> finalized: principal finalizes (marks locked, positions computed)
    finalized --> published: principal publishes report cards
    published --> [*]: parents and pupils notified, PDF available
```

### Course registration

```mermaid
stateDiagram-v2
    [*] --> pending: student requests (checks: prerequisites, seats, clashes, credit limit, window)
    [*] --> approved: registrar / adviser registers directly
    pending --> approved: adviser approves
    pending --> rejected: adviser rejects
    approved --> dropped: drop before the add/drop deadline
```

## 6. Frontend

```
frontend/src
  api/client.js        fetch wrapper: JWT per tab, silent refresh, structured errors, downloads
  auth/                AuthContext (session per tab), route guards
  config/              roles, navigation per role and mode
  components/          AppShell (sidebar, top bar, notifications), UI kit, CRUD cards
  pages/common/        dashboards, students, admissions, staff, fees, documents, reports, audit, profile
  pages/school/        classes, attendance, timetable, homework, marks, report cards, promotions, setup
  pages/university/    programs, offerings, registration, gradebook, approvals, transcript, degree audit, setup
  pages/platform/      institutions, tenant settings, administrator invitations
```

* The menu is built from the user's role and the institution's mode, but **the server is the authority**: hiding a
  button is a convenience, never a security control.
* Lists refresh when a tab regains focus; every form shows the server's field errors next to the field.

## 7. Deployment

```mermaid
flowchart LR
    U[Browser] -->|80 / 443| W
    subgraph Docker["docker-compose.prod.yml"]
        W["web<br/>Nginx + React build"] -->|/api, /admin| B["backend<br/>Gunicorn + Django<br/>(non-root)"]
        B --> DB[("db<br/>PostgreSQL 16")]
        W -. reads .-> ST[(static volume)]
        W -. logos only .-> M[(media volume)]
        B --> ST
        B --> M
        DB --- PG[(pgdata volume)]
    end
```

On start the backend waits for PostgreSQL, runs migrations, collects static files and, if `SEED_DEMO=true` and the
database is empty, loads the demo school and university. See [deployment.md](deployment.md).
