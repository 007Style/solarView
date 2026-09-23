#!/usr/bin/env python3
"""Verify SolarEdgeClient module against the live inverter."""

from solaredge_modbus import SolarEdgeClient

client = SolarEdgeClient(host="192.168.1.7", port=1502)
if not client.connect():
    print("FAIL: could not connect")
    exit(1)

print("Connected to SolarEdge at 192.168.1.7:1502")

for unit_id in [1, 2, 3]:
    print(f"\n=== Inverter Unit {unit_id} ===")

    data = client.read_inverter(unit_id=unit_id)
    if data:
        print(f"  Inverter data: {len(data)} fields")
        for key in ["line_voltage", "voltage_an", "ac_power", "frequency", "energy_wh", "temperature"]:
            val = data.get(key)
            if val is not None:
                unit = ""
                if "voltage" in key: unit = "V"
                elif "power" in key: unit = "W"
                elif "frequency" in key: unit = "Hz"
                elif "energy" in key: unit = "Wh"
                elif "temperature" in key: unit = "°C"
                print(f"    {key}: {val:.1f} {unit}")
    else:
        print("  No inverter data")

# Battery is on the SunSpec chain of inverter unit 1 only
print("\n=== Battery (unit_id=1 SunSpec chain) ===")
bat = client.read_battery(unit_id=1)
if bat:
    print(f"  Battery data: {len(bat)} fields")
    for key in ["battery_power", "battery_voltage", "battery_soe", "battery_current",
                "battery_state_str", "cell_v_max", "cell_v_min", "cell_v_avg"]:
        val = bat.get(key)
        if val is not None:
            print(f"    {key}: {val}")
else:
    print("  No battery data")

client.close()
print("\nVerification complete.")
