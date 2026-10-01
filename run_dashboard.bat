@echo off
echo Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo =======================================================
    echo ERROR: Python is not installed or not added to PATH!
    echo =======================================================
    echo To fix this:
    echo 1. Go to https://www.python.org/downloads/
    echo 2. Download the latest Python installer for Windows.
    echo 3. Run the installer.
    echo 4. IMPORTANT: Check the box "Add Python to PATH" at the bottom!
    echo 5. Click "Install Now".
    echo.
    echo After installing, try running this dashboard again.
    pause
    exit /b
)

echo Installing required packages...
python -m pip install -r requirements.txt

echo Starting Upstox Dashboard...
python -m streamlit run app.py
pause
