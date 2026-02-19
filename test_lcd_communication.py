#!/usr/bin/env python3
"""
Test script for LCD communication with Arduino
Tests the combined Arduino code with LCD display commands
"""

import serial
import serial.tools.list_ports
import time

def find_arduino_ports():
    """Scan for Arduino devices"""
    ports = serial.tools.list_ports.comports()
    arduino_ports = []
    
    for port in ports:
        port_name = port.device
        description = port.description.lower()
        
        is_arduino = (
            'arduino' in description or
            'ch340' in description or
            'cp210' in description or
            'ftdi' in description or
            'usb serial' in description or
            'usb2.0-serial' in description or
            'usb' in description.lower()
        )
        
        if is_arduino or port_name.startswith('/dev/cu.usbmodem') or port_name.startswith('/dev/ttyUSB'):
            arduino_ports.append(port_name)
    
    return arduino_ports

def test_lcd_communication():
    """Test LCD display commands"""
    print("🔍 Scanning for Arduino devices...")
    ports = find_arduino_ports()
    
    if not ports:
        print("❌ No Arduino devices found!")
        print("Please check:")
        print("  • Arduino is connected via USB")
        print("  • Drivers are installed")
        print("  • Cable is working")
        return
    
    print(f"✅ Found {len(ports)} device(s): {', '.join(ports)}")
    port = ports[0]  # Use first port
    
    try:
        print(f"🔌 Connecting to {port}...")
        arduino = serial.Serial(port, 9600, timeout=2)
        
        # Wait for Arduino to initialize
        time.sleep(2)
        
        # Check if Arduino is ready
        arduino.write(b"PING\n")
        time.sleep(0.5)
        
        if arduino.in_waiting > 0:
            response = arduino.readline().decode().strip()
            if response == "PONG":
                print("✅ Arduino communication established!")
            else:
                print(f"⚠️ Unexpected response: {response}")
        else:
            print("❌ No response from Arduino")
            return
        
        # Test LCD commands
        print("\n🧪 Testing LCD commands...")
        
        commands = [
            ("DISPLAY,READY", "Ready message"),
            ("DISPLAY,TESTING", "Testing message"),
            ("DISPLAY,PASS", "Pass message"),
            ("DISPLAY,FAIL", "Fail message"),
            ("DISPLAY_2LINE,Custom Line 1,Custom Line 2", "Two-line custom message"),
        ]
        
        for cmd, description in commands:
            print(f"  📟 Sending: {description}")
            arduino.write(f"{cmd}\n".encode())
            time.sleep(1)  # Wait for display to update
            
            # Check for response
            if arduino.in_waiting > 0:
                response = arduino.readline().decode().strip()
                print(f"     Response: {response}")
            else:
                print("     No response")
        
        # Test LED control
        print("\n💡 Testing LED control...")
        arduino.write(b"LED_ON\n")
        time.sleep(1)
        print("  LED should be ON")
        
        arduino.write(b"LED_OFF\n")
        time.sleep(0.5)
        print("  LED should be OFF")
        
        print("\n✅ All tests completed!")
        print("The LCD should have shown various messages.")
        print("Check your Arduino LCD shield to verify all messages appeared correctly.")
        
    except serial.SerialException as e:
        print(f"❌ Serial error: {e}")
        print("Try:")
        print("  • Closing Arduino IDE")
        print("  • Unplugging and replugging Arduino")
        print("  • Checking the correct port")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'arduino' in locals() and arduino.is_open:
            arduino.close()
            print("🔌 Connection closed")

if __name__ == "__main__":
    print("=" * 50)
    print("LCD Communication Test")
    print("=" * 50)
    test_lcd_communication()
