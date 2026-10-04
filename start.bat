@echo off
REM Starts FastAPI (port 8000) and the React dev server (port 5173), then opens the app.
cd /d "%~dp0"
start "Farmer Assistant - Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python -m uvicorn app.main:app --port 8000"
start "Farmer Assistant - Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"
timeout /t 6 /nobreak >nul
start http://localhost:5173
