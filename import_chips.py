"""
Chip-database conversion utility.

This script converts a legacy text database format into the JSON structure used
by the tester application. The conversion pipeline is:
1. parse raw chip entries from the source text file,
2. decode pattern characters into input/output expectations,
3. infer a simple pinout,
4. emit the normalized JSON definition used by the app.
"""
import json
import os
import re

def parse_database(filename):
    """Parse the database.txt file and return list of chip definitions"""
    chips = []
    
    with open(filename, 'r') as f:
        content = f.read()
    
    # Each chip entry starts with `$`, so splitting on that marker turns the
    # flat text export into per-chip chunks we can parse independently.
    entries = re.split(r'\n\$', content)
    
    for entry in entries:
        if not entry.strip():
            continue
        
        lines = entry.strip().split('\n')
        if len(lines) < 3:
            continue
        
        # First line is chip ID (might start with $ if first entry)
        chip_id = lines[0].lstrip('$').strip()
        
        # Second line is description
        description = lines[1].strip()
        
        # Third line is pin count
        try:
            pin_count = int(lines[2].strip())
        except:
            continue
        
        # Rest are test patterns
        test_patterns = [l.strip() for l in lines[3:] if l.strip()]
        
        if chip_id and test_patterns:
            chips.append({
                'id': chip_id,
                'description': description,
                'pins': pin_count,
                'patterns': test_patterns
            })
    
    return chips

def convert_pattern_to_test(pattern, pin_count):
    """
    Convert a test pattern to input/output definitions
    Pattern codes:
    - 0/1: Input LOW/HIGH
    - L/H: Expected output LOW/HIGH
    - G: Ground (pin 7 for 14-pin, pin 8 for 16-pin)
    - V: VCC (pin 14 for 14-pin, pin 16 for 16-pin)
    - C: Clock pulse
    - X: Don't care / not connected
    - Z: High impedance
    """
    inputs = {}
    expected_outputs = {}
    
    # `G` marks the ground divider between the low-numbered and high-numbered
    # halves of the package in the source pattern syntax.
    if 'G' in pattern:
        parts = pattern.split('G')
        left = parts[0]
        right = parts[1] if len(parts) > 1 else ''
        
        # For 14-pin: pins 1-6 on left, 8-13 on right (7=GND, 14=VCC)
        # For 16-pin: pins 1-7 on left, 9-15 on right (8=GND, 16=VCC)
        if pin_count == 14:
            gnd_pin = 7
            vcc_pin = 14
            left_pins = list(range(1, 7))  # 1-6
            right_pins = list(range(8, 14))  # 8-13
        else:  # 16-pin
            gnd_pin = 8
            vcc_pin = 16
            left_pins = list(range(1, 8))  # 1-7
            right_pins = list(range(9, 16))  # 9-15
        
        # Process left side (low pin numbers)
        for i, char in enumerate(left):
            if i < len(left_pins):
                pin = left_pins[i]
                if char == '0':
                    inputs[pin] = 'LOW'
                elif char == '1':
                    inputs[pin] = 'HIGH'
                elif char == 'L':
                    expected_outputs[pin] = 'LOW'
                elif char == 'H':
                    expected_outputs[pin] = 'HIGH'
                elif char == 'C':
                    inputs[pin] = 'CLOCK'
        
        # The source format lists the package's right side in reverse order, so
        # flip it before mapping characters back onto physical pin numbers.
        right_reversed = right[::-1]  # Patterns list right side in reverse
        for i, char in enumerate(right_reversed):
            if i < len(right_pins):
                pin = right_pins[len(right_pins) - 1 - i]
                if char == '0':
                    inputs[pin] = 'LOW'
                elif char == '1':
                    inputs[pin] = 'HIGH'
                elif char == 'L':
                    expected_outputs[pin] = 'LOW'
                elif char == 'H':
                    expected_outputs[pin] = 'HIGH'
                elif char == 'C':
                    inputs[pin] = 'CLOCK'
    
    return inputs, expected_outputs

def create_json_chip(chip_data):
    """Create a JSON chip definition from parsed data"""
    chip_id = chip_data['id']
    pin_count = chip_data['pins']
    
    # Determine GND and VCC pins
    if pin_count == 14:
        gnd_pin = 7
        vcc_pin = 14
    else:
        gnd_pin = 8
        vcc_pin = 16
    
    # Turn the textual truth-table patterns into the `tests` structure consumed
    # by the runtime tester.
    tests = []
    for i, pattern in enumerate(chip_data['patterns'][:8]):  # Limit to 8 tests
        inputs, outputs = convert_pattern_to_test(pattern, pin_count)
        if inputs or outputs:
            tests.append({
                'testId': i + 1,
                'description': f"Test pattern {i + 1}",
                'inputs': {f"PIN{p}": v for p, v in inputs.items() if v != 'CLOCK'},
                'expectedOutputs': {f"PIN{p}": v for p, v in outputs.items()}
            })
    
    # Build pinout (simplified - just uses pin numbers)
    input_pins = []
    output_pins = []
    
    # Infer which pins behave like inputs vs outputs by inspecting the first few
    # patterns. This is heuristic, but good enough for bootstrapping JSON files
    # from the legacy database export.
    for pattern in chip_data['patterns'][:3]:
        if 'G' in pattern:
            parts = pattern.split('G')
            full_pattern = parts[0] + parts[1] if len(parts) > 1 else parts[0]
            for i, char in enumerate(full_pattern):
                pin = i + 1
                if pin == gnd_pin or pin == vcc_pin:
                    continue
                if char in '01C':
                    if pin not in [p['pin'] for p in input_pins]:
                        input_pins.append({'pin': pin, 'name': f'PIN{pin}', 'description': f'Pin {pin}'})
                elif char in 'LH':
                    if pin not in [p['pin'] for p in output_pins]:
                        output_pins.append({'pin': pin, 'name': f'PIN{pin}', 'description': f'Pin {pin}'})
    
    # Sort pins
    input_pins.sort(key=lambda x: x['pin'])
    output_pins.sort(key=lambda x: x['pin'])
    
    # Build Arduino mapping (sequential from pin 2)
    io_mapping = {}
    arduino_pin = 2
    for p in input_pins + output_pins:
        if arduino_pin <= 13:
            io_mapping[str(p['pin'])] = arduino_pin
            arduino_pin += 1
    
    json_chip = {
        'chipId': chip_id,
        'name': chip_data['description'],
        'manufacturer': 'Generic',
        'package': f'{pin_count}-pin DIP',
        'description': chip_data['description'],
        'pinout': {
            'vcc': vcc_pin,
            'gnd': gnd_pin,
            'inputs': input_pins,
            'outputs': output_pins,
            'noConnect': []
        },
        'arduinoMapping': {
            'comment': 'Auto-generated mapping',
            'power': {
                str(vcc_pin): '5V',
                str(gnd_pin): 'GND'
            },
            'io': io_mapping
        },
        'testSequence': {
            'description': f'Test sequence for {chip_id}',
            'setup': [{
                'step': 1,
                'action': 'Initialize all inputs LOW',
                'pins': {f'PIN{p["pin"]}': 'LOW' for p in input_pins}
            }],
            'tests': tests
        },
        'notes': [f'Imported from Smart IC Tester database']
    }
    
    return json_chip

def main():
    """Main entry point"""
    database_file = 'database_import.txt'
    output_dir = 'chips'
    
    if not os.path.exists(database_file):
        print(f"Error: {database_file} not found")
        return
    
    print(f"Parsing {database_file}...")
    chips = parse_database(database_file)
    print(f"Found {len(chips)} chips")
    
    # Show available chips
    print("\nAvailable chips:")
    for i, chip in enumerate(chips):
        print(f"  {chip['id']}: {chip['description']} ({chip['pins']} pins, {len(chip['patterns'])} tests)")
    
    # Convert specific chips (can be expanded)
    chips_to_convert = ['7400', '7402', '7404', '7408', '7410', '7414', '7432', '7486']
    
    print(f"\nConverting selected chips: {chips_to_convert}")
    
    for chip_data in chips:
        if chip_data['id'] in chips_to_convert:
            json_chip = create_json_chip(chip_data)
            output_file = os.path.join(output_dir, f"{chip_data['id']}.json")
            
            with open(output_file, 'w') as f:
                json.dump(json_chip, f, indent=2)
            
            print(f"  Created {output_file}")
    
    print("\nDone!")

if __name__ == '__main__':
    main()
