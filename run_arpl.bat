@echo off
REM ============================================================================
REM   🚦 ARPL Unified Traffic Detour Analysis Suite
REM   Production Windows Runner for Workstation
REM ============================================================================

setlocal
title ARPL Unified Detour Analysis Suite

set ARPL_DIR=C:\Users\Owen.Martin\OneDrive - Arup\Documents\GitHub\ARPL
set CONDA_BAT=C:\Users\Owen.Martin\AppData\Local\miniforge3\condabin\conda.bat
set ENV_NAME=arup-env

echo ============================================================================
echo   🚦 Launching ARPL Unified Detour Analysis Suite (Streamlit)
echo   Directory: %ARPL_DIR%
echo   Environment: %ENV_NAME%
echo ============================================================================

if not exist "%CONDA_BAT%" (
    echo [ERROR] Conda environment manager not found at %CONDA_BAT%
    pause
    exit /b 1
)

cd /d "%ARPL_DIR%"

echo Activating %ENV_NAME%...
call "%CONDA_BAT%" activate %ENV_NAME%

echo Starting Streamlit server...
streamlit run app.py --server.port 8501

pause
