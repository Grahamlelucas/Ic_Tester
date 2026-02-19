# ic_tester_app/logger.py
# Last edited: 2026-01-19
# Purpose: Centralized logging system with file and console output
# Dependencies: logging, pathlib

"""
Logging module for IC Tester application.
Provides consistent logging across all modules with file rotation.
"""

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import Config


# Global logger cache
_loggers = {}


def setup_logging():
    """Initialize the logging system"""
    Config.ensure_directories()
    
    # Create root logger for the application
    root_logger = logging.getLogger("ic_tester")
    root_logger.setLevel(getattr(logging, Config.LOG_LEVEL))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_format = logging.Formatter(
        "%(levelname)s - %(name)s - %(message)s"
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)
    
    # File handler with rotation
    log_filename = Config.LOGS_DIR / f"ic_tester_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = RotatingFileHandler(
        log_filename,
        maxBytes=Config.LOG_FILE_MAX_BYTES,
        backupCount=Config.LOG_BACKUP_COUNT
    )
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(Config.LOG_FORMAT, Config.LOG_DATE_FORMAT)
    file_handler.setFormatter(file_format)
    root_logger.addHandler(file_handler)
    
    root_logger.info(f"Logging initialized - {Config.APP_NAME} v{Config.APP_VERSION}")
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.
    
    Args:
        name: Module name (e.g., 'arduino.connection', 'gui.app')
    
    Returns:
        Logger instance
    """
    full_name = f"ic_tester.{name}"
    
    if full_name not in _loggers:
        _loggers[full_name] = logging.getLogger(full_name)
    
    return _loggers[full_name]


class GUILogHandler(logging.Handler):
    """
    Custom logging handler that forwards log messages to the GUI output panel.
    
    Usage:
        handler = GUILogHandler(gui_log_callback)
        logger.addHandler(handler)
    """
    
    def __init__(self, callback):
        """
        Args:
            callback: Function to call with (message, level) for each log entry
        """
        super().__init__()
        self.callback = callback
        
        # Map log levels to GUI log types
        self.level_map = {
            logging.DEBUG: "debug",
            logging.INFO: "info",
            logging.WARNING: "warning",
            logging.ERROR: "error",
            logging.CRITICAL: "error"
        }
    
    def emit(self, record):
        """Process a log record and send to GUI"""
        try:
            msg = self.format(record)
            level = self.level_map.get(record.levelno, "info")
            self.callback(msg, level)
        except Exception:
            self.handleError(record)
