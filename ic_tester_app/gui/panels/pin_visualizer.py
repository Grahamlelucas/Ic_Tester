# ic_tester_app/gui/panels/pin_visualizer.py
# Last edited: 2026-03-19
# Purpose: Live pin state visualization with interactive chip layout and real-time diagnostic feedback
# Dependencies: tkinter
# Related: gui/theme.py, gui/app.py, diagnostics/diagnostic_report.py

"""
Graphical chip/pin visualizer.

This panel translates abstract pin diagnostics into a physical DIP-style layout
so users can map software feedback back onto the real chip sitting on the
breadboard. It is primarily a visualization layer; it consumes test/report
data produced elsewhere and redraws the package accordingly.
"""

import tkinter as tk
from typing import Dict, Optional, Any, List

from ..theme import Theme, get_fonts
from ...logger import get_logger

logger = get_logger("gui.panels.pin_visualizer")


class PinVisualizer(tk.Frame):
    """
    Graphical IC chip visualization with live pin state indicators.

    Renders a DIP package outline with numbered pins. Each pin is drawn as
    a colored circle that updates in real time during testing:
    - Gray: idle/unmapped
    - Green: pin reading correctly
    - Red: pin failing
    - Yellow: intermittent/warning
    - Blue: currently being tested

    Attributes:
        canvas: The Tk Canvas used for drawing
        pin_items: Dict mapping chip_pin → canvas item IDs for updating
    """

    # Layout constants
    CHIP_WIDTH = 120
    PIN_SPACING = 28
    PIN_RADIUS = 8
    LABEL_OFFSET = 18
    CANVAS_PAD = 40

    # State colors
    COLOR_IDLE = "#4a5568"
    COLOR_HIGH = "#48bb78"
    COLOR_LOW = "#2d3748"
    COLOR_PASS = "#06d6a0"
    COLOR_FAIL = "#ef476f"
    COLOR_WARN = "#ffd166"
    COLOR_ACTIVE = "#4361ee"
    COLOR_ERROR = "#e53e3e"
    COLOR_VCC = "#f56565"
    COLOR_GND = "#2b6cb0"

    def __init__(self, parent, **kwargs):
        """
        Args:
            parent: Parent tkinter widget
        """
        super().__init__(parent, bg=Theme.BG_DARK, **kwargs)
        self.fonts = get_fonts()

        self.pin_items: Dict[int, Dict[str, Any]] = {}
        self.pin_labels: Dict[int, int] = {}
        self.pin_states: Dict[int, str] = {}
        self.pin_severities: Dict[int, str] = {}
        self.num_pins = 0
        self.chip_id = ""
        self._tooltip_id = None
        self._tooltip_widget = None

        # Header
        header = tk.Frame(self, bg=Theme.BG_CARD, padx=10, pady=6)
        header.pack(fill=tk.X, pady=(0, 5))
        tk.Label(
            header, text="🔌 Chip Layout", font=self.fonts["subheading"],
            bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY,
        ).pack(side=tk.LEFT)

        self._status_label = tk.Label(
            header, text="No chip loaded", font=self.fonts["small"],
            bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY,
        )
        self._status_label.pack(side=tk.RIGHT)

        # Canvas
        self.canvas = tk.Canvas(
            self, bg=Theme.BG_DARK, highlightthickness=0,
            width=260, height=300,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Legend
        legend = tk.Frame(self, bg=Theme.BG_DARK)
        legend.pack(fill=tk.X, padx=5, pady=(0, 5))
        for color, label in [
            (self.COLOR_PASS, "Pass"),
            (self.COLOR_FAIL, "Fail"),
            (self.COLOR_WARN, "Warn"),
            (self.COLOR_IDLE, "Idle"),
        ]:
            dot = tk.Canvas(legend, width=10, height=10, bg=Theme.BG_DARK, highlightthickness=0)
            dot.pack(side=tk.LEFT, padx=(4, 1))
            dot.create_oval(1, 1, 9, 9, fill=color, outline="")
            tk.Label(legend, text=label, font=self.fonts["small"],
                     bg=Theme.BG_DARK, fg=Theme.TEXT_MUTED).pack(side=tk.LEFT, padx=(0, 6))

        logger.debug("PinVisualizer initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_chip(self, chip_data: Dict):
        """
        Draw chip layout from chip definition data.

        Args:
            chip_data: Chip definition dict with pinout info
        """
        self.canvas.delete("all")
        self.pin_items.clear()
        self.pin_labels.clear()
        self.pin_states.clear()
        self.pin_severities.clear()

        self.chip_id = chip_data.get("chipId", "?")
        pinout = chip_data.get("pinout", {})
        package = chip_data.get("package", "14-pin DIP")

        # Prefer the declared package string, but fall back to inferring the pin
        # count from the actual pinout when the package metadata is incomplete.
        try:
            self.num_pins = int(package.split("-")[0])
        except (ValueError, IndexError):
            all_pins = set()
            for p in pinout.get("inputs", []):
                all_pins.add(p["pin"])
            for p in pinout.get("outputs", []):
                all_pins.add(p["pin"])
            vcc = pinout.get("vcc")
            gnd = pinout.get("gnd")
            if vcc:
                all_pins.add(vcc)
            if gnd:
                all_pins.add(gnd)
            self.num_pins = max(all_pins) if all_pins else 14

        # Build one lookup describing every visible pin so the draw/update code
        # can treat inputs, outputs, and power pins uniformly.
        pin_info = {}
        for p in pinout.get("inputs", []):
            pin_info[p["pin"]] = {"name": p["name"], "type": "input", "desc": p.get("description", "")}
        for p in pinout.get("outputs", []):
            pin_info[p["pin"]] = {"name": p["name"], "type": "output", "desc": p.get("description", "")}
        vcc_pin = pinout.get("vcc")
        gnd_pin = pinout.get("gnd")
        if vcc_pin:
            pin_info[vcc_pin] = {"name": "VCC", "type": "power", "desc": "+5V Power"}
        if gnd_pin:
            pin_info[gnd_pin] = {"name": "GND", "type": "power", "desc": "Ground"}

        self._draw_chip(pin_info, vcc_pin, gnd_pin)
        self._status_label.config(text=f"{self.chip_id} ({self.num_pins}-pin)")

    def update_pin_state(self, chip_pin: int, state: str):
        """
        Update the visual state of a single pin.

        Args:
            chip_pin: IC pin number
            state: 'HIGH', 'LOW', 'ERROR', 'ACTIVE', 'IDLE'
        """
        self.pin_states[chip_pin] = state
        if chip_pin in self.pin_items:
            color = self._state_to_color(state)
            self.canvas.itemconfig(self.pin_items[chip_pin]["oval"], fill=color)

    def update_pin_severity(self, chip_pin: int, severity: str):
        """
        Update pin color based on diagnostic severity.

        Args:
            chip_pin: IC pin number
            severity: 'ok', 'warning', 'error', 'critical'
        """
        self.pin_severities[chip_pin] = severity
        if chip_pin in self.pin_items:
            color_map = {
                "ok": self.COLOR_PASS,
                "warning": self.COLOR_WARN,
                "error": self.COLOR_FAIL,
                "critical": self.COLOR_ERROR,
            }
            color = color_map.get(severity, self.COLOR_IDLE)
            self.canvas.itemconfig(self.pin_items[chip_pin]["oval"], fill=color)

    def update_from_test_result(self, test_result: Dict):
        """
        Bulk update all pin visuals from a test result's pinDiagnostics.

        Args:
            test_result: ICTester run_test() result dict
        """
        pin_diag = test_result.get("pinDiagnostics", {})
        # We need to map pin names back to chip pin numbers
        for pin_name, diag in pin_diag.items():
            chip_pin = diag.get("chipPin")
            if chip_pin is None:
                continue
            stuck = diag.get("stuckState", "") or ""
            tested = diag.get("timesTested", 0)
            correct = diag.get("timesCorrect", 0)

            if stuck == "NO_RESPONSE":
                self.update_pin_severity(chip_pin, "critical")
            elif stuck in ("HIGH", "LOW"):
                self.update_pin_severity(chip_pin, "error")
            elif stuck == "INTERMITTENT":
                self.update_pin_severity(chip_pin, "warning")
            elif tested > 0 and correct == tested:
                self.update_pin_severity(chip_pin, "ok")
            elif tested > 0:
                pct = correct / tested
                if pct >= 0.9:
                    self.update_pin_severity(chip_pin, "ok")
                elif pct >= 0.5:
                    self.update_pin_severity(chip_pin, "warning")
                else:
                    self.update_pin_severity(chip_pin, "error")

    def update_from_diagnostic_report(self, report):
        """
        Update pin visuals from a DiagnosticReport object.

        Args:
            report: DiagnosticReport instance
        """
        for pin_name, entry in report.pin_diagnostics.items():
            chip_pin = entry.chip_pin
            if isinstance(chip_pin, int):
                self.update_pin_severity(chip_pin, entry.severity)

    def reset(self):
        """Reset all pins to idle state."""
        for chip_pin in self.pin_items:
            self.update_pin_state(chip_pin, "IDLE")
        self.pin_severities.clear()

    # ------------------------------------------------------------------
    # Drawing internals
    # ------------------------------------------------------------------

    def _draw_chip(self, pin_info: Dict, vcc_pin: Optional[int], gnd_pin: Optional[int]):
        """Draw the DIP chip outline and pins on the canvas."""
        half = self.num_pins // 2
        chip_h = half * self.PIN_SPACING + 20
        cx = 130
        cy_start = self.CANVAS_PAD

        # Chip body
        x1 = cx - self.CHIP_WIDTH // 2
        y1 = cy_start
        x2 = cx + self.CHIP_WIDTH // 2
        y2 = cy_start + chip_h
        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            fill="#2d3748", outline="#4a5568", width=2,
        )

        # Notch at top
        notch_r = 8
        self.canvas.create_arc(
            cx - notch_r, y1 - notch_r, cx + notch_r, y1 + notch_r,
            start=0, extent=180, style=tk.ARC, outline="#4a5568", width=2,
        )

        # Chip label
        self.canvas.create_text(
            cx, (y1 + y2) // 2, text=self.chip_id,
            font=self.fonts["small"], fill=Theme.TEXT_SECONDARY,
        )

        # Left side pins (1 to half)
        for i in range(half):
            pin_num = i + 1
            py = cy_start + 15 + i * self.PIN_SPACING
            px = x1 - self.LABEL_OFFSET

            info = pin_info.get(pin_num, {})
            color = self._get_initial_color(pin_num, info, vcc_pin, gnd_pin)

            oval = self.canvas.create_oval(
                px - self.PIN_RADIUS, py - self.PIN_RADIUS,
                px + self.PIN_RADIUS, py + self.PIN_RADIUS,
                fill=color, outline="#718096", width=1,
            )
            # Pin number label
            lbl = self.canvas.create_text(
                px - self.PIN_RADIUS - 10, py,
                text=str(pin_num), font=self.fonts["small"],
                fill=Theme.TEXT_SECONDARY, anchor=tk.E,
            )
            # Pin name on inside
            name_text = info.get("name", "")
            self.canvas.create_text(
                x1 + 5, py, text=name_text, font=self.fonts["small"],
                fill=Theme.TEXT_MUTED, anchor=tk.W,
            )

            self.pin_items[pin_num] = {"oval": oval, "label": lbl, "info": info}
            self._bind_tooltip(oval, pin_num, info)

        # Right side pins (num_pins down to half+1)
        for i in range(half):
            pin_num = self.num_pins - i
            py = cy_start + 15 + i * self.PIN_SPACING
            px = x2 + self.LABEL_OFFSET

            info = pin_info.get(pin_num, {})
            color = self._get_initial_color(pin_num, info, vcc_pin, gnd_pin)

            oval = self.canvas.create_oval(
                px - self.PIN_RADIUS, py - self.PIN_RADIUS,
                px + self.PIN_RADIUS, py + self.PIN_RADIUS,
                fill=color, outline="#718096", width=1,
            )
            lbl = self.canvas.create_text(
                px + self.PIN_RADIUS + 10, py,
                text=str(pin_num), font=self.fonts["small"],
                fill=Theme.TEXT_SECONDARY, anchor=tk.W,
            )
            name_text = info.get("name", "")
            self.canvas.create_text(
                x2 - 5, py, text=name_text, font=self.fonts["small"],
                fill=Theme.TEXT_MUTED, anchor=tk.E,
            )

            self.pin_items[pin_num] = {"oval": oval, "label": lbl, "info": info}
            self._bind_tooltip(oval, pin_num, info)

        # Resize canvas to fit
        total_h = chip_h + self.CANVAS_PAD * 2
        self.canvas.config(height=total_h)

    def _get_initial_color(
        self, pin_num: int, info: Dict, vcc_pin: Optional[int], gnd_pin: Optional[int]
    ) -> str:
        """Determine initial color for a pin based on its type."""
        if pin_num == vcc_pin:
            return self.COLOR_VCC
        if pin_num == gnd_pin:
            return self.COLOR_GND
        pin_type = info.get("type", "")
        if pin_type == "power":
            return self.COLOR_VCC if "VCC" in info.get("name", "") else self.COLOR_GND
        return self.COLOR_IDLE

    def _state_to_color(self, state: str) -> str:
        """Map a pin state string to a display color."""
        return {
            "HIGH": self.COLOR_HIGH,
            "LOW": self.COLOR_LOW,
            "ERROR": self.COLOR_ERROR,
            "ACTIVE": self.COLOR_ACTIVE,
            "PASS": self.COLOR_PASS,
            "FAIL": self.COLOR_FAIL,
            "WARN": self.COLOR_WARN,
        }.get(state, self.COLOR_IDLE)

    # ------------------------------------------------------------------
    # Tooltips
    # ------------------------------------------------------------------

    def _bind_tooltip(self, oval_id: int, pin_num: int, info: Dict):
        """Bind hover tooltip to a pin oval."""
        self.canvas.tag_bind(oval_id, "<Enter>", lambda e, p=pin_num, i=info: self._show_tooltip(e, p, i))
        self.canvas.tag_bind(oval_id, "<Leave>", lambda e: self._hide_tooltip())

    def _show_tooltip(self, event, pin_num: int, info: Dict):
        """Display tooltip near cursor."""
        self._hide_tooltip()
        name = info.get("name", f"Pin {pin_num}")
        desc = info.get("desc", "")
        ptype = info.get("type", "unknown")
        state = self.pin_states.get(pin_num, "idle")
        severity = self.pin_severities.get(pin_num, "")

        text = f"Pin {pin_num}: {name}\nType: {ptype}\nState: {state}"
        if severity:
            text += f"\nStatus: {severity}"
        if desc:
            text += f"\n{desc}"

        self._tooltip_widget = tk.Toplevel(self)
        self._tooltip_widget.wm_overrideredirect(True)
        self._tooltip_widget.wm_geometry(f"+{event.x_root + 15}+{event.y_root + 10}")

        lbl = tk.Label(
            self._tooltip_widget, text=text, font=self.fonts["small"],
            bg="#2d3748", fg=Theme.TEXT_PRIMARY,
            relief=tk.SOLID, borderwidth=1, padx=6, pady=4,
            justify=tk.LEFT,
        )
        lbl.pack()

    def _hide_tooltip(self):
        """Remove tooltip."""
        if self._tooltip_widget:
            self._tooltip_widget.destroy()
            self._tooltip_widget = None
