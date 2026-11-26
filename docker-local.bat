@echo off
setlocal
cd /d "%~dp0"
title OmniEducation (Docker)
set "COMPOSE=docker compose -f docker-compose.prod.yml --env-file .env.prod"

docker info >nul 2>nul
if errorlevel 1 (
  echo Docker Desktop is not running.
  echo Open Docker Desktop, wait until it says "Engine running", then run this file again.
  pause
  exit /b 1
)

if exist ".env.prod" goto have_env
echo Creating .env.prod with new random passwords...
copy /y .env.prod.example .env.prod >nul
set "HTTP_PORT=80"
powershell -NoProfile -Command "if (Get-NetTCPConnection -State Listen -LocalPort 80 -ErrorAction SilentlyContinue) { exit 1 }"
if errorlevel 1 set "HTTP_PORT=8080"
powershell -NoProfile -Command "$f = '.env.prod'; $port = '%HTTP_PORT%'; $url = 'http://localhost'; if ($port -ne '80') { $url = $url + ':' + $port }; $pw = [guid]::NewGuid().ToString('N'); $sk = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N'); $lines = (Get-Content $f) -replace '^POSTGRES_PASSWORD=.*', ('POSTGRES_PASSWORD=' + $pw) -replace '^DJANGO_SECRET_KEY=.*', ('DJANGO_SECRET_KEY=' + $sk) -replace '^(FRONTEND_URL|CORS_ALLOWED_ORIGINS|DJANGO_CSRF_TRUSTED_ORIGINS)=.*', ('$1=' + $url); $lines += ('HTTP_PORT=' + $port); $lines += 'HTTPS_PORT=8443'; [IO.File]::WriteAllText((Join-Path (Get-Location) $f), (($lines -join [char]10) + [char]10))"
if errorlevel 1 goto fail

:have_env
set "PORT=80"
for /f "tokens=2 delims==" %%a in ('findstr /b "HTTP_PORT=" .env.prod') do set "PORT=%%a"
set "URL=http://localhost"
if not "%PORT%"=="80" set "URL=http://localhost:%PORT%"

echo.
echo Building and starting PostgreSQL, Django and Nginx.
echo The first time this downloads and builds everything: 5-15 minutes.
echo.
%COMPOSE% up -d --build
if errorlevel 1 goto fail

echo.
echo Waiting for the system to be ready (the first start also loads the demo data)...
set /a tries=0
:wait
set "CODE="
for /f %%c in ('curl -s -o nul -w "%%{http_code}" %URL%/api/auth/me/') do set "CODE=%%c"
if "%CODE%"=="401" goto ready
if "%CODE%"=="200" goto ready
set /a tries+=1
if %tries% GEQ 120 goto slow
timeout /t 5 /nobreak >nul
goto wait

:ready
echo.
echo ============================================================
echo  OmniEducation is running at %URL%
echo  Sign in with any demo account, password Demo@1234
echo  (for example registrar@omniu.edu or admin@sunrise.edu - see README.md)
echo.
echo  Stop:            docker compose -f docker-compose.prod.yml --env-file .env.prod stop
echo  Start again:     run this file
echo  Remove all data: docker compose -f docker-compose.prod.yml --env-file .env.prod down -v
echo ============================================================
start "" "%URL%"
pause
exit /b 0

:slow
echo.
echo The system did not answer within 10 minutes. Last backend messages:
%COMPOSE% logs --tail 40 backend
goto fail

:fail
echo.
echo Something went wrong. Copy the messages above and send them to Claude.
pause
exit /b 1
