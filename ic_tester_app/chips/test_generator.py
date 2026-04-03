# ic_tester_app/chips/test_generator.py
# Last edited: 2026-03-19
# Purpose: Automatic truth table generation and modular test definition builder
# Dependencies: itertools, json, typing, pathlib
# Related: chips/database.py, chips/tester.py, diagnostics/fingerprint.py

"""
Automatic test-definition generator.

This module is about authoring chip definitions rather than executing them. It
can synthesize test vectors from known logic templates, build simple sequential
counter sequences, and convert observed fingerprint data back into a reusable
test suite.
"""

import json
import itertools
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field

from ..logger import get_logger
from ..config import Config

logger = get_logger("chips.test_generator")


@dataclass
class TestVector:
    """A single test vector: input values and expected output values."""
    test_id: str
    inputs: Dict[str, int]
    expected_outputs: Dict[str, int]
    description: str = ""
    is_sequential: bool = False
    clock_edges: int = 0


@dataclass
class GeneratedTestSuite:
    """Collection of generated test vectors for a chip."""
    chip_id: str
    vectors: List[TestVector] = field(default_factory=list)
    logic_type: str = "combinational"
    gate_function: str = ""
    num_gates: int = 0
    notes: str = ""


# Built-in templates describe the structural information needed to generate a
# first-pass JSON definition for common chip layouts.
CHIP_TEMPLATES = {
    # Quad 2-input gates (14-pin DIP)
    "NAND_QUAD": {
        "function": "NAND",
        "logic_type": "combinational",
        "gates": [
            {"inputs": ["1A", "1B"], "output": "1Y", "in_pins": [1, 2], "out_pin": 3},
            {"inputs": ["2A", "2B"], "output": "2Y", "in_pins": [4, 5], "out_pin": 6},
            {"inputs": ["3A", "3B"], "output": "3Y", "in_pins": [9, 10], "out_pin": 8},
            {"inputs": ["4A", "4B"], "output": "4Y", "in_pins": [12, 13], "out_pin": 11},
        ],
        "vcc": 14, "gnd": 7, "package": "14-pin DIP",
    },
    "AND_QUAD": {
        "function": "AND",
        "logic_type": "combinational",
        "gates": [
            {"inputs": ["1A", "1B"], "output": "1Y", "in_pins": [1, 2], "out_pin": 3},
            {"inputs": ["2A", "2B"], "output": "2Y", "in_pins": [4, 5], "out_pin": 6},
            {"inputs": ["3A", "3B"], "output": "3Y", "in_pins": [9, 10], "out_pin": 8},
            {"inputs": ["4A", "4B"], "output": "4Y", "in_pins": [12, 13], "out_pin": 11},
        ],
        "vcc": 14, "gnd": 7, "package": "14-pin DIP",
    },
    "OR_QUAD": {
        "function": "OR",
        "logic_type": "combinational",
        "gates": [
            {"inputs": ["1A", "1B"], "output": "1Y", "in_pins": [1, 2], "out_pin": 3},
            {"inputs": ["2A", "2B"], "output": "2Y", "in_pins": [4, 5], "out_pin": 6},
            {"inputs": ["3A", "3B"], "output": "3Y", "in_pins": [9, 10], "out_pin": 8},
            {"inputs": ["4A", "4B"], "output": "4Y", "in_pins": [12, 13], "out_pin": 11},
        ],
        "vcc": 14, "gnd": 7, "package": "14-pin DIP",
    },
    "NOR_QUAD": {
        "function": "NOR",
        "logic_type": "combinational",
        "gates": [
            {"inputs": ["1A", "1B"], "output": "1Y", "in_pins": [1, 2], "out_pin": 3},
            {"inputs": ["2A", "2B"], "output": "2Y", "in_pins": [4, 5], "out_pin": 6},
            {"inputs": ["3A", "3B"], "output": "3Y", "in_pins": [9, 10], "out_pin": 8},
            {"inputs": ["4A", "4B"], "output": "4Y", "in_pins": [12, 13], "out_pin": 11},
        ],
        "vcc": 14, "gnd": 7, "package": "14-pin DIP",
    },
    "XOR_QUAD": {
        "function": "XOR",
        "logic_type": "combinational",
        "gates": [
            {"inputs": ["1A", "1B"], "output": "1Y", "in_pins": [1, 2], "out_pin": 3},
            {"inputs": ["2A", "2B"], "output": "2Y", "in_pins": [4, 5], "out_pin": 6},
            {"inputs": ["3A", "3B"], "output": "3Y", "in_pins": [9, 10], "out_pin": 8},
            {"inputs": ["4A", "4B"], "output": "4Y", "in_pins": [12, 13], "out_pin": 11},
        ],
        "vcc": 14, "gnd": 7, "package": "14-pin DIP",
    },
    # Hex inverters (14-pin DIP)
    "NOT_HEX": {
        "function": "NOT",
        "logic_type": "combinational",
        "gates": [
            {"inputs": ["1A"], "output": "1Y", "in_pins": [1], "out_pin": 2},
            {"inputs": ["2A"], "output": "2Y", "in_pins": [3], "out_pin": 4},
            {"inputs": ["3A"], "output": "3Y", "in_pins": [5], "out_pin": 6},
            {"inputs": ["4A"], "output": "4Y", "in_pins": [9], "out_pin": 8},
            {"inputs": ["5A"], "output": "5Y", "in_pins": [11], "out_pin": 10},
            {"inputs": ["6A"], "output": "6Y", "in_pins": [13], "out_pin": 12},
        ],
        "vcc": 14, "gnd": 7, "package": "14-pin DIP",
    },
}

# Gate logic functions
GATE_LOGIC = {
    "AND":    lambda a, b: a & b,
    "OR":     lambda a, b: a | b,
    "NAND":   lambda a, b: 1 - (a & b),
    "NOR":    lambda a, b: 1 - (a | b),
    "XOR":    lambda a, b: a ^ b,
    "XNOR":   lambda a, b: 1 - (a ^ b),
    "NOT":    lambda a: 1 - a,
    "BUFFER": lambda a: a,
}


class TestGenerator:
    """
    Generates test suites for IC chips automatically.

    Supports:
    - Combinational logic: full truth table enumeration for standard gates
    - Sequential logic: clock-driven test sequences with state tracking
    - Custom: conversion from fingerprint observations to test definitions
    - Export: saves generated tests as JSON chip definitions

    Attributes:
        chips_dir: Directory containing JSON chip definition files
    """

    def __init__(self, chips_dir: Optional[Path] = None):
        """
        Args:
            chips_dir: Path to chips/ directory for saving generated definitions
        """
        self.chips_dir = chips_dir or Config.CHIPS_DIR
        logger.info("TestGenerator initialized")

    # ------------------------------------------------------------------
    # Combinational logic generation
    # ------------------------------------------------------------------

    def generate_truth_table(
        self,
        gate_function: str,
        input_names: List[str],
        output_name: str,
        gate_index: int = 1,
    ) -> List[TestVector]:
        """
        Generate a complete truth table for a logic gate.

        Args:
            gate_function: Gate type (AND, OR, NAND, NOR, XOR, XNOR, NOT, BUFFER)
            input_names: List of input pin names
            output_name: Output pin name
            gate_index: Gate number for test ID naming

        Returns:
            List of TestVector covering all input combinations
        """
        func = GATE_LOGIC.get(gate_function)
        if func is None:
            logger.error(f"Unknown gate function: {gate_function}")
            return []

        num_inputs = len(input_names)
        vectors = []

        # Enumerate every binary input combination and compute the expected
        # output row exactly once.
        for combo in itertools.product([0, 1], repeat=num_inputs):
            # Compute expected output
            if num_inputs == 1:
                expected = func(combo[0])
            elif num_inputs == 2:
                expected = func(combo[0], combo[1])
            else:
                # Chain the function for >2 inputs
                result = combo[0]
                for val in combo[1:]:
                    result = func(result, val)
                expected = result

            inputs = {input_names[i]: combo[i] for i in range(num_inputs)}
            in_str = "".join(str(b) for b in combo)

            vectors.append(TestVector(
                test_id=f"gate{gate_index}_{gate_function}_{in_str}",
                inputs=inputs,
                expected_outputs={output_name: expected},
                description=f"Gate {gate_index}: {gate_function} inputs={in_str} → {expected}",
            ))

        return vectors

    def generate_chip_test_suite(
        self,
        template_key: str,
    ) -> GeneratedTestSuite:
        """
        Generate a full test suite for a chip using a template.

        Args:
            template_key: Key into CHIP_TEMPLATES (e.g. "NAND_QUAD")

        Returns:
            GeneratedTestSuite with all test vectors
        """
        template = CHIP_TEMPLATES.get(template_key)
        if template is None:
            logger.error(f"Unknown chip template: {template_key}")
            return GeneratedTestSuite(chip_id=template_key)

        suite = GeneratedTestSuite(
            chip_id=template_key,
            logic_type=template["function"],
            gate_function=template["function"],
            num_gates=len(template["gates"]),
        )

        # Concatenate each gate's truth table into one suite representing the
        # whole packaged IC.
        for gate_idx, gate in enumerate(template["gates"], 1):
            vectors = self.generate_truth_table(
                gate_function=template["function"],
                input_names=gate["inputs"],
                output_name=gate["output"],
                gate_index=gate_idx,
            )
            suite.vectors.extend(vectors)

        logger.info(
            f"Generated {len(suite.vectors)} test vectors for {template_key} "
            f"({suite.num_gates} gates)"
        )
        return suite

    def detect_logic_function(self, chip_data: Dict[str, Any]) -> Optional[str]:
        """
        Infer a basic combinational logic function from chip metadata.

        Supports the standard gate/inverter chips used by the manual tester
        game mode. Returns None for unsupported or ambiguous parts.
        """
        haystack = " ".join([
            str(chip_data.get("chipId", "")),
            str(chip_data.get("name", "")),
            str(chip_data.get("description", "")),
        ]).lower()

        checks = [
            ("XNOR", ["xnor"]),
            ("XOR", ["xor"]),
            ("NAND", ["nand"]),
            ("NOR", [" nor", "nor ", "quad nor", "2-input nor"]),
            ("BUFFER", ["buffer"]),
            ("NOT", ["inverter", "not gate", "hex inverter", "inverting"]),
            ("AND", [" and", "and ", "quad and", "2-input and"]),
            ("OR", [" or", "or ", "quad or", "2-input or"]),
        ]

        for logic_name, patterns in checks:
            if any(pattern in haystack for pattern in patterns):
                return logic_name
        return None

    def infer_gate_groups(
        self, chip_data: Dict[str, Any]
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Infer gate groupings from a chip definition's pin names.

        Expected naming convention:
        - 2-input gates: `1A`, `1B` -> `1Y`
        - 1-input gates: `1A` -> `1Y`
        """
        pinout = chip_data.get("pinout", {})
        inputs = pinout.get("inputs", [])
        outputs = pinout.get("outputs", [])
        groups: List[Dict[str, Any]] = []

        for out in outputs:
            out_name = str(out.get("name", ""))
            if not out_name.endswith("Y") or len(out_name) < 2:
                return None

            prefix = out_name[:-1]
            matching_inputs = [
                inp for inp in inputs
                if str(inp.get("name", "")).startswith(prefix)
            ]
            if len(matching_inputs) not in (1, 2):
                return None

            matching_inputs.sort(key=lambda item: str(item.get("name", "")))
            groups.append({
                "prefix": prefix,
                "inputs": [str(inp["name"]) for inp in matching_inputs],
                "output": out_name,
            })

        groups.sort(key=lambda item: item["prefix"])
        return groups if groups else None

    def generate_suite_from_chip(
        self, chip_data: Dict[str, Any]
    ) -> Optional[GeneratedTestSuite]:
        """
        Generate a combinational test suite directly from a chip definition.

        This is used by the manual tester game mode to create round data from
        the chip's structure rather than its stored automated test sequence.
        """
        logic_function = self.detect_logic_function(chip_data)
        groups = self.infer_gate_groups(chip_data)
        if logic_function is None or groups is None:
            return None

        valid_input_counts = {len(group["inputs"]) for group in groups}
        if valid_input_counts == {1} and logic_function not in ("NOT", "BUFFER"):
            return None
        if valid_input_counts == {2} and logic_function not in (
            "AND", "OR", "NAND", "NOR", "XOR", "XNOR"
        ):
            return None
        if len(valid_input_counts) != 1:
            return None

        suite = GeneratedTestSuite(
            chip_id=str(chip_data.get("chipId", "UNKNOWN")),
            logic_type="combinational",
            gate_function=logic_function,
            num_gates=len(groups),
            notes="Generated directly from chip pin groups",
        )

        for gate_idx, group in enumerate(groups, 1):
            suite.vectors.extend(
                self.generate_truth_table(
                    gate_function=logic_function,
                    input_names=group["inputs"],
                    output_name=group["output"],
                    gate_index=gate_idx,
                )
            )

        return suite

    # ------------------------------------------------------------------
    # Sequential logic support
    # ------------------------------------------------------------------

    def generate_counter_test(
        self,
        clock_pin: str,
        output_pins: List[str],
        max_count: int = 16,
        reset_pin: str = None,
    ) -> List[TestVector]:
        """
        Generate test vectors for a binary counter IC.

        Args:
            clock_pin: Name of the clock input pin
            output_pins: Names of output pins (LSB first)
            max_count: Maximum count to test (default: 16)
            reset_pin: Optional reset pin name

        Returns:
            List of TestVector with clock edges and expected counter states
        """
        vectors = []
        num_bits = len(output_pins)
        max_val = min(max_count, 2 ** num_bits)

        # For sequential parts we generate an ordered scenario instead of a flat
        # truth table, because expected outputs depend on prior clock events.
        # Reset sequence (if reset pin exists)
        if reset_pin:
            vectors.append(TestVector(
                test_id="counter_reset",
                inputs={reset_pin: 1, clock_pin: 0},
                expected_outputs={pin: 0 for pin in output_pins},
                description="Reset counter to 0",
                is_sequential=True,
            ))
            vectors.append(TestVector(
                test_id="counter_release_reset",
                inputs={reset_pin: 0, clock_pin: 0},
                expected_outputs={pin: 0 for pin in output_pins},
                description="Release reset",
                is_sequential=True,
            ))

        # Then step through each expected count value in LSB-first bit order.
        for count in range(max_val):
            expected = {}
            for bit_idx, pin in enumerate(output_pins):
                expected[pin] = (count >> bit_idx) & 1

            vectors.append(TestVector(
                test_id=f"counter_count_{count}",
                inputs={clock_pin: 1},
                expected_outputs=expected,
                description=f"Count = {count} (binary: {count:0{num_bits}b})",
                is_sequential=True,
                clock_edges=count,
            ))

        logger.info(f"Generated {len(vectors)} counter test vectors (up to {max_val})")
        return vectors

    # ------------------------------------------------------------------
    # JSON export
    # ------------------------------------------------------------------

    def export_as_chip_json(
        self,
        suite: GeneratedTestSuite,
        chip_id: str,
        chip_name: str,
        description: str = "",
        template_key: str = None,
        save: bool = True,
    ) -> Dict:
        """
        Export a generated test suite as a JSON chip definition file.

        Args:
            suite: GeneratedTestSuite to export
            chip_id: Chip identifier (e.g. "SN74LS00N")
            chip_name: Human-readable chip name
            description: Chip description
            template_key: Optional template key for pin assignments
            save: Whether to save to chips/ directory

        Returns:
            Dict containing the complete chip definition
        """
        template = CHIP_TEMPLATES.get(template_key) if template_key else None

        # Reconstruct the JSON schema expected by the runtime chip database from
        # the richer generated suite/template structures.
        # Build pinout
        inputs = []
        outputs = []
        if template:
            for gate in template["gates"]:
                for i, name in enumerate(gate["inputs"]):
                    if not any(p["name"] == name for p in inputs):
                        inputs.append({"pin": gate["in_pins"][i], "name": name})
                if not any(p["name"] == gate["output"] for p in outputs):
                    outputs.append({"pin": gate["out_pin"], "name": gate["output"]})

        pinout = {
            "inputs": inputs,
            "outputs": outputs,
        }
        if template:
            pinout["vcc"] = template.get("vcc", 14)
            pinout["gnd"] = template.get("gnd", 7)

        # Convert 0/1 vector values into the HIGH/LOW strings used by the tester.
        tests = []
        for vec in suite.vectors:
            test = {
                "id": vec.test_id,
                "inputs": {k: "HIGH" if v else "LOW" for k, v in vec.inputs.items()},
                "expectedOutputs": {k: "HIGH" if v else "LOW" for k, v in vec.expected_outputs.items()},
                "description": vec.description,
            }
            tests.append(test)

        chip_def = {
            "chipId": chip_id,
            "name": chip_name,
            "description": description,
            "package": template.get("package", "14-pin DIP") if template else "14-pin DIP",
            "logicType": suite.logic_type,
            "gateFunction": suite.gate_function,
            "pinout": pinout,
            "tests": tests,
            "generatedBy": "TestGenerator",
            "notes": suite.notes,
        }

        if save:
            filepath = self.chips_dir / f"{chip_id}.json"
            filepath.write_text(
                json.dumps(chip_def, indent=2), encoding="utf-8"
            )
            logger.info(f"Exported chip definition: {filepath}")

        return chip_def

    def from_fingerprint(
        self,
        fingerprint,
        chip_id: str = "UNKNOWN",
    ) -> GeneratedTestSuite:
        """
        Convert an ICFingerprinter ChipFingerprint into a test suite.

        Uses the observed truth table from fingerprinting as the basis
        for test vectors. Useful for creating test definitions from
        unknown chips that were identified via exploratory probing.

        Args:
            fingerprint: ChipFingerprint from ICFingerprinter
            chip_id: Chip ID to assign

        Returns:
            GeneratedTestSuite derived from observed behavior
        """
        # This path converts empirical observations back into authored tests,
        # which is useful when exploring an unknown part and then preserving the
        # discovered behavior as a reusable definition.
        suite = GeneratedTestSuite(
            chip_id=chip_id,
            gate_function=fingerprint.best_match_function or "UNKNOWN",
            notes="Generated from fingerprint observation",
        )

        for idx, row in enumerate(fingerprint.derived_truth_table):
            inputs = row.get("inputs", {})
            outputs = row.get("outputs", {})

            suite.vectors.append(TestVector(
                test_id=f"fp_observed_{idx}",
                inputs={k: v for k, v in inputs.items()},
                expected_outputs={k: v for k, v in outputs.items()},
                description=f"Observed behavior row {idx}",
            ))

        logger.info(
            f"Generated {len(suite.vectors)} vectors from fingerprint of {chip_id}"
        )
        return suite
