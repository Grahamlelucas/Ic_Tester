# ic_tester_app/__init__.py
# Last edited: 2026-01-19
# Purpose: IC Tester Application Package - 74-Series Chip Testing System
# Dependencies: See individual modules

"""
IC Tester Application
A modular application for testing 74-series integrated circuits using Arduino Mega 2560.

Package Structure:
    - arduino/     : Arduino communication and commands
    - chips/       : Chip database and testing logic
    - gui/         : User interface components
    - utils/       : Utility functions and helpers
"""

__version__ = "4.1"
__author__ = "Legways Software"

from .config import Config
from .logger import get_logger
