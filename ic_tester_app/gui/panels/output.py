# ic_tester_app/gui/panels/output.py
# Last edited: 2026-01-19
# Purpose: Output log panel for displaying test progress and results
# Dependencies: tkinter

"""
Output Panel module.
Displays scrolling log output with color-coded messages for test progress and results.
"""

import tkinter as tk
from tkinter import scrolledtext
from typing import Optional

from ..theme import Theme, get_fonts
from ..widgets import ModernButton
from ...logger import get_logger

logger = get_logger("gui.panels.output")


class OutputPanel:
    """
    Scrolling output log panel with color-coded messages.
    
    Provides:
    - Scrollable text output area
    - Color-coded log levels (info, success, warning, error, header)
    - Clear and Identify buttons
    - Auto-scroll to bottom on new messages
    
    Attributes:
        frame: The main frame widget
        output_text: ScrolledText widget for log display
    """
    
    def __init__(self, parent, on_clear: callable):
        """
        Initialize the output panel.
        
        Args:
            parent: Parent tkinter widget
            on_clear: Callback for clear button
        """
        self.parent = parent
        self.on_clear = on_clear
        self.fonts = get_fonts()
        
        self._create_panel()
        logger.debug("OutputPanel initialized")
    
    def _create_panel(self):
        """Build the panel UI"""
        # Card container
        self.frame = tk.Frame(self.parent, bg=Theme.BG_CARD, padx=15, pady=15)
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Header with title and buttons
        header = tk.Frame(self.frame, bg=Theme.BG_CARD)
        header.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(header, text="Output Log", font=self.fonts['subheading'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY).pack(side=tk.LEFT)
        
        # Button row
        ModernButton(header, "Clear Log", self.on_clear,
                    width=80, height=32, bg_color=Theme.BG_LIGHT).pack(side=tk.RIGHT, padx=(5, 0))
        
        ModernButton(header, "Copy All", self._copy_all,
                    width=80, height=32, bg_color=Theme.ACCENT_INFO).pack(side=tk.RIGHT)
        
        # Output text area with custom styling
        self.output_text = scrolledtext.ScrolledText(
            self.frame,
            font=self.fonts['mono'],
            bg=Theme.BG_DARK,
            fg=Theme.TEXT_PRIMARY,
            relief=tk.FLAT,
            padx=10,
            pady=10,
            wrap=tk.WORD,
            cursor="arrow",
            insertbackground=Theme.TEXT_PRIMARY
        )
        self.output_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure color tags for different message types
        self._configure_tags()
        
        # Make read-only but allow selection
        self.output_text.bind("<Key>", lambda e: "break" if e.keysym not in ['c', 'C'] else None)
    
    def _configure_tags(self):
        """Configure text tags for color-coded output"""
        # Success messages (green)
        self.output_text.tag_configure("success", foreground=Theme.ACCENT_SUCCESS)
        
        # Error messages (red)
        self.output_text.tag_configure("error", foreground=Theme.ACCENT_ERROR)
        
        # Warning messages (yellow)
        self.output_text.tag_configure("warning", foreground=Theme.ACCENT_WARNING)
        
        # Info messages (blue)
        self.output_text.tag_configure("info", foreground=Theme.ACCENT_INFO)
        
        # Header messages (primary color, bold effect via different color)
        self.output_text.tag_configure("header", foreground=Theme.ACCENT_PRIMARY)
        
        # Debug messages (muted)
        self.output_text.tag_configure("debug", foreground=Theme.TEXT_MUTED)
    
    def log(self, message: str, level: Optional[str] = None):
        """
        Add a message to the output log.
        
        Args:
            message: Message text to display
            level: Message level for color coding:
                   'success', 'error', 'warning', 'info', 'header', 'debug', or None
        """
        self.output_text.configure(state=tk.NORMAL)
        
        if level:
            self.output_text.insert(tk.END, message + "\n", level)
        else:
            self.output_text.insert(tk.END, message + "\n")
        
        # Auto-scroll to bottom
        self.output_text.see(tk.END)
        self.output_text.configure(state=tk.DISABLED)
    
    def clear(self):
        """Clear all output text"""
        self.output_text.configure(state=tk.NORMAL)
        self.output_text.delete(1.0, tk.END)
        self.output_text.configure(state=tk.DISABLED)
        logger.debug("Output cleared")
    
    def get_text(self) -> str:
        """Get all text from the output log"""
        return self.output_text.get(1.0, tk.END)
    
    def _copy_all(self):
        """Copy all log text to clipboard"""
        text = self.get_text().strip()
        if text:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(text)
            self.log("📋 Log copied to clipboard!", "success")
            logger.debug(f"Copied {len(text)} characters to clipboard")
        else:
            self.log("⚠️ Nothing to copy", "warning")
    
    def log_separator(self, char: str = "═", length: int = 50):
        """Log a separator line"""
        self.log(char * length, "header")
    
    def log_test_start(self, chip_id: str):
        """Log test start header"""
        self.log("")
        self.log_separator()
        self.log(f"  TESTING: {chip_id}", "header")
        self.log_separator()
    
    def log_test_result(self, passed: bool):
        """Log test result"""
        if passed:
            self.log("  ✅ PASS", "success")
        else:
            self.log("  ❌ FAIL", "error")
    
    def log_test_complete(self, results: dict):
        """Log test completion summary"""
        self.log("")
        self.log("─" * 50)
        self.log("TEST RESULTS", "header")
        self.log("─" * 50)
        
        self.log(f"Chip: {results.get('chipName', 'Unknown')} ({results.get('chipId', '')})")
        self.log(f"Tests Run: {results.get('testsRun', 0)}")
        self.log(f"Passed: {results.get('testsPassed', 0)}", "success")
        
        failed = results.get('testsFailed', 0)
        self.log(f"Failed: {failed}", "error" if failed > 0 else None)
        
        if results.get('success'):
            self.log("\n🎉 CHIP PASSED ALL TESTS! ✅", "success")
        else:
            self.log("\n❌ CHIP FAILED - See details above", "error")
        
        self.log_separator()
