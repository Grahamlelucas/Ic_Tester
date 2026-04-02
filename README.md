# IC Tester Pro

A GUI application for testing 74-series IC chips with either an Arduino Mega 2560 or an Arduino Uno R3.

The desktop app supports both boards, but the Arduino must be loaded with the matching firmware before use. If you switch between a Mega and an Uno, you must upload the correct `.ino` file to that board in the Arduino IDE first.

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
- **Arduino Mega 2560** for larger IC support
- **Arduino Uno R3** for smaller 14-pin IC testing
- Tkinter (included with Python)

## Features

- GUI interface for chip testing
- Supports both Arduino Mega 2560 and Arduino Uno R3
- Chip database with JSON definitions
- Session logging
- Build script for standalone executable

## Arduino Board Compatibility

This project supports two Arduino boards with automatic detection:

### Arduino Mega 2560 (Recommended)
- **Firmware**: `ic_tester_firmware/ic_tester_firmware.ino`
- **Pins**: 52 digital (2-53) + 16 analog (A0-A15)
- **Best for**: Testing 14-pin, 16-pin, 20-pin, and larger ICs
- **Use when**: You want the widest chip support and the fewest pin limitations

### Arduino Uno R3
- **Firmware**: `ic_tester_firmware_uno/ic_tester_firmware_uno.ino`
- **Pins**: 12 digital (2-13) + 6 analog (A0-A5)
- **Best for**: Testing 14-pin ICs (7400, 7404, 7408, etc.)
- **Use when**: You only need smaller chips and want to run the tester on an Uno
- **See**: `ic_tester_firmware_uno/README_UNO_R3.md` for detailed setup

The Python GUI automatically detects which board is connected and adjusts pin validation accordingly.

## Uploading the Correct Arduino Firmware

Before using the GUI, upload the correct firmware to the board you plan to connect:

- **Mega 2560**: open `ic_tester_firmware/ic_tester_firmware.ino` in Arduino IDE and upload it to the Mega
- **Uno R3**: open `ic_tester_firmware_uno/ic_tester_firmware_uno.ino` in Arduino IDE and upload it to the Uno

Important:

- The Python app does not flash the board for you
- Switching from Mega to Uno, or from Uno back to Mega, requires uploading the matching firmware to the actual Arduino first
- After the correct sketch is uploaded, connect the board to USB and run the GUI normally

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
