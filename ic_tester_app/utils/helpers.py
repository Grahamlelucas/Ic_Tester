# ic_tester_app/utils/helpers.py
# Last edited: 2026-01-19
# Purpose: General utility functions for the IC Tester application
# Dependencies: None

"""
Helper utilities for IC Tester application.
Contains commonly used functions for validation, formatting, and data conversion.
"""

from typing import Optional, List, Union

from ..config import Config


def validate_pin_number(pin: Union[int, str]) -> tuple[bool, Optional[int], str]:
    """
    Validate an Arduino pin number for Mega 2560.
    
    Accepts:
    - Integer pin numbers (0-53 for digital, 54-69 for analog)
    - String pin numbers ('22', '53')
    - Analog pin notation ('A0' through 'A15')
    
    Args:
        pin: Pin number or string to validate
    
    Returns:
        Tuple of (is_valid, pin_number, error_message)
        pin_number is None if invalid
    """
    # Handle string input
    if isinstance(pin, str):
        pin = pin.strip().upper()
        
        # Check for analog pin notation
        if pin.startswith('A'):
            try:
                analog_num = int(pin[1:])
                if 0 <= analog_num <= 15:
                    # Convert to digital pin number (A0 = 54 on Mega)
                    return (True, 54 + analog_num, "")
                else:
                    return (False, None, f"Invalid analog pin: {pin}. Valid: A0-A15")
            except ValueError:
                return (False, None, f"Invalid analog pin format: {pin}")
        
        # Try to parse as integer
        try:
            pin = int(pin)
        except ValueError:
            return (False, None, f"Invalid pin value: {pin}")
    
    # Validate integer pin number
    if not isinstance(pin, int):
        return (False, None, f"Pin must be integer, got {type(pin).__name__}")
    
    # Check valid range for Mega 2560
    if pin < 0 or pin > 69:
        return (False, None, f"Pin {pin} out of range. Valid: 0-53 (digital), A0-A15 (analog)")
    
    # Check for reserved pins
    if pin in Config.RESERVED_PINS:
        reason = Config.RESERVED_PINS[pin]
        return (True, pin, f"Warning: Pin {pin} is reserved for {reason}")
    
    return (True, pin, "")


def is_valid_test_pin(pin: int) -> bool:
    """
    Check if a pin is valid for IC testing (not reserved).
    
    Args:
        pin: Pin number to check
    
    Returns:
        True if pin can be used for testing
    """
    return pin in Config.VALID_TEST_PINS


def format_pin_list(pins: List[int], include_analog: bool = True) -> str:
    """
    Format a list of pin numbers for display.
    
    Args:
        pins: List of pin numbers
        include_analog: If True, convert pins 54+ to 'Ax' notation
    
    Returns:
        Formatted string like "22, 23, 24, A0, A1"
    """
    formatted = []
    for pin in sorted(pins):
        if include_analog and pin >= 54:
            formatted.append(f"A{pin - 54}")
        else:
            formatted.append(str(pin))
    return ", ".join(formatted)


def safe_int(value: any, default: int = 0) -> int:
    """
    Safely convert a value to integer.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
    
    Returns:
        Integer value or default
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def parse_pin_state(response: str) -> Optional[str]:
    """
    Parse a pin state from Arduino response.
    
    Args:
        response: Response string from Arduino
    
    Returns:
        'HIGH', 'LOW', or None if unparseable
    """
    if not response:
        return None
    
    response = response.upper()
    if 'HIGH' in response:
        return 'HIGH'
    elif 'LOW' in response:
        return 'LOW'
    
    return None


def format_test_result(passed: int, failed: int, total: int) -> str:
    """
    Format test results as a summary string.
    
    Args:
        passed: Number of tests passed
        failed: Number of tests failed
        total: Total number of tests
    
    Returns:
        Formatted string like "8/10 passed (80%)"
    """
    if total == 0:
        return "No tests run"
    
    percentage = (passed / total) * 100
    return f"{passed}/{total} passed ({percentage:.0f}%)"


def truncate_string(text: str, max_length: int = 50, suffix: str = "...") -> str:
    """
    Truncate a string to a maximum length.
    
    Args:
        text: String to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add when truncated
    
    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix
