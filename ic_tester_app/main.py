# ic_tester_app/main.py
# Last edited: 2026-01-19
# Purpose: Application entry point - launches the IC Tester GUI
# Dependencies: gui.app

"""
IC Tester Application Entry Point

This is the main entry point for the IC Tester application.
Run this file to start the GUI application.

Usage:
    python -m ic_tester_app.main
    
    OR from the project root:
    
    python run_ic_tester.py
"""

from .gui.app import ICTesterApp, main

if __name__ == "__main__":
    main()
