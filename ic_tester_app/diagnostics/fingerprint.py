# ic_tester_app/diagnostics/fingerprint.py
# Last edited: 2026-03-19
# Purpose: IC behavior fingerprinting - identify unknown chips by observed logic patterns
# Dependencies: time, itertools, typing, dataclasses
# Related: chips/database.py, diagnostics/signal_analyzer.py

"""
IC Behavior Fingerprinting module.

Identifies unknown ICs by:
1. Running exploratory input combinations on mapped pins
2. Building a derived truth table from observed outputs
3. Comparing observed behavior against a library of known IC logic patterns
4. Estimating the most likely IC family/function

Works independently of predefined chip profiles when the IC type is unknown.
"""

import time
import itertools
from typing import Optional, Dict, List, Any, Callable, Tuple
from dataclasses import dataclass, field

from ..logger import get_logger

logger = get_logger("diagnostics.fingerprint")

ProgressCallback = Optional[Callable[[str], None]]


# Known logic function signatures for common 74-series gate ICs.
# Each entry maps a gate type to its truth table (inputs → output).
KNOWN_GATE_SIGNATURES = {
    "AND": {(0, 0): 0, (0, 1): 0, (1, 0): 0, (1, 1): 1},
    "OR":  {(0, 0): 0, (0, 1): 1, (1, 0): 1, (1, 1): 1},
    "NAND": {(0, 0): 1, (0, 1): 1, (1, 0): 1, (1, 1): 0},
    "NOR": {(0, 0): 1, (0, 1): 0, (1, 0): 0, (1, 1): 0},
    "XOR": {(0, 0): 0, (0, 1): 1, (1, 0): 1, (1, 1): 0},
    "XNOR": {(0, 0): 1, (0, 1): 0, (1, 0): 0, (1, 1): 1},
    "NOT": {(0,): 1, (1,): 0},
    "BUFFER": {(0,): 0, (1,): 1},
}

# Chip ID → (gate_type, num_gates, pin_count)
KNOWN_CHIP_FUNCTIONS = {
    "7400": ("NAND", 4, 14),
    "7402": ("NOR", 4, 14),
    "7404": ("NOT", 6, 14),
    "7408": ("AND", 4, 14),
    "7432": ("OR", 4, 14),
    "7486": ("XOR", 4, 14),
    "7414": ("NOT", 6, 14),
    "74LS00": ("NAND", 4, 14),
    "SN74LS00N": ("NAND", 4, 14),
    "74LS04": ("NOT", 6, 14),
    "74LS04N": ("NOT", 6, 14),
    "74LS08": ("AND", 4, 14),
    "74LS32": ("OR", 4, 14),
    "74LS86": ("XOR", 4, 14),
}


@dataclass
class TruthTableEntry:
    """Single row of an observed truth table."""
    inputs: Tuple
    expected_outputs: Tuple = ()
    observed_outputs: Tuple = ()
    match: bool = False


@dataclass
class GateFingerprint:
    """Fingerprint of a single gate within the IC."""
    gate_index: int
    input_pin_names: List[str]
    output_pin_name: str
    truth_table: List[TruthTableEntry] = field(default_factory=list)
    matched_function: str = ""
    match_confidence: float = 0.0


@dataclass
class ChipFingerprint:
    """Complete behavioral fingerprint of an IC."""
    chip_id_tested: str
    gate_fingerprints: List[GateFingerprint] = field(default_factory=list)
    derived_truth_table: List[Dict] = field(default_factory=list)
    best_match_chip: str = ""
    best_match_function: str = ""
    best_match_confidence: float = 0.0
    candidate_matches: List[Tuple[str, str, float]] = field(default_factory=list)
    num_inputs_tested: int = 0
    num_outputs_observed: int = 0
    timestamp: str = ""


class ICFingerprinter:
    """
    Identifies unknown ICs by probing input/output behavior.

    Runs exploratory input combinations, builds observed truth tables,
    and matches behavior against known IC logic patterns.

    Attributes:
        arduino: ArduinoConnection instance
        chip_db: ChipDatabase instance (optional, for cross-referencing)
    """

    def __init__(self, arduino_conn, chip_db=None):
        """
        Args:
            arduino_conn: ArduinoConnection instance
            chip_db: Optional ChipDatabase for cross-referencing known chips
        """
        self.arduino = arduino_conn
        self.chip_db = chip_db
        logger.info("ICFingerprinter initialized")

    def fingerprint_chip(
        self,
        chip_data: Dict,
        progress_callback: ProgressCallback = None,
        max_input_combos: int = 16,
    ) -> ChipFingerprint:
        """
        Build a behavioral fingerprint of the chip by probing all input combinations.

        Args:
            chip_data: Chip definition dict (needs arduinoMapping and pinout at minimum)
            progress_callback: Optional progress callback
            max_input_combos: Maximum number of input combinations to test

        Returns:
            ChipFingerprint with observed truth tables and best match
        """
        chip_id = chip_data.get("chipId", "Unknown")
        mapping = chip_data.get("arduinoMapping", {}).get("io", {})
        pinout = chip_data.get("pinout", {})

        input_pins = pinout.get("inputs", [])
        output_pins = pinout.get("outputs", [])

        fp = ChipFingerprint(
            chip_id_tested=chip_id,
            num_inputs_tested=len(input_pins),
            num_outputs_observed=len(output_pins),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        if progress_callback:
            progress_callback(f"\n{'═' * 50}")
            progress_callback(f"🔬 IC FINGERPRINTING: {chip_id}")
            progress_callback(f"{'═' * 50}")
            progress_callback(
                f"  Inputs: {len(input_pins)}, Outputs: {len(output_pins)}"
            )

        if not input_pins or not output_pins:
            if progress_callback:
                progress_callback("  ❌ Need at least 1 input and 1 output pin mapped")
            return fp

        # Build list of Arduino pins for inputs and outputs
        input_info = []
        for ip in input_pins:
            ard = mapping.get(str(ip["pin"]))
            if ard is not None:
                input_info.append((ip["name"], ip["pin"], ard))

        output_info = []
        for op in output_pins:
            ard = mapping.get(str(op["pin"]))
            if ard is not None:
                output_info.append((op["name"], op["pin"], ard))

        if not input_info or not output_info:
            if progress_callback:
                progress_callback("  ❌ No valid pin mappings for fingerprinting")
            return fp

        # Generate input combinations (limit to max_input_combos)
        num_inputs = len(input_info)
        all_combos = list(itertools.product([0, 1], repeat=num_inputs))
        if len(all_combos) > max_input_combos:
            all_combos = all_combos[:max_input_combos]

        if progress_callback:
            progress_callback(
                f"  Testing {len(all_combos)} input combinations..."
            )

        # Run exploratory tests
        truth_table = []
        for combo_idx, combo in enumerate(all_combos):
            # Set all inputs according to this combination
            for i, (name, cpin, apin) in enumerate(input_info):
                state = "HIGH" if combo[i] == 1 else "LOW"
                self.arduino.send_command(f"SET_PIN,{apin},{state}")
                self.arduino.read_response(timeout=0.15)

            time.sleep(0.05)

            # Read all outputs
            observed = []
            for name, cpin, apin in output_info:
                self.arduino.send_command(f"READ_PIN,{apin}")
                resp = self.arduino.read_response(timeout=0.15)
                if resp and "HIGH" in resp:
                    observed.append(1)
                else:
                    observed.append(0)

            row = {
                "inputs": {input_info[i][0]: combo[i] for i in range(num_inputs)},
                "outputs": {output_info[j][0]: observed[j] for j in range(len(output_info))},
                "input_tuple": combo,
                "output_tuple": tuple(observed),
            }
            truth_table.append(row)
            fp.derived_truth_table.append(row)

            if progress_callback:
                in_str = "".join(str(b) for b in combo)
                out_str = "".join(str(b) for b in observed)
                progress_callback(f"    [{in_str}] → [{out_str}]")

        # Try to identify gate functions per output
        fp.gate_fingerprints = self._identify_gates(
            input_info, output_info, truth_table
        )

        # Match against known chips
        fp.candidate_matches = self._match_known_chips(fp.gate_fingerprints)
        if fp.candidate_matches:
            best = fp.candidate_matches[0]
            fp.best_match_chip = best[0]
            fp.best_match_function = best[1]
            fp.best_match_confidence = best[2]

        if progress_callback:
            progress_callback(f"\n  Gate Analysis:")
            for gf in fp.gate_fingerprints:
                conf_str = f"{gf.match_confidence:.0%}" if gf.matched_function else "unknown"
                progress_callback(
                    f"    Gate {gf.gate_index}: "
                    f"{' + '.join(gf.input_pin_names)} → {gf.output_pin_name}: "
                    f"{gf.matched_function or '?'} ({conf_str})"
                )

            if fp.candidate_matches:
                progress_callback(f"\n  🏆 Best Match:")
                for cid, func, conf in fp.candidate_matches[:3]:
                    icon = "✓" if conf >= 0.8 else "?" if conf >= 0.5 else "✗"
                    progress_callback(f"    {icon} {cid} ({func}): {conf:.0%}")
            else:
                progress_callback(f"\n  ❌ No known chip pattern matched")

            progress_callback(f"{'═' * 50}")

        # Reset all inputs to LOW
        for name, cpin, apin in input_info:
            self.arduino.send_command(f"SET_PIN,{apin},LOW")
            self.arduino.read_response(timeout=0.1)

        logger.info(
            f"Fingerprinting complete: best match={fp.best_match_chip} "
            f"({fp.best_match_confidence:.0%})"
        )
        return fp

    def _identify_gates(
        self,
        input_info: List[Tuple],
        output_info: List[Tuple],
        truth_table: List[Dict],
    ) -> List[GateFingerprint]:
        """
        Attempt to identify the logic function of each output by comparing
        its observed truth table against known gate signatures.
        """
        gate_fps = []

        for out_idx, (out_name, out_cpin, out_apin) in enumerate(output_info):
            gf = GateFingerprint(
                gate_index=out_idx + 1,
                input_pin_names=[ip[0] for ip in input_info],
                output_pin_name=out_name,
            )

            # Extract observed output column for this pin
            observed_map = {}
            for row in truth_table:
                in_tuple = row["input_tuple"]
                out_val = row["outputs"].get(out_name, 0)
                observed_map[in_tuple] = out_val

            # Try to match against 2-input gates (most common)
            # For chips with many inputs, try all pairs of inputs
            best_func = ""
            best_conf = 0.0

            if len(input_info) == 1:
                # Single-input: try NOT, BUFFER
                sub_map = {(row["input_tuple"][0],): observed_map[row["input_tuple"]]
                           for row in truth_table}
                for func_name, sig in KNOWN_GATE_SIGNATURES.items():
                    if all(len(k) == 1 for k in sig.keys()):
                        matches = sum(
                            1 for k, v in sig.items()
                            if k in sub_map and sub_map[k] == v
                        )
                        total = len(sig)
                        if total > 0:
                            conf = matches / total
                            if conf > best_conf:
                                best_conf = conf
                                best_func = func_name
            else:
                # Multi-input: try each pair against 2-input gate signatures
                for i in range(len(input_info)):
                    for j in range(i + 1, len(input_info)):
                        sub_map = {}
                        for row in truth_table:
                            key = (row["input_tuple"][i], row["input_tuple"][j])
                            sub_map[key] = observed_map[row["input_tuple"]]

                        for func_name, sig in KNOWN_GATE_SIGNATURES.items():
                            if all(len(k) == 2 for k in sig.keys()):
                                matches = sum(
                                    1 for k, v in sig.items()
                                    if k in sub_map and sub_map[k] == v
                                )
                                total = len(sig)
                                if total > 0:
                                    conf = matches / total
                                    if conf > best_conf:
                                        best_conf = conf
                                        best_func = func_name
                                        gf.input_pin_names = [
                                            input_info[i][0],
                                            input_info[j][0],
                                        ]

            gf.matched_function = best_func
            gf.match_confidence = best_conf

            # Build truth table entries
            for row in truth_table:
                gf.truth_table.append(TruthTableEntry(
                    inputs=row["input_tuple"],
                    observed_outputs=(observed_map[row["input_tuple"]],),
                ))

            gate_fps.append(gf)

        return gate_fps

    def _match_known_chips(
        self, gate_fingerprints: List[GateFingerprint]
    ) -> List[Tuple[str, str, float]]:
        """
        Match detected gate functions against known chip database.

        Returns list of (chip_id, function, confidence) sorted by confidence.
        """
        if not gate_fingerprints:
            return []

        # Count detected gate functions
        func_counts = {}
        total_conf = 0.0
        for gf in gate_fingerprints:
            if gf.matched_function:
                func_counts[gf.matched_function] = (
                    func_counts.get(gf.matched_function, 0) + 1
                )
                total_conf += gf.match_confidence

        if not func_counts:
            return []

        # Dominant function
        dominant_func = max(func_counts, key=func_counts.get)
        avg_conf = total_conf / len(gate_fingerprints)

        # Match against known chips
        candidates = []
        for chip_id, (func, num_gates, pins) in KNOWN_CHIP_FUNCTIONS.items():
            if func == dominant_func:
                # Boost confidence if gate count matches
                gate_match = func_counts.get(dominant_func, 0)
                count_bonus = 0.1 if gate_match == num_gates else 0.0
                conf = min(1.0, avg_conf + count_bonus)
                candidates.append((chip_id, func, conf))

        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates
