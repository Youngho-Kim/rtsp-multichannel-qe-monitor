@echo off
chcp 65001 > nul
cd /d "%~dp0"

:MENU
cls
echo ============================================================
echo   RTSP Multi-Channel QE Monitor (Windows 11)
echo ============================================================
echo   1. Virtual Camera Demo Mode (6s quick test + report)
echo   2. Start Live Monitoring (Background Watchdog)
echo   3. Discover ONVIF Cameras + Start Monitoring
echo   4. Check Process Status
echo   5. Stop Monitoring
echo   6. Generate Daily Report (Local Preview)
echo   7. Cleanup Logs older than 7 days (Dry-Run)
echo   8. Open Web Dashboard (http://127.0.0.1:8890)
echo   0. Exit
echo ============================================================
set /p CHOICE=Select menu [0-8]: 

if "%CHOICE%"=="1" goto DEMO
if "%CHOICE%"=="2" goto START_LIVE
if "%CHOICE%"=="3" goto DISCOVER
if "%CHOICE%"=="4" goto STATUS
if "%CHOICE%"=="5" goto STOP
if "%CHOICE%"=="6" goto REPORT
if "%CHOICE%"=="7" goto CLEAN
if "%CHOICE%"=="8" goto WEB
if "%CHOICE%"=="0" goto END
goto MENU

:DEMO
echo [INFO] Running Virtual Camera Demo (4 channels, 6 seconds)...
python manage.py start --discover --demo --duration 6
python manage.py report --no-slack
pause
goto MENU

:START_LIVE
python manage.py start
pause
goto MENU

:DISCOVER
python manage.py start --discover
pause
goto MENU

:STATUS
python manage.py status
pause
goto MENU

:STOP
python manage.py stop
pause
goto MENU

:REPORT
python manage.py report --no-slack
pause
goto MENU

:CLEAN
python manage.py clean --days 7 --dry-run
pause
goto MENU

:WEB
echo [INFO] Launching Web Dashboard at http://127.0.0.1:8890 ...
echo [INFO] Press Ctrl+C in this window to return or close dashboard.
python manage.py web
pause
goto MENU

:END
exit /b 0
