"""
Base protocol for chip data providers.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any


class ChipDataProvider(ABC):
    """Abstract interface for a chip definition source."""

    @abstractmethod
    def reload(self):
        """Reload provider data from backing store."""

    @abstractmethod
    def get_chip(self, chip_id: str, board: str = "MEGA") -> Optional[Dict[str, Any]]:
        """Get a chip by ID."""

    @abstractmethod
    def get_all_chip_ids(self, board: str = "MEGA") -> List[str]:
        """Get all available chip IDs."""

    @abstractmethod
    def get_chip_count(self, board: str = "MEGA") -> int:
        """Get number of chips available."""

    @abstractmethod
    def validate_chip(self, chip_id: str, board: str = "MEGA") -> Tuple[bool, List[str]]:
        """Validate a chip definition."""
