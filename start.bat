@echo off
setlocal
title Energy-Aware Life Planner
cd /d "%~dp0backend"

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 or newer is needed. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup. Then run start.bat again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First run: setting up Python packages. This needs internet once and takes a few minutes.
  python -m venv .venv || goto :fail
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
)

if not exist "..\frontend\dist\index.html" (
  echo The built web interface is missing: frontend\dist\index.html
  echo Run "npm install" and "npm run build" inside the frontend folder, then try again.
  pause
  exit /b 1
)

echo.
echo  Energy-Aware Life Planner is running at http://localhost:8000
echo  Keep this window open while you use it. Close it to stop the planner.
echo.
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8000"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
goto :eof

:fail
echo.
echo Setup failed. Read the messages above; the most common cause is no internet on the first run.
pause
exit /b 1
