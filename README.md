# IC Tester Pro

A GUI application for testing 74-series IC chips using Arduino Mega 2560.

## Quick Start

### Windows

1. Install Python 3.8+ from [python.org](https://www.python.org/downloads/) (check "Add Python to PATH")
2. Clone or download this repository
3. Create a virtual environment and install dependencies:
   ```
   py -m venv .venv
   .\.venv\Scripts\python -m pip install -r requirements.txt
   ```
4. Run the application:
   ```
   .\.venv\Scripts\python run_ic_tester.py
   ```

### macOS

1. Install Python 3.8+ (if not already installed)
2. Create a virtual environment and install dependencies:
   ```
   python3 -m venv .venv
   ./.venv/bin/python -m pip install -r requirements.txt
   ```
3. Run the application:
   ```
   ./.venv/bin/python run_ic_tester.py
   ```

## Requirements

- Python 3.8+
- pyserial (Arduino communication)
- **Arduino Mega 2560** (recommended, 52 digital + 16 analog pins) OR
- **Arduino Uno R3** (12 digital + 6 analog pins, for 14-pin ICs)
- Tkinter (included with Python)

## Features

- GUI interface for chip testing
- Arduino Mega 2560 integration
- Chip database with JSON definitions
- Session logging
- Build script for standalone executable

## Arduino Board Compatibility

This project supports two Arduino boards with automatic detection:

### Arduino Mega 2560 (Recommended)
- **Firmware**: `ic_tester_firmware/ic_tester_firmware.ino`
- **Pins**: 52 digital (2-53) + 16 analog (A0-A15)
- **Best for**: Testing 14-pin, 16-pin, 20-pin, and larger ICs

### Arduino Uno R3
- **Firmware**: `ic_tester_firmware_uno/ic_tester_firmware_uno.ino`
- **Pins**: 12 digital (2-13) + 6 analog (A0-A5)
- **Best for**: Testing 14-pin ICs (7400, 7404, 7408, etc.)
- **See**: `ic_tester_firmware_uno/README_UNO_R3.md` for detailed setup

The Python GUI automatically detects which board is connected and adjusts pin validation accordingly.

## Project Structure

- `run_ic_tester.py` - Main entry point
- `ic_tester_app/` - Modular application code
- `chips/` - Chip definition files
- `ic_tester_firmware/` - Arduino Mega 2560 firmware
- `ic_tester_firmware_uno/` - Arduino Uno R3 firmware
- `build_app.py` - Build standalone executable

## Building Standalone Executable

To create a portable version that doesn't require Python:

```
python3 -m venv .venv
./.venv/bin/python -m pip install pyinstaller
./.venv/bin/python build_app.py
```

This creates a standalone application in the `dist/` folder.

## License

MIT License
