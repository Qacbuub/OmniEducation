# OmniEducation – Frontend (React)

React + Vite single-page app for the OmniEducation multi-tenant school & university platform, branded with OmniTeckno's identity.

## Run it

```bash
cd frontend
npm install
cp .env.example .env      # VITE_USE_MOCK=true runs without the backend
npm run dev               # http://localhost:5173
```

Sign in with any demo account (password `Demo@1234`) using the buttons under the login form.

| Setting | Meaning |
|---|---|
| `VITE_USE_MOCK=true` | Uses built-in synthetic demo data (`src/api/mock.js`) for the login and dashboards only. The module screens (classes, attendance, registration, gradebook, fees…) need the Django API. |
| `VITE_USE_MOCK=false` | Calls the Django API at `VITE_API_URL` (default `/api`, proxied to `127.0.0.1:8000` in dev). |

Production build: `npm run build` → static files in `dist/`, served by Nginx.

## Structure

```
src/
├── api/          client.js (JWT, token refresh, structured errors), mock.js (demo data)
├── auth/         AuthContext (session), guards (login + per-mode route protection)
├── config/       roles.js, navigation.js (role-aware menus), demoAccounts.js
├── components/
│   ├── layout/   AppShell – sidebar, top bar, notifications, user menu
│   └── ui/       Button, Card, StatCard, Badge, Field, Modal, DataTable, charts
├── pages/
│   ├── auth/     Login, ForgotPassword
│   ├── platform/ PlatformDashboard, Institutions, InstitutionDetail (tenant settings + admin invites), PlatformInvitations
│   ├── school/   SchoolDashboard, Classes, Attendance, Timetable, Homework, Marks, ReportCards, Promotions, MyChildren (guardian portal)
│   ├── university/ UniversityDashboard, Programs, Offerings, Registration, Timetable, Gradebook, GradeApprovals, Transcript, DegreeAudit
│   └── common/   Students, StudentDetail (documents, enrollment history), Admissions, FeeLedger, Staff, Announcements,
│                 Notifications, Reports, AuditLog, Settings, PersonalDashboard
├── styles/       tokens.css (brand design tokens), app.css
└── utils/        hooks (useApi, useDebounced), formatters
```

## Branding

Colours are sampled from the official OmniTeckno logo: **#00AEFF**, **#000000**, **#FFFFFF**.

- Buttons use brand blue with **black** text (8.5:1 contrast). White on #00AEFF fails WCAG at 2.5:1.
- Links and text on white use **#0077B3**, a darker shade of the brand blue (4.9:1).
- Green, amber and red appear only as status colours, never as brand colours.

## Accessibility

Skip link, visible focus rings, labelled form fields with linked error messages, `aria-current` on the active menu item, a modal that traps Escape and restores focus, and charts with screen-reader data tables. Reduced-motion is respected. Layouts are responsive at 1440, 1024 and 390 px.

## Security notes

- Hiding a menu item is only UX. The Django API enforces every permission and tenant boundary server-side.
- Users are routed to their own shell only: a school user who opens `/university` is redirected back.
- The platform super admin cannot open student records (the API returns 403).
