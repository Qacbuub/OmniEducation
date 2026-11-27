@echo off
setlocal
cd /d "%~dp0"
title OmniEducation public link (Tailscale)
set "COMPOSE=docker compose -f docker-compose.prod.yml --env-file .env.prod"

set "TS=tailscale"
where tailscale >nul 2>nul
if errorlevel 1 set "TS=%ProgramFiles%\Tailscale\tailscale.exe"
"%TS%" version >nul 2>nul
if errorlevel 1 (
  echo Tailscale is not installed. Download it from https://tailscale.com/download, sign in, then run this again.
  goto stop
)
if not exist ".env.prod" (
  echo Start the system once with docker-local.bat first, then run this again.
  goto stop
)
docker info >nul 2>nul
if errorlevel 1 (
  echo Docker Desktop is not running. Open it, wait for "Engine running", then run this again.
  goto stop
)

set "HOST="
for /f "delims=" %%h in ('powershell -NoProfile -Command "try { $s = & '%TS%' status --json | ConvertFrom-Json; if ($s.BackendState -eq 'Running') { $s.Self.DNSName.TrimEnd('.') } } catch {}"') do set "HOST=%%h"
if not defined HOST (
  echo Tailscale is not signed in. Open Tailscale from the taskbar, sign in, then run this again.
  goto stop
)
set "PORT=80"
for /f "tokens=2 delims==" %%a in ('findstr /b "HTTP_PORT=" .env.prod') do set "PORT=%%a"

echo.
echo Your public address will be:  https://%HOST%
echo.
echo Switching on Tailscale Funnel. The first time, Tailscale may print a link to allow Funnel:
echo open it in your browser, click Enable, and this window continues by itself.
echo.
"%TS%" funnel --bg %PORT%
if errorlevel 1 (
  echo.
  echo Funnel did not start. Read the message above; if it asked you to enable Funnel or HTTPS,
  echo do that in the Tailscale admin page, then run this file again.
  goto stop
)

powershell -NoProfile -ExecutionPolicy Bypass -File deploy\set-public-host.ps1 -PublicHost "%HOST%" -Port "%PORT%"
if errorlevel 1 goto stop

echo.
echo Restarting the system with the public address...
%COMPOSE% up -d
if errorlevel 1 goto stop
%COMPOSE% restart web >nul

echo Waiting for the public address to answer (the very first time this can take up to 10 minutes)...
set /a tries=0
:wait
set "CODE="
for /f %%c in ('curl -s -o nul -w "%%{http_code}" https://%HOST%/api/auth/me/') do set "CODE=%%c"
if "%CODE%"=="401" goto ready
set /a tries+=1
if %tries% GEQ 72 goto slow
timeout /t 10 /nobreak >nul
goto wait

:ready
echo.
echo ============================================================
echo  OmniEducation is online at:  https://%HOST%
echo  Online application:          https://%HOST%/apply
echo  Anyone can open these while this laptop is on, awake,
echo  connected to the internet and Docker is running.
echo  Turn the public link off:    "%TS%" funnel reset
echo ============================================================
start "" "https://%HOST%"
pause
exit /b 0

:slow
echo.
echo The address does not answer yet. Tailscale's public DNS can take a few more minutes the first time:
echo try https://%HOST% in your browser later. Everything else is set up.
:stop
pause
exit /b 1
