#!/bin/sh
# Prepares the database and static files, then starts the command (Gunicorn by default).
set -e

echo "Waiting for PostgreSQL..."
python - <<'PY'
import time, django
from django.db import connection
django.setup()
for attempt in range(30):
    try:
        connection.ensure_connection()
        break
    except Exception as exc:  # database container still starting
        time.sleep(2)
else:
    raise SystemExit("PostgreSQL did not become available.")
PY

python manage.py migrate --noinput
python manage.py collectstatic --noinput --verbosity 0

# Demo data only on a brand-new database, and only when asked for (SEED_DEMO=true).
if [ "${SEED_DEMO:-false}" = "true" ]; then
  python - <<'PY'
import django
django.setup()
from core.models import Tenant
from django.core.management import call_command
if Tenant.objects.exists():
    print("Database already has data: demo seed skipped.")
else:
    call_command("seed_demo")
PY
fi

exec "$@"
