# ic_tester_app/diagnostics/statistical_tester.py
# Last edited: 2026-03-19
# Purpose: Multi-run statistical testing to detect intermittent failures and build confidence
# Dependencies: time, typing, dataclasses
# Related: chips/tester.py, diagnostics/diagnostic_report.py

"""
Statistical multi-run testing module.

Single-run testing is good for obvious faults, but intermittent wiring and
borderline chips often fail only sometimes. This module repeats the same chip
test several times, aggregates the per-pin outcomes, and turns them into
stability/confidence signals.

Workflow:
1. Run the normal chip test N times.
2. Merge each run's pin diagnostics into aggregate counters.
3. Detect pins that alternate between good and bad behavior.
4. Produce a summary report the UI can present as confidence evidence.
"""

import time
from typing import Optional, Dict, List, Any, Callable, Tuple
from dataclasses import dataclass, field

from ..logger import get_logger

logger = get_logger("diagnostics.statistical_tester")

ProgressCallback = Optional[Callable[[str], None]]


@dataclass
class PinStatistics:
    """Accumulated statistics for a single output pin across multiple test runs."""
    pin_name: str
    chip_pin: Any
    arduino_pin: Any
    total_reads: int = 0
    correct_reads: int = 0
    wrong_reads: int = 0
    error_reads: int = 0
    high_count: int = 0
    low_count: int = 0
    consistency_score: float = 1.0
    intermittent: bool = False
    wrong_readings_detail: List[Dict] = field(default_factory=list)


@dataclass
class StatisticalResult:
    """Aggregated result from multi-run statistical testing."""
    chip_id: str
    num_runs: int
    runs_passed: int
    runs_failed: int
    per_pin_stats: Dict[str, PinStatistics] = field(default_factory=dict)
    run_results: List[Dict] = field(default_factory=list)
    overall_pass_rate: float = 0.0
    overall_confidence: float = 0.0
    intermittent_pins: List[str] = field(default_factory=list)
    stable_failures: List[str] = field(default_factory=list)
    timestamp: str = ""


class StatisticalTester:
    """
    Multi-run statistical testing engine.

    Executes test sequences N times to build statistical confidence in results.
    Detects intermittent failures invisible to single-run testing by comparing
    per-pin outcomes across runs.

    Attributes:
        tester: ICTester instance for running individual tests
        default_runs: Default number of test runs for statistical analysis
    """

    DEFAULT_RUNS = 5
    MAX_RUNS = 20

    def __init__(self, tester):
        """
        Args:
            tester: ICTester instance for executing individual test runs
        """
        self.tester = tester
        logger.info("StatisticalTester initialized")

    def run_statistical_test(
        self,
        chip_id: str,
        num_runs: int = None,
        progress_callback: ProgressCallback = None,
        custom_mapping: Optional[Dict] = None,
        board: str = "MEGA",
        inter_run_delay: float = 0.5,
    ) -> StatisticalResult:
        """
        Run test sequence multiple times and aggregate results statistically.

        Args:
            chip_id: ID of chip to test
            num_runs: Number of test runs (default: DEFAULT_RUNS)
            progress_callback: Optional callback for progress updates
            custom_mapping: Optional user-defined Arduino pin mapping
            board: Board profile
            inter_run_delay: Seconds to wait between runs for signal settling

        Returns:
            StatisticalResult with aggregated statistics
        """
        # Clamp the run count so the feature stays useful without letting the UI
        # accidentally launch an excessively long classroom test session.
        if num_runs is None:
            num_runs = self.DEFAULT_RUNS
        num_runs = max(1, min(num_runs, self.MAX_RUNS))

        logger.info(f"Starting statistical test: {chip_id}, {num_runs} runs")

        if progress_callback:
            progress_callback(f"\n{'═' * 50}")
            progress_callback(f"📊 STATISTICAL TEST: {chip_id} ({num_runs} runs)")
            progress_callback(f"{'═' * 50}")

        result = StatisticalResult(
            chip_id=chip_id,
            num_runs=num_runs,
            runs_passed=0,
            runs_failed=0,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        for run_idx in range(num_runs):
            if progress_callback:
                progress_callback(f"\n── Run {run_idx + 1}/{num_runs} ──")

            run_result = self.tester.run_test(
                chip_id,
                progress_callback=progress_callback,
                custom_mapping=custom_mapping,
                board=board,
            )
            result.run_results.append(run_result)

            if run_result.get("success"):
                result.runs_passed += 1
            else:
                result.runs_failed += 1

            # Reuse the same pin-diagnostic structure produced by the core
            # tester, but merge it into a longer-lived aggregate view.
            self._accumulate_pin_stats(result, run_result, run_idx)

            if run_idx < num_runs - 1:
                time.sleep(inter_run_delay)

        # Finalize statistics
        self._finalize_statistics(result)

        # Report
        if progress_callback:
            self._report_statistics(result, progress_callback)

        logger.info(
            f"Statistical test complete: {result.runs_passed}/{num_runs} passed, "
            f"confidence={result.overall_confidence:.0%}"
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _accumulate_pin_stats(
        self, stat_result: StatisticalResult, run_result: Dict, run_idx: int
    ):
        """Merge per-pin diagnostics from a single run into the aggregate."""
        pin_diag = run_result.get("pinDiagnostics", {})
        for pin_name, diag in pin_diag.items():
            if pin_name not in stat_result.per_pin_stats:
                stat_result.per_pin_stats[pin_name] = PinStatistics(
                    pin_name=pin_name,
                    chip_pin=diag.get("chipPin", "?"),
                    arduino_pin=diag.get("arduinoPin", "?"),
                )
            ps = stat_result.per_pin_stats[pin_name]
            ps.total_reads += diag.get("timesTested", 0)
            ps.correct_reads += diag.get("timesCorrect", 0)
            ps.wrong_reads += diag.get("timesWrong", 0)
            ps.error_reads += diag.get("timesError", 0)

            # Preserve the raw HIGH/LOW distribution so later reports can say
            # whether a failing pin was biased high, biased low, or mixed.
            for val in diag.get("allReadValues", []):
                if val == "HIGH":
                    ps.high_count += 1
                elif val == "LOW":
                    ps.low_count += 1

            for w in diag.get("wrongReadings", []):
                ps.wrong_readings_detail.append(
                    {**w, "run": run_idx + 1}
                )

    def _finalize_statistics(self, result: StatisticalResult):
        """Compute derived statistics after all runs complete."""
        if result.num_runs > 0:
            result.overall_pass_rate = result.runs_passed / result.num_runs

        for pin_name, ps in result.per_pin_stats.items():
            if ps.total_reads > 0:
                ps.consistency_score = ps.correct_reads / ps.total_reads
            else:
                ps.consistency_score = 0.0

            # Intermittent means the pin is neither consistently good nor
            # consistently bad across repeated runs.
            if ps.wrong_reads > 0 and ps.correct_reads > 0:
                ps.intermittent = True
                result.intermittent_pins.append(pin_name)
            elif ps.wrong_reads > 0 and ps.correct_reads == 0:
                result.stable_failures.append(pin_name)

        # Overall confidence balances "how many whole runs passed" with "how
        # reliable each individual pin looked across all reads."
        if result.per_pin_stats:
            avg_consistency = sum(
                ps.consistency_score for ps in result.per_pin_stats.values()
            ) / len(result.per_pin_stats)
        else:
            avg_consistency = 0.0

        result.overall_confidence = (
            result.overall_pass_rate * 0.5 + avg_consistency * 0.5
        )

    def _report_statistics(
        self, result: StatisticalResult, callback: ProgressCallback
    ):
        """Generate human-readable statistical report."""
        callback(f"\n{'═' * 50}")
        callback(f"📊 STATISTICAL ANALYSIS RESULTS")
        callback(f"{'═' * 50}")
        callback(
            f"  Runs: {result.runs_passed}/{result.num_runs} passed "
            f"({result.overall_pass_rate:.0%})"
        )
        callback(f"  Confidence: {result.overall_confidence:.0%}")

        if result.intermittent_pins:
            callback(f"\n  🟡 INTERMITTENT PINS ({len(result.intermittent_pins)}):")
            for pn in result.intermittent_pins:
                ps = result.per_pin_stats[pn]
                callback(
                    f"    • {pn} (pin {ps.chip_pin}): "
                    f"{ps.correct_reads}/{ps.total_reads} correct "
                    f"({ps.consistency_score:.0%})"
                )

        if result.stable_failures:
            callback(f"\n  🔴 CONSISTENT FAILURES ({len(result.stable_failures)}):")
            for pn in result.stable_failures:
                ps = result.per_pin_stats[pn]
                callback(
                    f"    • {pn} (pin {ps.chip_pin} → Ard.{ps.arduino_pin}): "
                    f"FAILED every read"
                )

        # Per-pin summary
        callback(f"\n  Pin Reliability Summary:")
        for pn, ps in result.per_pin_stats.items():
            if ps.total_reads == 0:
                continue
            icon = "🟢" if ps.consistency_score >= 0.95 else (
                "🟡" if ps.consistency_score >= 0.5 else "🔴"
            )
            callback(
                f"    {icon} {pn}: {ps.consistency_score:.0%} "
                f"({ps.correct_reads}/{ps.total_reads})"
            )

        callback(f"{'═' * 50}")
