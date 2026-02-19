# ic_tester_app/gui/panels/connection.py
# Last edited: 2026-01-19
# Purpose: Arduino connection panel with port selection and connect/disconnect controls
# Dependencies: tkinter, ttk

"""
Connection Panel module.
Provides Arduino port scanning, selection, and connection management.
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
        # Card container with more padding
        self.frame = tk.Frame(self.parent, bg=Theme.BG_CARD, padx=18, pady=18)
        self.frame.pack(fill=tk.X, pady=(0, 12))
        
        # Title row with scan button on right
        title_row = tk.Frame(self.frame, bg=Theme.BG_CARD)
        title_row.pack(fill=tk.X, pady=(0, 12))
        
        tk.Label(title_row, text="Arduino Connection", 
                font=self.fonts['subheading'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY).pack(side=tk.LEFT)
        
        # Scan button in header for visibility
        ModernButton(title_row, "🔍 Scan", self.on_scan,
                    width=75, height=30, bg_color=Theme.ACCENT_INFO).pack(side=tk.RIGHT)
        
        # Port selection row
        port_row = tk.Frame(self.frame, bg=Theme.BG_CARD)
        port_row.pack(fill=tk.X, pady=(0, 12))
        
        tk.Label(port_row, text="Port:", font=self.fonts['body'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY, width=6, 
                anchor=tk.W).pack(side=tk.LEFT)
        
        # Port dropdown - wider
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(port_row, textvariable=self.port_var,
                                       state='readonly', width=22)
        self.port_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Status row
        status_row = tk.Frame(self.frame, bg=Theme.BG_CARD)
        status_row.pack(fill=tk.X, pady=(0, 15))
        
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
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.current(0)
    
    def get_selected_port(self) -> str:
        """Get the currently selected port name"""
        return self.port_var.get()
    
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
