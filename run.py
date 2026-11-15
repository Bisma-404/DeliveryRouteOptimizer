"""
Delivery Route Optimizer — Root Launcher
=========================================
Run from the project root:
    python run.py

Do NOT run from inside src/ — relative imports won't resolve.
"""

from __future__ import annotations
import os
import sys
import tempfile
import logging
import tkinter as tk

# ── Matplotlib config (must be set before ANY matplotlib import) ───────────────
os.environ.setdefault(
    "MPLCONFIGDIR",
    os.path.join(tempfile.gettempdir(), "dro_mpl_cache")
)

# ── Project root on sys.path ──────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("run")


def main() -> None:
    """Launch the full-screen Delivery Route Optimizer GUI."""
    logger.info("Starting Delivery Route Optimizer — Fleet Logistics Edition")
    logger.info("Project root: %s", PROJECT_ROOT)

    from src.gui.app import DeliveryRouteOptimizerApp

    root = tk.Tk()
    _app = DeliveryRouteOptimizerApp(root)
    root.mainloop()
    logger.info("Application closed normally.")


if __name__ == "__main__":
    main()
