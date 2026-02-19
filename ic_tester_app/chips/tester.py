# ic_tester_app/chips/tester.py
# Last edited: 2026-01-19
# Purpose: IC testing logic - runs test sequences and verifies chip functionality
# Dependencies: time

"""
IC Tester module.
Contains the core testing logic for 74-series integrated circuits.

This module handles:
- Power verification
- Pin connection verification  
- Running test sequences
- Chip identification
- Result collection and reporting
"""

import time
from typing import Optional, Dict, List, Tuple, Any, Callable

from ..logger import get_logger

logger = get_logger("chips.tester")

# Type alias for progress callback function
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
    # Power Verification
    # =========================================================================
    
    def verify_power(self, chip_data: Dict, progress_callback: ProgressCallback = None, 
                     external_power: bool = False) -> Tuple[bool, str]:
        """
        Verify that power (VCC/GND) is properly configured for the chip.
        
        This check ensures:
        1. Chip definition has VCC and GND pins defined
        2. Power mapping exists in chip definition (unless external_power=True)
        3. Arduino is responding to commands
        
        Args:
            chip_data: Chip definition dictionary
            progress_callback: Optional function for progress updates
            external_power: If True, skip Arduino power mapping check (using external supply)
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        pinout = chip_data.get('pinout', {})
        mapping = chip_data.get('arduinoMapping', {})
        
        # Check if power pins are defined in chip data
        vcc_pin = pinout.get('vcc')
        gnd_pin = pinout.get('gnd')
        
        if not vcc_pin or not gnd_pin:
            logger.warning("Chip definition missing VCC or GND pin configuration")
            return (False, "Chip definition missing VCC or GND pin configuration")
        
        # External power mode - skip Arduino power mapping check
        if external_power:
            if progress_callback:
                progress_callback(f"🔋 External power mode: VCC=pin {vcc_pin}, GND=pin {gnd_pin}")
                progress_callback("   (Power supplied by external breadboard module)")
        else:
            # Check if power mapping exists
            power_mapping = mapping.get('power', {})
            if not power_mapping:
                logger.warning("Chip definition missing power pin mapping")
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
        
        # Clear any stale data in serial buffer before PING
        self.arduino.clear_buffer()
        import time
        time.sleep(0.1)  # Brief pause after clearing
        
        # Send a test command to verify Arduino is responding (with retries)
        max_retries = 3
        for attempt in range(max_retries):
            response = self.arduino.send_and_receive("PING", timeout=2.0)
            if response and "PONG" in response:
                break
            logger.debug(f"PING attempt {attempt + 1}/{max_retries} failed, response: {response}")
            time.sleep(0.2)  # Brief pause between retries
        else:
            # All retries failed
            logger.error(f"Arduino not responding to PING after {max_retries} attempts")
            return (False, "Arduino not responding - check USB connection")
        
        if progress_callback:
            progress_callback("✅ Arduino responding to commands")
        
        logger.info("Power verification passed" + (" (external power)" if external_power else ""))
        return (True, "Power configuration verified")
    
    # =========================================================================
    # Pin Connection Verification
    # =========================================================================
    
    def verify_pin_connections(self, chip_data: Dict, progress_callback: ProgressCallback = None) -> Tuple[bool, str, List]:
        """
        Verify all pin connections by running initial test patterns.
        
        Uses the first 2 tests from the chip's test sequence to verify
        that the chip is responding correctly. Uses 3x voting for reliability.
        
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
        
        # Build lookups for pin names and types
        input_pins = {p['name']: p['pin'] for p in pinout.get('inputs', [])}
        output_pins = {p['name']: p['pin'] for p in pinout.get('outputs', [])}
        
        # Helper functions
        def set_pin(arduino_pin: int, state: str) -> bool:
            """Set a pin with verification"""
            for attempt in range(3):
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
        
        # Check: Did any outputs change between states?
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
        
        # Verify all output pins
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
                 external_power: bool = False,
                 board: str = "MEGA") -> Dict[str, Any]:
        """
        Run complete test sequence for a chip.
        
        This is the main testing method that:
        1. Verifies power configuration
        2. Verifies pin connections
        3. Runs all tests from the chip's test sequence
        4. Collects and returns results
        
        Args:
            chip_id: ID of the chip to test (e.g., '7490', '7414')
            progress_callback: Optional function for progress updates
            custom_mapping: Optional user-defined Arduino pin mapping
                           {chip_pin_str: arduino_pin_int}
                           Overrides the JSON-defined arduinoMapping if provided
            external_power: If True, skip Arduino power check (using external supply)
            board: Board profile to use when resolving chip data
        
        Returns:
            Dictionary with test results:
            {
                'chipId': str,
                'chipName': str,
                'testsRun': int,
                'testsPassed': int,
                'testsFailed': int,
                'testDetails': list,
                'success': bool,
                'powerVerified': bool,
                'pinsVerified': bool,
                'error': str (if failed)
            }
        """
        logger.info(f"Starting test for chip {chip_id}")
        
        # Reset abort flag at start of test
        self._abort_flag = False
        
        chip_data = self.chip_db.get_chip(chip_id, board=board)
        if not chip_data:
            logger.error(f"Chip {chip_id} not found in database")
            return {"success": False, "error": f"Chip {chip_id} not found"}
        
        # Use custom mapping if provided
        if custom_mapping:
            chip_data = chip_data.copy()
            existing = chip_data.get("arduinoMapping", {})
            chip_data['arduinoMapping'] = {
                'io': custom_mapping,
                'power': existing.get("power", {}),
            }
            if progress_callback:
                progress_callback(f"📌 Using user-defined pin mapping ({len(custom_mapping)} pins)")
            logger.info(f"Using custom pin mapping with {len(custom_mapping)} pins")
        
        # Initialize results
        results = {
            "chipId": chip_id,
            "chipName": chip_data['name'],
            "board": str(board).upper(),
            "testsRun": 0,
            "testsPassed": 0,
            "testsFailed": 0,
            "testDetails": [],
            "success": False,
            "powerVerified": False,
            "pinsVerified": False
        }
        
        # Step 1: Verify power
        if progress_callback:
            if external_power:
                progress_callback("🔋 Using external power supply...")
            else:
                progress_callback("🔌 Verifying power configuration...")
        
        power_ok, power_msg = self.verify_power(chip_data, progress_callback, external_power)
        results["powerVerified"] = power_ok
        
        if not power_ok:
            if progress_callback:
                progress_callback(f"❌ Power check failed: {power_msg}")
            results["error"] = f"Power verification failed: {power_msg}"
            return results
        
        if progress_callback:
            progress_callback("✅ Power check passed")
        
        # Step 2: Verify pin connections
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
        
        # Step 5: Run all tests
        tests = chip_data['testSequence']['tests']
        all_input_pins = [p['name'] for p in chip_data.get('pinout', {}).get('inputs', [])]
        
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
            
            # Reset all inputs to LOW before each test
            for pin_name in all_input_pins:
                if self._abort_flag:
                    break
                self.set_pin_state(chip_data, pin_name, 'LOW')
            if self._abort_flag:
                continue
            time.sleep(0.05)
            
            # Set test-specific inputs
            if progress_callback:
                progress_callback(f"    Setting test inputs: {test['inputs']}")
            for pin_name, state in test['inputs'].items():
                if self._abort_flag:
                    break
                success = self.set_pin_state(chip_data, pin_name, state)
                if not success and progress_callback:
                    progress_callback(f"    ⚠️ Failed to set {pin_name} {state}")
            if self._abort_flag:
                continue
            
            time.sleep(0.1)  # Allow chip to settle
            
            # Read and verify outputs
            test_passed = True
            actual_outputs = {}
            
            for pin_name, expected_state in test['expectedOutputs'].items():
                if self._abort_flag:
                    break
                actual_state = self.read_pin_state(chip_data, pin_name)
                actual_outputs[pin_name] = actual_state
                
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
