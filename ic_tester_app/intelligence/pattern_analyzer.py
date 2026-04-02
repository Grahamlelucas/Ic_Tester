# ic_tester_app/intelligence/pattern_analyzer.py
# Last edited: 2026-01-19
# Purpose: Analyze test patterns to detect wiring mistakes and suggest corrections
# Dependencies: None

"""
Failure-pattern analysis module.

This layer turns raw test failures into likely human explanations. It does not
change the hardware result; it interprets it by looking for recognizable
signatures such as stuck pins, all-inverted outputs, missing power, or a likely
wrong chip/orientation.

The analyzer is deliberately heuristic. It is trying to answer "what should the
user check next?" rather than prove a fault mathematically.
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from ..logger import get_logger

logger = get_logger("intelligence.pattern_analyzer")


@dataclass
class WiringMistake:
    """Detected wiring mistake"""
    type: str  # 'swapped_pins', 'missing_power', 'floating_input', etc.
    description: str
    affected_pins: List[int]
    confidence: float  # 0.0 - 1.0
    suggested_fix: str


@dataclass
class ConfidenceScore:
    """Confidence assessment of test results"""
    overall: float  # 0.0 - 1.0
    power_confidence: float
    wiring_confidence: float
    chip_identity_confidence: float
    factors: List[str]  # Reasons affecting confidence


# Common mistake signatures used as a shared vocabulary for the analyzer and UI.
MISTAKE_SIGNATURES = {
    "vcc_gnd_swapped": {
        "description": "VCC and GND appear to be swapped",
        "indicators": ["power_verification_failed", "all_outputs_wrong"],
        "symptoms": "Chip may get hot, all tests fail immediately",
        "fix": "Check that VCC goes to +5V and GND goes to ground"
    },
    "missing_power": {
        "description": "Power pins not connected",
        "indicators": ["power_verification_failed"],
        "symptoms": "No response from chip, outputs floating",
        "fix": "Ensure VCC (usually pin 14) and GND (usually pin 7) are connected"
    },
    "floating_inputs": {
        "description": "Input pins left unconnected",
        "indicators": ["random_failures", "inconsistent_results"],
        "symptoms": "Tests pass/fail randomly, different results each run",
        "fix": "Connect all inputs to either HIGH or LOW, don't leave floating"
    },
    "adjacent_pins_swapped": {
        "description": "Two adjacent pins appear swapped",
        "indicators": ["output_on_wrong_pin", "partial_failures"],
        "symptoms": "Some tests pass but outputs appear on adjacent pins",
        "fix": "Double-check wire placement - may be off by one position"
    },
    "output_shorted_to_ground": {
        "description": "Output pin accidentally connected to ground",
        "indicators": ["output_always_low", "specific_gate_fails"],
        "symptoms": "Specific output always reads LOW regardless of inputs",
        "fix": "Check for accidental short between output and ground"
    },
    "input_output_confused": {
        "description": "Input and output pins confused",
        "indicators": ["driving_input_pin", "reading_output_as_input"],
        "symptoms": "Trying to read from output or drive input",
        "fix": "Review chip pinout - inputs and outputs are not interchangeable"
    },
    "wrong_chip_orientation": {
        "description": "Chip may be inserted backwards",
        "indicators": ["all_tests_fail", "inverse_behavior"],
        "symptoms": "All tests fail, chip may get warm",
        "fix": "Check chip orientation - notch/dot indicates pin 1"
    },
    "wrong_chip_model": {
        "description": "Different chip than expected is inserted",
        "indicators": ["partial_match", "wrong_gate_count"],
        "symptoms": "Some gates work but others behave differently",
        "fix": "Verify chip marking matches selected chip ID"
    }
}

# Pin patterns for different chip families
CHIP_PIN_PATTERNS = {
    "14_pin_quad_gate": {
        "vcc": 14,
        "gnd": 7,
        "gate_groups": [
            {"inputs": [1, 2], "output": 3},
            {"inputs": [4, 5], "output": 6},
            {"inputs": [9, 10], "output": 8},
            {"inputs": [12, 13], "output": 11}
        ],
        "chips": ["7400", "7402", "7408", "7432", "7486"]
    },
    "14_pin_hex_inverter": {
        "vcc": 14,
        "gnd": 7,
        "gate_groups": [
            {"inputs": [1], "output": 2},
            {"inputs": [3], "output": 4},
            {"inputs": [5], "output": 6},
            {"inputs": [9], "output": 8},
            {"inputs": [11], "output": 10},
            {"inputs": [13], "output": 12}
        ],
        "chips": ["7404", "7406", "7414"]
    },
    "14_pin_dual_flip_flop": {
        "vcc": 14,
        "gnd": 7,
        "ff_groups": [
            {"D": 2, "CLK": 3, "SET": 4, "RESET": 1, "Q": 5, "Qbar": 6},
            {"D": 12, "CLK": 11, "SET": 10, "RESET": 13, "Q": 9, "Qbar": 8}
        ],
        "chips": ["7474"]
    },
    "14_pin_counter": {
        "vcc": 14,
        "gnd": 7,
        "has_ripple_outputs": True,
        "chips": ["7490", "7493"]
    }
}


class PatternAnalyzer:
    """
    Analyzes test results to detect patterns and suggest corrections.
    
    Uses algorithmic pattern matching to identify:
    - Common wiring mistakes
    - Likely chip misidentification
    - Connection problems
    """
    
    def __init__(self):
        """Initialize the pattern analyzer"""
        self.mistake_signatures = MISTAKE_SIGNATURES
        self.pin_patterns = CHIP_PIN_PATTERNS
        logger.debug("PatternAnalyzer initialized")
    
    def analyze_failure(self, chip_id: str, results: Dict[str, Any],
                       pin_mapping: Dict[str, int] = None) -> List[WiringMistake]:
        """
        Analyze a test failure to identify likely causes.
        
        Args:
            chip_id: ID of the chip tested
            results: Test results dictionary
            pin_mapping: Pin mapping used for test
        
        Returns:
            List of possible wiring mistakes, sorted by confidence
        """
        mistakes = []
        # Combine several narrower heuristics into one ranked list. Each helper
        # contributes a different perspective on the same failed result.
        
        # Check pin verification
        if not results.get('pinsVerified', True):
            mistakes.extend(self._analyze_pin_failure(chip_id, results, pin_mapping))
        
        # Check test failures
        if results.get('testsFailed', 0) > 0:
            mistakes.extend(self._analyze_test_failures(chip_id, results, pin_mapping))
        
        # Sort by confidence (highest first)
        mistakes.sort(key=lambda m: m.confidence, reverse=True)
        
        return mistakes
    
    def _analyze_power_failure(self, chip_id: str, 
                               results: Dict[str, Any]) -> List[WiringMistake]:
        """Analyze power-related failures"""
        mistakes = []
        
        # Most likely: power not connected
        mistakes.append(WiringMistake(
            type="missing_power",
            description=MISTAKE_SIGNATURES["missing_power"]["description"],
            affected_pins=self._get_power_pins(chip_id),
            confidence=0.85,
            suggested_fix=MISTAKE_SIGNATURES["missing_power"]["fix"]
        ))
        
        # Possible: VCC/GND swapped
        mistakes.append(WiringMistake(
            type="vcc_gnd_swapped",
            description=MISTAKE_SIGNATURES["vcc_gnd_swapped"]["description"],
            affected_pins=self._get_power_pins(chip_id),
            confidence=0.5,
            suggested_fix=MISTAKE_SIGNATURES["vcc_gnd_swapped"]["fix"]
        ))
        
        return mistakes
    
    def _analyze_pin_failure(self, chip_id: str, results: Dict[str, Any],
                            pin_mapping: Dict[str, int]) -> List[WiringMistake]:
        """Analyze pin connection failures"""
        mistakes = []
        problem_pins = results.get('problemPins', [])
        
        if problem_pins:
            affected = [p['chip_pin'] for p in problem_pins]
            
            # Adjacent failures are a strong clue for off-by-one placement on a
            # breadboard or header row.
            for i, pin in enumerate(affected):
                if pin + 1 in affected or pin - 1 in affected:
                    mistakes.append(WiringMistake(
                        type="adjacent_pins_swapped",
                        description=MISTAKE_SIGNATURES["adjacent_pins_swapped"]["description"],
                        affected_pins=affected,
                        confidence=0.7,
                        suggested_fix=MISTAKE_SIGNATURES["adjacent_pins_swapped"]["fix"]
                    ))
                    break
            
            # General connection issue
            mistakes.append(WiringMistake(
                type="loose_connection",
                description="One or more wires may be loose or disconnected",
                affected_pins=affected,
                confidence=0.6,
                suggested_fix="Check that all jumper wires are firmly seated in both the chip socket and Arduino"
            ))
        
        return mistakes
    
    def _analyze_test_failures(self, chip_id: str, results: Dict[str, Any],
                              pin_mapping: Dict[str, int]) -> List[WiringMistake]:
        """Analyze functional test failures using testDetails and pinDiagnostics"""
        mistakes = []
        failed_tests = results.get('failedTests', results.get('testDetails', []))
        # Filter to only actually-failed tests if using testDetails
        if failed_tests and 'passed' in (failed_tests[0] if failed_tests else {}):
            failed_tests = [t for t in failed_tests if not t.get('passed', True)]
        tests_run = results.get('testsRun', 0)
        tests_failed = results.get('testsFailed', 0)
        pin_diag = results.get('pinDiagnostics', {})

        # Pin diagnostics already capture repeat-read behavior, so start there
        # before falling back to broader whole-test heuristics.
        stuck_pins = self._analyze_stuck_pins(pin_diag)
        mistakes.extend(stuck_pins)

        # -- Inverted-output detection --
        inverted = self._detect_inverted_outputs(pin_diag)
        if inverted:
            mistakes.extend(inverted)

        # If every vector failed, broad setup mistakes become more likely than a
        # single bad output wire.
        if tests_run > 0 and tests_failed == tests_run:
            mistakes.append(WiringMistake(
                type="wrong_chip_orientation",
                description=MISTAKE_SIGNATURES["wrong_chip_orientation"]["description"],
                affected_pins=[],
                confidence=0.6,
                suggested_fix=MISTAKE_SIGNATURES["wrong_chip_orientation"]["fix"]
            ))
            
            mistakes.append(WiringMistake(
                type="wrong_chip_model",
                description=MISTAKE_SIGNATURES["wrong_chip_model"]["description"],
                affected_pins=[],
                confidence=0.5,
                suggested_fix=MISTAKE_SIGNATURES["wrong_chip_model"]["fix"]
            ))
        
        # Partial failures usually point to a subset of outputs or an incomplete
        # mapping problem rather than total power/orientation failure.
        elif tests_failed > 0 and tests_failed < tests_run:
            # Identify failing output pins from testDetails
            output_failures = self._identify_failing_outputs(failed_tests, chip_id)
            
            if output_failures:
                for pin_name, chip_pin in output_failures:
                    mistakes.append(WiringMistake(
                        type="output_connection_issue",
                        description=f"Output {pin_name} (chip pin {chip_pin}) not responding correctly",
                        affected_pins=[chip_pin] if isinstance(chip_pin, int) else [],
                        confidence=0.7,
                        suggested_fix=f"Check the wire connected to {pin_name} (chip pin {chip_pin})"
                    ))
            
            # Check for floating inputs
            if self._suggests_floating_inputs(failed_tests):
                mistakes.append(WiringMistake(
                    type="floating_inputs",
                    description=MISTAKE_SIGNATURES["floating_inputs"]["description"],
                    affected_pins=[],
                    confidence=0.6,
                    suggested_fix=MISTAKE_SIGNATURES["floating_inputs"]["fix"]
                ))
        
        return mistakes

    def _analyze_stuck_pins(self, pin_diag: Dict[str, Any]) -> List[WiringMistake]:
        """Detect pins that are stuck HIGH, stuck LOW, or not responding"""
        mistakes = []
        for pin_name, diag in pin_diag.items():
            stuck = diag.get('stuckState')
            chip_pin = diag.get('chipPin', '?')
            arduino_pin = diag.get('arduinoPin', '?')
            if stuck == 'HIGH':
                mistakes.append(WiringMistake(
                    type="stuck_high",
                    description=f"{pin_name} (chip pin {chip_pin}) stuck HIGH in all readings",
                    affected_pins=[chip_pin] if isinstance(chip_pin, int) else [],
                    confidence=0.85,
                    suggested_fix=f"{pin_name} always reads HIGH — check if Arduino pin {arduino_pin} is shorted to 5V or if the output wire is loose"
                ))
            elif stuck == 'LOW':
                mistakes.append(WiringMistake(
                    type="stuck_low",
                    description=f"{pin_name} (chip pin {chip_pin}) stuck LOW in all readings",
                    affected_pins=[chip_pin] if isinstance(chip_pin, int) else [],
                    confidence=0.85,
                    suggested_fix=f"{pin_name} always reads LOW — check if Arduino pin {arduino_pin} is shorted to GND or wire is disconnected"
                ))
            elif stuck == 'NO_RESPONSE':
                mistakes.append(WiringMistake(
                    type="no_response",
                    description=f"{pin_name} (chip pin {chip_pin}) returned ERROR on every read",
                    affected_pins=[chip_pin] if isinstance(chip_pin, int) else [],
                    confidence=0.9,
                    suggested_fix=f"{pin_name} is not responding — verify wire between chip pin {chip_pin} and Arduino pin {arduino_pin}"
                ))
            elif stuck == 'INTERMITTENT':
                mistakes.append(WiringMistake(
                    type="intermittent",
                    description=f"{pin_name} (chip pin {chip_pin}) gives inconsistent readings",
                    affected_pins=[chip_pin] if isinstance(chip_pin, int) else [],
                    confidence=0.7,
                    suggested_fix=f"{pin_name} reads are unreliable — check for loose wire at Arduino pin {arduino_pin} or breadboard contact"
                ))
        return mistakes

    def _detect_inverted_outputs(self, pin_diag: Dict[str, Any]) -> List[WiringMistake]:
        """Detect if all outputs are inverted (suggests chip backwards or wrong chip)"""
        if not pin_diag:
            return []
        total_pins = 0
        inverted_pins = 0
        for pin_name, diag in pin_diag.items():
            wrongs = diag.get('wrongReadings', [])
            if not wrongs:
                continue
            total_pins += 1
            # Look for the special case where every bad reading is exactly the
            # opposite of expected rather than simply noisy or missing.
            all_inverted = all(
                (w['expected'] == 'HIGH' and w['actual'] == 'LOW') or
                (w['expected'] == 'LOW' and w['actual'] == 'HIGH')
                for w in wrongs
            )
            if all_inverted:
                inverted_pins += 1
        
        if total_pins > 0 and inverted_pins == total_pins:
            return [WiringMistake(
                type="all_outputs_inverted",
                description="All outputs are inverted — every expected HIGH reads LOW and vice versa",
                affected_pins=[],
                confidence=0.8,
                suggested_fix="Chip may be inserted backwards (rotated 180°), or a different chip with inverted logic is inserted"
            )]
        return []
    
    def _get_power_pins(self, chip_id: str) -> List[int]:
        """Get power pin numbers for a chip"""
        # Most 14-pin TTL chips use pin 14 for VCC, pin 7 for GND
        for pattern_name, pattern in self.pin_patterns.items():
            if chip_id in pattern.get('chips', []):
                return [pattern['vcc'], pattern['gnd']]
        return [14, 7]  # Default for 14-pin DIPs
    
    def _identify_failing_outputs(self, failed_tests: List[Dict],
                                  chip_id: str) -> List[Tuple[str, Any]]:
        """Identify which output pins are failing.
        Returns list of (pin_name, chip_pin) tuples."""
        failing_outputs = {}
        
        for test in failed_tests:
            expected = test.get('expectedOutputs', test.get('expected', {}))
            actual = test.get('actualOutputs', test.get('actual', {}))
            
            for pin_name, exp_val in expected.items():
                if actual.get(pin_name) != exp_val:
                    if pin_name not in failing_outputs:
                        failing_outputs[pin_name] = pin_name
        
        return [(name, name) for name in failing_outputs.keys()]
    
    def _suggests_floating_inputs(self, failed_tests: List[Dict]) -> bool:
        """Check if failure pattern suggests floating inputs"""
        # Floating inputs often cause inconsistent results
        # This is a heuristic - real detection would need multiple runs
        if len(failed_tests) < 2:
            return False
        
        # Check for alternating pass/fail on same test (would need history)
        # For now, just flag if many tests fail with unexpected patterns
        return len(failed_tests) > 3
    
    def calculate_confidence(self, chip_id: str, results: Dict[str, Any],
                            historical_success_rate: float = None) -> ConfidenceScore:
        """
        Calculate confidence score for test results.
        
        Args:
            chip_id: ID of the chip tested
            results: Test results dictionary
            historical_success_rate: User's past success rate with this chip
        
        Returns:
            ConfidenceScore with detailed breakdown
        """
        factors = []
        
        # Confidence is not just "how many tests passed". We separately score the
        # trustworthiness of wiring, functional behavior, and chip identity.
        # Wiring confidence
        wiring_conf = 1.0 if results.get('pinsVerified', False) else 0.3
        if wiring_conf < 1.0:
            factors.append("Pin verification failed - check connections")
        
        # Test result confidence
        tests_run = results.get('testsRun', 0)
        tests_passed = results.get('testsPassed', 0)
        
        if tests_run == 0:
            test_conf = 0.0
            factors.append("No tests were run")
        else:
            test_conf = tests_passed / tests_run
            
            if test_conf == 1.0:
                factors.append("All tests passed - high confidence")
            elif test_conf > 0.8:
                factors.append("Most tests passed - likely minor wiring issue")
            elif test_conf > 0.5:
                factors.append("Mixed results - possible partial connection issues")
            else:
                factors.append("Many tests failed - verify chip and connections")
        
        # Chip identity confidence
        # If all tests fail, might be wrong chip
        if test_conf == 0 and tests_run > 0:
            identity_conf = 0.5
            factors.append("Complete failure may indicate wrong chip inserted")
        elif test_conf < 0.3 and tests_run > 5:
            identity_conf = 0.6
            factors.append("Low success rate - verify chip marking")
        else:
            identity_conf = 0.9
        
        # Historical success matters because a sudden failure on a chip the user
        # normally wires correctly often means a one-off setup mistake.
        if historical_success_rate is not None:
            if historical_success_rate > 0.8 and test_conf < 0.5:
                factors.append("Unusual failure for a chip you usually pass")
                identity_conf *= 0.8  # More likely wrong chip or wiring
        
        # Weighted blend: wiring and actual test vectors matter most, while chip
        # identity confidence is informative but slightly less direct.
        overall = (wiring_conf * 0.4 + 
                  test_conf * 0.4 + identity_conf * 0.2)
        
        return ConfidenceScore(
            overall=overall,
            power_confidence=1.0,
            wiring_confidence=wiring_conf,
            chip_identity_confidence=identity_conf,
            factors=factors
        )
    
    def suggest_chip_from_behavior(self, observed_behavior: Dict[str, Any],
                                   candidate_chips: List[str]) -> List[Tuple[str, float]]:
        """
        Suggest which chip might be inserted based on observed behavior.
        
        Args:
            observed_behavior: Dict with observed inputs/outputs
            candidate_chips: List of chips to consider
        
        Returns:
            List of (chip_id, confidence) tuples sorted by confidence
        """
        suggestions = []
        
        # This would require running quick tests against multiple chip
        # truth tables - for now return empty
        # Full implementation would test observed I/O against known patterns
        
        return suggestions
    
    def get_fix_priority(self, mistakes: List[WiringMistake]) -> List[str]:
        """
        Get prioritized list of fixes to try.
        
        Args:
            mistakes: List of detected wiring mistakes
        
        Returns:
            Ordered list of suggested fixes to try
        """
        if not mistakes:
            return ["Re-run the test to confirm results"]
        
        # Deduplicate and sort by confidence
        seen_fixes = set()
        prioritized = []
        
        for mistake in mistakes:
            if mistake.suggested_fix not in seen_fixes:
                seen_fixes.add(mistake.suggested_fix)
                prioritized.append(mistake.suggested_fix)
        
        return prioritized
