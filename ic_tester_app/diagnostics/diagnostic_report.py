# ic_tester_app/diagnostics/diagnostic_report.py
# Last edited: 2026-03-19
# Purpose: Structured diagnostic report generation combining all analysis sources
# Dependencies: time, json, dataclasses
# Related: diagnostics/statistical_tester.py, diagnostics/signal_analyzer.py, intelligence/pattern_analyzer.py

"""
Unified diagnostic report module.

This file is where the app's different analysis streams are merged into one
structured artifact. Instead of every UI component or export path having to
know about raw test results, statistical reruns, signal analysis, and pattern
mistake objects separately, they can all consume one `DiagnosticReport`.
"""

import json
import time
from typing import Optional, Dict, List, Any, Callable
from dataclasses import dataclass, field, asdict
from pathlib import Path

from ..logger import get_logger
from ..config import Config

logger = get_logger("diagnostics.diagnostic_report")


@dataclass
class PinDiagnosticEntry:
    """Diagnostic summary for a single pin combining all analysis sources."""
    pin_name: str
    chip_pin: Any
    arduino_pin: Any
    pass_rate: float = 0.0
    stability_score: float = 1.0
    is_flickering: bool = False
    stuck_state: str = ""
    is_intermittent: bool = False
    propagation_delay_us: float = 0.0
    fault_type: str = ""
    fault_confidence: float = 0.0
    severity: str = "ok"
    detail: str = ""


@dataclass
class DiagnosticReport:
    """Complete diagnostic report for a chip test session."""
    chip_id: str
    chip_name: str = ""
    timestamp: str = ""
    overall_result: str = "UNKNOWN"
    overall_confidence: float = 0.0
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    statistical_runs: int = 0
    statistical_pass_rate: float = 0.0
    pin_diagnostics: Dict[str, PinDiagnosticEntry] = field(default_factory=dict)
    fault_summary: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    signal_stability: float = 1.0
    avg_propagation_us: float = 0.0
    raw_test_result: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def get_severity_counts(self) -> Dict[str, int]:
        """Count pins by severity level."""
        counts = {"ok": 0, "warning": 0, "error": 0, "critical": 0}
        for entry in self.pin_diagnostics.values():
            counts[entry.severity] = counts.get(entry.severity, 0) + 1
        return counts


class DiagnosticReportGenerator:
    """
    Generates comprehensive diagnostic reports by combining all analysis sources.

    Integrates:
    - ICTester results (per-test pass/fail, pinDiagnostics)
    - StatisticalTester results (multi-run aggregation)
    - SignalAnalyzer results (stability, propagation)
    - PatternAnalyzer results (fault classification)

    Reports are structured for GUI display, JSON export, and ML training.
    """

    # Severity thresholds
    PASS_RATE_WARNING = 0.9
    PASS_RATE_ERROR = 0.5
    STABILITY_WARNING = 0.95
    STABILITY_ERROR = 0.8

    def __init__(self, logs_dir: Optional[Path] = None):
        """
        Args:
            logs_dir: Directory for saving diagnostic report JSON files
        """
        self.logs_dir = logs_dir or Config.LOGS_DIR
        self.logs_dir.mkdir(exist_ok=True)
        logger.info("DiagnosticReportGenerator initialized")

    def generate_report(
        self,
        test_result: Dict,
        statistical_result=None,
        signal_report=None,
        pattern_mistakes: List = None,
        confidence_score=None,
    ) -> DiagnosticReport:
        """
        Generate a unified diagnostic report from all available analysis sources.

        Args:
            test_result: Standard ICTester run_test() result dict
            statistical_result: Optional StatisticalResult from multi-run testing
            signal_report: Optional SignalReport from signal analysis
            pattern_mistakes: Optional list of WiringMistake from pattern analyzer
            confidence_score: Optional ConfidenceScore from pattern analyzer

        Returns:
            DiagnosticReport combining all sources
        """
        chip_id = test_result.get("chipId", "Unknown")

        report = DiagnosticReport(
            chip_id=chip_id,
            chip_name=test_result.get("chipName", chip_id),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            tests_run=test_result.get("testsRun", 0),
            tests_passed=test_result.get("testsPassed", 0),
            tests_failed=test_result.get("testsFailed", 0),
            raw_test_result=test_result,
        )

        # First determine the session-level headline result before enriching it
        # with per-pin evidence from the other analysis sources.
        if test_result.get("success"):
            report.overall_result = "PASS"
        elif test_result.get("error"):
            report.overall_result = "ERROR"
        else:
            report.overall_result = "FAIL"

        # The raw tester output is the base layer. Later merges refine these pin
        # entries with statistical stability, signal timing, and fault labels.
        self._merge_test_diagnostics(report, test_result)

        # Merge statistical data if available
        if statistical_result is not None:
            self._merge_statistical(report, statistical_result)

        # Merge signal analysis if available
        if signal_report is not None:
            self._merge_signal(report, signal_report)

        # Merge pattern analysis faults
        if pattern_mistakes:
            self._merge_faults(report, pattern_mistakes)

        # Set confidence
        if confidence_score is not None:
            report.overall_confidence = confidence_score.overall
        elif statistical_result is not None:
            report.overall_confidence = statistical_result.overall_confidence
        else:
            report.overall_confidence = self._calculate_confidence(report)

        # Compute severity for each pin
        self._assign_severities(report)

        # Generate recommendations
        report.recommendations = self._generate_recommendations(report)

        logger.info(
            f"Diagnostic report generated: {chip_id} "
            f"result={report.overall_result} "
            f"confidence={report.overall_confidence:.0%}"
        )
        return report

    def save_report(self, report: DiagnosticReport, filename: str = None) -> Path:
        """
        Save diagnostic report as JSON for ML training and historical analysis.

        Args:
            report: DiagnosticReport to save
            filename: Optional filename override

        Returns:
            Path to saved file
        """
        if filename is None:
            ts = time.strftime("%Y%m%d_%H%M%S")
            filename = f"diag_{report.chip_id}_{ts}.json"

        filepath = self.logs_dir / filename
        filepath.write_text(report.to_json(), encoding="utf-8")
        logger.info(f"Diagnostic report saved to {filepath}")
        return filepath

    # ------------------------------------------------------------------
    # Internal merge helpers
    # ------------------------------------------------------------------

    def _merge_test_diagnostics(self, report: DiagnosticReport, test_result: Dict):
        """Populate per-pin entries from standard test pinDiagnostics."""
        pin_diag = test_result.get("pinDiagnostics", {})
        for pin_name, diag in pin_diag.items():
            tested = diag.get("timesTested", 0)
            correct = diag.get("timesCorrect", 0)
            entry = PinDiagnosticEntry(
                pin_name=pin_name,
                chip_pin=diag.get("chipPin", "?"),
                arduino_pin=diag.get("arduinoPin", "?"),
                pass_rate=correct / tested if tested > 0 else 0.0,
                stuck_state=diag.get("stuckState", "") or "",
            )
            report.pin_diagnostics[pin_name] = entry

    def _merge_statistical(self, report: DiagnosticReport, stat_result):
        """Merge StatisticalResult data into report."""
        report.statistical_runs = stat_result.num_runs
        report.statistical_pass_rate = stat_result.overall_pass_rate

        for pin_name, ps in stat_result.per_pin_stats.items():
            if pin_name not in report.pin_diagnostics:
                report.pin_diagnostics[pin_name] = PinDiagnosticEntry(
                    pin_name=pin_name,
                    chip_pin=ps.chip_pin,
                    arduino_pin=ps.arduino_pin,
                )
            entry = report.pin_diagnostics[pin_name]
            if ps.total_reads > 0:
                entry.pass_rate = ps.correct_reads / ps.total_reads
            entry.is_intermittent = ps.intermittent

    def _merge_signal(self, report: DiagnosticReport, sig_report):
        """Merge SignalReport data into report."""
        report.signal_stability = sig_report.overall_stability
        report.avg_propagation_us = sig_report.avg_propagation_us

        for pin_name, stab in sig_report.pin_stability.items():
            if pin_name not in report.pin_diagnostics:
                report.pin_diagnostics[pin_name] = PinDiagnosticEntry(
                    pin_name=pin_name,
                    chip_pin=stab.chip_pin,
                    arduino_pin=stab.arduino_pin,
                )
            entry = report.pin_diagnostics[pin_name]
            entry.stability_score = stab.stability_score
            entry.is_flickering = stab.is_flickering

        # Assign propagation delays to first matching output pin
        for delay in sig_report.propagation_delays:
            pn = delay.output_pin_name
            if pn in report.pin_diagnostics:
                report.pin_diagnostics[pn].propagation_delay_us = delay.delay_us

    def _merge_faults(self, report: DiagnosticReport, mistakes: List):
        """Merge WiringMistake list into fault summary."""
        for m in mistakes:
            report.fault_summary.append({
                "type": m.type,
                "description": m.description,
                "confidence": m.confidence,
                "affected_pins": m.affected_pins,
                "fix": m.suggested_fix,
            })
            # Assign fault type to affected pins
            for chip_pin in m.affected_pins:
                for entry in report.pin_diagnostics.values():
                    if entry.chip_pin == chip_pin and m.confidence > entry.fault_confidence:
                        entry.fault_type = m.type
                        entry.fault_confidence = m.confidence

    def _assign_severities(self, report: DiagnosticReport):
        """Assign severity levels to each pin based on combined metrics."""
        for entry in report.pin_diagnostics.values():
            if entry.stuck_state in ("NO_RESPONSE",):
                entry.severity = "critical"
                entry.detail = f"Pin not responding"
            elif entry.pass_rate < self.PASS_RATE_ERROR:
                entry.severity = "error"
                entry.detail = f"Pass rate {entry.pass_rate:.0%}"
            elif entry.stuck_state in ("HIGH", "LOW"):
                entry.severity = "error"
                entry.detail = f"Stuck {entry.stuck_state}"
            elif entry.is_flickering:
                entry.severity = "warning"
                entry.detail = f"Signal unstable ({entry.stability_score:.0%})"
            elif entry.is_intermittent:
                entry.severity = "warning"
                entry.detail = f"Intermittent failures"
            elif entry.pass_rate < self.PASS_RATE_WARNING:
                entry.severity = "warning"
                entry.detail = f"Pass rate {entry.pass_rate:.0%}"
            else:
                entry.severity = "ok"
                entry.detail = "Healthy"

    def _calculate_confidence(self, report: DiagnosticReport) -> float:
        """Calculate overall confidence when no external score is provided."""
        if report.tests_run == 0:
            return 0.0
        test_rate = report.tests_passed / report.tests_run
        stability = report.signal_stability
        return test_rate * 0.6 + stability * 0.4

    def _generate_recommendations(self, report: DiagnosticReport) -> List[str]:
        """Generate prioritized list of recommendations based on findings."""
        recs = []
        severity_counts = report.get_severity_counts()

        if severity_counts.get("critical", 0) > 0:
            critical_pins = [
                e.pin_name for e in report.pin_diagnostics.values()
                if e.severity == "critical"
            ]
            recs.append(
                f"🔴 CRITICAL: {len(critical_pins)} pin(s) not responding: "
                f"{', '.join(critical_pins)}. Check wiring immediately."
            )

        if severity_counts.get("error", 0) > 0:
            error_pins = [
                e.pin_name for e in report.pin_diagnostics.values()
                if e.severity == "error"
            ]
            recs.append(
                f"🟠 {len(error_pins)} pin(s) with errors: {', '.join(error_pins)}"
            )

        if report.avg_propagation_us > 1000:
            recs.append(
                f"⏱ High propagation delay ({report.avg_propagation_us:.0f}μs). "
                f"May indicate degraded gate or weak drive."
            )

        if hasattr(report, 'flickering_pins') and report.flickering_pins:
            for fp in report.flickering_pins:
                recs.append(f"⚡ {fp}: flickering detected — check for floating input or noise")

        for entry in report.pin_diagnostics.values():
            if entry.is_intermittent:
                recs.append(
                    f"🟡 {entry.pin_name}: intermittent failures — "
                    f"run statistical test for confirmation"
                )

        if report.fault_summary:
            top_fault = max(report.fault_summary, key=lambda f: f["confidence"])
            recs.append(f"🔧 Most likely issue: {top_fault['description']} — {top_fault['fix']}")

        if not recs and report.overall_result == "PASS":
            recs.append("✅ All pins healthy. Chip operating within expected parameters.")

        if not recs:
            recs.append("Re-run the test to confirm results.")

        return recs
