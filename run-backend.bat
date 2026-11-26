@echo off
setlocal
cd /d "%~dp0backend"
echo === OmniEducation backend ===
where python >nul 2>nul
if errorlevel 1 goto nopython

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"
echo Installing Python packages...
python -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto fail
if not exist ".env" copy ".env.example" ".env" >nul

REM --- Database: use PostgreSQL from .env if we can sign in to it, otherwise a local SQLite file ---
python -c "import os,django;from dotenv import load_dotenv;load_dotenv();os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.dev');django.setup();from django.db import connection;connection.ensure_connection()" >nul 2>nul
if not errorlevel 1 goto pgok
echo.
echo  Could not sign in to PostgreSQL with DATABASE_URL from backend\.env.
echo  Using a local SQLite file instead (backend\db.sqlite3).
echo  To use Postgres, create the omniedu user/database (see README) and rerun.
echo.
set "DATABASE_URL=sqlite:///db.sqlite3"
set "DBKIND=sqlite"
goto migrate
:pgok
echo Connected to PostgreSQL.
set "DBKIND=postgres"

:migrate
python manage.py makemigrations core people admissions finance comms school university
if errorlevel 1 goto fail
python manage.py migrate
if errorlevel 1 goto fail
REM Demo data version: bump when new modules add demo data, so it is reloaded once (resets demo records).
if not exist ".seeded-%DBKIND%-v4" (
  echo Loading demo data...
  python manage.py seed_demo --reset && type nul > ".seeded-%DBKIND%-v4"
)
echo.
echo  API:      http://127.0.0.1:8000/api/docs/
echo  Admin:    http://127.0.0.1:8000/admin/
echo.
python manage.py runserver 127.0.0.1:8000
goto :eof

:nopython
echo Python was not found. Install Python 3.12+ from https://www.python.org/downloads/ (tick "Add to PATH"), then rerun.
goto :eof
:fail
echo.
echo Backend setup failed - see the error above.
goto :eof
