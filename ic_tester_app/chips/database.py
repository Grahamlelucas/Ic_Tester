"""
Chip database module with pluggable data providers.
Supports JSON, Excel, and hybrid loading modes.
"""

from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple, Literal

from ..config import Config
from ..logger import get_logger
from .providers import JsonChipProvider, ExcelChipProvider

logger = get_logger("chips.database")

SourceMode = Literal["json", "excel", "hybrid"]


class ChipDatabase:
    """Chip definition facade across JSON/Excel providers."""

    def __init__(
        self,
        chips_dir: Optional[Path] = None,
        source_mode: SourceMode = None,
        excel_path: Optional[Path] = None,
        board: str = None,
        hybrid_fallback_to_json: bool = None,
    ):
        self.chips_dir = chips_dir or Config.CHIPS_DIR
        self.source_mode: SourceMode = (source_mode or Config.DATA_SOURCE_MODE).lower()  # type: ignore[assignment]
        self.excel_path = excel_path or Config.EXCEL_LIBRARY_PATH
        self.board = (board or Config.DEFAULT_BOARD).upper()
        self.hybrid_fallback_to_json = (
            Config.HYBRID_FALLBACK_TO_JSON
            if hybrid_fallback_to_json is None
            else hybrid_fallback_to_json
        )

        self.json_provider = JsonChipProvider(self.chips_dir)
        self.excel_provider = ExcelChipProvider(self.excel_path)

        self._source_modes = {"json", "excel", "hybrid"}
        if self.source_mode not in self._source_modes:
            logger.warning(
                f"Unknown source mode '{self.source_mode}', defaulting to 'hybrid'"
            )
            self.source_mode = "hybrid"

    def reload(self):
        logger.info("Reloading chip database providers...")
        self.json_provider.reload()
        self.excel_provider.reload()

    def set_source_mode(self, source_mode: SourceMode):
        mode = str(source_mode).lower()
        if mode not in self._source_modes:
            logger.warning(f"Ignoring invalid source mode: {source_mode}")
            return
        self.source_mode = mode  # type: ignore[assignment]
        logger.info(f"Chip source mode set to: {self.source_mode}")

    def set_excel_path(self, excel_path: Path):
        self.excel_path = excel_path
        self.excel_provider = ExcelChipProvider(excel_path)
        logger.info(f"Excel library path set to: {excel_path}")

    def set_board(self, board: str):
        self.board = str(board or "MEGA").upper()
        logger.info(f"Chip board profile set to: {self.board}")

    def get_chip(self, chip_id: str, board: str = None) -> Optional[Dict[str, Any]]:
        selected_board = str(board or self.board).upper()

        if self.source_mode == "json":
            return self.json_provider.get_chip(chip_id, board=selected_board)

        if self.source_mode == "excel":
            return self.excel_provider.get_chip(chip_id, board=selected_board)

        # hybrid: prefer Excel, optionally fallback to JSON
        chip = self.excel_provider.get_chip(chip_id, board=selected_board)
        if chip:
            return chip
        if self.hybrid_fallback_to_json:
            return self.json_provider.get_chip(chip_id, board=selected_board)
        return None

    def get_all_chip_ids(self, board: str = None) -> List[str]:
        selected_board = str(board or self.board).upper()

        if self.source_mode == "json":
            return self.json_provider.get_all_chip_ids(board=selected_board)

        if self.source_mode == "excel":
            return self.excel_provider.get_all_chip_ids(board=selected_board)

        excel_ids = set(self.excel_provider.get_all_chip_ids(board=selected_board))
        json_ids = set(self.json_provider.get_all_chip_ids(board=selected_board))
        return sorted(excel_ids | json_ids if self.hybrid_fallback_to_json else excel_ids)

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

        if self.source_mode == "json":
            return self.json_provider.validate_chip(chip_id, board=selected_board)

        if self.source_mode == "excel":
            return self.excel_provider.validate_chip(chip_id, board=selected_board)

        # hybrid validation: validate whichever source resolves first
        chip = self.excel_provider.get_chip(chip_id, board=selected_board)
        if chip:
            return self.excel_provider.validate_chip(chip_id, board=selected_board)

        if self.hybrid_fallback_to_json:
            return self.json_provider.validate_chip(chip_id, board=selected_board)

        return False, [f"Chip '{chip_id}' not found in active source"]

    def get_source_mode(self) -> str:
        return self.source_mode

    def get_board(self) -> str:
        return self.board
    
    def get_source_errors(self) -> List[str]:
        errors: List[str] = []
        if self.source_mode in {"excel", "hybrid"}:
            if hasattr(self.excel_provider, "get_errors"):
                errors.extend(self.excel_provider.get_errors())
        return errors
