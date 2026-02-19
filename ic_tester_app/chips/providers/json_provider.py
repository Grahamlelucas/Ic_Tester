"""
JSON-based chip data provider.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from ...logger import get_logger
from .base import ChipDataProvider

logger = get_logger("chips.providers.json")


class JsonChipProvider(ChipDataProvider):
    """Loads chip definitions from JSON files in a directory."""

    def __init__(self, chips_dir: Path):
        self.chips_dir = chips_dir
        self._chips: Dict[str, Dict[str, Any]] = {}
        self.reload()

    def reload(self):
        self._chips.clear()
        if not self.chips_dir.exists():
            self.chips_dir.mkdir(parents=True, exist_ok=True)
            logger.warning(f"Created chips directory: {self.chips_dir}")
            return

        json_files = list(self.chips_dir.glob("*.json"))
        logger.info(f"JSON provider found {len(json_files)} chip definition file(s)")

        for json_file in json_files:
            self._load_chip_file(json_file)

        logger.info(f"JSON provider loaded {len(self._chips)} chip(s)")

    def _load_chip_file(self, filepath: Path) -> bool:
        try:
            with open(filepath, "r") as f:
                chip_data = json.load(f)

            chip_id = chip_data.get("chipId")
            if not chip_id:
                logger.warning(f"Chip file {filepath.name} missing 'chipId' field")
                return False

            self._chips[chip_id] = chip_data
            return True
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error in {filepath.name}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error loading {filepath.name}: {e}")
            return False

    def get_chip(self, chip_id: str, board: str = "MEGA") -> Optional[Dict[str, Any]]:
        _ = board
        return self._chips.get(chip_id)

    def get_all_chip_ids(self, board: str = "MEGA") -> List[str]:
        _ = board
        return sorted(self._chips.keys())

    def get_chip_count(self, board: str = "MEGA") -> int:
        _ = board
        return len(self._chips)

    def validate_chip(self, chip_id: str, board: str = "MEGA") -> Tuple[bool, List[str]]:
        _ = board
        chip = self.get_chip(chip_id)
        errors = []

        if not chip:
            return False, [f"Chip '{chip_id}' not found"]

        required = ["pinout", "testSequence"]
        for field in required:
            if field not in chip:
                errors.append(f"Missing required field: {field}")

        pinout = chip.get("pinout", {})
        if not pinout.get("inputs") and not pinout.get("outputs"):
            errors.append("Pinout must contain inputs and/or outputs")

        test_seq = chip.get("testSequence", {})
        if "tests" not in test_seq or not test_seq["tests"]:
            errors.append("testSequence must contain 'tests' array")

        return len(errors) == 0, errors
