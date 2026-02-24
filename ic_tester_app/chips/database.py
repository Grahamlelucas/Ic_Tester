"""
Chip database module - JSON-only data provider.
"""

from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

from ..config import Config
from ..logger import get_logger
from .providers import JsonChipProvider

logger = get_logger("chips.database")


class ChipDatabase:
    """Chip definition facade using JSON provider."""

    def __init__(
        self,
        chips_dir: Optional[Path] = None,
        board: str = None,
        **kwargs,
    ):
        self.chips_dir = chips_dir or Config.CHIPS_DIR
        self.board = (board or Config.DEFAULT_BOARD).upper()
        self.json_provider = JsonChipProvider(self.chips_dir)

    def reload(self):
        logger.info("Reloading chip database...")
        self.json_provider.reload()

    def set_board(self, board: str):
        self.board = str(board or "MEGA").upper()
        logger.info(f"Chip board profile set to: {self.board}")

    def get_chip(self, chip_id: str, board: str = None) -> Optional[Dict[str, Any]]:
        selected_board = str(board or self.board).upper()
        return self.json_provider.get_chip(chip_id, board=selected_board)

    def get_all_chip_ids(self, board: str = None) -> List[str]:
        selected_board = str(board or self.board).upper()
        return self.json_provider.get_all_chip_ids(board=selected_board)

    def get_chip_count(self, board: str = None) -> int:
        return len(self.get_all_chip_ids(board=board))

    def get_chip_pinout(self, chip_id: str, board: str = None) -> Optional[Dict[str, Any]]:
        chip = self.get_chip(chip_id, board=board)
        if chip:
            return chip.get("pinout", {})
        return None

    def get_chip_test_sequence(self, chip_id: str, board: str = None) -> Optional[Dict[str, Any]]:
        chip = self.get_chip(chip_id, board=board)
        if chip:
            return chip.get("testSequence", {})
        return None

    def get_chip_info(self, chip_id: str, board: str = None) -> Dict[str, str]:
        chip = self.get_chip(chip_id, board=board)
        if chip:
            return {
                "name": chip.get("name", chip_id),
                "description": chip.get("description", "No description available"),
            }
        return {"name": chip_id, "description": "Chip not found"}

    def validate_chip(self, chip_id: str, board: str = None) -> Tuple[bool, List[str]]:
        selected_board = str(board or self.board).upper()
        return self.json_provider.validate_chip(chip_id, board=selected_board)

    def get_board(self) -> str:
        return self.board
