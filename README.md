# OmniEducation

One multi-tenant platform for **schools (K-12)** and **universities**, built for the OmniTeckno developer challenge.
Each institution is an isolated tenant with its own branding, academic structure, permissions and reports.

| Layer | Technology |
|---|---|
| Frontend | React 19 + Vite, React Router |
| Backend | Python, Django 5 + Django REST Framework, SimpleJWT |
| Database | PostgreSQL 16 or newer |
| Web server | Nginx → Gunicorn, with Docker Compose for a reproducible deployment (`docs/deployment.md`) |

## Quick start

### Option A – one command with Docker (Nginx + Gunicorn + PostgreSQL)
Needs only [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine on Linux).

**Windows:** double-click **`docker-local.bat`**. It creates `.env.prod` with random secrets, builds and starts
everything (5-15 minutes the first time), waits until the system answers and opens it in the browser.

**Any system:**
```bash
cp .env.prod.example .env.prod     # then set POSTGRES_PASSWORD and DJANGO_SECRET_KEY
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```
Open http://localhost. Demo data loads on the first start. Details, HTTPS and environment variables:
[`docs/deployment.md`](docs/deployment.md).

### Option B – Windows development setup
Double-click **`start-dev.bat`**: it opens a Backend tab (Django on :8000) and a Frontend tab (Vite on :5173),
installs everything the first time and loads the demo data. Open http://localhost:5173.
To move the local data from SQLite to PostgreSQL, run **`setup-postgres.bat`** once (see `docs/deployment.md`).

### Option C – by hand (any OS)
1. Database – `docker compose up -d db`, or in PostgreSQL 16 run `backend/scripts/create_db.sql` as `postgres`.
2. Backend:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver         # http://127.0.0.1:8000
```
3. Frontend:
```bash
cd frontend
npm install
echo VITE_USE_MOCK=false > .env
npm run dev                         # http://localhost:5173
```

- API docs (OpenAPI / Swagger): http://127.0.0.1:8000/api/docs/
- Django admin: http://127.0.0.1:8000/admin/ (sign in as `superadmin@omniedu.app`)
- Emails such as invitations and password resets are printed in the backend log during development; invitation
  links are also shown on screen there.

Tests (they create their own temporary database; on PostgreSQL the `omniedu` user needs CREATEDB):
```bash
cd backend && pytest               # 92 tests, pass on SQLite and PostgreSQL 16+
```

## Documentation

| Document | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | System and module diagrams, request lifecycle, security controls, data-model overview, workflows |
| [docs/data-model.md](docs/data-model.md) | ER diagrams of all 52 tables, generated from the models |
| [docs/roles.md](docs/roles.md) | Role and permission matrix (generated from `core/rbac.py`) and data scope per role |
| [docs/school.md](docs/school.md) | K-12 business rules |
| [docs/university.md](docs/university.md) | University business rules |
| [docs/deployment.md](docs/deployment.md) | Docker/Nginx deployment, HTTPS, PostgreSQL, email |
| [docs/limitations.md](docs/limitations.md) | Known limitations, verification status and prioritized improvements |

## Demo accounts
Password for every account: **`Demo@1234`** (synthetic data only).

| Institution | Role | Email |
|---|---|---|
| Platform | Super admin | superadmin@omniedu.app |
| Sunrise Academy (school) | Institution admin | admin@sunrise.edu |
| | Principal | principal@sunrise.edu |
| | Class teacher | teacher@sunrise.edu |
| | Subject teacher | subject@sunrise.edu |
| | Parent / guardian | parent@sunrise.edu |
| | Pupil | pupil@sunrise.edu |
| | Finance officer | finance@sunrise.edu |
| Omni University | Registrar | registrar@omniu.edu |
| | Dean | dean@omniu.edu |
| | Department head | hod@omniu.edu |
| | Lecturer | lecturer@omniu.edu |
| | Academic adviser | adviser@omniu.edu |
| | Student | student@omniu.edu |
| | Finance officer | finance@omniu.edu |

## Online application (no account needed)
Applicants open **`/apply`** (also linked from the sign-in page), choose a school or university and fill in the
form. They get a private reference code and use it on **`/apply/<institution>/status`** to follow the application,
add a passport photo and supporting documents, and (university) accept or decline an offer. Staff see online
applications in *Admissions*, marked *Online*.

## Project layout
```
backend/
  config/       settings (base/dev/prod/test from environment variables), URLs, WSGI
  core/         tenants, users, roles & permissions, invitations, MFA-ready login, audit log, tenant isolation
  people/       persons, students, guardians + links, emergency contacts, staff
  admissions/   academic calendar, application pipeline, enrollment history
  finance/      fee plans, invoices, discounts/scholarships, payments, receipts, arrears
  comms/        notifications, announcements, documents
  reports/      dashboards and branded PDFs (ID card, enrollment letter)
  school/       K-12: grades, classes, timetable, attendance, marks, report cards, promotion (docs/school.md)
  university/   faculties, programs, curricula, semesters, registration, grades, transcript, degree audit (docs/university.md)
  seed/         seed_demo and copy_data commands
  scripts/      create_db.sql (PostgreSQL user + database)
  tests/        pytest suite
frontend/       React app (see frontend/README.md)
deploy/nginx/   Nginx site configuration
docs/           deployment, school and university business rules
```
The school (K-12) and university modules plug into the shared services through registered hooks
(`admissions/hooks.py`, `people/scoping.py`, `reports/views.py`, `seed/hooks.py`). This keeps class/term/promotion
logic separate from course/credit/semester/transcript logic, as the brief requires.

## Security model
- **Tenant isolation is enforced on the server.** Every query is filtered by the signed-in user's tenant, so another
  tenant's records return 404. Foreign keys in request bodies are tenant-checked too, and the tenant always comes
  from the login, never from the request.
- **Role-based permissions:** each endpoint declares the permission it needs (`core/rbac.py` is the role matrix).
  Actions with no declared permission are denied by default.
- Guardians see only linked children. Pupils and students see only themselves. Platform admins can't browse student records.
- Login and password-reset endpoints are rate-limited. Reset links are single-use and expire after 1 hour, and the
  response never reveals whether an email address has an account.
- JWT access tokens last 30 minutes and refresh tokens rotate; logout blacklists the refresh token.
- Optional TOTP two-factor login (`/api/auth/mfa/`).
- Audit events are append-only (they can't be changed or deleted) and cover logins, data changes, payments, exports and downloads.
- Uploaded documents get random file names, are type- and size-checked, and are served only through the
  permission-checked API.
- Payments are **mock only**: no card data is collected or stored, and mock payments are labelled on screen and on receipts.

## Status
Done: shared foundation, the school (K-12) module, the university module, all frontend screens for every role,
PostgreSQL support and the Nginx/Gunicorn Docker deployment.
Next: screenshots and a demo walkthrough.
