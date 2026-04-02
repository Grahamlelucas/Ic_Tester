# ic_tester_app/diagnostics/analog_analyzer.py
# Last edited: 2026-03-19
# Purpose: Analog voltage analysis for IC output pins using Arduino Mega ADC (A0-A15)
# Dependencies: time, typing, dataclasses
# Related: arduino/commands.py (analog_read, analog_rapid_sample), signal_analyzer.py

"""
Analog voltage analysis module.

This subsystem complements the normal digital tester by looking at the actual
measured voltage on a line, not just whether the firmware interpreted it as HIGH
or LOW. That makes it useful for diagnosing weak outputs, floating nodes, and
power-rail problems that can hide behind apparently "valid" digital states.

Analysis flow:
1. Confirm the firmware supports analog commands.
2. Read or profile one or more analog-capable Arduino pins.
3. Classify the measured voltages into TTL zones.
4. Roll those per-pin observations into a chip-level health report.

TTL Voltage Thresholds:
- Valid LOW:   0.0V - 0.8V  (ADC 0-163,   0-800 mV)
- Undefined:   0.8V - 2.0V  (ADC 164-409,  800-2000 mV)
- Valid HIGH:  2.0V - 5.0V  (ADC 410-1023, 2000-5000 mV)

Detects:
- Marginal logic levels (voltage near threshold boundaries)
- Floating pins (voltage drifting in the undefined zone)
- Degraded output drive (voltage sagging under load)
- Power rail issues (VCC not reaching 5V)
- Noise/ripple on signals (min/max spread from rapid sampling)

NOTE: IC outputs must be wired to analog-capable pins (A0-A15) for this analysis.
The existing digital test pipeline on pins 2-53 is completely unaffected.
"""

import time
from typing import Optional, Dict, List, Any, Callable, Tuple
from dataclasses import dataclass, field

from ..logger import get_logger

logger = get_logger("diagnostics.analog_analyzer")

ProgressCallback = Optional[Callable[[str], None]]

# TTL threshold constants (millivolts). These define the digital/analog bridge:
# every measured voltage is eventually described in TTL terms for the user.
TTL_LOW_MAX_MV = 800
TTL_HIGH_MIN_MV = 2000
TTL_NOMINAL_HIGH_MV = 3400
TTL_NOMINAL_LOW_MV = 200

# Noise margin thresholds (millivolts from boundary)
NOISE_MARGIN_WARNING_MV = 200

# Arduino analog pin mapping used by the firmware protocol.
ANALOG_PIN_OFFSET = 54  # A0 = digital 54, A1 = 55, ..., A15 = 69
ANALOG_PIN_COUNT = 16
ANALOG_PIN_RANGE = range(ANALOG_PIN_OFFSET, ANALOG_PIN_OFFSET + ANALOG_PIN_COUNT)


@dataclass
class AnalogPinReading:
    """Single analog voltage reading for a pin."""
    pin_name: str
    chip_pin: Any
    arduino_pin: int
    analog_channel: int = 0
    raw_adc: int = 0
    millivolts: int = 0
    voltage_str: str = ""
    ttl_zone: str = ""
    expected_digital: str = ""
    matches_expected: bool = True


@dataclass
class AnalogPinProfile:
    """Voltage profile from rapid sampling of a single pin."""
    pin_name: str
    chip_pin: Any
    arduino_pin: int
    analog_channel: int = 0
    num_samples: int = 0
    min_mv: int = 0
    max_mv: int = 0
    avg_mv: int = 0
    min_adc: int = 0
    max_adc: int = 0
    avg_adc: int = 0
    spread_mv: int = 0
    below_low_count: int = 0
    in_undefined_count: int = 0
    above_high_count: int = 0
    duration_us: int = 0
    dominant_zone: str = ""
    noise_level: str = ""
    is_floating: bool = False
    is_marginal: bool = False
    health: str = "ok"
    detail: str = ""


@dataclass
class AnalogReport:
    """Complete analog voltage analysis report for a chip."""
    chip_id: str
    pin_readings: Dict[str, AnalogPinReading] = field(default_factory=dict)
    pin_profiles: Dict[str, AnalogPinProfile] = field(default_factory=dict)
    vcc_mv: int = 0
    gnd_mv: int = 0
    power_ok: bool = True
    floating_pins: List[str] = field(default_factory=list)
    marginal_pins: List[str] = field(default_factory=list)
    noisy_pins: List[str] = field(default_factory=list)
    overall_voltage_health: str = "ok"
    recommendations: List[str] = field(default_factory=list)
    timestamp: str = ""
    analog_pin_map: Dict[str, int] = field(default_factory=dict)


class AnalogAnalyzer:
    """
    Measures actual voltage levels on IC output pins using the Mega's ADC.

    Provides voltage-domain analysis complementing the existing digital
    (HIGH/LOW) test pipeline. IC outputs must be wired to A0-A15 pins
    for measurement — the analyzer will guide the user through mapping.

    Key capabilities:
    - Single-shot voltage reads with TTL zone classification
    - Rapid multi-sample voltage profiling (noise, spread, distribution)
    - Power rail verification (VCC and GND)
    - Automatic floating/marginal/noisy pin detection

    Attributes:
        arduino: ArduinoConnection instance
    """

    DEFAULT_RAPID_SAMPLES = 200

    def __init__(self, arduino_conn):
        """
        Args:
            arduino_conn: ArduinoConnection instance
        """
        self.arduino = arduino_conn
        self._firmware_analog = None
        logger.info("AnalogAnalyzer initialized")

    def check_firmware_support(self) -> bool:
        """
        Check whether the connected firmware understands analog commands.

        The result is cached because this question may be asked many times while
        the user experiments with analog mapping in the UI.
        """
        if self._firmware_analog is not None:
            return self._firmware_analog

        response = self.arduino.send_and_receive("VERSION", timeout=1.0)
        if response and response.startswith("VERSION,"):
            try:
                version = float(response.split(",")[1])
                self._firmware_analog = version >= 9.0
            except (ValueError, IndexError):
                self._firmware_analog = False
        else:
            self._firmware_analog = False

        logger.info(f"Firmware analog support: {self._firmware_analog}")
        return self._firmware_analog

    # ------------------------------------------------------------------
    # Single-shot reads
    # ------------------------------------------------------------------

    def read_voltage(self, arduino_pin: int, pin_name: str = "",
                     chip_pin: Any = "?", expected: str = "") -> AnalogPinReading:
        """
        Read the analog voltage on a single pin.

        Args:
            arduino_pin: Arduino pin number (must be 54-69 for analog)
            pin_name: Human-readable pin name
            chip_pin: IC pin number
            expected: Expected digital state ('HIGH' or 'LOW') for comparison

        Returns:
            AnalogPinReading with voltage, zone, and match status
        """
        reading = AnalogPinReading(
            pin_name=pin_name,
            chip_pin=chip_pin,
            arduino_pin=arduino_pin,
            analog_channel=arduino_pin - ANALOG_PIN_OFFSET,
            expected_digital=expected,
        )

        if arduino_pin not in ANALOG_PIN_RANGE:
            logger.warning(f"Pin {arduino_pin} is not analog-capable (need 54-69)")
            reading.ttl_zone = "NOT_ANALOG"
            reading.matches_expected = False
            return reading

        if not self.check_firmware_support():
            logger.warning("Firmware does not support analog commands")
            reading.ttl_zone = "NO_FIRMWARE"
            return reading

        cmd = f"ANALOG_READ,{arduino_pin}"
        response = self.arduino.send_and_receive(cmd, timeout=1.0)

        if response and response.startswith("ANALOG_READ_OK,"):
            try:
                parts = response.split(",")
                reading.raw_adc = int(parts[2])
                reading.millivolts = int(parts[3])
                reading.ttl_zone = parts[4]
                reading.voltage_str = f"{reading.millivolts / 1000:.3f}V"
            except (ValueError, IndexError):
                logger.warning(f"Failed to parse ANALOG_READ response: {response}")

        # Check if measured zone matches expected digital state
        if expected:
            if expected == "HIGH":
                reading.matches_expected = reading.ttl_zone == "HIGH"
            elif expected == "LOW":
                reading.matches_expected = reading.ttl_zone == "LOW"

        return reading

    def read_multiple_voltages(self, pin_map: Dict[int, Dict]) -> Dict[int, AnalogPinReading]:
        """
        Batch analog read on multiple pins.

        Args:
            pin_map: Dict mapping arduino_pin → {name, chip_pin, expected}

        Returns:
            Dict mapping arduino_pin → AnalogPinReading
        """
        results = {}
        # Keep only analog-capable pins because the firmware's batch analog read
        # expects board-level analog pin numbers, not arbitrary digital lines.
        analog_pins = [p for p in pin_map if p in ANALOG_PIN_RANGE]

        if not analog_pins or not self.check_firmware_support():
            return results

        cmd = f"ANALOG_READ_PINS,{','.join(map(str, analog_pins))}"
        response = self.arduino.send_and_receive(cmd, timeout=2.0)

        if response and response.startswith("ANALOG_READ_PINS_OK,"):
            # Parse the compact batch format returned by firmware into richer
            # per-pin records the UI/report generator can consume directly.
            data = response[len("ANALOG_READ_PINS_OK,"):]
            for entry in data.split(","):
                parts = entry.split(":")
                if len(parts) >= 4:
                    try:
                        pin = int(parts[0])
                        info = pin_map.get(pin, {})
                        reading = AnalogPinReading(
                            pin_name=info.get("name", f"A{pin - ANALOG_PIN_OFFSET}"),
                            chip_pin=info.get("chip_pin", "?"),
                            arduino_pin=pin,
                            analog_channel=pin - ANALOG_PIN_OFFSET,
                            raw_adc=int(parts[1]),
                            millivolts=int(parts[2]),
                            ttl_zone=parts[3],
                            voltage_str=f"{int(parts[2]) / 1000:.3f}V",
                            expected_digital=info.get("expected", ""),
                        )
                        if reading.expected_digital:
                            reading.matches_expected = (
                                reading.ttl_zone == reading.expected_digital
                            )
                        results[pin] = reading
                    except (ValueError, IndexError):
                        continue

        return results

    # ------------------------------------------------------------------
    # Voltage profiling (rapid sampling)
    # ------------------------------------------------------------------

    def profile_pin_voltage(
        self,
        arduino_pin: int,
        pin_name: str = "",
        chip_pin: Any = "?",
        num_samples: int = None,
    ) -> AnalogPinProfile:
        """
        Take rapid analog samples to build a voltage profile for a pin.

        Measures voltage distribution, noise, and zone statistics.

        Args:
            arduino_pin: Arduino analog pin (54-69)
            pin_name: Human-readable pin name
            chip_pin: IC pin number
            num_samples: Number of rapid samples (default: 200)

        Returns:
            AnalogPinProfile with min/max/avg voltages and zone distribution
        """
        if num_samples is None:
            num_samples = self.DEFAULT_RAPID_SAMPLES

        profile = AnalogPinProfile(
            pin_name=pin_name,
            chip_pin=chip_pin,
            arduino_pin=arduino_pin,
            analog_channel=arduino_pin - ANALOG_PIN_OFFSET,
        )

        if arduino_pin not in ANALOG_PIN_RANGE:
            profile.health = "error"
            profile.detail = "Not an analog pin"
            return profile

        if not self.check_firmware_support():
            profile.health = "error"
            profile.detail = "Firmware <9.0"
            return profile

        cmd = f"ANALOG_RAPID_SAMPLE,{arduino_pin},{num_samples}"
        response = self.arduino.send_and_receive(cmd, timeout=3.0)

        if not response or not response.startswith("ANALOG_RAPID_SAMPLE_OK,"):
            profile.health = "error"
            profile.detail = f"Command failed: {response}"
            return profile

        try:
            parts = response.split(",")
            profile.num_samples = int(parts[2])
            profile.min_adc = int(parts[3])
            profile.max_adc = int(parts[4])
            profile.avg_adc = int(parts[5])
            profile.below_low_count = int(parts[6])
            profile.in_undefined_count = int(parts[7])
            profile.above_high_count = int(parts[8])
            profile.duration_us = int(parts[9])

            # Convert to millivolts
            profile.min_mv = profile.min_adc * 5000 // 1023
            profile.max_mv = profile.max_adc * 5000 // 1023
            profile.avg_mv = profile.avg_adc * 5000 // 1023
            profile.spread_mv = profile.max_mv - profile.min_mv
        except (ValueError, IndexError):
            profile.health = "error"
            profile.detail = "Parse error"
            return profile

        # Convert raw ADC aggregates into human-meaningful health labels.
        self._classify_profile(profile)
        return profile

    def _classify_profile(self, profile: AnalogPinProfile):
        """Assign health status and classify voltage behavior."""
        total = profile.num_samples
        if total == 0:
            profile.health = "error"
            profile.detail = "No samples"
            return

        # Determine which TTL zone dominated the sample window so later code can
        # talk about the pin in terms of "mostly HIGH", "mostly LOW", etc.
        counts = {
            "LOW": profile.below_low_count,
            "UNDEFINED": profile.in_undefined_count,
            "HIGH": profile.above_high_count,
        }
        profile.dominant_zone = max(counts, key=counts.get)

        # Noise level based on voltage spread
        if profile.spread_mv <= 50:
            profile.noise_level = "clean"
        elif profile.spread_mv <= 200:
            profile.noise_level = "low"
        elif profile.spread_mv <= 500:
            profile.noise_level = "moderate"
        else:
            profile.noise_level = "high"

        # A floating or weakly-driven line tends to spend a noticeable fraction
        # of time in the undefined TTL band instead of clustering cleanly high/low.
        undef_ratio = profile.in_undefined_count / total
        if undef_ratio > 0.3:
            profile.is_floating = True
            profile.health = "error"
            profile.detail = (
                f"Floating: {undef_ratio:.0%} in undefined zone "
                f"({profile.avg_mv}mV avg)"
            )
            return

        # Multi-zone: samples split across LOW and HIGH
        low_ratio = profile.below_low_count / total
        high_ratio = profile.above_high_count / total
        if low_ratio > 0.1 and high_ratio > 0.1:
            profile.is_floating = True
            profile.health = "warning"
            profile.detail = (
                f"Unstable: {low_ratio:.0%} LOW, {high_ratio:.0%} HIGH, "
                f"{undef_ratio:.0%} undefined"
            )
            return

        # Marginal voltage: avg near TTL threshold boundaries
        if profile.dominant_zone == "HIGH":
            margin = profile.avg_mv - TTL_HIGH_MIN_MV
            if margin < NOISE_MARGIN_WARNING_MV:
                profile.is_marginal = True
                profile.health = "warning"
                profile.detail = (
                    f"Marginal HIGH: {profile.avg_mv}mV "
                    f"(only {margin}mV above threshold)"
                )
                return
        elif profile.dominant_zone == "LOW":
            margin = TTL_LOW_MAX_MV - profile.avg_mv
            if margin < NOISE_MARGIN_WARNING_MV:
                profile.is_marginal = True
                profile.health = "warning"
                profile.detail = (
                    f"Marginal LOW: {profile.avg_mv}mV "
                    f"(only {margin}mV below threshold)"
                )
                return

        # Noisy but within zone
        if profile.noise_level in ("moderate", "high"):
            profile.health = "warning"
            profile.detail = (
                f"{profile.noise_level.title()} noise: "
                f"{profile.spread_mv}mV spread "
                f"({profile.min_mv}-{profile.max_mv}mV)"
            )
            return

        # Clean and within zone
        profile.health = "ok"
        profile.detail = (
            f"{profile.dominant_zone} @ {profile.avg_mv}mV "
            f"(spread {profile.spread_mv}mV, {profile.noise_level})"
        )

    # ------------------------------------------------------------------
    # Full chip analog analysis
    # ------------------------------------------------------------------

    def analyze_chip_analog(
        self,
        chip_data: Dict,
        analog_pin_map: Dict[str, int],
        progress_callback: ProgressCallback = None,
        num_samples: int = None,
    ) -> AnalogReport:
        """
        Run full analog voltage analysis on a chip's output pins.

        Args:
            chip_data: Chip definition dictionary
            analog_pin_map: Dict mapping chip_pin_name → analog Arduino pin (54-69)
                           Example: {"1Y": 54, "2Y": 55, "3Y": 56, "4Y": 57}
            progress_callback: Optional progress callback
            num_samples: Samples per pin for profiling

        Returns:
            AnalogReport with voltage readings and health assessment
        """
        chip_id = chip_data.get("chipId", "Unknown")
        pinout = chip_data.get("pinout", {})

        report = AnalogReport(
            chip_id=chip_id,
            analog_pin_map=analog_pin_map,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        if progress_callback:
            progress_callback(f"\n{'═' * 50}")
            progress_callback(f"🔬 ANALOG VOLTAGE ANALYSIS: {chip_id}")
            progress_callback(f"{'═' * 50}")
            progress_callback(f"  Analog pins mapped: {len(analog_pin_map)}")

        if not self.check_firmware_support():
            if progress_callback:
                progress_callback("  ❌ Firmware v9.0+ required for analog analysis")
                progress_callback("     Please upload the latest firmware to the Arduino")
            return report

        # 1. Check power rails first. Bad power can make every later pin profile
        # look suspicious, so we want that context early in the report.
        vcc_pin_num = pinout.get("vcc")
        gnd_pin_num = pinout.get("gnd")
        self._check_power_rails(report, vcc_pin_num, gnd_pin_num,
                                analog_pin_map, progress_callback)

        # 2. Profile each mapped output pin. Output lines are where analog
        # health is usually most informative because the chip is actively driving
        # them and weak/floating behavior is easier to spot.
        output_pins = pinout.get("outputs", [])
        if progress_callback:
            progress_callback(f"\n  📊 Profiling output pin voltages...")

        for out in output_pins:
            pin_name = out["name"]
            if pin_name not in analog_pin_map:
                continue

            ard_pin = analog_pin_map[pin_name]
            chip_pin = out["pin"]

            profile = self.profile_pin_voltage(
                arduino_pin=ard_pin,
                pin_name=pin_name,
                chip_pin=chip_pin,
                num_samples=num_samples,
            )
            report.pin_profiles[pin_name] = profile

            # Track issues
            if profile.is_floating:
                report.floating_pins.append(pin_name)
            if profile.is_marginal:
                report.marginal_pins.append(pin_name)
            if profile.noise_level in ("moderate", "high"):
                report.noisy_pins.append(pin_name)

            if progress_callback:
                icon = {"ok": "🟢", "warning": "🟡", "error": "🔴"}.get(
                    profile.health, "⚪"
                )
                progress_callback(
                    f"    {icon} {pin_name} (pin {chip_pin} → A{ard_pin - 54}): "
                    f"{profile.avg_mv}mV [{profile.dominant_zone}] "
                    f"range {profile.min_mv}-{profile.max_mv}mV "
                    f"({profile.noise_level} noise)"
                )
                if profile.health != "ok":
                    progress_callback(f"       → {profile.detail}")

        # 3. Input pins usually do not need full profiling, but a one-shot read
        # still helps confirm they are sitting in a sane TTL region.
        input_pins = pinout.get("inputs", [])
        for inp in input_pins:
            pin_name = inp["name"]
            if pin_name not in analog_pin_map:
                continue

            ard_pin = analog_pin_map[pin_name]
            reading = self.read_voltage(
                arduino_pin=ard_pin, pin_name=pin_name, chip_pin=inp["pin"]
            )
            report.pin_readings[pin_name] = reading

            if progress_callback:
                progress_callback(
                    f"    📌 {pin_name} (input, pin {inp['pin']} → A{ard_pin - 54}): "
                    f"{reading.voltage_str} [{reading.ttl_zone}]"
                )

        # 4. Collapse the per-pin observations into the summary state shown to
        # the user and dashboard.
        report.overall_voltage_health = self._assess_overall_health(report)
        report.recommendations = self._generate_recommendations(report)

        if progress_callback:
            progress_callback(f"\n  Overall voltage health: {report.overall_voltage_health.upper()}")
            for rec in report.recommendations:
                progress_callback(f"  {rec}")
            progress_callback(f"{'═' * 50}")

        logger.info(
            f"Analog analysis complete: {chip_id}, "
            f"floating={len(report.floating_pins)}, "
            f"marginal={len(report.marginal_pins)}, "
            f"noisy={len(report.noisy_pins)}"
        )
        return report

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_power_rails(self, report, vcc_pin, gnd_pin,
                           analog_pin_map, progress_callback):
        """Measure VCC and GND voltage if they're mapped to analog pins."""
        if progress_callback:
            progress_callback(f"\n  ⚡ Power rail check:")

        # Power rails are optional in the analog map. When present, they provide
        # strong evidence for whether later pin anomalies are chip-related or
        # simply caused by bad supply/ground wiring.
        # Check VCC
        vcc_name = f"VCC_pin{vcc_pin}" if vcc_pin else None
        if vcc_name and vcc_name in analog_pin_map:
            vcc_ard = analog_pin_map[vcc_name]
            reading = self.read_voltage(vcc_ard, "VCC", vcc_pin)
            report.vcc_mv = reading.millivolts
            if report.vcc_mv < 4500:
                report.power_ok = False
                if progress_callback:
                    progress_callback(
                        f"    ⚠️ VCC: {report.vcc_mv}mV (expected ~5000mV)"
                    )
            else:
                if progress_callback:
                    progress_callback(f"    ✅ VCC: {report.vcc_mv}mV")

        # Check GND
        gnd_name = f"GND_pin{gnd_pin}" if gnd_pin else None
        if gnd_name and gnd_name in analog_pin_map:
            gnd_ard = analog_pin_map[gnd_name]
            reading = self.read_voltage(gnd_ard, "GND", gnd_pin)
            report.gnd_mv = reading.millivolts
            if report.gnd_mv > 100:
                report.power_ok = False
                if progress_callback:
                    progress_callback(
                        f"    ⚠️ GND: {report.gnd_mv}mV (expected ~0mV)"
                    )
            else:
                if progress_callback:
                    progress_callback(f"    ✅ GND: {report.gnd_mv}mV")

        if not vcc_name and not gnd_name:
            if progress_callback:
                progress_callback("    ℹ️ VCC/GND not mapped to analog pins — skipped")

    def _assess_overall_health(self, report: AnalogReport) -> str:
        """Determine overall voltage health from all profiles."""
        if report.floating_pins or not report.power_ok:
            return "error"
        if report.marginal_pins or report.noisy_pins:
            return "warning"
        return "ok"

    def _generate_recommendations(self, report: AnalogReport) -> List[str]:
        """Generate recommendations based on analog analysis findings."""
        recs = []

        if not report.power_ok:
            if report.vcc_mv and report.vcc_mv < 4500:
                recs.append(
                    f"🔴 VCC is {report.vcc_mv}mV — check power supply and wiring"
                )
            if report.gnd_mv and report.gnd_mv > 100:
                recs.append(
                    f"🔴 GND is {report.gnd_mv}mV — check ground connection"
                )

        for pn in report.floating_pins:
            profile = report.pin_profiles.get(pn)
            if profile:
                recs.append(
                    f"🔴 {pn}: floating at {profile.avg_mv}mV — "
                    f"check input connections to this gate"
                )

        for pn in report.marginal_pins:
            profile = report.pin_profiles.get(pn)
            if profile:
                recs.append(
                    f"🟡 {pn}: marginal voltage ({profile.avg_mv}mV) — "
                    f"gate may be degraded or overloaded"
                )

        for pn in report.noisy_pins:
            profile = report.pin_profiles.get(pn)
            if profile:
                recs.append(
                    f"🟡 {pn}: noisy signal ({profile.spread_mv}mV spread) — "
                    f"add bypass capacitor or check for crosstalk"
                )

        if not recs and report.pin_profiles:
            recs.append("✅ All measured voltages within TTL specifications")

        return recs

    @staticmethod
    def get_analog_pin_guide() -> str:
        """
        Return a guide for mapping IC outputs to analog pins.
        Displayed in the GUI when the user activates analog mode.
        """
        return """
╔══════════════════════════════════════════════════╗
║  ANALOG VOLTAGE ANALYSIS — PIN MAPPING GUIDE    ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  To measure voltage levels, wire IC outputs to   ║
║  the Arduino Mega's ANALOG pins:                 ║
║                                                  ║
║  Analog Pin    Digital Pin    Board Label        ║
║  ──────────    ───────────    ───────────        ║
║  A0            54             A0                 ║
║  A1            55             A1                 ║
║  A2            56             A2                 ║
║  A3            57             A3                 ║
║  A4            58             A4                 ║
║  A5            59             A5                 ║
║  A6            60             A6                 ║
║  A7            61             A7                 ║
║  A8            62             A8                 ║
║  A9            63             A9                 ║
║  A10           64             A10                ║
║  A11           65             A11                ║
║  A12           66             A12                ║
║  A13           67             A13                ║
║  A14           68             A14                ║
║  A15           69             A15                ║
║                                                  ║
║  USAGE:                                          ║
║  1. Keep digital test wiring as-is (pins 2-53)   ║
║  2. Add extra jumper wires from IC outputs to    ║
║     analog pins (A0-A15) for voltage analysis    ║
║  3. Same IC output can connect to BOTH a digital ║
║     test pin AND an analog measurement pin       ║
║                                                  ║
║  TTL VOLTAGE THRESHOLDS:                         ║
║  • Valid LOW:   0.0V - 0.8V   (healthy)         ║
║  • UNDEFINED:   0.8V - 2.0V   (floating/bad)    ║
║  • Valid HIGH:  2.0V - 5.0V   (healthy)         ║
║                                                  ║
║  ADC: 10-bit (0-1023), ~4.88mV per step          ║
║  Sample time: ~104μs per analogRead()            ║
╚══════════════════════════════════════════════════╝
"""
