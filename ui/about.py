"""Animated About dialog for solarView.

Canvas animation: orbiting solar particles around a pulsing sun core,
rendered on a tkinter Canvas with a 30 ms timer.  Pure stdlib — no external
animation packages required.
"""

from __future__ import annotations

import math
import os
import tkinter as tk

__version__ = "1.0.0"

# ── Particle definitions ───────────────────────────────────────────────────────
# (color, phase_offset, orbit_radius_x, orbit_radius_y, dot_radius)
_ORBS: list[tuple[str, float, float, float, int]] = [
    ("#FFD700", 0.00, 80, 32, 7),   # gold   — large inner orbit
    ("#FF6A00", 1.05, 80, 32, 5),   # orange
    ("#3b82d4", 2.10, 80, 32, 5),   # blue
    ("#10b981", 3.14, 80, 32, 5),   # green  — battery colour
    ("#f59e0b", 4.19, 80, 32, 5),   # amber
    ("#8b5cf6", 5.24, 80, 32, 5),   # purple — frequency colour
    ("#FFD700", 0.52, 115, 46, 4),  # outer orbit
    ("#3b82d4", 1.90, 115, 46, 4),
    ("#10b981", 3.40, 115, 46, 4),
    ("#FF6A00", 4.80, 115, 46, 3),
]

_BG       = "#0d1117"
_SUN_CORE = "#FFD700"
_SUN_GLOW = "#FF8C00"


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _blend(color: str, alpha: float) -> str:
    """Blend a hex color toward _BG by alpha (0=bg, 1=full color)."""
    r1, g1, b1 = _hex_to_rgb(_BG)
    r2, g2, b2 = _hex_to_rgb(color)
    r = int(r1 + (r2 - r1) * alpha)
    g = int(g1 + (g2 - g1) * alpha)
    b = int(b1 + (b2 - b1) * alpha)
    return f"#{r:02x}{g:02x}{b:02x}"


class _AnimCanvas(tk.Canvas):
    """Draws the animated solar system scene."""

    _W = 460
    _H = 180

    def __init__(self, parent: tk.Widget):
        super().__init__(
            parent,
            width=self._W,
            height=self._H,
            bg=_BG,
            highlightthickness=0,
            bd=0,
        )
        self._tick  = 0.0
        self._items: list[int] = []
        self._after_id: str | None = None
        self._step()

    def _step(self) -> None:
        self._tick += 0.035
        self._draw()
        self._after_id = self.after(30, self._step)

    def stop(self) -> None:
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None

    def _draw(self) -> None:
        self.delete("all")
        cx = self._W / 2
        cy = self._H / 2
        t  = self._tick

        # ── Background star-field (static but randomised by position hash) ───
        for i in range(28):
            sx = (i * 137 + 23)  % self._W
            sy = (i * 97  + 41)  % self._H
            twinkle = 0.3 + 0.7 * abs(math.sin(t * 0.7 + i * 0.9))
            sc = _blend("#ffffff", twinkle * 0.6)
            self.create_oval(sx - 1, sy - 1, sx + 1, sy + 1, fill=sc, outline="")

        # ── Pulsing sun glow rings ────────────────────────────────────────────
        pulse = 0.55 + 0.45 * math.sin(t * 1.8)
        for radius, base_alpha in [(52, 0.18), (38, 0.30), (26, 0.50)]:
            r = int(radius * (0.9 + 0.1 * pulse))
            col = _blend(_SUN_GLOW, base_alpha * pulse)
            self.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                fill=col, outline=""
            )

        # ── Sun core ─────────────────────────────────────────────────────────
        core_r = int(13 + 2 * pulse)
        self.create_oval(
            cx - core_r, cy - core_r, cx + core_r, cy + core_r,
            fill=_SUN_CORE, outline=_blend("#ffffff", 0.4 * pulse), width=1,
        )

        # ── Orbit ellipse guide lines ─────────────────────────────────────────
        for orx, ory in [(80, 32), (115, 46)]:
            self.create_oval(
                cx - orx, cy - ory, cx + orx, cy + ory,
                outline=_blend("#444466", 0.6), width=1, fill="",
            )

        # ── Orbiting particles ────────────────────────────────────────────────
        for color, phase, orx, ory, dr in _ORBS:
            angle = t + phase
            px = cx + orx * math.cos(angle)
            py = cy + ory * math.sin(angle)

            # glow halo
            gr = dr * 3
            gc = _blend(color, 0.25)
            self.create_oval(
                px - gr, py - gr, px + gr, py + gr,
                fill=gc, outline=""
            )
            # bright dot
            self.create_oval(
                px - dr, py - dr, px + dr, py + dr,
                fill=color, outline=_blend("#ffffff", 0.3), width=1,
            )

        # ── "solarView" title text with colour-shift ──────────────────────────
        hue_r = int(180 + 75 * math.sin(t * 0.9))
        hue_g = int(160 + 60 * math.sin(t * 0.9 + 1.0))
        title_col = f"#{hue_r:02x}{hue_g:02x}20"

        self.create_text(
            cx, cy - 68,
            text="solarView",
            font=("Helvetica", 22, "bold"),
            fill=title_col,
        )


# ── Markdown renderer ──────────────────────────────────────────────────────────

import re as _re

def _render_markdown(widget: tk.Text, content: str, theme: dict) -> None:
    """Render a markdown string into a tk.Text widget using tag-based styling.

    Supports: H1–H3, bold, inline code, code blocks, bullet lists,
    numbered lists, horizontal rules, blockquotes, tables, and plain text.
    Bold and inline-code are applied inline within the same paragraph line.
    """
    t = theme
    is_dark = t["bg"] == "#1e1e2e" or t["bg"].startswith("#0") or t["bg"] < "#888888"

    # Colour palette tuned for dark/light
    accent      = "#FFD700"
    h1_col      = "#FFD700"
    h2_col      = "#3b82d4"
    h3_col      = "#10b981"
    code_fg     = "#f59e0b" if is_dark else "#c7253e"
    code_bg     = "#1a1a2e" if is_dark else "#f0f0f8"
    rule_col    = "#444466" if is_dark else "#ccccdd"
    quote_col   = "#8b5cf6"
    quote_bg    = "#1a1230" if is_dark else "#f5f0ff"
    table_head  = "#3b82d4"
    table_bg    = "#16213e" if is_dark else "#f0f5ff"
    muted       = t["tick"]
    normal_fg   = t["fg"]
    normal_bg   = t["axes_bg"]

    mono = "Menlo" if os.path.exists("/System/Library/Fonts/Menlo.ttc") else "Courier"

    # ── Configure tags ────────────────────────────────────────────────────────
    widget.tag_configure("h1",      font=("Helvetica", 20, "bold"), foreground=h1_col,
                         spacing1=14, spacing3=4, background=normal_bg)
    widget.tag_configure("h2",      font=("Helvetica", 16, "bold"), foreground=h2_col,
                         spacing1=10, spacing3=2, background=normal_bg)
    widget.tag_configure("h3",      font=("Helvetica", 13, "bold"), foreground=h3_col,
                         spacing1=8,  spacing3=2, background=normal_bg)
    widget.tag_configure("bold",    font=("Helvetica", 11, "bold"), foreground=normal_fg,
                         background=normal_bg)
    widget.tag_configure("code_inline", font=(mono, 10), foreground=code_fg,
                         background=code_bg)
    widget.tag_configure("code_block",  font=(mono, 10), foreground=code_fg,
                         background=code_bg, lmargin1=16, lmargin2=16,
                         spacing1=2, spacing3=2)
    widget.tag_configure("bullet",  font=("Helvetica", 11), foreground=normal_fg,
                         lmargin1=16, lmargin2=28, background=normal_bg)
    widget.tag_configure("bullet_accent", font=("Helvetica", 11, "bold"),
                         foreground=accent, background=normal_bg)
    widget.tag_configure("numbered",font=("Helvetica", 11), foreground=normal_fg,
                         lmargin1=16, lmargin2=32, background=normal_bg)
    widget.tag_configure("rule",    font=("Helvetica", 3),  foreground=rule_col,
                         background=rule_col, spacing1=6, spacing3=6)
    widget.tag_configure("quote",   font=("Helvetica", 11, "italic"), foreground=quote_col,
                         background=quote_bg, lmargin1=20, lmargin2=20,
                         spacing1=2, spacing3=2)
    widget.tag_configure("table_head", font=("Helvetica", 10, "bold"), foreground=table_head,
                         background=table_bg)
    widget.tag_configure("table_row",  font=(mono, 10), foreground=normal_fg,
                         background=normal_bg)
    widget.tag_configure("table_sep",  font=("Helvetica", 3), foreground=rule_col,
                         background=rule_col)
    widget.tag_configure("normal",  font=("Helvetica", 11), foreground=normal_fg,
                         background=normal_bg, spacing1=1)
    widget.tag_configure("muted",   font=("Helvetica", 10), foreground=muted,
                         background=normal_bg)
    widget.tag_configure("badge",   font=("Helvetica", 9,  "bold"), foreground=accent,
                         background=code_bg)

    def _insert_inline(line: str, base_tag: str) -> None:
        """Insert a line applying bold (**text**) and `code` inline tags."""
        # Pattern: **bold**, `code`, or plain text
        pattern = _re.compile(r'(\*\*(.+?)\*\*|`([^`]+)`)')
        pos = 0
        for m in pattern.finditer(line):
            # Plain text before match
            if m.start() > pos:
                widget.insert(tk.END, line[pos:m.start()], base_tag)
            if m.group(0).startswith("**"):
                widget.insert(tk.END, m.group(2), "bold")
            else:
                widget.insert(tk.END, m.group(3), "code_inline")
            pos = m.end()
        if pos < len(line):
            widget.insert(tk.END, line[pos:], base_tag)

    lines = content.splitlines()
    in_code_block = False
    code_buf: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # ── Fenced code block ─────────────────────────────────────────────────
        if line.strip().startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_buf = []
            else:
                in_code_block = False
                block_text = "\n".join(code_buf)
                widget.insert(tk.END, block_text + "\n", "code_block")
            i += 1
            continue
        if in_code_block:
            code_buf.append(line)
            i += 1
            continue

        # ── Horizontal rule ───────────────────────────────────────────────────
        if _re.match(r'^[-*_]{3,}\s*$', line):
            widget.insert(tk.END, "─" * 72 + "\n", "rule")
            i += 1
            continue

        # ── Headings ──────────────────────────────────────────────────────────
        m = _re.match(r'^(#{1,3})\s+(.*)', line)
        if m:
            level = len(m.group(1))
            text  = _re.sub(r'[`*_]', '', m.group(2))  # strip inline marks
            tag   = f"h{level}"
            widget.insert(tk.END, text + "\n", tag)
            i += 1
            continue

        # ── Badge lines (![...] links — strip them, show as muted) ───────────
        if line.strip().startswith("!["):
            stripped = _re.sub(r'!\[.*?\]\(.*?\)', '', line).strip()
            if stripped:
                widget.insert(tk.END, stripped + "\n", "muted")
            i += 1
            continue

        # ── Blockquote ────────────────────────────────────────────────────────
        if line.startswith("> "):
            widget.insert(tk.END, "  " + line[2:] + "\n", "quote")
            i += 1
            continue

        # ── Table ─────────────────────────────────────────────────────────────
        if "|" in line and i + 1 < len(lines) and _re.match(r'^[\s|:-]+$', lines[i + 1]):
            # Header row
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            widget.insert(tk.END, "  " + "   ".join(cells) + "\n", "table_head")
            widget.insert(tk.END, "─" * 72 + "\n", "table_sep")
            i += 2  # skip separator line
            # Data rows
            while i < len(lines) and "|" in lines[i]:
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                widget.insert(tk.END, "  " + "   ".join(cells) + "\n", "table_row")
                i += 1
            widget.insert(tk.END, "\n", "normal")
            continue

        # ── Bullet list ───────────────────────────────────────────────────────
        m = _re.match(r'^(\s*)[-*+]\s+(.*)', line)
        if m:
            widget.insert(tk.END, "  • ", "bullet_accent")
            _insert_inline(m.group(2), "bullet")
            widget.insert(tk.END, "\n", "bullet")
            i += 1
            continue

        # ── Numbered list ─────────────────────────────────────────────────────
        m = _re.match(r'^(\s*)\d+\.\s+(.*)', line)
        if m:
            num_m = _re.match(r'^(\s*)(\d+)\.\s+(.*)', line)
            widget.insert(tk.END, f"  {num_m.group(2)}. ", "bullet_accent")
            _insert_inline(num_m.group(3), "numbered")
            widget.insert(tk.END, "\n", "numbered")
            i += 1
            continue

        # ── Empty line ────────────────────────────────────────────────────────
        if line.strip() == "":
            widget.insert(tk.END, "\n", "normal")
            i += 1
            continue

        # ── Normal paragraph line ─────────────────────────────────────────────
        _insert_inline(line, "normal")
        widget.insert(tk.END, "\n", "normal")
        i += 1


# ── Readme viewer ──────────────────────────────────────────────────────────────

class _ReadmeWindow(tk.Toplevel):
    """Scrollable markdown-rendered README viewer."""

    def __init__(self, parent: tk.Widget, readme_path: str, theme: dict):
        super().__init__(parent)
        self.title("solarView — README")
        self.resizable(True, True)
        self.grab_set()
        self.transient(parent)
        t = theme

        self.configure(bg=t["bg"])
        self.geometry("860x680")

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

        # Scrollable text area — no toolbar
        frame = tk.Frame(self, bg=t["bg"])
        frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        scrollbar = tk.Scrollbar(frame, bg=t["axes_bg"], troughcolor=t["bg"],
                                 relief=tk.FLAT, bd=0)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        text = tk.Text(
            frame,
            wrap=tk.WORD,
            bg=t["axes_bg"],
            fg=t["fg"],
            insertbackground=t["fg"],
            selectbackground=t["grid"],
            font=("Helvetica", 11),
            relief=tk.FLAT,
            bd=0,
            padx=20,
            pady=14,
            yscrollcommand=scrollbar.set,
            cursor="arrow",
            spacing2=2,
        )
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=text.yview)

        if os.path.exists(readme_path):
            with open(readme_path, encoding="utf-8") as f:
                content = f.read()
        else:
            content = f"# README not found\n\nExpected at:\n`{readme_path}`\n"

        _render_markdown(text, content, t)
        text.config(state=tk.DISABLED)

        # Close button at bottom
        btn_bar = tk.Frame(self, bg=t["bg"])
        btn_bar.pack(fill=tk.X, padx=16, pady=(0, 12))
        tk.Button(
            btn_bar, text="Close",
            command=self.destroy,
            bg=t["axes_bg"], fg=t["fg"],
            activebackground=t["grid"], activeforeground=t["fg"],
            relief=tk.FLAT, bd=0, padx=20, pady=6,
            font=("Helvetica", 11), cursor="hand2",
        ).pack(side=tk.RIGHT)


# ── About dialog ───────────────────────────────────────────────────────────────

class AboutDialog(tk.Toplevel):
    """Animated About dialog for solarView."""

    def __init__(self, parent: tk.Widget, theme: dict, readme_path: str = ""):
        super().__init__(parent)
        self.title("About solarView")
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self.configure(bg=_BG)

        self._theme  = theme
        self._readme = readme_path
        self._canvas: _AnimCanvas | None = None

        self._build()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        outer = tk.Frame(self, bg=_BG, padx=20, pady=16)
        outer.pack(fill=tk.BOTH, expand=True)

        # ── Animated canvas ───────────────────────────────────────────────────
        self._canvas = _AnimCanvas(outer)
        self._canvas.pack()

        # ── Version badge ─────────────────────────────────────────────────────
        ver_frame = tk.Frame(outer, bg=_BG)
        ver_frame.pack(pady=(6, 2))

        tk.Label(
            ver_frame,
            text=f"v{__version__}",
            font=("Helvetica", 15, "bold"),
            fg="#FFD700",
            bg="#1a1200",
            relief=tk.FLAT,
            padx=14, pady=3,
        ).pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(
            ver_frame,
            text="☀️  First Release",
            font=("Helvetica", 11, "bold"),
            fg="#10b981",
            bg="#001a0d",
            relief=tk.FLAT,
            padx=10, pady=3,
        ).pack(side=tk.LEFT)

        # ── Tagline ───────────────────────────────────────────────────────────
        tk.Label(
            outer,
            text="Real-time SolarEdge inverter & battery monitoring",
            font=("Helvetica", 11),
            fg="#9ca3af",
            bg=_BG,
        ).pack(pady=(4, 0))

        # ── Divider ───────────────────────────────────────────────────────────
        tk.Frame(outer, bg="#1e2030", height=1).pack(fill=tk.X, pady=10)

        # ── Credits ───────────────────────────────────────────────────────────
        cred_frame = tk.Frame(outer, bg=_BG)
        cred_frame.pack()

        tk.Label(
            cred_frame,
            text="From the minds of",
            font=("Helvetica", 12),
            fg="#cccccc",
            bg=_BG,
        ).pack()

        names_frame = tk.Frame(cred_frame, bg=_BG)
        names_frame.pack(pady=2)

        tk.Label(
            names_frame,
            text="IBM Bob",
            font=("Helvetica", 16, "bold"),
            fg="#FF6A00",
            bg=_BG,
        ).pack(side=tk.LEFT, padx=4)

        tk.Label(
            names_frame,
            text="&",
            font=("Helvetica", 14),
            fg="#666666",
            bg=_BG,
        ).pack(side=tk.LEFT, padx=4)

        tk.Label(
            names_frame,
            text="Daneyand",
            font=("Helvetica", 16, "bold"),
            fg="#3b82d4",
            bg=_BG,
        ).pack(side=tk.LEFT, padx=4)

        # ── Platform badges ───────────────────────────────────────────────────
        badge_frame = tk.Frame(outer, bg=_BG)
        badge_frame.pack(pady=(10, 6))

        for label_text, fg_col, bg_col in [
            ("🍎 macOS",   "#FF6A00", "#1a0a00"),
            ("🐧 Linux",   "#3b82d4", "#00081a"),
            ("🪟 Windows", "#10b981", "#001a0d"),
        ]:
            tk.Label(
                badge_frame,
                text=label_text,
                font=("Helvetica", 10, "bold"),
                fg=fg_col,
                bg=bg_col,
                relief=tk.FLAT,
                padx=8, pady=2,
            ).pack(side=tk.LEFT, padx=5)

        # ── Divider ───────────────────────────────────────────────────────────
        tk.Frame(outer, bg="#1e2030", height=1).pack(fill=tk.X, pady=10)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = tk.Frame(outer, bg=_BG)
        btn_frame.pack()

        _btn_style = dict(
            font=("Helvetica", 11),
            relief=tk.FLAT,
            bd=0,
            padx=16, pady=6,
            cursor="hand2",
        )

        tk.Button(
            btn_frame,
            text="📖  View README",
            command=self._open_readme,
            bg="#1e2a3a",
            fg="#3b82d4",
            activebackground="#2a3a4a",
            activeforeground="#6ab0f5",
            **_btn_style,
        ).pack(side=tk.LEFT, padx=8)

        tk.Button(
            btn_frame,
            text="Close",
            command=self._close,
            bg="#1e1e2e",
            fg="#9ca3af",
            activebackground="#2a2a3e",
            activeforeground="#cdd6f4",
            **_btn_style,
        ).pack(side=tk.LEFT, padx=8)

    def _open_readme(self) -> None:
        _ReadmeWindow(self, self._readme, self._theme)

    def _close(self) -> None:
        if self._canvas:
            self._canvas.stop()
        self.destroy()
