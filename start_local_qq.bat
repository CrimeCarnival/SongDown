@echo off
setlocal
cd /d "%~dp0"
set "WEB_DATA_DIR=%~dp0.web-data-qq"
set "SONGDOWN_PYTHON=python"
if exist "%~dp0.venv\Scripts\python.exe" set "SONGDOWN_PYTHON=%~dp0.venv\Scripts\python.exe"
echo SongDown - Local QQ mode
 echo Keep QQ Music running and signed in under the same Windows user.
echo Open http://127.0.0.1:8766 after the server starts.
echo If process access is denied: stop this server, then right-click this file
 echo and choose Run as administrator. Windows will ask you to confirm.
echo Keep this window open. Press Ctrl+C to stop the server.
echo.
"%SONGDOWN_PYTHON%" run_web.py --local-qq --host 127.0.0.1 --port 8766
if errorlevel 1 (
    echo.
    echo Startup failed. Check Python dependencies and whether port 8766 is in use.
    pause
)
