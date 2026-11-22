@echo off
setlocal
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
  echo Run start.bat once first so the Python environment exists.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -q -r requirements-dev.txt
echo Running backend and AI tests...
".venv\Scripts\python.exe" -m pytest --cov=ai --cov-report=term
pause
