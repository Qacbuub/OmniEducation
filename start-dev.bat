@echo off
REM Opens the OmniEducation backend and frontend in two terminal tabs.
set "ROOT=%~dp0"
where wt >nul 2>nul
if errorlevel 1 goto plain
wt -w new new-tab --title "Backend (Django :8000)" -d "%ROOT%." cmd /k "%ROOT%run-backend.bat" ; new-tab --title "Frontend (Vite :5173)" -d "%ROOT%." cmd /k "%ROOT%run-frontend.bat"
exit /b 0
:plain
REM Windows Terminal not installed: open two separate windows instead.
start "OmniEducation backend" cmd /k "%ROOT%run-backend.bat"
start "OmniEducation frontend" cmd /k "%ROOT%run-frontend.bat"
