"""
IC Tester - Full Testing System with GUI
Version 4.0 - Modern UI with Cross-Platform Support
"""

import serial
import serial.tools.list_ports
import time
import json
import os
import platform
from pathlib import Path
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, font as tkfont
import threading
import customtkinter as ctk

# Configure CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# =============================================================================
# THEME CONFIGURATION - Cross-platform color scheme
# =============================================================================
class Theme:
    """Modern color theme for the application"""
    # Main colors
    BG_DARK = "#1a1a2e"
    BG_MEDIUM = "#16213e"
    BG_LIGHT = "#0f3460"
    BG_CARD = "#1f2940"
    
    # Accent colors
    ACCENT_PRIMARY = "#4361ee"
    ACCENT_SUCCESS = "#06d6a0"
    ACCENT_ERROR = "#ef476f"
    ACCENT_WARNING = "#ffd166"
    ACCENT_INFO = "#118ab2"
    
    # Text colors
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#a0aec0"
    TEXT_MUTED = "#718096"
    
    # Status colors
    CONNECTED = "#06d6a0"
    DISCONNECTED = "#ef476f"
    PENDING = "#ffd166"
    
    # Fonts - cross-platform
    @staticmethod
    def get_fonts():
        system = platform.system()
        if system == "Darwin":  # macOS
            return {
                'heading': ('SF Pro Display', 24, 'bold'),
                'subheading': ('SF Pro Display', 14, 'bold'),
                'body': ('SF Pro Text', 11),
                'mono': ('SF Mono', 10),
                'button': ('SF Pro Text', 11, 'bold'),
                'small': ('SF Pro Text', 9),
            }
        elif system == "Windows":
            return {
                'heading': ('Segoe UI', 22, 'bold'),
                'subheading': ('Segoe UI', 13, 'bold'),
                'body': ('Segoe UI', 10),
                'mono': ('Consolas', 10),
                'button': ('Segoe UI', 10, 'bold'),
                'small': ('Segoe UI', 9),
            }
        else:  # Linux and others
            return {
                'heading': ('Ubuntu', 22, 'bold'),
                'subheading': ('Ubuntu', 13, 'bold'),
                'body': ('Ubuntu', 10),
                'mono': ('Ubuntu Mono', 10),
                'button': ('Ubuntu', 10, 'bold'),
                'small': ('Ubuntu', 9),
            }


class ArduinoConnection:
    """Handles Arduino serial communication"""
    
    def __init__(self):
        self.arduino = None
        self.connected = False
        
    def find_arduino_ports(self):
        """Scan for Arduino devices"""
        ports = serial.tools.list_ports.comports()
        arduino_ports = []
        
        for port in ports:
            port_name = port.device
            description = port.description.lower()
            
            is_arduino = (
                'arduino' in description or
                'usbmodem' in port_name.lower() or
                'usbserial' in port_name.lower() or
                port_name.startswith('/dev/ttyACM') or
                port_name.startswith('/dev/ttyUSB') or
                (port_name.startswith('COM') and 'usb' in description)
            )
            
            if is_arduino:
                arduino_ports.append(port_name)
        
        return arduino_ports
    
    def connect(self, port):
        """Connect to Arduino on specified port"""
        try:
            self.arduino = serial.Serial(port, 9600, timeout=2)
            time.sleep(2)  # Wait for Arduino reset
            
            # Wait for READY message
            start_time = time.time()
            while time.time() - start_time < 3:
                if self.arduino.in_waiting > 0:
                    line = self.arduino.readline().decode('utf-8').strip()
                    if line == "READY":
                        self.connected = True
                        return True
            
            # Try PING if no READY
            self.send_command("PING")
            response = self.read_response()
            if response == "PONG":
                self.connected = True
                return True
            
            self.arduino.close()
            return False
            
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    def send_command(self, command):
        """Send command to Arduino"""
        if not self.connected:
            return False
        try:
            self.arduino.write(f"{command}\n".encode('utf-8'))
            return True
        except:
            return False
    
    def read_response(self, timeout=0.5):
        """Read response from Arduino"""
        if not self.connected:
            return None
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.arduino.in_waiting > 0:
                return self.arduino.readline().decode('utf-8').strip()
            time.sleep(0.01)
        return None
    
    def disconnect(self):
        """Close Arduino connection"""
        if self.arduino:
            self.arduino.close()
        self.connected = False


class ChipDatabase:
    """Loads and manages chip definitions"""
    
    def __init__(self, chips_dir="chips"):
        self.chips_dir = Path(chips_dir)
        self.chips = {}
        self.load_all_chips()
    
    def load_all_chips(self):
        """Load all chip definition files"""
        if not self.chips_dir.exists():
            self.chips_dir.mkdir()
            print(f"Created chips directory: {self.chips_dir}")
            return
        
        for json_file in self.chips_dir.glob("*.json"):
            try:
                with open(json_file, 'r') as f:
                    chip_data = json.load(f)
                    chip_id = chip_data['chipId']
                    self.chips[chip_id] = chip_data
                    print(f"Loaded chip: {chip_id}")
            except Exception as e:
                print(f"Error loading {json_file}: {e}")
    
    def get_chip(self, chip_id):
        """Get chip definition by ID"""
        return self.chips.get(chip_id)
    
    def get_all_chip_ids(self):
        """Get list of all available chip IDs"""
        return sorted(self.chips.keys())


class ICTester:
    """Main IC testing logic"""
    
    def __init__(self, arduino_conn, chip_db):
        self.arduino = arduino_conn
        self.chip_db = chip_db
    
    def verify_power(self, chip_data, progress_callback=None):
        """
        Verify that power (VCC/GND) is properly configured for the chip.
        Returns tuple: (success: bool, message: str)
        """
        pinout = chip_data.get('pinout', {})
        mapping = chip_data.get('arduinoMapping', {})
        
        # Check if power pins are defined in chip data
        vcc_pin = pinout.get('vcc')
        gnd_pin = pinout.get('gnd')
        
        if not vcc_pin or not gnd_pin:
            return (False, "Chip definition missing VCC or GND pin configuration")
        
        # Check if power mapping exists
        power_mapping = mapping.get('power', {})
        if not power_mapping:
            return (False, "Chip definition missing power pin mapping to Arduino")
        
        # Verify VCC is mapped to 5V
        vcc_mapping = power_mapping.get(str(vcc_pin))
        if vcc_mapping != "5V":
            return (False, f"VCC (pin {vcc_pin}) should be connected to Arduino 5V, got: {vcc_mapping}")
        
        # Verify GND is mapped to GND
        gnd_mapping = power_mapping.get(str(gnd_pin))
        if gnd_mapping != "GND":
            return (False, f"GND (pin {gnd_pin}) should be connected to Arduino GND, got: {gnd_mapping}")
        
        if progress_callback:
            progress_callback(f"⚡ Power config: VCC=pin {vcc_pin}→5V, GND=pin {gnd_pin}→GND")
        
        # Send a test command to verify Arduino is responding (power check)
        self.arduino.send_command("PING")
        response = self.arduino.read_response()
        
        if not response or "PONG" not in response:
            return (False, "Arduino not responding - check USB connection and power")
        
        if progress_callback:
            progress_callback("⚡ Arduino power verified - responding to commands")
        
        return (True, "Power configuration verified")
    
    def verify_pin_connections(self, chip_data, progress_callback=None):
        """
        GENERIC pin verification - works with any chip by using first 2 tests from JSON.
        Uses REDUNDANT READS (3x voting) for reliability.
        Returns tuple: (success: bool, message: str, problem_pins: list)
        """
        mapping = chip_data.get('arduinoMapping', {}).get('io', {})
        pinout = chip_data.get('pinout', {})
        test_sequence = chip_data.get('testSequence', {})
        tests = test_sequence.get('tests', [])
        
        if not mapping:
            return (False, "No I/O pin mapping found in chip definition", [])
        
        if len(tests) < 2:
            return (False, "Chip needs at least 2 tests defined for verification", [])
        
        problem_pins = []
        chip_id = chip_data.get('chipId', 'Unknown')
        
        if progress_callback:
            progress_callback(f"🔌 Running pin verification for {chip_id}...")
        
        # Build lookups for pin names and types
        input_pins = {}
        output_pins = {}
        
        for input_pin in pinout.get('inputs', []):
            input_pins[input_pin['name']] = input_pin['pin']
        for output_pin in pinout.get('outputs', []):
            output_pins[output_pin['name']] = output_pin['pin']
        
        # Helper to set a pin with verification
        def set_pin(arduino_pin, state):
            for attempt in range(3):
                self.arduino.send_command(f"SET_PIN,{arduino_pin},{state}")
                response = self.arduino.read_response()
                if response and "SET_PIN_OK" in response:
                    return True
                time.sleep(0.05)
            return False
        
        # Helper to set all inputs to a specific state from test definition
        def set_inputs_from_test(test_inputs):
            for pin_name, state in test_inputs.items():
                chip_pin = input_pins.get(pin_name)
                if chip_pin:
                    arduino_pin = mapping.get(str(chip_pin))
                    if arduino_pin:
                        if not set_pin(arduino_pin, state):
                            if progress_callback:
                                progress_callback(f"    ⚠️ Failed to set {pin_name} to {state}")
                        time.sleep(0.03)
        
        # Helper to read a single pin with VOTING (3 reads, take majority)
        def read_pin_voted(arduino_pin):
            reads = []
            for _ in range(3):
                self.arduino.send_command(f"READ_PIN,{arduino_pin}")
                response = self.arduino.read_response()
                if response and "HIGH" in response:
                    reads.append("HIGH")
                elif response and "LOW" in response:
                    reads.append("LOW")
                else:
                    reads.append("ERROR")
                time.sleep(0.03)
            
            # Majority vote
            high_count = reads.count("HIGH")
            low_count = reads.count("LOW")
            error_count = reads.count("ERROR")
            
            if error_count >= 2:
                return "ERROR"
            elif high_count > low_count:
                return "HIGH"
            else:
                return "LOW"
        
        # Helper to read all output pins with voting
        def read_all_outputs():
            results = {}
            for pin_name, chip_pin in output_pins.items():
                arduino_pin = mapping.get(str(chip_pin))
                if arduino_pin:
                    results[pin_name] = read_pin_voted(arduino_pin)
            return results
        
        # Run first 2 tests from chip's test sequence for verification
        test1 = tests[0]
        test2 = tests[1]
        
        # ===== STATE 1: First test =====
        if progress_callback:
            progress_callback(f"  STATE 1: {test1.get('description', 'Test 1')}...")
        
        set_inputs_from_test(test1.get('inputs', {}))
        time.sleep(0.25)
        state1 = read_all_outputs()
        expected1 = test1.get('expectedOutputs', {})
        
        # Log output names dynamically
        output_str = ", ".join([f"{name}={state1.get(name,'?')}" for name in output_pins.keys()])
        if progress_callback:
            progress_callback(f"    Read: {output_str}")
        
        # ===== STATE 2: Second test =====
        if progress_callback:
            progress_callback(f"  STATE 2: {test2.get('description', 'Test 2')}...")
        
        set_inputs_from_test(test2.get('inputs', {}))
        time.sleep(0.25)
        state2 = read_all_outputs()
        expected2 = test2.get('expectedOutputs', {})
        
        output_str = ", ".join([f"{name}={state2.get(name,'?')}" for name in output_pins.keys()])
        if progress_callback:
            progress_callback(f"    Read: {output_str}")
        
        # ===== CHECK: Did any outputs change between states? =====
        any_changed = False
        for pin_name in output_pins.keys():
            if state1.get(pin_name) != state2.get(pin_name):
                any_changed = True
                break
        
        if not any_changed:
            if progress_callback:
                progress_callback("  ❌ No outputs changed between states - CHIP NOT RESPONDING!")
                progress_callback("     Check VCC and GND connections.")
            return (False, "Chip not responding - check VCC and GND connections!", [{
                'chip_pin': 'ALL',
                'arduino_pin': 'N/A',
                'name': 'ALL OUTPUTS',
                'error': 'No outputs changed between test states',
                'expected': 'Outputs should change',
                'actual': 'No change detected'
            }])
        
        if progress_callback:
            progress_callback("  ✓ Chip is responding (outputs changed)")
        
        # ===== VERIFY ALL OUTPUT PINS =====
        if progress_callback:
            progress_callback("  Verifying all output pins...")
        
        for pin_name, chip_pin in output_pins.items():
            arduino_pin = mapping.get(str(chip_pin))
            if not arduino_pin:
                continue
            
            val1 = state1.get(pin_name, 'ERROR')
            val2 = state2.get(pin_name, 'ERROR')
            exp1 = expected1.get(pin_name, 'LOW')
            exp2 = expected2.get(pin_name, 'LOW')
            
            # Check for errors
            if 'ERROR' in [val1, val2]:
                problem_pins.append({
                    'chip_pin': chip_pin,
                    'arduino_pin': arduino_pin,
                    'name': pin_name,
                    'error': 'No response from pin',
                    'expected': f'{exp1}/{exp2}',
                    'actual': f'{val1}/{val2}'
                })
                if progress_callback:
                    progress_callback(f"  ❌ {pin_name} (pin {chip_pin}): ERROR - Check wire to Arduino pin {arduino_pin}!")
            elif val1 != exp1 or val2 != exp2:
                problem_pins.append({
                    'chip_pin': chip_pin,
                    'arduino_pin': arduino_pin,
                    'name': pin_name,
                    'error': f'Pin reads {val1}/{val2}, expected {exp1}/{exp2}',
                    'expected': f'{exp1}/{exp2}',
                    'actual': f'{val1}/{val2}'
                })
                if progress_callback:
                    progress_callback(f"  ❌ {pin_name} (pin {chip_pin}): Got {val1}/{val2}, expected {exp1}/{exp2}")
            else:
                if progress_callback:
                    progress_callback(f"  ✓ {pin_name} (pin {chip_pin}): {val1}→{val2} ✓")
        
        # Reset all inputs to LOW
        for pin_name in input_pins.keys():
            chip_pin = input_pins.get(pin_name)
            if chip_pin:
                arduino_pin = mapping.get(str(chip_pin))
                if arduino_pin:
                    set_pin(arduino_pin, "LOW")
        
        if problem_pins:
            return (False, f"{len(problem_pins)} output pin(s) not responding correctly", problem_pins)
        
        if progress_callback:
            progress_callback(f"✅ All output pins verified - chip responding correctly")
        
        return (True, "All pins connected and chip responding", [])
    
    def identify_chip(self, progress_callback=None):
        """
        Attempt to identify an unknown chip by testing known patterns.
        Returns: (chip_id, confidence, message)
        """
        if progress_callback:
            progress_callback("🔍 Attempting chip identification...")
        
        # Get all loaded chips
        all_chips = self.chip_db.get_all_chip_ids()
        results = []
        
        for chip_id in all_chips:
            chip_data = self.chip_db.get_chip(chip_id)
            if not chip_data:
                continue
            
            test_sequence = chip_data.get('testSequence', {})
            tests = test_sequence.get('tests', [])
            if len(tests) < 2:
                continue
            
            mapping = chip_data.get('arduinoMapping', {}).get('io', {})
            pinout = chip_data.get('pinout', {})
            
            # Build pin lookups
            input_pins = {p['name']: p['pin'] for p in pinout.get('inputs', [])}
            output_pins = {p['name']: p['pin'] for p in pinout.get('outputs', [])}
            
            if progress_callback:
                progress_callback(f"  Testing pattern for {chip_id}...")
            
            # Run first 2 tests and count matches
            matches = 0
            total_checks = 0
            
            for test in tests[:2]:
                # Set inputs
                for pin_name, state in test.get('inputs', {}).items():
                    chip_pin = input_pins.get(pin_name)
                    if chip_pin:
                        arduino_pin = mapping.get(str(chip_pin))
                        if arduino_pin:
                            self.arduino.send_command(f"SET_PIN,{arduino_pin},{state}")
                            time.sleep(0.03)
                
                time.sleep(0.2)
                
                # Check outputs
                expected = test.get('expectedOutputs', {})
                for pin_name, exp_state in expected.items():
                    chip_pin = output_pins.get(pin_name)
                    if chip_pin:
                        arduino_pin = mapping.get(str(chip_pin))
                        if arduino_pin:
                            self.arduino.send_command(f"READ_PIN,{arduino_pin}")
                            response = self.arduino.read_response()
                            actual = "HIGH" if response and "HIGH" in response else "LOW"
                            total_checks += 1
                            if actual == exp_state:
                                matches += 1
            
            # Calculate match percentage
            if total_checks > 0:
                confidence = (matches / total_checks) * 100
                results.append((chip_id, confidence, chip_data.get('name', chip_id)))
        
        # Sort by confidence
        results.sort(key=lambda x: x[1], reverse=True)
        
        if results:
            best = results[0]
            if progress_callback:
                progress_callback(f"\n📊 Identification Results:")
                for chip_id, conf, name in results[:3]:
                    indicator = "✓" if conf >= 80 else "?" if conf >= 50 else "✗"
                    progress_callback(f"  {indicator} {chip_id} ({name}): {conf:.0f}% match")
            
            if best[1] >= 80:
                return (best[0], best[1], f"Chip identified as {best[0]} with {best[1]:.0f}% confidence")
            elif best[1] >= 50:
                return (best[0], best[1], f"Possible match: {best[0]} ({best[1]:.0f}% confidence)")
            else:
                return (None, 0, "Unable to identify chip - no patterns matched")
        
        return (None, 0, "No chips in database to compare")
    
    def setup_pins(self, chip_data):
        """Configure Arduino pins for the chip"""
        mapping = chip_data['arduinoMapping']['io']
        
        # Set all mapped pins to LOW initially
        for chip_pin, arduino_pin in mapping.items():
            self.arduino.send_command(f"SET_PIN,{arduino_pin},LOW")
            time.sleep(0.05)
    
    def set_pin_state(self, chip_data, pin_name, state):
        """Set a chip pin to HIGH or LOW with retry logic"""
        # Find the chip pin number for this pin name
        chip_pin = None
        
        for input_pin in chip_data['pinout']['inputs']:
            if input_pin['name'] == pin_name:
                chip_pin = input_pin['pin']
                break
        
        if chip_pin is None:
            return False
        
        # Get corresponding Arduino pin
        arduino_pin = chip_data['arduinoMapping']['io'].get(str(chip_pin))
        if arduino_pin is None:
            return False
        
        # Send command with retry logic and longer timeout
        for attempt in range(3):
            # Clear any pending data in buffer
            if self.arduino.arduino and self.arduino.arduino.in_waiting > 0:
                self.arduino.arduino.read(self.arduino.arduino.in_waiting)
            
            time.sleep(0.05)  # Small delay before sending
            self.arduino.send_command(f"SET_PIN,{arduino_pin},{state}")
            time.sleep(0.1)   # Wait for Arduino to process
            response = self.arduino.read_response(timeout=0.5)
            
            if response and "SET_PIN_OK" in response:
                return True
            time.sleep(0.1)
        
        return False
    
    def read_pin_state(self, chip_data, pin_name):
        """Read state of a chip output pin with voting for reliability"""
        # Find the chip pin number
        chip_pin = None
        
        for output_pin in chip_data['pinout']['outputs']:
            if output_pin['name'] == pin_name:
                chip_pin = output_pin['pin']
                break
        
        if chip_pin is None:
            return None
        
        # Get corresponding Arduino pin
        arduino_pin = chip_data['arduinoMapping']['io'].get(str(chip_pin))
        if arduino_pin is None:
            return None
        
        # Read pin with 3x voting for reliability (same as verification)
        reads = []
        for _ in range(3):
            self.arduino.send_command(f"READ_PIN,{arduino_pin}")
            response = self.arduino.read_response()
            
            # Accept both "READ_PIN_OK,HIGH" and just "HIGH" formats
            if response:
                if "HIGH" in response:
                    reads.append("HIGH")
                elif "LOW" in response:
                    reads.append("LOW")
                else:
                    reads.append("ERROR")
            else:
                reads.append("ERROR")
            time.sleep(0.03)
        
        # Majority vote
        high_count = reads.count("HIGH")
        low_count = reads.count("LOW")
        
        if high_count > low_count:
            return "HIGH"
        elif low_count > 0:
            return "LOW"
        
        return None
    
    def run_test(self, chip_id, progress_callback=None, custom_mapping=None):
        """Run complete test sequence for a chip
        
        Args:
            chip_id: ID of the chip to test
            progress_callback: Function to call with progress updates
            custom_mapping: User-defined Arduino pin mapping {chip_pin_str: arduino_pin_int}
                           If provided, overrides the JSON-defined arduinoMapping
        """
        chip_data = self.chip_db.get_chip(chip_id)
        if not chip_data:
            return {"success": False, "error": f"Chip {chip_id} not found"}
        
        # Use custom mapping if provided, otherwise fall back to JSON mapping
        if custom_mapping:
            # Create a modified chip_data with user's pin mapping
            chip_data = chip_data.copy()
            chip_data['arduinoMapping'] = custom_mapping
            if progress_callback:
                progress_callback(f"📌 Using user-defined pin mapping ({len(custom_mapping)} pins)")
        
        results = {
            "chipId": chip_id,
            "chipName": chip_data['name'],
            "testsRun": 0,
            "testsPassed": 0,
            "testsFailed": 0,
            "testDetails": [],
            "success": False,
            "powerVerified": False
        }
        
        # Verify power configuration first
        if progress_callback:
            progress_callback("🔌 Verifying power configuration...")
        
        power_ok, power_msg = self.verify_power(chip_data, progress_callback)
        results["powerVerified"] = power_ok
        
        if not power_ok:
            if progress_callback:
                progress_callback(f"❌ Power check failed: {power_msg}")
            results["error"] = f"Power verification failed: {power_msg}"
            return results
        
        if progress_callback:
            progress_callback("✅ Power check passed")
        
        # Verify pin connections
        pins_ok, pins_msg, problem_pins = self.verify_pin_connections(chip_data, progress_callback)
        results["pinsVerified"] = pins_ok
        results["problemPins"] = problem_pins
        
        if not pins_ok:
            if progress_callback:
                progress_callback(f"❌ Pin connection check failed: {pins_msg}")
            results["error"] = f"Pin connection verification failed: {pins_msg}"
            return results
        
        if progress_callback:
            progress_callback("✅ Pin connections verified")
        
        # Setup pins
        if progress_callback:
            progress_callback("Setting up Arduino pins...")
        self.setup_pins(chip_data)
        time.sleep(0.2)
        
        # Run setup steps
        if 'setup' in chip_data['testSequence']:
            if progress_callback:
                progress_callback("Running setup sequence...")
            for setup_step in chip_data['testSequence']['setup']:
                for pin_name, state in setup_step['pins'].items():
                    self.set_pin_state(chip_data, pin_name, state)
                time.sleep(0.1)
        
        # Run tests
        tests = chip_data['testSequence']['tests']
        for test in tests:
            if 'inputs' not in test:
                continue  # Skip informational tests
            
            results['testsRun'] += 1
            test_id = test['testId']
            description = test['description']
            
            if progress_callback:
                progress_callback(f"Test {test_id}: {description}")
            
            # CRITICAL: Reset ALL input pins to LOW before each test
            # This clears any residual state from verification or previous tests
            if progress_callback:
                progress_callback("    Resetting all inputs to LOW...")
            # Get all input pin names from chip definition (generic for any chip)
            all_input_pins = [p['name'] for p in chip_data.get('pinout', {}).get('inputs', [])]
            for pin_name in all_input_pins:
                success = self.set_pin_state(chip_data, pin_name, 'LOW')
                if not success and progress_callback:
                    progress_callback(f"    ⚠️ Failed to set {pin_name} LOW")
                time.sleep(0.03)
            time.sleep(0.15)
            
            # Now set the test-specific input pins
            if progress_callback:
                progress_callback(f"    Setting test inputs: {test['inputs']}")
            for pin_name, state in test['inputs'].items():
                success = self.set_pin_state(chip_data, pin_name, state)
                if not success and progress_callback:
                    progress_callback(f"    ⚠️ Failed to set {pin_name} {state}")
                time.sleep(0.05)
            
            time.sleep(0.35)  # Longer settle time for chip to respond
            
            # Read and verify outputs
            test_passed = True
            actual_outputs = {}
            
            for pin_name, expected_state in test['expectedOutputs'].items():
                actual_state = self.read_pin_state(chip_data, pin_name)
                actual_outputs[pin_name] = actual_state
                
                # Debug output to show actual vs expected
                if progress_callback:
                    match = "✓" if actual_state == expected_state else "✗"
                    progress_callback(f"    {pin_name}: got {actual_state}, expected {expected_state} {match}")
                
                if actual_state != expected_state:
                    test_passed = False
            
            # Record result
            test_result = {
                "testId": test_id,
                "description": description,
                "passed": test_passed,
                "expectedOutputs": test['expectedOutputs'],
                "actualOutputs": actual_outputs
            }
            
            results['testDetails'].append(test_result)
            
            if test_passed:
                results['testsPassed'] += 1
                if progress_callback:
                    progress_callback(f"  ✅ PASS")
            else:
                results['testsFailed'] += 1
                if progress_callback:
                    progress_callback(f"  ❌ FAIL")
        
        results['success'] = results['testsFailed'] == 0
        return results


class StatusIndicator(tk.Canvas):
    """Large visual pass/fail indicator with animated icons"""
    
    def __init__(self, parent, size=120, **kwargs):
        super().__init__(parent, width=size, height=size, 
                        bg=Theme.BG_CARD, highlightthickness=0, **kwargs)
        self.size = size
        self.center = size // 2
        self.current_state = "idle"
        self.set_idle()
    
    def set_idle(self):
        """Show idle/waiting state"""
        self.current_state = "idle"
        self.delete("all")
        # Draw circle outline
        padding = 10
        self.create_oval(padding, padding, self.size - padding, self.size - padding,
                        outline=Theme.TEXT_MUTED, width=3, dash=(5, 3))
        # Draw question mark
        self.create_text(self.center, self.center, text="?", 
                        font=('Arial', 40, 'bold'), fill=Theme.TEXT_MUTED)
    
    def set_testing(self):
        """Show testing in progress"""
        self.current_state = "testing"
        self.delete("all")
        # Draw pulsing circle
        padding = 10
        self.create_oval(padding, padding, self.size - padding, self.size - padding,
                        outline=Theme.ACCENT_WARNING, width=4)
        # Draw loading dots
        self.create_text(self.center, self.center, text="...", 
                        font=('Arial', 40, 'bold'), fill=Theme.ACCENT_WARNING)
    
    def set_passed(self):
        """Show pass state with checkmark"""
        self.current_state = "passed"
        self.delete("all")
        # Draw filled circle
        padding = 10
        self.create_oval(padding, padding, self.size - padding, self.size - padding,
                        fill=Theme.ACCENT_SUCCESS, outline="")
        # Draw checkmark
        cx, cy = self.center, self.center
        points = [
            cx - 25, cy,
            cx - 8, cy + 20,
            cx + 28, cy - 20
        ]
        self.create_line(points, fill="white", width=8, capstyle=tk.ROUND, joinstyle=tk.ROUND)
    
    def set_failed(self):
        """Show fail state with X"""
        self.current_state = "failed"
        self.delete("all")
        # Draw filled circle
        padding = 10
        self.create_oval(padding, padding, self.size - padding, self.size - padding,
                        fill=Theme.ACCENT_ERROR, outline="")
        # Draw X
        cx, cy = self.center, self.center
        offset = 22
        self.create_line(cx - offset, cy - offset, cx + offset, cy + offset,
                        fill="white", width=8, capstyle=tk.ROUND)
        self.create_line(cx + offset, cy - offset, cx - offset, cy + offset,
                        fill="white", width=8, capstyle=tk.ROUND)


class ModernButton(tk.Canvas):
    """Custom styled button with hover effects"""
    
    def __init__(self, parent, text, command, width=120, height=40, 
                 bg_color=None, hover_color=None, text_color="white", **kwargs):
        super().__init__(parent, width=width, height=height, 
                        bg=Theme.BG_CARD, highlightthickness=0, **kwargs)
        
        self.command = command
        self.text = text
        self.width = width
        self.height = height
        self.bg_color = bg_color or Theme.ACCENT_PRIMARY
        self.hover_color = hover_color or Theme.ACCENT_INFO
        self.text_color = text_color
        self.fonts = Theme.get_fonts()
        
        self.draw_button(self.bg_color)
        
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)
    
    def draw_button(self, color):
        self.delete("all")
        # Draw rounded rectangle
        radius = 8
        self.create_rounded_rect(2, 2, self.width - 2, self.height - 2, radius, color)
        # Draw text
        self.create_text(self.width // 2, self.height // 2, text=self.text,
                        font=self.fonts['button'], fill=self.text_color)
    
    def create_rounded_rect(self, x1, y1, x2, y2, radius, color):
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        self.create_polygon(points, fill=color, smooth=True)
    
    def on_enter(self, event):
        self.draw_button(self.hover_color)
    
    def on_leave(self, event):
        self.draw_button(self.bg_color)
    
    def on_click(self, event):
        if self.command:
            self.command()


class HelpDialog:
    """Help dialog with documentation tabs"""
    
    def __init__(self, parent):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("IC Tester Pro - Help & Documentation")
        self.dialog.geometry("700x550")
        self.dialog.configure(bg=Theme.BG_DARK)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.fonts = Theme.get_fonts()
        self.create_dialog()
        
        # Center on parent
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def create_dialog(self):
        """Build the help dialog"""
        # Header
        header = tk.Frame(self.dialog, bg=Theme.BG_DARK, pady=15)
        header.pack(fill=tk.X, padx=20)
        
        tk.Label(header, text="📖 Help & Documentation", 
                font=self.fonts['heading'],
                bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY).pack(side=tk.LEFT)
        
        # Tab buttons
        tab_frame = tk.Frame(self.dialog, bg=Theme.BG_DARK)
        tab_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        self.tabs = {}
        self.tab_buttons = {}
        tab_names = ["Getting Started", "Adding Chips", "JSON Format", "Troubleshooting"]
        
        for i, name in enumerate(tab_names):
            btn = tk.Label(tab_frame, text=name, font=self.fonts['body'],
                          bg=Theme.BG_LIGHT if i == 0 else Theme.BG_CARD,
                          fg=Theme.TEXT_PRIMARY, padx=15, pady=8, cursor="hand2")
            btn.pack(side=tk.LEFT, padx=(0, 5))
            btn.bind("<Button-1>", lambda e, n=name: self.show_tab(n))
            self.tab_buttons[name] = btn
        
        # Content area
        content_frame = tk.Frame(self.dialog, bg=Theme.BG_CARD, padx=20, pady=20)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        
        self.content_text = scrolledtext.ScrolledText(
            content_frame,
            font=self.fonts['body'],
            bg=Theme.BG_DARK,
            fg=Theme.TEXT_PRIMARY,
            relief=tk.FLAT,
            padx=15,
            pady=15,
            wrap=tk.WORD,
            cursor="arrow"
        )
        self.content_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure text tags
        self.content_text.tag_configure("h1", font=(self.fonts['heading'][0], 18, 'bold'), 
                                        foreground=Theme.ACCENT_PRIMARY)
        self.content_text.tag_configure("h2", font=(self.fonts['subheading'][0], 14, 'bold'),
                                        foreground=Theme.ACCENT_INFO)
        self.content_text.tag_configure("code", font=self.fonts['mono'],
                                        background=Theme.BG_MEDIUM, foreground=Theme.ACCENT_WARNING)
        self.content_text.tag_configure("highlight", foreground=Theme.ACCENT_SUCCESS)
        
        # Show first tab
        self.show_tab("Getting Started")
        
        # Close button
        close_frame = tk.Frame(self.dialog, bg=Theme.BG_DARK)
        close_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        ModernButton(close_frame, "Close", self.dialog.destroy,
                    width=100, height=36).pack(side=tk.RIGHT)
    
    def show_tab(self, tab_name):
        """Switch to specified tab"""
        # Update button styles
        for name, btn in self.tab_buttons.items():
            if name == tab_name:
                btn.configure(bg=Theme.BG_LIGHT)
            else:
                btn.configure(bg=Theme.BG_CARD)
        
        # Get content
        content = self.get_tab_content(tab_name)
        
        # Display content
        self.content_text.configure(state=tk.NORMAL)
        self.content_text.delete(1.0, tk.END)
        
        for text, tag in content:
            self.content_text.insert(tk.END, text, tag)
        
        self.content_text.configure(state=tk.DISABLED)
    
    def get_tab_content(self, tab_name):
        """Return content for each tab as list of (text, tag) tuples"""
        
        if tab_name == "Getting Started":
            return [
                ("Getting Started with IC Tester Pro\n\n", "h1"),
                ("Welcome to IC Tester Pro! This application helps you test 74-series integrated circuits using an Arduino.\n\n", None),
                
                ("Step 1: Connect Your Arduino\n\n", "h2"),
                ("1. Plug your Arduino into a USB port\n", None),
                ("2. Make sure you've uploaded the IC Tester sketch to your Arduino\n", None),
                ("3. Close the Arduino IDE (it blocks the serial port)\n", None),
                ("4. Click ", None), ("Scan", "code"), (" to find your Arduino\n", None),
                ("5. Select the correct port and click ", None), ("Connect", "code"), ("\n\n", None),
                
                ("Step 2: Wire Your IC\n\n", "h2"),
                ("1. Place the 74-series IC in your breadboard\n", None),
                ("2. Connect VCC (usually pin 14) to Arduino 5V\n", None),
                ("3. Connect GND (usually pin 7) to Arduino GND\n", None),
                ("4. Wire the I/O pins according to the chip's mapping\n", None),
                ("   (Check the ", None), ("chips/", "code"), (" folder for pin mappings)\n\n", None),
                
                ("Step 3: Run the Test\n\n", "h2"),
                ("1. Select your chip from the dropdown\n", None),
                ("2. Click ", None), ("▶ Run Test", "highlight"), ("\n", None),
                ("3. Watch the status indicator for results:\n", None),
                ("   • ", None), ("Green ✓", "highlight"), (" = All tests passed\n", None),
                ("   • Red ✗ = One or more tests failed\n\n", None),
                
                ("The test output panel shows detailed results for each test step.\n", None),
            ]
        
        elif tab_name == "Adding Chips":
            return [
                ("Adding New Chip Definitions\n\n", "h1"),
                ("IC Tester Pro loads chip definitions from JSON files in the ", None),
                ("chips/", "code"), (" folder.\n\n", None),
                
                ("Quick Start\n\n", "h2"),
                ("1. Create a new file in the ", None), ("chips/", "code"), (" folder\n", None),
                ("2. Name it with the chip ID (e.g., ", None), ("7400.json", "code"), (")\n", None),
                ("3. Follow the JSON format (see 'JSON Format' tab)\n", None),
                ("4. Restart the application to load the new chip\n\n", None),
                
                ("What You Need to Know\n\n", "h2"),
                ("• ", None), ("chipId", "code"), (" - The chip's part number (e.g., \"7490\")\n", None),
                ("• ", None), ("name", "code"), (" - Human-readable name\n", None),
                ("• ", None), ("pinout", "code"), (" - Which pins are inputs, outputs, power\n", None),
                ("• ", None), ("arduinoMapping", "code"), (" - How chip pins connect to Arduino pins\n", None),
                ("• ", None), ("testSequence", "code"), (" - The tests to run\n\n", None),
                
                ("Pin Types\n\n", "h2"),
                ("• ", None), ("vcc", "highlight"), (" - Power supply pin (connect to 5V)\n", None),
                ("• ", None), ("gnd", "highlight"), (" - Ground pin\n", None),
                ("• ", None), ("inputs", "highlight"), (" - Pins the Arduino controls\n", None),
                ("• ", None), ("outputs", "highlight"), (" - Pins the Arduino reads\n", None),
                ("• ", None), ("noConnect", "highlight"), (" - Pins not used in testing\n\n", None),
                
                ("Tips\n\n", "h2"),
                ("• Check the chip's datasheet for truth tables\n", None),
                ("• Start with simple reset/clear tests\n", None),
                ("• Test one function at a time\n", None),
                ("• Use the existing ", None), ("7490.json", "code"), (" as a template\n", None),
            ]
        
        elif tab_name == "JSON Format":
            return [
                ("Chip Definition JSON Format\n\n", "h1"),
                ("Here's the complete structure for a chip definition file:\n\n", None),
                
                ("Basic Structure\n\n", "h2"),
                ('{\n', "code"),
                ('  "chipId": "7490",\n', "code"),
                ('  "name": "Decade Counter",\n', "code"),
                ('  "manufacturer": "Texas Instruments",\n', "code"),
                ('  "package": "14-pin DIP",\n', "code"),
                ('  "description": "Description here",\n', "code"),
                ('  "pinout": { ... },\n', "code"),
                ('  "arduinoMapping": { ... },\n', "code"),
                ('  "testSequence": { ... }\n', "code"),
                ('}\n\n', "code"),
                
                ("Pinout Section\n\n", "h2"),
                ('"pinout": {\n', "code"),
                ('  "vcc": 14,\n', "code"),
                ('  "gnd": 7,\n', "code"),
                ('  "inputs": [\n', "code"),
                ('    {"pin": 1, "name": "A", "description": "Input A"}\n', "code"),
                ('  ],\n', "code"),
                ('  "outputs": [\n', "code"),
                ('    {"pin": 3, "name": "Y", "description": "Output Y"}\n', "code"),
                ('  ]\n', "code"),
                ('}\n\n', "code"),
                
                ("Arduino Mapping\n\n", "h2"),
                ('"arduinoMapping": {\n', "code"),
                ('  "power": {"14": "5V", "7": "GND"},\n', "code"),
                ('  "io": {\n', "code"),
                ('    "1": 2,    // Chip pin 1 → Arduino pin 2\n', "code"),
                ('    "3": 3     // Chip pin 3 → Arduino pin 3\n', "code"),
                ('  }\n', "code"),
                ('}\n\n', "code"),
                
                ("Test Sequence\n\n", "h2"),
                ('"testSequence": {\n', "code"),
                ('  "tests": [\n', "code"),
                ('    {\n', "code"),
                ('      "testId": 1,\n', "code"),
                ('      "description": "Test AND gate",\n', "code"),
                ('      "inputs": {"A": "HIGH", "B": "HIGH"},\n', "code"),
                ('      "expectedOutputs": {"Y": "HIGH"}\n', "code"),
                ('    }\n', "code"),
                ('  ]\n', "code"),
                ('}\n', "code"),
            ]
        
        elif tab_name == "Troubleshooting":
            return [
                ("Troubleshooting Guide\n\n", "h1"),
                
                ("Arduino Not Found\n\n", "h2"),
                ("• Make sure Arduino is plugged in via USB\n", None),
                ("• Close Arduino IDE (it blocks the port)\n", None),
                ("• Try a different USB cable\n", None),
                ("• Click 'Scan' to refresh the port list\n", None),
                ("• On Mac: Look for ", None), ("/dev/cu.usbmodem*", "code"), ("\n", None),
                ("• On Windows: Look for ", None), ("COM3", "code"), (" or similar\n\n", None),
                
                ("Connection Failed\n\n", "h2"),
                ("• Verify the IC Tester sketch is uploaded to Arduino\n", None),
                ("• Check baud rate is set to ", None), ("9600", "code"), ("\n", None),
                ("• Try unplugging and replugging the Arduino\n", None),
                ("• Wait 2-3 seconds after plugging in before connecting\n\n", None),
                
                ("All Tests Failing\n\n", "h2"),
                ("• Double-check your wiring matches the pin mapping\n", None),
                ("• Verify VCC and GND are connected correctly\n", None),
                ("• Make sure the chip is inserted the right way\n", None),
                ("• Check if the chip is damaged (try a known good chip)\n", None),
                ("• Verify the JSON file has correct pin numbers\n\n", None),
                
                ("Chip Not in List\n\n", "h2"),
                ("• Add a new JSON file to the ", None), ("chips/", "code"), (" folder\n", None),
                ("• See 'Adding Chips' and 'JSON Format' tabs for details\n", None),
                ("• Restart the application after adding new files\n\n", None),
                
                ("Inconsistent Results\n\n", "h2"),
                ("• Check for loose wires or bad breadboard connections\n", None),
                ("• Add small delays between tests if needed\n", None),
                ("• Some chips need decoupling capacitors near VCC/GND\n", None),
                ("• Avoid long wire runs that can pick up noise\n", None),
            ]
        
        return [("No content available.", None)]


class ICTesterGUI:
    """Modern GUI for IC Tester - Cross-platform compatible"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("IC Tester Pro")
        self.root.geometry("950x700")
        self.root.minsize(800, 600)
        
        # Get cross-platform fonts
        self.fonts = Theme.get_fonts()
        
        # Configure dark theme
        self.root.configure(bg=Theme.BG_DARK)
        
        # Initialize components
        self.arduino = ArduinoConnection()
        self.chip_db = ChipDatabase()
        self.tester = ICTester(self.arduino, self.chip_db)
        
        # State management for edge cases
        self.last_result = None
        self.is_testing = False           # Prevent multiple simultaneous tests
        self.scan_cooldown = False        # Prevent rapid scan clicking
        self.scan_cooldown_seconds = 3    # Cooldown duration
        self.connection_check_interval = 2000  # Check connection every 2 seconds
        
        # Button references for state management
        self.scan_btn = None
        self.connect_btn = None
        self.disconnect_btn = None
        self.test_btn = None
        
        # Build the interface
        self.setup_styles()
        self.create_gui()
        
        # Start connection health monitor
        self.start_connection_monitor()
        
    def setup_styles(self):
        """Configure ttk styles for modern look"""
        style = ttk.Style()
        
        # Try to use clam theme as base (most customizable)
        try:
            style.theme_use('clam')
        except:
            pass
        
        # Configure Combobox
        style.configure('Modern.TCombobox',
                       fieldbackground=Theme.BG_LIGHT,
                       background=Theme.BG_LIGHT,
                       foreground=Theme.TEXT_PRIMARY,
                       arrowcolor=Theme.TEXT_PRIMARY,
                       padding=8)
        
        # Configure Labels
        style.configure('Title.TLabel',
                       background=Theme.BG_DARK,
                       foreground=Theme.TEXT_PRIMARY,
                       font=self.fonts['heading'])
        
        style.configure('Subtitle.TLabel',
                       background=Theme.BG_DARK,
                       foreground=Theme.TEXT_SECONDARY,
                       font=self.fonts['body'])
        
        style.configure('Card.TFrame',
                       background=Theme.BG_CARD)
        
    def create_gui(self):
        """Build the modern GUI"""
        # Main container with padding
        main_container = tk.Frame(self.root, bg=Theme.BG_DARK)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # === HEADER ===
        self.create_header(main_container)
        
        # === CONTENT AREA (two columns) ===
        content = tk.Frame(main_container, bg=Theme.BG_DARK)
        content.pack(fill=tk.BOTH, expand=True, pady=(20, 0))
        
        # Left column - Controls and Status
        left_col = tk.Frame(content, bg=Theme.BG_DARK, width=280)
        left_col.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_col.pack_propagate(False)
        
        self.create_connection_panel(left_col)
        self.create_chip_panel(left_col)
        self.create_status_panel(left_col)
        
        # Center column - Pin Mapping
        center_col = tk.Frame(content, bg=Theme.BG_DARK, width=280)
        center_col.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        center_col.pack_propagate(False)
        
        self.create_pin_mapping_panel(center_col)
        
        # Right column - Output Log
        right_col = tk.Frame(content, bg=Theme.BG_DARK)
        right_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.create_output_panel(right_col)
        
        # Auto-scan ports on startup
        self.root.after(100, self.scan_ports)
    
    def create_header(self, parent):
        """Create app header with title"""
        header = tk.Frame(parent, bg=Theme.BG_DARK)
        header.pack(fill=tk.X)
        
        # Title
        title = tk.Label(header, text="IC Tester Pro", 
                        font=self.fonts['heading'],
                        bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY)
        title.pack(side=tk.LEFT)
        
        # Subtitle
        subtitle = tk.Label(header, text="74-Series Chip Testing System",
                           font=self.fonts['body'],
                           bg=Theme.BG_DARK, fg=Theme.TEXT_SECONDARY)
        subtitle.pack(side=tk.LEFT, padx=(15, 0), pady=(8, 0))
        
        # Right side - Help button and version badge
        right_frame = tk.Frame(header, bg=Theme.BG_DARK)
        right_frame.pack(side=tk.RIGHT)
        
        # Help button
        ModernButton(right_frame, "? Help", self.show_help,
                    width=80, height=32, bg_color=Theme.ACCENT_INFO).pack(side=tk.LEFT, padx=(0, 10))
        
        # Version badge
        version_frame = tk.Frame(right_frame, bg=Theme.ACCENT_PRIMARY, padx=8, pady=2)
        version_frame.pack(side=tk.LEFT)
        tk.Label(version_frame, text="v4.0", font=self.fonts['small'],
                bg=Theme.ACCENT_PRIMARY, fg="white").pack()
    
    def create_card(self, parent, title):
        """Create a styled card container"""
        card = tk.Frame(parent, bg=Theme.BG_CARD, padx=15, pady=15)
        card.pack(fill=tk.X, pady=(0, 15))
        
        # Card title
        title_label = tk.Label(card, text=title, font=self.fonts['subheading'],
                              bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY)
        title_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Content area
        content = tk.Frame(card, bg=Theme.BG_CARD)
        content.pack(fill=tk.X)
        
        return content
    
    def create_connection_panel(self, parent):
        """Create Arduino connection controls"""
        content = self.create_card(parent, "Arduino Connection")
        
        # Port selection row
        port_row = tk.Frame(content, bg=Theme.BG_CARD)
        port_row.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(port_row, text="Port:", font=self.fonts['body'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY).pack(side=tk.LEFT)
        
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(port_row, textvariable=self.port_var, 
                                       state='readonly', width=18)
        self.port_combo.pack(side=tk.LEFT, padx=(10, 0))
        
        # Connection status indicator
        status_row = tk.Frame(content, bg=Theme.BG_CARD)
        status_row.pack(fill=tk.X, pady=(0, 10))
        
        # Status dot
        self.status_dot = tk.Canvas(status_row, width=12, height=12,
                                   bg=Theme.BG_CARD, highlightthickness=0)
        self.status_dot.pack(side=tk.LEFT)
        self.status_dot.create_oval(2, 2, 10, 10, fill=Theme.DISCONNECTED, outline="")
        
        self.conn_status = tk.Label(status_row, text="Disconnected", 
                                   font=self.fonts['body'],
                                   bg=Theme.BG_CARD, fg=Theme.DISCONNECTED)
        self.conn_status.pack(side=tk.LEFT, padx=(8, 0))
        
        # Buttons row
        btn_row = tk.Frame(content, bg=Theme.BG_CARD)
        btn_row.pack(fill=tk.X)
        
        # Scan button with cooldown indicator
        self.scan_btn = ModernButton(btn_row, "Scan", self.scan_ports, 
                    width=90, height=36, bg_color=Theme.BG_LIGHT)
        self.scan_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Connect button (shown when disconnected)
        self.connect_btn = ModernButton(btn_row, "Connect", self.connect_arduino,
                    width=90, height=36, bg_color=Theme.ACCENT_PRIMARY)
        self.connect_btn.pack(side=tk.LEFT)
        
        # Disconnect button (hidden initially, shown when connected)
        self.disconnect_btn = ModernButton(btn_row, "Disconnect", self.disconnect_arduino,
                    width=90, height=36, bg_color=Theme.ACCENT_ERROR)
        # Don't pack yet - will be shown when connected
    
    def create_chip_panel(self, parent):
        """Create chip selection controls"""
        content = self.create_card(parent, "Chip Selection")
        
        # Chip dropdown
        chip_row = tk.Frame(content, bg=Theme.BG_CARD)
        chip_row.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(chip_row, text="Chip:", font=self.fonts['body'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY).pack(side=tk.LEFT)
        
        self.chip_var = tk.StringVar()
        self.chip_combo = ttk.Combobox(chip_row, textvariable=self.chip_var,
                                       state='readonly', width=18)
        self.chip_combo.pack(side=tk.LEFT, padx=(10, 0))
        self.chip_combo['values'] = self.chip_db.get_all_chip_ids()
        
        # Chip info (create before binding callback)
        self.chip_info = tk.Label(content, text="", font=self.fonts['small'],
                                 bg=Theme.BG_CARD, fg=Theme.TEXT_MUTED,
                                 wraplength=250, justify=tk.LEFT)
        self.chip_info.pack(anchor=tk.W, pady=(0, 15))
        
        # Now set up selection
        if self.chip_combo['values']:
            self.chip_combo.current(0)
            self.chip_combo.bind('<<ComboboxSelected>>', self.on_chip_selected)
            self.on_chip_selected(None)
        else:
            # No chips loaded - show warning
            self.chip_info.config(text="⚠️ No chips loaded!\nAdd JSON files to the 'chips/' folder\nand restart the application.",
                                 fg=Theme.ACCENT_WARNING)
        
        # Button row
        btn_row = tk.Frame(content, bg=Theme.BG_CARD)
        btn_row.pack(fill=tk.X, pady=(0, 10))
        
        # Run Test button (prominent) - store reference for state management
        self.test_btn = ModernButton(btn_row, "▶  Run Test", self.run_test,
                    width=120, height=40, 
                    bg_color=Theme.ACCENT_SUCCESS,
                    hover_color="#05c493")
        self.test_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Run Counter button - continuous counting mode
        self.run_counter_btn = ModernButton(btn_row, "⏱  Run Counter", self.start_counter,
                    width=120, height=40, 
                    bg_color=Theme.ACCENT_INFO,
                    hover_color="#0099cc")
        self.run_counter_btn.pack(side=tk.LEFT)
        
        # Stop button (hidden initially)
        self.stop_btn = ModernButton(btn_row, "⏹  Stop", self.stop_counter,
                    width=80, height=40, 
                    bg_color=Theme.ACCENT_ERROR,
                    hover_color="#cc3333")
        # Don't pack yet - shown when counter is running
        
        # Live counter display
        self.counter_display = tk.Label(content, text="", 
                                        font=self.fonts['mono'],
                                        bg=Theme.BG_CARD, fg=Theme.ACCENT_PRIMARY)
        self.counter_display.pack(pady=(5, 0))
        
        # Counter running flag
        self.counter_running = False
    
    def create_pin_mapping_panel(self, parent):
        """Create dynamic pin mapping panel where user assigns Arduino pins to chip pins"""
        # Card container
        card = tk.Frame(parent, bg=Theme.BG_CARD, padx=15, pady=15)
        card.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # Header with title and buttons
        header = tk.Frame(card, bg=Theme.BG_CARD)
        header.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(header, text="Pin Mapping", font=self.fonts['subheading'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY).pack(side=tk.LEFT)
        
        # Validate button
        ModernButton(header, "Validate", self.validate_pin_mapping,
                    width=70, height=28, bg_color=Theme.ACCENT_INFO).pack(side=tk.RIGHT, padx=(5, 0))
        
        # Save button
        ModernButton(header, "Save", self.save_pin_mapping,
                    width=50, height=28, bg_color=Theme.ACCENT_SUCCESS).pack(side=tk.RIGHT, padx=(5, 0))
        
        # Load button
        ModernButton(header, "Load", self.load_pin_mapping,
                    width=50, height=28, bg_color=Theme.ACCENT_WARNING).pack(side=tk.RIGHT, padx=(5, 0))
        
        # Clear button
        ModernButton(header, "Clear", self.clear_pin_mapping,
                    width=50, height=28, bg_color=Theme.BG_LIGHT).pack(side=tk.RIGHT)
        
        # Instructions
        tk.Label(card, text="Enter Arduino pin for each chip pin:",
                font=self.fonts['small'], bg=Theme.BG_CARD, 
                fg=Theme.TEXT_MUTED).pack(anchor=tk.W, pady=(0, 5))
        
        # Scrollable frame for pin entries
        canvas_frame = tk.Frame(card, bg=Theme.BG_CARD)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        # Canvas with scrollbar
        self.pin_canvas = tk.Canvas(canvas_frame, bg=Theme.BG_CARD, 
                                    highlightthickness=0, height=300)
        scrollbar = tk.Scrollbar(canvas_frame, orient="vertical", 
                                command=self.pin_canvas.yview)
        
        self.pin_mapping_frame = tk.Frame(self.pin_canvas, bg=Theme.BG_CARD)
        
        self.pin_canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.pin_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.pin_canvas_window = self.pin_canvas.create_window((0, 0), 
                                                               window=self.pin_mapping_frame, 
                                                               anchor="nw")
        
        # Bind events for scrolling
        self.pin_mapping_frame.bind("<Configure>", self._on_pin_frame_configure)
        self.pin_canvas.bind("<Configure>", self._on_pin_canvas_configure)
        
        # Storage for pin entry widgets
        self.pin_entries = {}  # {chip_pin: Entry widget}
        self.user_pin_mapping = {}  # {chip_pin: arduino_pin}
        
        # Validation status label
        self.mapping_status = tk.Label(card, text="Select a chip to configure pins",
                                      font=self.fonts['small'], bg=Theme.BG_CARD,
                                      fg=Theme.TEXT_MUTED)
        self.mapping_status.pack(anchor=tk.W, pady=(10, 0))
    
    def _on_pin_frame_configure(self, event):
        """Update scroll region when frame size changes"""
        self.pin_canvas.configure(scrollregion=self.pin_canvas.bbox("all"))
    
    def _on_pin_canvas_configure(self, event):
        """Update frame width when canvas size changes"""
        self.pin_canvas.itemconfig(self.pin_canvas_window, width=event.width)
    
    def populate_pin_mapping(self, chip_data):
        """Populate pin mapping entries based on selected chip"""
        # Clear existing entries
        for widget in self.pin_mapping_frame.winfo_children():
            widget.destroy()
        self.pin_entries.clear()
        self.user_pin_mapping.clear()
        
        if not chip_data:
            return
        
        pinout = chip_data.get('pinout', {})
        
        # Get all pin numbers and sort them
        pin_numbers = []
        for key in pinout.keys():
            if key not in ['vcc', 'gnd', 'description']:
                try:
                    pin_numbers.append(int(key))
                except ValueError:
                    pass
        pin_numbers.sort()
        
        # Create header row
        header_frame = tk.Frame(self.pin_mapping_frame, bg=Theme.BG_CARD)
        header_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(header_frame, text="Chip Pin", font=self.fonts['small'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY, width=8).pack(side=tk.LEFT)
        tk.Label(header_frame, text="Function", font=self.fonts['small'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY, width=10).pack(side=tk.LEFT, padx=(5, 0))
        tk.Label(header_frame, text="Arduino Pin", font=self.fonts['small'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY, width=10).pack(side=tk.LEFT, padx=(5, 0))
        
        # Create entry for each pin
        for pin_num in pin_numbers:
            pin_name = pinout.get(str(pin_num), f"Pin {pin_num}")
            
            row = tk.Frame(self.pin_mapping_frame, bg=Theme.BG_CARD)
            row.pack(fill=tk.X, pady=2)
            
            # Pin number
            tk.Label(row, text=f"{pin_num}", font=self.fonts['body'],
                    bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY, width=8,
                    anchor=tk.W).pack(side=tk.LEFT)
            
            # Pin function name
            display_name = pin_name[:10] if len(pin_name) > 10 else pin_name
            tk.Label(row, text=display_name, font=self.fonts['small'],
                    bg=Theme.BG_CARD, fg=Theme.TEXT_MUTED, width=10,
                    anchor=tk.W).pack(side=tk.LEFT, padx=(5, 0))
            
            # Arduino pin entry
            entry = tk.Entry(row, width=8, font=self.fonts['body'],
                           bg=Theme.BG_LIGHT, fg=Theme.TEXT_PRIMARY,
                           insertbackground=Theme.TEXT_PRIMARY,
                           relief=tk.FLAT)
            entry.pack(side=tk.LEFT, padx=(5, 0))
            
            # Check if this is VCC or GND
            if pin_name.upper() in ['VCC', 'GND', '+5V', '5V', 'GROUND']:
                entry.insert(0, "PWR")
                entry.config(state='readonly', fg=Theme.ACCENT_WARNING)
            
            self.pin_entries[pin_num] = entry
        
        self.mapping_status.config(text=f"Configure {len(pin_numbers)} pins for {chip_data.get('name', 'chip')}",
                                  fg=Theme.TEXT_SECONDARY)
    
    def validate_pin_mapping(self):
        """Validate that all pin mappings are valid and unique"""
        if not self.pin_entries:
            self.log("⚠️ No chip selected for pin mapping", "warning")
            return False
        
        errors = []
        warnings = []
        used_pins = {}  # arduino_pin: chip_pin (to detect duplicates)
        valid_mapping = {}
        
        # Reserved pins for Mega 2560
        reserved_pins = {
            0: "Serial RX",
            1: "Serial TX", 
        }
        
        for chip_pin, entry in self.pin_entries.items():
            value = entry.get().strip().upper()
            
            # Skip power pins
            if value == "PWR":
                valid_mapping[chip_pin] = "PWR"
                continue
            
            # Check if empty
            if not value:
                errors.append(f"Chip pin {chip_pin}: No Arduino pin specified")
                entry.config(bg=Theme.ACCENT_ERROR)
                continue
            
            # Try to parse as integer
            try:
                arduino_pin = int(value)
            except ValueError:
                # Check for analog pins (A0-A15)
                if value.startswith('A') and value[1:].isdigit():
                    analog_num = int(value[1:])
                    if analog_num < 0 or analog_num > 15:
                        errors.append(f"Chip pin {chip_pin}: Invalid analog pin {value}")
                        entry.config(bg=Theme.ACCENT_ERROR)
                        continue
                    arduino_pin = 54 + analog_num  # A0 = 54 on Mega
                else:
                    errors.append(f"Chip pin {chip_pin}: Invalid value '{value}'")
                    entry.config(bg=Theme.ACCENT_ERROR)
                    continue
            
            # Validate pin range for Mega 2560
            if arduino_pin < 0 or arduino_pin > 69:
                errors.append(f"Chip pin {chip_pin}: Pin {arduino_pin} out of range (0-53 digital, A0-A15)")
                entry.config(bg=Theme.ACCENT_ERROR)
                continue
            
            # Check for reserved pins
            if arduino_pin in reserved_pins:
                warnings.append(f"Chip pin {chip_pin}: Pin {arduino_pin} is reserved for {reserved_pins[arduino_pin]}")
                entry.config(bg=Theme.ACCENT_WARNING)
            
            # Check for duplicates
            if arduino_pin in used_pins:
                errors.append(f"Chip pin {chip_pin}: Arduino pin {arduino_pin} already used by chip pin {used_pins[arduino_pin]}")
                entry.config(bg=Theme.ACCENT_ERROR)
                continue
            
            # Valid!
            used_pins[arduino_pin] = chip_pin
            valid_mapping[chip_pin] = arduino_pin
            entry.config(bg=Theme.BG_LIGHT)
        
        # Report results
        if errors:
            self.log("❌ Pin mapping validation failed:", "error")
            for err in errors:
                self.log(f"   • {err}", "error")
            self.mapping_status.config(text=f"❌ {len(errors)} error(s) found", fg=Theme.ACCENT_ERROR)
            return False
        
        if warnings:
            self.log("⚠️ Pin mapping warnings:", "warning")
            for warn in warnings:
                self.log(f"   • {warn}", "warning")
        
        # Store valid mapping
        self.user_pin_mapping = valid_mapping
        
        self.log("✅ Pin mapping validated successfully!", "success")
        self.log(f"   Mapped {len([p for p in valid_mapping.values() if p != 'PWR'])} I/O pins", "success")
        self.mapping_status.config(text=f"✅ Valid - {len(valid_mapping)} pins mapped", fg=Theme.ACCENT_SUCCESS)
        
        return True
    
    def clear_pin_mapping(self):
        """Clear all pin mapping entries"""
        for entry in self.pin_entries.values():
            if entry.cget('state') != 'readonly':
                entry.delete(0, tk.END)
                entry.config(bg=Theme.BG_LIGHT)
        
        self.user_pin_mapping.clear()
        self.mapping_status.config(text="Pin mappings cleared", fg=Theme.TEXT_MUTED)
        self.log("🔄 Pin mappings cleared", "info")
    
    def get_user_arduino_mapping(self):
        """Get the user-defined Arduino pin mapping for testing"""
        if not self.user_pin_mapping:
            # Try to validate first
            if not self.validate_pin_mapping():
                return None
        
        # Convert to the format expected by the tester
        # Format: {chip_pin_str: arduino_pin_int}
        mapping = {}
        for chip_pin, arduino_pin in self.user_pin_mapping.items():
            if arduino_pin != "PWR":
                mapping[str(chip_pin)] = arduino_pin
        
        return mapping
    
    def save_pin_mapping(self):
        """Save current pin mapping to a JSON file"""
        if not self.pin_entries:
            self.log("⚠️ No pin mapping to save", "warning")
            return
        
        chip_id = self.chip_var.get()
        if not chip_id:
            self.log("⚠️ No chip selected", "warning")
            return
        
        # Gather current entries
        mapping_data = {
            "chipId": chip_id,
            "mappings": {}
        }
        
        for chip_pin, entry in self.pin_entries.items():
            value = entry.get().strip()
            if value:
                mapping_data["mappings"][str(chip_pin)] = value
        
        # Create mappings directory if it doesn't exist
        mappings_dir = Path("pin_mappings")
        mappings_dir.mkdir(exist_ok=True)
        
        # Save to file
        filename = mappings_dir / f"{chip_id}_mapping.json"
        try:
            with open(filename, 'w') as f:
                json.dump(mapping_data, f, indent=2)
            self.log(f"✅ Pin mapping saved to {filename}", "success")
            self.mapping_status.config(text=f"Saved: {filename.name}", fg=Theme.ACCENT_SUCCESS)
        except Exception as e:
            self.log(f"❌ Failed to save mapping: {e}", "error")
    
    def load_pin_mapping(self):
        """Load pin mapping from a JSON file"""
        chip_id = self.chip_var.get()
        if not chip_id:
            self.log("⚠️ No chip selected", "warning")
            return
        
        # Look for saved mapping file
        mappings_dir = Path("pin_mappings")
        filename = mappings_dir / f"{chip_id}_mapping.json"
        
        if not filename.exists():
            self.log(f"⚠️ No saved mapping found for {chip_id}", "warning")
            self.log(f"   Looking for: {filename}", "info")
            return
        
        try:
            with open(filename, 'r') as f:
                mapping_data = json.load(f)
            
            # Verify chip ID matches
            if mapping_data.get("chipId") != chip_id:
                self.log(f"⚠️ Mapping file is for {mapping_data.get('chipId')}, not {chip_id}", "warning")
                return
            
            # Apply mappings to entries
            mappings = mapping_data.get("mappings", {})
            loaded_count = 0
            
            for chip_pin_str, arduino_pin_str in mappings.items():
                chip_pin = int(chip_pin_str)
                if chip_pin in self.pin_entries:
                    entry = self.pin_entries[chip_pin]
                    if entry.cget('state') != 'readonly':
                        entry.delete(0, tk.END)
                        entry.insert(0, arduino_pin_str)
                        loaded_count += 1
            
            self.log(f"✅ Loaded {loaded_count} pin mappings from {filename.name}", "success")
            self.mapping_status.config(text=f"Loaded: {filename.name}", fg=Theme.ACCENT_SUCCESS)
            
            # Auto-validate after loading
            self.validate_pin_mapping()
            
        except Exception as e:
            self.log(f"❌ Failed to load mapping: {e}", "error")
    
    def create_status_panel(self, parent):
        """Create large status indicator panel"""
        content = self.create_card(parent, "Test Result")
        
        # Center the status indicator with fixed height container
        indicator_frame = tk.Frame(content, bg=Theme.BG_CARD, height=100, width=100)
        indicator_frame.pack(pady=10)
        indicator_frame.pack_propagate(False)
        
        self.status_indicator = StatusIndicator(indicator_frame, size=80)
        self.status_indicator.place(relx=0.5, rely=0.5, anchor="center")
        
        # Status text
        self.result_text = tk.Label(content, text="Ready to test",
                                   font=self.fonts['subheading'],
                                   bg=Theme.BG_CARD, fg=Theme.TEXT_MUTED)
        self.result_text.pack(pady=(10, 0))
        
        # Stats row
        self.stats_frame = tk.Frame(content, bg=Theme.BG_CARD)
        self.stats_frame.pack(fill=tk.X, pady=(15, 0))
        
        self.create_stat(self.stats_frame, "Passed", "0", Theme.ACCENT_SUCCESS, "passed_stat")
        self.create_stat(self.stats_frame, "Failed", "0", Theme.ACCENT_ERROR, "failed_stat")
        self.create_stat(self.stats_frame, "Total", "0", Theme.TEXT_SECONDARY, "total_stat")
    
    def create_stat(self, parent, label, value, color, attr_name):
        """Create a stat display"""
        frame = tk.Frame(parent, bg=Theme.BG_CARD)
        frame.pack(side=tk.LEFT, expand=True)
        
        val_label = tk.Label(frame, text=value, font=self.fonts['heading'],
                            bg=Theme.BG_CARD, fg=color)
        val_label.pack()
        
        tk.Label(frame, text=label, font=self.fonts['small'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_MUTED).pack()
        
        setattr(self, attr_name, val_label)
    
    def create_output_panel(self, parent):
        """Create the test output log panel"""
        # Card container
        card = tk.Frame(parent, bg=Theme.BG_CARD, padx=15, pady=15)
        card.pack(fill=tk.BOTH, expand=True)
        
        # Header with title and clear button
        header = tk.Frame(card, bg=Theme.BG_CARD)
        header.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(header, text="Test Output", font=self.fonts['subheading'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY).pack(side=tk.LEFT)
        
        ModernButton(header, "Clear", self.clear_output,
                    width=70, height=28, bg_color=Theme.BG_LIGHT).pack(side=tk.RIGHT, padx=(5, 0))
        
        ModernButton(header, "Copy All", self.copy_output,
                    width=80, height=28, bg_color=Theme.ACCENT_INFO).pack(side=tk.RIGHT)
        
        # Output text area with custom styling
        text_frame = tk.Frame(card, bg=Theme.BG_MEDIUM, padx=2, pady=2)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.output_text = scrolledtext.ScrolledText(
            text_frame, 
            font=self.fonts['mono'],
            bg=Theme.BG_DARK,
            fg=Theme.TEXT_PRIMARY,
            insertbackground=Theme.TEXT_PRIMARY,
            selectbackground=Theme.ACCENT_PRIMARY,
            relief=tk.FLAT,
            padx=10,
            pady=10,
            wrap=tk.WORD
        )
        self.output_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure text tags for colored output
        self.output_text.tag_configure("success", foreground=Theme.ACCENT_SUCCESS)
        self.output_text.tag_configure("error", foreground=Theme.ACCENT_ERROR)
        self.output_text.tag_configure("warning", foreground=Theme.ACCENT_WARNING)
        self.output_text.tag_configure("info", foreground=Theme.ACCENT_INFO)
        self.output_text.tag_configure("header", foreground=Theme.ACCENT_PRIMARY, 
                                       font=(self.fonts['mono'][0], self.fonts['mono'][1], 'bold'))
    
    def log(self, message, tag=None):
        """Add message to output with optional styling"""
        # Auto-detect message type for coloring
        if tag is None:
            if "✅" in message or "PASS" in message:
                tag = "success"
            elif "❌" in message or "FAIL" in message or "Error" in message:
                tag = "error"
            elif "⚠️" in message or "Warning" in message:
                tag = "warning"
            elif "===" in message:
                tag = "header"
        
        self.output_text.insert(tk.END, message + "\n", tag)
        self.output_text.see(tk.END)
        self.root.update()
    
    def copy_output(self):
        """Copy all output text to clipboard"""
        text = self.output_text.get(1.0, tk.END).strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.log("📋 Output copied to clipboard!", "success")
        else:
            self.log("⚠️ Nothing to copy", "warning")
    
    def clear_output(self):
        """Clear the output log and reset test status indicator"""
        self.output_text.delete(1.0, tk.END)
        
        
        # Reset status indicator to idle state
        self.status_indicator.set_idle()
        self.result_text.config(text="Ready to test", fg=Theme.TEXT_MUTED)
        
        # Reset stats
        self.passed_stat.config(text="0")
        self.failed_stat.config(text="0")
        self.total_stat.config(text="0")
        
        # Clear last result
        self.last_result = None
        
        self.log("🔄 Output cleared. Ready for new test.", "info")
    
    def show_help(self):
        """Open the help dialog"""
        HelpDialog(self.root)
    
    def on_chip_selected(self, event):
        """Update chip info when selection changes and show/hide appropriate buttons"""
        chip_id = self.chip_var.get()
        chip = self.chip_db.get_chip(chip_id)
        if chip:
            self.chip_info.config(text=f"{chip['name']}\n{chip.get('description', '')[:100]}...")
            
            # Populate pin mapping panel with chip pins
            if hasattr(self, 'pin_mapping_frame'):
                self.populate_pin_mapping(chip)
            
            # Show/hide Run Counter button based on chip type (only if buttons exist)
            if hasattr(self, 'run_counter_btn'):
                # Counter chips have clock inputs (CKA, CKB, CLK, etc.)
                input_names = [p['name'] for p in chip.get('pinout', {}).get('inputs', [])]
                is_counter = any(name in input_names for name in ['CKA', 'CKB', 'CLK', 'CLOCK'])
                
                if is_counter:
                    self.run_counter_btn.pack(side=tk.LEFT)
                    self.counter_display.pack(pady=(5, 0))
                else:
                    self.run_counter_btn.pack_forget()
                    self.counter_display.pack_forget()
                    self.counter_display.config(text="")
    
    def start_counter(self):
        """Start continuous counter mode - clock the chip and show live values"""
        if not self.arduino.connected:
            self.log("❌ Connect to Arduino first!", "error")
            return
        
        if self.counter_running:
            return
        
        chip_id = self.chip_var.get()
        chip_data = self.chip_db.get_chip(chip_id)
        if not chip_data:
            self.log("❌ No chip selected!", "error")
            return
        
        self.counter_running = True
        self.log("⏱ Starting continuous counter mode...", "info")
        
        # Show stop button, hide run counter button
        self.run_counter_btn.pack_forget()
        self.stop_btn.pack(side=tk.LEFT)
        
        # Reset chip to 0 first - set ALL inputs to known state
        self.log("  Resetting all inputs LOW...")
        self.tester.set_pin_state(chip_data, 'CKA', 'LOW')
        self.tester.set_pin_state(chip_data, 'CKB', 'LOW')
        self.tester.set_pin_state(chip_data, 'R9_1', 'LOW')
        self.tester.set_pin_state(chip_data, 'R9_2', 'LOW')
        self.tester.set_pin_state(chip_data, 'R0_1', 'LOW')
        self.tester.set_pin_state(chip_data, 'R0_2', 'LOW')
        time.sleep(0.2)
        
        # Now pulse reset to 0
        self.log("  Pulsing R0_1 and R0_2 HIGH to reset to 0...")
        self.tester.set_pin_state(chip_data, 'R0_1', 'HIGH')
        self.tester.set_pin_state(chip_data, 'R0_2', 'HIGH')
        time.sleep(0.3)  # Hold reset longer
        self.tester.set_pin_state(chip_data, 'R0_1', 'LOW')
        self.tester.set_pin_state(chip_data, 'R0_2', 'LOW')
        time.sleep(0.2)
        
        # Start counter loop in background
        def counter_loop():
            count = 0
            while self.counter_running:
                # Read current outputs
                qa = self.tester.read_pin_state(chip_data, 'QA') or '?'
                qb = self.tester.read_pin_state(chip_data, 'QB') or '?'
                qc = self.tester.read_pin_state(chip_data, 'QC') or '?'
                qd = self.tester.read_pin_state(chip_data, 'QD') or '?'
                
                # Convert to binary display
                qa_bit = '1' if qa == 'HIGH' else '0'
                qb_bit = '1' if qb == 'HIGH' else '0'
                qc_bit = '1' if qc == 'HIGH' else '0'
                qd_bit = '1' if qd == 'HIGH' else '0'
                
                # Calculate decimal value (BCD: QD=8, QC=4, QB=2, QA=1)
                try:
                    decimal = (int(qd_bit) * 8) + (int(qc_bit) * 4) + (int(qb_bit) * 2) + int(qa_bit)
                except:
                    decimal = '?'
                
                # Update display
                display_text = f"Count: {decimal}  |  QD QC QB QA = {qd_bit} {qc_bit} {qb_bit} {qa_bit}"
                self.counter_display.config(text=display_text)
                self.log(f"  {display_text}")
                self.root.update()
                
                # 7490 DECADE COUNTING: Must simulate QA→CKB connection
                # CKA only drives QA. CKB drives QB/QC/QD.
                # For 0-9 counting: when QA falls (HIGH→LOW), clock CKB
                
                # Remember QA state before clocking
                qa_before = qa
                
                # Pulse CKA (falling edge triggers QA toggle)
                self.tester.set_pin_state(chip_data, 'CKA', 'HIGH')
                time.sleep(0.05)
                self.tester.set_pin_state(chip_data, 'CKA', 'LOW')
                time.sleep(0.1)
                
                # Read QA after pulse
                qa_after = self.tester.read_pin_state(chip_data, 'QA') or '?'
                
                # If QA went HIGH→LOW, simulate the QA→CKB connection by pulsing CKB
                if qa_before == 'HIGH' and qa_after == 'LOW':
                    self.tester.set_pin_state(chip_data, 'CKB', 'HIGH')
                    time.sleep(0.05)
                    self.tester.set_pin_state(chip_data, 'CKB', 'LOW')
                    time.sleep(0.1)
                
                time.sleep(0.2)  # Wait between counts
                count += 1
                
                if count > 25:  # Safety limit
                    self.counter_running = False
                    self.log("⏹ Counter stopped (reached limit)", "warning")
            
            # Cleanup
            self.stop_btn.pack_forget()
            self.run_counter_btn.pack(side=tk.LEFT)
            self.log("⏹ Counter stopped", "info")
        
        # Run in thread to keep GUI responsive
        import threading
        thread = threading.Thread(target=counter_loop, daemon=True)
        thread.start()
    
    def stop_counter(self):
        """Stop the continuous counter mode"""
        self.counter_running = False
        self.counter_display.config(text="")
    
    def identify_chip(self):
        """Attempt to identify an unknown chip based on its behavior"""
        if not self.arduino.connected:
            self.log("❌ Connect to Arduino first!", "error")
            return
        
        self.log("=" * 50, "info")
        self.log("🔍 CHIP IDENTIFICATION MODE", "info")
        self.log("=" * 50, "info")
        self.log("Testing chip against known patterns...", "info")
        
        # Update status
        self.status_indicator.set_testing()
        self.result_text.config(text="Identifying...", fg=Theme.ACCENT_INFO)
        
        
        self.root.update()
        
        # Run identification
        chip_id, confidence, message = self.tester.identify_chip(self.log)
        
        if chip_id and confidence >= 80:
            self.log(f"\n✅ {message}", "success")
            self.status_indicator.set_pass()
            self.result_text.config(text=f"Detected: {chip_id}", fg=Theme.ACCENT_SUCCESS)
            
            
            # Offer to switch to detected chip
            if chip_id != self.chip_var.get():
                self.log(f"\n💡 Tip: Selected chip is {self.chip_var.get()}, but detected {chip_id}", "warning")
                self.log(f"   Consider switching to {chip_id} in the dropdown.", "warning")
        elif chip_id and confidence >= 50:
            self.log(f"\n⚠️ {message}", "warning")
            self.status_indicator.set_idle()
            self.result_text.config(text=f"Maybe: {chip_id}?", fg=Theme.ACCENT_WARNING)
            
        else:
            self.log(f"\n❌ {message}", "error")
            self.status_indicator.set_failed()
            self.result_text.config(text="Unknown chip", fg=Theme.ACCENT_ERROR)
            
    
    def scan_ports(self):
        """Scan for Arduino ports with cooldown to prevent rapid clicking"""
        # Check cooldown
        if self.scan_cooldown:
            self.log("⏳ Please wait before scanning again...", "warning")
            return
        
        # Check if already connected - no need to scan
        if self.arduino.connected:
            self.log("ℹ️ Already connected. Disconnect first to scan for new devices.", "info")
            return
        
        # Activate cooldown
        self.scan_cooldown = True
        self.scan_btn.draw_button(Theme.TEXT_MUTED)  # Visual feedback - greyed out
        
        self.log("🔍 Scanning for Arduino devices...", "info")
        ports = self.arduino.find_arduino_ports()
        
        if ports:
            self.port_combo['values'] = ports
            self.port_combo.current(0)
            self.log(f"✅ Found {len(ports)} device(s): {', '.join(ports)}", "success")
        else:
            self.port_combo['values'] = []
            self.log("⚠️ No Arduino devices found!", "warning")
        
        # Reset cooldown after delay
        def reset_cooldown():
            self.scan_cooldown = False
            if self.scan_btn:
                self.scan_btn.draw_button(Theme.BG_LIGHT)  # Restore normal color
        
        self.root.after(self.scan_cooldown_seconds * 1000, reset_cooldown)
    
    def connect_arduino(self):
        """Connect to selected Arduino"""
        # Edge case: Already connected
        if self.arduino.connected:
            self.log("ℹ️ Already connected to Arduino.", "info")
            return
        
        port = self.port_var.get()
        if not port:
            messagebox.showerror("No Port Selected", 
                               "Please select a port first.\n\n"
                               "Click 'Scan' to find available Arduino devices.")
            return
        
        self.log(f"🔌 Connecting to {port}...")
        self.conn_status.config(text="Connecting...", fg=Theme.PENDING)
        self.root.update()
        
        if self.arduino.connect(port):
            self.status_dot.delete("all")
            self.status_dot.create_oval(2, 2, 10, 10, fill=Theme.CONNECTED, outline="")
            self.conn_status.config(text="Connected", fg=Theme.CONNECTED)
            self.log("✅ Arduino connected successfully!", "success")
            
            
            # Swap Connect button for Disconnect button
            self.connect_btn.pack_forget()
            self.disconnect_btn.pack(side=tk.LEFT)
            
            # Disable port selection while connected
            self.port_combo.config(state='disabled')
        else:
            self.status_dot.delete("all")
            self.status_dot.create_oval(2, 2, 10, 10, fill=Theme.DISCONNECTED, outline="")
            self.conn_status.config(text="Failed", fg=Theme.DISCONNECTED)
            self.log("❌ Failed to connect to Arduino", "error")
            messagebox.showerror("Connection Failed", 
                               "Could not connect to Arduino.\n\nCheck:\n"
                               "1. Arduino IDE is closed\n"
                               "2. Sketch is uploaded\n"
                               "3. Correct port selected")
    
    def disconnect_arduino(self):
        """Safely disconnect from Arduino"""
        # Edge case: Test in progress
        if self.is_testing:
            result = messagebox.askyesno("Test in Progress",
                                        "A test is currently running.\n\n"
                                        "Disconnecting now may cause incomplete results.\n"
                                        "Are you sure you want to disconnect?")
            if not result:
                return
            self.is_testing = False
        
        self.log("🔌 Disconnecting from Arduino...", "info")
        self.arduino.disconnect()
        
        # Update UI
        self.status_dot.delete("all")
        self.status_dot.create_oval(2, 2, 10, 10, fill=Theme.DISCONNECTED, outline="")
        self.conn_status.config(text="Disconnected", fg=Theme.DISCONNECTED)
        
        # Swap Disconnect button for Connect button
        self.disconnect_btn.pack_forget()
        self.connect_btn.pack(side=tk.LEFT)
        
        # Re-enable port selection
        self.port_combo.config(state='readonly')
        
        self.log("✅ Arduino disconnected safely.", "success")
    
    def start_connection_monitor(self):
        """Monitor connection health and detect unexpected disconnections"""
        def check_connection():
            if self.arduino.connected:
                try:
                    # Try to verify connection is still alive
                    if self.arduino.arduino and not self.arduino.arduino.is_open:
                        raise Exception("Port closed")
                except:
                    # Connection lost unexpectedly
                    self.log("⚠️ Arduino connection lost unexpectedly!", "error")
                    self.arduino.connected = False
                    
                    # Update UI
                    self.status_dot.delete("all")
                    self.status_dot.create_oval(2, 2, 10, 10, fill=Theme.DISCONNECTED, outline="")
                    self.conn_status.config(text="Disconnected", fg=Theme.DISCONNECTED)
                    
                    # Swap buttons
                    self.disconnect_btn.pack_forget()
                    self.connect_btn.pack(side=tk.LEFT)
                    self.port_combo.config(state='readonly')
                    
                    # Reset test state if testing
                    if self.is_testing:
                        self.is_testing = False
                        self.status_indicator.set_failed()
                        self.result_text.config(text="CONNECTION LOST", fg=Theme.ACCENT_ERROR)
            
            # Schedule next check
            self.root.after(self.connection_check_interval, check_connection)
        
        # Start monitoring
        self.root.after(self.connection_check_interval, check_connection)
    
    def run_test(self):
        """Run test on selected chip with edge case handling"""
        # Edge case: Not connected
        if not self.arduino.connected:
            messagebox.showerror("Not Connected", 
                               "Please connect to Arduino first.\n\n"
                               "1. Click 'Scan' to find your Arduino\n"
                               "2. Select the port\n"
                               "3. Click 'Connect'")
            return
        
        # Edge case: Test already in progress
        if self.is_testing:
            self.log("⚠️ Test already in progress. Please wait...", "warning")
            messagebox.showwarning("Test in Progress", 
                                  "A test is already running.\n\n"
                                  "Please wait for it to complete before starting another.")
            return
        
        # Edge case: No chip selected
        chip_id = self.chip_var.get()
        if not chip_id:
            messagebox.showerror("No Chip Selected", 
                               "Please select a chip to test.\n\n"
                               "If no chips are available, add JSON files\n"
                               "to the 'chips/' folder and restart.")
            return
        
        # Edge case: Chip data validation
        chip_data = self.chip_db.get_chip(chip_id)
        if not chip_data:
            self.log(f"❌ Error: Chip {chip_id} data not found!", "error")
            messagebox.showerror("Chip Data Error", 
                               f"Could not load data for chip {chip_id}.\n\n"
                               "The JSON file may be corrupted or missing.")
            return
        
        # Validate chip has required fields (arduinoMapping no longer required - user provides it)
        required_fields = ['pinout', 'testSequence']
        missing_fields = [f for f in required_fields if f not in chip_data]
        if missing_fields:
            self.log(f"❌ Error: Chip {chip_id} is missing required fields: {missing_fields}", "error")
            messagebox.showerror("Invalid Chip Definition", 
                               f"Chip {chip_id} is missing required fields:\n"
                               f"{', '.join(missing_fields)}\n\n"
                               "Please check the JSON file format.")
            return
        
        # Validate user pin mapping before running test
        if not self.validate_pin_mapping():
            messagebox.showerror("Invalid Pin Mapping", 
                               "Please configure valid Arduino pin mappings.\n\n"
                               "Enter the Arduino pin number for each chip pin\n"
                               "in the Pin Mapping panel, then click Validate.")
            return
        
        # Get user-defined Arduino mapping
        user_mapping = self.get_user_arduino_mapping()
        if not user_mapping:
            self.log("❌ No valid pin mapping configured!", "error")
            return
        
        # Set testing state
        self.is_testing = True
        
        # Update UI for testing state
        self.status_indicator.set_testing()
        self.result_text.config(text="Testing...", fg=Theme.ACCENT_WARNING)
        
        
        # Disable test button during test
        self.test_btn.draw_button(Theme.TEXT_MUTED)
        
        self.log("\n" + "═" * 50, "header")
        self.log(f"  TESTING: {chip_id}", "header")
        self.log("═" * 50, "header")
        
        # Run test in thread with user-defined pin mapping
        def test_thread():
            try:
                results = self.tester.run_test(chip_id, progress_callback=self.log, 
                                               custom_mapping=user_mapping)
                self.root.after(0, lambda: self.display_results(results))
            except Exception as e:
                self.root.after(0, lambda: self.handle_test_error(str(e)))
        
        threading.Thread(target=test_thread, daemon=True).start()
    
    def handle_test_error(self, error_msg):
        """Handle errors that occur during testing"""
        self.is_testing = False
        self.test_btn.draw_button(Theme.ACCENT_SUCCESS)
        
        self.status_indicator.set_failed()
        self.result_text.config(text="TEST ERROR", fg=Theme.ACCENT_ERROR)
        
        
        self.log(f"\n❌ Test error: {error_msg}", "error")
        messagebox.showerror("Test Error", 
                           f"An error occurred during testing:\n\n{error_msg}\n\n"
                           "Check your wiring and try again.")
    
    
    def display_results(self, results):
        """Display test results with visual indicators"""
        # Reset testing state
        self.is_testing = False
        self.test_btn.draw_button(Theme.ACCENT_SUCCESS)  # Re-enable test button
        
        self.last_result = results
        
        # Check for power verification failure
        if not results.get('powerVerified', True):
            self.status_indicator.set_failed()
            self.result_text.config(text="POWER ERROR", fg=Theme.ACCENT_ERROR)
            
            
            error_msg = results.get('error', 'Power verification failed')
            self.log("\n" + "─" * 50)
            self.log("⚡ POWER CHECK FAILED", "error")
            self.log("─" * 50)
            self.log(f"Error: {error_msg}", "error")
            self.log("\nPlease check:", "warning")
            self.log("  • Arduino is properly connected via USB", "warning")
            self.log("  • VCC pin connected to Arduino 5V", "warning")
            self.log("  • GND pin connected to Arduino GND", "warning")
            self.log("  • Chip is seated correctly in socket", "warning")
            self.log("═" * 50 + "\n", "header")
            return
        
        # Check for pin connection verification failure
        if not results.get('pinsVerified', True):
            self.status_indicator.set_failed()
            self.result_text.config(text="PIN ERROR", fg=Theme.ACCENT_ERROR)
            
            
            error_msg = results.get('error', 'Pin verification failed')
            problem_pins = results.get('problemPins', [])
            
            self.log("\n" + "─" * 50)
            self.log("🔌 PIN CONNECTION CHECK FAILED", "error")
            self.log("─" * 50)
            self.log(f"Error: {error_msg}", "error")
            
            if problem_pins:
                self.log("\nProblem pins detected:", "warning")
                for pin in problem_pins:
                    self.log(f"  • Chip Pin {pin['chip_pin']} ({pin['name']}) → Arduino Pin {pin['arduino_pin']}", "error")
            
            self.log("\nPlease check:", "warning")
            self.log("  • All jumper wires are firmly connected", "warning")
            self.log("  • Wires are in the correct Arduino pins", "warning")
            self.log("  • Chip is seated properly (no bent pins)", "warning")
            self.log("  • No loose connections on breadboard", "warning")
            self.log("═" * 50 + "\n", "header")
            return
        
        # Update stats
        self.passed_stat.config(text=str(results['testsPassed']))
        self.failed_stat.config(text=str(results['testsFailed']))
        self.total_stat.config(text=str(results['testsRun']))
        
        self.log("\n" + "─" * 50)
        self.log("TEST RESULTS", "header")
        self.log("─" * 50)
        self.log(f"⚡ Power: Verified", "success")
        self.log(f"🔌 Pins: All connected", "success")
        self.log(f"Chip: {results['chipName']} ({results['chipId']})")
        self.log(f"Tests Run: {results['testsRun']}")
        self.log(f"Passed: {results['testsPassed']}", "success")
        self.log(f"Failed: {results['testsFailed']}", "error" if results['testsFailed'] > 0 else None)
        
        if results['success']:
            self.status_indicator.set_passed()
            self.result_text.config(text="ALL TESTS PASSED", fg=Theme.ACCENT_SUCCESS)
            self.log("\n🎉 CHIP PASSED ALL TESTS! ✅", "success")
            
        else:
            self.status_indicator.set_failed()
            self.result_text.config(text="TESTS FAILED", fg=Theme.ACCENT_ERROR)
            self.log("\n❌ CHIP FAILED - See details above", "error")
            
            
            # Auto-detect if wrong chip might be inserted
            self.log("\n🔍 Checking if a different chip is inserted...", "info")
            self.root.update()
            
            detected_id, confidence, message = self.tester.identify_chip(self.log)
            
            if detected_id and detected_id != results['chipId'] and confidence >= 70:
                self.log(f"\n⚠️ WRONG CHIP DETECTED!", "warning")
                self.log(f"   You selected: {results['chipId']}", "warning")
                self.log(f"   Detected chip: {detected_id} ({confidence:.0f}% match)", "warning")
                self.log(f"   → Try selecting '{detected_id}' from the dropdown", "info")
                self.result_text.config(text=f"Wrong chip? Try {detected_id}", fg=Theme.ACCENT_WARNING)
            elif detected_id == results['chipId'] and confidence >= 70:
                self.log(f"\n✓ Chip appears to be {detected_id}, but some tests failed", "info")
                self.log("   The chip may be defective or have intermittent issues", "warning")
        
        self.log("═" * 50 + "\n", "header")
    
    def run(self):
        """Start the GUI"""
        # Center window on screen
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        
        self.root.mainloop()


def main():
    """Main entry point"""
    app = ICTesterGUI()
    app.run()


if __name__ == "__main__":
    main()
