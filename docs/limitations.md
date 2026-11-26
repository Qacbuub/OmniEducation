# Known limitations

What the platform deliberately does not do yet, what is simulated, and what was not verified. Each item says what
would be needed to close it.

## Simulated by design

| Area | Current behaviour | To make it real |
|---|---|---|
| Online payments | **Mock only.** "Pay online" records a payment marked *MOCK – no real payment processed*; no card or bank data is ever collected or stored. Cash, bank transfer and mobile-money payments are recorded by finance staff. | Integrate a payment provider (e.g. M-Pesa, Stripe) through its hosted checkout and a verified webhook. |
| SMS | Not supported. Notifications are in-app, plus email for invitations, password resets and admission decisions. | Add an SMS gateway to `comms.services.notify`. |

## Functional gaps

- **No public application web page.** Applicants can apply through the public API
  (`POST /api/public/<institution>/apply/`) and check status with their reference code, but the React app only has
  the staff application form. A small public form page would close this. The public API also does not accept a
  photo; staff add it during review.
- **No bulk import.** Students, staff and marks are entered one by one (students can be exported to CSV). A CSV
  import with validation and a dry run would help institutions moving from another system.
- **Timetables are built by hand.** The server rejects clashes (a teacher or class booked twice), but it does not
  generate a timetable automatically.
- **Full sections have no waiting list.** Registration into a full section is refused; there is no waitlist or
  automatic promotion from one.
- **Fees are flat per plan.** University tuition per credit hour, instalment plans, late-payment penalties and
  refunds are not modelled. An invoice can be voided and a discount applied, but a payment cannot be reversed in
  the app.
- **One currency per institution.** Each tenant has a single currency.
- **Custom domains are stored, not routed.** The tenant comes from the signed-in account; the `domain` field on an
  institution is informational.
- **English only.** No translations yet; dates and money use one display format.
- **Staff cannot reset another user's password in the app.** Users reset their own (email link) or change it in
  *My profile*; a developer can use `python manage.py changepassword <email>` or the Django admin.

## Email

- Emails are sent during the request (no background queue or retry). A slow mail server adds a few seconds to the
  action that sends the email; a failed send is logged and does not block the action. A queue (Celery/RQ) is the
  production answer.
- Links in emails use `FRONTEND_URL`. On a developer PC that is `http://localhost:5173`, which only opens on that
  same computer. On a server it must be the public address.
- On a development machine the invitation link is also shown on screen (`SHOW_INVITE_LINKS`), so testing never
  depends on email. Production turns this off.

## Verification status

| What | Status |
|---|---|
| Backend tests | 89 automated tests (pytest) pass on SQLite and on PostgreSQL 16: tenancy, permissions, workflows, money, grades, security. |
| API smoke test | Every list endpoint opened as all 20 demo accounts on PostgreSQL: no server errors. |
| Frontend | No automated UI test suite. Every screen was opened as every demo role in a browser with no API or console errors, and the main end-to-end flows were exercised by hand. A static checker verifies imports, exports and icons. |
| Docker deployment | Files written; the entrypoint (migrate, collectstatic, demo seed) and Gunicorn with production settings were run against PostgreSQL. **The full `docker compose` stack with Nginx was not started**, because the build environment had no Docker daemon. |
| Load and accessibility | Not measured. Form fields have labels and controls are keyboard-reachable, but there has been no formal WCAG audit or load test. |
| Mock frontend mode | `VITE_USE_MOCK=true` (frontend without a backend) covers only the original screens, not the school/university modules added later. Use the real API. |

## Operations

- **Backups are manual:** pgAdmin → right-click the database → *Backup…*, or `pg_dump`. Schedule `pg_dump` (and
  copy the `media` folder) in production.
- **Uploads live on local disk** (`media/`). Several servers would need shared or object storage (e.g. S3).
- **The Django development server is used locally.** Production uses Gunicorn behind Nginx (see
  [deployment.md](deployment.md)).
- **Secrets live in `.env` files** (`backend/.env`, `.env.prod`), kept out of Git by `.gitignore`. A managed secret
  store is the production answer.
