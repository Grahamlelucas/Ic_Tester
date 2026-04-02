# ic_tester_app/gui/panels/dashboard.py
# Last edited: 2026-03-19
# Purpose: Visual summary dashboard for test results, diagnostics, and ML predictions
# Dependencies: tkinter
# Related: gui/theme.py, diagnostics/diagnostic_report.py, intelligence/ml_classifier.py

"""
Diagnostics dashboard panel.

This is the condensed, at-a-glance view of everything the rest of the system
learned from a test. It is intentionally presentation-focused: it does not run
analysis itself, it renders already-computed results in a way that is easy to
scan during troubleshooting.
"""

import tkinter as tk
from typing import Dict, Optional, Any, List

from ..theme import Theme, get_fonts
from ...logger import get_logger

logger = get_logger("gui.panels.dashboard")


class DashboardPanel(tk.Frame):
    """
    Visual summary dashboard for test results and diagnostics.

    Shows at-a-glance status of the last test run including per-pin
    health indicators, confidence score, ML fault predictions, and
    actionable recommendations.

    Attributes:
        canvas: Main drawing canvas for gauges and charts
    """

    BAR_HEIGHT = 14
    BAR_WIDTH = 120
    BAR_SPACING = 22

    def __init__(self, parent, **kwargs):
        """
        Args:
            parent: Parent tkinter widget
        """
        super().__init__(parent, bg=Theme.BG_DARK, **kwargs)
        self.fonts = get_fonts()

        # Header
        header = tk.Frame(self, bg=Theme.BG_CARD, padx=10, pady=6)
        header.pack(fill=tk.X, pady=(0, 5))
        tk.Label(
            header, text="📊 Diagnostics Dashboard", font=self.fonts["subheading"],
            bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY,
        ).pack(side=tk.LEFT)

        # The dashboard can grow vertically once recommendations, per-pin bars,
        # and ML predictions are populated, so the content area scrolls.
        container = tk.Frame(self, bg=Theme.BG_DARK)
        container.pack(fill=tk.BOTH, expand=True)

        self._canvas_scroll = tk.Canvas(container, bg=Theme.BG_DARK, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient=tk.VERTICAL, command=self._canvas_scroll.yview)
        self._scroll_frame = tk.Frame(self._canvas_scroll, bg=Theme.BG_DARK)

        self._scroll_frame.bind(
            "<Configure>",
            lambda e: self._canvas_scroll.configure(scrollregion=self._canvas_scroll.bbox("all"))
        )
        self._canvas_scroll.create_window((0, 0), window=self._scroll_frame, anchor=tk.NW)
        self._canvas_scroll.configure(yscrollcommand=scrollbar.set)

        self._canvas_scroll.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind mousewheel ONLY to this dashboard's canvas (not bind_all!)
        self._bind_mousewheel(self._canvas_scroll)
        self._bind_mousewheel(self._scroll_frame)

        # Sections inside scroll frame
        self._result_frame = tk.Frame(self._scroll_frame, bg=Theme.BG_DARK)
        self._result_frame.pack(fill=tk.X, padx=10, pady=5)

        self._confidence_frame = tk.Frame(self._scroll_frame, bg=Theme.BG_DARK)
        self._confidence_frame.pack(fill=tk.X, padx=10, pady=5)

        self._pins_frame = tk.Frame(self._scroll_frame, bg=Theme.BG_DARK)
        self._pins_frame.pack(fill=tk.X, padx=10, pady=5)

        self._faults_frame = tk.Frame(self._scroll_frame, bg=Theme.BG_DARK)
        self._faults_frame.pack(fill=tk.X, padx=10, pady=5)

        self._recs_frame = tk.Frame(self._scroll_frame, bg=Theme.BG_DARK)
        self._recs_frame.pack(fill=tk.X, padx=10, pady=5)

        self._show_empty_state()
        logger.debug("DashboardPanel initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_from_test_result(self, test_result: Dict):
        """
        Populate dashboard from a standard test result dict.

        Args:
            test_result: ICTester run_test() result dict
        """
        # This lightweight path is used when only a raw test result is available
        # and the richer combined diagnostic report has not been generated yet.
        self._clear_all()

        chip_id = test_result.get("chipId", "?")
        success = test_result.get("success", False)
        passed = test_result.get("testsPassed", 0)
        total = test_result.get("testsRun", 0)
        failed = test_result.get("testsFailed", 0)

        # Result header
        self._draw_result_header(chip_id, success, passed, total)

        # Confidence (basic from pass rate)
        conf = passed / total if total > 0 else 0.0
        self._draw_confidence_gauge(conf)

        # Per-pin health bars
        pin_diag = test_result.get("pinDiagnostics", {})
        self._draw_pin_health(pin_diag)

    def update_from_diagnostic_report(self, report):
        """
        Populate dashboard from a DiagnosticReport.

        Args:
            report: DiagnosticReport instance
        """
        # This richer path consumes the merged diagnostic report that already
        # blends standard tests, statistics, stability, and fault analysis.
        self._clear_all()

        success = report.overall_result == "PASS"
        self._draw_result_header(
            report.chip_id, success,
            report.tests_passed, report.tests_run,
        )

        self._draw_confidence_gauge(report.overall_confidence)

        # Build pin_diag-like dict from report for health bars
        pin_diag = {}
        for pn, entry in report.pin_diagnostics.items():
            pin_diag[pn] = {
                "chipPin": entry.chip_pin,
                "arduinoPin": entry.arduino_pin,
                "pass_rate": entry.pass_rate,
                "severity": entry.severity,
                "detail": entry.detail,
                "stability_score": entry.stability_score,
            }
        self._draw_pin_health_from_report(pin_diag)

        # Fault summary
        if report.fault_summary:
            self._draw_faults(report.fault_summary)

        # Recommendations
        if report.recommendations:
            self._draw_recommendations(report.recommendations)

        # Signal info
        if report.avg_propagation_us > 0:
            self._draw_signal_info(report)

    def update_ml_predictions(self, predictions: Dict):
        """
        Add ML fault predictions to the dashboard.

        Args:
            predictions: Dict of pin_name → FaultPrediction
        """
        for widget in self._faults_frame.winfo_children():
            widget.destroy()

        if not predictions:
            return

        tk.Label(
            self._faults_frame, text="🧠 ML Fault Classification",
            font=self.fonts["subheading"], bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY,
        ).pack(anchor=tk.W, pady=(5, 3))

        for pin_name, pred in predictions.items():
            if pred.predicted_fault == "healthy":
                continue
            color = self._fault_color(pred.predicted_fault)
            row = tk.Frame(self._faults_frame, bg=Theme.BG_DARK)
            row.pack(fill=tk.X, pady=1)
            tk.Label(
                row, text=f"  • {pin_name}: ", font=self.fonts["body"],
                bg=Theme.BG_DARK, fg=Theme.TEXT_SECONDARY,
            ).pack(side=tk.LEFT)
            tk.Label(
                row, text=f"{pred.predicted_fault}", font=self.fonts["body"],
                bg=Theme.BG_DARK, fg=color,
            ).pack(side=tk.LEFT)
            tk.Label(
                row, text=f" ({pred.confidence:.0%})", font=self.fonts["small"],
                bg=Theme.BG_DARK, fg=Theme.TEXT_MUTED,
            ).pack(side=tk.LEFT)

    def _bind_mousewheel(self, widget):
        """Bind mousewheel scrolling to a specific widget only (not globally)."""
        import platform
        if platform.system() == "Darwin":
            widget.bind("<MouseWheel>",
                lambda e: self._canvas_scroll.yview_scroll(int(-1 * e.delta), "units"))
        else:
            widget.bind("<MouseWheel>",
                lambda e: self._canvas_scroll.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    def clear(self):
        """Reset dashboard to empty state."""
        self._clear_all()
        self._show_empty_state()

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _clear_all(self):
        """Remove all content from all sections."""
        for frame in (self._result_frame, self._confidence_frame,
                      self._pins_frame, self._faults_frame, self._recs_frame):
            for widget in frame.winfo_children():
                widget.destroy()

    def _show_empty_state(self):
        """Show placeholder when no results are loaded."""
        tk.Label(
            self._result_frame, text="Run a test to see diagnostics",
            font=self.fonts["body"], bg=Theme.BG_DARK, fg=Theme.TEXT_MUTED,
        ).pack(pady=20)

    def _draw_result_header(self, chip_id: str, success: bool, passed: int, total: int):
        """Draw the overall result section."""
        color = Theme.ACCENT_SUCCESS if success else Theme.ACCENT_ERROR
        text = "✅ ALL TESTS PASSED" if success else f"❌ {total - passed}/{total} TESTS FAILED"

        tk.Label(
            self._result_frame, text=f"{chip_id}", font=self.fonts["subheading"],
            bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY,
        ).pack(anchor=tk.W)
        tk.Label(
            self._result_frame, text=text, font=self.fonts["body"],
            bg=Theme.BG_DARK, fg=color,
        ).pack(anchor=tk.W, pady=(2, 0))
        tk.Label(
            self._result_frame, text=f"{passed}/{total} passed",
            font=self.fonts["small"], bg=Theme.BG_DARK, fg=Theme.TEXT_SECONDARY,
        ).pack(anchor=tk.W)

    def _draw_confidence_gauge(self, confidence: float):
        """Draw a horizontal confidence bar."""
        tk.Label(
            self._confidence_frame, text="Confidence",
            font=self.fonts["small"], bg=Theme.BG_DARK, fg=Theme.TEXT_SECONDARY,
        ).pack(anchor=tk.W)

        bar_canvas = tk.Canvas(
            self._confidence_frame, height=20, bg=Theme.BG_DARK, highlightthickness=0,
        )
        bar_canvas.pack(fill=tk.X, pady=2)

        def draw_bar(event=None):
            bar_canvas.delete("all")
            w = bar_canvas.winfo_width() or 200
            # Background
            bar_canvas.create_rectangle(0, 2, w, 16, fill="#2d3748", outline="")
            # Filled portion
            fill_w = int(w * confidence)
            if confidence >= 0.8:
                fill_color = Theme.ACCENT_SUCCESS
            elif confidence >= 0.5:
                fill_color = Theme.ACCENT_WARNING
            else:
                fill_color = Theme.ACCENT_ERROR
            bar_canvas.create_rectangle(0, 2, fill_w, 16, fill=fill_color, outline="")
            # Label
            bar_canvas.create_text(
                w // 2, 9, text=f"{confidence:.0%}",
                font=self.fonts["small"], fill="white",
            )

        bar_canvas.bind("<Configure>", draw_bar)

    def _draw_pin_health(self, pin_diag: Dict):
        """Draw per-pin health bars from raw pinDiagnostics."""
        if not pin_diag:
            return

        tk.Label(
            self._pins_frame, text="Pin Health",
            font=self.fonts["subheading"], bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY,
        ).pack(anchor=tk.W, pady=(5, 3))

        for pin_name, diag in pin_diag.items():
            tested = diag.get("timesTested", 0)
            correct = diag.get("timesCorrect", 0)
            rate = correct / tested if tested > 0 else 0.0
            stuck = diag.get("stuckState", "") or ""

            self._draw_single_pin_bar(pin_name, rate, stuck, diag.get("chipPin", "?"))

    def _draw_pin_health_from_report(self, pin_diag: Dict):
        """Draw per-pin health bars from DiagnosticReport entries."""
        if not pin_diag:
            return

        tk.Label(
            self._pins_frame, text="Pin Health",
            font=self.fonts["subheading"], bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY,
        ).pack(anchor=tk.W, pady=(5, 3))

        for pin_name, info in pin_diag.items():
            rate = info.get("pass_rate", 0.0)
            severity = info.get("severity", "ok")
            detail = info.get("detail", "")
            chip_pin = info.get("chipPin", "?")

            row = tk.Frame(self._pins_frame, bg=Theme.BG_DARK)
            row.pack(fill=tk.X, pady=1)

            tk.Label(
                row, text=f"{pin_name} ({chip_pin})", font=self.fonts["small"],
                bg=Theme.BG_DARK, fg=Theme.TEXT_SECONDARY, width=14, anchor=tk.W,
            ).pack(side=tk.LEFT)

            bar = tk.Canvas(row, height=self.BAR_HEIGHT, width=self.BAR_WIDTH,
                           bg="#2d3748", highlightthickness=0)
            bar.pack(side=tk.LEFT, padx=4)

            fill_w = int(self.BAR_WIDTH * rate)
            color = {"ok": Theme.ACCENT_SUCCESS, "warning": Theme.ACCENT_WARNING,
                     "error": Theme.ACCENT_ERROR, "critical": "#e53e3e"}.get(severity, "#4a5568")
            bar.create_rectangle(0, 0, fill_w, self.BAR_HEIGHT, fill=color, outline="")

            tk.Label(
                row, text=f"{rate:.0%}", font=self.fonts["small"],
                bg=Theme.BG_DARK, fg=color, width=5,
            ).pack(side=tk.LEFT)

            if detail:
                tk.Label(
                    row, text=detail, font=self.fonts["small"],
                    bg=Theme.BG_DARK, fg=Theme.TEXT_MUTED,
                ).pack(side=tk.LEFT, padx=(4, 0))

    def _draw_single_pin_bar(self, pin_name: str, rate: float, stuck: str, chip_pin: Any):
        """Draw a single pin health bar row."""
        row = tk.Frame(self._pins_frame, bg=Theme.BG_DARK)
        row.pack(fill=tk.X, pady=1)

        tk.Label(
            row, text=f"{pin_name} ({chip_pin})", font=self.fonts["small"],
            bg=Theme.BG_DARK, fg=Theme.TEXT_SECONDARY, width=14, anchor=tk.W,
        ).pack(side=tk.LEFT)

        bar = tk.Canvas(row, height=self.BAR_HEIGHT, width=self.BAR_WIDTH,
                       bg="#2d3748", highlightthickness=0)
        bar.pack(side=tk.LEFT, padx=4)

        fill_w = int(self.BAR_WIDTH * rate)
        if rate >= 0.9:
            color = Theme.ACCENT_SUCCESS
        elif rate >= 0.5:
            color = Theme.ACCENT_WARNING
        else:
            color = Theme.ACCENT_ERROR
        bar.create_rectangle(0, 0, fill_w, self.BAR_HEIGHT, fill=color, outline="")

        label = f"{rate:.0%}"
        if stuck:
            label += f" [{stuck}]"
        tk.Label(
            row, text=label, font=self.fonts["small"],
            bg=Theme.BG_DARK, fg=color,
        ).pack(side=tk.LEFT)

    def _draw_faults(self, fault_summary: List[Dict]):
        """Draw fault summary section."""
        tk.Label(
            self._faults_frame, text="🔧 Detected Faults",
            font=self.fonts["subheading"], bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY,
        ).pack(anchor=tk.W, pady=(5, 3))

        for fault in fault_summary[:5]:
            color = self._fault_color(fault.get("type", ""))
            conf = fault.get("confidence", 0)
            tk.Label(
                self._faults_frame,
                text=f"  • {fault.get('description', '')} ({conf:.0%})",
                font=self.fonts["small"], bg=Theme.BG_DARK, fg=color,
                wraplength=350, justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=1)

    def _draw_recommendations(self, recs: List[str]):
        """Draw recommendations section."""
        tk.Label(
            self._recs_frame, text="💡 Recommendations",
            font=self.fonts["subheading"], bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY,
        ).pack(anchor=tk.W, pady=(5, 3))

        for rec in recs[:5]:
            tk.Label(
                self._recs_frame, text=f"  {rec}",
                font=self.fonts["small"], bg=Theme.BG_DARK, fg=Theme.TEXT_SECONDARY,
                wraplength=350, justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=1)

    def _draw_signal_info(self, report):
        """Draw signal analysis metrics."""
        info_frame = tk.Frame(self._recs_frame, bg=Theme.BG_DARK)
        info_frame.pack(fill=tk.X, pady=(5, 0))
        tk.Label(
            info_frame,
            text=f"📡 Avg propagation: {report.avg_propagation_us:.0f}μs | "
                 f"Stability: {report.signal_stability:.0%}",
            font=self.fonts["small"], bg=Theme.BG_DARK, fg=Theme.TEXT_MUTED,
        ).pack(anchor=tk.W)

    @staticmethod
    def _fault_color(fault_type: str) -> str:
        """Map fault type to display color."""
        return {
            "open_pin": "#e53e3e",
            "shorted_high": "#ef476f",
            "shorted_low": "#ef476f",
            "floating_pin": "#ffd166",
            "timing_unstable": "#ffd166",
            "degraded_gate": "#ed8936",
            "stuck_high": "#ef476f",
            "stuck_low": "#ef476f",
            "no_response": "#e53e3e",
        }.get(fault_type, Theme.TEXT_SECONDARY)
