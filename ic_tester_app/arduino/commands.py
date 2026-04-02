# ic_tester_app/arduino/commands.py
# Last edited: 2026-01-19
# Purpose: Arduino command protocol and helper functions
# Dependencies: None (uses connection module)

"""
Arduino command helpers.

This module sits one level above the raw serial connection and translates
semantic operations used by the GUI/test engine into the firmware's string
protocol.

The main jobs here are:
- normalize board-specific pin rules after handshake,
- format commands consistently,
- parse firmware replies into Python dictionaries,
- keep board detection and validation logic in one place.
"""

from typing import Optional, Dict, List, Tuple
from ..logger import get_logger

logger = get_logger("arduino.commands")


class ArduinoCommands:
    """
    High-level Arduino command interface for IC testing.
    
    Wraps the low-level connection with semantic commands for:
    - Pin mode configuration
    - Pin state control (read/write)
    - Batch operations
    - Board-specific pin range validation
    """
    
    # Board-specific pin configurations.
    #
    # The rest of the app reasons in "Arduino pin numbers", so both digital and
    # analog channels are normalized into the numeric ranges reported by the
    # firmware. That lets the GUI and diagnostics use one validation model per
    # board instead of hard-coding Mega/Uno rules everywhere.
    BOARD_CONFIGS = {
        "MEGA2560": {
            "digital_pins": (2, 53),  # pins 2-53
            "analog_pins": (54, 69),  # A0-A15 = pins 54-69
            "analog_offset": 54,      # A0 starts at pin 54
        },
        "UNO_R3": {
            "digital_pins": (2, 13),  # pins 2-13
            "analog_pins": (14, 19),  # A0-A5 = pins 14-19
            "analog_offset": 14,      # A0 starts at pin 14
        },
    }
    
    def __init__(self, connection):
        """
        Args:
            connection: ArduinoConnection instance
        """
        self.conn = connection
        # Board metadata is filled in immediately so callers can validate pin
        # mappings as soon as a connection is established.
        self.board_type = None
        self.pin_config = None
        self._detect_board_type()
    
    # =========================================================================
    # Pin Configuration Commands
    # =========================================================================
    
    def set_pin_mode(self, pin: int, mode: str) -> bool:
        """
        Set pin mode (INPUT/OUTPUT).
        
        Args:
            pin: Arduino pin number
            mode: 'INPUT' or 'OUTPUT'
        
        Returns:
            True if successful
        """
        command = f"MODE,{pin},{mode}"
        response = self.conn.send_and_receive(command)
        success = response == "OK"
        
        if not success:
            logger.warning(f"Failed to set pin {pin} to {mode}: {response}")
        
        return success
    
    def set_pin_input(self, pin: int) -> bool:
        """Set pin as INPUT"""
        return self.set_pin_mode(pin, "INPUT")
    
    def set_pin_output(self, pin: int) -> bool:
        """Set pin as OUTPUT"""
        return self.set_pin_mode(pin, "OUTPUT")
    
    # =========================================================================
    # Pin State Commands
    # =========================================================================
    
    def write_pin(self, pin: int, state: str) -> bool:
        """
        Write digital state to pin.
        
        Args:
            pin: Arduino pin number
            state: 'HIGH' or 'LOW'
        
        Returns:
            True if successful
        """
        command = f"SET,{pin},{state}"
        response = self.conn.send_and_receive(command)
        return response == "OK"
    
    def write_high(self, pin: int) -> bool:
        """Write HIGH to pin"""
        return self.write_pin(pin, "HIGH")
    
    def write_low(self, pin: int) -> bool:
        """Write LOW to pin"""
        return self.write_pin(pin, "LOW")
    
    def read_pin(self, pin: int) -> Optional[str]:
        """
        Read digital state from pin.
        
        Args:
            pin: Arduino pin number
        
        Returns:
            'HIGH', 'LOW', or None if error
        """
        command = f"READ,{pin}"
        response = self.conn.send_and_receive(command)
        
        if response in ['HIGH', 'LOW']:
            return response
        
        logger.warning(f"Unexpected read response for pin {pin}: {response}")
        return None
    
    # =========================================================================
    # Batch Operations (more efficient for multi-pin operations)
    # =========================================================================
    
    def batch_set_pins(self, pin_states: Dict[int, str]) -> bool:
        """
        Set multiple pins at once.
        
        Args:
            pin_states: Dict of {pin: state} where state is 'HIGH' or 'LOW'
        
        Returns:
            True if all successful
        """
        if not pin_states:
            return True
        
        # Bundle state changes into one command where supported by the firmware.
        # This reduces serial round-trips during larger setup/reset operations.
        pairs = [f"{pin}:{state}" for pin, state in pin_states.items()]
        command = f"BSET,{','.join(pairs)}"
        response = self.conn.send_and_receive(command)
        return response == "OK"
    
    def batch_read_pins(self, pins: List[int]) -> Dict[int, str]:
        """
        Read multiple pins at once.
        
        Args:
            pins: List of pin numbers to read
        
        Returns:
            Dict of {pin: state} results
        """
        if not pins:
            return {}
        
        # Format: BREAD,pin1,pin2,pin3,...
        command = f"BREAD,{','.join(map(str, pins))}"
        response = self.conn.send_and_receive(command)
        
        if not response:
            logger.warning("No response from batch read")
            return {}
        
        # Parse response: pin1:state1,pin2:state2,...
        results = {}
        try:
            for pair in response.split(','):
                if ':' in pair:
                    pin_str, state = pair.split(':')
                    results[int(pin_str)] = state
        except ValueError as e:
            logger.error(f"Error parsing batch read response: {e}")
        
        return results
    
    def batch_set_modes(self, pin_modes: Dict[int, str]) -> bool:
        """
        Set modes for multiple pins at once.
        
        Args:
            pin_modes: Dict of {pin: mode} where mode is 'INPUT' or 'OUTPUT'
        
        Returns:
            True if all successful
        """
        if not pin_modes:
            return True
        
        # Format: BMODE,pin1:mode1,pin2:mode2,...
        pairs = [f"{pin}:{mode}" for pin, mode in pin_modes.items()]
        command = f"BMODE,{','.join(pairs)}"
        response = self.conn.send_and_receive(command)
        return response == "OK"
    
    # =========================================================================
    # Utility Commands
    # =========================================================================
    
    def _detect_board_type(self):
        """
        Detect board type from the firmware STATUS response.

        This is the bridge between "a serial device is connected" and
        "the rest of the app now knows which pins are legal". If detection
        fails we fall back to Mega behavior because that was the original
        hardware target and is the least surprising legacy default.
        """
        try:
            response = self.conn.send_and_receive("STATUS", timeout=1.0)
            if response and "STATUS_OK" in response:
                parts = response.split(",")
                if len(parts) >= 2:
                    board = parts[1].strip()
                    if board in self.BOARD_CONFIGS:
                        self.board_type = board
                        self.pin_config = self.BOARD_CONFIGS[board]
                        logger.info(f"Detected board: {board}")
                        return
            # Default to MEGA2560 if detection fails
            logger.warning("Board detection failed, defaulting to MEGA2560")
            self.board_type = "MEGA2560"
            self.pin_config = self.BOARD_CONFIGS["MEGA2560"]
        except Exception as e:
            logger.error(f"Error detecting board type: {e}")
            self.board_type = "MEGA2560"
            self.pin_config = self.BOARD_CONFIGS["MEGA2560"]
    
    def get_board_type(self) -> str:
        """Get detected board type."""
        return self.board_type or "UNKNOWN"
    
    def get_pin_ranges(self) -> Dict[str, Tuple[int, int]]:
        """Get valid pin ranges for current board."""
        if self.pin_config:
            return {
                "digital": self.pin_config["digital_pins"],
                "analog": self.pin_config["analog_pins"],
            }
        return {"digital": (2, 53), "analog": (54, 69)}  # Default to Mega
    
    def is_valid_digital_pin(self, pin: int) -> bool:
        """Check if pin is valid for digital I/O on current board."""
        if not self.pin_config:
            return 2 <= pin <= 53  # Default to Mega range
        d_min, d_max = self.pin_config["digital_pins"]
        a_min, a_max = self.pin_config["analog_pins"]
        return (d_min <= pin <= d_max) or (a_min <= pin <= a_max)
    
    def is_valid_analog_pin(self, pin: int) -> bool:
        """Check if pin is valid for analog input on current board."""
        if not self.pin_config:
            return 54 <= pin <= 69  # Default to Mega range
        a_min, a_max = self.pin_config["analog_pins"]
        return a_min <= pin <= a_max
    
    def ping(self) -> bool:
        """Test connection with PING/PONG"""
        response = self.conn.send_and_receive("PING")
        return response == "PONG"
    
    def get_version(self) -> Optional[str]:
        """Get Arduino firmware version"""
        return self.conn.send_and_receive("VERSION")
    
    def reset_all_pins(self, pins: List[int]) -> bool:
        """
        Reset all specified pins to LOW/INPUT.
        
        Args:
            pins: List of pins to reset
        
        Returns:
            True if successful
        """
        # Drive every tracked line LOW in a predictable way before a new test so
        # the previous chip state does not leak into the next measurement.
        modes = {pin: "OUTPUT" for pin in pins}
        states = {pin: "LOW" for pin in pins}
        
        return self.batch_set_modes(modes) and self.batch_set_pins(states)
    
    # =========================================================================
    # Enhanced Firmware v8.0 Commands
    # =========================================================================
    
    def rapid_sample(self, pin: int, count: int = 100) -> Optional[Dict]:
        """
        Take N rapid consecutive reads of a pin for stability analysis.
        Requires firmware v8.0+.
        
        Args:
            pin: Arduino pin number to sample
            count: Number of rapid samples (1-500)
        
        Returns:
            Dict with high_count, low_count, duration_us or None on error
        """
        # The firmware does the tight sampling loop because Python serial latency
        # is far too slow and jittery for stability analysis.
        command = f"RAPID_SAMPLE,{pin},{count}"
        response = self.conn.send_and_receive(command, timeout=2.0)
        
        if not response or not response.startswith("RAPID_SAMPLE_OK,"):
            logger.warning(f"RAPID_SAMPLE failed for pin {pin}: {response}")
            return None
        
        try:
            parts = response.split(",")
            return {
                "pin": int(parts[1]),
                "high_count": int(parts[2]),
                "low_count": int(parts[3]),
                "duration_us": int(parts[4]),
            }
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing RAPID_SAMPLE response: {e}")
            return None
    
    def timed_read(self, pin: int, interval_us: int = 100, count: int = 50) -> Optional[Dict]:
        """
        Read a pin at fixed intervals for waveform capture.
        Requires firmware v8.0+.
        
        Args:
            pin: Arduino pin number
            interval_us: Microseconds between samples (min 4)
            count: Number of samples (1-200)
        
        Returns:
            Dict with samples string (H/L chars), duration_us or None on error
        """
        # This mode captures a compact H/L waveform snapshot on the board and
        # returns the compressed sample string to Python for analysis.
        command = f"TIMED_READ,{pin},{interval_us},{count}"
        response = self.conn.send_and_receive(command, timeout=3.0)
        
        if not response or not response.startswith("TIMED_READ_OK,"):
            logger.warning(f"TIMED_READ failed for pin {pin}: {response}")
            return None
        
        try:
            parts = response.split(",")
            return {
                "pin": int(parts[1]),
                "samples": parts[2],
                "duration_us": int(parts[3]),
            }
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing TIMED_READ response: {e}")
            return None
    
    def set_and_time(self, set_pin: int, state: str, read_pin: int) -> Optional[Dict]:
        """
        Set an input pin and measure propagation delay until output changes.
        Requires firmware v8.0+.
        
        Args:
            set_pin: Arduino pin to drive
            state: 'HIGH' or 'LOW' to set
            read_pin: Arduino pin to monitor for state change
        
        Returns:
            Dict with prev_state, new_state, delay_us, timed_out or None on error
        """
        # Used for propagation-delay style measurements: flip one line, then let
        # firmware time how long the observed output takes to follow.
        command = f"SET_AND_TIME,{set_pin},{state},{read_pin}"
        response = self.conn.send_and_receive(command, timeout=2.0)
        
        if not response or not response.startswith("SET_AND_TIME_OK,"):
            logger.warning(f"SET_AND_TIME failed: {response}")
            return None
        
        try:
            parts = response.split(",")
            return {
                "set_pin": int(parts[1]),
                "read_pin": int(parts[2]),
                "prev_state": parts[3],
                "new_state": parts[4],
                "delay_us": int(parts[5]),
                "timed_out": parts[4] == "TIMEOUT",
            }
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing SET_AND_TIME response: {e}")
            return None
    
    def get_firmware_version(self) -> Optional[str]:
        """
        Get firmware version string.
        
        Returns:
            Version string (e.g. '9.0') or None
        """
        response = self.conn.send_and_receive("VERSION", timeout=1.0)
        if response and response.startswith("VERSION,"):
            return response.split(",")[1].strip()
        return None
    
    # =========================================================================
    # Analog Voltage Measurement Commands (Firmware v9.0+)
    # =========================================================================
    
    def analog_read(self, pin: int) -> Optional[Dict]:
        """
        Read analog voltage on a single pin.
        Mega 2560: A0-A15 = digital 54-69
        Uno R3: A0-A5 = digital 14-19
        Requires firmware v9.0+.
        
        Args:
            pin: Arduino analog pin number (board-specific)
        
        Returns:
            Dict with raw (0-1023), millivolts (0-5000), zone (LOW/UNDEFINED/HIGH)
            or None on error
        """
        # Validate first so callers get a clean Python-side failure instead of
        # firing a command the board can only reject later.
        if not self.is_valid_analog_pin(pin):
            logger.error(f"Pin {pin} is not a valid analog pin for {self.board_type}")
            return None
        command = f"ANALOG_READ,{pin}"
        response = self.conn.send_and_receive(command, timeout=1.0)
        
        if not response or not response.startswith("ANALOG_READ_OK,"):
            logger.warning(f"ANALOG_READ failed for pin {pin}: {response}")
            return None
        
        try:
            parts = response.split(",")
            return {
                "pin": int(parts[1]),
                "raw": int(parts[2]),
                "millivolts": int(parts[3]),
                "zone": parts[4],
            }
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing ANALOG_READ response: {e}")
            return None
    
    def analog_read_pins(self, pins: List[int]) -> Dict[int, Dict]:
        """
        Batch analog read on multiple pins.
        Mega 2560: A0-A15 = digital 54-69
        Uno R3: A0-A5 = digital 14-19
        Requires firmware v9.0+.
        
        Args:
            pins: List of analog pin numbers (board-specific)
        
        Returns:
            Dict mapping pin → {raw, millivolts, zone}
        """
        # Keep the command focused on legal analog channels for the detected
        # board. This is especially important when users switch between Mega and
        # Uno mappings without restarting the GUI.
        # Filter out invalid pins
        valid_pins = [p for p in pins if self.is_valid_analog_pin(p)]
        if len(valid_pins) != len(pins):
            invalid = set(pins) - set(valid_pins)
            logger.warning(f"Filtered out invalid analog pins for {self.board_type}: {invalid}")
        if not valid_pins:
            return {}
        
        command = f"ANALOG_READ_PINS,{','.join(map(str, valid_pins))}"
        response = self.conn.send_and_receive(command, timeout=2.0)
        
        if not response or not response.startswith("ANALOG_READ_PINS_OK,"):
            logger.warning(f"ANALOG_READ_PINS failed: {response}")
            return {}
        
        results = {}
        try:
            data = response[len("ANALOG_READ_PINS_OK,"):]
            for entry in data.split(","):
                parts = entry.split(":")
                if len(parts) >= 4:
                    results[int(parts[0])] = {
                        "raw": int(parts[1]),
                        "millivolts": int(parts[2]),
                        "zone": parts[3],
                    }
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing ANALOG_READ_PINS response: {e}")
        
        return results
    
    def analog_rapid_sample(self, pin: int, count: int = 100) -> Optional[Dict]:
        """
        Take N rapid analog reads for voltage distribution analysis.
        Mega 2560: A0-A15 = digital 54-69
        Uno R3: A0-A5 = digital 14-19
        Requires firmware v9.0+.
        
        Args:
            pin: Analog pin number (board-specific)
            count: Number of rapid samples (1-500)
        
        Returns:
            Dict with min/max/avg ADC values, zone distribution counts,
            and duration_us, or None on error
        """
        # Like `rapid_sample`, but for voltage zones rather than binary logic.
        if not self.is_valid_analog_pin(pin):
            logger.error(f"Pin {pin} is not a valid analog pin for {self.board_type}")
            return None
        command = f"ANALOG_RAPID_SAMPLE,{pin},{count}"
        response = self.conn.send_and_receive(command, timeout=3.0)
        
        if not response or not response.startswith("ANALOG_RAPID_SAMPLE_OK,"):
            logger.warning(f"ANALOG_RAPID_SAMPLE failed for pin {pin}: {response}")
            return None
        
        try:
            parts = response.split(",")
            return {
                "pin": int(parts[1]),
                "count": int(parts[2]),
                "min_adc": int(parts[3]),
                "max_adc": int(parts[4]),
                "avg_adc": int(parts[5]),
                "below_low": int(parts[6]),
                "in_undefined": int(parts[7]),
                "above_high": int(parts[8]),
                "duration_us": int(parts[9]),
                "min_mv": int(parts[3]) * 5000 // 1023,
                "max_mv": int(parts[4]) * 5000 // 1023,
                "avg_mv": int(parts[5]) * 5000 // 1023,
            }
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing ANALOG_RAPID_SAMPLE response: {e}")
            return None
