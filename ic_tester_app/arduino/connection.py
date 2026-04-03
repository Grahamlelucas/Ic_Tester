# ic_tester_app/arduino/connection.py
# Last edited: 2026-01-19
# Purpose: Arduino serial connection management for Mega 2560
# Dependencies: serial, serial.tools.list_ports

"""
Arduino connection module.

This layer is intentionally small and procedural because every higher-level
system depends on it behaving predictably:

1. Discover likely Arduino serial ports.
2. Open the selected serial device without causing unnecessary resets.
3. Wait for the firmware boot banner / handshake.
4. Provide safe send/receive helpers to the rest of the app.
5. Separate normal command replies from asynchronous firmware events.
"""

import time
from typing import Optional, List

import serial
import serial.tools.list_ports

from ..config import Config
from ..logger import get_logger
from .commands import ArduinoCommands

logger = get_logger("arduino.connection")


class ArduinoConnection:
    """
    Manage serial communication with the tester firmware.

    The GUI, tester, and diagnostics layers all funnel through this object so
    they do not each need to worry about serial timing, disconnect behavior, or
    handshake details.
    """
    
    def __init__(self):
        # `_serial` holds the live pyserial object after a successful connect.
        self._serial: Optional[serial.Serial] = None
        # `_connected` tracks logical connection state; it is cleared on any
        # send/read failure so the UI can react immediately.
        self._connected: bool = False
        self._port: Optional[str] = None
        # Firmware can emit out-of-band `EVT,...` lines while a test is running.
        # We queue them here so command/response reads stay deterministic.
        self._event_queue: List[str] = []
        # Board-aware command helper is created after a successful handshake.
        self.commands: Optional[ArduinoCommands] = None
        
        logger.info("ArduinoConnection initialized")
    
    @property
    def connected(self) -> bool:
        """Check if Arduino is connected"""
        return self._connected and self._serial is not None
    
    @property
    def port(self) -> Optional[str]:
        """Get current port name"""
        return self._port
    
    def find_arduino_ports(self) -> List[str]:
        """
        Scan for Arduino devices on available serial ports.
        
        Returns:
            List of port names that appear to be Arduino devices
        """
        ports = serial.tools.list_ports.comports()
        arduino_ports = []
        
        for port in ports:
            port_name = port.device
            description = port.description.lower()
            
            # We intentionally use a broad heuristic here because classrooms
            # often use genuine boards, clones, CH340 adapters, and different
            # USB naming conventions across macOS, Windows, and Linux.
            is_arduino = (
                'arduino' in description or
                'mega' in description or
                'usbmodem' in port_name.lower() or
                'usbserial' in port_name.lower() or
                port_name.startswith('/dev/ttyACM') or
                port_name.startswith('/dev/ttyUSB') or
                (port_name.startswith('COM') and 'usb' in description)
            )
            
            if is_arduino:
                arduino_ports.append(port_name)
                logger.debug(f"Found Arduino port: {port_name} ({port.description})")
        
        logger.info(f"Port scan complete: {len(arduino_ports)} Arduino device(s) found")
        return arduino_ports
    
    def connect(self, port: str) -> bool:
        """
        Establish connection to Arduino on specified port.
        
        Args:
            port: Serial port name (e.g., '/dev/ttyACM0', 'COM3')
        
        Returns:
            True if connection successful, False otherwise
        """
        logger.info(f"Attempting connection to {port}")
        
        try:
            # Close existing connection if any
            if self._serial:
                self.disconnect()
            
            # Open serial connection with DTR disabled to prevent
            # Arduino reset on connect/reconnect.
            self._serial = serial.Serial(
                port, 
                Config.SERIAL_BAUD_RATE, 
                timeout=Config.SERIAL_TIMEOUT,
                dsrdtr=False,
            )
            self._serial.dtr = False
            self._port = port
            
            # Wait for the firmware to finish booting.
            #
            # Important behavior:
            # - Opening a serial port can reset many Arduino boards.
            # - During that reset window the firmware may miss early commands.
            # - Listening for `READY` first is more reliable than immediately
            #   sending traffic and hoping the board is already running.
            time.sleep(0.3)
            ready_timeout = 10.0
            start_time = time.time()
            
            while time.time() - start_time < ready_timeout:
                while self._serial.in_waiting > 0:
                    line = self._serial.readline().decode('utf-8', errors='ignore').strip()
                    if not line:
                        continue
                    logger.debug(f"Received during handshake: {line}")
                    if line == "READY" or line == "PONG":
                        self._connected = True
                        self._init_commands()
                        logger.info(f"Connected to Arduino on {port} (handshake: {line})")
                        return True
                time.sleep(0.05)

            # If the boot banner was missed, fall back to active probing.
            # This keeps reconnects resilient when the OS or serial adapter
            # drops buffered startup text before Python can read it.
            for attempt in range(3):
                try:
                    self._serial.reset_input_buffer()
                    self._serial.write(b"PING\n")
                    ping_start = time.time()
                    while time.time() - ping_start < 1.5:
                        if self._serial.in_waiting > 0:
                            line = self._serial.readline().decode('utf-8', errors='ignore').strip()
                            if line:
                                logger.debug(f"PING response attempt {attempt+1}: {line}")
                            if line == "PONG" or line == "READY":
                                self._connected = True
                                self._init_commands()
                                logger.info(f"Connected to Arduino on {port} (PING retry)")
                                return True
                        time.sleep(0.03)
                except Exception:
                    pass
            
            # Connection failed
            logger.warning(f"Connection handshake failed on {port}")
            self._serial.close()
            self._serial = None
            self._port = None
            self.commands = None
            return False
            
        except serial.SerialException as e:
            logger.error(f"Serial error connecting to {port}: {e}")
            self.commands = None
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to {port}: {e}")
            self.commands = None
            return False
    
    def disconnect(self):
        """Close the Arduino connection"""
        if self._serial:
            try:
                self._serial.close()
                logger.info(f"Disconnected from {self._port}")
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")
            finally:
                self._serial = None
                self._port = None
        
        self._connected = False
        self._event_queue.clear()
        self.commands = None

    def _init_commands(self):
        """Create the board-aware command helper after a successful connect."""
        try:
            self.commands = ArduinoCommands(self)
        except Exception as e:
            logger.warning(f"Failed to initialize ArduinoCommands helper: {e}")
            self.commands = None
    
    def send_command(self, command: str) -> bool:
        """
        Send a command string to Arduino.
        
        Args:
            command: Command to send (newline will be appended)
        
        Returns:
            True if send successful, False otherwise
        """
        if not self._connected or not self._serial:
            logger.warning(f"Cannot send command '{command}': not connected")
            return False
        
        try:
            # Every firmware command is line-oriented. Appending `\n` keeps the
            # protocol easy to debug in the Arduino serial monitor as well.
            self._serial.write(f"{command}\n".encode('utf-8'))
            logger.debug(f"Sent: {command}")
            return True
        except serial.SerialException as e:
            logger.error(f"Error sending command '{command}': {e}")
            self._connected = False
            return False
    
    def read_response(self, timeout: float = 0.15) -> Optional[str]:
        """
        Read a response line from Arduino.
        
        Args:
            timeout: Maximum time to wait for response in seconds
        
        Returns:
            Response string or None if timeout/error
        """
        if not self._connected or not self._serial:
            return None
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if self._serial.in_waiting > 0:
                    response = self._serial.readline().decode('utf-8', errors='ignore').strip()
                    if not response:
                        continue
                    if response.startswith("EVT,"):
                        # Event lines are not direct replies to the command that
                        # is currently waiting, so stash them for the event poller.
                        self._event_queue.append(response)
                        logger.debug(f"Queued event: {response}")
                        continue
                    logger.debug(f"Received: {response}")
                    return response
            except serial.SerialException as e:
                logger.error(f"Error reading response: {e}")
                self._connected = False
                return None
            time.sleep(0.01)
        
        return None
    
    def send_and_receive(self, command: str, timeout: float = 0.5) -> Optional[str]:
        """
        Send a command and wait for response.
        
        Args:
            command: Command to send
            timeout: Maximum time to wait for response
        
        Returns:
            Response string or None if timeout/error
        """
        if not self.send_command(command):
            return None
        
        # A short inter-command gap prevents back-to-back GUI operations from
        # overrunning slower firmware handlers.
        time.sleep(Config.COMMAND_DELAY)
        start_time = time.time()
        while time.time() - start_time < timeout:
            response = self.read_response(timeout=0.05)
            if response is not None:
                return response
        return None
    
    def is_responsive(self) -> bool:
        """
        Check if Arduino is still responding.
        
        Returns:
            True if Arduino responds to PING, False otherwise
        """
        response = self.send_and_receive("PING", timeout=2.0)
        return response == "PONG"
    
    def is_port_alive(self) -> bool:
        """Quick check that the serial port is still present on the system."""
        if not self._serial or not self._port:
            return False
        try:
            # On macOS/Linux, a closed USB port raises on property access.
            _ = self._serial.in_waiting
            return True
        except (OSError, serial.SerialException):
            logger.warning(f"Port {self._port} is no longer available")
            self._connected = False
            return False

    def clear_buffer(self) -> bool:
        """Clear any pending data in serial buffer.
        Returns True on success, False if the port has died."""
        if not self._serial:
            return False
        try:
            # Clear both directions so a previous failed test cannot poison the
            # next handshake or pin operation with stale bytes.
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            self._event_queue.clear()
            return True
        except (OSError, serial.SerialException) as e:
            logger.error(f"Error clearing buffer (port likely disconnected): {e}")
            self._connected = False
            return False
    
    def drain_events(self) -> List[str]:
        """Return and clear queued firmware EVT lines."""
        events = list(self._event_queue)
        self._event_queue.clear()
        return events
