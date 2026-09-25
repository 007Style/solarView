# ☀️ solarView

> **Real-time SolarEdge inverter & battery monitoring — straight from your hardware to your desktop, no cloud nonsense required.**

![Version](https://img.shields.io/badge/version-1.0.0-gold)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)
![License](https://img.shields.io/badge/license-Beerware-yellow)
![Built with](https://img.shields.io/badge/built%20with-IBM%20Bob%20%26%20love-blueviolet)

---

## 🌞 So, What Even Is This?

You've got a SolarEdge solar system. Maybe one inverter, maybe three. Maybe you've got a shiny LG RESU battery sitting in your garage humming quietly. And yet — to see what's actually happening right now, you have to:

1. Open a browser
2. Log in to the SolarEdge cloud portal
3. Wait for it to load
4. Look at data that's 15 minutes stale

**That is insane.** Your hardware is *right there on your local network*. It speaks Modbus TCP. It will talk to you directly, in real time, no internet required.

**solarView** is the solar nerd's solution to this problem. It's a Python desktop app that connects directly to your SolarEdge inverters over Modbus TCP and shows you live, scrolling charts updating every 2 seconds. Power, voltage, temperature, battery state of charge, battery power, grid frequency — all of it, live, in a beautiful dark (or light) themed window that you can put on a spare monitor and just... watch your house make electricity.

It's deeply satisfying. Trust us.

---

## ✨ Features That Actually Matter

| 🟢 Feature | What it does |
|---|---|
| **Live inverter power charts** | One scrolling chart per inverter — watch solar ramp up at sunrise in real time |
| **Battery SOE chart** | State of Charge %, plotted live from the hardware register (not the SolarEdge portal's guesses) |
| **Battery power chart** | Positive = charging, negative = discharging — know exactly what your battery is doing |
| **Grid frequency chart** | 60.00 Hz looks boring until the grid has a bad day |
| **Multi-battery support** | Up to 6 batteries, each on its own named series on the charts |
| **Summary strip** | Big-number tiles at the top — power, voltage, temperature, battery %, state, total solar |
| **Wrapping tile layout** | Tiles wrap to a new row if your window is narrow — nothing ever falls off screen |
| **Dark & light themes** | Toggle instantly from the menu. Dark by default because we're not animals |
| **Rolling chart window** | 2h or 12h rolling history, switchable in Settings |
| **CSV data logging** | Every poll cycle saved to a timestamped CSV — import into Excel, InfluxDB, whatever |
| **Run log capture** | Everything printed to terminal captured to a `.txt` file for post-mortem debugging |
| **Multi-monitor aware** | Opens on whichever screen your mouse is on at launch. Works perfectly with negative-X monitors |
| **Geometry memory** | Remembers window size and position across sessions |
| **Animated About dialog** | A tiny solar system animation because why not |
| **In-app README viewer** | Styled markdown viewer so you can read these docs without leaving the app |

---

## 📸 What It Looks Like

```
┌─────────────────────────────────────────────────────────────────────────┐
│  solarView                                          [dark theme]         │
├─────────────────────────────────────────────────────────────────────────┤
│ [Inv1 Power] [Inv1 V] [Inv1 Temp] [Bat1 SOE] [Bat1 W] [Bat1 State]    │
│ [Inv2 Power] [Inv2 V] [Inv2 Temp] [Total Solar] [Frequency]            │
├─────────────────┬─────────────────┬─────────────────────────────────────┤
│  Inverter 1     │  Inverter 2     │  Inverter 3                         │
│  AC Power (W)   │  AC Power (W)   │  AC Power (W)                       │
│  ╭─────────╮    │  ╭─────────╮    │  ╭─────────╮                        │
│  │ ~~~~~   │    │  │ ~~~~~   │    │  │ ~~~~~   │                        │
│  ╰─────────╯    │  ╰─────────╯    │  ╰─────────╯                        │
├─────────────────┴─────────────────┴─────────────────────────────────────┤
│  Battery Power  │  Battery SOE    │  Grid Frequency                     │
│  (W) Bat1/2/3   │  (%) Bat1/2/3  │  (Hz)                               │
│  ╭─────────╮    │  ╭─────────╮    │  ╭─────────╮                        │
│  │ -310W   │    │  │ 99%     │    │  │ 60.00Hz │                        │
│  ╰─────────╯    │  ╰─────────╯    │  ╰─────────╯                        │
└─────────────────────────────────────────────────────────────────────────┘
```

*(actual data, actual inverters, actual gratuitous ASCII art)*

---

## 🍺 License — Beerware

```
/*
 * ----------------------------------------------------------------------------
 * "THE BEER-WARE LICENSE" (Revision 42):
 * <daneyand> and IBM Bob wrote this software. As long as you retain this
 * notice you can do whatever you want with this stuff. If we meet some day,
 * and you think this is worth it, you can buy us a beer in return.
 * ----------------------------------------------------------------------------
 */
```

Seriously though — if solarView saves you even one annoying trip to the SolarEdge portal, consider buying the authors a beer. We'll probably be at the same hackerspace arguing about register maps.

---

## ⚡ Quick Start (macOS — Pre-built App)

**Zero Python required.**

1. Go to the [**Releases page**](../../releases)
2. Download `solarView-1.0.0-macos-arm64.dmg`
3. Open the DMG

### Easiest install — double-click `Install.command` in the DMG

The DMG contains an `Install.command` script. Double-click it — Terminal opens, strips the Gatekeeper quarantine flag, copies solarView to `/Applications`, and launches it. Done.

### Manual install — drag to Applications

Drag **solarView.app** to the **Applications** folder. Then on first launch:

> 🍎 **App won't open?** macOS silently blocks apps without an Apple Developer certificate. Fix it with **one of these**:
>
> **Option A** — Right-click the app → **Open** → **Open** (one-time only)
>
> **Option B** — Run this in Terminal:
> ```bash
> xattr -r -d com.apple.quarantine /Applications/solarView.app
> ```
> Then double-click normally — no warnings, ever again.

The DMG also includes a `READ ME FIRST.txt` with these same instructions for anyone who misses this README.

---

## 🐧 Linux & Windows — Run From Source

Don't have a Mac? No problem. solarView is pure Python and runs anywhere Python runs.

### Requirements

- Python 3.10 or newer
- `tkinter` (see below — it's not always included by default)
- The packages in `requirements` (5 total, all pip-installable)

### Step 1 — Get tkinter

**Ubuntu/Debian:**
```bash
sudo apt install python3-tk
```

**Fedora/RHEL:**
```bash
sudo dnf install python3-tkinter
```

**Windows:** Python from python.org includes tkinter by default. ✅

**macOS (Homebrew Python):**
```bash
brew install python-tk
```

### Step 2 — Install and run

```bash
git clone https://github.com/007Style/solarView.git
cd solarView

# Create a virtual environment (strongly recommended)
python3 -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .venv\Scripts\activate       # Windows

# Install dependencies
pip install pymodbus matplotlib numpy pyyaml

# Launch
python3 main.py
```

### Step 3 — Point it at your inverter

Edit (or create) `~/.solarview/config.yaml`:

```yaml
inverter:
  host: "192.168.1.X"   # ← your inverter's IP here
  port: 1502            # SolarEdge default Modbus port
  units: [1, 2, 3]      # Adjust for your number of inverters
  timeout: 5.0
```

Done. The window opens on your current screen and starts polling within 2 seconds.

---

## 🏗️ Build From Source (macOS Only — makes a .app + DMG)

Want to build your own distributable `.app`?

```bash
git clone https://github.com/007Style/solarView.git
cd solarView
./build.sh
```

The build script will:
1. Create a `.venv` and install all dependencies automatically
2. Run PyInstaller with the included `.spec` file
3. Ad-hoc sign the resulting `.app`
4. Package it into a `.dmg` file ready for distribution

Output: `dist/solarView-1.0.0-macos-arm64.dmg`

```bash
# Just the .app, no DMG:
./build.sh --app-only
```

---

## ⚠️ CRITICAL FIRST STEP: Enable Modbus TCP on Your Inverter

**solarView cannot read anything until you enable Modbus TCP on your SolarEdge inverter.** It is disabled by default. Here's how:

### The Quick Version

1. Download the **SolarEdge SetApp** on your phone (iOS or Android)
2. Connect your phone to the inverter's local WiFi access point (check your inverter's sticker for the SSID/password)
3. In SetApp, navigate to **Communication → Modbus TCP**
4. Enable it and note the **port** (default: **1502**)
5. Assign your inverter a **static IP** via your router's DHCP reservation settings

### Verify It's Working

From any terminal on the same network:
```bash
nc -z YOUR_INVERTER_IP 1502 && echo "✅ Modbus TCP is open" || echo "❌ Port closed"
```

If you see `✅`, you're ready to run solarView.

> 📖 For detailed instructions, search for **"SolarEdge enable Modbus TCP SetApp"** — the exact UI varies by firmware version. SolarEdge also publishes an official Modbus Implementation Guide on their support portal.

### Multi-Inverter Note

Multiple SolarEdge inverters share a **single IP and port** through the primary inverter. The secondaries are accessed via Modbus **unit IDs** (typically 1, 2, 3). Configure `units: [1, 2, 3]` in your config.

---

## ⚙️ Configuration Reference

Config is loaded in this order (later overrides earlier):

1. `solarView/config/default.yaml` — bundled defaults, don't edit
2. `~/.solarview/config.yaml` — your personal settings ← **edit this one**
3. `--config /path/to/file.yaml` — explicit override via CLI

### Full Config Reference

```yaml
inverter:
  host: "192.168.1.7"       # IP of your primary SolarEdge inverter
  port: 1502                # Modbus TCP port (SolarEdge default: 1502, NOT 502)
  units: [1, 2, 3]          # Modbus unit IDs — adjust to match your system
  timeout: 5.0              # Seconds to wait for a Modbus response
  retries: 1

battery:
  # The LG RESU battery has NO separate unit ID — it's read from unit 1.
  # You usually don't need to touch this section.
  unit_ids: [1]

logging:
  enabled: true             # Write a CSV file every poll cycle
  directory: "~/solarView"  # Where to save CSV and run log files
  run_log_enabled: true     # Capture all terminal output to a .txt file

ui:
  refresh_interval_ms: 1000     # UI redraw frequency (ms)
  poll_interval_seconds: 2      # Modbus poll frequency (2/5/30/60)
  chart_window_hours: 2         # Rolling chart history: 2 or 12 hours
  theme: "dark"                 # "dark" or "light"
```

### Minimal Setup (copy this into `~/.solarview/config.yaml`)

```yaml
inverter:
  host: "192.168.1.X"    # ← change this
  units: [1]             # ← adjust for your inverter count
```

---

## 📊 Dashboard Guide

### Summary Strip (top of window)

Big tiles showing the latest value for each metric. Tiles **wrap to a new row** if the window is too narrow — nothing falls off screen.

| Tile | Meaning |
|---|---|
| **Inv N Power** | AC output wattage — this is what's flowing onto your house circuits |
| **Inv N V** | AC voltage, phase A to neutral |
| **Inv N Temp** | Inverter heat sink temperature °C |
| **BatN SOE** | Battery State of Energy % — the real live value, not a portal estimate |
| **BatN W** | Battery power — positive = charging, negative = discharging |
| **BatN State** | Text status: `Charging` / `Discharging` / `Full/Hold` |
| **Total Solar** | Sum of all inverter AC output |
| **Frequency** | Grid frequency Hz — fun to watch during grid events |

> Battery tiles for Bat2, Bat3, etc. only appear if that hardware actually responds. No ghost tiles.

### Charts

**Top row** — One scrolling watt chart per inverter. Watch sunrise ramp all three up simultaneously. Notice if one panel is shaded.

**Bottom row:**
- **Battery Power** — All batteries plotted on one chart as separate coloured series
- **Battery SOE** — All batteries' state of charge on one chart
- **Grid Frequency** — Just the one grid, thankfully

### Menus

- **solarView → About solarView** — Animated solar system. You earned it.
- **solarView → Settings…** — Change IP, port, log directory, chart window, toggle logging
- **solarView → Switch to Light Theme** — If you live in the sun (figuratively)
- **solarView → Open Log Directory** — Opens Finder/Explorer to your log folder
- **solarView → Reset Window Geometry** — Forgot where you put the window?
- **Poll Rate → 2s / 5s / 30s / 60s** — Tune the Modbus polling frequency live

---

## 🗂️ Log Files

All files go to `~/solarView/` by default (configurable).

### `solarview_log_YYYYMMDD_HHMMSS.csv`

One row per device per poll cycle. Columns are discovered dynamically — new fields appear automatically if new hardware shows up.

Key columns: `timestamp`, `inverter_1_ac_power`, `inverter_1_temperature`, `inverter_1_frequency`, `inverter_1_energy_wh`, `battery_battery_soe`, `battery_battery_power`, `battery_cell_v_max/min/avg`

### `solarview_run_log_YYYYMMDD_HHMMSS.txt`

Every `print()` from the entire session captured here. This is your primary debug tool when something goes wrong at 2 AM and you can't remember what the error was.

---

## 🐛 When Things Go Wrong

### Step 1: Look at the run log

`solarView menu → Open Log Directory` → open the newest `solarview_run_log_*.txt`

Look for lines containing `FAIL`, `error`, `Cannot connect`, or `Traceback`.

### Step 2: Network sanity check

```bash
ping YOUR_INVERTER_IP
nc -z YOUR_INVERTER_IP 1502 && echo "OPEN" || echo "CLOSED"
```

If `CLOSED` — go back to SetApp and enable Modbus TCP.

### Step 3: Run the smoke test

```bash
cd solarView
python3 smoke_test.py
```

This tests the full read chain and prints clear PASS/FAIL for each device.

### Common Errors

| Symptom | Cause | Fix |
|---|---|---|
| All tiles show `—` forever | Can't connect | Check IP, port, Modbus TCP enabled |
| `Connection refused` | Port wrong or Modbus disabled | Enable in SetApp, verify port 1502 |
| `Timed out` | IP wrong, firewall, inverter busy | Check router, try disabling cloud monitor |
| Battery shows `—` only | Battery not on unit 1 / DID 705 not found | Check run log for `BAT1` lines |
| Charts draw but values look wrong | Scale factor mismatch | Open an issue with your run log |
| App won't launch on macOS | Gatekeeper blocked it | Right-click → Open → Open |

---

## 🔬 Register Map Notes (For the Nerds)

The Modbus registers in `registers.py` were verified address-by-address against live SolarEdge hardware. Some non-obvious gotchas that bit us before this version was correct:

- **`[SF][value]` ordering** — SolarEdge puts the scale-factor register *before* the value register. The SunSpec standard says the opposite. Both are "correct" depending on who you ask. We handle it correctly.
- **Frequency is at 40086** (SF at 40087 = −3), not at the SunSpec-standard 40094. Register 40094 is the AC energy low word on this hardware.
- **Battery SoC is at 40225** in SE's proprietary status block (SF at 40226 = −2). Register 40781 (DID 705 off=18) is the user-configured MaxSoC *setpoint* — always 100. Don't confuse them.
- **Battery has no separate Modbus unit ID** — it lives in the SunSpec model chain on unit_id=1. DID 705 @ 40763, DID 703 @ 40677.
- **Battery current uses A_SF** at 40693 (DID 703 off=16), not W_SF. We learned this the hard way.
- **ChaSt=4 is "Full/Hold"** — the charge control mode setpoint stays at 4 even when the battery is actively discharging 310W to power its own BMS. This is normal. The power sign tells you the actual direction.

---

## 🏗️ Project Structure

```
solarView/
├── main.py                     Entry point, config loading, user config persistence
├── build.sh                    macOS build script → .app + .dmg
├── solarview.spec              PyInstaller spec file
├── pyproject.toml              Python project metadata
├── smoke_test.py               CLI connectivity & read test
├── test_client.py              Quick live hardware verification tool
├── config/
│   └── default.yaml            Bundled defaults (don't edit)
├── solaredge_modbus/
│   ├── __init__.py
│   ├── registers.py            Hardware-verified Modbus register map
│   └── client.py               Modbus TCP client + multi-model decoder
└── ui/
    ├── __init__.py
    ├── about.py                Animated About dialog + in-app README viewer
    ├── charts.py               Multi-series LiveChart widget + theme definitions
    ├── dashboard.py            Main window, ModbusManager, DataLogger, RunLogger
    └── summary.py              Wrapping summary strip with place()-based layout
```

---

## 📝 Version History

### v1.0.0 — First Public Release 🎉

- Full multi-inverter support (up to 3 SolarEdge inverters via unit IDs 1–3)
- LG RESU battery integration via SunSpec chain — no separate unit ID scan
- Hardware-verified register map — every address confirmed on live hardware
- Battery SoC from correct register (40225), not the MaxSoC setpoint
- Battery current decoded with correct A_SF (not reusing W_SF)
- Multi-battery chart support — each battery is its own named series
- Battery tiles only appear when hardware actually responds (no ghost tiles)
- Summary strip wraps to multiple rows on narrow windows
- Dark and light themes with live toggle
- Rolling chart window (2h or 12h)
- CSV data logging with dynamic column discovery
- Run log capture for full session debugging
- Multi-monitor aware window placement (handles negative-X left-of-primary monitors)
- Window geometry persistence across sessions
- All settings saved on quit (not just window position)
- Clean shutdown — no zombie processes, Dock icon clears properly
- Animated About dialog with orbiting solar particles
- In-app styled markdown README viewer

---

## 🙌 Contributing

Found a bug? Have a SolarEdge model with different register addresses? Different firmware that puts frequency somewhere else entirely? **Open an issue or PR.**

The more hardware configurations this has been tested on, the better it gets for everyone.

When filing a bug report, please include:
1. The output of `python3 smoke_test.py`
2. The most recent `solarview_run_log_*.txt` from your log directory
3. Your SolarEdge inverter model and firmware version if you know it

---

## 🙏 Acknowledgements

- [pymodbus](https://github.com/pymodbus-dev/pymodbus) — the Modbus TCP library doing all the actual work
- [matplotlib](https://matplotlib.org/) — the charts
- The SunSpec Alliance — for writing down most of the register map
- SolarEdge — for deviating from SunSpec in interesting ways that kept this project exciting

---

*From the minds of IBM Bob & Daneyand* 🍺
