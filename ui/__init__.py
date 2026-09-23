"""solarView UI package — tkinter + matplotlib desktop interface."""

from .dashboard import Dashboard
from .charts import LiveChart
from .summary import SummaryPanel

__all__ = ["Dashboard", "LiveChart", "SummaryPanel"]
