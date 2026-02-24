# ic_tester_app/gui/panels/status.py
# Last edited: 2026-01-19
# Purpose: Test result status panel with visual indicator and statistics
# Dependencies: tkinter

"""
Status Panel module.
Displays test results with a large visual indicator and test statistics.
"""

import tkinter as tk
from typing import Dict

from ..theme import Theme, get_fonts
from ..widgets import StatusIndicator
from ...logger import get_logger

logger = get_logger("gui.panels.status")


class StatusPanel:
    """
    Test result status display panel.
    
    Provides:
    - Large visual pass/fail/testing indicator
    - Result text description
    - Test statistics (passed, failed, total)
    
    Attributes:
        frame: The main frame widget
        indicator: StatusIndicator widget
    """
    
    def __init__(self, parent):
        """
        Initialize the status panel.
        
        Args:
            parent: Parent tkinter widget
        """
        self.parent = parent
        self.fonts = get_fonts()
        
        self._create_panel()
        logger.debug("StatusPanel initialized")
    
    def _create_panel(self):
        """Build the panel UI with improved spacing"""
        # Card container with more padding
        self.frame = tk.Frame(self.parent, bg=Theme.BG_CARD, padx=18, pady=18)
        self.frame.pack(fill=tk.X, pady=(0, 12))
        
        # Title
        tk.Label(self.frame, text="Test Result", 
                font=self.fonts['subheading'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY).pack(anchor=tk.W, pady=(0, 10))
        
        # Center the status indicator
        indicator_frame = tk.Frame(self.frame, bg=Theme.BG_CARD, height=100, width=100)
        indicator_frame.pack(pady=10)
        indicator_frame.pack_propagate(False)
        
        self.indicator = StatusIndicator(indicator_frame, size=80)
        self.indicator.place(relx=0.5, rely=0.5, anchor="center")
        
        # Status text
        self.result_text = tk.Label(self.frame, text="Ready to test",
                                   font=self.fonts['subheading'],
                                   bg=Theme.BG_CARD, fg=Theme.TEXT_MUTED)
        self.result_text.pack(pady=(10, 0))
        
        # Stats row
        stats_frame = tk.Frame(self.frame, bg=Theme.BG_CARD)
        stats_frame.pack(fill=tk.X, pady=(15, 0))
        
        # Passed stat
        passed_frame = tk.Frame(stats_frame, bg=Theme.BG_CARD)
        passed_frame.pack(side=tk.LEFT, expand=True)
        tk.Label(passed_frame, text="Passed", font=self.fonts['small'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_MUTED).pack()
        self.passed_stat = tk.Label(passed_frame, text="0", 
                                   font=self.fonts['subheading'],
                                   bg=Theme.BG_CARD, fg=Theme.ACCENT_SUCCESS)
        self.passed_stat.pack()
        
        # Failed stat
        failed_frame = tk.Frame(stats_frame, bg=Theme.BG_CARD)
        failed_frame.pack(side=tk.LEFT, expand=True)
        tk.Label(failed_frame, text="Failed", font=self.fonts['small'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_MUTED).pack()
        self.failed_stat = tk.Label(failed_frame, text="0", 
                                   font=self.fonts['subheading'],
                                   bg=Theme.BG_CARD, fg=Theme.ACCENT_ERROR)
        self.failed_stat.pack()
        
        # Total stat
        total_frame = tk.Frame(stats_frame, bg=Theme.BG_CARD)
        total_frame.pack(side=tk.LEFT, expand=True)
        tk.Label(total_frame, text="Total", font=self.fonts['small'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_MUTED).pack()
        self.total_stat = tk.Label(total_frame, text="0", 
                                  font=self.fonts['subheading'],
                                  bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY)
        self.total_stat.pack()
    
    def set_idle(self):
        """Set status to idle/ready state"""
        self.indicator.set_idle()
        self.result_text.config(text="Ready to test", fg=Theme.TEXT_MUTED)
    
    def set_testing(self):
        """Set status to testing in progress"""
        self.indicator.set_testing()
        self.result_text.config(text="Testing...", fg=Theme.ACCENT_WARNING)
    
    def set_passed(self):
        """Set status to all tests passed"""
        self.indicator.set_passed()
        self.result_text.config(text="ALL TESTS PASSED", fg=Theme.ACCENT_SUCCESS)
    
    def set_failed(self):
        """Set status to tests failed"""
        self.indicator.set_failed()
        self.result_text.config(text="TESTS FAILED", fg=Theme.ACCENT_ERROR)
    
    def set_pin_error(self):
        """Set status to pin connection error"""
        self.indicator.set_failed()
        self.result_text.config(text="PIN ERROR", fg=Theme.ACCENT_ERROR)
    
    def set_test_error(self):
        """Set status to test error"""
        self.indicator.set_failed()
        self.result_text.config(text="TEST ERROR", fg=Theme.ACCENT_ERROR)
    
    def set_custom_text(self, text: str, color: str = None):
        """Set custom result text"""
        self.result_text.config(text=text, fg=color or Theme.TEXT_MUTED)
    
    def update_stats(self, passed: int, failed: int, total: int):
        """
        Update the test statistics display.
        
        Args:
            passed: Number of tests passed
            failed: Number of tests failed
            total: Total number of tests run
        """
        self.passed_stat.config(text=str(passed))
        self.failed_stat.config(text=str(failed))
        self.total_stat.config(text=str(total))
    
    def reset_stats(self):
        """Reset all statistics to zero"""
        self.update_stats(0, 0, 0)
    
    def update_from_results(self, results: Dict):
        """
        Update panel from test results dictionary.
        
        Args:
            results: Test results dictionary with keys:
                     testsPassed, testsFailed, testsRun, success
        """
        passed = results.get('testsPassed', 0)
        failed = results.get('testsFailed', 0)
        total = results.get('testsRun', 0)
        
        self.update_stats(passed, failed, total)
        
        if results.get('success'):
            self.set_passed()
        else:
            self.set_failed()
