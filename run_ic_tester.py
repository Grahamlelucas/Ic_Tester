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
    python run_ic_tester.py

For the legacy single-file version, use:
    python ic_tester.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Launch the IC Tester application"""
    try:
        from ic_tester_app.gui.app import ICTesterApp
        
        print("Starting IC Tester Pro...")
        app = ICTesterApp()
        app.run()
        
    except ImportError as e:
        print(f"Error: Missing dependency - {e}")
        print("\nPlease install required packages:")
        print("  pip install pyserial")
        sys.exit(1)
    except Exception as e:
        print(f"Error starting application: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
