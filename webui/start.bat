@echo off
REM Start PodQueue Web UI on Windows

echo Starting PodQueue Web UI...
echo ========================
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

echo Starting Streamlit Web UI...
echo.
echo Once the server starts, open your browser and go to:
echo   http://localhost:8501
echo.
echo To stop the server, close this window or press Ctrl+C.
echo.

streamlit run app.py