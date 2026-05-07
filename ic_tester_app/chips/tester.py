# ic_tester_app/chips/tester.py
# Last edited: 2026-01-19
# Purpose: IC testing logic - runs test sequences and verifies chip functionality
# Dependencies: time

"""
IC test execution engine.

This module is the core runtime path for an actual chip test. It takes the
selected chip definition plus a resolved Arduino pin mapping and performs the
entire hardware workflow:

1. Confirm the Arduino is still alive.
2. Confirm the wired chip is responding to basic state changes.
3. Execute every JSON-defined test vector.
4. Track per-pin reliability so the GUI can explain failures.
5. Optionally probe definitions to guess whether the wrong chip is inserted.
"""

import time
from typing import Optional, Dict, List, Tuple, Any, Callable

from ..logger import get_logger

logger = get_logger("chips.tester")

# Type alias for the GUI logger callback used throughout the test pipeline.
ProgressCallback = Optional[Callable[[str], None]]


class ICTester:
    """
    Main IC testing logic engine.
    
    Coordinates with Arduino to run test sequences defined in chip JSON files.
    Supports custom pin mappings for flexible hardware configurations.
    
    Attributes:
        arduino: ArduinoConnection instance for hardware communication
        chip_db: ChipDatabase instance for chip definitions
    """
    
    def __init__(self, arduino_conn, chip_db):
        """
        Initialize IC Tester.
        
        Args:
            arduino_conn: ArduinoConnection instance
            chip_db: ChipDatabase instance
        """
        self.arduino = arduino_conn
        self.chip_db = chip_db
        self._abort_flag = False
        logger.info("ICTester initialized")
    
    def abort(self):
        """Signal the current test to abort"""
        self._abort_flag = True
        logger.info("Test abort requested")
    
    def _check_abort(self) -> bool:
        """Check if abort was requested. Returns True if should abort."""
        if self._abort_flag:
            logger.info("Test aborted by user")
            return True
        return False
    
    # =========================================================================
    # Arduino Connectivity Check
    # =========================================================================
    
    def verify_arduino(self, progress_callback: ProgressCallback = None) -> Tuple[bool, str]:
        """
        Verify that Arduino is responding to commands.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        # First make sure the operating system still sees the USB device.
        # This catches hard disconnects before we start a test sequence.
        if not self.arduino.is_port_alive():
            logger.error("Arduino USB port is no longer available")
            return (False, "Arduino disconnected - USB port not found. "
                    "Check cable and try reconnecting.")
        
        # Clear stale bytes from a previous test/handshake so the PING probe does
        # not accidentally read an old response and produce a false positive.
        if not self.arduino.clear_buffer():
            logger.error("Failed to clear serial buffer - port may have dropped")
            return (False, "Arduino connection lost during buffer clear. "
                    "Try unplugging and re-plugging the USB cable.")
        time.sleep(0.1)
        
        # The board may still be settling after reconnect or buffer clear, so a
        # few retries make the check tolerant without hiding persistent failure.
        max_retries = 3
        for attempt in range(max_retries):
            response = self.arduino.send_and_receive("PING", timeout=2.0)
            if response and "PONG" in response:
                break
            logger.debug(f"PING attempt {attempt + 1}/{max_retries} failed, response: {response}")
            if not self.arduino.is_port_alive():
                return (False, "Arduino disconnected during PING. "
                        "USB cable may be loose.")
            time.sleep(0.2)
        else:
            logger.error(f"Arduino not responding to PING after {max_retries} attempts")
            return (False, "Arduino not responding - check USB connection")
        
        if progress_callback:
            progress_callback("✅ Arduino responding to commands")
        
        logger.info("Arduino connectivity check passed")
        return (True, "Arduino connected and responding")
    
    # =========================================================================
    # Pin Connection Verification
    # =========================================================================
    
    def verify_pin_connections(self, chip_data: Dict, progress_callback: ProgressCallback = None) -> Tuple[bool, str, List]:
        """
        Verify all pin connections by running initial test patterns.
        
        Uses the first 2 tests from the chip's test sequence to verify that the
        chip can actually change state and that each output line responds in the
        expected direction. Reads use 3x voting so one noisy sample does not
        immediately look like a wiring fault.
        
        Args:
            chip_data: Chip definition dictionary
            progress_callback: Optional function for progress updates
        
        Returns:
            Tuple of (success: bool, message: str, problem_pins: list)
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
        
        # Convert the JSON pinout into quick lookups so the verification code can
        # work in terms of semantic pin names instead of repeatedly scanning lists.
        input_pins = {p['name']: p['pin'] for p in pinout.get('inputs', [])}
        output_pins = {p['name']: p['pin'] for p in pinout.get('outputs', [])}
        
        # Helper functions
        def set_pin(arduino_pin: int, state: str) -> bool:
            """Set a pin with verification"""
            for attempt in range(3):
                # We deliberately talk to the firmware at the raw command level
                # here because verification wants tight control over retry timing.
                self.arduino.send_command(f"SET_PIN,{arduino_pin},{state}")
                response = self.arduino.read_response()
                if response and "SET_PIN_OK" in response:
                    return True
                time.sleep(0.05)
            return False
        
        def set_inputs_from_test(test_inputs: Dict, verbose: bool = False):
            """Set all inputs according to test definition"""
            for pin_name, state in test_inputs.items():
                chip_pin = input_pins.get(pin_name)
                if chip_pin:
                    arduino_pin = mapping.get(str(chip_pin))
                    if arduino_pin:
                        success = set_pin(arduino_pin, state)
                        if verbose and progress_callback:
                            status = "✓" if success else "✗"
                            progress_callback(f"    {status} Set {pin_name} (chip pin {chip_pin} → Arduino {arduino_pin}) = {state}")
                        if not success:
                            if progress_callback:
                                progress_callback(f"    ⚠️ Failed to set {pin_name} to {state}")
                        time.sleep(0.03)
                    elif verbose and progress_callback:
                        progress_callback(f"    ⚠️ No Arduino mapping for {pin_name} (chip pin {chip_pin})")
        
        def read_pin_voted(arduino_pin: int) -> str:
            """Read a pin with 3x voting for reliability"""
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
            
            # Majority vote smooths out transient read glitches caused by loose
            # jumpers or a chip output still settling.
            high_count = reads.count("HIGH")
            low_count = reads.count("LOW")
            error_count = reads.count("ERROR")
            
            if error_count >= 2:
                return "ERROR"
            elif high_count > low_count:
                return "HIGH"
            else:
                return "LOW"
        
        def read_all_outputs(verbose: bool = False) -> Dict[str, str]:
            """Read all output pins with voting"""
            results = {}
            for pin_name, chip_pin in output_pins.items():
                arduino_pin = mapping.get(str(chip_pin))
                if arduino_pin:
                    value = read_pin_voted(arduino_pin)
                    results[pin_name] = value
                    if verbose and progress_callback:
                        progress_callback(f"    📖 Read {pin_name} (chip pin {chip_pin} → Arduino {arduino_pin}) = {value}")
            return results
        
        # Run first 2 tests for verification
        test1 = tests[0]
        test2 = tests[1]
        
        # Show pin mapping being used for debugging
        if progress_callback:
            progress_callback("  📋 Pin mapping in use:")
            progress_callback(f"    INPUTS: " + ", ".join([f"{n}(pin {p})→Ard.{mapping.get(str(p),'?')}" for n, p in input_pins.items()]))
            progress_callback(f"    OUTPUTS: " + ", ".join([f"{n}(pin {p})→Ard.{mapping.get(str(p),'?')}" for n, p in output_pins.items()]))
        
        # STATE 1: First test
        if progress_callback:
            progress_callback(f"  STATE 1: {test1.get('description', 'Test 1')}...")
        
        set_inputs_from_test(test1.get('inputs', {}), verbose=True)
        time.sleep(0.25)
        state1 = read_all_outputs(verbose=True)
        expected1 = test1.get('expectedOutputs', {})
        
        if progress_callback:
            output_str = ", ".join([f"{name}={state1.get(name,'?')}" for name in output_pins.keys()])
            progress_callback(f"    Read: {output_str}")
        
        # STATE 2: Second test
        if progress_callback:
            progress_callback(f"  STATE 2: {test2.get('description', 'Test 2')}...")
        
        set_inputs_from_test(test2.get('inputs', {}), verbose=True)
        time.sleep(0.25)
        state2 = read_all_outputs(verbose=True)
        expected2 = test2.get('expectedOutputs', {})
        
        if progress_callback:
            output_str = ", ".join([f"{name}={state2.get(name,'?')}" for name in output_pins.keys()])
            progress_callback(f"    Read: {output_str}")
        
        # Before comparing against exact expectations, check for the more basic
        # failure mode: none of the outputs changed at all. That almost always
        # points to missing power, ground, or a badly seated chip.
        any_changed = any(state1.get(pin) != state2.get(pin) for pin in output_pins.keys())
        
        if not any_changed:
            if progress_callback:
                progress_callback("  ❌ No outputs changed between states - CHIP NOT RESPONDING!")
                progress_callback("     Check VCC and GND connections.")
            logger.error("Chip not responding - no output changes detected")
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
        
        # Verify all output pins — ERROR responses (no reply at all) are hard
        # failures. Value mismatches are warnings only: things like LED loading
        # or chip settling can cause a single read to disagree with the expected
        # truth-table value without meaning the chip or wire is actually broken.
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
            
            if 'ERROR' in [val1, val2]:
                # Hard failure — Arduino got no response at all from the pin
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
                # Soft warning — pin responded but value differs from expected.
                # Could be LED loading, slow settling, or a legitimate chip fault.
                # We log it but do not block the full test run.
                if progress_callback:
                    progress_callback(f"  ⚠️  {pin_name} (pin {chip_pin}): Got {val1}/{val2}, expected {exp1}/{exp2} (proceeding anyway)")
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
            logger.warning(f"Pin verification found {len(problem_pins)} problem(s)")
            return (False, f"{len(problem_pins)} output pin(s) not responding correctly", problem_pins)
        
        if progress_callback:
            progress_callback(f"✅ All output pins verified - chip responding correctly")
        
        logger.info("Pin verification passed")
        return (True, "All pins connected and chip responding", [])
    
    # =========================================================================
    # Pin Control Helpers
    # =========================================================================
    
    def setup_pins(self, chip_data: Dict):
        """
        Configure Arduino pins for the chip by setting all to LOW.
        
        Args:
            chip_data: Chip definition dictionary
        """
        mapping = chip_data['arduinoMapping']['io']
        
        for chip_pin, arduino_pin in mapping.items():
            self.arduino.send_command(f"SET_PIN,{arduino_pin},LOW")
            time.sleep(0.05)
        
        logger.debug(f"Set up {len(mapping)} pins")
    
    def set_pin_state(self, chip_data: Dict, pin_name: str, state: str) -> bool:
        """
        Set a chip input pin to HIGH or LOW with retry logic.
        
        Args:
            chip_data: Chip definition dictionary
            pin_name: Name of the pin (from chip definition)
            state: 'HIGH' or 'LOW'
        
        Returns:
            True if successful, False otherwise
        """
        # Find the chip pin number for this pin name
        chip_pin = None
        for input_pin in chip_data['pinout']['inputs']:
            if input_pin['name'] == pin_name:
                chip_pin = input_pin['pin']
                break
        
        if chip_pin is None:
            logger.warning(f"Pin name '{pin_name}' not found in chip inputs")
            return False
        
        # Get corresponding Arduino pin
        arduino_pin = chip_data['arduinoMapping']['io'].get(str(chip_pin))
        if arduino_pin is None:
            logger.warning(f"No Arduino mapping for chip pin {chip_pin}")
            return False
        
        # Send command with retry logic (fast version matching verification)
        for attempt in range(3):
            self.arduino.send_command(f"SET_PIN,{arduino_pin},{state}")
            response = self.arduino.read_response()
            if response and "SET_PIN_OK" in response:
                return True
            time.sleep(0.05)
        
        logger.warning(f"Failed to set pin {pin_name} to {state} after 3 attempts")
        return False
    
    def read_pin_state(self, chip_data: Dict, pin_name: str) -> Optional[str]:
        """
        Read state of a chip output pin with 3x voting for reliability.
        
        Args:
            chip_data: Chip definition dictionary
            pin_name: Name of the output pin
        
        Returns:
            'HIGH', 'LOW', or None if error
        """
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
        
        # Read with 3x voting for reliability
        reads = []
        for _ in range(3):
            self.arduino.send_command(f"READ_PIN,{arduino_pin}")
            response = self.arduino.read_response()
            
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
    
    # =========================================================================
    # Main Test Runner
    # =========================================================================
    
    def run_test(self, chip_id: str, progress_callback: ProgressCallback = None,
                 custom_mapping: Optional[Dict] = None,
                 board: str = "MEGA", **kwargs) -> Dict[str, Any]:
        """
        Run complete test sequence for a chip.
        
        This is the main testing method that:
        1. Verifies Arduino connectivity
        2. Verifies pin connections
        3. Runs all tests from the chip's test sequence
        4. Collects and returns results
        
        Args:
            chip_id: ID of the chip to test (e.g., '7490', '7414')
            progress_callback: Optional function for progress updates
            custom_mapping: Optional user-defined Arduino pin mapping
                           {chip_pin_str: arduino_pin_int}
                           Overrides the JSON-defined arduinoMapping if provided
            board: Board profile to use when resolving chip data
        
        Returns:
            Dictionary with test results
        """
        logger.info(f"Starting test for chip {chip_id}")
        
        # Reset abort flag at start of test
        self._abort_flag = False
        
        chip_data = self.chip_db.get_chip(chip_id, board=board)
        if not chip_data:
            logger.error(f"Chip {chip_id} not found in database")
            return {"success": False, "error": f"Chip {chip_id} not found"}
        
        # The GUI can override the JSON mapping with a user-edited wiring table.
        # To preserve the database entry, we clone the chip definition first and
        # attach the custom mapping only to this one test run.
        if custom_mapping:
            chip_data = chip_data.copy()
            chip_data['arduinoMapping'] = {
                'io': custom_mapping,
            }
            if progress_callback:
                progress_callback(f"📌 Using user-defined pin mapping ({len(custom_mapping)} pins)")
            logger.info(f"Using custom pin mapping with {len(custom_mapping)} pins")

        # Pre-flight: verify every required IO pin has an entry in the mapping.
        # A test with missing input or output pins will silently produce wrong
        # results — it is much safer to refuse to run and tell the user exactly
        # which wires are absent.
        active_mapping = chip_data.get('arduinoMapping', {}).get('io', {})
        pinout = chip_data.get('pinout', {})
        missing_pins = []
        for p in pinout.get('inputs', []):
            if str(p['pin']) not in active_mapping:
                missing_pins.append(f"INPUT  {p['name']} (chip pin {p['pin']}) — not in mapping")
        for p in pinout.get('outputs', []):
            if str(p['pin']) not in active_mapping:
                missing_pins.append(f"OUTPUT {p['name']} (chip pin {p['pin']}) — not in mapping")

        if missing_pins:
            msg = f"Cannot run — {len(missing_pins)} pin(s) not mapped:"
            if progress_callback:
                progress_callback(f"❌ {msg}")
                for m in missing_pins:
                    progress_callback(f"   ⚠️  {m}")
                progress_callback("   Add these pins to the pin mapping before running the test.")
            logger.error(f"Pre-flight failed: {missing_pins}")
            results = {
                "chipId": chip_id,
                "chipName": chip_data.get('name', chip_id),
                "board": str(board).upper(),
                "testsRun": 0, "testsPassed": 0, "testsFailed": 0,
                "testDetails": [], "failedTests": [], "pinDiagnostics": {},
                "success": False, "pinsVerified": False,
                "error": msg,
                "missingPins": missing_pins,
            }
            return results
        
        # `results` is intentionally verbose because multiple downstream systems
        # consume it: the output log, dashboard, ML classifier, pattern analyzer,
        # report generator, and session history.
        results = {
            "chipId": chip_id,
            "chipName": chip_data['name'],
            "board": str(board).upper(),
            "testsRun": 0,
            "testsPassed": 0,
            "testsFailed": 0,
            "testDetails": [],
            "failedTests": [],
            "pinDiagnostics": {},
            "success": False,
            "pinsVerified": False
        }

        # Pre-populate diagnostics for every output pin so later code can update
        # counters without repeatedly checking whether a record exists.
        for out_pin in chip_data.get('pinout', {}).get('outputs', []):
            pin_name = out_pin['name']
            results['pinDiagnostics'][pin_name] = {
                'chipPin': out_pin['pin'],
                'arduinoPin': chip_data.get('arduinoMapping', {}).get('io', {}).get(str(out_pin['pin'])),
                'timesTested': 0,
                'timesCorrect': 0,
                'timesWrong': 0,
                'timesError': 0,
                'stuckState': None,
                'allReadValues': [],
                'failedTestIds': [],
                'wrongReadings': []
            }
        
        # Step 1: Verify Arduino connectivity
        if progress_callback:
            progress_callback("🔌 Checking Arduino connection...")
        
        arduino_ok, arduino_msg = self.verify_arduino(progress_callback)
        
        if not arduino_ok:
            if progress_callback:
                progress_callback(f"❌ Connection check failed: {arduino_msg}")
            results["error"] = f"Arduino check failed: {arduino_msg}"
            return results
        
        # Step 2: Verify pin connections before running the full vector list.
        # Failing early here gives much better feedback than letting dozens of
        # tests fail because one jumper is misplaced.
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
        
        # Note: Pin setup already done during verification - skip redundant setup
        
        # Step 3: Run the chip's full truth-table / test-vector sequence.
        tests = chip_data['testSequence']['tests']
        all_input_pins = [p['name'] for p in chip_data.get('pinout', {}).get('inputs', [])]
        mapping = chip_data.get('arduinoMapping', {}).get('io', {})

        # Build physical-pin lookups once so the progress log can always explain
        # failures in terms of both the logical signal name and the real wire.
        output_pin_info = {}
        for out_pin in chip_data.get('pinout', {}).get('outputs', []):
            pname = out_pin['name']
            cpin = out_pin['pin']
            apin = mapping.get(str(cpin), '?')
            output_pin_info[pname] = (cpin, apin)

        # Same for input pins
        input_pin_info = {}
        for in_pin in chip_data.get('pinout', {}).get('inputs', []):
            pname = in_pin['name']
            cpin = in_pin['pin']
            apin = mapping.get(str(cpin), '?')
            input_pin_info[pname] = (cpin, apin)

        # Consecutive failure streaks help distinguish a one-off mismatch from a
        # likely unplugged or stuck output line.
        pin_fail_streak = {name: 0 for name in output_pin_info}

        for test in tests:
            # Check for abort request
            if self._check_abort():
                if progress_callback:
                    progress_callback("⏹ Test aborted by user")
                results["error"] = "Test aborted by user"
                return results
            
            if 'inputs' not in test:
                continue  # Skip informational tests
            
            results['testsRun'] += 1
            test_id = test['testId']
            description = test['description']
            
            if progress_callback:
                progress_callback(f"Test {test_id}: {description}")
            
            # Start every vector from a clean baseline so no previous test leaves
            # an input asserted accidentally.
            for pin_name in all_input_pins:
                if self._abort_flag:
                    break
                self.set_pin_state(chip_data, pin_name, 'LOW')
            if self._abort_flag:
                continue
            time.sleep(0.05)
            
            # Apply only the inputs relevant to this vector after the reset pass.
            input_set_failed = False
            for pin_name, state in test['inputs'].items():
                if self._abort_flag:
                    break
                success = self.set_pin_state(chip_data, pin_name, state)
                if not success:
                    cpin, apin = input_pin_info.get(pin_name, ('?', '?'))
                    if progress_callback:
                        progress_callback(f"    ❌ Cannot set {pin_name} (chip pin {cpin} → Arduino {apin}) to {state}")
                        progress_callback(f"       Check that Arduino pin {apin} is wired to chip pin {cpin}.")
                    input_set_failed = True
                    self._abort_flag = True
                    break
            if self._abort_flag:
                if input_set_failed:
                    results["error"] = f"Wiring problem detected during test {test_id} — pin write failed. Check connections."
                continue
            
            time.sleep(0.05)  # Allow chip to settle after input changes

            # If this test vector requires clock pulses (for sequential chips),
            # pulse each listed pin HIGH then LOW to generate a falling edge.
            for clk_pin_name in test.get('clock', []):
                if self._abort_flag:
                    break
                self.set_pin_state(chip_data, clk_pin_name, 'HIGH')
                time.sleep(0.02)
                self.set_pin_state(chip_data, clk_pin_name, 'LOW')
                time.sleep(0.02)
            if self._abort_flag:
                continue

            time.sleep(0.05)  # Allow counter to settle after clock edges
            
            # Read the observable outputs and compare them to the expected
            # truth-table row defined in the chip JSON.
            test_passed = True
            actual_outputs = {}
            this_test_failures = []
            
            for pin_name, expected_state in test['expectedOutputs'].items():
                if self._abort_flag:
                    break
                actual_state = self.read_pin_state(chip_data, pin_name)
                actual_outputs[pin_name] = actual_state
                cpin, apin = output_pin_info.get(pin_name, ('?', '?'))
                
                if actual_state == expected_state:
                    pin_fail_streak[pin_name] = 0
                    if progress_callback:
                        progress_callback(f"    ✓ {pin_name} (pin {cpin}): {actual_state}")
                else:
                    test_passed = False
                    pin_fail_streak[pin_name] = pin_fail_streak.get(pin_name, 0) + 1
                    streak = pin_fail_streak[pin_name]
                    this_test_failures.append((pin_name, cpin, apin, expected_state, actual_state, streak))
                    if progress_callback:
                        progress_callback(f"    ✗ {pin_name} (pin {cpin} → Arduino {apin}): "
                                         f"got {actual_state}, expected {expected_state}")
            
            # Keep a per-test record so the UI can show exactly which vector
            # failed instead of only summarizing pass/fail totals.
            test_result = {
                "testId": test_id,
                "description": description,
                "passed": test_passed,
                "expectedOutputs": test['expectedOutputs'],
                "actualOutputs": actual_outputs
            }
            results['testDetails'].append(test_result)

            # Update per-pin diagnostics
            for pin_name, expected_state in test['expectedOutputs'].items():
                actual_state = actual_outputs.get(pin_name)
                diag = results['pinDiagnostics'].get(pin_name)
                if diag is not None:
                    diag['timesTested'] += 1
                    diag['allReadValues'].append(actual_state)
                    if actual_state is None or actual_state == 'ERROR':
                        diag['timesError'] += 1
                        diag['failedTestIds'].append(test_id)
                    elif actual_state == expected_state:
                        diag['timesCorrect'] += 1
                    else:
                        diag['timesWrong'] += 1
                        diag['failedTestIds'].append(test_id)
                        diag['wrongReadings'].append({
                            'testId': test_id,
                            'expected': expected_state,
                            'actual': actual_state
                        })

            if test_passed:
                results['testsPassed'] += 1
                if progress_callback:
                    progress_callback(f"  ✅ PASS")
            else:
                results['testsFailed'] += 1
                results['failedTests'].append(test_result)
                if progress_callback:
                    progress_callback(f"  ❌ FAIL")
                    # Call out pins that have failed multiple tests in a row
                    for pname, cpin, apin, exp, act, streak in this_test_failures:
                        if streak >= 2:
                            progress_callback(
                                f"  ⚠️  {pname} (pin {cpin}) has failed {streak} tests in a row "
                                f"→ CHECK WIRE to Arduino pin {apin}"
                            )
                        if streak >= 3:
                            progress_callback(
                                f"  🔌 {pname} (pin {cpin}) LIKELY UNPLUGGED "
                                f"— always reads {act}, never {exp}"
                            )
        
        results['success'] = results['testsFailed'] == 0

        # Finalize per-pin diagnostics after all vectors have run. This derives a
        # higher-level label such as STUCK HIGH or INTERMITTENT from the raw
        # counters collected above.
        for pin_name, diag in results['pinDiagnostics'].items():
            reads = diag['allReadValues']
            valid_reads = [r for r in reads if r in ('HIGH', 'LOW')]
            if valid_reads:
                unique = set(valid_reads)
                if len(unique) == 1:
                    only_val = unique.pop()
                    if diag['timesWrong'] > 0 or diag['timesError'] > 0:
                        diag['stuckState'] = only_val
                elif diag['timesWrong'] > 0 and diag['timesCorrect'] > 0:
                    diag['stuckState'] = 'INTERMITTENT'
            elif diag['timesError'] == diag['timesTested'] and diag['timesTested'] > 0:
                diag['stuckState'] = 'NO_RESPONSE'

        logger.info(f"Test complete: {results['testsPassed']}/{results['testsRun']} passed")
        return results
    
    # =========================================================================
    # Chip Identification
    # =========================================================================
    
    def identify_chip(self, progress_callback: ProgressCallback = None, board: str = "MEGA") -> Tuple[Optional[str], float, str]:
        """
        Attempt to identify an unknown chip by testing against known patterns.
        
        Tests the chip against all loaded chip definitions and returns
        the best match based on how many tests pass.
        
        Args:
            progress_callback: Optional function for progress updates
        
        Returns:
            Tuple of (chip_id, confidence_percentage, message)
            chip_id is None if no match found
        """
        if progress_callback:
            progress_callback("🔍 Attempting chip identification...")
        
        logger.info("Starting chip identification")
        
        # Identification is intentionally lightweight: we compare only a small
        # subset of patterns across all known chips so the user gets a quick hint
        # rather than waiting for full exhaustive testing of every definition.
        all_chips = self.chip_db.get_all_chip_ids(board=board)
        results = []
        
        for chip_id in all_chips:
            chip_data = self.chip_db.get_chip(chip_id, board=board)
            if not chip_data:
                continue
            
            test_sequence = chip_data.get('testSequence', {})
            tests = test_sequence.get('tests', [])
            if len(tests) < 2:
                continue
            
            mapping = chip_data.get('arduinoMapping', {}).get('io', {})
            pinout = chip_data.get('pinout', {})
            
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
                logger.info(f"Chip identified as {best[0]} with {best[1]:.0f}% confidence")
                return (best[0], best[1], f"Chip identified as {best[0]} with {best[1]:.0f}% confidence")
            elif best[1] >= 50:
                logger.info(f"Possible chip match: {best[0]} with {best[1]:.0f}% confidence")
                return (best[0], best[1], f"Possible match: {best[0]} ({best[1]:.0f}% confidence)")
            else:
                logger.warning("Unable to identify chip - no patterns matched")
                return (None, 0, "Unable to identify chip - no patterns matched")
        
        logger.warning("No chips in database to compare")
        return (None, 0, "No chips in database to compare")
