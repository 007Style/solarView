# solarView — Plan Document

> *From the minds of IBM Bob & Daneyand*

## Project Vision

A lightweight, native-feeling desktop application that reads real-time Modbus TCP data from SolarEdge inverters (and the LG RESU16H battery) and displays it in live-updating charts. No historical persistence — just "what's happening right now," visualized on your desktop.

## Hardware Configuration

Based on the user's setup:

| Component | Address | Details |
|---|---|---|
| SolarEdge Inverter 1 | 192.168.1.7, Unit ID 1 | Main array inverter |
| SolarEdge Inverter 2 | 192.168.1.7, Unit ID 2 | Second string inverter |
| SolarEdge Inverter 3 | 192.168.1.7, Unit ID 3 | Third string inverter |
| LG RESU16H Battery | 192.168.1.7, Unit ID (TBD) | Typically Unit ID 16 or discovered via scan |

All devices share the same SolarEdge modbus gateway at `192.168.1.7:1502` (port 1502, **not** the standard port 80).

### Smoke Test Results (confirmed working)

| Metric | Value |
|---|---|
| TCP Port | **1502** (not 80) |
| Modbus Function | **FC3 (Holding Registers)**, not FC4 (Input Registers) |
| Primary Inverter Unit ID | **1** (confirmed — returns full SolarEdge data) |
| Battery Unit ID | 16 (needs verification) |
| Key Reading | AC Power: 1138 W, Voltage: 117.6 V, Temp: 42 °C |

## Technical Stack

| Layer | Technology | Rationale |
|---|---|---|
| Language | Python 3.10+ | Portable, you're already deep in it, rich ecosystem |
| Protocol | `pymodbus` | De facto standard Python Modbus library |
| UI Framework | `tkinter` + `matplotlib` | Bundled with Python, native look per-OS, zero-install |
| Packaging | `pyinstaller` | Single binary per platform (`app`/`.exe`/`.AppImage`) |
| Build Config | `pyproject.toml` | Modern Python packaging, single source of truth |

## SolarEdge Modbus Register Map (Reference)

These are the key registers we read from each inverter unit via **FC3 (holding registers)**. Addresses are SolarEdge's extended SunSpec model (offset starting at register 40069). Scale factors (SF) are in the **preceding** register:

**Key protocol facts (verified):**
- Port: **1502** (not 80)
- Function code: **3** (read holding registers, not 4)
- Base address: register 40069 (0-based modbus address 68)
- Read block: 52 consecutive registers starting at address 68
- Sign extension: 0x8000 = -32768 = "not available" (skip these)
- sf values are negative exponents: -1 = ×0.1, -2 = ×0.01


| Field | Modbus Address | SF Address | Unit | Description |
|---|---|---|---|---|
| AC_Voltage_Line | 40077 | 40076 (-1) | V | Line voltage (235.0 V confirmed) |
| AC_Voltage_AN | 40080 | 40078 (-1) | V | Phase A voltage (117.6 V confirmed) |
| AC_Voltage_BN | 40081 | 40078 (-1) | V | Phase B voltage (117.3 V confirmed) |
| AC_Power | 40084 | 40082 (-1) | W | Instantaneous AC power (1138 W confirmed) |
| AC_Frequency | 40101 | 40102 (-2) | Hz | Grid frequency |
| AC_Energy_WH | 40094 | 40093 (-2) | Wh | Cumulative energy (uint32) |
| I_Temp_Sink | 40104 | 40107 (-2) | °C | Inverter heatsink temperature (42 °C confirmed) |
| DC_Power | 40097 | 40096 | W | DC power from panels |
| DC_Voltage | 40099 | 40098 (-5?) | V | DC voltage from panels |

**Important:** Scale factors are at the **preceding** register address, not at the standard SunSpec offset. The address range is the SolarEdge extended model (Model DID=1, starting at register 40069). Read via **FC3 (holding registers)**, not FC4.

### Battery Registers (LG RESU16H, Unit ID 16)

| Field | Modbus Address | Unit | Description |
|---|---|---|---|
| B_DC_Power | 57716 | W | Battery charge/discharge power (+charge, -discharge) |
| B_DC_Voltage | 57712 | V | Battery DC voltage |
| B_DC_Current | 57714 | A | Battery DC current |
| B_SOE | 57732 | % | State of Energy |
| B_SOH | 57730 | % | State of Health |
| B_Export_Energy_WH | 57718 | Wh | Energy exported to grid (uint64) |
| B_Import_Energy_WH | 57722 | Wh | Energy imported from grid (uint64) |

**Note:** Battery registers use little-endian word ordering; some are uint64 (two consecutive 16-bit registers).

## Milestones

### Milestone 1 — Foundation & Single Inverter Read
- **Scope:** Project scaffold, modbus read for one inverter, basic tkinter window with power chart
- **Files created:**
  - `pyproject.toml`
  - `solaredge_modbus/__init__.py`, `registers.py`, `client.py`
  - `ui/__init__.py`, `dashboard.py`, `charts.py`
  - `main.py`
  - `solarView.spec`
- **Success criteria:** `python main.py` opens a window, connects to inverter 1 at 192.168.1.7:1502, and shows a live chart of AC power updating every 1 second
- **Status:** ✅ Module scaffold created and verified. Client reads real data: 1099W, 117.6V, 42°C. Battery (Unit 16) needs discovery.
- **Estimated effort:** 2-3 hours

### Milestone 2 — Multi-Inverter + Battery Dashboard
- **Scope:** Read all 3 inverters + battery, display 5 charts in a grid, summary panel with big numbers
- **New files/features:**
  - Multi-unit discovery (scan unit IDs 1-247 or use manual config)
  - 2×3 grid of charts: AC Power (each inverter), Battery Power/SOE, House Load estimate
  - Summary panel: total solar generation, battery %, grid import/export
- **Success criteria:** All 4 devices read simultaneously, all charts updating in sync
- **Estimated effort:** 4-5 hours

### Milestone 3 — Native Polish & Packaging
- **Scope:** App icon, proper menu bar (macOS), `--watch` style status, single-binary build
- **New files/features:**
  - `icons/solarview.icns` (512×512 → ICNS)
  - macOS menu bar integration (Apple menu, Preferences)
  - `pyinstaller --onefile` build script
  - README with install + usage instructions
- **Success criteria:** `./build.sh` produces `solarView.app`, double-clickable, native feel
- **Estimated effort:** 3-4 hours

### Milestone 4 — Stretch Goals
- Configurable refresh rate, unit ID scan, export chart as PNG, dark mode toggle
- Per-inverter naming/aliases
- Network error resilience (graceful degradation when inverter unreachable)

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Modbus connection flakes / inverter reboots | Connection retry with backoff; UI shows "disconnected" state |
| Battery Unit ID unknown | Auto-scan common range or add to config.yaml |
| Endianness quirks on uint64 energy registers | Use pymodbus `Decoder` with explicit byte/word order — tested against reference project |
| tkinter on macOS requires ActivePython/Tcl | Test with system Python first; document Homebrew Tcl-Tk requirement if needed |

## Out of Scope

- ✗ Historical data storage (SQLite, CSV export)
- ✗ Web/dashboard (this is desktop-only)
- ✗ SolarEdge API/cloud integration (pure local Modbus)
- ✗ Configuration write-back to inverter (read-only)
