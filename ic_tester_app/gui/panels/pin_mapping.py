# ic_tester_app/gui/panels/pin_mapping.py
# Last edited: 2026-01-19
# Purpose: Dynamic pin mapping panel for user-defined Arduino pin assignments
# Dependencies: tkinter, json, pathlib

"""
Pin Mapping Panel module.
Allows users to define which Arduino pins connect to each chip pin.
Includes validation, save/load functionality.
"""

import json
import tkinter as tk
from pathlib import Path
from typing import Callable, Dict, Optional, Any

from ..theme import Theme, get_fonts
from ..widgets import ModernButton
from ...config import Config
from ...logger import get_logger

logger = get_logger("gui.panels.pin_mapping")


class PinMappingPanel:
    """
    Dynamic pin mapping configuration panel.
    
    Allows users to:
    - Enter Arduino pin numbers for each chip pin
    - Validate mappings (no duplicates, valid pin range)
    - Save/load mappings to JSON files
    - Clear all mappings
    
    Attributes:
        frame: The main frame widget
        pin_entries: Dict mapping chip pin numbers to Entry widgets
        user_pin_mapping: Dict of validated {chip_pin: arduino_pin} mappings
    """
    
    def __init__(self, parent, log_callback: Callable):
        """
        Initialize the pin mapping panel.
        
        Args:
            parent: Parent tkinter widget
            log_callback: Function to call for logging messages
        """
        self.parent = parent
        self.log = log_callback
        self.fonts = get_fonts()
        
        self.pin_entries: Dict[int, tk.Entry] = {}
        self.user_pin_mapping: Dict[int, Any] = {}
        
        self._create_panel()
        logger.debug("PinMappingPanel initialized")
    
    def _create_panel(self):
        """Build the panel UI"""
        # Card container
        self.frame = tk.Frame(self.parent, bg=Theme.BG_CARD, padx=15, pady=15)
        self.frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # Header with title and buttons
        header = tk.Frame(self.frame, bg=Theme.BG_CARD)
        header.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(header, text="Pin Mapping", font=self.fonts['subheading'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY).pack(side=tk.LEFT)
        
        # Buttons row (Validate, Save, Clear - Load removed since chip select auto-loads)
        btn_frame = tk.Frame(header, bg=Theme.BG_CARD)
        btn_frame.pack(side=tk.RIGHT)
        
        ModernButton(btn_frame, "Clear", self.clear,
                    width=55, height=30, bg_color=Theme.BG_LIGHT).pack(side=tk.LEFT, padx=(0, 8))
        
        ModernButton(btn_frame, "Save", self.save,
                    width=55, height=30, bg_color=Theme.ACCENT_SUCCESS).pack(side=tk.LEFT, padx=(0, 8))
        
        ModernButton(btn_frame, "Validate", self.validate,
                    width=70, height=30, bg_color=Theme.ACCENT_INFO).pack(side=tk.LEFT)
        
        # Instructions
        tk.Label(self.frame, text="Enter Arduino pin for each chip pin:",
                font=self.fonts['small'], bg=Theme.BG_CARD, 
                fg=Theme.TEXT_MUTED).pack(anchor=tk.W, pady=(0, 5))
        
        self.requirements_label = tk.Label(
            self.frame,
            text="",
            font=self.fonts['small'],
            bg=Theme.BG_CARD,
            fg=Theme.ACCENT_WARNING,
            justify=tk.LEFT,
            wraplength=420
        )
        self.requirements_label.pack(anchor=tk.W, pady=(0, 8))
        
        # Scrollable frame for pin entries
        canvas_frame = tk.Frame(self.frame, bg=Theme.BG_CARD)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        # Canvas with scrollbar
        self.pin_canvas = tk.Canvas(canvas_frame, bg=Theme.BG_CARD, 
                                    highlightthickness=0, height=300)
        scrollbar = tk.Scrollbar(canvas_frame, orient="vertical", 
                                command=self.pin_canvas.yview)
        
        self.pin_mapping_frame = tk.Frame(self.pin_canvas, bg=Theme.BG_CARD)
        
        self.pin_canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.pin_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.pin_canvas_window = self.pin_canvas.create_window((0, 0), 
                                                               window=self.pin_mapping_frame, 
                                                               anchor="nw")
        
        # Bind scroll events
        self.pin_mapping_frame.bind("<Configure>", self._on_frame_configure)
        self.pin_canvas.bind("<Configure>", self._on_canvas_configure)
        
        # Status label
        self.status_label = tk.Label(self.frame, text="Select a chip to configure pins",
                                    font=self.fonts['small'], bg=Theme.BG_CARD,
                                    fg=Theme.TEXT_MUTED)
        self.status_label.pack(anchor=tk.W, pady=(10, 0))
    
    def _on_frame_configure(self, event):
        """Update scroll region when frame size changes"""
        self.pin_canvas.configure(scrollregion=self.pin_canvas.bbox("all"))
    
    def _on_canvas_configure(self, event):
        """Update frame width when canvas size changes"""
        self.pin_canvas.itemconfig(self.pin_canvas_window, width=event.width)
    
    def populate(self, chip_data: Optional[Dict]):
        """
        Populate pin mapping entries based on selected chip.
        
        Args:
            chip_data: Chip definition dictionary or None to clear
        """
        # Clear existing entries
        for widget in self.pin_mapping_frame.winfo_children():
            widget.destroy()
        self.pin_entries.clear()
        self.user_pin_mapping.clear()
        
        if not chip_data:
            self.requirements_label.config(text="")
            self.status_label.config(text="Select a chip to configure pins",
                                    fg=Theme.TEXT_MUTED)
            return
        
        self.requirements_label.config(
            text=self._format_hardware_requirements(chip_data)
        )
        
        pinout = chip_data.get('pinout', {})
        
        # Get all pin numbers and sort them
        pin_numbers = []
        for key in pinout.keys():
            if key not in ['vcc', 'gnd', 'description', 'inputs', 'outputs', 'noConnect']:
                try:
                    pin_numbers.append(int(key))
                except ValueError:
                    pass
        
        # Also get pins from inputs/outputs arrays
        for input_pin in pinout.get('inputs', []):
            pin_num = input_pin.get('pin')
            if pin_num and pin_num not in pin_numbers:
                pin_numbers.append(pin_num)
        
        for output_pin in pinout.get('outputs', []):
            pin_num = output_pin.get('pin')
            if pin_num and pin_num not in pin_numbers:
                pin_numbers.append(pin_num)
        
        # Add VCC and GND if defined
        if pinout.get('vcc'):
            pin_numbers.append(pinout['vcc'])
        if pinout.get('gnd'):
            pin_numbers.append(pinout['gnd'])
        
        pin_numbers = sorted(set(pin_numbers))
        
        # Build pin name lookup
        pin_names = {}
        for key, value in pinout.items():
            if key.isdigit():
                pin_names[int(key)] = value
        for input_pin in pinout.get('inputs', []):
            pin_names[input_pin['pin']] = input_pin.get('name', f"Pin {input_pin['pin']}")
        for output_pin in pinout.get('outputs', []):
            pin_names[output_pin['pin']] = output_pin.get('name', f"Pin {output_pin['pin']}")
        if pinout.get('vcc'):
            pin_names[pinout['vcc']] = 'VCC'
        if pinout.get('gnd'):
            pin_names[pinout['gnd']] = 'GND'
        
        # Create header row
        header_frame = tk.Frame(self.pin_mapping_frame, bg=Theme.BG_CARD)
        header_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(header_frame, text="Chip Pin", font=self.fonts['small'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY, width=8).pack(side=tk.LEFT)
        tk.Label(header_frame, text="Function", font=self.fonts['small'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY, width=10).pack(side=tk.LEFT, padx=(5, 0))
        tk.Label(header_frame, text="Arduino Pin", font=self.fonts['small'],
                bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY, width=10).pack(side=tk.LEFT, padx=(5, 0))
        
        # Create entry for each pin
        for pin_num in pin_numbers:
            pin_name = pin_names.get(pin_num, f"Pin {pin_num}")
            
            row = tk.Frame(self.pin_mapping_frame, bg=Theme.BG_CARD)
            row.pack(fill=tk.X, pady=2)
            
            # Pin number
            tk.Label(row, text=f"{pin_num}", font=self.fonts['body'],
                    bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY, width=8,
                    anchor=tk.W).pack(side=tk.LEFT)
            
            # Pin function name
            display_name = pin_name[:10] if len(str(pin_name)) > 10 else pin_name
            tk.Label(row, text=str(display_name), font=self.fonts['small'],
                    bg=Theme.BG_CARD, fg=Theme.TEXT_MUTED, width=10,
                    anchor=tk.W).pack(side=tk.LEFT, padx=(5, 0))
            
            # Arduino pin entry
            entry = tk.Entry(row, width=8, font=self.fonts['body'],
                           bg=Theme.BG_LIGHT, fg=Theme.TEXT_PRIMARY,
                           insertbackground=Theme.TEXT_PRIMARY,
                           relief=tk.FLAT)
            entry.pack(side=tk.LEFT, padx=(5, 0))
            
            # Check if this is VCC or GND
            if str(pin_name).upper() in ['VCC', 'GND', '+5V', '5V', 'GROUND']:
                entry.insert(0, "PWR")
                entry.config(state='readonly', fg=Theme.ACCENT_WARNING)
            
            self.pin_entries[pin_num] = entry
        
        chip_name = chip_data.get('name', 'chip')
        self.status_label.config(
            text=f"Configure {len(pin_numbers)} pins for {chip_name}",
            fg=Theme.TEXT_SECONDARY
        )
        
        logger.debug(f"Populated {len(pin_numbers)} pins for chip")
    
    def _format_hardware_requirements(self, chip_data: Dict[str, Any]) -> str:
        """
        Build a one-block message for chip-specific wiring requirements.
        """
        requirements = chip_data.get("hardwareRequirements", [])
        if not requirements:
            return ""
        
        formatted = []
        for req in requirements:
            if isinstance(req, str):
                formatted.append(req)
                continue
            
            if not isinstance(req, dict):
                continue
            
            description = str(req.get("description", "")).strip()
            if description:
                formatted.append(description)
                continue
            
            req_type = str(req.get("type", "")).lower()
            pin = req.get("pin")
            signal = req.get("signal")
            target = req.get("target")
            resistor = req.get("resistor")
            
            if req_type == "pullup" and pin:
                signal_text = f" ({signal})" if signal else ""
                resistor_text = f" using {resistor}" if resistor else ""
                target_text = f" to {target}" if target else ""
                formatted.append(
                    f"Add pull-up resistor{resistor_text} from pin {pin}{signal_text}{target_text}."
                )
            elif req_type == "pulldown" and pin:
                signal_text = f" ({signal})" if signal else ""
                resistor_text = f" using {resistor}" if resistor else ""
                target_text = f" to {target}" if target else ""
                formatted.append(
                    f"Add pull-down resistor{resistor_text} from pin {pin}{signal_text}{target_text}."
                )
        
        if not formatted:
            return ""
        
        return "Hardware requirement(s):\n• " + "\n• ".join(formatted)
    
    def validate(self) -> bool:
        """
        Validate all pin mappings.
        
        Checks:
        - All pins have values (except PWR)
        - No duplicate Arduino pins
        - Valid pin range for Mega 2560
        - Warns about reserved pins
        
        Returns:
            True if valid, False otherwise
        """
        if not self.pin_entries:
            self.log("⚠️ No chip selected for pin mapping", "warning")
            return False
        
        errors = []
        warnings = []
        used_pins = {}  # arduino_pin: chip_pin
        valid_mapping = {}
        
        for chip_pin, entry in self.pin_entries.items():
            value = entry.get().strip().upper()
            
            # Skip power pins
            if value == "PWR":
                valid_mapping[chip_pin] = "PWR"
                continue
            
            # Check if empty
            if not value:
                errors.append(f"Chip pin {chip_pin}: No Arduino pin specified")
                entry.config(bg=Theme.ACCENT_ERROR)
                continue
            
            # Try to parse as integer
            try:
                arduino_pin = int(value)
            except ValueError:
                # Check for analog pins (A0-A15)
                if value.startswith('A') and value[1:].isdigit():
                    analog_num = int(value[1:])
                    if analog_num < 0 or analog_num > 15:
                        errors.append(f"Chip pin {chip_pin}: Invalid analog pin {value}")
                        entry.config(bg=Theme.ACCENT_ERROR)
                        continue
                    arduino_pin = 54 + analog_num  # A0 = 54 on Mega
                else:
                    errors.append(f"Chip pin {chip_pin}: Invalid value '{value}'")
                    entry.config(bg=Theme.ACCENT_ERROR)
                    continue
            
            # Validate pin range for Mega 2560
            if arduino_pin < 0 or arduino_pin > 69:
                errors.append(f"Chip pin {chip_pin}: Pin {arduino_pin} out of range (0-53, A0-A15)")
                entry.config(bg=Theme.ACCENT_ERROR)
                continue
            
            # Check for reserved pins
            if arduino_pin in Config.RESERVED_PINS:
                warnings.append(f"Chip pin {chip_pin}: Pin {arduino_pin} reserved for {Config.RESERVED_PINS[arduino_pin]}")
                entry.config(bg=Theme.ACCENT_WARNING)
            
            # Check for duplicates
            if arduino_pin in used_pins:
                errors.append(f"Chip pin {chip_pin}: Arduino pin {arduino_pin} already used by chip pin {used_pins[arduino_pin]}")
                entry.config(bg=Theme.ACCENT_ERROR)
                continue
            
            # Valid!
            used_pins[arduino_pin] = chip_pin
            valid_mapping[chip_pin] = arduino_pin
            entry.config(bg=Theme.BG_LIGHT)
        
        # Report results
        if errors:
            self.log("❌ Pin mapping validation failed:", "error")
            for err in errors:
                self.log(f"   • {err}", "error")
            self.status_label.config(text=f"❌ {len(errors)} error(s) found", fg=Theme.ACCENT_ERROR)
            logger.warning(f"Validation failed with {len(errors)} errors")
            return False
        
        if warnings:
            self.log("⚠️ Pin mapping warnings:", "warning")
            for warn in warnings:
                self.log(f"   • {warn}", "warning")
        
        # Store valid mapping
        self.user_pin_mapping = valid_mapping
        
        io_count = len([p for p in valid_mapping.values() if p != 'PWR'])
        self.log("✅ Pin mapping validated successfully!", "success")
        self.log(f"   Mapped {io_count} I/O pins", "success")
        self.status_label.config(text=f"✅ Valid - {len(valid_mapping)} pins mapped", fg=Theme.ACCENT_SUCCESS)
        
        logger.info(f"Validation passed: {io_count} I/O pins mapped")
        return True
    
    def clear(self):
        """Clear all pin mapping entries"""
        for entry in self.pin_entries.values():
            if entry.cget('state') != 'readonly':
                entry.delete(0, tk.END)
                entry.config(bg=Theme.BG_LIGHT)
        
        self.user_pin_mapping.clear()
        self.status_label.config(text="Pin mappings cleared", fg=Theme.TEXT_MUTED)
        self.log("🔄 Pin mappings cleared", "info")
        logger.debug("Pin mappings cleared")
    
    def save(self):
        """Save current pin mapping to a JSON file"""
        if not self.pin_entries:
            self.log("⚠️ No pin mapping to save", "warning")
            return
        
        # Need chip_id - this should be passed in
        # For now, we'll need to get it from somewhere
        chip_id = getattr(self, '_current_chip_id', None)
        if not chip_id:
            self.log("⚠️ No chip selected", "warning")
            return
        
        # Gather current entries
        mapping_data = {
            "chipId": chip_id,
            "mappings": {}
        }
        
        for chip_pin, entry in self.pin_entries.items():
            value = entry.get().strip()
            if value:
                mapping_data["mappings"][str(chip_pin)] = value
        
        # Create mappings directory if needed
        Config.PIN_MAPPINGS_DIR.mkdir(exist_ok=True)
        
        # Save to file
        filename = Config.PIN_MAPPINGS_DIR / f"{chip_id}_mapping.json"
        try:
            with open(filename, 'w') as f:
                json.dump(mapping_data, f, indent=2)
            self.log(f"✅ Pin mapping saved to {filename.name}", "success")
            self.status_label.config(text=f"Saved: {filename.name}", fg=Theme.ACCENT_SUCCESS)
            logger.info(f"Saved pin mapping to {filename}")
        except Exception as e:
            self.log(f"❌ Failed to save mapping: {e}", "error")
            logger.error(f"Failed to save mapping: {e}")
    
    def load(self, silent: bool = False):
        """Load pin mapping from a JSON file
        
        Args:
            silent: If True, don't show warnings when no mapping exists
        """
        chip_id = getattr(self, '_current_chip_id', None)
        if not chip_id:
            if not silent:
                self.log("⚠️ No chip selected", "warning")
            return
        
        filename = Config.PIN_MAPPINGS_DIR / f"{chip_id}_mapping.json"
        
        if not filename.exists():
            # Silent mode - don't warn about missing files (for auto-load)
            if not silent:
                self.log(f"⚠️ No saved mapping found for {chip_id}", "warning")
                self.log(f"   Looking for: {filename}", "info")
            return
        
        try:
            with open(filename, 'r') as f:
                mapping_data = json.load(f)
            
            # Verify chip ID matches
            if mapping_data.get("chipId") != chip_id:
                self.log(f"⚠️ Mapping file is for {mapping_data.get('chipId')}, not {chip_id}", "warning")
                return
            
            # Apply mappings to entries
            mappings = mapping_data.get("mappings", {})
            loaded_count = 0
            
            for chip_pin_str, arduino_pin_str in mappings.items():
                chip_pin = int(chip_pin_str)
                if chip_pin in self.pin_entries:
                    entry = self.pin_entries[chip_pin]
                    if entry.cget('state') != 'readonly':
                        entry.delete(0, tk.END)
                        entry.insert(0, arduino_pin_str)
                        loaded_count += 1
            
            self.log(f"✅ Loaded {loaded_count} pin mappings from {filename.name}", "success")
            self.status_label.config(text=f"Loaded: {filename.name}", fg=Theme.ACCENT_SUCCESS)
            logger.info(f"Loaded pin mapping from {filename}")
            
            # Auto-validate after loading
            self.validate()
            
        except Exception as e:
            self.log(f"❌ Failed to load mapping: {e}", "error")
            logger.error(f"Failed to load mapping: {e}")
    
    def set_chip_id(self, chip_id: str):
        """Set the current chip ID for save/load operations"""
        self._current_chip_id = chip_id
    
    def get_mapping(self) -> Optional[Dict[str, int]]:
        """
        Get the validated user-defined Arduino pin mapping.
        
        Returns:
            Dict of {chip_pin_str: arduino_pin_int} or None if invalid
        """
        if not self.user_pin_mapping:
            if not self.validate():
                return None
        
        # Convert to the format expected by the tester
        mapping = {}
        for chip_pin, arduino_pin in self.user_pin_mapping.items():
            if arduino_pin != "PWR":
                mapping[str(chip_pin)] = arduino_pin
        
        return mapping
