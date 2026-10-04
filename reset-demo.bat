@echo off
REM Clears conversations, alerts, diary, audio and photos. Stop the backend first.
cd /d "%~dp0backend"
.venv\Scripts\python -m app.database.reset
