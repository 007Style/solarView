#!/usr/bin/env python3
"""solarView — Real-time SolarEdge inverter monitoring desktop app.

Reads Modbus TCP data from SolarEdge inverters and LG RESU batteries,
displays it in live-updating charts. No historical persistence.

Usage:
    python main.py
    python main.py --config /path/to/config.yaml
"""

from __future__ import annotations

import argparse
import os
import sys
import yaml

_USER_CONFIG_PATH = os.path.expanduser("~/.solarview/config.yaml")

# Ensure the package can be imported when running directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from solaredge_modbus import SolarEdgeClient
from ui.dashboard import Dashboard, ModbusManager


def load_config(config_path: str | None = None) -> dict:
    """Load configuration, merging user overrides with defaults.

    Config locations checked (in order, overrides earlier):
      1. Bundled default (config/default.yaml)
      2. ~/.solarview/config.yaml (user-level)
      3. --config <path> (explicit override)
    """
    config: dict = {}

    # Load bundled default
    default_path = os.path.join(os.path.dirname(__file__), "config", "default.yaml")
    if os.path.exists(default_path):
        with open(default_path) as f:
            config.update(yaml.safe_load(f) or {})

    # Load user-level config
    if os.path.exists(_USER_CONFIG_PATH):
        with open(_USER_CONFIG_PATH) as f:
            config.update(yaml.safe_load(f) or {})

    # Load explicit override
    if config_path and os.path.exists(config_path):
        with open(config_path) as f:
            config.update(yaml.safe_load(f) or {})

    return config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="solarView — Real-time SolarEdge monitoring",
        prog="solarView",
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to an optional YAML config file (overrides defaults)",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    # Create the modbus manager
    manager = ModbusManager(config)

    # Create and run the dashboard
    dashboard = Dashboard(manager, config)

    # Run the UI — blocks until quit() is called from _on_closing
    dashboard.mainloop()

    # Persist ui.window_geometry (and any other live changes) to user config
    _save_user_config(config)

    # mainloop() returned cleanly — force process exit so the Dock icon disappears
    sys.exit(0)


def _save_user_config(config: dict) -> None:
    """Persist all live config changes to ~/.solarview/config.yaml.

    Saves: window geometry, connection settings, log settings, chart window.
    Merges into any existing user config file so unrecognised keys are preserved.
    """
    try:
        # Load existing user config (if any) so we don't clobber unknown keys
        existing: dict = {}
        if os.path.exists(_USER_CONFIG_PATH):
            with open(_USER_CONFIG_PATH) as f:
                existing = yaml.safe_load(f) or {}

        # ── ui section ────────────────────────────────────────────────────────
        ui = config.get("ui", {})
        ex_ui = existing.setdefault("ui", {})
        geo = ui.get("window_geometry", "")
        if geo:
            ex_ui["window_geometry"] = geo
        for key in ("theme", "chart_window_hours", "poll_interval_seconds",
                    "refresh_interval_ms"):
            if key in ui:
                ex_ui[key] = ui[key]

        # ── inverter section ─────────────────────────────────────────────────
        inv = config.get("inverter", {})
        if inv:
            ex_inv = existing.setdefault("inverter", {})
            for key in ("host", "port", "timeout"):
                if key in inv:
                    ex_inv[key] = inv[key]

        # ── logging section ──────────────────────────────────────────────────
        log = config.get("logging", {})
        if log:
            ex_log = existing.setdefault("logging", {})
            for key in ("directory", "enabled", "run_log_enabled"):
                if key in log:
                    ex_log[key] = log[key]

        os.makedirs(os.path.dirname(_USER_CONFIG_PATH), exist_ok=True)
        with open(_USER_CONFIG_PATH, "w") as f:
            yaml.dump(existing, f, default_flow_style=False, allow_unicode=True)
        print(f"[main] User config saved: {_USER_CONFIG_PATH}")
    except Exception as e:
        print(f"[main] Could not save user config: {e}")


if __name__ == "__main__":
    main()
