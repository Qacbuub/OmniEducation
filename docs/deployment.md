# Deployment

OmniEducation runs as four parts:

```
Browser ──► Nginx (port 80/443) ──┬─► React app (built static files)
                                  ├─► /api/, /admin/  ──► Django + DRF on Gunicorn (port 8000) ──► PostgreSQL 16+
                                  ├─► /static/        (Django admin / API-docs assets, from collectstatic)
                                  └─► /media/tenant-logos/ (public logos only)
```

Student photos and documents are **not** served by Nginx. They are only downloadable through the API, which checks
that the person asking may see that student.

There are two ways to run it.

| | Local development (Windows) | Production-style (Docker) |
|---|---|---|
| Use for | building and demoing on one PC | a server, or a reproducible demo |
| Web server | Vite dev server :5173 | Nginx :80 (HTTPS-ready) |
| API server | Django `runserver` :8000 | Gunicorn :8000 (internal) |
| Database | PostgreSQL on the PC (SQLite as fallback) | PostgreSQL container |

---

## A. Production-style deployment with Docker

Needs Docker Desktop (Windows/macOS) or Docker Engine + Compose (Linux).

On Windows, **`docker-local.bat`** does all of the steps below: it creates `.env.prod` with random secrets (and
uses port 8080 if port 80 is taken), runs `docker compose up -d --build`, waits for the API and opens the site.

```bash
cp .env.prod.example .env.prod        # Windows: copy .env.prod.example .env.prod
# edit .env.prod: set POSTGRES_PASSWORD and DJANGO_SECRET_KEY (see the comments in the file)
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Open **http://localhost**. The first start:

1. waits for PostgreSQL, runs all migrations and `collectstatic`;
2. loads the demo school and university when `SEED_DEMO=true` and the database is empty (demo password `Demo@1234`);
3. starts Gunicorn behind Nginx.

Useful commands:

```bash
docker compose -f docker-compose.prod.yml logs -f backend        # API log (also shows "sent" emails)
docker compose -f docker-compose.prod.yml exec backend python manage.py createsuperuser
docker compose -f docker-compose.prod.yml exec backend python manage.py seed_demo --reset   # fresh demo data
docker compose -f docker-compose.prod.yml down                   # stop (data is kept in volumes)
```

Data lives in three named volumes: `pgdata` (database), `media` (uploads), `static` (collected static files).

### Environment variables (`.env.prod`)

| Variable | Purpose |
|---|---|
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | database created by the `db` container and used by the backend |
| `DJANGO_SECRET_KEY` | required; the backend refuses to start with the placeholder |
| `DJANGO_ALLOWED_HOSTS` | host names the site answers to, comma-separated |
| `FRONTEND_URL` | address users open; used in invitation and password-reset links |
| `CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | the same address (with scheme) |
| `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SECURE_COOKIES` | `false` for plain HTTP; `true` once HTTPS is on |
| `SEED_DEMO` | `true` loads demo data on an empty database |
| `EMAIL_BACKEND` (+ SMTP settings) | `console` prints emails to the log; use SMTP for real email |
| `SHOW_INVITE_LINKS` | show invitation links on screen (only while emails are not really sent) |

### On a cloud server, in one step (Oracle Cloud, DigitalOcean or any Ubuntu 22.04/24.04 server)

`deploy/server-setup.sh` does everything on a fresh Ubuntu server: adds swap on 1 GB machines, installs Docker and
Certbot, opens ports 80/443 in the server firewall, gets a free Let's Encrypt certificate, writes `.env.prod` with
new random secrets, and starts PostgreSQL, Django and Nginx with the demo data.

- **When creating the server:** paste [`deploy/cloud-init.sh`](../deploy/cloud-init.sh) into the *cloud-init
  script* (Oracle) or *User data* (DigitalOcean) box. The site is ready 10-20 minutes after the server starts;
  progress is in `/var/log/omniedu-setup.log`.
- **On an existing server:** `git clone https://github.com/Qacbuub/OmniEducation.git /opt/omniedu` then
  `sudo bash /opt/omniedu/deploy/server-setup.sh`.
- **Updating:** `cd /opt/omniedu && git pull && sudo bash deploy/server-setup.sh` (secrets and data are kept).

Without a domain the address is the server's IP with dashes plus `.sslip.io`, for example
`https://203-0-113-7.sslip.io` (a free DNS name that points at that IP). With your own domain, point its DNS at the
server and run the script with `DOMAIN=demo.example.com`. On Oracle Cloud, also allow TCP 80 and 443 in the
subnet's security list (the cloud firewall); the script opens them inside the server.

### Turning on HTTPS by hand

1. Put the certificate files in `deploy/certs/` as `fullchain.pem` and `privkey.pem`
   (for example from Let's Encrypt / certbot).
2. In `docker-compose.prod.yml`, uncomment the `./deploy/certs:/etc/nginx/certs:ro` line.
3. In `deploy/nginx/omniedu.conf`, uncomment the `return 301 https://…` line and the `listen 443` server block,
   and set `server_name`.
4. In `.env.prod`: `DJANGO_SECURE_SSL_REDIRECT=true`, `DJANGO_SECURE_COOKIES=true`, and use `https://` in
   `FRONTEND_URL`, `CORS_ALLOWED_ORIGINS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.
5. `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d`

With HTTPS on, Django also sends HSTS and marks cookies secure. Nginx adds `X-Content-Type-Options`,
`X-Frame-Options` and `Referrer-Policy` headers, rate-limits the sign-in endpoint, and limits uploads to 12 MB.

### Files

| File | What it does |
|---|---|
| `docker-compose.prod.yml` | the three services (`db`, `backend`, `web`) and their volumes |
| `backend/Dockerfile` | Python 3.12 image running Gunicorn as a non-root user |
| `backend/docker-entrypoint.sh` | waits for the database, migrates, collects static files, optional demo seed |
| `frontend/Dockerfile` | builds the React app, then serves it with Nginx |
| `deploy/nginx/omniedu.conf` | Nginx site: HTTP server, commented HTTPS server, login rate limit |
| `deploy/nginx/omniedu-app.inc` | routes shared by both servers (SPA fallback, `/api`, `/static`, logos, caching) |
| `deploy/server-setup.sh` | one-step setup/update of a Ubuntu server, with Let's Encrypt HTTPS |
| `deploy/cloud-init.sh` | paste-in startup script for a new cloud server (runs `server-setup.sh`) |
| `config/settings/prod.py` | production Django settings (DEBUG off, secure proxy headers, HSTS) |

---

## B. Local development on Windows

Double-click **`start-dev.bat`** in the project folder. It opens two Windows Terminal tabs:

- **Backend** (`run-backend.bat`): creates the Python environment, installs packages, connects to PostgreSQL
  (falls back to SQLite if it can't sign in), migrates, loads demo data the first time, and runs the API on
  http://127.0.0.1:8000.
- **Frontend** (`run-frontend.bat`): installs packages and runs the app on http://localhost:5173.

### Moving the local copy from SQLite to PostgreSQL

1. Install PostgreSQL 16 or newer for Windows (default options, port 5432) and remember the `postgres` password.
2. Double-click **`setup-postgres.bat`**. It asks for that password, creates the `omniedu` user and database
   (`backend/scripts/create_db.sql`), creates the tables, and offers to **copy everything from the SQLite file**
   (`python manage.py copy_data --source sqlite:///db.sqlite3`) so records you added are kept.
3. Restart the backend tab. It now says **"Connected to PostgreSQL"**.

The SQLite file stays in `backend/db.sqlite3` as a backup.

### Real email (Gmail)

Double-click **`setup-email.bat`**. It asks for the Gmail address and an App password (hidden), checks them with
Gmail, sends a test email and only then saves them to `backend\.env`. Restart the backend afterwards.
`test-email.bat` re-checks the saved settings step by step. New Gmail accounts are often refused App-password
sign-ins for their first days; use an established account.

### Tests

```bash
cd backend
.venv\Scripts\activate           # macOS/Linux: source .venv/bin/activate
pytest                           # 92 tests; on PostgreSQL the omniedu user needs CREATEDB
```
