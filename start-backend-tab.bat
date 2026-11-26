@echo off
REM Opens just the backend as a new tab in the current Windows Terminal window.
wt -w 0 new-tab --title "Backend (Django :8000)" -d "%~dp0." cmd /k "%~dp0run-backend.bat"
