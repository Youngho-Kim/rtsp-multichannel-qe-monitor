@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo [INFO] Installing dependencies via python -m pip ...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if not exist ".env" (
    copy ".env.example" ".env" > nul
    echo [INFO] Created .env from .env.example
)
echo [DONE] Setup complete! Run run_monitor.bat to start.
pause
