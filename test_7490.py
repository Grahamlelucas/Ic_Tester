#!/usr/bin/env python3
from ic_tester_app.arduino.connection import ArduinoConnection
import time

a = ArduinoConnection()
p = a.find_arduino_ports()
print(f"Ports: {p}")
if not p:
    print("No Arduino")
    exit(1)
a.connect(p[0])
c = a.commands
conn = a

def read_digital():
    r = c.batch_read_pins([10,8,7,9])
    print(f"  Digital: QA={r.get(10)} QB={r.get(8)} QC={r.get(7)} QD={r.get(9)}")

def read_raw():
    """Send raw READ_PIN commands one at a time and print raw responses"""
    for name, pin in [("QA",10),("QB",8),("QC",7),("QD",9)]:
        resp = conn.send_and_receive(f"READ_PIN,{pin}", timeout=1.0)
        print(f"  Raw {name}(pin {pin}): {resp}")

print("=== Step 1: Reset to 0 ===")
c.batch_set_pins({3:"HIGH",4:"HIGH",5:"LOW",6:"LOW",11:"LOW",2:"LOW"})
time.sleep(0.1)
read_digital()
read_raw()

print("\n=== Step 2: Reset to 9 ===")
c.batch_set_pins({3:"LOW",4:"LOW",5:"HIGH",6:"HIGH"})
time.sleep(0.1)
read_digital()
read_raw()

print("\n=== Step 3: Release R9 ===")
c.batch_set_pins({5:"LOW",6:"LOW"})
time.sleep(0.1)
read_digital()
read_raw()

print("\n=== Step 4: Write QA pin HIGH directly (test LED) ===")
c.write_pin(10, "HIGH")
time.sleep(0.1)
resp = conn.send_and_receive("READ_PIN,10", timeout=1.0)
print(f"  After writing HIGH to pin 10: {resp}")

print("\n=== Step 5: Release pin 10 back to input ===")
resp = conn.send_and_receive("READ_PIN,10", timeout=1.0)
print(f"  Read pin 10: {resp}")

c.batch_set_pins({3:"LOW",4:"LOW",5:"LOW",6:"LOW",11:"LOW",2:"LOW"})
a.disconnect()
print("\nDone")
