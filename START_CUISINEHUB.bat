@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
 echo Python is not installed. Install Python 3.11+ and try again.
 pause
 exit /b 1
)
if not exist backend\.venv (
 echo Creating virtual environment...
 python -m venv backend\.venv
)
call backend\.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
if not exist backend\.env copy backend\.env.example backend\.env
start "CuisineHub Browser" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:5000"
python backend\app.py
pause
