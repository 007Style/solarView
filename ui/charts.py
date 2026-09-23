"""Live charting widget for solarView.

A thread-safe matplotlib chart that embeds in a tkinter frame and scrolls
with live data.  Supports dark and light themes via the apply_theme() method.

Multi-series:
  By default every LiveChart has one series named "default".  Call
  add_series(label, color) to register additional named series before the
  first append().  All series share the same axes, time window, and maxlen.
  A legend is shown automatically when more than one series is present.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk

# ── Theme colour sets ─────────────────────────────────────────────────────────

DARK_THEME: dict = {
    "bg":         "#1e1e2e",   # window / figure background
    "axes_bg":    "#2a2a3e",   # axes face colour
    "fg":         "#cdd6f4",   # text / label colour
    "grid":       "#44475a",   # grid line colour
    "tick":       "#cdd6f4",   # tick label colour
    "spine":      "#6c7086",   # axes border colour
}

LIGHT_THEME: dict = {
    "bg":         "#ffffff",
    "axes_bg":    "#f7f8fa",
    "fg":         "#1f2328",
    "grid":       "#e5e7eb",
    "tick":       "#57606a",
    "spine":      "#d0d7de",
}

# Colour palette for auto-assigned series colours (used by add_series)
_SERIES_PALETTE = [
    "#f59e0b",  # amber   — Bat 1
    "#10b981",  # emerald — Bat 2
    "#3b82f6",  # blue    — Bat 3
    "#ec4899",  # pink    — Bat 4
    "#8b5cf6",  # violet  — Bat 5
    "#f97316",  # orange  — Bat 6
]


class LiveChart:
    """A scrolling live chart backed by matplotlib, embedded in tkinter.

    Thread-safe: call `append()` from any thread, `redraw()` from the UI thread.

    Single-series usage (backwards-compatible):
        chart.append(value)          # appends to "default" series
        chart.redraw()

    Multi-series usage:
        chart.add_series("Bat 2", color="#10b981")
        chart.append(value, series="Bat 2")
        chart.redraw()
    """

    def __init__(
        self,
        parent: tk.Widget,
        title: str,
        ylabel: str,
        color: str = "#3b82d4",
        maxlen: int = 120,
        theme: dict | None = None,
    ):
        self.parent  = parent
        self.title   = title
        self.ylabel  = ylabel
        self._maxlen = maxlen
        self._lock   = threading.Lock()
        self._theme  = theme or DARK_THEME

        # Ordered dict: label → {"color": str, "data": deque}
        # "default" is always present (used by single-series callers).
        self._series: dict[str, dict] = {
            "default": {"color": color, "data": deque(maxlen=maxlen)}
        }

        # ── Build figure ──────────────────────────────────────────────────────
        t = self._theme
        self.fig, self.ax = plt.subplots(figsize=(4, 2.8), dpi=100)
        self.fig.patch.set_facecolor(t["bg"])

        # Embed in tkinter — caller is responsible for packing the widget.
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.get_tk_widget().configure(bg=t["bg"], highlightthickness=0, bd=0)

        self._style_axes()
        self.canvas.draw()
        # NOTE: do NOT call .pack() here — layout is the caller's responsibility.

    # ── Series management ─────────────────────────────────────────────────────

    def add_series(self, label: str, color: str | None = None) -> None:
        """Register a new named series.  No-op if label already exists.

        Call from the UI thread before the first append() for that label.
        color defaults to the next colour in _SERIES_PALETTE.
        """
        with self._lock:
            if label in self._series:
                return
            if color is None:
                idx = len(self._series) - 1          # "default" doesn't count
                color = _SERIES_PALETTE[idx % len(_SERIES_PALETTE)]
            self._series[label] = {"color": color, "data": deque(maxlen=self._maxlen)}

    def series_labels(self) -> list[str]:
        """Return all registered series labels (excluding 'default')."""
        with self._lock:
            return [k for k in self._series if k != "default"]

    # ── Theme helpers ─────────────────────────────────────────────────────────

    def _style_axes(self) -> None:
        """Apply current theme colours to axes decorations."""
        t = self._theme
        self.ax.set_facecolor(t["axes_bg"])
        self.ax.set_title(self.title,   fontsize=10, fontweight="bold", color=t["fg"])
        self.ax.set_ylabel(self.ylabel,  fontsize=8,  color=t["fg"])
        self.ax.tick_params(axis="both", labelsize=7, colors=t["tick"])
        self.ax.grid(True, color=t["grid"], linewidth=0.5, alpha=0.8)
        for spine in self.ax.spines.values():
            spine.set_edgecolor(t["spine"])
        self.ax.xaxis.label.set_color(t["fg"])
        self.ax.yaxis.label.set_color(t["fg"])
        self.fig.patch.set_facecolor(t["bg"])
        self.canvas.get_tk_widget().configure(bg=t["bg"], highlightthickness=0, bd=0)

    def _style_legend(self) -> None:
        """Show a legend only when more than one series has data."""
        # Count series that have at least one point (skip "default" if it's empty
        # and other named series are present)
        with self._lock:
            named = {k: v for k, v in self._series.items() if k != "default"}
        if not named:
            return   # single-series: no legend needed
        t = self._theme
        leg = self.ax.legend(
            fontsize=7,
            facecolor=t["axes_bg"],
            edgecolor=t["spine"],
            labelcolor=t["fg"],
            loc="upper left",
            framealpha=0.8,
        )
        if leg:
            for text in leg.get_texts():
                text.set_color(t["fg"])

    def apply_theme(self, theme: dict) -> None:
        """Switch to a new theme and redraw.  Call from UI thread."""
        self._theme = theme
        self.ax.clear()
        self._style_axes()
        with self._lock:
            series_snapshot = {k: list(v["data"]) for k, v in self._series.items()}
            colors          = {k: v["color"]       for k, v in self._series.items()}
        has_named = any(k != "default" for k in series_snapshot)
        any_plotted = False
        for label, data in series_snapshot.items():
            if not data:
                continue
            times, values = zip(*data)
            lbl = label if (has_named and label != "default") else None
            self.ax.plot(times, values, color=colors[label], linewidth=1.5, label=lbl)
            any_plotted = True
        if any_plotted and len(series_snapshot) > 1:
            if len(times) > 1:
                self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
                self.ax.xaxis.set_major_locator(mdates.AutoDateLocator())
                self.fig.autofmt_xdate(rotation=30)
            self._style_legend()
        elif any_plotted and len(times) > 1:
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
            self.ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            self.fig.autofmt_xdate(rotation=30)
        self.canvas.draw_idle()

    # ── Data ──────────────────────────────────────────────────────────────────

    def append(self, value: float, series: str = "default") -> None:
        """Append a new data point to the named series (thread-safe).

        series defaults to "default" for backwards-compatible single-series use.
        If the named series does not exist it is created with an auto colour.
        """
        with self._lock:
            if series not in self._series:
                idx = len(self._series) - 1
                color = _SERIES_PALETTE[idx % len(_SERIES_PALETTE)]
                self._series[series] = {"color": color, "data": deque(maxlen=self._maxlen)}
            self._series[series]["data"].append((datetime.now(), value))

    def redraw(self) -> None:
        """Redraw the chart from all series data.  Call from UI thread only."""
        with self._lock:
            series_snapshot = {k: list(v["data"]) for k, v in self._series.items()}
            colors          = {k: v["color"]       for k, v in self._series.items()}

        # Nothing to draw yet
        if not any(series_snapshot.values()):
            return

        t = self._theme
        self.ax.clear()
        self.ax.set_facecolor(t["axes_bg"])

        has_named = any(k != "default" for k in series_snapshot)
        last_times = None
        for label, data in series_snapshot.items():
            if not data:
                continue
            times, values = zip(*data)
            last_times = times
            lbl = label if (has_named and label != "default") else None
            self.ax.plot(times, values, color=colors[label], linewidth=1.5, label=lbl)

        self.ax.set_title(self.title,   fontsize=10, fontweight="bold", color=t["fg"])
        self.ax.set_ylabel(self.ylabel,  fontsize=8,  color=t["fg"])
        self.ax.tick_params(axis="both", labelsize=7, colors=t["tick"])
        self.ax.grid(True, color=t["grid"], linewidth=0.5, alpha=0.8)
        for spine in self.ax.spines.values():
            spine.set_edgecolor(t["spine"])
        self.fig.patch.set_facecolor(t["bg"])
        self.canvas.get_tk_widget().configure(bg=t["bg"])

        if last_times is not None and len(last_times) > 1:
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
            self.ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            self.fig.autofmt_xdate(rotation=30)

        if has_named:
            self._style_legend()

        self.canvas.draw_idle()

    def clear(self) -> None:
        """Clear all series data and reset the axes."""
        with self._lock:
            for s in self._series.values():
                s["data"].clear()
        self.ax.clear()
        self._style_axes()
        self.canvas.draw_idle()

    def latest(self, series: str = "default") -> float | None:
        """Return the most recent value for the named series, or None if empty."""
        with self._lock:
            s = self._series.get(series)
            return s["data"][-1][1] if s and s["data"] else None

    def resize_maxlen(self, new_maxlen: int) -> None:
        """Change the rolling-window size across all series.  Trims oldest data."""
        with self._lock:
            self._maxlen = new_maxlen
            for s in self._series.values():
                s["data"] = type(s["data"])(s["data"], maxlen=new_maxlen)
