#!/usr/bin/env python3
# run_ic_tester.py
# Last edited: 2026-01-19
# Purpose: Entry point script to launch IC Tester application
# Dependencies: ic_tester_app

"""
IC Tester Pro - 74-Series Chip Testing System
==============================================

This script launches the IC Tester GUI application.

Requirements:
    - Python 3.8+
    - pyserial
    - tkinter (usually included with Python)

Usage:
    python3 run_ic_tester.py

For the legacy single-file version, use:
    python3 ic_tester.py
"""

import sys
import os

# Add the project root to `sys.path` so the launcher still works when users
# run this file directly instead of installing the package first.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """
    Launch the GUI application from the repository root.

    Process overview:
    1. Print a startup breadcrumb so double-click / terminal launches show progress.
    2. Import the real GUI entrypoint lazily so missing dependencies fail with a
       friendly message instead of a raw stack trace during module import.
    3. Construct the Tk application object and hand over control to its event loop.
    """
    try:
        print("Launching IC Tester Pro GUI...", flush=True)
        from ic_tester_app.gui.app import ICTesterApp

        print("Starting IC Tester Pro...", flush=True)
        app = ICTesterApp()
        app.run()
        
    except ImportError as e:
        print(f"Error: Missing dependency - {e}")
        print("\nPlease install required packages:")
        print("  python3 -m venv .venv")
        print("  ./.venv/bin/python -m pip install -r requirements.txt")
        print("  ./.venv/bin/python run_ic_tester.py")
        sys.exit(1)
    except Exception as e:
        print(f"Error starting application: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
