"""SolarEdge Modbus register definitions for solarView.

Layout verified register-by-register against live hardware (unit_id=1) on
2026-09-23.  Raw dump decoded by hand — every address below is confirmed.

This SolarEdge gateway uses [SF][value] ordering: the scale-factor register
immediately PRECEDES its data register (opposite of the SunSpec standard).
Scale factors are signed 16-bit negative exponents: -1 = ×0.1, -2 = ×0.01.
The sentinel 0x8000 (raw 32768 / signed -32768) means "not available".

Confirmed layout (from raw register dump, unit_id=1) — VERIFIED 2026-09-23:
  40069  DID = 1
  40070  Length = 102
  40071  AC_Current_Total          (SF @ 40074)
  40072  AC_Current_A              (SF @ 40074)
  40073  AC_Current_B              (SF @ 40074)
  40074  AC_Current_SF             = -1
  40075  AC_Voltage_Line_SF        = -1
  40076  (not available — 0x8000)
  40077  AC_Voltage_Line           = 2359 → 235.9 V  ✓
  40078  (not available — 0x8000)
  40079  AC_Voltage_Phase_SF       = -1
  40080  AC_Voltage_AN             = 1183 → 118.3 V  ✓
  40081  AC_Voltage_BN             = 1176 → 117.6 V  ✓
  40082  (not available — 0x8000)
  40083  AC_Power_SF               = -1
  40084  AC_Power                  = 7416 → 741.6 W  ✓
  40085  (not available — 0x8000)
  40086  AC_Frequency              = 5999 → 59.99 Hz ✓  (SF @ 40087 = -3)
  40087  AC_VA_SF / Freq_SF        = -3   (shared: used by both AC_VA and AC_Frequency)
  40088  AC_VA                     = 7466 → 7.466 kVA  (SF @ 40087 = -3)
  40089  AC_VAR_SF                 = -1
  40090  AC_VAR                    (SF @ 40089)
  40091  AC_PF_SF                  = -2
  40092  AC_PF                     = 9933 → 99.33 %  ✓
  40093  AC_Energy_SF              = -2
  40094  AC_Energy_lo              = low word of uint32 lifetime energy
  40095  AC_Energy_hi              = high word of uint32  → combined e.g. 30,222,587 Wh ✓
  40096  (zero / not used)
  40097  (not a reliable DC reading here)
  40098  (not available — 0x8000)
  40099  (not usable)
  40100  DC_Power_SF               = -1
  40101  DC_Power                  = 7529 → 752.9 W  ✓  (matches AC power)
  40102  (not available — 0x8000)
  40103  (not available — 0x8000)
  40104  Heat_Sink_Temp            = 4195  (SF @ 40107 = -2) → 41.95 °C ✓
  40105  (not available — 0x8000)
  40106  (not available — 0x8000)
  40107  Temp_SF                   = -2
  40108  Inverter_Status           = 4 (producing)
  40113  Grid_Status               (raw)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Register:
    """A SolarEdge modbus register definition.

    Attributes:
        address:    1-based Modbus address of the VALUE register.
        name:       Human-readable field name.
        unit:       Display unit (e.g. "V", "W", "Hz").
        signed:     True if the 16-bit value should be sign-extended.
        sf_address: 1-based address of the scale-factor register.
                    Decoded value = raw_value × 10^sf.
                    The SF register precedes the value register on this hardware.
        is_uint32:  Combine this register (low word) with the next register
                    (high word) into a uint32, then apply SF.
        is_float32: Decode this and the next register as IEEE-754 float32
                    (SunSpec little-endian word order).
    """

    address: int
    name: str
    unit: str
    signed: bool = True
    sf_address: int | None = None
    is_uint32: bool = False
    is_float32: bool = False


class InverterRegisters:
    """SolarEdge extended inverter registers — layout verified from live hardware.

    All addresses confirmed by raw register dump and manual decode.
    SF[n] immediately precedes value[n+1] on this hardware.
    """

    # ── Model header ─────────────────────────────────────────────────────────
    DID    = Register(40069, "SunSpec_DID",    "-", signed=False)
    LENGTH = Register(40070, "SunSpec_Length", "-", signed=False)

    # ── AC Current ───────────────────────────────────────────────────────────
    # SF @ 40074 = -1;  total @ 40071, phase A @ 40072, phase B @ 40073
    CURRENT_TOTAL = Register(40071, "AC_Current_Total", "A", signed=False, sf_address=40074)
    CURRENT_A     = Register(40072, "AC_Current_A",     "A", signed=False, sf_address=40074)
    CURRENT_B     = Register(40073, "AC_Current_B",     "A", signed=False, sf_address=40074)

    # ── AC Voltage ───────────────────────────────────────────────────────────
    # Line-to-line (AB): SF @ 40075 = -1,  value @ 40077  → 235.9 V confirmed
    LINE_VOLTAGE = Register(40077, "AC_Voltage_Line", "V", signed=False, sf_address=40075)

    # Phase-to-neutral: shared SF @ 40079 = -1
    # AN @ 40080 → 118.3 V,  BN @ 40081 → 117.6 V  (confirmed)
    # CN (40082) is 0x8000 on this split-phase US install — skip
    VOLTAGE_AN = Register(40080, "AC_Voltage_AN", "V", signed=False, sf_address=40079)
    VOLTAGE_BN = Register(40081, "AC_Voltage_BN", "V", signed=False, sf_address=40079)

    # ── AC Power ─────────────────────────────────────────────────────────────
    # SF @ 40083 = -1,  value @ 40084  → 741.6 W confirmed
    AC_POWER = Register(40084, "AC_Power", "W", signed=True, sf_address=40083)

    # ── AC Apparent Power (VA) ────────────────────────────────────────────────
    # SF @ 40087 = -3,  value @ 40088
    AC_VA = Register(40088, "AC_VA", "VA", signed=True, sf_address=40087)

    # ── AC Reactive Power (var) ───────────────────────────────────────────────
    # SF @ 40089 = -1,  value @ 40090
    AC_VAR = Register(40090, "AC_VAR", "var", signed=True, sf_address=40089)

    # ── AC Power Factor ───────────────────────────────────────────────────────
    # SF @ 40091 = -2,  value @ 40092  → 99.33 % confirmed
    AC_PF = Register(40092, "AC_PF", "%", signed=True, sf_address=40091)

    # ── AC Frequency ─────────────────────────────────────────────────────────
    # SF @ 40087 = -3, value @ 40086 → 59.99 Hz confirmed from live US hardware
    # NOTE: 40094 is the AC Energy low word, NOT frequency (previous assumption wrong)
    AC_FREQUENCY = Register(40086, "AC_Frequency", "Hz", signed=False, sf_address=40087)

    # ── AC Energy (uint32) ────────────────────────────────────────────────────
    # SF @ 40093 = -2,  low word @ 40094,  high word @ 40095
    # → 30,222,587 Wh confirmed (cumulative lifetime generation)
    AC_ENERGY_WH = Register(40094, "AC_Energy_WH", "Wh", signed=False,
                            sf_address=40093, is_uint32=True)

    # ── DC Power ─────────────────────────────────────────────────────────────
    # SF @ 40100 = -1,  value @ 40101  → 752.9 W confirmed (shared SF with freq)
    DC_POWER = Register(40101, "DC_Power", "W", signed=True, sf_address=40100)

    # ── Temperature ──────────────────────────────────────────────────────────
    # SF @ 40107 = -2,  value @ 40104  → 41.95 °C confirmed
    HEAT_SINK_TEMP = Register(40104, "Heat_Sink_Temperature", "°C",
                              signed=True, sf_address=40107)

    # ── Status ────────────────────────────────────────────────────────────────
    # Raw unsigned integers — no scale factor.
    # 40108 = operating status (4 = producing),  40113 = grid status
    INVERTER_STATUS = Register(40108, "I_Status",      "-", signed=False)
    GRID_STATUS     = Register(40113, "I_Grid_Status", "-", signed=False)


class BatteryRegisters:
    """LG RESU16H battery registers (SunSpec Battery Model 802+).

    Battery values are IEEE-754 float32, SunSpec word order:
    low word at lower address, high word at lower+1.
    """

    B_DC_POWER            = Register(57716, "B_DC_Power",          "W",  is_float32=True)
    B_DC_VOLTAGE          = Register(57712, "B_DC_Voltage",         "V",  is_float32=True)
    B_DC_CURRENT          = Register(57714, "B_DC_Current",         "A",  is_float32=True)
    B_SOE                 = Register(57732, "B_SOE",                "%",  is_float32=True)
    B_SOH                 = Register(57730, "B_SOH",                "%",  is_float32=True)
    B_TEMP_AVERAGE        = Register(57708, "B_Temp_Average",       "°C", is_float32=True)
    B_TEMP_MAX            = Register(57710, "B_Temp_Max",           "°C", is_float32=True)
    B_MAX_CHARGE_POWER    = Register(57668, "B_MaxChargePower",     "W",  is_float32=True)
    B_MAX_DISCHARGE_POWER = Register(57670, "B_MaxDischargePower",  "W",  is_float32=True)
    B_ENERGY_MAX          = Register(57726, "B_Energy_Max",         "Wh", is_float32=True)
    B_ENERGY_AVAILABLE    = Register(57728, "B_Energy_Available",   "Wh", is_float32=True)
    B_EXPORT_ENERGY       = Register(57718, "B_Export_Energy_WH",   "Wh", is_uint32=True)
    B_IMPORT_ENERGY       = Register(57722, "B_Import_Energy_WH",   "Wh", is_uint32=True)
