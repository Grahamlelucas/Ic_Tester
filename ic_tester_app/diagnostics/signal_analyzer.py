# ic_tester_app/diagnostics/signal_analyzer.py
# Last edited: 2026-03-19
# Purpose: Signal stability analysis and propagation delay measurement using enhanced firmware
# Dependencies: time, typing, dataclasses
# Related: arduino/connection.py, ic_tester_firmware.ino (v8.0 RAPID_SAMPLE, SET_AND_TIME)

"""
Signal Analyzer module.

Uses enhanced firmware commands to perform hardware-level diagnostics:
- RAPID_SAMPLE: Take N rapid reads of a pin to detect flickering/instability
- SET_AND_TIME: Measure propagation delay between input change and output response
- TIMED_READ: Capture waveform samples at fixed intervals

Provides:
- Pin stability scoring (0.0 = completely unstable, 1.0 = perfectly stable)
- Propagation delay measurement in microseconds
- Signal quality assessment for each output pin
"""

import time
from typing import Optional, Dict, List, Any, Callable, Tuple
from dataclasses import dataclass, field

from ..logger import get_logger

logger = get_logger("diagnostics.signal_analyzer")

ProgressCallback = Optional[Callable[[str], None]]


@dataclass
class PinStability:
    """Stability measurement for a single pin."""
    pin_name: str
    chip_pin: Any
    arduino_pin: Any
    high_count: int = 0
    low_count: int = 0
    total_samples: int = 0
    sample_duration_us: int = 0
    stability_score: float = 1.0
    dominant_state: str = "UNKNOWN"
    is_flickering: bool = False


@dataclass
class PropagationDelay:
    """Propagation delay measurement between an input and output pin."""
    input_pin_name: str
    output_pin_name: str
    input_arduino_pin: Any
    output_arduino_pin: Any
    input_transition: str = ""
    output_prev_state: str = ""
    output_new_state: str = ""
    delay_us: int = 0
    timed_out: bool = False


@dataclass
class SignalReport:
    """Complete signal analysis report for a chip."""
    chip_id: str
    pin_stability: Dict[str, PinStability] = field(default_factory=dict)
    propagation_delays: List[PropagationDelay] = field(default_factory=list)
    avg_propagation_us: float = 0.0
    max_propagation_us: float = 0.0
    overall_stability: float = 1.0
    flickering_pins: List[str] = field(default_factory=list)
    timestamp: str = ""


class SignalAnalyzer:
    """
    Performs hardware-level signal analysis on IC pins.

    Uses enhanced firmware commands (v8.0+) to measure:
    - Pin signal stability via rapid sampling
    - Propagation delay through IC gates
    - Signal quality metrics

    Falls back gracefully if firmware lacks enhanced commands.

    Attributes:
        arduino: ArduinoConnection instance
        samples_per_pin: Number of rapid samples for stability analysis
    """

    DEFAULT_SAMPLES = 100

    def __init__(self, arduino_conn):
        """
        Args:
            arduino_conn: ArduinoConnection instance
        """
        self.arduino = arduino_conn
        self._firmware_enhanced = None
        logger.info("SignalAnalyzer initialized")

    def check_firmware_support(self) -> bool:
        """Check if firmware supports enhanced commands (v8.0+)."""
        if self._firmware_enhanced is not None:
            return self._firmware_enhanced

        response = self.arduino.send_and_receive("VERSION", timeout=1.0)
        if response and response.startswith("VERSION,"):
            try:
                version = float(response.split(",")[1])
                self._firmware_enhanced = version >= 8.0
            except (ValueError, IndexError):
                self._firmware_enhanced = False
        else:
            self._firmware_enhanced = False

        logger.info(f"Firmware enhanced commands: {self._firmware_enhanced}")
        return self._firmware_enhanced

    def analyze_pin_stability(
        self,
        arduino_pin: int,
        pin_name: str = "",
        chip_pin: Any = "?",
        num_samples: int = None,
    ) -> PinStability:
        """
        Measure stability of a single pin using rapid sampling.

        Args:
            arduino_pin: Arduino pin number to sample
            pin_name: Human-readable pin name
            chip_pin: IC pin number
            num_samples: Number of rapid samples (default: DEFAULT_SAMPLES)

        Returns:
            PinStability with high/low counts and stability score
        """
        if num_samples is None:
            num_samples = self.DEFAULT_SAMPLES

        result = PinStability(
            pin_name=pin_name,
            chip_pin=chip_pin,
            arduino_pin=arduino_pin,
        )

        if self.check_firmware_support():
            # Use RAPID_SAMPLE firmware command for maximum speed
            cmd = f"RAPID_SAMPLE,{arduino_pin},{num_samples}"
            response = self.arduino.send_and_receive(cmd, timeout=2.0)

            if response and response.startswith("RAPID_SAMPLE_OK,"):
                parts = response.split(",")
                try:
                    result.high_count = int(parts[2])
                    result.low_count = int(parts[3])
                    result.sample_duration_us = int(parts[4])
                    result.total_samples = result.high_count + result.low_count
                except (ValueError, IndexError):
                    logger.warning(f"Failed to parse RAPID_SAMPLE response: {response}")
            else:
                logger.warning(f"RAPID_SAMPLE failed for pin {arduino_pin}: {response}")
        else:
            # Fallback: software-based rapid reads via individual READ_PIN commands
            result.total_samples = min(num_samples, 20)
            t0 = time.time()
            for _ in range(result.total_samples):
                self.arduino.send_command(f"READ_PIN,{arduino_pin}")
                resp = self.arduino.read_response(timeout=0.15)
                if resp and "HIGH" in resp:
                    result.high_count += 1
                elif resp and "LOW" in resp:
                    result.low_count += 1
            result.sample_duration_us = int((time.time() - t0) * 1_000_000)

        # Calculate stability
        if result.total_samples > 0:
            dominant = max(result.high_count, result.low_count)
            result.stability_score = dominant / result.total_samples
            result.dominant_state = "HIGH" if result.high_count >= result.low_count else "LOW"
            result.is_flickering = result.stability_score < 0.95
        else:
            result.stability_score = 0.0
            result.is_flickering = True

        return result

    def measure_propagation_delay(
        self,
        input_arduino_pin: int,
        output_arduino_pin: int,
        input_state: str = "HIGH",
        input_pin_name: str = "",
        output_pin_name: str = "",
    ) -> PropagationDelay:
        """
        Measure propagation delay between input change and output response.

        Args:
            input_arduino_pin: Arduino pin connected to IC input
            output_arduino_pin: Arduino pin connected to IC output
            input_state: State to set input to ("HIGH" or "LOW")
            input_pin_name: Human-readable input pin name
            output_pin_name: Human-readable output pin name

        Returns:
            PropagationDelay with timing measurement
        """
        result = PropagationDelay(
            input_pin_name=input_pin_name,
            output_pin_name=output_pin_name,
            input_arduino_pin=input_arduino_pin,
            output_arduino_pin=output_arduino_pin,
            input_transition=f"→{input_state}",
        )

        if self.check_firmware_support():
            cmd = f"SET_AND_TIME,{input_arduino_pin},{input_state},{output_arduino_pin}"
            response = self.arduino.send_and_receive(cmd, timeout=2.0)

            if response and response.startswith("SET_AND_TIME_OK,"):
                parts = response.split(",")
                try:
                    result.output_prev_state = parts[3]
                    result.output_new_state = parts[4]
                    result.delay_us = int(parts[5])
                    result.timed_out = parts[4] == "TIMEOUT"
                except (ValueError, IndexError):
                    logger.warning(f"Failed to parse SET_AND_TIME response: {response}")
                    result.timed_out = True
            else:
                logger.warning(f"SET_AND_TIME failed: {response}")
                result.timed_out = True
        else:
            # Fallback: software timing (much less accurate, ~ms resolution)
            self.arduino.send_command(f"READ_PIN,{output_arduino_pin}")
            resp = self.arduino.read_response(timeout=0.15)
            prev = "HIGH" if resp and "HIGH" in resp else "LOW"
            result.output_prev_state = prev

            t0 = time.time()
            self.arduino.send_command(f"SET_PIN,{input_arduino_pin},{input_state}")
            self.arduino.read_response(timeout=0.15)
            time.sleep(0.001)

            self.arduino.send_command(f"READ_PIN,{output_arduino_pin}")
            resp = self.arduino.read_response(timeout=0.15)
            elapsed = time.time() - t0
            new_state = "HIGH" if resp and "HIGH" in resp else "LOW"

            result.output_new_state = new_state
            result.delay_us = int(elapsed * 1_000_000)
            result.timed_out = new_state == prev

        return result

    def analyze_chip_signals(
        self,
        chip_data: Dict,
        progress_callback: ProgressCallback = None,
        num_samples: int = None,
    ) -> SignalReport:
        """
        Run full signal analysis on all output pins of a chip.

        Measures stability of every output pin and propagation delay
        through the first gate/path found in the pinout.

        Args:
            chip_data: Chip definition dictionary (with arduinoMapping)
            progress_callback: Optional progress callback
            num_samples: Samples per pin for stability analysis

        Returns:
            SignalReport with complete signal analysis
        """
        chip_id = chip_data.get("chipId", "Unknown")
        mapping = chip_data.get("arduinoMapping", {}).get("io", {})
        pinout = chip_data.get("pinout", {})

        report = SignalReport(
            chip_id=chip_id,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        if progress_callback:
            progress_callback(f"\n{'═' * 50}")
            progress_callback(f"📡 SIGNAL ANALYSIS: {chip_id}")
            progress_callback(f"{'═' * 50}")

        # 1. Stability analysis on all output pins
        output_pins = pinout.get("outputs", [])
        if progress_callback:
            progress_callback(f"  Analyzing stability of {len(output_pins)} output pins...")

        for out in output_pins:
            pin_name = out["name"]
            chip_pin = out["pin"]
            arduino_pin = mapping.get(str(chip_pin))
            if arduino_pin is None:
                continue

            stability = self.analyze_pin_stability(
                arduino_pin=arduino_pin,
                pin_name=pin_name,
                chip_pin=chip_pin,
                num_samples=num_samples,
            )
            report.pin_stability[pin_name] = stability

            if stability.is_flickering:
                report.flickering_pins.append(pin_name)

            if progress_callback:
                icon = "🟢" if stability.stability_score >= 0.95 else (
                    "🟡" if stability.stability_score >= 0.8 else "🔴"
                )
                progress_callback(
                    f"    {icon} {pin_name} (pin {chip_pin}): "
                    f"{stability.stability_score:.0%} stable "
                    f"({stability.dominant_state}, "
                    f"{stability.total_samples} samples in "
                    f"{stability.sample_duration_us}μs)"
                )

        # 2. Propagation delay: test first input→output pair found
        input_pins = pinout.get("inputs", [])
        if input_pins and output_pins:
            first_in = input_pins[0]
            first_out = output_pins[0]
            in_ard = mapping.get(str(first_in["pin"]))
            out_ard = mapping.get(str(first_out["pin"]))

            if in_ard is not None and out_ard is not None:
                if progress_callback:
                    progress_callback(f"\n  Measuring propagation delay...")

                # Reset input LOW, then transition HIGH
                self.arduino.send_and_receive(
                    f"SET_PIN,{in_ard},LOW", timeout=0.5
                )
                time.sleep(0.05)

                delay = self.measure_propagation_delay(
                    input_arduino_pin=in_ard,
                    output_arduino_pin=out_ard,
                    input_state="HIGH",
                    input_pin_name=first_in["name"],
                    output_pin_name=first_out["name"],
                )
                report.propagation_delays.append(delay)

                # Also measure HIGH→LOW transition
                delay_hl = self.measure_propagation_delay(
                    input_arduino_pin=in_ard,
                    output_arduino_pin=out_ard,
                    input_state="LOW",
                    input_pin_name=first_in["name"],
                    output_pin_name=first_out["name"],
                )
                report.propagation_delays.append(delay_hl)

                if progress_callback:
                    for d in report.propagation_delays:
                        status = "TIMEOUT" if d.timed_out else f"{d.delay_us}μs"
                        progress_callback(
                            f"    ⏱ {d.input_pin_name}{d.input_transition} → "
                            f"{d.output_pin_name}: {d.output_prev_state}→"
                            f"{d.output_new_state} in {status}"
                        )

        # 3. Compute aggregate metrics
        valid_delays = [d.delay_us for d in report.propagation_delays if not d.timed_out]
        if valid_delays:
            report.avg_propagation_us = sum(valid_delays) / len(valid_delays)
            report.max_propagation_us = max(valid_delays)

        if report.pin_stability:
            report.overall_stability = sum(
                s.stability_score for s in report.pin_stability.values()
            ) / len(report.pin_stability)

        if progress_callback:
            progress_callback(f"\n  Overall stability: {report.overall_stability:.0%}")
            if valid_delays:
                progress_callback(
                    f"  Avg propagation delay: {report.avg_propagation_us:.0f}μs"
                )
            if report.flickering_pins:
                progress_callback(
                    f"  ⚠️ Flickering pins: {', '.join(report.flickering_pins)}"
                )
            progress_callback(f"{'═' * 50}")

        logger.info(
            f"Signal analysis complete for {chip_id}: "
            f"stability={report.overall_stability:.0%}, "
            f"flickering={len(report.flickering_pins)} pins"
        )
        return report
