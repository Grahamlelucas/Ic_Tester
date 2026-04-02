# ic_tester_app/gui/theme.py
# Last edited: 2026-01-19
# Purpose: UI theme colors, fonts, and styling constants
# Dependencies: platform

"""
Theme module for IC Tester GUI.
Defines consistent colors, fonts, and styling across the application.
Supports cross-platform font selection (macOS, Windows, Linux).
"""

import platform
from typing import Dict, Tuple


class Theme:
    """
    Modern dark theme color palette and styling constants.
    
    All colors use hex format for tkinter compatibility.
    Fonts are platform-specific for native look and feel.
    """
    
    # =========================================================================
    # Background Colors
    # =========================================================================
    BG_DARK = "#1a1a2e"      # Main window background
    BG_MEDIUM = "#16213e"    # Secondary background
    BG_LIGHT = "#0f3460"     # Highlighted background
    BG_CARD = "#1f2940"      # Card/panel background
    
    # =========================================================================
    # Accent Colors (for buttons, indicators, highlights)
    # =========================================================================
    ACCENT_PRIMARY = "#4361ee"   # Primary action buttons
    ACCENT_SUCCESS = "#06d6a0"   # Success states, pass indicators
    ACCENT_ERROR = "#ef476f"     # Error states, fail indicators
    ACCENT_WARNING = "#ffd166"   # Warning states, in-progress
    ACCENT_INFO = "#118ab2"      # Info buttons, hover states
    
    # =========================================================================
    # Text Colors
    # =========================================================================
    TEXT_PRIMARY = "#ffffff"     # Main text (white)
    TEXT_SECONDARY = "#a0aec0"   # Secondary text (light gray)
    TEXT_MUTED = "#718096"       # Muted text (dark gray)
    
    # =========================================================================
    # Status Colors (for connection indicators)
    # =========================================================================
    CONNECTED = "#06d6a0"        # Green - connected
    DISCONNECTED = "#ef476f"     # Red - disconnected
    PENDING = "#ffd166"          # Yellow - connecting/testing
    
    # =========================================================================
    # Sizing Constants
    # =========================================================================
    BUTTON_RADIUS = 8            # Border radius for buttons
    CARD_PADDING = 15            # Padding inside cards
    SECTION_SPACING = 15         # Vertical spacing between sections


def get_fonts() -> Dict[str, Tuple]:
    """
    Get platform-specific font definitions.
    
    Returns a dictionary of font tuples for different text styles:
    - heading: Large titles
    - subheading: Section headers
    - body: Regular text
    - mono: Monospace text (for code/output)
    - button: Button labels
    - small: Small captions
    
    Returns:
        Dictionary mapping font names to (family, size, weight) tuples
    """
    system = platform.system()
    
    if system == "Darwin":  # macOS
        return {
            'heading': ('SF Pro Display', 24, 'bold'),
            'subheading': ('SF Pro Display', 14, 'bold'),
            'body': ('SF Pro Text', 11),
            'body_bold': ('SF Pro Text', 11, 'bold'),
            'mono': ('SF Mono', 10),
            'button': ('SF Pro Text', 11, 'bold'),
            'small': ('SF Pro Text', 9),
        }
    elif system == "Windows":
        return {
            'heading': ('Segoe UI', 22, 'bold'),
            'subheading': ('Segoe UI', 13, 'bold'),
            'body': ('Segoe UI', 10),
            'body_bold': ('Segoe UI', 10, 'bold'),
            'mono': ('Consolas', 10),
            'button': ('Segoe UI', 10, 'bold'),
            'small': ('Segoe UI', 9),
        }
    else:  # Linux and others
        return {
            'heading': ('Ubuntu', 22, 'bold'),
            'subheading': ('Ubuntu', 13, 'bold'),
            'body': ('Ubuntu', 10),
            'body_bold': ('Ubuntu', 10, 'bold'),
            'mono': ('Ubuntu Mono', 10),
            'button': ('Ubuntu', 10, 'bold'),
            'small': ('Ubuntu', 9),
        }


# Export fonts function from Theme class for convenience
Theme.get_fonts = staticmethod(get_fonts)
