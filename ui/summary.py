"""Summary panel for solarView.

Displays large numeric values for key metrics in a tkinter frame.
Tiles wrap onto additional rows when the window is too narrow to fit
them all on one line.  Supports dark and light themes via apply_theme().
"""

from __future__ import annotations

import tkinter as tk

from .charts import DARK_THEME, LIGHT_THEME

# Fixed tile dimensions (pixels).  All tiles are the same size so the
# wrapping arithmetic is trivial.
_TILE_W   = 100   # outer width  (frame + padx)
_TILE_H   = 72    # outer height (frame + pady)
_TILE_PAD = 6     # horizontal gap between tiles
_ROW_PAD  = 4     # vertical gap between rows


class SummaryPanel(tk.Frame):
    """A wrapping strip of metric tiles.

    Tiles are positioned with place() so they reflow onto new rows whenever
    the panel is narrower than the total tile width.  The panel height
    adjusts automatically to fit however many rows are needed.
    """

    def __init__(self, parent: tk.Widget, theme: dict | None = None, **kwargs):
        t = theme or DARK_THEME
        kwargs.setdefault("relief", tk.FLAT)
        kwargs.setdefault("bd", 0)
        kwargs["bg"] = t["bg"]
        super().__init__(parent, **kwargs)

        self._theme = t
        self._tiles:      dict[str, tk.Frame] = {}   # key → tile frame
        self._labels:     dict[str, tk.Label] = {}   # key → value label
        self._all_labels: list[tk.Label]      = []   # every label (bulk recolour)
        self._order:      list[str]           = []   # insertion order of keys

        # Don't let pack shrink us below the height we compute in _reflow
        self.pack_propagate(False)
        # Reflow whenever our width changes
        self.bind("<Configure>", self._on_configure)

    # ── Build ─────────────────────────────────────────────────────────────────

    def add_metric(self, key: str, label: str, unit: str, initial: str = "—") -> None:
        """Add a new tile.  Safe to call after initial layout (dynamic tiles)."""
        t = self._theme
        frame = tk.Frame(
            self,
            bg=t["axes_bg"],
            relief=tk.FLAT,
            bd=0,
            padx=8,
            pady=4,
            highlightbackground=t["spine"],
            highlightthickness=1,
            width=_TILE_W - _TILE_PAD,
            height=_TILE_H - _ROW_PAD,
        )
        frame.pack_propagate(False)   # honour explicit width/height
        self._tiles[key] = frame
        self._order.append(key)

        lbl_label = tk.Label(frame, text=label,
                             font=("Helvetica", 8, "bold"),
                             fg=t["tick"], bg=t["axes_bg"])
        lbl_label.pack()
        self._all_labels.append(lbl_label)

        lbl_value = tk.Label(frame, text=initial,
                             font=("Helvetica", 18, "bold"),
                             fg=t["fg"], bg=t["axes_bg"])
        lbl_value.pack()
        self._labels[key] = lbl_value
        self._all_labels.append(lbl_value)

        lbl_unit = tk.Label(frame, text=unit,
                            font=("Helvetica", 9),
                            fg=t["tick"], bg=t["axes_bg"])
        lbl_unit.pack()
        self._all_labels.append(lbl_unit)

        # Trigger an immediate reflow so the new tile appears in the right place
        self.after_idle(self._reflow)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _on_configure(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        """Re-place all tiles whenever the panel is resized."""
        self._reflow(event.width)

    def _reflow(self, panel_width: int | None = None) -> None:
        """Position every tile with place(), wrapping rows as needed.

        Computes how many tiles fit across the available width and places them
        in left-to-right, top-to-bottom order.  Then resizes the panel height
        to exactly fit the resulting rows.
        """
        if not self._order:
            return

        w = panel_width if panel_width and panel_width > 1 else self.winfo_width()
        if w <= 1:
            # Widget not yet mapped — defer until it is
            self.after(50, self._reflow)
            return

        step_x = _TILE_W + _TILE_PAD
        step_y = _TILE_H + _ROW_PAD

        tiles_per_row = max(1, w // step_x)

        x, y = _TILE_PAD, _ROW_PAD
        col = 0
        for key in self._order:
            frame = self._tiles.get(key)
            if frame is None:
                continue
            frame.place(x=x, y=y)
            col += 1
            if col >= tiles_per_row:
                col = 0
                x = _TILE_PAD
                y += step_y
            else:
                x += step_x

        # Number of complete rows (plus partial last row)
        n_tiles = len(self._order)
        n_rows  = max(1, (n_tiles + tiles_per_row - 1) // tiles_per_row)
        needed_h = n_rows * step_y + _ROW_PAD
        self.configure(height=needed_h)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def apply_theme(self, theme: dict) -> None:
        """Re-colour every tile and label.  Call from UI thread."""
        self._theme = theme
        t = theme
        self.configure(bg=t["bg"])
        for frame in self._tiles.values():
            frame.configure(
                bg=t["axes_bg"],
                highlightbackground=t["spine"],
            )
        for lbl in self._all_labels:
            font = lbl.cget("font")
            is_value = "18" in str(font)
            lbl.configure(
                bg=t["axes_bg"],
                fg=t["fg"] if is_value else t["tick"],
            )

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, key: str, value: float | str | None, unit: str = "") -> None:
        label = self._labels.get(key)
        if label is None:
            return

        if value is None:
            display = "—"
        elif isinstance(value, float):
            if abs(value) >= 1000:
                display = f"{value:,.0f}"
            elif abs(value) >= 100:
                display = f"{value:.0f}"
            else:
                display = f"{value:.1f}"
        else:
            display = str(value)

        label.config(text=display)

    def update_text(self, key: str, text: str) -> None:
        """Set a tile's value label to an arbitrary string (no number formatting).

        Uses a smaller font than numeric tiles so longer words fit cleanly.
        """
        label = self._labels.get(key)
        if label is None:
            return
        label.config(text=text, font=("Helvetica", 14, "bold"))
