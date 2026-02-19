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
    
    Attributes:
        frame: The main frame widget
        chip_var: StringVar containing selected chip ID
        on_chip_selected: Callback when chip selection changes
        on_run_test: Callback for run test button
        on_run_counter: Callback for run counter button
        on_stop: Callback for stop button
    """
    
    def __init__(self, parent, chip_ids: List[str],
                 on_chip_selected: Callable,
                 on_run_test: Callable,
                 on_run_counter: Callable,
                 on_stop: Callable,
                 on_source_changed: Optional[Callable] = None,
                 on_load_workbook: Optional[Callable] = None,
                 on_open_workbook: Optional[Callable] = None,
                 on_sync_json_to_excel: Optional[Callable] = None,
                 on_export_results: Optional[Callable] = None,
                 board: str = "MEGA",
                 source_mode: str = "hybrid"):
        """
        Initialize the chip panel.
        
        Args:
            parent: Parent tkinter widget
            chip_ids: List of available chip IDs
            on_chip_selected: Callback when chip selection changes
            on_run_test: Callback for run test button
            on_run_counter: Callback for counter button
            on_stop: Callback for stop button
        """
        self.parent = parent
        self.chip_ids = chip_ids
        self.on_chip_selected = on_chip_selected
        self.on_run_test = on_run_test
        self.on_run_counter = on_run_counter
        self.on_stop = on_stop
        self.on_source_changed = on_source_changed
        self.on_load_workbook = on_load_workbook
        self.on_open_workbook = on_open_workbook
        self.on_sync_json_to_excel = on_sync_json_to_excel
        self.on_export_results = on_export_results
        self.board = str(board).upper()
        self.source_mode = str(source_mode or "hybrid")
        self.fonts = get_fonts()
        
        self._create_panel()
        logger.debug("ChipPanel initialized")
    
    def _create_panel(self):
        """Build the panel UI with improved spacing"""
        # Card container with more padding
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
        
        # Source and board controls
        source_row = tk.Frame(self.frame, bg=Theme.BG_CARD)
        source_row.pack(fill=tk.X, pady=(0, 8))
        
        tk.Label(source_row, text="Source:", font=self.fonts['small'],
                 bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY, width=7,
                 anchor=tk.W).pack(side=tk.LEFT)
        
        self.source_var = tk.StringVar(value=self._display_source(self.source_mode))
        self.source_combo = ttk.Combobox(
            source_row,
            textvariable=self.source_var,
            state='readonly',
            width=9,
            values=["JSON", "Excel", "Hybrid"]
        )
        self.source_combo.pack(side=tk.LEFT, padx=(0, 8))
        self.source_combo.bind('<<ComboboxSelected>>', self._on_source_changed)
        
        tk.Label(source_row, text="Board:", font=self.fonts['small'],
                 bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY).pack(side=tk.LEFT, padx=(4, 4))
        self.board_value_label = tk.Label(
            source_row,
            text=self.board,
            font=self.fonts['small'],
            bg=Theme.BG_CARD,
            fg=Theme.ACCENT_INFO
        )
        self.board_value_label.pack(side=tk.LEFT)
        
        tool_row = tk.Frame(self.frame, bg=Theme.BG_CARD)
        tool_row.pack(fill=tk.X, pady=(0, 8))
        ModernButton(
            tool_row,
            "Load Workbook",
            self._on_load_workbook_clicked,
            width=115,
            height=30,
            bg_color=Theme.ACCENT_INFO
        ).pack(side=tk.LEFT, padx=(0, 8))
        
        ModernButton(
            tool_row,
            "Open Workbook",
            self._on_open_workbook_clicked,
            width=115,
            height=30,
            bg_color=Theme.BG_LIGHT
        ).pack(side=tk.LEFT, padx=(0, 8))
        
        ModernButton(
            tool_row,
            "Export Results",
            self._on_export_results_clicked,
            width=115,
            height=30,
            bg_color=Theme.ACCENT_PRIMARY
        ).pack(side=tk.LEFT, padx=(0, 8))
        
        ModernButton(
            tool_row,
            "Sync JSON->Excel",
            self._on_sync_json_to_excel_clicked,
            width=130,
            height=30,
            bg_color=Theme.ACCENT_WARNING
        ).pack(side=tk.LEFT)
        
        # Chip info label - wider wrapping
        self.chip_info = tk.Label(self.frame, text="", font=self.fonts['small'],
                                 bg=Theme.BG_CARD, fg=Theme.TEXT_MUTED,
                                 wraplength=280, justify=tk.LEFT)
        self.chip_info.pack(anchor=tk.W, pady=(0, 10))
        
        # External power checkbox
        self.external_power_var = tk.BooleanVar(value=True)  # Default ON
        self.external_power_cb = tk.Checkbutton(
            self.frame, 
            text="🔋 External Power Supply",
            variable=self.external_power_var,
            font=self.fonts['small'],
            bg=Theme.BG_CARD, 
            fg=Theme.ACCENT_INFO,
            activebackground=Theme.BG_CARD,
            activeforeground=Theme.ACCENT_INFO,
            selectcolor=Theme.BG_DARK
        )
        self.external_power_cb.pack(anchor=tk.W, pady=(0, 12))
        
        # Setup selection handling
        if self.chip_ids:
            self.chip_combo.current(0)
            self.chip_combo.bind('<<ComboboxSelected>>', self._on_selection_changed)
        else:
            self.chip_info.config(
                text="⚠️ No chips loaded!\nLoad Excel workbook or add JSON files in 'chips/' folder.",
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
        # Don't pack initially - shown for counter chips only
        
        # Stop button (hidden initially)
        self.stop_btn = ModernButton(btn_row, "⏹  Stop", self.on_stop,
                    width=80, height=40, 
                    bg_color=Theme.ACCENT_ERROR,
                    hover_color="#cc3333")
        # Don't pack yet - shown when counter is running
        
        # Counter display
        self.counter_display = tk.Label(self.frame, text="", 
                                        font=self.fonts['mono'],
                                        bg=Theme.BG_CARD, fg=Theme.ACCENT_PRIMARY)
        # Don't pack yet - shown when counter is running
    
    def _on_selection_changed(self, event):
        """Handle chip selection change"""
        if self.on_chip_selected:
            self.on_chip_selected(self.chip_var.get())
    
    def _on_source_changed(self, event):
        if self.on_source_changed:
            self.on_source_changed(self.get_source_mode())
    
    def _on_load_workbook_clicked(self):
        if self.on_load_workbook:
            self.on_load_workbook()
    
    def _on_export_results_clicked(self):
        if self.on_export_results:
            self.on_export_results()
    
    def _on_open_workbook_clicked(self):
        if self.on_open_workbook:
            self.on_open_workbook()
    
    def _on_sync_json_to_excel_clicked(self):
        if self.on_sync_json_to_excel:
            self.on_sync_json_to_excel()
    
    def get_selected_chip(self) -> str:
        """Get the currently selected chip ID"""
        return self.chip_var.get()
    
    def get_source_mode(self) -> str:
        value = self.source_var.get().strip().lower()
        if value == "excel":
            return "excel"
        if value == "json":
            return "json"
        return "hybrid"
    
    def set_source_mode(self, source_mode: str):
        self.source_var.set(self._display_source(source_mode))
    
    def _display_source(self, source_mode: str) -> str:
        mode = str(source_mode or "hybrid").strip().lower()
        if mode == "excel":
            return "Excel"
        if mode == "json":
            return "JSON"
        return "Hybrid"
    
    def set_board(self, board: str):
        self.board = str(board or "MEGA").upper()
        self.board_value_label.config(text=self.board)
    
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
                text="⚠️ No chips available for selected source/board.",
                fg=Theme.ACCENT_WARNING
            )
    
    def set_chip_info(self, name: str, description: str):
        """
        Update the chip info display.
        
        Args:
            name: Chip name
            description: Chip description (will be truncated)
        """
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
    
    def is_external_power(self) -> bool:
        """Check if external power mode is enabled"""
        return self.external_power_var.get()
