@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8010 --reload
