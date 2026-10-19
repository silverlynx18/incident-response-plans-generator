#!/usr/bin/env python3
"""
ARPL Unified Production Desktop Launcher
Launches the ARPL Traffic Detour Analysis Suite with environment auto-detection,
pre-flight dependency validation, and browser management.
"""

import os
import sys
import subprocess
import webbrowser
import time
from pathlib import Path

# Fix Windows cp1252 stdout encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


ARPL_DIR = Path(r"C:\Users\Owen.Martin\OneDrive - Arup\Documents\GitHub\ARPL")
CONDA_BAT = Path(r"C:\Users\Owen.Martin\AppData\Local\miniforge3\condabin\conda.bat")
ENV_NAME = "arup-env"
PORT = 8501

def main():
    print("=" * 65)
    print("  🚦 ARPL Unified Traffic Detour Analysis Platform")
    print("  Production Desktop Runner (Workstation Maven Edition)")
    print("=" * 65)

    if not ARPL_DIR.exists():
        print(f"❌ Error: ARPL directory not found at: {ARPL_DIR}")
        sys.exit(1)

    # Validate Conda Environment
    if not CONDA_BAT.exists():
        print(f"❌ Error: Conda batch script not found at: {CONDA_BAT}")
        sys.exit(1)

    print(f"✅ Found Conda Environment runner: {CONDA_BAT}")
    print(f"📦 Environment Target: {ENV_NAME}")

    # Launch Streamlit via conda environment
    cmd = f'call "{CONDA_BAT}" activate {ENV_NAME} && streamlit run app.py --server.port {PORT}'
    print(f"🚀 Starting Streamlit application on http://localhost:{PORT} ...")

    # Open browser after a slight delay
    def open_browser():
        time.sleep(2.5)
        webbrowser.open(f"http://localhost:{PORT}")

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    try:
        subprocess.run(cmd, shell=True, cwd=str(ARPL_DIR), check=True)
    except KeyboardInterrupt:
        print("\n🛑 ARPL application stopped by user.")
    except Exception as e:
        print(f"\n❌ Error launching ARPL: {e}")

if __name__ == "__main__":
    main()
