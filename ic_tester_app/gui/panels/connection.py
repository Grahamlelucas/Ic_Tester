# ic_tester_app/gui/panels/connection.py
# Last edited: 2026-01-19
# Purpose: Arduino connection panel with port selection and connect/disconnect controls
# Dependencies: tkinter, ttk

"""
Arduino connection control panel.

This panel owns the visible connect/disconnect workflow in the sidebar. It does
not talk to serial hardware directly; instead it exposes UI state and delegates
actions to callbacks supplied by the main application coordinator.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from ..theme import Theme, get_fonts
from ..widgets import ModernButton
from ...logger import get_logger

logger = get_logger("gui.panels.connection")


class ConnectionPanel:
    """
    Arduino connection control panel.
    
    Provides:
    - Port scanning and selection dropdown
    - Connect/Disconnect buttons
    - Connection status indicator
    
    Attributes:
        frame: The main frame widget
        port_var: StringVar containing selected port
        on_connect: Callback when connect is clicked
        on_disconnect: Callback when disconnect is clicked
        on_scan: Callback when scan is clicked
    """
    
    def __init__(self, parent, on_connect: Callable, on_disconnect: Callable, 
                 on_scan: Callable):
        """
        Initialize the connection panel.
        
        Args:
            parent: Parent tkinter widget
            on_connect: Callback for connect button
            on_disconnect: Callback for disconnect button
            on_scan: Callback for scan button
        """
        self.parent = parent
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.on_scan = on_scan
        self.fonts = get_fonts()
        
        self._create_panel()
        logger.debug("ConnectionPanel initialized")
    
    def _create_panel(self):
        """Build the panel UI with improved spacing"""
        # Card container with the panel's full layout. Each row reflects one
        # stage of the connection workflow: scan, choose port, inspect status,
        # then connect/disconnect.
        self.frame = tk.Frame(self.parent, bg=Theme.BG_CARD, padx=18, pady=18)
        self.frame.pack(fill=tk.X, pady=(0, 12))
        
        # Title row
        title_row = tk.Frame(self.frame, bg=Theme.BG_CARD)
        title_row.pack(fill=tk.X, pady=(0, 12))
        
        tk.Label(title_row, text="Arduino Connection", 
                font=self.fonts['subheading'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY).pack(side=tk.LEFT)
        
        # Scan button row
        scan_row = tk.Frame(self.frame, bg=Theme.BG_CARD)
        scan_row.pack(fill=tk.X, pady=(0, 12))
        
        ModernButton(scan_row, "🔍 Scan Ports", self.on_scan,
                    width=120, height=32, bg_color=Theme.ACCENT_INFO).pack(fill=tk.X)
        
        # Port selection row
        port_row = tk.Frame(self.frame, bg=Theme.BG_CARD)
        port_row.pack(fill=tk.X, pady=(0, 12))
        
        tk.Label(port_row, text="Port:", font=self.fonts['body'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY, width=6, 
                anchor=tk.W).pack(side=tk.LEFT)
        
        # Port dropdown
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(port_row, textvariable=self.port_var,
                                       state='readonly', width=22)
        self.port_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Status row
        status_row = tk.Frame(self.frame, bg=Theme.BG_CARD)
        status_row.pack(fill=tk.X, pady=(0, 12))
        
        tk.Label(status_row, text="Status:", font=self.fonts['body'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY, width=6,
                anchor=tk.W).pack(side=tk.LEFT)
        
        # Status dot (canvas circle)
        self.status_dot = tk.Canvas(status_row, width=14, height=14, 
                                    bg=Theme.BG_CARD, highlightthickness=0)
        self.status_dot.pack(side=tk.LEFT, padx=(0, 8))
        self.status_dot.create_oval(2, 2, 12, 12, fill=Theme.DISCONNECTED, outline="")
        
        # Status text
        self.conn_status = tk.Label(status_row, text="Disconnected", 
                                   font=self.fonts['body'],
                                   bg=Theme.BG_CARD, fg=Theme.DISCONNECTED)
        self.conn_status.pack(side=tk.LEFT)
        
        # Board details stay hidden until a successful handshake tells us what
        # hardware is actually attached.
        self.board_info_row = tk.Frame(self.frame, bg=Theme.BG_CARD)
        
        tk.Label(self.board_info_row, text="Board:", font=self.fonts['body'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY, width=6,
                anchor=tk.W).pack(side=tk.LEFT)
        
        self.board_label = tk.Label(self.board_info_row, text="", 
                                   font=self.fonts['body_bold'],
                                   bg=Theme.BG_CARD, fg=Theme.ACCENT_PRIMARY)
        self.board_label.pack(side=tk.LEFT)
        
        self.pin_info_label = tk.Label(self.board_info_row, text="", 
                                      font=self.fonts['small'],
                                      bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY)
        self.pin_info_label.pack(side=tk.LEFT, padx=(8, 0))
        
        # Button row - full width buttons
        btn_row = tk.Frame(self.frame, bg=Theme.BG_CARD)
        btn_row.pack(fill=tk.X)
        
        # Connect button (shown when disconnected)
        self.connect_btn = ModernButton(btn_row, "Connect", self.on_connect,
                    width=120, height=38, bg_color=Theme.ACCENT_PRIMARY)
        self.connect_btn.pack(side=tk.LEFT, expand=True, fill=tk.X)
        
        # Disconnect button (hidden initially, shown when connected)
        self.disconnect_btn = ModernButton(btn_row, "Disconnect", self.on_disconnect,
                    width=120, height=38, bg_color=Theme.ACCENT_ERROR)
        # Don't pack yet - will be shown when connected
    
    def set_ports(self, ports: list):
        """
        Update the port dropdown with available ports.
        
        Args:
            ports: List of port names to display
        """
        # Replace the dropdown contents after a scan. If ports exist, preselect
        # the first one so the common classroom case is one click shorter.
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.current(0)
    
    def get_selected_port(self) -> str:
        """Get the currently selected port name"""
        return self.port_var.get()
    
    def set_board_info(self, board_type: str, digital_range: tuple, analog_range: tuple):
        """Update board information display.
        
        Args:
            board_type: Board type string (e.g., 'MEGA2560', 'UNO_R3')
            digital_range: Tuple of (min, max) digital pins
            analog_range: Tuple of (min, max) analog pins
        """
        board_display = board_type.replace("_", " ")
        self.board_label.config(text=board_display)
        
        d_count = digital_range[1] - digital_range[0] + 1
        a_count = analog_range[1] - analog_range[0] + 1
        pin_text = f"({d_count} digital, {a_count} analog pins)"
        self.pin_info_label.config(text=pin_text)
        
        # Reveal the board row only after we have meaningful information to show.
        self.board_info_row.pack(fill=tk.X, pady=(0, 12), before=self.frame.winfo_children()[-1])
        
        # Notify parent to rebind mousewheel events for new widgets
        self.frame.event_generate("<<WidgetsChanged>>")
        
        logger.info(f"Board info displayed: {board_type}")
    
    def set_connected(self):
        """Update UI to show connected state"""
        self.status_dot.delete("all")
        self.status_dot.create_oval(2, 2, 10, 10, fill=Theme.CONNECTED, outline="")
        self.conn_status.config(text="Connected", fg=Theme.CONNECTED)
        
        # Swap buttons
        self.connect_btn.pack_forget()
        self.disconnect_btn.pack(side=tk.LEFT)
        
        # Disable port selection
        self.port_combo.config(state='disabled')
        
        logger.info("UI updated to connected state")
    
    def set_disconnected(self):
        """Update UI to show disconnected state"""
        self.status_dot.delete("all")
        self.status_dot.create_oval(2, 2, 10, 10, fill=Theme.DISCONNECTED, outline="")
        self.conn_status.config(text="Disconnected", fg=Theme.DISCONNECTED)
        
        # Hide board info
        self.board_info_row.pack_forget()
        
        # Swap buttons
        self.disconnect_btn.pack_forget()
        self.connect_btn.pack(side=tk.LEFT)
        
        # Enable port selection
        self.port_combo.config(state='readonly')
        
        logger.info("UI updated to disconnected state")
    
    def set_connecting(self):
        """Update UI to show connecting state"""
        self.status_dot.delete("all")
        self.status_dot.create_oval(2, 2, 10, 10, fill=Theme.PENDING, outline="")
        self.conn_status.config(text="Connecting...", fg=Theme.PENDING)
    
    def set_failed(self):
        """Update UI to show connection failed state"""
        self.status_dot.delete("all")
        self.status_dot.create_oval(2, 2, 10, 10, fill=Theme.DISCONNECTED, outline="")
        self.conn_status.config(text="Failed", fg=Theme.DISCONNECTED)
