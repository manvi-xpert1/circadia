@echo off
rem Development mode: backend with auto-reload on :8000 and Vite with hot reload on :5173.
rem Needs Node.js 18+ for the frontend. Open http://localhost:5173 while developing.
setlocal
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
  echo Run start.bat once first so the Python environment exists.
  pause
  exit /b 1
)
start "Planner backend" cmd /k "cd /d backend && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
cd frontend
if not exist node_modules call npm install
npm run dev
