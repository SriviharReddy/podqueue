@echo off
setlocal enabledelayedexpansion

echo PodQueue Windows Setup Script
echo ============================
echo.

:: Get repo root path
set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%"

echo Creating directories...
if not exist "data\downloads" mkdir "data\downloads"
if not exist "data\feeds" mkdir "data\feeds"
if not exist "data\artwork" mkdir "data\artwork"
if not exist "data\logs" mkdir "data\logs"
if not exist "data\state\channel_checks" mkdir "data\state\channel_checks"
echo ✓ Run directories created under .\data
echo.

:: Check python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH.
    echo Please install Python 3 and add it to your system PATH.
    pause
    exit /b 1
)

:: Create virtual environment
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    echo ✓ Virtual environment created
) else (
    echo ✓ Virtual environment already exists
)
echo.

:: Install dependencies
echo Installing dependencies...
call venv\Scripts\python.exe -m pip install --upgrade pip
call venv\Scripts\pip.exe install -r requirements.txt
if %errorlevel% neq 0 (
    echo Error: Failed to install dependencies.
    pause
    exit /b 1
)
echo ✓ Dependencies installed
echo.

:: Create .env from template
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        :: Generate random secret using Python
        for /f "tokens=*" %%i in ('venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(16))"') do set "RAND_SECRET=%%i"
        
        :: Replace SESSION_SECRET in .env using Python to avoid batch string replacement issues
        venv\Scripts\python.exe -c "import os; content = open('.env', 'r', encoding='utf-8').read().replace('SESSION_SECRET=changeme', 'SESSION_SECRET=%RAND_SECRET%'); open('.env', 'w', encoding='utf-8').write(content)"
        echo ✓ Created .env from template (with auto-generated SESSION_SECRET)
    ) else (
        echo ⚠ Warning: .env.example not found. Creating manual .env placeholder.
        echo BASE_URL=http://localhost:8000> .env
        echo ADMIN_PASSWORD=changeme>> .env
        for /f "tokens=*" %%i in ('venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(16))"') do set "RAND_SECRET=%%i"
        echo SESSION_SECRET=!RAND_SECRET!>> .env
    )
    echo   IMPORTANT: Please update ADMIN_PASSWORD and BASE_URL in the .env file!
) else (
    echo ✓ .env already exists
)

:: Create empty channels.json
if not exist "data\channels.json" (
    echo []> data\channels.json
    echo ✓ Created empty data\channels.json
)

:: Create cookies.txt placeholder
if not exist "cookies.txt" (
    echo # Place YouTube cookies here> cookies.txt
    echo ✓ Created cookies.txt placeholder
)
echo.

echo ======================================
echo Setup complete!
echo ======================================
echo.
set /p START_SERVER="Would you like to start the PodQueue server now? (y/n): "
if /i "%START_SERVER%"=="y" (
    echo Starting PodQueue server...
    call venv\Scripts\uvicorn.exe podqueue.api.main:app --host 0.0.0.0 --port 8000
) else (
    echo You can start the server later by running:
    echo   venv\Scripts\uvicorn.exe podqueue.api.main:app --host 0.0.0.0 --port 8000
)
pause
