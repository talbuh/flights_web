@echo off
echo ========================================
echo   Starting Flight Search V2 (with Auth)
echo ========================================
echo.
cd /d "%~dp0v2_development"
echo Running from: %CD%
echo.
python app.py
pause


