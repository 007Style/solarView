"""Main dashboard window for solarView.

Combines live charts and a summary panel, driven by data from the
ModbusManager background thread.

Threading model:
  - ModbusManager._run() runs on a daemon thread, reads Modbus, pushes
    bundles to a queue.  It never touches tkinter.
  - Dashboard._tick() runs on the main (UI) thread via root.after().
    It drains the queue and calls chart/summary update methods — which are
    all tkinter/matplotlib ops and must only happen on the UI thread.
"""

from __future__ import annotations

import csv
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox

from solaredge_modbus import SolarEdgeClient
from .about import AboutDialog
from .charts import LiveChart, DARK_THEME, LIGHT_THEME
from .summary import SummaryPanel


def _force_ttk_theme() -> None:
    """Switch away from the macOS 'aqua' ttk theme.

    The aqua theme ignores tk widget bg/fg options and renders everything with
    native macOS colours.  Switching to 'clam' (cross-platform, ships with Tk)
    lets us set background colours directly on every widget.
    """
    style = ttk.Style()
    available = style.theme_names()
    # Prefer clam (most neutral), fall back to alt, then default
    for name in ("clam", "alt", "default"):
        if name in available:
            style.theme_use(name)
            return


# ── Run Logger — tees stdout/stderr to a dated text file ─────────────────────

class RunLogger:
    """Redirect stdout and stderr to both the terminal and a dated log file.

    All print() calls and tracebacks are captured transparently.
    Call close() to flush and restore the original streams.
    """

    def __init__(self, log_dir: str):
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._path = os.path.join(log_dir, f"solarview_run_log_{ts}.txt")
        self._file = open(self._path, "w", buffering=1, encoding="utf-8")
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        sys.stdout = self          # type: ignore[assignment]
        sys.stderr = self          # type: ignore[assignment]
        self.write(f"[RunLogger] Session started {datetime.now().isoformat()}\n")
        self.write(f"[RunLogger] Log file: {self._path}\n")

    # ── io.TextIOBase-compatible interface ────────────────────────────────────

    def write(self, text: str) -> int:
        self._orig_stdout.write(text)
        self._orig_stdout.flush()
        try:
            self._file.write(text)
        except Exception:
            pass
        return len(text)

    def flush(self) -> None:
        self._orig_stdout.flush()
        try:
            self._file.flush()
        except Exception:
            pass

    @property
    def path(self) -> str:
        return self._path

    def close(self) -> None:
        self.write(f"[RunLogger] Session ended {datetime.now().isoformat()}\n")
        sys.stdout = self._orig_stdout
        sys.stderr = self._orig_stderr
        try:
            self._file.close()
        except Exception:
            pass
        print(f"[RunLogger] Run log saved: {self._path}")


# ── CSV Data Logger ───────────────────────────────────────────────────────────

class DataLogger:
    """Logs Modbus data to CSV; discovers new columns dynamically."""

    def __init__(self, config: dict, base_filename: str = "solarview_log"):
        log_cfg = config.get("logging", {})
        base_dir = os.path.expanduser(log_cfg.get("directory", "~/solarView"))
        os.makedirs(base_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._filepath = os.path.join(base_dir, f"{base_filename}_{timestamp}.csv")
        self._file = open(self._filepath, "w", newline="", buffering=1)
        self._fieldnames = ["timestamp"]
        self._writer = csv.DictWriter(self._file, fieldnames=self._fieldnames)
        self._writer.writeheader()
        print(f"[DataLogger] Logging to: {self._filepath}")

    def log(self, data: dict) -> None:
        """Log a data bundle to CSV. Discovers new columns on the fly."""
        row: dict = {"timestamp": datetime.now().isoformat(sep=" ")}
        for key, val in data.items():
            if isinstance(val, dict):
                for subkey, subval in val.items():
                    row[f"{key}_{subkey}"] = subval
            else:
                row[key] = val

        new_fields = [k for k in row if k not in self._fieldnames]
        if new_fields:
            self._fieldnames.extend(new_fields)
            self._rewrite_file()

        for col in self._fieldnames:
            row.setdefault(col, "")
        self._writer.writerow(row)
        self._file.flush()

    def _rewrite_file(self) -> None:
        self._file.close()
        with open(self._filepath, "r", newline="") as f:
            existing = list(csv.reader(f))

        self._file = open(self._filepath, "w", newline="", buffering=1)
        self._writer = csv.DictWriter(self._file, fieldnames=self._fieldnames)
        self._writer.writeheader()

        if len(existing) > 1:
            old_header = existing[0]
            for old_row in existing[1:]:
                row_dict: dict = {}
                for i, val in enumerate(old_row):
                    if i < len(old_header) and old_header[i] in self._fieldnames:
                        row_dict[old_header[i]] = val
                for col in self._fieldnames:
                    row_dict.setdefault(col, "")
                self._writer.writerow(row_dict)
        self._file.flush()

    def close(self) -> None:
        if self._file:
            self._file.close()
            print(f"[DataLogger] Log saved: {self._filepath}")


# ── ModbusManager — background polling thread ─────────────────────────────────

class ModbusManager:
    """Polls SolarEdge inverters and batteries on a background daemon thread.

    Each device's data is pushed to a queue immediately after it responds,
    so the UI can update in real-time rather than waiting for a full scan.
    The UI thread drains the queue via Dashboard._tick().
    """

    def __init__(self, config: dict):
        self._config = config
        self._inv_cfg = config.get("inverter", {})
        self._bat_cfg = config.get("battery", {})

        self._host = self._inv_cfg.get("host", "192.168.1.7")
        self._port = self._inv_cfg.get("port", 1502)
        self._timeout = self._inv_cfg.get("timeout", 5.0)
        self._inverter_units: list[int] = self._inv_cfg.get("units", [1, 2, 3])

        # Battery unit IDs from config or derived from inverter count
        self._battery_units: list[int] = self._bat_cfg.get(
            "unit_ids", self._derive_battery_ids(self._inverter_units)
        )

        poll_seconds = config.get("ui", {}).get("poll_interval_seconds", 2)
        self._poll_seconds: float = poll_seconds

        # Queue holds bundles of the form {"inverter_1": {...}} or {"battery_15": {...}}
        self._queue: queue.Queue = queue.Queue(maxsize=50)
        self._running = threading.Event()
        self._thread: threading.Thread | None = None
        self._client: SolarEdgeClient | None = None

        log_cfg = config.get("logging", {})
        if log_cfg.get("enabled", True):
            self._logger: DataLogger | None = DataLogger(config)
        else:
            self._logger = None

    @staticmethod
    def _derive_battery_ids(inverter_units: list[int]) -> list[int]:
        """Derive battery unit IDs from inverter list.

        SolarEdge residential: Inv1→15/14, Inv2→13/12, Inv3→11/10.
        """
        ids = []
        for i in range(len(inverter_units)):
            primary = 15 - i * 2
            ids.extend([primary, primary - 1])
        return ids

    def start(self) -> None:
        self._running.set()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ModbusReader")
        self._thread.start()

    def stop(self) -> None:
        self._running.clear()
        if self._client:
            self._client.close()
            self._client = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

    def latest(self) -> dict | None:
        """Non-blocking dequeue — returns None if queue is empty."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def _push(self, data: dict) -> None:
        """Push a device bundle to the queue and log it."""
        try:
            self._queue.put_nowait(data)
        except queue.Full:
            # Drop the oldest item to make room
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(data)
            except queue.Full:
                pass

        if self._logger:
            try:
                self._logger.log(data)
            except Exception as e:
                print(f"[ModbusManager] CSV log error: {e}")

    def _run(self) -> None:
        """Background loop: read each device, push bundles immediately."""
        while self._running.is_set():
            try:
                # (Re-)establish connection if needed
                if not self._client:
                    self._client = SolarEdgeClient(
                        host=self._host, port=self._port, timeout=self._timeout
                    )
                    if not self._client.connect():
                        print(f"[ModbusManager] Cannot connect to {self._host}:{self._port}")
                        self._client = None
                        time.sleep(self._poll_seconds)
                        continue

                # ── Read inverters ────────────────────────────────────────────
                for uid in self._inverter_units:
                    if not self._running.is_set():
                        break
                    try:
                        inv = self._client.read_inverter(unit_id=uid)
                        if inv:
                            self._push({f"inverter_{uid}": inv})
                            print(f"[ModbusManager] INV{uid} "
                                  f"Power={inv.get('ac_power')} W  "
                                  f"Temp={inv.get('temperature')} °C")
                        else:
                            print(f"[ModbusManager] INV{uid}: no response")
                    except Exception as e:
                        print(f"[ModbusManager] INV{uid} error: {e}")
                        self._safe_disconnect()

                # ── Read battery from each inverter unit (up to 6 batteries) ──
                # Each inverter exposes its attached battery on its own unit_id
                # at fixed SunSpec addresses.  We try every inverter unit.
                for uid in self._inverter_units:
                    if not self._running.is_set():
                        break
                    try:
                        bat = self._client.read_battery(unit_id=uid)
                        if bat:
                            self._push({f"battery_{uid}": bat})
                            soe   = bat.get("battery_soe")
                            pwr   = bat.get("battery_power")
                            state = bat.get("battery_state_str", "?")
                            print(f"[ModbusManager] BAT{uid} "
                                  f"SoE={soe}%  Power={pwr} W  State={state}")
                    except Exception as e:
                        print(f"[ModbusManager] BAT{uid} error: {e}")

                time.sleep(self._poll_seconds)

            except Exception as e:
                print(f"[ModbusManager] CRITICAL: {e}")
                self._safe_disconnect()
                time.sleep(self._poll_seconds)

    def _safe_disconnect(self) -> None:
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None


# ── Config dialog ─────────────────────────────────────────────────────────────

class ConfigDialog(tk.Toplevel):
    """Modal dialog for editing connection settings and log directory."""

    def __init__(self, parent: tk.Tk, config: dict, theme: dict | None = None):
        super().__init__(parent)
        self.title("solarView — Settings")
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)

        t = theme or DARK_THEME
        self.configure(bg=t["bg"])

        self._config = config
        self._result: dict | None = None

        inv_cfg = config.get("inverter", {})
        log_cfg = config.get("logging",  {})
        ui_cfg  = config.get("ui", {})

        # Apply a ttk style that respects dark bg
        style = ttk.Style(self)
        style.configure("Dark.TLabelframe",        background=t["bg"],       foreground=t["fg"])
        style.configure("Dark.TLabelframe.Label",  background=t["bg"],       foreground=t["fg"])
        style.configure("Dark.TLabel",             background=t["bg"],       foreground=t["fg"])
        style.configure("Dark.TEntry",             fieldbackground=t["axes_bg"], foreground=t["fg"],
                        insertcolor=t["fg"])
        style.configure("Dark.TCheckbutton",       background=t["bg"],       foreground=t["fg"])
        style.configure("Dark.TButton",            background=t["axes_bg"],  foreground=t["fg"])

        pad = {"padx": 10, "pady": 4}

        # ── Connection ────────────────────────────────────────────────────────
        conn_frame = ttk.LabelFrame(self, text="Connection", padding=8, style="Dark.TLabelframe")
        conn_frame.pack(fill=tk.X, padx=12, pady=(12, 4))

        ttk.Label(conn_frame, text="Host / IP address:", style="Dark.TLabel").grid(row=0, column=0, sticky=tk.W, **pad)
        self._host_var = tk.StringVar(value=inv_cfg.get("host", "192.168.1.7"))
        ttk.Entry(conn_frame, textvariable=self._host_var, width=22, style="Dark.TEntry").grid(row=0, column=1, **pad)

        ttk.Label(conn_frame, text="Port:", style="Dark.TLabel").grid(row=1, column=0, sticky=tk.W, **pad)
        self._port_var = tk.StringVar(value=str(inv_cfg.get("port", 1502)))
        ttk.Entry(conn_frame, textvariable=self._port_var, width=8, style="Dark.TEntry").grid(row=1, column=1, sticky=tk.W, **pad)

        ttk.Label(conn_frame, text="Timeout (s):", style="Dark.TLabel").grid(row=2, column=0, sticky=tk.W, **pad)
        self._timeout_var = tk.StringVar(value=str(inv_cfg.get("timeout", 5.0)))
        ttk.Entry(conn_frame, textvariable=self._timeout_var, width=8, style="Dark.TEntry").grid(row=2, column=1, sticky=tk.W, **pad)

        # ── Chart window ─────────────────────────────────────────────────────
        chart_frame = ttk.LabelFrame(self, text="Chart Window", padding=8, style="Dark.TLabelframe")
        chart_frame.pack(fill=tk.X, padx=12, pady=4)

        ttk.Label(chart_frame, text="Rolling window:", style="Dark.TLabel").grid(row=0, column=0, sticky=tk.W, **pad)
        self._chart_hours_var = tk.IntVar(value=int(ui_cfg.get("chart_window_hours", 2)))
        for col, hours in enumerate([2, 12]):
            ttk.Radiobutton(
                chart_frame,
                text=f"{hours}h",
                variable=self._chart_hours_var,
                value=hours,
                style="Dark.TCheckbutton",   # TCheckbutton renders fine for radio buttons on clam
            ).grid(row=0, column=col + 1, sticky=tk.W, padx=(0, 8))

        # ── Logging ───────────────────────────────────────────────────────────
        log_frame = ttk.LabelFrame(self, text="Logging", padding=8, style="Dark.TLabelframe")
        log_frame.pack(fill=tk.X, padx=12, pady=4)

        ttk.Label(log_frame, text="Log directory:", style="Dark.TLabel").grid(row=0, column=0, sticky=tk.W, **pad)
        self._logdir_var = tk.StringVar(value=log_cfg.get("directory", "~/solarView"))
        ttk.Entry(log_frame, textvariable=self._logdir_var, width=30, style="Dark.TEntry").grid(row=0, column=1, **pad)

        ttk.Label(log_frame, text="Data logging enabled:", style="Dark.TLabel").grid(row=1, column=0, sticky=tk.W, **pad)
        self._log_enabled_var = tk.BooleanVar(value=log_cfg.get("enabled", True))
        ttk.Checkbutton(log_frame, variable=self._log_enabled_var, style="Dark.TCheckbutton").grid(row=1, column=1, sticky=tk.W, **pad)

        ttk.Label(log_frame, text="Enable run log:", style="Dark.TLabel").grid(row=2, column=0, sticky=tk.W, **pad)
        self._run_log_var = tk.BooleanVar(value=log_cfg.get("run_log_enabled", True))
        ttk.Checkbutton(log_frame, variable=self._run_log_var, style="Dark.TCheckbutton").grid(row=2, column=1, sticky=tk.W, **pad)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = tk.Frame(self, bg=t["bg"])
        btn_frame.pack(fill=tk.X, padx=12, pady=(4, 12))
        ttk.Button(btn_frame, text="Save",   command=self._save,    style="Dark.TButton").pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy,  style="Dark.TButton").pack(side=tk.RIGHT, padx=4)

        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    def _save(self) -> None:
        try:
            port    = int(self._port_var.get())
            timeout = float(self._timeout_var.get())
        except ValueError:
            messagebox.showerror("Invalid input", "Port must be an integer and timeout a number.",
                                 parent=self)
            return
        self._result = {
            "host":              self._host_var.get().strip(),
            "port":              port,
            "timeout":           timeout,
            "log_dir":           self._logdir_var.get().strip(),
            "log_enabled":       self._log_enabled_var.get(),
            "run_log_enabled":   self._run_log_var.get(),
            "chart_window_hours": self._chart_hours_var.get(),
        }
        self.destroy()

    @property
    def result(self) -> dict | None:
        return self._result


# ── Dashboard — main tkinter window ──────────────────────────────────────────

class Dashboard(tk.Tk):
    """Main application window."""

    # Per-chart pixel budget used to compute the initial window width.
    # Each inverter gets one chart in the top row; the bottom row always
    # has 3 charts (battery power, battery SOE, frequency).
    _CHART_W = 460    # pixels per chart column (widened for Battery State tile)
    _CHART_H = 340    # pixels per chart row (two rows)
    _SUMMARY_H = 110  # summary strip height
    _CHROME_H  = 60   # menu bar + window decorations

    def __init__(self, modbus_manager: ModbusManager, config: dict):
        super().__init__()

        # Must happen before any ttk widget is created so the theme applies globally
        _force_ttk_theme()

        self._manager     = modbus_manager
        self._config      = config
        self._ui_cfg      = config.get("ui", {})
        self._refresh_ms  = self._ui_cfg.get("refresh_interval_ms", 1000)
        self._poll_secs   = float(self._ui_cfg.get("poll_interval_seconds", 2))
        self._window_hours = int(self._ui_cfg.get("chart_window_hours", 2))
        self._chart_max   = self._window_hours_to_maxlen(self._window_hours)

        # Theme — dark by default, toggled via menu
        default_theme = self._ui_cfg.get("theme", "dark")
        self._theme   = DARK_THEME if default_theme == "dark" else LIGHT_THEME
        self._is_dark = (self._theme is DARK_THEME)

        self._tick_id: str | None = None   # after() callback id — cancelled on close

        # Run logger — started before anything else so every print() is captured
        log_cfg = config.get("logging", {})
        log_dir = os.path.expanduser(log_cfg.get("directory", "~/solarView"))
        if log_cfg.get("run_log_enabled", True):
            self._run_logger: RunLogger | None = RunLogger(log_dir)
        else:
            self._run_logger = None

        self._setup_window()
        self._setup_layout()
        self._setup_menus()

        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        self._manager.start()
        self._tick()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _window_hours_to_maxlen(self, hours: int) -> int:
        """Convert a rolling-window duration to a deque maxlen.

        maxlen = window_seconds / poll_interval_seconds.
        We use the manager's current poll rate if it's already running,
        otherwise fall back to self._poll_secs set at init time.
        """
        poll = getattr(self._manager, "_poll_seconds", self._poll_secs)
        return max(60, int(hours * 3600 / poll))

    def _apply_window_hours(self, hours: int) -> None:
        """Resize all chart deques to match a new rolling window."""
        self._window_hours = hours
        new_maxlen = self._window_hours_to_maxlen(hours)
        self._chart_max = new_maxlen
        for chart in self.charts.values():
            chart.resize_maxlen(new_maxlen)
        self._config.setdefault("ui", {})["chart_window_hours"] = hours
        print(f"[Dashboard] Chart window → {hours}h ({new_maxlen} points)")

    # ── Window ────────────────────────────────────────────────────────────────

    def _screen_bounds_at_pointer(self) -> tuple[int, int, int, int]:
        """Return (scr_x, scr_y, width, height) of the screen the mouse is on.

        Uses a Swift one-liner to get the exact NSScreen frames (macOS global
        coords, where screens to the left of the primary have negative x).
        Falls back to arithmetic if Swift is unavailable.
        """
        pw = self.winfo_screenwidth()
        ph = self.winfo_screenheight()
        px = self.winfo_pointerx()
        py = self.winfo_pointery()

        # ── Method 1: Swift NSScreen (exact, no Python package needed) ───────
        try:
            import subprocess, re as _re
            swift_code = (
                "import AppKit;"
                "let s=NSScreen.screens;"
                "let ph=Int(s[0].frame.height);"
                "for sc in s{"
                "let f=sc.frame;"
                "let y=ph-Int(f.origin.y)-Int(f.size.height);"
                "print(\"\\(Int(f.origin.x)) \\(y) \\(Int(f.size.width)) \\(Int(f.size.height))\")"
                "}"
            )
            r = subprocess.run(
                ["swift", "-e", swift_code],
                capture_output=True, text=True, timeout=8
            )
            for line in r.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) == 4:
                    sx, sy, sw, sh = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                    if sx <= px < sx + sw and sy <= py < sy + sh:
                        return sx, sy, sw, sh
        except Exception:
            pass

        # ── Method 2: arithmetic fallback (handles negative-x left screens) ──
        # floor-divide handles negative x correctly:
        #   px=-2000, pw=3440 → -2000//3440 = -1 → scr_x = -3440  (left screen)
        #   px= 1000, pw=3440 →  1000//3440 =  0 → scr_x =     0  (primary)
        screen_index = px // pw          # no max(0) — left screen is index -1
        scr_x = screen_index * pw
        return scr_x, 0, pw, ph

    def _default_geometry(self) -> str:
        """Compute the default WxH+X+Y geometry string from scratch."""
        n_inv  = len(self._manager._inverter_units)
        n_cols = max(n_inv, 3)
        scr_x, scr_y, sw, sh = self._screen_bounds_at_pointer()
        ideal_w = n_cols * self._CHART_W
        col_w   = self._CHART_W if ideal_w <= int(sw * 0.97) else max(280, int(sw * 0.97) // n_cols)
        width   = n_cols * col_w
        height  = min((self._CHART_H * 2) + self._SUMMARY_H + self._CHROME_H, int(sh * 0.90))
        x = scr_x + (sw - width)  // 2
        y = scr_y + (sh - height) // 2
        return f"{width}x{height}+{x}+{y}"

    def _setup_window(self) -> None:
        self.title("solarView")
        t = self._theme

        n_inv  = len(self._manager._inverter_units)
        n_cols = max(n_inv, 3)
        self.minsize(n_cols * 280, 700)
        self.configure(bg=t["bg"])

        # Restore saved geometry if present, otherwise compute default
        saved = self._ui_cfg.get("window_geometry", "")
        if saved:
            try:
                self.geometry(saved)
                print(f"[Dashboard] Restored geometry: {saved}")
            except Exception:
                saved = ""
        if not saved:
            geo = self._default_geometry()
            self.geometry(geo)
            print(f"[Dashboard] Default geometry: {geo}")

        try:
            self.tk.call("tk", "mac", "redeminimize", True)
        except Exception:
            pass

    # ── Layout ────────────────────────────────────────────────────────────────

    def _setup_layout(self) -> None:
        units = self._manager._inverter_units
        t     = self._theme

        # Tracks which battery unit IDs have had their summary tiles created.
        # Starts with unit 1 (the known battery); others appear on first response.
        self._bat_tiles_created: set[int] = set()

        # ── Summary panel ─────────────────────────────────────────────────────
        self.summary = SummaryPanel(self, theme=t)
        self.summary.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        for uid in units:
            self.summary.add_metric(f"inv{uid}_power", f"Inv {uid} Power", "W")
            self.summary.add_metric(f"inv{uid}_volt",  f"Inv {uid} V",     "V")
            self.summary.add_metric(f"inv{uid}_temp",  f"Inv {uid} Temp",  "°C")

        # Create summary tiles for unit 1 (the known battery) immediately.
        # Chart series for unit 1 are registered further down once self.charts exists.
        # Tiles for other units are added dynamically when data first arrives.
        first_uid = units[0]
        self._bat_tiles_created.add(first_uid)
        self.summary.add_metric(f"bat{first_uid}_soe",   f"Bat{first_uid} SOE",   "%")
        self.summary.add_metric(f"bat{first_uid}_power", f"Bat{first_uid} W",     "W")
        self.summary.add_metric(f"bat{first_uid}_state", f"Bat{first_uid} State", "")

        self.summary.add_metric("total_power", "Total Solar", "W")
        self.summary.add_metric("frequency",   "Frequency",   "Hz")

        # ── Chart grid ────────────────────────────────────────────────────────
        self._chart_frame = tk.Frame(self, bg=t["bg"], highlightthickness=0, bd=0)
        self._chart_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.charts: dict[str, LiveChart] = {}

        # Top row — one chart per inverter
        self._top_row = tk.Frame(self._chart_frame, bg=t["bg"], highlightthickness=0, bd=0)
        self._top_row.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=2)

        for uid in units:
            chart = LiveChart(
                self._top_row,
                title=f"Inverter {uid} — AC Power",
                ylabel="W",
                color="#3b82d4",
                maxlen=self._chart_max,
                theme=t,
            )
            self.charts[f"inv{uid}_power"] = chart
            chart.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)

        # Bottom row — battery power, SOE, frequency
        self._bottom_row = tk.Frame(self._chart_frame, bg=t["bg"], highlightthickness=0, bd=0)
        self._bottom_row.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=2)

        for key, title, ylabel, color in [
            ("battery_power_chart", "Battery Power",  "W",  "#10b981"),
            ("battery_soe_chart",   "Battery SOE",    "%",  "#f59e0b"),
            ("frequency_chart",     "Grid Frequency", "Hz", "#8b5cf6"),
        ]:
            chart = LiveChart(
                self._bottom_row, title=title, ylabel=ylabel,
                color=color, maxlen=self._chart_max, theme=t,
            )
            self.charts[key] = chart
            chart.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)

        # Register the first battery's named series on both battery charts.
        # Additional batteries are registered in _add_battery_tiles() as they appear.
        first_uid = units[0]
        self.charts["battery_power_chart"].add_series(f"Bat {first_uid}", color="#10b981")
        self.charts["battery_soe_chart"].add_series(f"Bat {first_uid}",   color="#f59e0b")

    # ── Battery tile helpers ──────────────────────────────────────────────────

    def _add_battery_tiles(self, uid: int) -> None:
        """Create the three summary tiles for battery uid and mark them created.

        Safe to call at any time from the UI thread — tiles are packed into the
        existing SummaryPanel frame and appear immediately.
        """
        if uid in self._bat_tiles_created:
            return
        self._bat_tiles_created.add(uid)
        # Summary strip tiles
        self.summary.add_metric(f"bat{uid}_soe",   f"Bat{uid} SOE",   "%")
        self.summary.add_metric(f"bat{uid}_power", f"Bat{uid} W",     "W")
        self.summary.add_metric(f"bat{uid}_state", f"Bat{uid} State", "")
        # Register a new series on both battery charts (auto-colour from palette)
        self.charts["battery_power_chart"].add_series(f"Bat {uid}")
        self.charts["battery_soe_chart"].add_series(f"Bat {uid}")
        print(f"[Dashboard] Battery tiles + chart series created for unit {uid}")

    # ── Menus ─────────────────────────────────────────────────────────────────

    def _setup_menus(self) -> None:
        self._menubar = tk.Menu(self)
        self.config(menu=self._menubar)

        # solarView menu
        app_menu = tk.Menu(self._menubar, tearoff=0)
        self._menubar.add_cascade(label="solarView", menu=app_menu)
        app_menu.add_command(label="About solarView",       command=self._open_about)
        app_menu.add_separator()
        app_menu.add_command(label="Settings…",             command=self._open_settings)
        app_menu.add_command(label="Open Log Directory",    command=self._open_log_dir)
        app_menu.add_command(label="Reset Window Geometry", command=self._reset_geometry)
        app_menu.add_separator()
        # Theme toggle — stored by label so entryconfig can find it reliably
        self._theme_toggle_label = "Switch to Light Theme"
        self._app_menu = app_menu
        app_menu.add_command(label=self._theme_toggle_label, command=self._toggle_theme)
        app_menu.add_separator()
        app_menu.add_command(label="Quit", command=self._on_closing)

        # Poll rate submenu
        rate_menu = tk.Menu(self._menubar, tearoff=0)
        self._menubar.add_cascade(label="Poll Rate", menu=rate_menu)
        self._poll_var = tk.IntVar(value=int(self._manager._poll_seconds))
        for sec in [2, 5, 30, 60]:
            rate_menu.add_radiobutton(
                label=f"{sec}s",
                variable=self._poll_var,
                value=sec,
                command=self._on_poll_rate_change,
            )

    # ── Theme toggle ──────────────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        """Flip between dark and light and repaint every widget."""
        self._is_dark = not self._is_dark
        self._theme   = DARK_THEME if self._is_dark else LIGHT_THEME
        t = self._theme

        # Update menu label — look up by current label string, swap to next
        next_label = "Switch to Light Theme" if self._is_dark else "Switch to Dark Theme"
        self._app_menu.entryconfig(self._theme_toggle_label, label=next_label)
        self._theme_toggle_label = next_label

        # Window and frame backgrounds
        self.configure(bg=t["bg"])
        self._chart_frame.configure(bg=t["bg"], highlightthickness=0)
        self._top_row.configure(bg=t["bg"], highlightthickness=0)
        self._bottom_row.configure(bg=t["bg"], highlightthickness=0)

        # Summary panel
        self.summary.apply_theme(t)

        # All charts
        for chart in self.charts.values():
            chart.apply_theme(t)

        print(f"[Dashboard] Theme → {'dark' if self._is_dark else 'light'}")

    # ── Menu handlers ─────────────────────────────────────────────────────────

    def _open_about(self) -> None:
        readme_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "README.md",
        )
        dlg = AboutDialog(self, theme=self._theme, readme_path=readme_path)
        self.wait_window(dlg)

    def _open_settings(self) -> None:
        dlg = ConfigDialog(self, self._config, theme=self._theme)
        self.wait_window(dlg)
        result = dlg.result
        if result is None:
            return

        self._config.setdefault("inverter", {})
        self._config["inverter"]["host"]    = result["host"]
        self._config["inverter"]["port"]    = result["port"]
        self._config["inverter"]["timeout"] = result["timeout"]
        self._config.setdefault("logging", {})
        self._config["logging"]["directory"]       = result["log_dir"]
        self._config["logging"]["enabled"]         = result["log_enabled"]
        self._config["logging"]["run_log_enabled"] = result["run_log_enabled"]

        # Start or stop the run logger if the setting changed
        new_run_log = result["run_log_enabled"]
        if new_run_log and self._run_logger is None:
            new_dir = os.path.expanduser(result["log_dir"])
            self._run_logger = RunLogger(new_dir)
        elif not new_run_log and self._run_logger is not None:
            self._run_logger.close()
            self._run_logger = None

        self._manager._host    = result["host"]
        self._manager._port    = result["port"]
        self._manager._timeout = result["timeout"]
        self._manager._safe_disconnect()

        # Apply new chart rolling window if it changed
        new_hours = result.get("chart_window_hours", self._window_hours)
        if new_hours != self._window_hours:
            self._apply_window_hours(new_hours)

        messagebox.showinfo(
            "Settings saved",
            "Connection settings updated.\nNew values take effect on the next poll.",
            parent=self,
        )

    def _open_log_dir(self) -> None:
        log_path = self._manager._logger._filepath if self._manager._logger else None
        log_dir  = os.path.dirname(log_path) if log_path else os.path.expanduser("~/solarView")
        os.makedirs(log_dir, exist_ok=True)
        try:
            subprocess.run(["open", log_dir], check=True)
        except Exception as e:
            print(f"[Dashboard] Could not open log dir: {e}")

    def _on_poll_rate_change(self) -> None:
        self._manager._poll_seconds = float(self._poll_var.get())
        print(f"[Dashboard] Poll rate → {self._manager._poll_seconds}s")

    # ── UI update loop ────────────────────────────────────────────────────────

    def _tick(self) -> None:
        """Drain the data queue and refresh the UI.  Runs on the main thread only."""
        try:
            processed = 0
            while processed < 20:
                bundle = self._manager.latest()
                if bundle is None:
                    break
                self._update_ui(bundle)
                processed += 1
        except Exception as e:
            print(f"[Dashboard] _tick error: {e}")
        self._tick_id = self.after(self._refresh_ms, self._tick)

    def _update_ui(self, bundle: dict) -> None:
        """Apply one device-bundle to charts and summary."""
        if not bundle:
            return

        units = self._manager._inverter_units

        # ── Inverter bundles ──────────────────────────────────────────────────
        for uid in units:
            inv = bundle.get(f"inverter_{uid}")
            if inv is None:
                continue
            try:
                power = inv.get("ac_power")
                if power is not None:
                    chart = self.charts.get(f"inv{uid}_power")
                    if chart:
                        chart.append(power)
                        chart.redraw()
                    self.summary.update(f"inv{uid}_power", power, "W")

                volt = inv.get("voltage_an")
                if volt is not None:
                    self.summary.update(f"inv{uid}_volt", volt, "V")

                temp = inv.get("temperature")
                if temp is not None:
                    self.summary.update(f"inv{uid}_temp", temp, "°C")

                # Only append frequency from the first inverter to avoid
                # triple-counting the same grid reading every poll cycle.
                if uid == units[0]:
                    freq = inv.get("frequency")
                    if freq is not None:
                        self.charts["frequency_chart"].append(freq)
                        self.charts["frequency_chart"].redraw()
                        self.summary.update("frequency", freq, "Hz")

            except Exception as e:
                print(f"[Dashboard] inverter_{uid} update error: {e}")

        # Recalculate total solar from latest chart readings
        try:
            total = sum(
                v for uid in units
                if (v := (self.charts.get(f"inv{uid}_power") or type("", (), {"latest": lambda s: None})()).latest()) is not None
            )
            if total > 0:
                self.summary.update("total_power", total, "W")
        except Exception:
            pass

        # ── Battery bundles — keyed by battery_{uid} ─────────────────────────
        # Each battery gets its own named series on the SOE and power charts.
        # Tiles and series are created lazily on first response.
        soe_updated = False
        pwr_updated = False

        for uid in units:
            bat = bundle.get(f"battery_{uid}")
            if not bat or not isinstance(bat, dict):
                continue
            try:
                soe   = bat.get("battery_soe")
                bp    = bat.get("battery_power")
                state = bat.get("battery_state_str")

                # Create summary tiles + chart series on first response
                self._add_battery_tiles(uid)

                # Per-battery summary tiles
                if soe is not None:
                    self.summary.update(f"bat{uid}_soe", soe, "%")
                if bp is not None:
                    self.summary.update(f"bat{uid}_power", bp, "W")
                if state:
                    self.summary.update_text(f"bat{uid}_state", state)

                # Append to this battery's named series on both charts
                series_label = f"Bat {uid}"
                if soe is not None:
                    self.charts["battery_soe_chart"].append(soe, series=series_label)
                    soe_updated = True
                if bp is not None:
                    self.charts["battery_power_chart"].append(bp, series=series_label)
                    pwr_updated = True

            except Exception as e:
                print(f"[Dashboard] battery_{uid} update error: {e}")

        # Redraw once per chart after all series have been appended
        if soe_updated:
            self.charts["battery_soe_chart"].redraw()
        if pwr_updated:
            self.charts["battery_power_chart"].redraw()

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def _reset_geometry(self) -> None:
        """Revert to computed default size/position and clear saved geometry."""
        self._ui_cfg.pop("window_geometry", None)
        geo = self._default_geometry()
        self.geometry(geo)
        print(f"[Dashboard] Geometry reset to default: {geo}")

    def _on_closing(self) -> None:
        # Save current geometry before anything is torn down
        try:
            self._ui_cfg["window_geometry"] = self.geometry()
            print(f"[Dashboard] Saved geometry: {self._ui_cfg['window_geometry']}")
        except Exception:
            pass
        print("[Dashboard] Shutting down…")

        # Cancel the pending _tick so it never fires against a destroyed window
        if self._tick_id is not None:
            try:
                self.after_cancel(self._tick_id)
            except Exception:
                pass
            self._tick_id = None

        # Stop the Modbus thread — this joins it and closes the connection
        self._manager.stop()

        # Flush and close the CSV log
        if self._manager._logger:
            try:
                self._manager._logger.close()
            except Exception:
                pass

        self.quit()      # break mainloop() in main.py
        self.destroy()
        print("[Dashboard] Exit complete.")

        # Close run logger last so it captures the exit message above
        if self._run_logger is not None:
            try:
                self._run_logger.close()
            except Exception:
                pass
