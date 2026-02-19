# ic_tester_app/chips/migration.py
# Last edited: 2026-01-20
# Purpose: Smart pin migration helper for switching between chips
# Dependencies: None

"""
Pin Migration Helper.

When switching from one chip to another, this module analyzes the pinouts
and suggests the minimal wire changes needed. It identifies:
- Pins that changed function (I/O became power, power became I/O, etc.)
- Pins that can stay connected as-is
- Suggested wire moves to minimize rewiring
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

from ..logger import get_logger

logger = get_logger("chips.migration")


class PinFunction(Enum):
    """Types of pin functions"""
    VCC = "VCC"
    GND = "GND"
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    NO_CONNECT = "NC"
    UNKNOWN = "UNKNOWN"


@dataclass
class PinChange:
    """Represents a pin that needs attention when switching chips"""
    chip_pin: int
    old_function: PinFunction
    new_function: PinFunction
    old_name: str
    new_name: str
    arduino_pin: Optional[int]  # Current Arduino pin if mapped
    action: str  # Human-readable action to take


@dataclass
class MigrationPlan:
    """Complete migration plan from one chip to another"""
    from_chip: str
    to_chip: str
    same_pin_count: bool
    keep_pins: List[int]  # Pins that can stay connected
    move_pins: List[PinChange]  # Pins that need to move
    suggestions: List[str]  # Step-by-step instructions


class PinMigrationHelper:
    """
    Analyzes chip pinouts and generates migration suggestions.
    """
    
    def __init__(self, chip_db):
        """
        Initialize migration helper.
        
        Args:
            chip_db: ChipDatabase instance for looking up chip definitions
        """
        self.chip_db = chip_db
    
    def get_pin_function(self, chip_data: Dict, pin_num: int) -> Tuple[PinFunction, str]:
        """
        Determine the function of a specific pin on a chip.
        
        Returns:
            Tuple of (PinFunction, name/description)
        """
        pinout = chip_data.get('pinout', {})
        
        # Check if it's VCC
        if pinout.get('vcc') == pin_num:
            return (PinFunction.VCC, "VCC")
        
        # Check if it's GND
        if pinout.get('gnd') == pin_num:
            return (PinFunction.GND, "GND")
        
        # Check if it's No Connect
        if pin_num in pinout.get('noConnect', []):
            return (PinFunction.NO_CONNECT, "NC")
        
        # Check inputs
        for inp in pinout.get('inputs', []):
            if inp['pin'] == pin_num:
                return (PinFunction.INPUT, inp['name'])
        
        # Check outputs
        for out in pinout.get('outputs', []):
            if out['pin'] == pin_num:
                return (PinFunction.OUTPUT, out['name'])
        
        return (PinFunction.UNKNOWN, "Unknown")
    
    def get_pin_count(self, chip_data: Dict) -> int:
        """Get the total pin count from package description"""
        package = chip_data.get('package', '')
        if '14-pin' in package:
            return 14
        elif '16-pin' in package:
            return 16
        elif '20-pin' in package:
            return 20
        elif '24-pin' in package:
            return 24
        # Default fallback - count all defined pins
        pinout = chip_data.get('pinout', {})
        pins = set()
        if pinout.get('vcc'):
            pins.add(pinout['vcc'])
        if pinout.get('gnd'):
            pins.add(pinout['gnd'])
        for inp in pinout.get('inputs', []):
            pins.add(inp['pin'])
        for out in pinout.get('outputs', []):
            pins.add(out['pin'])
        for nc in pinout.get('noConnect', []):
            pins.add(nc)
        return max(pins) if pins else 0
    
    def analyze_migration(self, from_chip_id: str, to_chip_id: str, 
                         current_mapping: Dict[str, int]) -> MigrationPlan:
        """
        Analyze what changes are needed to switch from one chip to another.
        
        Args:
            from_chip_id: Current chip ID (e.g., '7414')
            to_chip_id: Target chip ID (e.g., '7490')
            current_mapping: Current Arduino pin mapping {chip_pin_str: arduino_pin}
        
        Returns:
            MigrationPlan with detailed instructions
        """
        from_chip = self.chip_db.get_chip(from_chip_id)
        to_chip = self.chip_db.get_chip(to_chip_id)
        
        if not from_chip or not to_chip:
            return MigrationPlan(
                from_chip=from_chip_id,
                to_chip=to_chip_id,
                same_pin_count=False,
                keep_pins=[],
                move_pins=[],
                suggestions=["Error: Could not find one or both chip definitions"]
            )
        
        from_pin_count = self.get_pin_count(from_chip)
        to_pin_count = self.get_pin_count(to_chip)
        same_pin_count = from_pin_count == to_pin_count
        
        keep_pins = []
        move_pins = []
        suggestions = []
        
        # Analyze each pin
        for pin_num in range(1, max(from_pin_count, to_pin_count) + 1):
            old_func, old_name = self.get_pin_function(from_chip, pin_num)
            new_func, new_name = self.get_pin_function(to_chip, pin_num)
            
            arduino_pin = current_mapping.get(str(pin_num))
            
            if old_func == new_func:
                # Same function - can potentially keep the wire
                if old_func in (PinFunction.INPUT, PinFunction.OUTPUT):
                    keep_pins.append(pin_num)
            else:
                # Function changed - need to rewire
                action = self._get_action(old_func, new_func, pin_num, arduino_pin)
                change = PinChange(
                    chip_pin=pin_num,
                    old_function=old_func,
                    new_function=new_func,
                    old_name=old_name,
                    new_name=new_name,
                    arduino_pin=arduino_pin,
                    action=action
                )
                move_pins.append(change)
        
        # Generate step-by-step suggestions
        suggestions = self._generate_suggestions(from_chip, to_chip, move_pins, current_mapping)
        
        return MigrationPlan(
            from_chip=from_chip_id,
            to_chip=to_chip_id,
            same_pin_count=same_pin_count,
            keep_pins=keep_pins,
            move_pins=move_pins,
            suggestions=suggestions
        )
    
    def _get_action(self, old_func: PinFunction, new_func: PinFunction, 
                   pin_num: int, arduino_pin: Optional[int]) -> str:
        """Generate action description for a pin change"""
        if new_func == PinFunction.VCC:
            if arduino_pin:
                return f"Disconnect Arduino {arduino_pin}, connect to 5V power"
            return "Connect to 5V power"
        
        elif new_func == PinFunction.GND:
            if arduino_pin:
                return f"Disconnect Arduino {arduino_pin}, connect to GND"
            return "Connect to GND"
        
        elif new_func == PinFunction.NO_CONNECT:
            if arduino_pin:
                return f"Disconnect Arduino {arduino_pin} (pin not used)"
            return "Leave disconnected"
        
        elif new_func in (PinFunction.INPUT, PinFunction.OUTPUT):
            if old_func == PinFunction.VCC:
                return "Disconnect from 5V, assign Arduino pin"
            elif old_func == PinFunction.GND:
                return "Disconnect from GND, assign Arduino pin"
            elif old_func == PinFunction.NO_CONNECT:
                return "Was NC, now needs Arduino pin"
            else:
                return "Reassign Arduino pin"
        
        return "Check manually"
    
    def _generate_suggestions(self, from_chip: Dict, to_chip: Dict,
                             move_pins: List[PinChange], 
                             current_mapping: Dict[str, int]) -> List[str]:
        """Generate human-readable step-by-step instructions"""
        suggestions = []
        
        from_id = from_chip.get('chipId', 'old chip')
        to_id = to_chip.get('chipId', 'new chip')
        
        suggestions.append(f"📋 Migration from {from_id} to {to_id}:")
        suggestions.append("")
        
        # Group by action type
        to_power = [p for p in move_pins if p.new_function == PinFunction.VCC]
        to_gnd = [p for p in move_pins if p.new_function == PinFunction.GND]
        from_power = [p for p in move_pins if p.old_function in (PinFunction.VCC, PinFunction.GND) 
                     and p.new_function in (PinFunction.INPUT, PinFunction.OUTPUT)]
        to_nc = [p for p in move_pins if p.new_function == PinFunction.NO_CONNECT]
        
        step = 1
        
        # Step 1: Handle pins becoming power
        if to_power:
            for p in to_power:
                if p.arduino_pin:
                    suggestions.append(f"  {step}. Pin {p.chip_pin}: Disconnect Arduino {p.arduino_pin} → Connect to 5V")
                    suggestions.append(f"     (Was {p.old_name}, now VCC)")
                    
                    # Suggest where to reassign that Arduino pin
                    for fp in from_power:
                        if not fp.arduino_pin:
                            suggestions.append(f"     💡 Reassign Arduino {p.arduino_pin} to pin {fp.chip_pin} ({fp.new_name})")
                            fp.arduino_pin = p.arduino_pin  # Mark as suggested
                            break
                    step += 1
        
        if to_gnd:
            for p in to_gnd:
                if p.arduino_pin:
                    suggestions.append(f"  {step}. Pin {p.chip_pin}: Disconnect Arduino {p.arduino_pin} → Connect to GND")
                    suggestions.append(f"     (Was {p.old_name}, now GND)")
                    
                    # Suggest where to reassign
                    for fp in from_power:
                        if not fp.arduino_pin:
                            suggestions.append(f"     💡 Reassign Arduino {p.arduino_pin} to pin {fp.chip_pin} ({fp.new_name})")
                            fp.arduino_pin = p.arduino_pin
                            break
                    step += 1
        
        # Step 2: Handle power pins becoming I/O
        if from_power:
            suggestions.append("")
            suggestions.append("  🔌 Former power pins now need Arduino connections:")
            for p in from_power:
                if p.old_function == PinFunction.VCC:
                    suggestions.append(f"  {step}. Pin {p.chip_pin}: Disconnect from 5V → Assign Arduino pin")
                else:
                    suggestions.append(f"  {step}. Pin {p.chip_pin}: Disconnect from GND → Assign Arduino pin")
                suggestions.append(f"     (Now {p.new_name} - {p.new_function.value})")
                step += 1
        
        # Step 3: Handle NC pins
        if to_nc:
            suggestions.append("")
            suggestions.append("  ⚪ Pins to disconnect (not used on new chip):")
            for p in to_nc:
                if p.arduino_pin:
                    suggestions.append(f"  {step}. Pin {p.chip_pin}: Disconnect Arduino {p.arduino_pin}")
                    suggestions.append(f"     (Was {p.old_name}, now not connected)")
                    step += 1
        
        if not move_pins:
            suggestions.append("  ✅ No pin changes needed - same pinout!")
        
        return suggestions
    
    def get_new_mapping_suggestion(self, from_chip_id: str, to_chip_id: str,
                                   current_mapping: Dict[str, int]) -> Dict[str, int]:
        """
        Generate a suggested mapping for the new chip based on the old mapping.
        Tries to reuse Arduino pins where possible.
        
        Returns:
            Suggested mapping for the new chip
        """
        plan = self.analyze_migration(from_chip_id, to_chip_id, current_mapping)
        to_chip = self.chip_db.get_chip(to_chip_id)
        
        if not to_chip:
            return {}
        
        new_mapping = {}
        used_arduino_pins = set()
        freed_arduino_pins = []
        
        # Collect freed Arduino pins (from pins that became power/NC)
        for change in plan.move_pins:
            if change.new_function in (PinFunction.VCC, PinFunction.GND, PinFunction.NO_CONNECT):
                if change.arduino_pin:
                    freed_arduino_pins.append(change.arduino_pin)
        
        # First pass: keep pins that haven't changed function
        for pin in plan.keep_pins:
            arduino = current_mapping.get(str(pin))
            if arduino:
                new_mapping[str(pin)] = arduino
                used_arduino_pins.add(arduino)
        
        # Second pass: assign freed pins to new I/O pins
        pinout = to_chip.get('pinout', {})
        new_io_pins = []
        
        for inp in pinout.get('inputs', []):
            if str(inp['pin']) not in new_mapping:
                new_io_pins.append(inp['pin'])
        for out in pinout.get('outputs', []):
            if str(out['pin']) not in new_mapping:
                new_io_pins.append(out['pin'])
        
        freed_iter = iter(freed_arduino_pins)
        for chip_pin in new_io_pins:
            try:
                arduino = next(freed_iter)
                new_mapping[str(chip_pin)] = arduino
                used_arduino_pins.add(arduino)
            except StopIteration:
                break  # No more freed pins
        
        return new_mapping
