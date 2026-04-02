#!/usr/bin/env python3
"""
Build script for packaging the legacy desktop app.

This uses PyInstaller to turn the monolithic `ic_tester.py` entrypoint plus its
bundled chip definitions into a distributable folder/app so users do not need a
local Python environment.

Usage:
    python3 build_app.py

This will create:
    - Mac: dist/IC Tester Pro.app (double-click to run)
    - Windows: dist/IC Tester Pro.exe
"""

import subprocess
import sys
import platform
import shutil
from pathlib import Path

def build_app():
    """
    Build the distributable desktop application.

    Process:
    1. Detect host platform so PyInstaller data-path syntax is correct.
    2. Bundle the `chips/` JSON assets alongside the executable.
    3. Include serial/tkinter hidden imports that PyInstaller may miss.
    4. Run PyInstaller and print distribution guidance for the result.
    """
    
    print("=" * 60)
    print("IC Tester Pro - Build Script")
    print("=" * 60)
    
    # Determine platform
    system = platform.system()
    print(f"\nDetected platform: {system}")
    
    # Base PyInstaller command
    app_name = "IC Tester Pro"
    
    # Build command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", app_name,
        "--windowed",           # No console window
        "--onedir",             # Create a folder with all dependencies
        "--clean",              # Clean build cache
        "--noconfirm",          # Replace existing output without asking
        
        # Add the chip-definition database so the packaged app can still load
        # test vectors without requiring a separate repository checkout.
        "--add-data", f"chips{':' if system != 'Windows' else ';'}chips",
        
        # Hidden imports that PyInstaller might miss
        "--hidden-import", "serial",
        "--hidden-import", "serial.tools.list_ports",
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.scrolledtext",
        "--hidden-import", "tkinter.messagebox",
        "--hidden-import", "tkinter.font",
        
        # The main script
        "ic_tester.py"
    ]
    
    print("\nBuilding application...")
    print("This may take a few minutes...\n")
    
    # Run PyInstaller
    result = subprocess.run(cmd, capture_output=False)
    
    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("BUILD SUCCESSFUL!")
        print("=" * 60)
        
        if system == "Darwin":  # macOS
            app_path = Path("dist") / f"{app_name}.app"
            print(f"\n✅ Application created: {app_path}")
            print("\nTo run: Double-click 'IC Tester Pro.app' in the dist folder")
            print("\nTo distribute:")
            print("  1. Copy the entire 'dist/IC Tester Pro.app' to a USB drive")
            print("  2. Or zip it and share via email/cloud storage")
            print("  3. Recipients just double-click to run - no Python needed!")
        else:  # Windows
            exe_path = Path("dist") / app_name / f"{app_name}.exe"
            print(f"\n✅ Application created: {exe_path}")
            print("\nTo run: Double-click 'IC Tester Pro.exe' in the dist folder")
        
        print("\n⚠️  Note: The 'chips' folder with JSON files is bundled inside.")
        print("    Users can add more chip definitions to their local chips folder.")
    else:
        print("\n❌ Build failed! Check the error messages above.")
        return False
    
    return True


if __name__ == "__main__":
    build_app()
