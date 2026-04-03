# ic_tester_app/gui/app.py
# Last edited: 2026-03-19
# Purpose: Main GUI application class that integrates all panels and coordinates testing
# Dependencies: tkinter, threading
# Related: diagnostics/, intelligence/ml_classifier.py, performance/benchmark.py

"""
Main GUI application coordinator.

This module is the glue between the visible interface and the lower-level
services that talk to the Arduino, load chip definitions, run diagnostics, and
explain results.

High-level flow:
1. Build the Tk window and child panels.
2. Connect to a board and learn its valid pin ranges.
3. Collect the selected chip and user wiring map.
4. Run the blocking hardware test on a background thread.
5. Fan the result out to the output log, dashboard, analytics, and helpers.
"""

import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Optional

from .theme import Theme, get_fonts
from .widgets import ModernButton, HelpDialog
from .manual_tester import ManualTesterController, ManualTesterWindow
from .panels import (ConnectionPanel, ChipPanel, PinMappingPanel, StatusPanel, OutputPanel,
                     PinVisualizer, DashboardPanel)

from ..arduino import ArduinoConnection
from ..chips import (
    ChipDatabase,
    ICTester,
)
from ..chips.migration import PinMigrationHelper
from ..config import Config
from ..logger import get_logger, setup_logging
from ..intelligence import ChipKnowledge, SessionTracker, PatternAnalyzer, ChipEducator
from ..intelligence.ml_classifier import MLFaultClassifier
from ..diagnostics import (
    StatisticalTester, SignalAnalyzer, DiagnosticReportGenerator, ICFingerprinter,
    AnalogAnalyzer,
)
from ..chips.test_generator import TestGenerator
from ..performance import PerformanceBenchmark

logger = get_logger("gui.app")


class ICTesterApp:
    """
    Main IC Tester GUI Application.
    
    Integrates all UI panels and coordinates:
    - Arduino connection management
    - Chip selection and pin mapping
    - Test execution and result display
    - Logging and status updates
    
    Attributes:
        root: Main Tk window
        arduino: ArduinoConnection instance
        chip_db: ChipDatabase instance
        tester: ICTester instance
    """
    
    def __init__(self):
        """Initialize the application"""
        # Configure logging first so every later startup stage can report useful
        # diagnostics if it fails.
        setup_logging()
        logger.info(f"Starting {Config.APP_NAME} v{Config.APP_VERSION}")
        
        # Create runtime directories before any subsystem tries to persist files.
        Config.ensure_directories()
        
        # Create the root Tk window before instantiating UI panels.
        self.root = tk.Tk()
        self.root.title(Config.APP_NAME)
        self.root.geometry(f"{Config.WINDOW_START_WIDTH}x{Config.WINDOW_START_HEIGHT}")
        self.root.minsize(Config.WINDOW_MIN_WIDTH, Config.WINDOW_MIN_HEIGHT)
        self.root.configure(bg=Theme.BG_DARK)
        
        # Get fonts
        self.fonts = get_fonts()
        
        # Core hardware/test services.
        self.arduino = ArduinoConnection()
        self.chip_db = ChipDatabase(
            board=Config.DEFAULT_BOARD
        )
        self.tester = ICTester(self.arduino, self.chip_db)
        
        # Result-explanation and learning helpers.
        self.knowledge = ChipKnowledge()
        self.session_tracker = SessionTracker()
        self.pattern_analyzer = PatternAnalyzer()
        self.educator = ChipEducator(self.knowledge, self.session_tracker)
        self.migration_helper = PinMigrationHelper(self.chip_db)
        
        # Advanced diagnostic tools that can be run after or alongside core tests.
        self.statistical_tester = StatisticalTester(self.tester)
        self.signal_analyzer = SignalAnalyzer(self.arduino)
        self.report_generator = DiagnosticReportGenerator()
        self.ml_classifier: Optional[MLFaultClassifier] = None
        self.fingerprinter = ICFingerprinter(self.arduino, self.chip_db)
        self.test_generator = TestGenerator()
        self.benchmark = PerformanceBenchmark(self.arduino)
        self.analog_analyzer = AnalogAnalyzer(self.arduino)
        self.manual_tester_controller = ManualTesterController(
            self.arduino, self.chip_db, self.test_generator, self.knowledge
        )
        
        # Cross-panel runtime state used to coordinate asynchronous work.
        self.is_testing = False
        self._previous_chip_id = None
        self._previous_chip_mapping = None
        self.manual_tester_window: Optional[ManualTesterWindow] = None
        self.counter_running = False
        self.last_result = None
        self.test_start_time = None
        self.connection_check_interval = Config.CONNECTION_CHECK_INTERVAL
        self._last_connect_time = time.time()  # Initialize to now (prevents early disconnect)
        self._monitor_enabled = True  # Can disable monitor temporarily
        
        # Build widgets after services exist so callbacks can bind directly.
        self._create_ui()
        
        # Delay the first scan slightly so the window paints immediately.
        self.root.after(100, self._scan_ports)
        
        # Background polling keeps the UI synchronized with unplug/replug events.
        self._start_connection_monitor()
        self._start_event_poller()
        
        logger.info("Application initialized successfully")

    def _get_ml_classifier(self) -> Optional[MLFaultClassifier]:
        """
        Create the ML classifier only when it is actually needed.

        This keeps the main GUI startup path independent from optional model or
        session-data issues.
        """
        if self.ml_classifier is None:
            try:
                self.ml_classifier = MLFaultClassifier()
            except Exception as e:
                logger.warning(f"ML classifier unavailable: {e}")
                return None
        return self.ml_classifier
    
    def _create_ui(self):
        """Build the main UI layout: scrollable sidebar + tabbed main area"""
        # Configure root grid
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Main container
        main = tk.Frame(self.root, bg=Theme.BG_DARK)
        main.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=0)  # sidebar fixed
        main.grid_columnconfigure(1, weight=1)  # main expands
        
        # ── Header (spans both columns) ──
        self._create_header(main)
        
        # ── Left sidebar (scrollable) ──
        self._create_sidebar(main)
        
        # ── Main area (tabbed notebook) ──
        self._create_main_tabs(main)
        
        # ── Style the Notebook tabs ──
        self._style_notebook()
        
        # Prime the mapping panel and pin visualizer with the initial chip.
        if self.chip_db.get_chip_count() > 0:
            chip_id = self.chip_panel.get_selected_chip()
            if chip_id:
                self._on_chip_selected(chip_id)
    
    def _create_sidebar(self, parent):
        """Build the scrollable left sidebar with connection, chip, status, and tools"""
        import platform
        
        sidebar_outer = tk.Frame(parent, bg=Theme.BG_DARK, width=290)
        sidebar_outer.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(10, 0))
        sidebar_outer.grid_propagate(False)
        
        # Canvas + scrollbar for sidebar scrolling
        self._sidebar_canvas = tk.Canvas(sidebar_outer, bg=Theme.BG_DARK,
                                         highlightthickness=0, width=280)
        sidebar_scrollbar = tk.Scrollbar(sidebar_outer, orient=tk.VERTICAL,
                                          command=self._sidebar_canvas.yview)
        self._sidebar_inner = tk.Frame(self._sidebar_canvas, bg=Theme.BG_DARK)
        
        self._sidebar_inner.bind("<Configure>",
            lambda e: self._sidebar_canvas.configure(
                scrollregion=self._sidebar_canvas.bbox("all")))
        
        self._sidebar_canvas_win = self._sidebar_canvas.create_window(
            (0, 0), window=self._sidebar_inner, anchor=tk.NW)
        self._sidebar_canvas.configure(yscrollcommand=sidebar_scrollbar.set)
        self._sidebar_canvas.bind("<Configure>",
            lambda e: self._sidebar_canvas.itemconfig(
                self._sidebar_canvas_win, width=e.width))
        
        self._sidebar_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sidebar_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Normalize wheel scrolling across platforms so every nested widget in
        # the sidebar still scrolls the same canvas.
        def _on_sidebar_scroll(event):
            if platform.system() == "Darwin":
                self._sidebar_canvas.yview_scroll(int(-1 * event.delta), "units")
            else:
                self._sidebar_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        # Store the scroll handler for later use
        self._sidebar_scroll_handler = _on_sidebar_scroll
        
        # Bind to canvas and inner frame
        self._sidebar_canvas.bind("<MouseWheel>", _on_sidebar_scroll)
        self._sidebar_inner.bind("<MouseWheel>", _on_sidebar_scroll)
        
        # Also bind to Button-4 and Button-5 for Linux
        if platform.system() == "Linux":
            self._sidebar_canvas.bind("<Button-4>", lambda e: self._sidebar_canvas.yview_scroll(-1, "units"))
            self._sidebar_canvas.bind("<Button-5>", lambda e: self._sidebar_canvas.yview_scroll(1, "units"))
            self._sidebar_inner.bind("<Button-4>", lambda e: self._sidebar_canvas.yview_scroll(-1, "units"))
            self._sidebar_inner.bind("<Button-5>", lambda e: self._sidebar_canvas.yview_scroll(1, "units"))
        
        # ── Panels inside sidebar ──
        self.connection_panel = ConnectionPanel(
            self._sidebar_inner,
            on_connect=self._connect_arduino,
            on_disconnect=self._disconnect_arduino,
            on_scan=self._scan_ports
        )
        
        self.chip_panel = ChipPanel(
            self._sidebar_inner,
            chip_ids=self.chip_db.get_all_chip_ids(),
            on_chip_selected=self._on_chip_selected,
            on_run_test=self._run_test,
            on_run_counter=self._start_counter,
            on_stop=self._stop_counter,
            board=self.chip_db.get_board()
        )
        
        self.status_panel = StatusPanel(self._sidebar_inner)
        
        # Advanced diagnostics button group
        adv_frame = tk.Frame(self._sidebar_inner, bg=Theme.BG_CARD, padx=10, pady=8)
        adv_frame.pack(fill=tk.X, pady=(10, 0))
        tk.Label(adv_frame, text="Advanced Diagnostics", font=self.fonts['subheading'],
                 bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY).pack(anchor=tk.W, pady=(0, 5))
        
        btn_row1 = tk.Frame(adv_frame, bg=Theme.BG_CARD)
        btn_row1.pack(fill=tk.X)
        ModernButton(btn_row1, "Statistical", self._run_statistical_test,
                     width=125, height=28, bg_color=Theme.ACCENT_INFO).pack(side=tk.LEFT, padx=(0, 5))
        ModernButton(btn_row1, "Signals", self._run_signal_analysis,
                     width=125, height=28, bg_color=Theme.ACCENT_INFO).pack(side=tk.LEFT)
        
        btn_row2 = tk.Frame(adv_frame, bg=Theme.BG_CARD)
        btn_row2.pack(fill=tk.X, pady=(5, 0))
        ModernButton(btn_row2, "Fingerprint", self._run_fingerprint,
                     width=125, height=28, bg_color=Theme.ACCENT_INFO).pack(side=tk.LEFT, padx=(0, 5))
        ModernButton(btn_row2, "Benchmark", self._run_benchmark,
                     width=125, height=28, bg_color=Theme.ACCENT_INFO).pack(side=tk.LEFT)
        
        btn_row3 = tk.Frame(adv_frame, bg=Theme.BG_CARD)
        btn_row3.pack(fill=tk.X, pady=(5, 0))
        ModernButton(btn_row3, "Analog Voltage", self._run_analog_analysis,
                     width=255, height=28, bg_color="#6b46c1").pack(side=tk.LEFT)
        
        # Recursively bind mousewheel on ALL sidebar children so scroll works everywhere
        self._bind_children_mousewheel(self._sidebar_inner, _on_sidebar_scroll)
        
        # Also use Enter/Leave events to ensure scrolling works when mouse enters any widget
        def _on_enter(event):
            self._sidebar_canvas.bind_all("<MouseWheel>", _on_sidebar_scroll)
            if platform.system() == "Linux":
                self._sidebar_canvas.bind_all("<Button-4>", lambda e: self._sidebar_canvas.yview_scroll(-1, "units"))
                self._sidebar_canvas.bind_all("<Button-5>", lambda e: self._sidebar_canvas.yview_scroll(1, "units"))
        
        def _on_leave(event):
            self._sidebar_canvas.unbind_all("<MouseWheel>")
            if platform.system() == "Linux":
                self._sidebar_canvas.unbind_all("<Button-4>")
                self._sidebar_canvas.unbind_all("<Button-5>")
        
        sidebar_outer.bind("<Enter>", _on_enter)
        sidebar_outer.bind("<Leave>", _on_leave)
        
        # Listen for widget changes (e.g., board info being added dynamically)
        def _on_widgets_changed(event):
            self._bind_children_mousewheel(self._sidebar_inner, _on_sidebar_scroll)
            # Update scroll region
            self._sidebar_canvas.configure(scrollregion=self._sidebar_canvas.bbox("all"))
        
        self._sidebar_inner.bind("<<WidgetsChanged>>", _on_widgets_changed)
    
    def _create_main_tabs(self, parent):
        """Build the tabbed main content area"""
        # Notebook container
        nb_frame = tk.Frame(parent, bg=Theme.BG_DARK)
        nb_frame.grid(row=1, column=1, sticky="nsew", pady=(10, 0))
        
        self.notebook = ttk.Notebook(nb_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # ── Tab 1: Pin Mapping ──
        tab_pins = tk.Frame(self.notebook, bg=Theme.BG_DARK)
        self.notebook.add(tab_pins, text="  Pin Mapping  ")
        
        # Split pin mapping tab into left (mapping) and right (chip view)
        tab_pins.grid_rowconfigure(0, weight=1)
        tab_pins.grid_columnconfigure(0, weight=1)
        tab_pins.grid_columnconfigure(1, weight=0)
        
        pin_map_container = tk.Frame(tab_pins, bg=Theme.BG_DARK)
        pin_map_container.grid(row=0, column=0, sticky="nsew", padx=(5, 5))
        
        self.pin_mapping_panel = PinMappingPanel(
            pin_map_container,
            log_callback=self._log
        )
        
        chip_view_container = tk.Frame(tab_pins, bg=Theme.BG_DARK, width=280)
        chip_view_container.grid(row=0, column=1, sticky="nsew", padx=(0, 5))
        chip_view_container.grid_propagate(False)
        
        self.pin_visualizer = PinVisualizer(chip_view_container)
        self.pin_visualizer.pack(fill=tk.BOTH, expand=True)
        
        # ── Tab 2: Output Log ──
        tab_output = tk.Frame(self.notebook, bg=Theme.BG_DARK)
        self.notebook.add(tab_output, text="  Output Log  ")
        
        self.output_panel = OutputPanel(
            tab_output,
            on_clear=self._clear_output
        )
        
        # ── Tab 3: Dashboard ──
        tab_dash = tk.Frame(self.notebook, bg=Theme.BG_DARK)
        self.notebook.add(tab_dash, text="  Dashboard  ")
        
        self.dashboard_panel = DashboardPanel(tab_dash)
        self.dashboard_panel.pack(fill=tk.BOTH, expand=True)
        
        # Start on the Output Log tab (most commonly used)
        self.notebook.select(tab_output)
    
    def _style_notebook(self):
        """Apply dark theme styling to ttk.Notebook tabs and comboboxes"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Notebook styling
        style.configure("TNotebook", background=Theme.BG_DARK, borderwidth=0,
                        tabmargins=[2, 5, 2, 0])
        style.configure("TNotebook.Tab",
            background=Theme.BG_CARD,
            foreground=Theme.TEXT_SECONDARY,
            padding=[14, 6],
            font=self.fonts['button'],
            borderwidth=0,
        )
        style.map("TNotebook.Tab",
            background=[("selected", Theme.BG_LIGHT), ("active", "#2a2a4a")],
            foreground=[("selected", Theme.TEXT_PRIMARY), ("active", Theme.TEXT_PRIMARY)],
        )
        # Remove dotted focus ring on tabs
        style.layout("TNotebook.Tab", [
            ('Notebook.tab', {'sticky': 'nswe', 'children': [
                ('Notebook.padding', {'side': 'top', 'sticky': 'nswe', 'children': [
                    ('Notebook.label', {'side': 'top', 'sticky': ''})
                ]})
            ]})
        ])
        
        # Combobox styling to match dark theme
        style.configure("TCombobox",
            fieldbackground=Theme.BG_LIGHT,
            background=Theme.BG_CARD,
            foreground=Theme.TEXT_PRIMARY,
            arrowcolor=Theme.TEXT_SECONDARY,
            borderwidth=0,
        )
        style.map("TCombobox",
            fieldbackground=[("readonly", Theme.BG_LIGHT), ("disabled", Theme.BG_CARD)],
            foreground=[("readonly", Theme.TEXT_PRIMARY), ("disabled", Theme.TEXT_MUTED)],
        )
        
        # Scrollbar styling
        style.configure("TScrollbar",
            background=Theme.BG_CARD,
            troughcolor=Theme.BG_DARK,
            arrowcolor=Theme.TEXT_SECONDARY,
            borderwidth=0,
        )
    
    def _create_header(self, parent):
        """Create the application header"""
        header = tk.Frame(parent, bg=Theme.BG_DARK)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        
        # Title
        tk.Label(header, text=Config.APP_NAME, 
                font=self.fonts['heading'],
                bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY).pack(side=tk.LEFT)
        
        # Subtitle
        tk.Label(header, text=Config.APP_SUBTITLE,
                font=self.fonts['body'],
                bg=Theme.BG_DARK, fg=Theme.TEXT_SECONDARY).pack(side=tk.LEFT, padx=(15, 0), pady=(8, 0))
        
        # Right side - Help and version
        right = tk.Frame(header, bg=Theme.BG_DARK)
        right.pack(side=tk.RIGHT)

        ModernButton(
            right,
            "Manual Tester",
            self._open_manual_tester,
            width=128,
            height=32,
            bg_color=Theme.ACCENT_PRIMARY,
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        ModernButton(right, "? Help", self._show_help,
                    width=80, height=32, bg_color=Theme.ACCENT_INFO).pack(side=tk.LEFT, padx=(0, 10))
        
        # Version badge
        version_frame = tk.Frame(right, bg=Theme.ACCENT_PRIMARY, padx=8, pady=2)
        version_frame.pack(side=tk.LEFT)
        tk.Label(version_frame, text=f"v{Config.APP_VERSION}", font=self.fonts['small'],
                bg=Theme.ACCENT_PRIMARY, fg="white").pack()
    
    # =========================================================================
    # Logging
    # =========================================================================
    
    def _log(self, message: str, level: str = None):
        """Log a message to both output panel and logger"""
        self.output_panel.log(message, level)
        
        # Also log to file
        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "success":
            logger.info(f"[SUCCESS] {message}")
        else:
            logger.info(message)
    
    def _switch_to_tab(self, index: int):
        """Switch the main notebook to the specified tab index (0=Pin Mapping, 1=Output, 2=Dashboard)"""
        try:
            self.notebook.select(index)
        except Exception:
            pass
    
    @staticmethod
    def _bind_children_mousewheel(widget, handler):
        """Recursively bind mousewheel handler to widget and all its descendants"""
        import platform
        
        # Bind mousewheel for Windows/macOS
        widget.bind("<MouseWheel>", handler, add="+")
        
        # Bind for Linux
        if platform.system() == "Linux":
            widget.bind("<Button-4>", lambda e: handler(type('Event', (), {'delta': 120})()), add="+")
            widget.bind("<Button-5>", lambda e: handler(type('Event', (), {'delta': -120})()), add="+")
        
        # Recursively bind to all children
        for child in widget.winfo_children():
            ICTesterApp._bind_children_mousewheel(child, handler)
    
    # =========================================================================
    # Connection Management
    # =========================================================================
    
    def _scan_ports(self):
        """Scan for available Arduino ports"""
        self._log("🔍 Scanning for Arduino devices...")
        ports = self.arduino.find_arduino_ports()
        
        if ports:
            self.connection_panel.set_ports(ports)
            self._log(f"✅ Found {len(ports)} device(s): {', '.join(ports)}", "success")
        else:
            self.connection_panel.set_ports([])
            self._log("⚠️ No Arduino devices found. Check USB connection.", "warning")
    
    def _connect_arduino(self):
        """
        Connect to the selected Arduino port and refresh board-aware UI state.

        After a successful handshake this method pushes the detected board type
        and valid pin ranges into the connection panel so mapping validation and
        user guidance stay aligned with the hardware that is actually attached.
        """
        if self.arduino.connected:
            self._log("ℹ️ Already connected.", "info")
            return
        
        port = self.connection_panel.get_selected_port()
        if not port:
            messagebox.showerror("No Port Selected", 
                               "Please select a port first.\n\n"
                               "Click 'Scan' to find available devices.")
            return
        
        self._log(f"🔌 Connecting to {port}...")
        self.connection_panel.set_connecting()
        self.root.update()
        
        # Record the attempt time before opening the port so the connection
        # monitor ignores the expected board reset/boot window.
        self._last_connect_time = time.time()
        
        if self.arduino.connect(port):
            self.connection_panel.set_connected()
            
            # Detect and display board information
            if hasattr(self.arduino, 'commands') and self.arduino.commands:
                board_type = self.arduino.commands.get_board_type()
                pin_ranges = self.arduino.commands.get_pin_ranges()
                self.connection_panel.set_board_info(
                    board_type,
                    pin_ranges['digital'],
                    pin_ranges['analog']
                )
                self._log(f"✅ Arduino connected successfully! Board: {board_type}", "success")
            else:
                self._log("✅ Arduino connected successfully!", "success")
        else:
            self.connection_panel.set_failed()
            self._log("❌ Failed to connect to Arduino", "error")
            messagebox.showerror("Connection Failed", 
                               "Could not connect to Arduino.\n\nCheck:\n"
                               "1. Arduino IDE is closed\n"
                               "2. Sketch is uploaded\n"
                               "3. Correct port selected")
    
    def _disconnect_arduino(self):
        """Disconnect from Arduino"""
        if self.is_testing:
            result = messagebox.askyesno("Test in Progress",
                                        "A test is currently running.\n\n"
                                        "Disconnecting now may cause incomplete results.\n"
                                        "Are you sure you want to disconnect?")
            if not result:
                return
            self.is_testing = False
        
        self.arduino.disconnect()
        self.connection_panel.set_disconnected()
        self._log("🔌 Disconnected from Arduino", "info")
    
    def _start_connection_monitor(self):
        """Start monitoring connection health - runs every 5 seconds"""
        def check_connection():
            # The monitor is intentionally conservative: it waits out a grace
            # period after connect and requires two failed checks before it
            # declares the board gone.
            if self._monitor_enabled and self.arduino.connected:
                # Grace period: skip checks within 10 seconds of connection
                elapsed = time.time() - self._last_connect_time
                if elapsed < 10.0:
                    logger.debug(f"Connection monitor: grace period ({elapsed:.1f}s since connect)")
                else:
                    # Do a gentle check - don't disconnect on single failure
                    if not self._check_arduino_alive():
                        logger.warning("Arduino not responding to health check")
                        # Try once more before giving up
                        if not self._check_arduino_alive():
                            self._log("⚠️ Lost connection to Arduino!", "warning")
                            self.connection_panel.set_disconnected()
                            self.arduino.disconnect()
            
            # Schedule next check
            self.root.after(self.connection_check_interval, check_connection)
        
        # Start the monitor loop
        self.root.after(self.connection_check_interval, check_connection)

    def _start_event_poller(self):
        """Poll queued firmware EVT lines and log them safely."""
        def poll_events():
            if self.arduino.connected:
                for event_line in self.arduino.drain_events():
                    self._handle_firmware_event(event_line)
            self.root.after(150, poll_events)

        self.root.after(150, poll_events)

    def _handle_firmware_event(self, event_line: str):
        """Log any unsolicited firmware lines."""
        try:
            self._log(f"📨 {event_line}", "info")
        except Exception as e:
            logger.debug(f"Failed to log firmware event '{event_line}': {e}")
    
    def _check_arduino_alive(self) -> bool:
        """Gentle check if Arduino is still connected (doesn't auto-disconnect)"""
        if not self.arduino.connected or not self.arduino._serial:
            return False
        
        try:
            # Just check if serial port is still open and responsive
            return self.arduino._serial.is_open
        except Exception:
            return False
    
    
    # =========================================================================
    # Chip Selection
    # =========================================================================
    
    def _refresh_chip_list(self):
        """Reload database and refresh chip list in UI."""
        self.chip_db.reload()
        chip_ids = self.chip_db.get_all_chip_ids(board=self.chip_panel.get_board())
        self.chip_panel.set_chip_ids(chip_ids)
        self._log(f"📚 Loaded {len(chip_ids)} chip(s)", "info")
    
    def _on_chip_selected(self, chip_id: str):
        """Handle chip selection change"""
        chip = self.chip_db.get_chip(chip_id, board=self.chip_panel.get_board())
        if not chip:
            return
        
        # Check if we're switching from a different chip with a mapping
        show_migration = False
        if (self._previous_chip_id and 
            self._previous_chip_id != chip_id and 
            self._previous_chip_mapping):
            show_migration = True
        
        # Update chip info
        name = chip.get('name', chip_id)
        desc = chip.get('description', '')
        self.chip_panel.set_chip_info(name, desc)
        
        # Populate pin mapping
        self.pin_mapping_panel.populate(chip)
        self.pin_mapping_panel.set_chip_id(chip_id)
        
        # Update chip visualizer and reset dashboard
        self.pin_visualizer.load_chip(chip)
        self.dashboard_panel.clear()
        
        # Auto-load saved pin mapping if it exists (silent - no warning if missing)
        self.pin_mapping_panel.load(silent=True)
        
        # Capture the loaded mapping for migration suggestions
        current_mapping = self.pin_mapping_panel.get_mapping()
        
        # Show migration suggestions if switching chips
        if show_migration and current_mapping:
            prev_chip_exists = self.chip_db.get_chip(self._previous_chip_id, board=self.chip_panel.get_board()) is not None
            if not prev_chip_exists:
                show_migration = False
        
        if show_migration and current_mapping:
            self._show_migration_suggestions(self._previous_chip_id, chip_id, 
                                            self._previous_chip_mapping)
        
        # Store current chip and mapping for next switch
        self._previous_chip_id = chip_id
        if current_mapping:
            self._previous_chip_mapping = current_mapping.copy()
        
        # Show/hide counter button based on chip type
        pinout = chip.get('pinout', {})
        input_names = [p['name'] for p in pinout.get('inputs', [])]
        is_counter = any(name in input_names for name in ['CKA', 'CKB', 'CLK', 'CLOCK'])
        self.chip_panel.show_counter_button(is_counter)
        
        logger.debug(f"Selected chip: {chip_id}")
    
    # =========================================================================
    # Testing
    # =========================================================================
    
    def _run_test(self):
        """
        Validate UI state, capture the active mapping, and launch a chip test.

        The actual hardware workflow runs on a worker thread so Tk stays
        responsive while serial commands and settle delays are in flight.
        """
        # Validate connection before doing any chip/mapping work.
        if not self.arduino.connected:
            messagebox.showerror("Not Connected", 
                               "Please connect to Arduino first.")
            return
        
        if self.is_testing:
            self._log("⚠️ Test already in progress.", "warning")
            return
        
        # Get chip
        chip_id = self.chip_panel.get_selected_chip()
        if not chip_id:
            messagebox.showerror("No Chip Selected", "Please select a chip to test.")
            return
        
        chip_data = self.chip_db.get_chip(chip_id, board=self.chip_panel.get_board())
        if not chip_data:
            self._log(f"❌ Chip {chip_id} data not found!", "error")
            return
        
        # Validate the user-edited mapping before any hardware writes happen.
        if not self.pin_mapping_panel.validate():
            messagebox.showerror("Invalid Pin Mapping", 
                               "Please configure valid Arduino pin mappings.")
            return
        
        user_mapping = self.pin_mapping_panel.get_mapping()
        # Store mapping for migration suggestions when switching chips
        self._previous_chip_mapping = user_mapping.copy() if user_mapping else None
        if not user_mapping:
            self._log("❌ No valid pin mapping!", "error")
            return
        
        # Lock the UI into test mode before the worker thread starts so users
        # cannot accidentally queue overlapping runs.
        self.is_testing = True
        self.test_start_time = __import__('time').time()
        self.status_panel.set_testing()
        self.chip_panel.set_testing(True)
        
        # Switch to Output Log tab so user sees results
        self._switch_to_tab(1)
                
        self.output_panel.log_test_start(chip_id)
        
        # These hints are explanatory only; they do not alter the real test.
        hints = self.educator.get_pre_test_hints(chip_id)
        for hint in hints[:2]:  # Show top 2 hints
            self._log(f"💡 {hint.title}: {hint.content}", "info")
        
        # Store mapping for later analysis
        self._current_test_mapping = user_mapping
        
        # Keep Tk operations on the main thread. The worker only performs the
        # blocking tester call, then marshals the result back with `after`.
        def test_thread():
            try:
                results = self.tester.run_test(chip_id, 
                                              progress_callback=self._log,
                                              custom_mapping=user_mapping,
                                              board=self.chip_panel.get_board())
                self.root.after(0, lambda: self._display_results(results))
            except Exception as e:
                self.root.after(0, lambda: self._handle_test_error(str(e)))
        
        threading.Thread(target=test_thread, daemon=True).start()
    
    def _display_results(self, results: dict):
        """
        Feed one completed hardware result into all post-processing layers.

        This includes the visible UI updates plus the educational, analytical,
        and historical subsystems that build on top of the raw pass/fail data.
        """
        import time
        self.is_testing = False
        self.chip_panel.set_testing(False)
        self.last_result = results
        
        # Calculate test duration
        duration = time.time() - self.test_start_time if self.test_start_time else 0
        
        # Persist the run so later hints, confidence scores, and analytics can
        # reason about the user's historical patterns.
        chip_id = results.get('chipId', self.chip_panel.get_selected_chip())
        self.session_tracker.record_test(
            chip_id=chip_id,
            results=results,
            pin_mapping=getattr(self, '_current_test_mapping', {}),
            duration=duration
        )
        
        # Confidence blends the immediate test result with prior history so the
        # feedback is more contextual than a bare pass/fail badge.
        historical_rate = self.session_tracker.get_success_rate(chip_id)
        confidence = self.pattern_analyzer.calculate_confidence(
            chip_id, results, historical_rate
        )
        
        # Wiring failures short-circuit the rest of the happy-path UI because
        # the most useful next step is to fix connections first.
        if not results.get('pinsVerified', True):
            self.status_panel.set_pin_error()
            self._log_pin_error(results)
            self._show_intelligent_analysis(chip_id, results, confidence)
            return
        
        # Update stats and status
        self.status_panel.update_from_results(results)
        self.output_panel.log_test_complete(results)
        
        # Show educational explanation
        explanation = self.educator.get_post_test_explanation(chip_id, results)
        self._log("")
        self._log(explanation["summary"], "success" if results.get('success') else "error")
        
        if explanation.get("celebration"):
            self._log(explanation["celebration"], "success")
        
        # Show learning points
        if explanation.get("learning_points"):
            self._log("\n📚 Learning Points:", "info")
            for point in explanation["learning_points"][:3]:
                self._log(f"   • {point}", "info")
        
        # Show confidence score
        self._log(f"\n🎯 Confidence: {confidence.overall:.0%}", "info")
        for factor in confidence.factors[:2]:
            self._log(f"   • {factor}", "info")
        
        # Show per-pin diagnostic summary
        self._show_pin_diagnostics(results)
        
        # === Advanced Diagnostics Integration ===
        # Use the same raw result payload to update all deeper analysis views so
        # the dashboard stays consistent with the log.
        self.pin_visualizer.update_from_test_result(results)
        
        # Generate diagnostic report
        mistakes = self.pattern_analyzer.analyze_failure(
            chip_id, results,
            getattr(self, '_current_test_mapping', {})
        ) if not results.get('success') else []
        
        diag_report = self.report_generator.generate_report(
            test_result=results,
            pattern_mistakes=mistakes,
            confidence_score=confidence,
        )
        
        # Update dashboard with diagnostic report
        self.dashboard_panel.update_from_diagnostic_report(diag_report)
        
        # Run ML fault classification and display on dashboard
        ml_classifier = self._get_ml_classifier()
        if ml_classifier is not None:
            ml_predictions = ml_classifier.classify_test_result(results)
            self.dashboard_panel.update_ml_predictions(ml_predictions)

            # Auto-train ML classifier from this result
            ml_classifier.auto_label_and_train(results)
        
        # Save diagnostic report for historical analysis
        try:
            self.report_generator.save_report(diag_report)
        except Exception as e:
            logger.debug(f"Failed to save diagnostic report: {e}")

        if not results.get('success'):
            # Try to identify correct chip
            self._try_identify_wrong_chip(results)
    
    def _show_pin_diagnostics(self, results):
        """Show per-pin diagnostic summary from test results"""
        pin_diag = results.get('pinDiagnostics', {})
        if not pin_diag:
            return

        has_issues = any(
            d.get('timesWrong', 0) > 0 or d.get('timesError', 0) > 0 or d.get('stuckState')
            for d in pin_diag.values()
        )

        if not has_issues and results.get('success'):
            return

        self._log("\n" + "═" * 50, "info")
        self._log("📊 PIN DIAGNOSTIC REPORT", "info")
        self._log("═" * 50, "info")

        for pin_name, diag in pin_diag.items():
            tested = diag.get('timesTested', 0)
            correct = diag.get('timesCorrect', 0)
            wrong = diag.get('timesWrong', 0)
            errors = diag.get('timesError', 0)
            stuck = diag.get('stuckState')
            chip_pin = diag.get('chipPin', '?')
            arduino_pin = diag.get('arduinoPin', '?')

            if tested == 0:
                continue

            pct = (correct / tested * 100) if tested > 0 else 0

            if stuck == 'HIGH':
                icon = "🔴"
                status = f"STUCK HIGH ({correct}/{tested} correct)"
                level = "error"
            elif stuck == 'LOW':
                icon = "🔵"
                status = f"STUCK LOW ({correct}/{tested} correct)"
                level = "error"
            elif stuck == 'NO_RESPONSE':
                icon = "⚫"
                status = f"NO RESPONSE ({errors} errors)"
                level = "error"
            elif stuck == 'INTERMITTENT':
                icon = "🟡"
                status = f"INTERMITTENT ({correct}/{tested} correct)"
                level = "warning"
            elif wrong > 0 or errors > 0:
                icon = "🟠"
                status = f"{correct}/{tested} correct ({pct:.0f}%)"
                level = "warning"
            else:
                icon = "🟢"
                status = f"{correct}/{tested} correct"
                level = "info"

            self._log(f"  {icon} {pin_name} (pin {chip_pin} → Ard.{arduino_pin}): {status}", level)

            # Show specific wrong readings for failing pins
            if wrong > 0:
                wrongs = diag.get('wrongReadings', [])
                for w in wrongs[:3]:
                    self._log(f"       Test {w['testId']}: expected {w['expected']}, got {w['actual']}", "warning")
                if len(wrongs) > 3:
                    self._log(f"       ...and {len(wrongs) - 3} more failures", "warning")

        self._log("═" * 50, "info")

    def _log_pin_error(self, results):
        """Log pin verification error details"""
        error_msg = results.get('error', 'Pin verification failed')
        problem_pins = results.get('problemPins', [])
        
        self._log("\n" + "─" * 50)
        self._log("🔌 PIN CONNECTION CHECK FAILED", "error")
        self._log("─" * 50)
        self._log(f"Error: {error_msg}", "error")
        
        if problem_pins:
            self._log("\nProblem pins detected:", "warning")
            for pin in problem_pins:
                self._log(f"  • Chip Pin {pin['chip_pin']} ({pin['name']}) → Arduino Pin {pin['arduino_pin']}", "error")
        
        self._log("\nPlease check:", "warning")
        self._log("  • All jumper wires are firmly connected", "warning")
        self._log("  • Wires are in the correct Arduino pins", "warning")
        self._log("  • Chip is seated properly", "warning")
    
    def _show_intelligent_analysis(self, chip_id: str, results: dict, confidence):
        """Show intelligent analysis of test failure"""
        # Analyze failure patterns
        mistakes = self.pattern_analyzer.analyze_failure(
            chip_id, results, 
            getattr(self, '_current_test_mapping', {})
        )
        
        if mistakes:
            self._log("\n🧠 Intelligent Analysis:", "info")
            for mistake in mistakes[:3]:
                self._log(f"   Possible: {mistake.description} ({mistake.confidence:.0%} likely)", "warning")
            
            # Get prioritized fixes
            fixes = self.pattern_analyzer.get_fix_priority(mistakes)
            if fixes:
                self._log("\n🔧 Suggested Fixes (try in order):", "info")
                for i, fix in enumerate(fixes[:3], 1):
                    self._log(f"   {i}. {fix}", "info")
        
        # Show historical context
        stats = self.session_tracker.get_chip_stats(chip_id)
        if stats and stats.total_tests > 1:
            rate = stats.successful_tests / stats.total_tests
            self._log(f"\n📊 Your history with {chip_id}: {rate:.0%} success ({stats.total_tests} tests)", "info")
            
            if self.session_tracker.is_improving(chip_id):
                self._log("   📈 You're improving with this chip!", "success")
    
    def _try_identify_wrong_chip(self, results):
        """Try to identify if wrong chip is inserted"""
        self._log("\n🔍 Checking if a different chip is inserted...", "info")
        self.root.update()
        
        detected_id, confidence, message = self.tester.identify_chip(
            self._log, board=self.chip_panel.get_board()
        )
        
        if detected_id and detected_id != results['chipId'] and confidence >= 70:
            self._log(f"\n⚠️ WRONG CHIP DETECTED!", "warning")
            self._log(f"   You selected: {results['chipId']}", "warning")
            self._log(f"   Detected chip: {detected_id} ({confidence:.0f}% match)", "warning")
            self._log(f"   → Try selecting '{detected_id}' from the dropdown", "info")
            self.status_panel.set_custom_text(f"Wrong chip? Try {detected_id}", Theme.ACCENT_WARNING)
        elif detected_id == results['chipId'] and confidence >= 70:
            self._log(f"\n✓ Chip appears to be {detected_id}, but some tests failed", "info")
            self._log("   The chip may be defective", "warning")
    
    def _handle_test_error(self, error_msg: str):
        """Handle errors during testing"""
        self.is_testing = False
        self.chip_panel.set_testing(False)
        self.status_panel.set_test_error()
                
        self._log(f"\n❌ Test error: {error_msg}", "error")
        messagebox.showerror("Test Error", 
                           f"An error occurred during testing:\n\n{error_msg}")
    
    # =========================================================================
    # Counter Mode
    # =========================================================================
    
    def _start_counter(self):
        """Start continuous counter mode"""
        if not self.arduino.connected:
            self._log("❌ Connect to Arduino first!", "error")
            return
        
        if self.counter_running:
            return
        
        self.counter_running = True
        self._log("⏱ Starting continuous counter mode...", "info")
        self.chip_panel.set_counter_running(True)
        
        # Counter logic would go here
        # This is a placeholder for the actual counter implementation
    
    def _stop_counter(self):
        """Stop counter mode or abort running test"""
        # Stop counter if running
        if self.counter_running:
            self.counter_running = False
            self.chip_panel.set_counter_running(False)
            self._log("⏱ Counter stopped.", "info")
        
        # Abort test if running
        if self.is_testing:
            self.tester.abort()
            self._log("⏹ Aborting test...", "warning")
    
    # =========================================================================
    # Advanced Diagnostics (Phases 1-7)
    # =========================================================================
    
    def _run_statistical_test(self):
        """Run multi-run statistical test for intermittent failure detection"""
        if not self.arduino.connected:
            self._log("❌ Connect to Arduino first!", "error")
            return
        if self.is_testing:
            self._log("⚠️ Test already in progress.", "warning")
            return
        
        chip_id = self.chip_panel.get_selected_chip()
        if not chip_id:
            messagebox.showerror("No Chip Selected", "Please select a chip.")
            return
        if not self.pin_mapping_panel.validate():
            messagebox.showerror("Invalid Pin Mapping", "Please configure valid pin mappings.")
            return
        
        user_mapping = self.pin_mapping_panel.get_mapping()
        if not user_mapping:
            self._log("❌ No valid pin mapping!", "error")
            return
        
        self.is_testing = True
        self.status_panel.set_testing()
        self.chip_panel.set_testing(True)
        
        def stat_thread():
            try:
                result = self.statistical_tester.run_statistical_test(
                    chip_id, num_runs=5,
                    progress_callback=self._log,
                    custom_mapping=user_mapping,
                    board=self.chip_panel.get_board(),
                )
                self.root.after(0, lambda: self._on_statistical_complete(result))
            except Exception as e:
                self.root.after(0, lambda: self._handle_test_error(str(e)))
        
        threading.Thread(target=stat_thread, daemon=True).start()
    
    def _on_statistical_complete(self, stat_result):
        """Handle completion of statistical testing"""
        self.is_testing = False
        self.chip_panel.set_testing(False)
        
        if stat_result.overall_pass_rate >= 0.9:
            self.status_panel.set_passed()
        elif stat_result.overall_pass_rate >= 0.5:
            self.status_panel.set_idle()
        else:
            self.status_panel.set_failed()
        
        # Generate diagnostic report incorporating statistical data
        if stat_result.run_results:
            last_result = stat_result.run_results[-1]
            diag_report = self.report_generator.generate_report(
                test_result=last_result,
                statistical_result=stat_result,
            )
            self.dashboard_panel.update_from_diagnostic_report(diag_report)
            self.pin_visualizer.update_from_diagnostic_report(diag_report)
    
    def _run_signal_analysis(self):
        """Run signal stability and propagation delay analysis"""
        if not self.arduino.connected:
            self._log("❌ Connect to Arduino first!", "error")
            return
        if self.is_testing:
            self._log("⚠️ Test already in progress.", "warning")
            return
        
        chip_id = self.chip_panel.get_selected_chip()
        if not chip_id:
            messagebox.showerror("No Chip Selected", "Please select a chip.")
            return
        
        chip_data = self.chip_db.get_chip(chip_id, board=self.chip_panel.get_board())
        if not chip_data:
            self._log(f"❌ Chip {chip_id} data not found!", "error")
            return
        
        self.is_testing = True
        self.status_panel.set_testing()
        
        def signal_thread():
            try:
                report = self.signal_analyzer.analyze_chip_signals(
                    chip_data, progress_callback=self._log,
                )
                self.root.after(0, lambda: self._on_signal_complete(report))
            except Exception as e:
                self.root.after(0, lambda: self._handle_test_error(str(e)))
        
        threading.Thread(target=signal_thread, daemon=True).start()
    
    def _on_signal_complete(self, signal_report):
        """Handle completion of signal analysis"""
        self.is_testing = False
        self.status_panel.set_idle()
        
        if signal_report.overall_stability >= 0.95:
            self._log("✅ All signals stable", "success")
        elif signal_report.flickering_pins:
            self._log(f"⚠️ {len(signal_report.flickering_pins)} flickering pin(s) detected", "warning")
    
    def _run_fingerprint(self):
        """Run IC behavior fingerprinting to identify unknown chips"""
        if not self.arduino.connected:
            self._log("❌ Connect to Arduino first!", "error")
            return
        if self.is_testing:
            self._log("⚠️ Test already in progress.", "warning")
            return
        
        chip_id = self.chip_panel.get_selected_chip()
        if not chip_id:
            messagebox.showerror("No Chip Selected", "Please select a chip for reference pinout.")
            return
        
        chip_data = self.chip_db.get_chip(chip_id, board=self.chip_panel.get_board())
        if not chip_data:
            self._log(f"❌ Chip {chip_id} data not found!", "error")
            return
        
        self.is_testing = True
        self.status_panel.set_testing()
        
        def fp_thread():
            try:
                fingerprint = self.fingerprinter.fingerprint_chip(
                    chip_data, progress_callback=self._log,
                )
                self.root.after(0, lambda: self._on_fingerprint_complete(fingerprint))
            except Exception as e:
                self.root.after(0, lambda: self._handle_test_error(str(e)))
        
        threading.Thread(target=fp_thread, daemon=True).start()
    
    def _on_fingerprint_complete(self, fingerprint):
        """Handle completion of IC fingerprinting"""
        self.is_testing = False
        self.status_panel.set_idle()
        
        if fingerprint.best_match_chip:
            conf = fingerprint.best_match_confidence
            if conf >= 0.8:
                self.status_panel.set_custom_text(
                    f"ID: {fingerprint.best_match_chip}", Theme.ACCENT_SUCCESS)
            elif conf >= 0.5:
                self.status_panel.set_custom_text(
                    f"Maybe: {fingerprint.best_match_chip}?", Theme.ACCENT_WARNING)
    
    def _run_benchmark(self):
        """Run system performance benchmark"""
        if not self.arduino.connected:
            self._log("❌ Connect to Arduino first!", "error")
            return
        if self.is_testing:
            self._log("⚠️ Test already in progress.", "warning")
            return
        
        self.is_testing = True
        self.status_panel.set_testing()
        
        def bench_thread():
            try:
                report = self.benchmark.run_full_benchmark(
                    progress_callback=self._log, iterations=30,
                )
                self.root.after(0, lambda: self._on_benchmark_complete(report))
            except Exception as e:
                self.root.after(0, lambda: self._handle_test_error(str(e)))
        
        threading.Thread(target=bench_thread, daemon=True).start()
    
    def _on_benchmark_complete(self, report):
        """Handle completion of benchmark"""
        self.is_testing = False
        self.status_panel.set_idle()
        self._log(f"\n📋 System limits reference available via PerformanceBenchmark.get_system_limits_doc()", "info")
    
    def _run_analog_analysis(self):
        """Run analog voltage analysis on IC output pins wired to A0-A15"""
        if not self.arduino.connected:
            self._log("❌ Connect to Arduino first!", "error")
            return
        if self.is_testing:
            self._log("⚠️ Test already in progress.", "warning")
            return
        
        chip_id = self.chip_panel.get_selected_chip()
        if not chip_id:
            messagebox.showerror("No Chip Selected", "Please select a chip.")
            return
        
        chip_data = self.chip_db.get_chip(chip_id, board=self.chip_panel.get_board())
        if not chip_data:
            self._log(f"❌ Chip {chip_id} data not found!", "error")
            return
        
        # Build analog pin map from the current pin mapping
        # Look for pins in the analog range (54-69 = A0-A15)
        user_mapping = self.pin_mapping_panel.get_mapping()
        pinout = chip_data.get("pinout", {})
        
        analog_pin_map = {}
        for out in pinout.get("outputs", []):
            pin_name = out["name"]
            chip_pin = str(out["pin"])
            ard_pin = user_mapping.get(chip_pin)
            if ard_pin is not None:
                try:
                    ard_int = int(ard_pin)
                    if 54 <= ard_int <= 69:
                        analog_pin_map[pin_name] = ard_int
                except (ValueError, TypeError):
                    pass
        
        for inp in pinout.get("inputs", []):
            pin_name = inp["name"]
            chip_pin = str(inp["pin"])
            ard_pin = user_mapping.get(chip_pin)
            if ard_pin is not None:
                try:
                    ard_int = int(ard_pin)
                    if 54 <= ard_int <= 69:
                        analog_pin_map[pin_name] = ard_int
                except (ValueError, TypeError):
                    pass
        
        if not analog_pin_map:
            # No analog pins found — show guide
            from ..diagnostics.analog_analyzer import AnalogAnalyzer
            guide = AnalogAnalyzer.get_analog_pin_guide()
            self._log(guide, "info")
            self._log(
                "ℹ️ No pins mapped to analog range (A0-A15 = pins 54-69).\n"
                "   To use analog analysis, wire IC outputs to analog pins\n"
                "   and enter the analog pin numbers (54-69) in the mapping.",
                "warning"
            )
            return
        
        self._log(
            f"🔬 Starting analog analysis with {len(analog_pin_map)} pin(s) on analog inputs",
            "info"
        )
        for name, apin in analog_pin_map.items():
            self._log(f"   {name} → A{apin - 54} (pin {apin})", "info")
        
        self.is_testing = True
        self.status_panel.set_testing()
        
        def analog_thread():
            try:
                report = self.analog_analyzer.analyze_chip_analog(
                    chip_data,
                    analog_pin_map=analog_pin_map,
                    progress_callback=self._log,
                )
                self.root.after(0, lambda: self._on_analog_complete(report))
            except Exception as e:
                self.root.after(0, lambda: self._handle_test_error(str(e)))
        
        threading.Thread(target=analog_thread, daemon=True).start()
    
    def _on_analog_complete(self, report):
        """Handle completion of analog voltage analysis"""
        self.is_testing = False
        self.status_panel.set_idle()
        
        health = report.overall_voltage_health
        if health == "ok":
            self.status_panel.set_custom_text("Voltages OK", Theme.ACCENT_SUCCESS)
        elif health == "warning":
            issues = len(report.marginal_pins) + len(report.noisy_pins)
            self.status_panel.set_custom_text(
                f"{issues} voltage warning(s)", Theme.ACCENT_WARNING)
        else:
            issues = len(report.floating_pins)
            self.status_panel.set_custom_text(
                f"{issues} voltage error(s)", Theme.ACCENT_ERROR)
    
    # =========================================================================
    # Pin Migration
    # =========================================================================
    
    def _show_migration_suggestions(self, from_chip: str, to_chip: str, 
                                    old_mapping: Dict[str, int]):
        """Show smart suggestions for rewiring when switching chips"""
        self._log("=" * 50, "info")
        self._log(f"🔄 SWITCHING FROM {from_chip} TO {to_chip}", "info")
        self._log("=" * 50, "info")
        
        plan = self.migration_helper.analyze_migration(from_chip, to_chip, old_mapping)
        
        # Show suggestions
        for suggestion in plan.suggestions:
            if suggestion.startswith("  ") and "→" in suggestion:
                self._log(suggestion, "warning")
            elif "💡" in suggestion:
                self._log(suggestion, "success")
            elif suggestion.startswith("📋") or suggestion.startswith("  🔌") or suggestion.startswith("  ⚪"):
                self._log(suggestion, "info")
            else:
                self._log(suggestion, "info")
        
        # Show summary
        if plan.keep_pins:
            self._log(f"\n✅ Pins that can stay connected: {', '.join(map(str, plan.keep_pins))}", "success")
        
        if plan.move_pins:
            self._log(f"⚠️ {len(plan.move_pins)} pins need rewiring", "warning")
        
        # Offer to apply suggested mapping
        suggested = self.migration_helper.get_new_mapping_suggestion(from_chip, to_chip, old_mapping)
        if suggested:
            self._log("\n💡 Suggested mapping applied to form. Review and adjust as needed.", "info")
            self._apply_suggested_mapping(suggested)
    
    def _apply_suggested_mapping(self, suggested_mapping: Dict[str, int]):
        """Apply a suggested mapping to the pin mapping panel"""
        for chip_pin, arduino_pin in suggested_mapping.items():
            if chip_pin in self.pin_mapping_panel.pin_entries:
                entry = self.pin_mapping_panel.pin_entries[chip_pin]
                entry.delete(0, 'end')
                entry.insert(0, str(arduino_pin))
    
    # =========================================================================
    # Utility Functions
    # =========================================================================
    
    def _clear_output(self):
        """Clear output and reset status"""
        self.output_panel.clear()
        self.status_panel.set_idle()
        self.status_panel.reset_stats()
        self.last_result = None
        self.pin_visualizer.reset()
        self.dashboard_panel.clear()
        self._log("🔄 Output cleared. Ready for new test.", "info")
    
    def _identify_chip(self):
        """Initiate chip identification"""
        if not self.arduino.connected:
            self._log("❌ Connect to Arduino first!", "error")
            return
        
        self._log("=" * 50, "info")
        self._log("🔍 CHIP IDENTIFICATION MODE", "info")
        self._log("=" * 50, "info")
        
        self.status_panel.set_testing()
        self.root.update()
        
        chip_id, confidence, message = self.tester.identify_chip(
            self._log, board=self.chip_panel.get_board()
        )
        
        if chip_id and confidence >= 80:
            self._log(f"\n✅ {message}", "success")
            self.status_panel.set_passed()
            self.status_panel.set_custom_text(f"Detected: {chip_id}", Theme.ACCENT_SUCCESS)
        elif chip_id and confidence >= 50:
            self._log(f"\n⚠️ {message}", "warning")
            self.status_panel.set_idle()
            self.status_panel.set_custom_text(f"Maybe: {chip_id}?", Theme.ACCENT_WARNING)
        else:
            self._log(f"\n❌ {message}", "error")
            self.status_panel.set_failed()
            self.status_panel.set_custom_text("Unknown chip", Theme.ACCENT_ERROR)

    def _get_manual_tester_context(self) -> Dict[str, Optional[Dict]]:
        """
        Snapshot the live chip selection and validated mapping for the add-on window.

        The manual tester reads from the same selected chip and mapping used by
        the automated workflow so there is one canonical wiring context.
        """
        chip_id = self.chip_panel.get_selected_chip()
        board = self.chip_panel.get_board()
        chip_data = self.chip_db.get_chip(chip_id, board=board) if chip_id else None
        mapping = self.pin_mapping_panel.get_mapping() if chip_data else None
        return {
            "chip_id": chip_id,
            "chip_data": chip_data,
            "board": board,
            "mapping": mapping,
            "connected": self.arduino.connected and self.arduino.commands is not None,
        }

    def _on_manual_tester_closed(self):
        """Release the window reference after the add-on closes."""
        self.manual_tester_window = None

    def _open_manual_tester(self):
        """Open or focus the separate manual tester window."""
        if self.manual_tester_window is not None:
            try:
                if self.manual_tester_window.window.winfo_exists():
                    self.manual_tester_window.focus()
                    return
            except Exception:
                self.manual_tester_window = None

        self.manual_tester_window = ManualTesterWindow(
            parent=self.root,
            controller=self.manual_tester_controller,
            get_current_context=self._get_manual_tester_context,
            is_main_app_busy=lambda: self.is_testing or self.counter_running,
            on_close=self._on_manual_tester_closed,
        )

    def _show_help(self):
        """Open help dialog"""
        HelpDialog(self.root)
    
    # =========================================================================
    # Application Control
    # =========================================================================
    
    def run(self):
        """Start the application main loop"""
        logger.info("Starting main event loop")
        self.root.mainloop()
    
    def quit(self):
        """Clean up and exit"""
        logger.info("Application shutting down")
        if self.arduino.connected:
            self.arduino.disconnect()
        self.root.quit()


def main():
    """Application entry point"""
    app = ICTesterApp()
    app.run()


if __name__ == "__main__":
    main()
