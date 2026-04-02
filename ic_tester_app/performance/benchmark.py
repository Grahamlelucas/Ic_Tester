# ic_tester_app/performance/benchmark.py
# Last edited: 2026-03-19
# Purpose: Arduino Mega 2560 performance benchmarking and system limit documentation
# Dependencies: time, typing, dataclasses
# Related: arduino/connection.py, config.py

"""
Performance Benchmark module.

Measures and documents the practical performance limits of the IC Tester system:
- Serial round-trip latency (PING/PONG)
- Single pin read/write throughput
- Batch pin operation throughput
- Rapid sampling rate (firmware v8.0+)
- Memory usage estimates
- Documented hardware limits of Arduino Mega 2560

All benchmarks run non-destructively and do not affect connected ICs.
"""

import time
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass, field

from ..logger import get_logger

logger = get_logger("performance.benchmark")

ProgressCallback = Optional[Callable[[str], None]]

# Arduino Mega 2560 documented limits
MEGA_2560_SPECS = {
    "mcu": "ATmega2560",
    "clock_mhz": 16,
    "sram_bytes": 8192,
    "flash_bytes": 262144,
    "eeprom_bytes": 4096,
    "digital_pins": 54,
    "analog_pins": 16,
    "pwm_pins": 15,
    "serial_ports": 4,
    "gpio_toggle_ns": 62.5,
    "adc_resolution_bits": 10,
    "adc_sample_time_us": 104,
    "digitalread_us": 3.5,
    "digitalwrite_us": 3.5,
    "serial_baud_max": 2000000,
    "serial_buffer_bytes": 64,
    "interrupt_latency_us": 4.0,
    "timer_resolution_ns": 62.5,
}


@dataclass
class BenchmarkResult:
    """Result of a single benchmark measurement."""
    name: str
    iterations: int
    total_ms: float
    avg_ms: float
    min_ms: float = 0.0
    max_ms: float = 0.0
    ops_per_second: float = 0.0
    notes: str = ""


@dataclass
class SystemBenchmarkReport:
    """Complete benchmark report for the IC Tester system."""
    benchmarks: List[BenchmarkResult] = field(default_factory=list)
    firmware_version: str = "unknown"
    serial_baud: int = 9600
    hardware_specs: Dict = field(default_factory=lambda: MEGA_2560_SPECS.copy())
    recommendations: List[str] = field(default_factory=list)
    timestamp: str = ""


class PerformanceBenchmark:
    """
    Benchmarks the IC Tester system to measure practical performance limits.

    Runs a series of non-destructive tests to measure communication latency,
    pin I/O throughput, and batch operation efficiency. Results inform
    optimization decisions and document system capabilities.

    Attributes:
        arduino: ArduinoConnection instance
    """

    # Benchmark pin (LED pin 13 is safe for testing, always available)
    BENCH_PIN = 13

    def __init__(self, arduino_conn):
        """
        Args:
            arduino_conn: ArduinoConnection instance
        """
        self.arduino = arduino_conn
        logger.info("PerformanceBenchmark initialized")

    def run_full_benchmark(
        self,
        progress_callback: ProgressCallback = None,
        iterations: int = 50,
    ) -> SystemBenchmarkReport:
        """
        Run all benchmarks and generate a comprehensive report.

        Args:
            progress_callback: Optional progress callback
            iterations: Number of iterations per benchmark

        Returns:
            SystemBenchmarkReport with all measurements
        """
        report = SystemBenchmarkReport(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        if progress_callback:
            progress_callback(f"\n{'═' * 50}")
            progress_callback(f"⚡ PERFORMANCE BENCHMARK")
            progress_callback(f"{'═' * 50}")

        # Check firmware version
        resp = self.arduino.send_and_receive("VERSION", timeout=1.0)
        if resp and resp.startswith("VERSION,"):
            report.firmware_version = resp.split(",")[1].strip()
        if progress_callback:
            progress_callback(f"  Firmware: v{report.firmware_version}")

        # 1. Serial round-trip latency
        if progress_callback:
            progress_callback(f"\n  [1/5] Serial round-trip (PING)...")
        report.benchmarks.append(
            self._bench_ping(iterations)
        )

        # 2. Single pin write
        if progress_callback:
            progress_callback(f"  [2/5] Single pin write...")
        report.benchmarks.append(
            self._bench_single_write(iterations)
        )

        # 3. Single pin read
        if progress_callback:
            progress_callback(f"  [3/5] Single pin read...")
        report.benchmarks.append(
            self._bench_single_read(iterations)
        )

        # 4. Batch pin read (4 pins)
        if progress_callback:
            progress_callback(f"  [4/5] Batch pin read...")
        report.benchmarks.append(
            self._bench_batch_read(min(iterations, 30))
        )

        # 5. Rapid sample (if firmware supports it)
        if report.firmware_version != "unknown":
            try:
                ver = float(report.firmware_version)
                if ver >= 8.0:
                    if progress_callback:
                        progress_callback(f"  [5/5] Rapid sampling (firmware v8+)...")
                    report.benchmarks.append(
                        self._bench_rapid_sample()
                    )
            except ValueError:
                pass

        # Generate recommendations
        report.recommendations = self._generate_recommendations(report)

        # Display results
        if progress_callback:
            progress_callback(f"\n  {'─' * 40}")
            progress_callback(f"  Results:")
            for b in report.benchmarks:
                progress_callback(
                    f"    {b.name}: {b.avg_ms:.2f}ms avg "
                    f"({b.ops_per_second:.0f} ops/s)"
                )
                if b.notes:
                    progress_callback(f"      → {b.notes}")

            if report.recommendations:
                progress_callback(f"\n  Recommendations:")
                for rec in report.recommendations:
                    progress_callback(f"    • {rec}")

            progress_callback(f"{'═' * 50}")

        logger.info(f"Benchmark complete: {len(report.benchmarks)} tests run")
        return report

    # ------------------------------------------------------------------
    # Individual benchmarks
    # ------------------------------------------------------------------

    def _bench_ping(self, iterations: int) -> BenchmarkResult:
        """Measure serial PING/PONG round-trip latency."""
        times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            resp = self.arduino.send_and_receive("PING", timeout=1.0)
            elapsed = (time.perf_counter() - t0) * 1000
            if resp and "PONG" in resp:
                times.append(elapsed)

        return self._make_result("Serial Round-trip (PING)", times, iterations,
                                  notes="Baseline communication latency")

    def _bench_single_write(self, iterations: int) -> BenchmarkResult:
        """Measure single pin SET_PIN latency."""
        times = []
        for i in range(iterations):
            state = "HIGH" if i % 2 == 0 else "LOW"
            t0 = time.perf_counter()
            resp = self.arduino.send_and_receive(
                f"SET_PIN,{self.BENCH_PIN},{state}", timeout=1.0
            )
            elapsed = (time.perf_counter() - t0) * 1000
            if resp and "SET_PIN_OK" in resp:
                times.append(elapsed)

        return self._make_result("Single Pin Write", times, iterations,
                                  notes="SET_PIN command round-trip")

    def _bench_single_read(self, iterations: int) -> BenchmarkResult:
        """Measure single pin READ_PIN latency."""
        times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            resp = self.arduino.send_and_receive(
                f"READ_PIN,{self.BENCH_PIN}", timeout=1.0
            )
            elapsed = (time.perf_counter() - t0) * 1000
            if resp and "READ_PIN_OK" in resp:
                times.append(elapsed)

        return self._make_result("Single Pin Read", times, iterations,
                                  notes="READ_PIN command round-trip")

    def _bench_batch_read(self, iterations: int) -> BenchmarkResult:
        """Measure batch READ_PINS latency (4 pins)."""
        # Use safe pins: 2, 3, 4, 5
        pin_str = "2,3,4,5"
        times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            resp = self.arduino.send_and_receive(
                f"READ_PINS,{pin_str}", timeout=1.0
            )
            elapsed = (time.perf_counter() - t0) * 1000
            if resp and "READ_PINS_OK" in resp:
                times.append(elapsed)

        return self._make_result("Batch Read (4 pins)", times, iterations,
                                  notes="READ_PINS vs 4× READ_PIN")

    def _bench_rapid_sample(self) -> BenchmarkResult:
        """Measure RAPID_SAMPLE performance (firmware v8+)."""
        sample_counts = [10, 50, 100, 200]
        times = []
        arduino_us_per_sample = []

        for count in sample_counts:
            t0 = time.perf_counter()
            resp = self.arduino.send_and_receive(
                f"RAPID_SAMPLE,{self.BENCH_PIN},{count}", timeout=2.0
            )
            elapsed = (time.perf_counter() - t0) * 1000
            if resp and "RAPID_SAMPLE_OK" in resp:
                times.append(elapsed)
                parts = resp.split(",")
                if len(parts) >= 5:
                    try:
                        us = int(parts[4])
                        arduino_us_per_sample.append(us / count)
                    except ValueError:
                        pass

        avg_us = sum(arduino_us_per_sample) / len(arduino_us_per_sample) if arduino_us_per_sample else 0
        notes = f"Arduino-side: ~{avg_us:.1f}μs/sample ({1_000_000/avg_us:.0f} samples/s)" if avg_us > 0 else ""

        return self._make_result("Rapid Sample", times, len(sample_counts), notes=notes)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_result(
        name: str, times: List[float], iterations: int, notes: str = ""
    ) -> BenchmarkResult:
        """Create a BenchmarkResult from a list of timing measurements."""
        if not times:
            return BenchmarkResult(
                name=name, iterations=iterations,
                total_ms=0, avg_ms=0, notes="No valid measurements"
            )

        total = sum(times)
        avg = total / len(times)
        return BenchmarkResult(
            name=name,
            iterations=len(times),
            total_ms=total,
            avg_ms=avg,
            min_ms=min(times),
            max_ms=max(times),
            ops_per_second=1000.0 / avg if avg > 0 else 0,
            notes=notes,
        )

    @staticmethod
    def _generate_recommendations(report: SystemBenchmarkReport) -> List[str]:
        """Generate optimization recommendations based on benchmark results."""
        recs = []

        for b in report.benchmarks:
            if b.name == "Serial Round-trip (PING)" and b.avg_ms > 10:
                recs.append(
                    f"Serial latency is {b.avg_ms:.1f}ms — consider increasing "
                    f"baud rate from 9600 to 115200 for ~10× improvement"
                )
            if b.name == "Single Pin Read" and b.avg_ms > 15:
                recs.append(
                    "Single pin reads are slow — use batch READ_PINS to reduce overhead"
                )
            if "Batch Read" in b.name and b.ops_per_second > 0:
                # Compare batch vs single
                single = next(
                    (x for x in report.benchmarks if x.name == "Single Pin Read"), None
                )
                if single and single.avg_ms > 0:
                    speedup = (single.avg_ms * 4) / b.avg_ms
                    if speedup > 1.5:
                        recs.append(
                            f"Batch reads are {speedup:.1f}× faster than 4 individual reads — "
                            f"always prefer batch operations"
                        )

        if report.firmware_version == "unknown":
            recs.append("Firmware version unknown — update to v8.0+ for enhanced diagnostics")
        else:
            try:
                ver = float(report.firmware_version)
                if ver < 8.0:
                    recs.append(
                        "Firmware <8.0 detected — update for RAPID_SAMPLE, "
                        "TIMED_READ, and SET_AND_TIME commands"
                    )
            except ValueError:
                pass

        if not recs:
            recs.append("System performing within expected parameters")

        return recs

    @staticmethod
    def get_system_limits_doc() -> str:
        """
        Return a formatted string documenting the Arduino Mega 2560 system limits.

        This serves as reference documentation for understanding the hardware
        constraints of the IC testing platform.
        """
        return f"""
╔══════════════════════════════════════════════════╗
║  ARDUINO MEGA 2560 — SYSTEM LIMITS REFERENCE    ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  MCU:          ATmega2560 @ 16 MHz               ║
║  SRAM:         8 KB (variables, stack, heap)      ║
║  Flash:        256 KB (program code)              ║
║  EEPROM:       4 KB (persistent storage)          ║
║                                                  ║
║  GPIO Pins:    54 digital + 16 analog             ║
║  PWM Pins:     15                                 ║
║  Serial Ports: 4 (Serial0 used for USB)           ║
║                                                  ║
║  TIMING LIMITS:                                  ║
║  • GPIO toggle:     62.5 ns (direct port)         ║
║  • digitalRead:     ~3.5 μs per call              ║
║  • digitalWrite:    ~3.5 μs per call              ║
║  • ADC sample:      ~104 μs (10-bit)              ║
║  • Interrupt entry:  ~4 μs                        ║
║  • Timer tick:       62.5 ns                      ║
║                                                  ║
║  SERIAL LIMITS:                                  ║
║  • Max baud:      2,000,000 (USB-reliable: 115200)║
║  • RX buffer:     64 bytes                        ║
║  • TX buffer:     64 bytes                        ║
║  • At 9600 baud:  ~1 ms per byte                  ║
║  • At 115200:     ~0.087 ms per byte              ║
║                                                  ║
║  PRACTICAL IC TESTING LIMITS:                    ║
║  • Max testable pins:  ~48 (excluding reserved)   ║
║  • Pin read rate:      ~250,000 samples/s (port)  ║
║  •                     ~280 reads/s (serial loop)  ║
║  • Propagation resolution: ~4 μs (digitalRead)    ║
║  • TTL prop. delay:    ~10-20 ns (unmeasurable)    ║
║  • SRAM for test data: ~4-6 KB available           ║
║  • Max test vectors in RAM: ~200-400               ║
║                                                  ║
║  NOTES:                                          ║
║  • Serial is the primary bottleneck               ║
║  • Batch commands reduce serial overhead           ║
║  • Direct port reads bypass digitalRead overhead   ║
║  • 16 MHz clock limits timing to 62.5 ns ticks    ║
║  • USB latency adds ~1-5 ms per round-trip        ║
╚══════════════════════════════════════════════════╝
"""
