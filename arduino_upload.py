#!/usr/bin/env python3
"""
Arduino Auto-Upload Utility
Compiles and uploads Arduino sketches using Arduino CLI
"""

import subprocess
import os
import sys
import serial.tools.list_ports

# Configuration
SKETCH_PATH = os.path.join(os.path.dirname(__file__), "ic_tester_firmware", "ic_tester_firmware.ino")
BOARD_FQBN = "arduino:avr:mega"  # Mega 2560

def check_arduino_cli():
    """Check if Arduino CLI is installed"""
    try:
        result = subprocess.run(["arduino-cli", "version"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Arduino CLI found: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    
    print("❌ Arduino CLI not found!")
    print("\nTo install Arduino CLI on macOS:")
    print("  brew install arduino-cli")
    print("\nOr download from:")
    print("  https://arduino.github.io/arduino-cli/installation/")
    print("\nAfter installing, run:")
    print("  arduino-cli core install arduino:avr")
    return False

def find_mega_port():
    """Find connected Arduino Mega 2560"""
    ports = serial.tools.list_ports.comports()
    
    for port in ports:
        desc = port.description.lower()
        # Mega 2560 usually shows as these
        if 'mega' in desc or 'arduino' in desc or 'ch340' in desc or 'usb' in desc:
            print(f"📟 Found: {port.device} - {port.description}")
            return port.device
    
    # On Mac, look for common USB serial patterns
    for port in ports:
        if 'usbmodem' in port.device or 'usbserial' in port.device:
            print(f"📟 Found USB device: {port.device}")
            return port.device
    
    return None

def compile_sketch(sketch_path):
    """Compile the Arduino sketch"""
    print(f"\n🔨 Compiling: {os.path.basename(sketch_path)}...")
    
    result = subprocess.run([
        "arduino-cli", "compile",
        "--fqbn", BOARD_FQBN,
        sketch_path
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Compilation successful!")
        return True
    else:
        print("❌ Compilation failed!")
        print(result.stderr)
        return False

def upload_sketch(sketch_path, port):
    """Upload the compiled sketch to Arduino"""
    print(f"\n📤 Uploading to {port}...")
    
    result = subprocess.run([
        "arduino-cli", "upload",
        "--fqbn", BOARD_FQBN,
        "--port", port,
        sketch_path
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Upload successful!")
        print("🎉 Arduino is ready!")
        return True
    else:
        print("❌ Upload failed!")
        print(result.stderr)
        return False

def compile_and_upload(sketch_path=None, port=None):
    """Main function to compile and upload"""
    if sketch_path is None:
        sketch_path = SKETCH_PATH
    
    # Check Arduino CLI
    if not check_arduino_cli():
        return False
    
    # Check sketch exists
    if not os.path.exists(sketch_path):
        print(f"❌ Sketch not found: {sketch_path}")
        return False
    
    print(f"📁 Sketch: {sketch_path}")
    
    # Find port if not specified
    if port is None:
        port = find_mega_port()
        if port is None:
            print("❌ No Arduino Mega 2560 found!")
            print("Make sure it's connected via USB.")
            return False
    
    print(f"🔌 Port: {port}")
    
    # Compile
    if not compile_sketch(sketch_path):
        return False
    
    # Upload
    if not upload_sketch(sketch_path, port):
        return False
    
    return True

def install_arduino_cli():
    """Attempt to install Arduino CLI using Homebrew"""
    print("🍺 Attempting to install Arduino CLI via Homebrew...")
    
    # Check if brew is installed
    try:
        subprocess.run(["brew", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("❌ Homebrew not found!")
        print("Install Homebrew first: https://brew.sh")
        return False
    
    # Install arduino-cli
    result = subprocess.run(["brew", "install", "arduino-cli"], 
                          capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Arduino CLI installed!")
        
        # Install AVR core for Mega 2560
        print("📦 Installing Arduino AVR core...")
        subprocess.run(["arduino-cli", "core", "install", "arduino:avr"])
        return True
    else:
        print("❌ Installation failed!")
        print(result.stderr)
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("Arduino Auto-Upload Utility")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--install":
            install_arduino_cli()
        elif sys.argv[1] == "--help":
            print("Usage:")
            print("  python arduino_upload.py          # Compile and upload")
            print("  python arduino_upload.py --install # Install Arduino CLI")
            print("  python arduino_upload.py --help   # Show this help")
        else:
            # Assume it's a sketch path
            compile_and_upload(sys.argv[1])
    else:
        compile_and_upload()
