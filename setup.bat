@echo off
REM PodQueue Setup Script for Windows
REM This script will set up the entire PodQueue environment including the Web UI

echo PodQueue Setup Script for Windows
echo ================================
echo.

REM Check if we're in the correct directory
if not exist "scripts" (
    echo Error: Please run this script from the root of the PodQueue repository.
    echo Current directory: %CD%
    echo.
    echo Make sure you've cloned the repository and navigate to the project directory before running this script.
    echo.
    pause
    exit /b 1
)

echo Checking for required tools...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH.
    echo Please install Python 3 from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
) else (
    for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
    echo Found %PYTHON_VERSION%
)

REM Check if pip is installed
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: pip is not installed.
    echo Please install pip or upgrade Python.
    echo.
    pause
    exit /b 1
) else (
    for /f "tokens=*" %%i in ('pip --version') do set PIP_VERSION=%%i
    echo Found %PIP_VERSION%
)

echo.
echo Installing main dependencies...
pip install -r scripts\requirements.txt
if %errorlevel% neq 0 (
    echo Error: Failed to install main dependencies.
    echo.
    pause
    exit /b 1
)

echo.
echo Installing Web UI dependencies...
pip install -r webui\requirements.txt
if %errorlevel% neq 0 (
    echo Error: Failed to install Web UI dependencies.
    echo.
    pause
    exit /b 1
)

echo.
echo Checking for required system tools...
echo.

REM Check if yt-dlp is installed
yt-dlp --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Warning: yt-dlp is not installed or not in PATH.
    echo Please install yt-dlp from https://github.com/yt-dlp/yt-dlp#installation
    echo The Web UI will not be able to convert @username URLs without yt-dlp.
    echo.
) else (
    for /f "tokens=*" %%i in ('yt-dlp --version') do set YTDLP_VERSION=%%i
    echo Found yt-dlp version %YTDLP_VERSION%
)

REM Check if jq is installed
jq --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Warning: jq is not installed or not in PATH.
    echo Please install jq from https://stedolan.github.io/jq/
    echo The downloader script will not work without jq.
    echo.
) else (
    for /f "tokens=*" %%i in ('jq --version') do set JQ_VERSION=%%i
    echo Found jq version %JQ_VERSION%
)

echo.
echo Creating channels.json file if it doesn't exist...
if not exist "scripts\channels.json" (
    copy "scripts\channels.json.example" "scripts\channels.json" >nul
    echo Created scripts\channels.json from example file.
) else (
    echo scripts\channels.json already exists.
)

echo.
echo Setup complete!
echo ==============
echo.
echo To start the Web UI, run:
echo   webui\start.bat
echo.
echo Or manually run:
echo   cd webui
echo   streamlit run app.py
echo.
echo After starting the Web UI, open your browser and go to:
echo   http://localhost:8501
echo.
pause