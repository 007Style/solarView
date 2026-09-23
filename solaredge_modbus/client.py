"""SolarEdge Modbus client for solarView.

Reads real-time inverter and battery data from SolarEdge devices via
Modbus TCP (port 1502, FC3).

Battery discovery:
  The LG RESU battery does NOT have its own Modbus unit ID.  It is exposed
  via the SunSpec model chain on unit_id=1 (the primary inverter):
    DID 701 @ 40470  — Battery Base Model (nameplate, mostly 0xffff here)
    DID 705 @ 40763  — Battery Module Model (SoC, state, cell voltages)
    DID 703 @ 40677  — Battery String Status (voltage, current)
  All battery reads use unit_id=1 at these fixed addresses.

Usage:
    client = SolarEdgeClient(host="192.168.1.7", port=1502)
    data = client.read_inverter(unit_id=1)
    battery = client.read_battery()   # always unit_id=1
"""

from __future__ import annotations

import struct
from typing import Optional

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

from .registers import Register, InverterRegisters, BatteryRegisters

# SolarEdge docs use 1-based 40xxx addresses; pymodbus uses 0-based.
# 40001 → 0, 40069 → 68, etc.
_MB_OFFSET = 40001


class SolarEdgeClient:
    """Modbus TCP client for SolarEdge inverters and batteries."""

    def __init__(self, host: str = "192.168.1.7", port: int = 1502, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._client: Optional[ModbusTcpClient] = None

    def connect(self) -> bool:
        """Open the TCP connection to the SolarEdge modbus gateway."""
        if self._client and self._client.connected:
            return True
        self._client = ModbusTcpClient(
            host=self.host, port=self.port, timeout=self.timeout, retries=0
        )
        return self._client.connect()

    def close(self) -> None:
        """Close the TCP connection."""
        if self._client:
            self._client.close()
            self._client = None

    # ── Internal helpers ──────────────────────────────────────────────

    def _read_block(self, unit_id: int, start_reg_1based: int, count: int) -> Optional[list[int]]:
        """Read a block of holding registers (FC3).

        Args:
            unit_id: Modbus unit ID.
            start_reg_1based: 1-based register address (e.g. 40069).
            count: Number of registers to read.

        Returns:
            List of raw unsigned 16-bit values (NOT sign-extended), or None on error.
        """
        if not self._client or not self._client.connected:
            if not self.connect():
                return None

        addr_0based = start_reg_1based - _MB_OFFSET

        try:
            result = self._client.read_holding_registers(
                address=addr_0based, count=count, device_id=unit_id
            )
            if hasattr(result, "registers") and result.registers is not None:
                # Return raw unsigned values; sign interpretation happens in _decode_value
                return list(result.registers)
            return None
        except (ModbusException, Exception) as e:
            print(f"[SolarEdgeClient] Read error (unit={unit_id}, "
                  f"addr={start_reg_1based}): {e}")
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None
            return None

    def _to_signed16(self, val: int) -> int:
        """Convert a raw unsigned 16-bit register value to a signed int."""
        return val - 65536 if val >= 32768 else val

    def _is_available(self, raw_unsigned: int) -> bool:
        """Return False if the register holds the SunSpec 'not available' sentinel (0x8000)."""
        return raw_unsigned != 0x8000

    def _decode_value(self, reg_dict: dict, reg: Register) -> Optional[float]:
        """Decode a register value applying scale factor, uint32, or float32 logic.

        reg_dict maps 1-based address → raw *unsigned* 16-bit value (as returned
        by pymodbus registers[]).

        Scale factor interpretation:
          - SF value is a signed 16-bit integer (e.g. -1 means ×0.1).
          - 0x8000 as the SF means 'not available' → return None.
        """
        if reg.is_float32:
            # SunSpec float32: low word at reg.address, high word at reg.address+1
            lo = reg_dict.get(reg.address, 0) & 0xFFFF
            hi = reg_dict.get(reg.address + 1, 0) & 0xFFFF
            raw_uint = (lo << 16) | hi
            val = struct.unpack(">f", struct.pack(">I", raw_uint))[0]
            return val

        if reg.is_uint32:
            # uint32: low word at reg.address, high word at reg.address+1
            lo_raw = reg_dict.get(reg.address, 0) & 0xFFFF
            hi_raw = reg_dict.get(reg.address + 1, 0) & 0xFFFF
            raw = (hi_raw << 16) | lo_raw
            # Apply scale factor
            if reg.sf_address is not None:
                sf_raw = reg_dict.get(reg.sf_address, 0)
                if sf_raw == 0x8000:
                    return None
                sf = self._to_signed16(sf_raw)
                try:
                    return float(raw) * (10 ** sf)
                except (ValueError, OverflowError):
                    return None
            return float(raw)

        # Single 16-bit value
        raw_unsigned = reg_dict.get(reg.address)
        if raw_unsigned is None:
            return None
        if not self._is_available(raw_unsigned):
            return None

        if reg.signed:
            raw = self._to_signed16(raw_unsigned)
        else:
            raw = raw_unsigned

        if reg.sf_address is not None:
            sf_raw = reg_dict.get(reg.sf_address, 0)
            if sf_raw == 0x8000:
                return None
            sf = self._to_signed16(sf_raw)
            try:
                return float(raw) * (10 ** sf)
            except (ValueError, OverflowError):
                return None

        return float(raw)

    def _decode_status(self, reg_dict: dict, reg: Register) -> Optional[int]:
        """Decode a raw status register (no SF, unsigned)."""
        raw = reg_dict.get(reg.address)
        if raw is None or raw == 0x8000:
            return None
        return int(raw)

    # ── Public API ────────────────────────────────────────────────────

    def read_inverter(self, unit_id: int = 1) -> Optional[dict]:
        """Read all available data from a SolarEdge inverter unit.

        Reads registers 40069–40120 (52 registers) covering the full
        SunSpec DID=1 extended model.

        Returns:
            Dict of named values, or None if the read failed.
        """
        # 40069 + 52 = 40121, covering all fields including status at 40113
        raw = self._read_block(unit_id, 40069, 52)
        if raw is None:
            return None

        # Build address→raw_unsigned map
        reg: dict[int, int] = {40069 + i: raw[i] for i in range(len(raw))}

        # Verify SunSpec DID
        did = reg.get(40069, 0)
        if did == 0 or did == 0x8000:
            return None

        data: dict = {
            "did": did,
            "length": reg.get(40070),
        }

        # Decoded fields — status registers handled separately
        field_map = [
            ("line_voltage",   InverterRegisters.LINE_VOLTAGE),
            ("voltage_an",     InverterRegisters.VOLTAGE_AN),
            ("voltage_bn",     InverterRegisters.VOLTAGE_BN),
            ("current",        InverterRegisters.CURRENT_TOTAL),
            ("current_a",      InverterRegisters.CURRENT_A),
            ("ac_power",       InverterRegisters.AC_POWER),
            ("ac_va",          InverterRegisters.AC_VA),
            ("ac_var",         InverterRegisters.AC_VAR),
            ("power_factor",   InverterRegisters.AC_PF),
            ("frequency",      InverterRegisters.AC_FREQUENCY),
            ("energy_wh",      InverterRegisters.AC_ENERGY_WH),
            ("dc_power",       InverterRegisters.DC_POWER),
            ("temperature",    InverterRegisters.HEAT_SINK_TEMP),
        ]

        for name, reg_def in field_map:
            val = self._decode_value(reg, reg_def)
            # Round to 2 dp to eliminate float64 noise (e.g. 39.480000000000004)
            data[name] = round(val, 2) if val is not None else None

        # Status registers are raw unsigned ints, not scaled floats
        data["inverter_status"] = self._decode_status(reg, InverterRegisters.INVERTER_STATUS)
        data["grid_status"]     = self._decode_status(reg, InverterRegisters.GRID_STATUS)

        return data

    def read_battery(self, unit_id: int = 1) -> Optional[dict]:
        """Read battery data from the SunSpec model chain on the given inverter unit.

        Each SolarEdge inverter exposes its attached battery through its own
        SunSpec chain (always at the same fixed addresses regardless of unit_id).
        Up to 6 batteries can be read by calling this method with unit_ids 1–3
        (one call per inverter, each may have one battery).

        Battery sign convention (confirmed from live hardware):
          battery_power < 0  →  discharging (supplying load)
          battery_power > 0  →  charging    (absorbing solar)
          battery_power ≈ 0  →  idle

        ChaSt (DID 705 off=15) is the *charge control mode setpoint*, NOT the
        instantaneous direction.  ChaSt=4 means "maintain full charge" and
        stays at 4 even while the battery is actively discharging.
        Use battery_power sign for real-time direction.

        Returns:
            Dict or None on failure.
        """
        # ── DID 705 — Battery Module Model @ 40763 ───────────────────────────
        raw705 = self._read_block(unit_id, 40763, 59)
        if raw705 is None:
            return None

        r705 = {40763 + i: raw705[i] for i in range(len(raw705))}

        # Verify this is actually a battery model (DID should be 705)
        if r705.get(40763, 0) != 705:
            return None

        cellv_sf   = self._to_signed16(r705.get(40777, 0))  # off 14: CellV_SF = -3
        mod_status = r705.get(40767, 0)                      # off  4: ModSt
        n_cells    = r705.get(40768, 0)                      # off  5: NCell
        # ChaSt is the control mode setpoint — kept for informational purposes
        cha_status = r705.get(40778, 0)                      # off 15: ChaSt

        def _cellv(addr: int) -> float | None:
            raw = r705.get(addr, 0)
            if raw == 0x8000:
                return None
            return round(self._to_signed16(raw) * (10 ** cellv_sf), 4)

        cell_v_max = _cellv(40786)
        cell_v_min = _cellv(40789)
        cell_v_avg = _cellv(40792)

        # ── SE proprietary block @ 40182 — live SoC ──────────────────────────
        # 40225 = live SoC value, 40226 = SF (-2)  →  e.g. 9900 × 0.01 = 99.0%
        soc_pct: float | None = None
        raw_se = self._read_block(unit_id, 40182, 50)
        if raw_se is not None:
            r_se    = {40182 + i: raw_se[i] for i in range(len(raw_se))}
            soc_sf  = self._to_signed16(r_se.get(40226, 0xffff))
            soc_raw = r_se.get(40225, 0x8000)
            if soc_raw != 0x8000 and soc_sf != 0x8000:
                soc_pct = round(soc_raw * (10 ** soc_sf), 2)

        # ── DID 703 — Battery String Status @ 40677 ──────────────────────────
        # SunSpec DID 703 layout (offsets from 40677):
        #   off  3 = StringVoltage (V)   → 40680   SF @ off 18 (V_SF)  = 40695
        #   off  5 = StringStatus  (raw) → 40682
        #   off  6 = StringPower   (W)   → 40683   SF @ off 17 (W_SF)  = 40694
        #   off 10 = StringCurrent (A)   → 40687   SF @ off 16 (A_SF)  = 40693
        #   off 16 = A_SF                → 40693
        #   off 17 = W_SF                → 40694
        #   off 18 = V_SF                → 40695
        # Block must be 19 registers (off 0..18) to include all three SF registers.
        raw703 = self._read_block(unit_id, 40677, 19)
        string_voltage:  float | None = None
        battery_power:   float | None = None
        battery_current: float | None = None
        string_status:   int   | None = None

        if raw703 is not None:
            r703 = {40677 + i: raw703[i] for i in range(len(raw703))}
            a_sf = self._to_signed16(r703.get(40693, 0))   # off 16: A_SF (current)
            w_sf = self._to_signed16(r703.get(40694, 0))   # off 17: W_SF (power)
            v_sf = self._to_signed16(r703.get(40695, 0))   # off 18: V_SF (voltage)

            raw_v = r703.get(40680, 0)
            if raw_v != 0x8000 and v_sf != 0x8000:
                string_voltage = round(raw_v * (10 ** v_sf), 3)

            raw_p = r703.get(40683, 0)
            sp    = self._to_signed16(raw_p)
            if raw_p != 0x8000 and w_sf != 0x8000:
                battery_power = round(sp * (10 ** w_sf), 2)

            raw_c = r703.get(40687, 0)
            sc    = self._to_signed16(raw_c)
            if raw_c != 0x8000 and a_sf != 0x8000:
                battery_current = round(sc * (10 ** a_sf), 2)

            string_status = r703.get(40682, 0)

        # ── State label — read directly from hardware ChaSt register ─────────
        bat_state_str = {2: "Discharging", 3: "Charging", 4: "Full/Hold"}.get(
            cha_status, f"State {cha_status}"
        )

        return {
            "battery_soe":        soc_pct,
            "battery_state":      cha_status,
            "battery_state_str":  bat_state_str,
            "battery_ncells":     n_cells,
            "battery_mod_status": mod_status,
            "battery_power":      battery_power,
            "battery_current":    battery_current,
            "battery_voltage":    string_voltage,
            "cell_v_max":         cell_v_max,
            "cell_v_min":         cell_v_min,
            "cell_v_avg":         cell_v_avg,
            "string_status":      string_status,
        }
