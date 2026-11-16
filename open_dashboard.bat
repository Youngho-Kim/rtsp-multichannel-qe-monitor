@echo off
cd /d "%~dp0"
where pythonw > nul 2>&1
if %errorlevel%==0 (
    start "" pythonw manage.py web
) else (
    start "" /B python manage.py web
)
exit /b 0
