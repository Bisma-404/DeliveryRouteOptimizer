"""
Delivery Route Optimizer — Flask Launcher
==========================================
Run from the project root:
    python run.py
"""

from __future__ import annotations
import argparse
import logging
import os
import sys

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
    """Launch the local browser-based Delivery Route Optimizer."""
    parser = argparse.ArgumentParser(description="Delivery Route Optimizer web application")
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind (default: localhost).")
    parser.add_argument("--port", type=int, default=5000, help="HTTP port (default: 5000).")
    args = parser.parse_args()

    from src.webapp import create_app

    app = create_app()
    logger.info("Starting Route Desk at http://%s:%d", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=False, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
