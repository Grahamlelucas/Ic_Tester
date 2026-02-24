# ic_tester_app/gui/app.py
# Last edited: 2026-01-19
# Purpose: Main GUI application class that integrates all panels and coordinates testing
# Dependencies: tkinter, threading

"""
Main GUI Application module.
Coordinates all GUI panels and manages the IC testing workflow.
"""

import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict

from .theme import Theme, get_fonts
from .widgets import ModernButton, HelpDialog
from .panels import ConnectionPanel, ChipPanel, PinMappingPanel, StatusPanel, OutputPanel

from ..arduino import ArduinoConnection
from ..chips import (
    ChipDatabase,
    ICTester,
)
from ..chips.migration import PinMigrationHelper
from ..config import Config
from ..logger import get_logger, setup_logging
from ..intelligence import ChipKnowledge, SessionTracker, PatternAnalyzer, ChipEducator

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
        # Setup logging first
        setup_logging()
        logger.info(f"Starting {Config.APP_NAME} v{Config.APP_VERSION}")
        
        # Ensure directories exist
        Config.ensure_directories()
        
        # Create main window
        self.root = tk.Tk()
        self.root.title(Config.APP_NAME)
        self.root.geometry(f"{Config.WINDOW_START_WIDTH}x{Config.WINDOW_START_HEIGHT}")
        self.root.minsize(Config.WINDOW_MIN_WIDTH, Config.WINDOW_MIN_HEIGHT)
        self.root.configure(bg=Theme.BG_DARK)
        
        # Get fonts
        self.fonts = get_fonts()
        
        # Initialize core components
        self.arduino = ArduinoConnection()
        self.chip_db = ChipDatabase(
            board=Config.DEFAULT_BOARD
        )
        self.tester = ICTester(self.arduino, self.chip_db)
        
        # Initialize intelligence system
        self.knowledge = ChipKnowledge()
        self.session_tracker = SessionTracker()
        self.pattern_analyzer = PatternAnalyzer()
        self.educator = ChipEducator(self.knowledge, self.session_tracker)
        self.migration_helper = PinMigrationHelper(self.chip_db)
        
        # State tracking
        self.is_testing = False
        self._previous_chip_id = None
        self._previous_chip_mapping = None
        self.counter_running = False
        self.last_result = None
        self.test_start_time = None
        self.connection_check_interval = Config.CONNECTION_CHECK_INTERVAL
        self._last_connect_time = time.time()  # Initialize to now (prevents early disconnect)
        self._monitor_enabled = True  # Can disable monitor temporarily
        
        # Build UI
        self._create_ui()
        
        # Auto-scan ports on startup
        self.root.after(100, self._scan_ports)
        
        # Start connection monitoring
        self._start_connection_monitor()
        self._start_event_poller()
        
        logger.info("Application initialized successfully")
    
    def _create_ui(self):
        """Build the main UI layout using grid for better control"""
        # Configure root grid weights for responsive layout
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Main container with padding
        main = tk.Frame(self.root, bg=Theme.BG_DARK)
        main.grid(row=0, column=0, sticky="nsew", padx=25, pady=20)
        
        # Configure main grid: header row + content row
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)
        
        # Header
        self._create_header(main)
        
        # Content area using grid (3 columns: left, center, right)
        content = tk.Frame(main, bg=Theme.BG_DARK)
        content.grid(row=1, column=0, sticky="nsew", pady=(20, 0))
        
        # Configure content columns with proper weights
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=0, minsize=300)   # Left: fixed width
        content.grid_columnconfigure(1, weight=0, minsize=320)   # Center: fixed width
        content.grid_columnconfigure(2, weight=1, minsize=400)   # Right: expands
        
        # Left column - Connection, Chip Selection, Status
        left_col = tk.Frame(content, bg=Theme.BG_DARK)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        
        self.connection_panel = ConnectionPanel(
            left_col,
            on_connect=self._connect_arduino,
            on_disconnect=self._disconnect_arduino,
            on_scan=self._scan_ports
        )
        
        self.chip_panel = ChipPanel(
            left_col,
            chip_ids=self.chip_db.get_all_chip_ids(),
            on_chip_selected=self._on_chip_selected,
            on_run_test=self._run_test,
            on_run_counter=self._start_counter,
            on_stop=self._stop_counter,
            board=self.chip_db.get_board()
        )
        
        self.status_panel = StatusPanel(left_col)
        
        # Center column - Pin Mapping (expandable)
        center_col = tk.Frame(content, bg=Theme.BG_DARK)
        center_col.grid(row=0, column=1, sticky="nsew", padx=(0, 15))
        
        self.pin_mapping_panel = PinMappingPanel(
            center_col,
            log_callback=self._log
        )
        
        # Right column - Output Log (main content, expands)
        right_col = tk.Frame(content, bg=Theme.BG_DARK)
        right_col.grid(row=0, column=2, sticky="nsew")
        
        self.output_panel = OutputPanel(
            right_col,
            on_clear=self._clear_output
        )
        
        # Trigger initial chip selection
        if self.chip_db.get_chip_count() > 0:
            chip_id = self.chip_panel.get_selected_chip()
            if chip_id:
                self._on_chip_selected(chip_id)
    
    def _create_header(self, parent):
        """Create the application header"""
        header = tk.Frame(parent, bg=Theme.BG_DARK)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
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
        """Connect to the selected Arduino port"""
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
        
        # Set grace period BEFORE connect (prevent race condition with monitor)
        self._last_connect_time = time.time()
        
        if self.arduino.connect(port):
            self.connection_panel.set_connected()
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
            # Only check if monitor is enabled and connected
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
        """Parse firmware EVT lines and log without affecting test flow."""
        try:
            parts = event_line.split(",")
            if len(parts) < 2 or parts[0] != "EVT":
                self._log(f"📨 {event_line}", "info")
                return

            category = parts[1]
            if category == "WARN":
                message = ",".join(parts[2:]) if len(parts) > 2 else "Firmware warning"
                self._log(f"⚠️ TFT WARN: {message}", "warning")
                return

            if category == "TOUCH" and len(parts) >= 4:
                subtype = parts[2]
                value = ",".join(parts[3:])
                self._log(f"👆 TFT Touch {subtype}: {value}", "info")
                return

            if category == "SETTING" and len(parts) >= 5 and parts[2] == "CHANGED":
                key = parts[3]
                value = ",".join(parts[4:])
                self._log(f"⚙️ TFT Setting changed: {key}={value}", "info")
                return

            if category == "DIAG" and len(parts) >= 4:
                metric = parts[2]
                value = ",".join(parts[3:])
                self._log(f"🩺 TFT Diag {metric}: {value}", "info")
                return

            self._log(f"📨 {event_line}", "info")
        except Exception as e:
            logger.debug(f"Failed to parse firmware event '{event_line}': {e}")
    
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
        """Run test on the selected chip"""
        # Validate connection
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
        
        # Validate pin mapping
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
        
        # Start test
        self.is_testing = True
        self.test_start_time = __import__('time').time()
        self.status_panel.set_testing()
        self.chip_panel.set_testing(True)
                
        self.output_panel.log_test_start(chip_id)
        
        # Show pre-test hints from intelligence system
        hints = self.educator.get_pre_test_hints(chip_id)
        for hint in hints[:2]:  # Show top 2 hints
            self._log(f"💡 {hint.title}: {hint.content}", "info")
        
        # Store mapping for later analysis
        self._current_test_mapping = user_mapping
        
        # Run in thread
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
        """Display test results with intelligence analysis"""
        import time
        self.is_testing = False
        self.chip_panel.set_testing(False)
        self.last_result = results
        
        # Calculate test duration
        duration = time.time() - self.test_start_time if self.test_start_time else 0
        
        # Record test in session tracker for learning
        chip_id = results.get('chipId', self.chip_panel.get_selected_chip())
        self.session_tracker.record_test(
            chip_id=chip_id,
            results=results,
            pin_mapping=getattr(self, '_current_test_mapping', {}),
            duration=duration
        )
        
        # Get confidence score from pattern analyzer
        historical_rate = self.session_tracker.get_success_rate(chip_id)
        confidence = self.pattern_analyzer.calculate_confidence(
            chip_id, results, historical_rate
        )
        
        # Check for pin verification failures
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
        
        if results.get('success'):
            pass
        else:
            # Try to identify correct chip
            self._try_identify_wrong_chip(results)
    
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
