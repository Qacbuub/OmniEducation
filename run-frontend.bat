@echo off
setlocal
cd /d "%~dp0frontend"
echo === OmniEducation frontend ===
where npm >nul 2>nul
if errorlevel 1 goto nonode
if not exist ".env" (
  echo VITE_API_URL=/api> .env
  echo VITE_USE_MOCK=false>> .env
)
if not exist "node_modules" (
  echo Installing npm packages...
  call npm install
  if errorlevel 1 goto fail
)
echo.
echo  App: http://localhost:5173
echo.
call npm run dev
goto :eof
:nonode
echo Node.js was not found. Install Node.js 20+ from https://nodejs.org/ then rerun.
goto :eof
:fail
echo npm install failed - see the error above.
