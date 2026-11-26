@echo off
cd /d "%~dp0backend"
echo === OmniEducation: email test ===
".venv\Scripts\python.exe" scripts\test_email.py %1
