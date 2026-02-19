# ic_tester_app/arduino/device_info.py
# Last edited: 2026-01-20
# Purpose: Extract detailed device information from connected Arduino
# Dependencies: serial, serial.tools.list_ports

"""
Arduino Device Information module.

Extracts detailed hardware and firmware information from connected Arduino:
- Hardware identifiers (VID, PID, serial number)
- Board model detection
- Firmware version and capabilities
- Connection health metrics
"""

import time
from typing import Dict, Optional, Any
from dataclasses import dataclass

import serial
import serial.tools.list_ports

from ..logger import get_logger

logger = get_logger("arduino.device_info")


# Arduino Vendor/Product IDs for identification
ARDUINO_IDENTIFIERS = {
    # Vendor ID 0x2341 = Arduino
    (0x2341, 0x0042): {"model": "Arduino Mega 2560", "board": "mega2560"},
    (0x2341, 0x0010): {"model": "Arduino Mega 2560", "board": "mega2560"},
    (0x2341, 0x0043): {"model": "Arduino Uno", "board": "uno"},
    (0x2341, 0x0001): {"model": "Arduino Uno", "board": "uno"},
    (0x2341, 0x8036): {"model": "Arduino Leonardo", "board": "leonardo"},
    (0x2341, 0x8037): {"model": "Arduino Micro", "board": "micro"},
    # Chinese clones often use CH340
    (0x1A86, 0x7523): {"model": "Arduino Clone (CH340)", "board": "unknown"},
    # FTDI chips
    (0x0403, 0x6001): {"model": "Arduino (FTDI)", "board": "unknown"},
}


@dataclass
class ArduinoDeviceInfo:
    """Complete device information for an Arduino"""
    port: str
    model: str
    board_type: str
    vendor_id: int
    product_id: int
    serial_number: str
    manufacturer: str
    description: str
    firmware_version: str
    ping_time_ms: float
    is_genuine: bool
    capabilities: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for display/storage"""
        return {
            "port": self.port,
            "model": self.model,
            "board_type": self.board_type,
            "vendor_id": f"0x{self.vendor_id:04X}" if self.vendor_id else "Unknown",
            "product_id": f"0x{self.product_id:04X}" if self.product_id else "Unknown",
            "serial_number": self.serial_number or "Unknown",
            "manufacturer": self.manufacturer or "Unknown",
            "firmware_version": self.firmware_version,
            "ping_time_ms": f"{self.ping_time_ms:.1f}",
            "is_genuine": self.is_genuine,
            "capabilities": self.capabilities
        }
    
    def summary(self) -> str:
        """Get human-readable summary"""
        lines = [
            f"📟 {self.model}",
            f"   Port: {self.port}",
            f"   Firmware: {self.firmware_version}",
            f"   Ping: {self.ping_time_ms:.1f}ms",
        ]
        if self.serial_number:
            lines.append(f"   Serial: {self.serial_number}")
        return "\n".join(lines)


class DeviceInfoExtractor:
    """
    Extracts detailed information from Arduino devices.
    
    Provides hardware identification, firmware querying, and
    connection health metrics.
    """
    
    def __init__(self):
        logger.debug("DeviceInfoExtractor initialized")
    
    def get_port_info(self, port_name: str) -> Dict[str, Any]:
        """
        Get hardware information for a serial port.
        
        Args:
            port_name: Serial port name
        
        Returns:
            Dict with port details (vid, pid, serial, manufacturer, etc.)
        """
        ports = serial.tools.list_ports.comports()
        
        for port in ports:
            if port.device == port_name:
                vid = port.vid or 0
                pid = port.pid or 0
                
                # Look up known Arduino identifiers
                identifier = ARDUINO_IDENTIFIERS.get((vid, pid), {})
                
                return {
                    "port": port.device,
                    "description": port.description,
                    "vendor_id": vid,
                    "product_id": pid,
                    "serial_number": port.serial_number or "",
                    "manufacturer": port.manufacturer or "",
                    "model": identifier.get("model", "Unknown Arduino"),
                    "board_type": identifier.get("board", "unknown"),
                    "is_genuine": vid == 0x2341,  # Arduino official VID
                    "hwid": port.hwid
                }
        
        return {"port": port_name, "error": "Port not found"}
    
    def query_firmware(self, serial_conn: serial.Serial) -> Dict[str, Any]:
        """
        Query the Arduino firmware for version and capabilities.
        
        Args:
            serial_conn: Open serial connection
        
        Returns:
            Dict with firmware info
        """
        firmware_info = {
            "version": "Unknown",
            "capabilities": {}
        }
        
        try:
            # Clear any pending data
            serial_conn.reset_input_buffer()
            
            # Send VERSION command (if firmware supports it)
            serial_conn.write(b"VERSION\n")
            time.sleep(0.1)
            
            # Read response
            if serial_conn.in_waiting > 0:
                response = serial_conn.readline().decode('utf-8', errors='ignore').strip()
                if response and not response.startswith("ERROR"):
                    firmware_info["version"] = response
            
            # Query capabilities
            serial_conn.write(b"CAPS\n")
            time.sleep(0.1)
            
            if serial_conn.in_waiting > 0:
                response = serial_conn.readline().decode('utf-8', errors='ignore').strip()
                if response and not response.startswith("ERROR"):
                    # Parse capabilities (format: "CAP1,CAP2,CAP3")
                    caps = response.split(",")
                    firmware_info["capabilities"] = {
                        "features": caps,
                        "has_lcd": "LCD" in caps,
                        "has_counter": "COUNTER" in caps
                    }
                    
        except Exception as e:
            logger.warning(f"Could not query firmware: {e}")
        
        return firmware_info
    
    def measure_ping(self, serial_conn: serial.Serial, samples: int = 3) -> float:
        """
        Measure connection latency.
        
        Args:
            serial_conn: Open serial connection
            samples: Number of ping samples to average
        
        Returns:
            Average ping time in milliseconds
        """
        times = []
        
        for _ in range(samples):
            try:
                serial_conn.reset_input_buffer()
                
                start = time.perf_counter()
                serial_conn.write(b"PING\n")
                
                # Wait for response with timeout
                response = serial_conn.readline()
                end = time.perf_counter()
                
                if response:
                    times.append((end - start) * 1000)  # Convert to ms
                    
            except Exception:
                pass
            
            time.sleep(0.05)
        
        return sum(times) / len(times) if times else 999.9
    
    def get_full_device_info(self, port_name: str, 
                            serial_conn: Optional[serial.Serial] = None) -> ArduinoDeviceInfo:
        """
        Get complete device information.
        
        Args:
            port_name: Serial port name
            serial_conn: Optional open serial connection for firmware queries
        
        Returns:
            ArduinoDeviceInfo with all available information
        """
        # Get hardware info
        port_info = self.get_port_info(port_name)
        
        # Get firmware info if connected
        firmware_info = {"version": "Not queried", "capabilities": {}}
        ping_time = 0.0
        
        if serial_conn and serial_conn.is_open:
            firmware_info = self.query_firmware(serial_conn)
            ping_time = self.measure_ping(serial_conn)
        
        return ArduinoDeviceInfo(
            port=port_name,
            model=port_info.get("model", "Unknown"),
            board_type=port_info.get("board_type", "unknown"),
            vendor_id=port_info.get("vendor_id", 0),
            product_id=port_info.get("product_id", 0),
            serial_number=port_info.get("serial_number", ""),
            manufacturer=port_info.get("manufacturer", ""),
            description=port_info.get("description", ""),
            firmware_version=firmware_info.get("version", "Unknown"),
            ping_time_ms=ping_time,
            is_genuine=port_info.get("is_genuine", False),
            capabilities=firmware_info.get("capabilities", {})
        )
    
    def detect_board_capabilities(self, board_type: str) -> Dict[str, Any]:
        """
        Get known capabilities for a board type.
        
        Args:
            board_type: Board identifier (e.g., 'mega2560', 'uno')
        
        Returns:
            Dict with board capabilities
        """
        capabilities = {
            "mega2560": {
                "digital_pins": 54,
                "analog_pins": 16,
                "pwm_pins": 15,
                "flash_kb": 256,
                "sram_kb": 8,
                "eeprom_kb": 4,
                "clock_mhz": 16,
                "usable_test_pins": list(range(2, 54)),  # Pins 0,1 are serial
                "analog_range": ["A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7",
                                "A8", "A9", "A10", "A11", "A12", "A13", "A14", "A15"]
            },
            "uno": {
                "digital_pins": 14,
                "analog_pins": 6,
                "pwm_pins": 6,
                "flash_kb": 32,
                "sram_kb": 2,
                "eeprom_kb": 1,
                "clock_mhz": 16,
                "usable_test_pins": list(range(2, 14)),
                "analog_range": ["A0", "A1", "A2", "A3", "A4", "A5"]
            }
        }
        
        return capabilities.get(board_type, {
            "digital_pins": 0,
            "analog_pins": 0,
            "note": "Unknown board - capabilities not defined"
        })
