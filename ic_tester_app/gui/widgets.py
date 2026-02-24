# ic_tester_app/gui/widgets.py
# Last edited: 2026-01-19
# Purpose: Reusable custom GUI widgets (buttons, indicators, dialogs)
# Dependencies: tkinter

"""
Custom GUI widgets for IC Tester application.

This module provides:
- StatusIndicator: Large visual pass/fail/testing indicator
- ModernButton: Styled button with hover effects
- HelpDialog: Documentation and help dialog
"""

import tkinter as tk
from tkinter import scrolledtext
from typing import Callable, Optional

from .theme import Theme, get_fonts


class StatusIndicator(tk.Canvas):
    """
    Large visual status indicator with animated icons.
    
    Shows the current test status with distinct visual states:
    - idle: Gray circle with question mark
    - testing: Yellow circle with dots (in progress)
    - passed: Green circle with checkmark
    - failed: Red circle with X
    
    Attributes:
        size: Diameter of the indicator in pixels
        current_state: Current state ('idle', 'testing', 'passed', 'failed')
    """
    
    def __init__(self, parent, size: int = 120, **kwargs):
        """
        Initialize the status indicator.
        
        Args:
            parent: Parent tkinter widget
            size: Diameter of the indicator in pixels
            **kwargs: Additional Canvas arguments
        """
        super().__init__(parent, width=size, height=size, 
                        bg=Theme.BG_CARD, highlightthickness=0, **kwargs)
        self.size = size
        self.center = size // 2
        self.current_state = "idle"
        self.set_idle()
    
    def set_idle(self):
        """Show idle/waiting state - gray circle with question mark"""
        self.current_state = "idle"
        self.delete("all")
        
        padding = 10
        # Draw dashed circle outline
        self.create_oval(padding, padding, self.size - padding, self.size - padding,
                        outline=Theme.TEXT_MUTED, width=3, dash=(5, 3))
        # Draw question mark
        self.create_text(self.center, self.center, text="?", 
                        font=('Arial', 40, 'bold'), fill=Theme.TEXT_MUTED)
    
    def set_testing(self):
        """Show testing in progress - yellow circle with dots"""
        self.current_state = "testing"
        self.delete("all")
        
        padding = 10
        # Draw solid circle
        self.create_oval(padding, padding, self.size - padding, self.size - padding,
                        outline=Theme.ACCENT_WARNING, width=4)
        # Draw loading dots
        self.create_text(self.center, self.center, text="...", 
                        font=('Arial', 40, 'bold'), fill=Theme.ACCENT_WARNING)
    
    def set_passed(self):
        """Show pass state - green circle with checkmark"""
        self.current_state = "passed"
        self.delete("all")
        
        padding = 10
        # Draw filled green circle
        self.create_oval(padding, padding, self.size - padding, self.size - padding,
                        fill=Theme.ACCENT_SUCCESS, outline="")
        # Draw checkmark
        cx, cy = self.center, self.center
        points = [
            cx - 25, cy,
            cx - 8, cy + 20,
            cx + 28, cy - 20
        ]
        self.create_line(points, fill="white", width=8, 
                        capstyle=tk.ROUND, joinstyle=tk.ROUND)
    
    # Alias for set_passed (some code uses set_pass)
    def set_pass(self):
        """Alias for set_passed()"""
        self.set_passed()
    
    def set_failed(self):
        """Show fail state - red circle with X"""
        self.current_state = "failed"
        self.delete("all")
        
        padding = 10
        # Draw filled red circle
        self.create_oval(padding, padding, self.size - padding, self.size - padding,
                        fill=Theme.ACCENT_ERROR, outline="")
        # Draw X
        cx, cy = self.center, self.center
        offset = 22
        self.create_line(cx - offset, cy - offset, cx + offset, cy + offset,
                        fill="white", width=8, capstyle=tk.ROUND)
        self.create_line(cx + offset, cy - offset, cx - offset, cy + offset,
                        fill="white", width=8, capstyle=tk.ROUND)


class ModernButton(tk.Canvas):
    """
    Custom styled button with hover effects.
    
    A canvas-based button that provides:
    - Rounded rectangle shape
    - Configurable colors
    - Hover color change
    - Click callback
    
    Attributes:
        command: Function to call when clicked
        text: Button label text
        bg_color: Background color (normal state)
        hover_color: Background color (hover state)
    """
    
    def __init__(self, parent, text: str, command: Callable, 
                 width: int = 120, height: int = 40,
                 bg_color: Optional[str] = None, 
                 hover_color: Optional[str] = None, 
                 text_color: str = "white", **kwargs):
        """
        Initialize the button.
        
        Args:
            parent: Parent tkinter widget
            text: Button label text
            command: Function to call when clicked
            width: Button width in pixels
            height: Button height in pixels
            bg_color: Background color (default: Theme.ACCENT_PRIMARY)
            hover_color: Hover background color (default: Theme.ACCENT_INFO)
            text_color: Text color (default: white)
            **kwargs: Additional Canvas arguments
        """
        super().__init__(parent, width=width, height=height, 
                        bg=Theme.BG_CARD, highlightthickness=0, **kwargs)
        
        self.command = command
        self.text = text
        self.width = width
        self.height = height
        self.bg_color = bg_color or Theme.ACCENT_PRIMARY
        self.hover_color = hover_color or Theme.ACCENT_INFO
        self.text_color = text_color
        self.fonts = get_fonts()
        
        # Draw initial state
        self.draw_button(self.bg_color)
        
        # Bind events
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
    
    def draw_button(self, color: str):
        """
        Redraw the button with the specified color.
        
        Args:
            color: Fill color for the button background
        """
        self.delete("all")
        
        # Draw rounded rectangle background
        radius = Theme.BUTTON_RADIUS
        self._create_rounded_rect(2, 2, self.width - 2, self.height - 2, radius, color)
        
        # Draw centered text
        self.create_text(self.width // 2, self.height // 2, 
                        text=self.text,
                        font=self.fonts['button'], 
                        fill=self.text_color)
    
    def _create_rounded_rect(self, x1: int, y1: int, x2: int, y2: int, 
                             radius: int, color: str):
        """Create a rounded rectangle using polygon with smooth corners"""
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        self.create_polygon(points, fill=color, smooth=True)
    
    def _on_enter(self, event):
        """Handle mouse enter - show hover color"""
        self.draw_button(self.hover_color)
    
    def _on_leave(self, event):
        """Handle mouse leave - restore normal color"""
        self.draw_button(self.bg_color)
    
    def _on_click(self, event):
        """Handle click - execute command"""
        if self.command:
            self.command()


class HelpDialog:
    """
    Help and documentation dialog with tabbed content.
    
    Provides user documentation organized into tabs:
    - Getting Started: Basic usage instructions
    - Adding Chips: How to add new chip definitions
    - JSON Format: Technical JSON structure reference
    - Troubleshooting: Common problems and solutions
    """
    
    def __init__(self, parent):
        """
        Create and display the help dialog.
        
        Args:
            parent: Parent window (dialog will be centered on this)
        """
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("IC Tester Pro - Help & Documentation")
        self.dialog.geometry("700x550")
        self.dialog.configure(bg=Theme.BG_DARK)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.fonts = get_fonts()
        self._create_dialog()
        
        # Center on parent window
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def _create_dialog(self):
        """Build the dialog UI"""
        # Header
        header = tk.Frame(self.dialog, bg=Theme.BG_DARK, pady=15)
        header.pack(fill=tk.X, padx=20)
        
        tk.Label(header, text="📖 Help & Documentation", 
                font=self.fonts['heading'],
                bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY).pack(side=tk.LEFT)
        
        # Tab buttons
        tab_frame = tk.Frame(self.dialog, bg=Theme.BG_DARK)
        tab_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        self.tabs = {}
        self.tab_buttons = {}
        tab_names = ["Getting Started", "Chip Learning", "Adding Chips", "Troubleshooting"]
        
        for i, name in enumerate(tab_names):
            btn = tk.Label(tab_frame, text=name, font=self.fonts['body'],
                          bg=Theme.BG_LIGHT if i == 0 else Theme.BG_CARD,
                          fg=Theme.TEXT_PRIMARY, padx=15, pady=8, cursor="hand2")
            btn.pack(side=tk.LEFT, padx=(0, 5))
            btn.bind("<Button-1>", lambda e, n=name: self._show_tab(n))
            self.tab_buttons[name] = btn
        
        # Content area
        content_frame = tk.Frame(self.dialog, bg=Theme.BG_CARD, padx=20, pady=20)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        
        self.content_text = scrolledtext.ScrolledText(
            content_frame,
            font=self.fonts['body'],
            bg=Theme.BG_DARK,
            fg=Theme.TEXT_PRIMARY,
            relief=tk.FLAT,
            padx=15,
            pady=15,
            wrap=tk.WORD,
            cursor="arrow"
        )
        self.content_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure text tags for formatting
        self.content_text.tag_configure("h1", 
            font=(self.fonts['heading'][0], 18, 'bold'), 
            foreground=Theme.ACCENT_PRIMARY)
        self.content_text.tag_configure("h2", 
            font=(self.fonts['subheading'][0], 14, 'bold'),
            foreground=Theme.ACCENT_INFO)
        self.content_text.tag_configure("code", 
            font=self.fonts['mono'],
            background=Theme.BG_MEDIUM, 
            foreground=Theme.ACCENT_WARNING)
        self.content_text.tag_configure("highlight", 
            foreground=Theme.ACCENT_SUCCESS)
        
        # Show first tab
        self._show_tab("Getting Started")
        
        # Close button
        close_frame = tk.Frame(self.dialog, bg=Theme.BG_DARK)
        close_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        ModernButton(close_frame, "Close", self.dialog.destroy,
                    width=100, height=36).pack(side=tk.RIGHT)
    
    def _show_tab(self, tab_name: str):
        """Switch to the specified tab"""
        # Update button styles
        for name, btn in self.tab_buttons.items():
            btn.configure(bg=Theme.BG_LIGHT if name == tab_name else Theme.BG_CARD)
        
        # Get and display content
        content = self._get_tab_content(tab_name)
        
        self.content_text.configure(state=tk.NORMAL)
        self.content_text.delete(1.0, tk.END)
        
        for text, tag in content:
            self.content_text.insert(tk.END, text, tag)
        
        self.content_text.configure(state=tk.DISABLED)
    
    def _get_tab_content(self, tab_name: str):
        """
        Get content for each tab as list of (text, tag) tuples.
        
        Args:
            tab_name: Name of the tab to get content for
        
        Returns:
            List of (text, tag) tuples for text widget insertion
        """
        if tab_name == "Getting Started":
            return [
                ("Getting Started with IC Tester Pro\n\n", "h1"),
                ("Welcome! This application helps you test 74-series integrated circuits using an Arduino Mega 2560.\n\n", None),
                
                ("Step 1: Connect Your Arduino\n\n", "h2"),
                ("1. Plug your Arduino Mega 2560 into a USB port\n", None),
                ("2. Upload the IC Tester sketch via Arduino IDE\n", None),
                ("3. Close the Arduino IDE (it blocks the serial port)\n", None),
                ("4. Click ", None), ("Scan", "code"), (" to find your Arduino\n", None),
                ("5. Select the correct port and click ", None), ("Connect", "code"), ("\n\n", None),
                
                ("Step 2: Configure Pin Mapping\n\n", "h2"),
                ("1. Select your chip from the dropdown\n", None),
                ("2. In the Pin Mapping panel, enter Arduino pin for each chip pin\n", None),
                ("3. VCC and GND are auto-marked as 'PWR'\n", None),
                ("4. Click ", None), ("Validate", "code"), (" to check your mapping\n", None),
                ("5. Optionally ", None), ("Save", "code"), (" your mapping for reuse\n\n", None),
                
                ("Step 3: Run the Test\n\n", "h2"),
                ("1. Click ", None), ("▶ Run Test", "highlight"), ("\n", None),
                ("2. Watch the status indicator for results:\n", None),
                ("   • ", None), ("Green ✓", "highlight"), (" = All tests passed\n", None),
                ("   • Red ✗ = One or more tests failed\n\n", None),
                
                ("The output panel shows detailed results for each test step.\n", None),
            ]
        
        elif tab_name == "Chip Learning":
            return [
                ("Learning About 74-Series Chips\n\n", "h1"),
                ("IC Tester Pro includes an intelligent learning system to help you understand chips better.\n\n", None),
                
                ("Chip Families\n\n", "h2"),
                ("74-series chips are organized into families:\n\n", None),
                ("• ", None), ("Logic Gates", "highlight"), (" (7400, 7404, 7408, 7432) - Basic building blocks\n", None),
                ("• ", None), ("Flip-Flops", "highlight"), (" (7474, 7475) - Memory elements\n", None),
                ("• ", None), ("Counters", "highlight"), (" (7490, 7493) - Count pulses\n", None),
                ("• ", None), ("Decoders", "highlight"), (" (74138, 74139) - Convert binary to outputs\n", None),
                ("• ", None), ("Shift Registers", "highlight"), (" (74595) - Serial to parallel\n\n", None),
                
                ("Recommended Learning Path\n\n", "h2"),
                ("1. Start with ", None), ("7404", "code"), (" (Inverter) - Simplest chip\n", None),
                ("2. Try ", None), ("7400", "code"), (" (NAND Gate) - Universal gate\n", None),
                ("3. Move to ", None), ("7408", "code"), (" (AND) and ", None), ("7432", "code"), (" (OR)\n", None),
                ("4. Learn ", None), ("7474", "code"), (" (D Flip-Flop) - Basic memory\n", None),
                ("5. Advance to ", None), ("7490", "code"), (" or ", None), ("7493", "code"), (" (Counters)\n\n", None),
                
                ("Key Concepts\n\n", "h2"),
                ("• ", None), ("Truth Tables", "highlight"), (" - Show all input/output combinations\n", None),
                ("• ", None), ("Edge Triggering", "highlight"), (" - Responds to signal transitions\n", None),
                ("• ", None), ("Active Low", "highlight"), (" - Signal is 'on' when LOW\n", None),
                ("• ", None), ("Floating Inputs", "highlight"), (" - Unconnected inputs cause problems\n\n", None),
                
                ("Intelligence Features\n\n", "h2"),
                ("The app learns from your testing:\n", None),
                ("• Tracks your success rate with each chip\n", None),
                ("• Identifies common mistakes you make\n", None),
                ("• Suggests fixes based on failure patterns\n", None),
                ("• Shows confidence scores for results\n", None),
                ("• Celebrates your progress! 🎉\n", None),
            ]
        
        elif tab_name == "Adding Chips":
            return [
                ("Adding New Chip Definitions\n\n", "h1"),
                ("Chip definitions are stored as ", None),
                ("JSON files", "highlight"),
                (" in the ", None), ("chips/", "code"), (" folder.\n\n", None),
                
                ("Quick Start\n\n", "h2"),
                ("1. Create a new ", None), (".json", "code"), (" file in the ", None), ("chips/", "code"), (" folder\n", None),
                ("2. Use an existing chip file as a template\n", None),
                ("3. Restart the app or reload to see the new chip\n\n", None),
                
                ("Required JSON Fields\n\n", "h2"),
                ("• ", None), ("chipId", "code"), (" - The chip's part number\n", None),
                ("• ", None), ("name", "code"), (" - Human-readable name\n", None),
                ("• ", None), ("pinout", "code"), (" - Pin definitions (inputs, outputs, VCC, GND)\n", None),
                ("• ", None), ("arduinoMapping", "code"), (" - Chip pin to Arduino pin mapping\n", None),
                ("• ", None), ("testSequence", "code"), (" - The tests to run\n\n", None),
                
                ("Example JSON Structure\n\n", "h2"),
                ('{\n', "code"),
                ('  "chipId": "7400",\n', "code"),
                ('  "name": "Quad 2-Input NAND",\n', "code"),
                ('  "pinout": {\n', "code"),
                ('    "vcc": 14, "gnd": 7,\n', "code"),
                ('    "inputs": [{"pin": 1, "name": "1A"}],\n', "code"),
                ('    "outputs": [{"pin": 3, "name": "1Y"}]\n', "code"),
                ('  },\n', "code"),
                ('  "arduinoMapping": {"io": {"1": 22}},\n', "code"),
                ('  "testSequence": {"tests": [...]}\n', "code"),
                ('}\n\n', "code"),
                
                ("Tips\n\n", "h2"),
                ("• Check the chip's datasheet for truth tables\n", None),
                ("• Use existing JSON files as templates\n", None),
                ("• The TTL Data Book is a great reference\n", None),
            ]
        
        elif tab_name == "JSON Format":
            return [
                ("Chip Definition JSON Format\n\n", "h1"),
                ("Complete structure for chip definition files:\n\n", None),
                
                ("Basic Structure\n\n", "h2"),
                ('{\n', "code"),
                ('  "chipId": "7490",\n', "code"),
                ('  "name": "Decade Counter",\n', "code"),
                ('  "description": "4-bit decade counter",\n', "code"),
                ('  "pinout": { ... },\n', "code"),
                ('  "testSequence": { ... }\n', "code"),
                ('}\n\n', "code"),
                
                ("Pinout Section\n\n", "h2"),
                ('"pinout": {\n', "code"),
                ('  "vcc": 14,\n', "code"),
                ('  "gnd": 7,\n', "code"),
                ('  "inputs": [\n', "code"),
                ('    {"pin": 1, "name": "A"}\n', "code"),
                ('  ],\n', "code"),
                ('  "outputs": [\n', "code"),
                ('    {"pin": 3, "name": "Y"}\n', "code"),
                ('  ]\n', "code"),
                ('}\n\n', "code"),
                
                ("Test Sequence\n\n", "h2"),
                ('"testSequence": {\n', "code"),
                ('  "tests": [\n', "code"),
                ('    {\n', "code"),
                ('      "testId": 1,\n', "code"),
                ('      "description": "Test description",\n', "code"),
                ('      "inputs": {"A": "HIGH"},\n', "code"),
                ('      "expectedOutputs": {"Y": "LOW"}\n', "code"),
                ('    }\n', "code"),
                ('  ]\n', "code"),
                ('}\n', "code"),
            ]
        
        elif tab_name == "Troubleshooting":
            return [
                ("Troubleshooting Guide\n\n", "h1"),
                
                ("Arduino Not Found\n\n", "h2"),
                ("• Make sure Arduino is plugged in via USB\n", None),
                ("• Close Arduino IDE (it blocks the port)\n", None),
                ("• Try a different USB cable\n", None),
                ("• Click 'Scan' to refresh the port list\n\n", None),
                
                ("Connection Failed\n\n", "h2"),
                ("• Verify the IC Tester sketch is uploaded\n", None),
                ("• Check baud rate is ", None), ("9600", "code"), ("\n", None),
                ("• Try unplugging and replugging the Arduino\n", None),
                ("• Wait 2-3 seconds after plugging in\n\n", None),
                
                ("All Tests Failing\n\n", "h2"),
                ("• Double-check your wiring\n", None),
                ("• Verify VCC (5V) and GND connections\n", None),
                ("• Make sure chip is inserted correctly\n", None),
                ("• Try a known-good chip\n", None),
                ("• Check pin mapping in the GUI\n\n", None),
                
                ("Inconsistent Results\n\n", "h2"),
                ("• Check for loose wires\n", None),
                ("• Add decoupling capacitors near VCC/GND\n", None),
                ("• Avoid long wire runs\n", None),
            ]
        
        return [("No content available.", None)]
