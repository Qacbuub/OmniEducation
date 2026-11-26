@echo off
setlocal
cd /d "%~dp0"
title Push OmniEducation to GitHub

where git >nul 2>nul
if errorlevel 1 (
  echo Git is not installed. Download it from https://git-scm.com/download/win
  echo then run this file again.
  pause
  exit /b 1
)

set "NAME="
for /f "delims=" %%a in ('git config --global user.name 2^>nul') do set "NAME=%%a"
if not defined NAME (
  set /p "NAME=Your name for commits: "
  call git config --global user.name "%%NAME%%"
)
set "MAIL="
for /f "delims=" %%a in ('git config --global user.email 2^>nul') do set "MAIL=%%a"
if not defined MAIL (
  set /p "MAIL=Your GitHub email: "
  call git config --global user.email "%%MAIL%%"
)

if not exist ".git" (
  git init -b main
  if errorlevel 1 goto fail
)

git add -A
if errorlevel 1 goto fail

git diff --cached --quiet
if errorlevel 1 (
  git commit -q -m "OmniEducation: school and university management platform" -m "React frontend, Django REST backend, PostgreSQL, Nginx and Docker deployment, tests, seed data and documentation." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01TCc6M1FYiN4WJiVnd441nL"
  if errorlevel 1 goto fail
  echo Commit created.
) else (
  echo Nothing new to commit.
)

git remote get-url origin >nul 2>nul
if errorlevel 1 (
  echo.
  echo Paste the repository address from GitHub,
  echo for example https://github.com/yourname/omnieducation.git
  set /p "URL=Repository address: "
  call git remote add origin "%%URL%%"
  if errorlevel 1 goto fail
)

echo.
echo Pushing. If a GitHub sign-in window opens, sign in there.
git push -u origin main
if errorlevel 1 goto fail

echo.
echo Done. Your code is on GitHub.
pause
exit /b 0

:fail
echo.
echo Something went wrong. Copy the messages above and send them to Claude.
pause
exit /b 1
