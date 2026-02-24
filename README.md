# IC Tester Pro

A GUI application for testing 74-series IC chips using Arduino Mega 2560.

## Quick Start

### Windows

1. Install Python 3.8+ from [python.org](https://www.python.org/downloads/) (check "Add Python to PATH")
2. Clone or download this repository
3. Install dependencies:
   ```
   pip install pyserial
   ```
4. Run the application:
   ```
   python run_ic_tester.py
   ```

### macOS

1. Install Python 3.8+ (if not already installed)
2. Install dependencies:
   ```
   pip install pyserial
   ```
3. Run the application:
   ```
   python run_ic_tester.py
   ```

## Requirements

- Python 3.8+
- pyserial (Arduino communication)
- Arduino Mega 2560 with custom shield
- Tkinter (included with Python)

## Features

- GUI interface for chip testing
- Arduino Mega 2560 integration
- Chip database with JSON definitions
- Session logging
- Build script for standalone executable

## Project Structure

- `run_ic_tester.py` - Main entry point
- `ic_tester_app/` - Modular application code
- `chips/` - Chip definition files
- `ic_tester_lcd_combined/` - Arduino firmware
- `build_app.py` - Build standalone executable

## Building Standalone Executable

To create a portable version that doesn't require Python:

```
pip install pyinstaller
python build_app.py
```

This creates a standalone application in the `dist/` folder.

## License

MIT License
