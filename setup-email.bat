@echo off
cd /d "%~dp0backend"
".venv\Scripts\python.exe" scripts\setup_email.py
