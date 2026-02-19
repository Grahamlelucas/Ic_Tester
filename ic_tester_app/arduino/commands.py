# ic_tester_app/arduino/commands.py
# Last edited: 2026-01-19
# Purpose: Arduino command protocol and helper functions
# Dependencies: None (uses connection module)

"""
Arduino commands module.
Defines the command protocol and provides helper functions for IC testing operations.
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
    - LCD display control
    """
    
    def __init__(self, connection):
        """
        Args:
            connection: ArduinoConnection instance
        """
        self.conn = connection
    
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
        
        # Format: BSET,pin1:state1,pin2:state2,...
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
    # LCD Display Commands
    # =========================================================================
    
    def display_message(self, message: str) -> bool:
        """
        Send display command to LCD.
        
        Args:
            message: Message type (READY, TESTING, PASS, FAIL, etc.)
        
        Returns:
            True if successful
        """
        command = f"DISPLAY,{message}"
        response = self.conn.send_and_receive(command)
        return response == "OK"
    
    def display_ready(self) -> bool:
        """Display READY on LCD"""
        return self.display_message("READY")
    
    def display_testing(self) -> bool:
        """Display TESTING on LCD"""
        return self.display_message("TESTING")
    
    def display_pass(self) -> bool:
        """Display PASS on LCD"""
        return self.display_message("PASS")
    
    def display_fail(self) -> bool:
        """Display FAIL on LCD"""
        return self.display_message("FAIL")
    
    def clear_display(self) -> bool:
        """Clear LCD display"""
        return self.display_message("CLEAR")
    
    # =========================================================================
    # Utility Commands
    # =========================================================================
    
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
        # Set all to INPUT first, then LOW
        modes = {pin: "OUTPUT" for pin in pins}
        states = {pin: "LOW" for pin in pins}
        
        return self.batch_set_modes(modes) and self.batch_set_pins(states)
