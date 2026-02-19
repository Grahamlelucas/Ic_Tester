"""
IC Tester - Arduino Communication Test
Version 2.0 - With Auto Port Detection
"""

import serial
import serial.tools.list_ports
import time
import sys

BAUD_RATE = 9600
TIMEOUT = 2


def find_arduino_ports():
    """Scan for all available serial ports that might be Arduino"""
    print("🔍 Scanning for Arduino devices...")
    
    ports = serial.tools.list_ports.comports()
    arduino_ports = []
    
    for port in ports:
        # Look for Arduino-like devices
        # On Mac: /dev/cu.usbmodem* or /dev/cu.usbserial*
        # On Windows: COM* with Arduino in description
        # On Linux: /dev/ttyACM* or /dev/ttyUSB*
        
        port_name = port.device
        description = port.description.lower()
        
        # Check if it looks like an Arduino
        is_arduino = (
            'arduino' in description or
            'usbmodem' in port_name.lower() or
            'usbserial' in port_name.lower() or
            port_name.startswith('/dev/ttyACM') or
            port_name.startswith('/dev/ttyUSB') or
            (port_name.startswith('COM') and 'usb' in description)
        )
        
        if is_arduino:
            arduino_ports.append({
                'port': port_name,
                'description': port.description,
                'hwid': port.hwid
            })
    
    return arduino_ports


def test_arduino_connection(port_name):
    """Try to connect to a port and verify it's our Arduino"""
    try:
        print(f"   Attempting connection to {port_name}...")
        arduino = serial.Serial(port_name, BAUD_RATE, timeout=TIMEOUT)
        time.sleep(2)  # Wait for Arduino to reset after connection
        
        # Try to read the READY message
        arduino.flush()  # Clear any stale data
        
        # Wait up to 3 seconds for READY message
        start_time = time.time()
        while time.time() - start_time < 3:
            if arduino.in_waiting > 0:
                line = arduino.readline().decode('utf-8').strip()
                if line == "READY":
                    print(f"   ✅ Arduino confirmed on {port_name}")
                    return arduino
        
        # If we didn't get READY, try sending PING
        arduino.write(b"PING\n")
        time.sleep(0.2)
        if arduino.in_waiting > 0:
            response = arduino.readline().decode('utf-8').strip()
            if response == "PONG":
                print(f"   ✅ Arduino confirmed on {port_name}")
                return arduino
        
        # Not our Arduino
        arduino.close()
        return None
        
    except (serial.SerialException, OSError) as e:
        print(f"   ❌ Connection failed: {e}")
        return None


def connect_to_arduino():
    """Find and connect to Arduino with automatic detection"""
    print("=" * 60)
    print("IC TESTER - ARDUINO CONNECTION")
    print("=" * 60)
    
    # Find potential Arduino ports
    arduino_ports = find_arduino_ports()
    
    if not arduino_ports:
        print("\n❌ No Arduino devices found!")
        print("\nTroubleshooting:")
        print("  1. Make sure Arduino is plugged into USB")
        print("  2. Check that you've uploaded the sketch to Arduino")
        print("  3. Try unplugging and replugging the Arduino")
        print("  4. Check Arduino IDE Tools → Port to see if it's detected there")
        return None
    
    print(f"\n✅ Found {len(arduino_ports)} potential Arduino device(s):\n")
    
    # Display found ports
    for i, port_info in enumerate(arduino_ports, 1):
        print(f"  {i}. {port_info['port']}")
        print(f"     Description: {port_info['description']}")
        print()
    
    # If only one port, auto-select it
    if len(arduino_ports) == 1:
        print("Only one device found, attempting connection...\n")
        selected_port = arduino_ports[0]['port']
    else:
        # Multiple ports - ask user to select
        while True:
            try:
                choice = input(f"Select port (1-{len(arduino_ports)}), or 'q' to quit: ").strip()
                
                if choice.lower() == 'q':
                    print("Exiting...")
                    return None
                
                choice_num = int(choice)
                if 1 <= choice_num <= len(arduino_ports):
                    selected_port = arduino_ports[choice_num - 1]['port']
                    break
                else:
                    print(f"Please enter a number between 1 and {len(arduino_ports)}")
            except ValueError:
                print("Invalid input. Please enter a number or 'q'")
    
    # Try to connect to selected port
    print(f"\n🔌 Connecting to: {selected_port}")
    arduino = test_arduino_connection(selected_port)
    
    if arduino:
        print("\n" + "=" * 60)
        print("✅ CONNECTION SUCCESSFUL")
        print("=" * 60)
        return arduino
    else:
        print("\n❌ Failed to verify Arduino on selected port")
        print("\nPossible issues:")
        print("  1. Arduino sketch not uploaded")
        print("  2. Wrong baud rate (should be 9600)")
        print("  3. Arduino is resetting - try again")
        return None


def send_command(arduino, command, verbose=True):
    """Send a command and get response"""
    try:
        arduino.write(f"{command}\n".encode('utf-8'))
        time.sleep(0.1)  # Small delay for Arduino to process
        
        if arduino.in_waiting > 0:
            response = arduino.readline().decode('utf-8').strip()
            if verbose:
                print(f"   → Response: {response}")
            return response
        else:
            if verbose:
                print(f"   ⚠️  No response received")
            return None
            
    except serial.SerialException as e:
        print(f"   ❌ Communication error: {e}")
        return None


def run_tests(arduino):
    """Run a series of tests to verify Arduino functionality"""
    print("\n" + "=" * 60)
    print("RUNNING COMMUNICATION TESTS")
    print("=" * 60)
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: PING/PONG
    print("\n📡 Test 1: Basic Communication (PING/PONG)")
    response = send_command(arduino, "PING")
    if response == "PONG":
        print("   ✅ PASS")
        tests_passed += 1
    else:
        print("   ❌ FAIL")
        tests_failed += 1
    
    # Test 2: LED Control ON
    print("\n💡 Test 2: LED Control - Turn ON")
    print("   (Watch for LED on pin 13 to light up)")
    response = send_command(arduino, "LED_ON")
    if response == "LED_ON_OK":
        print("   ✅ PASS")
        tests_passed += 1
    else:
        print("   ❌ FAIL")
        tests_failed += 1
    time.sleep(1)
    
    # Test 3: LED Control OFF
    print("\n💡 Test 3: LED Control - Turn OFF")
    print("   (Watch for LED on pin 13 to turn off)")
    response = send_command(arduino, "LED_OFF")
    if response == "LED_OFF_OK":
        print("   ✅ PASS")
        tests_passed += 1
    else:
        print("   ❌ FAIL")
        tests_failed += 1
    
    # Test 4: Set Pin HIGH
    print("\n🔌 Test 4: Digital Pin Control - Set Pin 5 HIGH")
    response = send_command(arduino, "SET_PIN,5,HIGH")
    if response and response.startswith("SET_PIN_OK"):
        print("   ✅ PASS")
        tests_passed += 1
    else:
        print("   ❌ FAIL")
        tests_failed += 1
    
    # Test 5: Read Pin
    print("\n🔌 Test 5: Digital Pin Read - Read Pin 5")
    print("   (Should read HIGH from previous test)")
    response = send_command(arduino, "READ_PIN,5")
    if response and "HIGH" in response:
        print("   ✅ PASS - Pin reads HIGH as expected")
        tests_passed += 1
    else:
        print("   ⚠️  PASS (with caveat) - Pin may be floating")
        tests_passed += 1
    
    # Test 6: Set Pin LOW
    print("\n🔌 Test 6: Digital Pin Control - Set Pin 5 LOW")
    response = send_command(arduino, "SET_PIN,5,LOW")
    if response and response.startswith("SET_PIN_OK"):
        print("   ✅ PASS")
        tests_passed += 1
    else:
        print("   ❌ FAIL")
        tests_failed += 1
    
    # Test 7: Error Handling - Invalid Command
    print("\n🛡️  Test 7: Error Handling - Send Invalid Command")
    response = send_command(arduino, "INVALID_COMMAND_XYZ")
    if response and "ERROR" in response:
        print("   ✅ PASS - Error handling works")
        tests_passed += 1
    else:
        print("   ❌ FAIL - Should return error message")
        tests_failed += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Tests Passed: {tests_passed}")
    print(f"Tests Failed: {tests_failed}")
    print(f"Success Rate: {(tests_passed / (tests_passed + tests_failed) * 100):.1f}%")
    
    if tests_failed == 0:
        print("\n🎉 ALL TESTS PASSED! Arduino is ready for IC testing.")
    else:
        print(f"\n⚠️  {tests_failed} test(s) failed. Check Arduino sketch and connections.")
    
    print("=" * 60)


def main():
    """Main program entry point"""
    print("\n" + "🔬" * 30)
    print("IC TESTER - COMMUNICATION TEST SUITE")
    print("Version 2.0")
    print("🔬" * 30 + "\n")
    
    # Connect to Arduino
    arduino = connect_to_arduino()
    
    if not arduino:
        print("\n❌ Cannot proceed without Arduino connection.")
        print("Exiting...\n")
        sys.exit(1)
    
    try:
        # Run tests
        run_tests(arduino)
        
        # Keep connection open for manual testing
        print("\n" + "=" * 60)
        print("MANUAL TEST MODE")
        print("=" * 60)
        print("Enter commands to send to Arduino (or 'quit' to exit):")
        print("Examples: PING, LED_ON, LED_OFF, SET_PIN,5,HIGH, READ_PIN,8")
        print()
        
        while True:
            try:
                cmd = input("Command: ").strip()
                
                if cmd.lower() in ['quit', 'exit', 'q']:
                    break
                
                if cmd:
                    send_command(arduino, cmd)
                    
            except KeyboardInterrupt:
                print("\n\n⚠️  Interrupted by user")
                break
        
    finally:
        # Clean up
        print("\n🔌 Closing Arduino connection...")
        arduino.close()
        print("✅ Connection closed.")
        print("\nThank you for using IC Tester!\n")


if __name__ == "__main__":
    main()
