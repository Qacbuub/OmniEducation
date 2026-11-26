@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0backend"
echo === OmniEducation: switch the backend to PostgreSQL ===
echo.

REM ---------- 1. find psql (PostgreSQL's command-line tool) ----------
set "PSQL="
for /f "delims=" %%P in ('where psql 2^>nul') do if not defined PSQL set "PSQL=%%P"
if not defined PSQL (
  for /d %%D in ("%ProgramFiles%\PostgreSQL\*") do if exist "%%D\bin\psql.exe" set "PSQL=%%D\bin\psql.exe"
)
if not defined PSQL goto nopg
echo Found PostgreSQL tools: !PSQL!
echo.

REM ---------- 2. create the omniedu user and database ----------
echo PostgreSQL will now ask for the password of its "postgres" administrator.
echo This is the password you chose when you installed PostgreSQL. Typing is hidden.
echo.
"!PSQL!" -h 127.0.0.1 -p 5432 -U postgres -d postgres -v ON_ERROR_STOP=1 -q -f "scripts\create_db.sql"
if errorlevel 1 goto sqlfail
echo Database user "omniedu" and database "omniedu" are ready.
echo.

REM ---------- 3. point the backend at PostgreSQL and build the tables ----------
if not exist ".venv\Scripts\python.exe" goto novenv
if not exist ".env" copy ".env.example" ".env" >nul
findstr /b /c:"DATABASE_URL=postgres://omniedu:omniedu@127.0.0.1:5432/omniedu" ".env" >nul
if errorlevel 1 (
  echo DATABASE_URL=postgres://omniedu:omniedu@127.0.0.1:5432/omniedu>> ".env"
)
set "DATABASE_URL=postgres://omniedu:omniedu@127.0.0.1:5432/omniedu"
echo Creating the tables in PostgreSQL...
".venv\Scripts\python.exe" manage.py migrate
if errorlevel 1 goto fail

REM ---------- 4. bring the current data across, or start from fresh demo data ----------
".venv\Scripts\python.exe" -c "import os,django;from dotenv import load_dotenv;load_dotenv();os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.dev');django.setup();from core.models import Tenant;raise SystemExit(1 if Tenant.objects.exists() else 0)"
if errorlevel 1 (
  echo PostgreSQL already has data - nothing to copy.
  goto done
)
if not exist "db.sqlite3" goto done
echo.
echo You have data in the SQLite file (students you added, payments, grades...).
choice /c YN /m "Copy it into PostgreSQL? (N = start from fresh demo data instead)"
if errorlevel 2 goto done
echo Copying - this takes about a minute...
set "PYTHONUTF8=1"
".venv\Scripts\python.exe" manage.py copy_data --source sqlite:///db.sqlite3
if errorlevel 1 goto fail
REM Tell run-backend.bat the data is already there so it does not reload the demo.
type nul > ".seeded-postgres-v4"

:done
echo.
echo ==========================================================
echo  Done. The backend will use PostgreSQL from now on.
echo  Close the "Backend" tab and run start-backend-tab.bat
echo  (or run-backend.bat). It should say "Connected to PostgreSQL".
echo  The old SQLite file is kept as backend\db.sqlite3.
echo ==========================================================
pause
goto :eof

:nopg
echo PostgreSQL is not installed on this computer (psql was not found).
echo.
echo  1. Download PostgreSQL 16 for Windows:
echo     https://www.enterprisedb.com/downloads/postgres-postgresql-downloads
echo  2. Run the installer with the default options and port 5432.
echo     Remember the password you set for the "postgres" user.
echo  3. Run this file again.
echo.
echo  (With Docker Desktop instead: run "docker compose up -d db" in this folder;
echo   it creates the omniedu user and database itself, then run run-backend.bat.)
pause
goto :eof

:sqlfail
echo.
echo Could not create the database. Usually the postgres password was wrong,
echo or the PostgreSQL service is not running (Windows: Services, "postgresql-x64-16").
echo Run this file again to retry.
pause
goto :eof

:novenv
echo The backend has not been set up yet. Run run-backend.bat once first, then this file.
pause
goto :eof

:fail
echo.
echo Something went wrong - see the error above. Your SQLite data is untouched.
pause
goto :eof
