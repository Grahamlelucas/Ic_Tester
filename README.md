# IC Tester Pro

A web-based application for testing 74-series IC chips with an Arduino Mega 2560.

The Arduino must be loaded with the Mega firmware before use. The web UI runs in your browser and communicates with the Arduino over USB serial.

## Quick Start (macOS)

1. **Upload firmware** to the Arduino Mega once (only needed the first time or after a firmware change):
   - Open `ic_tester_firmware/ic_tester_firmware.ino` in the Arduino IDE
   - Select board: **Arduino Mega 2560** and the correct port
   - Click Upload

2. **Install Python dependencies** (only needed once):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Start the web server:**
   ```bash
   source venv/bin/activate
   python -m ic_tester_app.web_ui.app
   ```

4. **Open the UI** in your browser: [http://127.0.0.1:5050](http://127.0.0.1:5050)

5. **Connect the Arduino** by clicking the Connect button in the UI — it auto-detects the port.

## Quick Start (Windows)

1. Upload firmware as above using Arduino IDE

2. Install dependencies:
   ```bat
   py -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Start the web server:
   ```bat
   venv\Scripts\activate
   python -m ic_tester_app.web_ui.app
   ```

4. Open [http://127.0.0.1:5050](http://127.0.0.1:5050) in your browser

## Stopping the Server

Press `Ctrl+C` in the terminal where the server is running.

## Requirements

- Python 3.8+
- Arduino Mega 2560 with firmware uploaded
- Dependencies in `requirements.txt` (Flask, Flask-SocketIO, pyserial)

## Features

- Browser-based UI — no desktop app installation required
- Manual pin control with real-time output reading
- Automated test sequences per chip
- Chip database with JSON definitions (`chips/` folder)
- Pin mapping per chip (`pin_mappings/` folder)
- Diagnostic reports with signal analysis
- Supports multiple 74-series chips

## LED Wiring Note

**Output pin LEDs must not be wired directly between the chip output and ground.** TTL outputs (like the 7490) have weak HIGH drive capability (~400μA) which cannot push enough current through a LED, causing incorrect LOW readings on the Arduino.

**Correct approach for output LEDs** — use an NPN transistor (e.g. 2N2222) as a buffer:
```
7490 output ──┬── Arduino pin (reads signal directly)
              └── 10kΩ ── Base (2N2222 center pin)
                          Collector ── LED ── 330Ω ── 5V
                          Emitter ── GND
```

**Input pin LEDs** (driven directly by the Arduino) work fine wired directly — the Arduino can source 20mA.

## Arduino Firmware Protocol

The Mega firmware (`ic_tester_firmware/ic_tester_firmware.ino`) uses these serial commands at 9600 baud:

| Command | Response | Description |
|---------|----------|-------------|
| `SET_PIN,pin,HIGH\|LOW` | `SET_PIN_OK,pin,state` | Drive a pin HIGH or LOW |
| `READ_PIN,pin` | `READ_PIN_OK,pin,HIGH\|LOW` | Read a pin's digital state |
| `SET_PINS,p1:s1,p2:s2,...` | `SET_PINS_OK,count` | Batch set multiple pins |
| `READ_PINS,p1,p2,...` | `READ_PINS_OK,p1:s1,p2:s2,...` | Batch read multiple pins |
| `STATUS` | `STATUS_OK,MEGA2560,READY` | Board health check |
| `PING` | `PONG` | Connectivity check |
| `VERSION` | `VERSION,9.0` | Firmware version |
| `CLEAR` | `CLEAR_OK` | Reset test state |

## Project Structure

```
ic_tester_app/
  web_ui/
    app.py              — Flask + SocketIO server (main backend)
    templates/
      index.html        — Web UI (single page)
  arduino/
    connection.py       — Serial connection manager (thread-safe)
    commands.py         — Arduino command helpers
  chips/
    providers/          — Chip definition loaders
  diagnostics/          — Test report generators
chips/                  — Chip JSON definitions (7490.json, etc.)
pin_mappings/           — Saved pin mappings per chip
ic_tester_firmware/     — Arduino Mega 2560 firmware (.ino)
ic_tester_firmware_uno/ — Arduino Uno R3 firmware (.ino)
requirements.txt
```

## Uploading Firmware

The Python app does **not** flash the Arduino for you. Use the Arduino IDE:

- **Mega 2560**: `ic_tester_firmware/ic_tester_firmware.ino`
- **Uno R3**: `ic_tester_firmware_uno/ic_tester_firmware_uno.ino` (limited pin support)

After uploading, close the Arduino IDE serial monitor before starting the web server — both cannot hold the serial port at the same time.

## License

MIT License
