# ic_tester_app/gui/panels/__init__.py
# Last edited: 2026-01-19
# Purpose: GUI panel components exports
# Dependencies: None

"""
GUI Panels module.
Contains individual panel components for the main application window.

Panels:
- ConnectionPanel: Arduino connection controls
- ChipPanel: Chip selection and test controls  
- PinMappingPanel: Dynamic pin mapping configuration
- StatusPanel: Test result status indicator
- OutputPanel: Log output display
"""

from .connection import ConnectionPanel
from .chip_select import ChipPanel
from .pin_mapping import PinMappingPanel
from .status import StatusPanel
from .output import OutputPanel
