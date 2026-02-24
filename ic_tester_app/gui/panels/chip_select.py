# ic_tester_app/gui/panels/chip_select.py
# Last edited: 2026-01-19
# Purpose: Chip selection panel with dropdown and test controls
# Dependencies: tkinter, ttk

"""
Chip Selection Panel module.
Provides chip selection dropdown, chip info display, and test buttons.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

from ..theme import Theme, get_fonts
from ..widgets import ModernButton
from ...logger import get_logger

logger = get_logger("gui.panels.chip_select")


class ChipPanel:
    """
    Chip selection and test control panel.
    
    Provides:
    - Chip selection dropdown
    - Chip info display
    - Run Test button
    - Run Counter button (for counter chips)
    - Stop button (for counter mode)
    """
    
    def __init__(self, parent, chip_ids: List[str],
                 on_chip_selected: Callable,
                 on_run_test: Callable,
                 on_run_counter: Callable,
                 on_stop: Callable,
                 board: str = "MEGA",
                 **kwargs):
        self.parent = parent
        self.chip_ids = chip_ids
        self.on_chip_selected = on_chip_selected
        self.on_run_test = on_run_test
        self.on_run_counter = on_run_counter
        self.on_stop = on_stop
        self.board = str(board).upper()
        self.fonts = get_fonts()
        
        self._create_panel()
        logger.debug("ChipPanel initialized")
    
    def _create_panel(self):
        """Build the panel UI"""
        # Card container
        self.frame = tk.Frame(self.parent, bg=Theme.BG_CARD, padx=18, pady=18)
        self.frame.pack(fill=tk.X, pady=(0, 12))
        
        # Title
        tk.Label(self.frame, text="Chip Selection", 
                font=self.fonts['subheading'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY).pack(anchor=tk.W, pady=(0, 12))
        
        # Chip dropdown row
        chip_row = tk.Frame(self.frame, bg=Theme.BG_CARD)
        chip_row.pack(fill=tk.X, pady=(0, 12))
        
        tk.Label(chip_row, text="Chip:", font=self.fonts['body'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY, width=6,
                anchor=tk.W).pack(side=tk.LEFT)
        
        self.chip_var = tk.StringVar()
        self.chip_combo = ttk.Combobox(chip_row, textvariable=self.chip_var,
                                       state='readonly', width=22)
        self.chip_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.chip_combo['values'] = self.chip_ids
        
        # Chip info label
        self.chip_info = tk.Label(self.frame, text="", font=self.fonts['small'],
                                 bg=Theme.BG_CARD, fg=Theme.TEXT_MUTED,
                                 wraplength=280, justify=tk.LEFT)
        self.chip_info.pack(anchor=tk.W, pady=(0, 10))
        
        # Setup selection handling
        if self.chip_ids:
            self.chip_combo.current(0)
            self.chip_combo.bind('<<ComboboxSelected>>', self._on_selection_changed)
        else:
            self.chip_info.config(
                text="⚠️ No chips loaded!\nAdd JSON files in 'chips/' folder.",
                fg=Theme.ACCENT_WARNING
            )
        
        # Button row
        btn_row = tk.Frame(self.frame, bg=Theme.BG_CARD)
        btn_row.pack(fill=tk.X, pady=(0, 10))
        
        # Run Test button
        self.test_btn = ModernButton(btn_row, "▶  Run Test", self.on_run_test,
                    width=120, height=40, 
                    bg_color=Theme.ACCENT_SUCCESS,
                    hover_color="#05c493")
        self.test_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Run Counter button (for counter chips)
        self.run_counter_btn = ModernButton(btn_row, "⏱  Counter", self.on_run_counter,
                    width=100, height=40, 
                    bg_color=Theme.ACCENT_INFO,
                    hover_color="#0099cc")
        
        # Stop button (hidden initially)
        self.stop_btn = ModernButton(btn_row, "⏹  Stop", self.on_stop,
                    width=80, height=40, 
                    bg_color=Theme.ACCENT_ERROR,
                    hover_color="#cc3333")
        
        # Counter display
        self.counter_display = tk.Label(self.frame, text="", 
                                        font=self.fonts['mono'],
                                        bg=Theme.BG_CARD, fg=Theme.ACCENT_PRIMARY)
    
    def _on_selection_changed(self, event):
        """Handle chip selection change"""
        if self.on_chip_selected:
            self.on_chip_selected(self.chip_var.get())
    
    def get_selected_chip(self) -> str:
        """Get the currently selected chip ID"""
        return self.chip_var.get()
    
    def set_board(self, board: str):
        self.board = str(board or "MEGA").upper()
    
    def get_board(self) -> str:
        return self.board
    
    def set_chip_ids(self, chip_ids: List[str]):
        self.chip_ids = sorted(chip_ids)
        self.chip_combo["values"] = self.chip_ids
        if self.chip_ids:
            self.chip_combo.current(0)
            if self.on_chip_selected:
                self.on_chip_selected(self.chip_var.get())
        else:
            self.chip_var.set("")
            self.chip_info.config(
                text="⚠️ No chips available.",
                fg=Theme.ACCENT_WARNING
            )
    
    def set_chip_info(self, name: str, description: str):
        """Update the chip info display."""
        text = f"{name}\n{description[:100]}..."
        self.chip_info.config(text=text, fg=Theme.TEXT_MUTED)
    
    def show_counter_button(self, show: bool):
        """Show or hide the counter button"""
        if show:
            self.run_counter_btn.pack(side=tk.LEFT)
        else:
            self.run_counter_btn.pack_forget()
            self.counter_display.pack_forget()
            self.counter_display.config(text="")
    
    def set_counter_running(self, running: bool):
        """Update UI for counter running state"""
        if running:
            self.run_counter_btn.pack_forget()
            self.stop_btn.pack(side=tk.LEFT)
            self.counter_display.pack(pady=(5, 0))
        else:
            self.stop_btn.pack_forget()
            self.run_counter_btn.pack(side=tk.LEFT)
            self.counter_display.config(text="")
    
    def update_counter_display(self, value: str):
        """Update the counter display value"""
        self.counter_display.config(text=value)
    
    def set_testing(self, testing: bool):
        """Update button state for testing - show stop button when running"""
        if testing:
            self.test_btn.draw_button(Theme.TEXT_MUTED)
            self.stop_btn.pack(side=tk.LEFT, padx=(10, 0))
        else:
            self.test_btn.draw_button(Theme.ACCENT_SUCCESS)
            self.stop_btn.pack_forget()
