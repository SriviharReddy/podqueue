@echo off
REM Start PodQueue Web UI on Windows (Network Mode)

echo Starting PodQueue Web UI (Network Mode)...
echo ======================================
echo.

cd /d "%~dp0"

REM Check if we're in the webui directory
if not exist "app.py" (
    echo Error: Please run this script from the webui directory.
    echo Current directory: %CD%
    echo.
    pause
    exit /b 1
)

echo Starting Streamlit Web UI in network mode...
echo.
echo To access the Web UI from other devices on your network, use:
echo   http://YOUR_COMPUTER_IP:8501
echo.
echo To stop the server, close this window or press Ctrl+C.
echo.

streamlit run app.py --server.address 0.0.0.0 --server.port 8501