@echo off
REM ARPL V1.6.2 Portable Quick Start Script for Windows
REM This script sets up and runs the ARPL V1.6.2 application

echo 🚀 ARPL V1.6.2 Portable Quick Start
echo ====================================

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed. Please install Python 3.8 or higher.
    pause
    exit /b 1
)

REM Check if pip is installed
pip --version >nul 2>&1
if errorlevel 1 (
    echo ❌ pip is not installed. Please install pip.
    pause
    exit /b 1
)

echo ✅ Python and pip found

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔧 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo 📚 Installing dependencies...
pip install -r requirements.txt

REM Check if installation was successful
if errorlevel 1 (
    echo ❌ Failed to install dependencies
    pause
    exit /b 1
)

echo ✅ Dependencies installed successfully

echo.
echo 📡 Note: OSM network data will be downloaded automatically as needed
echo 🌐 Starting ARPL V1.6.2...
echo 📱 Application will be available at: http://localhost:8501
echo 🛑 Press Ctrl+C to stop the application
echo.

streamlit run app.py --server.port 8501

pause

