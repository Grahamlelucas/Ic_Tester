# IC Tester Firmware - Arduino Uno R3 Edition

This is the Arduino Uno R3-compatible version of the IC Tester firmware. It provides the same functionality as the Mega 2560 version but with reduced pin count to match the Uno's hardware limitations.

## Hardware Specifications

### Arduino Uno R3 Pin Availability
- **Digital I/O Pins**: 12 pins (pins 2-13)
  - Pins 0-1 reserved for Serial communication
  - Pin 13 also used for onboard LED
- **Analog Input Pins**: 6 pins (A0-A5, mapped as digital pins 14-19)
- **Total Available**: 18 pins for IC testing

### Comparison with Mega 2560
| Feature | Mega 2560 | Uno R3 |
|---------|-----------|--------|
| Digital Pins | 52 (pins 2-53) | 12 (pins 2-13) |
| Analog Pins | 16 (A0-A15) | 6 (A0-A5) |
| Total Testing Pins | 68 | 18 |

## IC Compatibility

With 12 digital pins, the Uno R3 can test:
- ✅ **14-pin DIP ICs** (7400, 7404, 7408, 7432, 7486, etc.)
- ⚠️ **16-pin DIP ICs** (74LS161, 74LS193) - May require creative pin mapping
- ❌ **20-pin or larger ICs** - Insufficient pins

## Firmware Features

All features from the Mega 2560 version are preserved:
- ✅ Digital pin read/write operations
- ✅ Batch pin operations for efficiency
- ✅ Rapid sampling for signal stability analysis
- ✅ Timed reads for waveform capture
- ✅ Propagation delay measurement
- ✅ Analog voltage measurement (6 channels)
- ✅ TTL voltage zone classification (LOW/UNDEFINED/HIGH)
- ✅ Automatic board type detection

## Installation

### 1. Upload Firmware to Arduino Uno R3

1. Open Arduino IDE
2. Connect your Arduino Uno R3 via USB
3. Select **Tools → Board → Arduino Uno**
4. Select the correct **Port** (e.g., `/dev/cu.usbmodem*` on macOS)
5. Open `ic_tester_firmware_uno.ino`
6. Click **Upload** (→ button)
7. Wait for "Done uploading" message

### 2. Verify Installation

Open the Serial Monitor (Tools → Serial Monitor):
- Set baud rate to **9600**
- You should see: `READY`
- Type `STATUS` and press Enter
- Expected response: `STATUS_OK,UNO_R3,READY`

## Pin Mapping Guide

### Digital Pins (2-13)
Use these pins for IC input/output connections:
```
Pin 2  ──┐
Pin 3    │
Pin 4    │
Pin 5    ├─ Connect to IC pins
Pin 6    │
Pin 7    │
Pin 8    │
Pin 9    │
Pin 10   │
Pin 11   │
Pin 12   │
Pin 13 ──┘ (Also drives onboard LED)
```

### Analog Pins (A0-A5 / 14-19)
Use these for voltage measurement or additional digital I/O:
```
A0 (Pin 14) ──┐
A1 (Pin 15)   │
A2 (Pin 16)   ├─ Analog voltage measurement
A3 (Pin 17)   │  or digital I/O
A4 (Pin 18)   │
A5 (Pin 19) ──┘
```

## Python GUI Integration

The Python GUI automatically detects the board type:

1. **Automatic Detection**: When you connect, the GUI queries the Arduino and detects "UNO_R3"
2. **Pin Validation**: The GUI automatically validates pin numbers based on Uno R3 ranges
3. **Visual Feedback**: Connection panel shows:
   - Board type: "UNO R3"
   - Pin count: "(12 digital, 6 analog pins)"

### No Code Changes Required
The same Python application works with both Mega 2560 and Uno R3. Board detection is automatic.

## Command Protocol

All commands from the Mega 2560 version are supported with adjusted pin ranges:

### Basic Commands
- `PING` → `PONG`
- `STATUS` → `STATUS_OK,UNO_R3,READY`
- `VERSION` → `VERSION,9.0-UNO`
- `SET_PIN,<pin>,<HIGH|LOW>` (pin: 2-13 or 14-19)
- `READ_PIN,<pin>` (pin: 2-13 or 14-19)

### Advanced Commands
- `RAPID_SAMPLE,<pin>,<count>` - Stability analysis
- `TIMED_READ,<pin>,<interval_us>,<count>` - Waveform capture
- `SET_AND_TIME,<set_pin>,<state>,<read_pin>` - Propagation delay
- `ANALOG_READ,<pin>` - Voltage measurement (pins 14-19 only)
- `ANALOG_READ_PINS,<pin1>,<pin2>,...` - Batch analog read
- `ANALOG_RAPID_SAMPLE,<pin>,<count>` - Voltage distribution

## Troubleshooting

### "ERROR:INVALID_PIN"
- Uno R3 only supports pins 2-13 (digital) and 14-19 (analog)
- Check your pin mapping in the GUI

### "ERROR:NOT_ANALOG_PIN"
- Analog commands only work on pins 14-19 (A0-A5)
- Digital pins 2-13 cannot measure analog voltage

### Board Not Detected as UNO_R3
- Verify firmware upload was successful
- Check Serial Monitor shows `READY` on boot
- Try disconnecting and reconnecting
- Ensure baud rate is 9600

### IC Test Fails
- Verify IC has 14 pins or fewer
- Check all pin connections are secure
- Ensure IC is powered (if required)
- Use analog voltage measurement to verify signal levels

## Example: Testing a 7400 Quad NAND IC

The 7400 is a 14-pin IC, perfect for Uno R3:

1. **Physical Setup**:
   - Pin 1 (1A) → Arduino Pin 2
   - Pin 2 (1B) → Arduino Pin 3
   - Pin 3 (1Y) → Arduino Pin 4
   - ... (map remaining pins to Arduino pins 5-13)
   - Pin 7 (GND) → Arduino GND
   - Pin 14 (VCC) → Arduino 5V

2. **In GUI**:
   - Select "7400" from chip database
   - Map pins as shown above
   - Click "Run Test"
   - GUI automatically validates pins are in Uno R3 range

## Performance Notes

- **Digital Read Speed**: ~4μs per sample (same as Mega)
- **Analog Read Speed**: ~110μs per sample (same as Mega)
- **Memory**: Uno has 2KB SRAM vs Mega's 8KB (sufficient for this firmware)
- **Flash**: Uno has 32KB vs Mega's 256KB (firmware uses ~15KB)

## Upgrading to Mega 2560

If you need to test larger ICs (16-pin, 20-pin, 24-pin, etc.):

1. Get an Arduino Mega 2560
2. Upload `ic_tester_firmware/ic_tester_firmware.ino` (original firmware)
3. Connect to GUI - it will auto-detect as MEGA2560
4. Enjoy 52 digital + 16 analog pins!

## Technical Details

### Firmware Version
- **Version**: 9.0-UNO
- **Based on**: Mega 2560 v9.0 firmware
- **Differences**: Pin validation ranges only

### Pin Validation Logic
```cpp
bool isValidPin(int pin) {
  // Digital pins 2-13, Analog pins 14-19
  if (pin >= 2 && pin <= 13) return true;
  if (pin >= 14 && pin <= 19) return true;
  return false;
}

bool isAnalogPin(int pin) {
  // A0-A5 = digital pins 14-19
  return (pin >= 14 && pin <= 19);
}
```

### Analog Pin Mapping
- Arduino uses 0-based analog channels (A0-A5 = channels 0-5)
- Firmware converts: `analogRead(pin - 14)` where pin is 14-19
- This differs from Mega which uses: `analogRead(pin - 54)` where pin is 54-69

## License

MIT License - Same as main IC Tester project

## Support

For issues specific to Uno R3 compatibility:
1. Verify pin numbers are in valid range (2-13, 14-19)
2. Check Serial Monitor for error messages
3. Test with simple 14-pin ICs first
4. Consider upgrading to Mega 2560 for larger ICs
