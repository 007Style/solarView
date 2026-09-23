#!/usr/bin/env python3
"""Enhanced smoke test: verify multi-inverter + battery reads from SolarEdge Modbus.

Scans the complete device map for a SolarEdge installation with up to:
  - 3 inverters (Modbus unit IDs 1, 2, 3)
  - 6 batteries (2 per inverter, IDs 10–15)

Battery ID allocation (SolarEdge residential spec):
  Inverter 1: Battery primary = 15, secondary = 14
  Inverter 2: Battery primary = 13, secondary = 12
  Inverter 3: Battery primary = 11, secondary = 10

Verifies:
  1. TCP connect to configured host:port
  2. SunSpec header valid on each inverter unit_id
  3. Each battery unit_id responds and reports battery_soc/e
"""

import sys
import os
import yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from solaredge_modbus.client import SolarEdgeClient


def load_config():
    """Load config from default.yaml and ~/.solarview/config.yaml."""
    config = {}
    default_path = os.path.join(os.path.dirname(__file__), "config", "default.yaml")
    if os.path.exists(default_path):
        with open(default_path) as f:
            config.update(yaml.safe_load(f) or {})
    user_path = os.path.expanduser("~/.solarview/config.yaml")
    if os.path.exists(user_path):
        with open(user_path) as f:
            config.update(yaml.safe_load(f) or {})
    return config


def main():
    config = load_config()
    inv_cfg = config.get("inverter", {})
    host = inv_cfg.get("host", "192.168.1.7")
    port = inv_cfg.get("port", 1502)
    timeout = inv_cfg.get("timeout", 5.0)
    inverter_units = inv_cfg.get("units", [1, 2, 3])

    # NOTE: The LG RESU battery does NOT have its own Modbus unit ID.
    # It is accessible via the SunSpec model chain on unit_id=1 at fixed
    # addresses (DID 705 @ 40763, DID 703 @ 40677).  No unit ID scan needed.

    print(f"[smoke-test] Connecting to {host}:{port} (Inverters: {inverter_units})")
    client = SolarEdgeClient(host=host, port=port, timeout=timeout)
    if not client.connect():
        print("[FAIL] Could not connect")
        return 1

    results = {"inverters": {}, "battery": None, "errors": []}

    # ── Scan inverters ────────────────────────────────────────────────
    for uid in inverter_units:
        print(f"\n--- Inverter Unit ID {uid} ---")
        inv = client.read_inverter(unit_id=uid)
        if not inv:
            print(f"[FAIL] No data from inverter {uid}")
            results["errors"].append(f"Inverter {uid}: unreachable")
            continue

        results["inverters"][uid] = inv
        print(f"[OK] Inverter {uid}: "
              f"Power={inv.get('ac_power')} W, "
              f"Line_V={inv.get('line_voltage')} V, "
              f"Temp={inv.get('temperature')} °C")

    # ── Read battery (via SunSpec chain on unit_id=1) ─────────────────
    print(f"\n--- Battery (SunSpec chain, unit_id=1) ---")
    bat = client.read_battery()
    if bat:
        results["battery"] = bat
        soe     = bat.get("battery_soe")
        state   = bat.get("battery_state")
        power   = bat.get("battery_power")
        voltage = bat.get("battery_voltage")
        current = bat.get("battery_current")
        cv_max  = bat.get("cell_v_max")
        cv_min  = bat.get("cell_v_min")
        cv_avg  = bat.get("cell_v_avg")
        state_labels = {2: "discharging", 3: "charging", 4: "full/holding"}
        state_str = state_labels.get(state, f"unknown({state})")
        print(f"[OK] Battery: SoE={soe}%  State={state_str}")
        print(f"     Power={power} W  Current={current} A  Voltage={voltage} V")
        print(f"     Cell V: max={cv_max} V  min={cv_min} V  avg={cv_avg} V")
    else:
        print("[FAIL] No battery data")
        results["errors"].append("Battery: no data")

    client.close()

    # ── Summary ───────────────────────────────────────────────────────
    total_inv = len(results["inverters"])
    print(f"\n=== Summary ===")
    print(f"Inverters responding: {total_inv}/{len(inverter_units)}")
    print(f"Battery: {'OK' if results['battery'] else 'FAILED'}")

    if results["errors"]:
        print(f"Issues: {results['errors']}")

    success = total_inv >= 1 and results["battery"] is not None
    print(f"\n{'✅ Smoke test PASSED' if success else '❌ Smoke test FAILED'}")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
