#!/usr/bin/env python3
"""
ARPL Automated Test Suite Orchestrator
Runs all unit and integration test suites for ARPL Unified Platform.
"""

import sys
import os
import subprocess
from pathlib import Path

# Fix Windows cp1252 stdout encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ARPL_DIR = Path(__file__).parent.parent.resolve()


def main():
    print("=" * 65)
    print("  🚦 ARPL Unified Test Suite Orchestrator")
    print(f"  Working Directory: {ARPL_DIR}")
    print("=" * 65)

    test_files = [
        "tests/test_v2_features.py",
        "tests/test_detour_core.py",
        "tests/test_osm_loader.py"
    ]

    all_passed = True
    for test_file in test_files:
        test_path = ARPL_DIR / test_file
        if not test_path.exists():
            print(f"⚠️ Warning: Test file not found: {test_file}")
            continue

        print(f"\n▶️ Running {test_file} ...")
        cmd = [sys.executable, "-m", "pytest", str(test_path), "-v", "--no-header"]
        res = subprocess.run(cmd, cwd=str(ARPL_DIR))
        if res.returncode != 0:
            print(f"❌ Test suite FAILED: {test_file} (exit code {res.returncode})")
            all_passed = False
        else:
            print(f"✅ Test suite PASSED: {test_file}")

    print("\n" + "=" * 65)
    if all_passed:
        print("🎉 ALL ARPL TEST SUITES PASSED CLEANLY (100% SUCCESS)!")
        print("=" * 65)
        sys.exit(0)
    else:
        print("❌ ONE OR MORE TEST SUITES FAILED")
        print("=" * 65)
        sys.exit(1)

if __name__ == "__main__":
    main()
