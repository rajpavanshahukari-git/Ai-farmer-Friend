@echo off
REM One-time setup: Python venv + backend deps, frontend deps.
cd /d "%~dp0backend"
if not exist .venv python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
if not exist .env copy .env.example .env && echo Created backend\.env - add your GEMINI_API_KEY and MURF_API_KEY.
cd /d "%~dp0frontend"
call npm install
echo.
echo Setup complete. Run start.bat
