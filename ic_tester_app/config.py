# ic_tester_app/config.py
# Last edited: 2026-01-19
# Purpose: Application configuration and constants
# Dependencies: None

"""
Configuration module for IC Tester application.
Contains all configurable settings, constants, and default values.
"""

import os
from pathlib import Path


class Config:
    """Application configuration settings"""
    
    # Application Info
    APP_NAME = "IC Tester Pro"
    APP_VERSION = "4.1"
    APP_SUBTITLE = "74-Series Chip Testing System"
    
    # Paths
    BASE_DIR = Path(__file__).parent.parent
    CHIPS_DIR = BASE_DIR / "chips"
    PIN_MAPPINGS_DIR = BASE_DIR / "pin_mappings"
    LOGS_DIR = BASE_DIR / "logs"
    EXCEL_LIBRARY_PATH = CHIPS_DIR / "chip_library.xlsx"
    
    # Data source mode: "json", "excel", "hybrid"
    DATA_SOURCE_MODE = "hybrid"
    
    # Default board profile for mapping resolution
    DEFAULT_BOARD = "MEGA"
    
    # Hybrid mode fallback behavior
    HYBRID_FALLBACK_TO_JSON = True
    
    # Arduino Settings
    SERIAL_BAUD_RATE = 9600
    SERIAL_TIMEOUT = 2.0
    CONNECTION_CHECK_INTERVAL = 5000  # ms
    COMMAND_DELAY = 0.05  # seconds between commands
    
    # Mega 2560 Pin Configuration
    MEGA_DIGITAL_PINS = range(0, 54)  # 0-53
    MEGA_ANALOG_PINS = range(54, 70)  # A0-A15 (54-69)
    
    # Reserved pins (not available for IC testing)
    RESERVED_PINS = {
        0: "Serial RX",
        1: "Serial TX",
        50: "SPI MISO (may cause issues)",
        51: "SPI MOSI (may cause issues)",
        52: "SPI SCK (may cause issues)",
        53: "SPI SS (may cause issues)",
    }
    
    # Valid pins for IC testing (excludes serial 0-1, SPI 50-53, A0)
    VALID_TEST_PINS = list(range(2, 4)) + list(range(10, 50)) + list(range(55, 70))
    
    # GUI Settings - larger, more spacious window
    WINDOW_MIN_WIDTH = 1200
    WINDOW_MIN_HEIGHT = 750
    WINDOW_START_WIDTH = 1400
    WINDOW_START_HEIGHT = 900
    
    # Logging
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    LOG_FILE_MAX_BYTES = 5 * 1024 * 1024  # 5MB
    LOG_BACKUP_COUNT = 3
    
    @classmethod
    def ensure_directories(cls):
        """Create required directories if they don't exist"""
        cls.CHIPS_DIR.mkdir(exist_ok=True)
        cls.PIN_MAPPINGS_DIR.mkdir(exist_ok=True)
        cls.LOGS_DIR.mkdir(exist_ok=True)


class Theme:
    """UI Theme colors and styling"""
    
    # Background colors
    BG_DARK = "#1a1a2e"
    BG_CARD = "#16213e"
    BG_LIGHT = "#2a2a4a"
    
    # Text colors
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#a0a0a0"
    TEXT_MUTED = "#606080"
    
    # Accent colors
    ACCENT_PRIMARY = "#0f3460"
    ACCENT_SUCCESS = "#00d9a0"
    ACCENT_ERROR = "#e94560"
    ACCENT_WARNING = "#f39c12"
    ACCENT_INFO = "#00a8cc"
    
    # Status colors
    CONNECTED = "#00d9a0"
    DISCONNECTED = "#e94560"
    PENDING = "#f39c12"
    
    # Font sizes
    FONT_HEADING = 18
    FONT_SUBHEADING = 14
    FONT_BODY = 11
    FONT_SMALL = 10
    FONT_MONO = 10
