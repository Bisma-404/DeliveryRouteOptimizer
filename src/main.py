"""Main entry point for Delivery Route Optimizer.

Launches the Tkinter GUI application or executes CLI benchmarks.
"""

import os
import sys
import argparse
import tempfile
import logging
import tkinter as tk

# Set writable Matplotlib config directory before importing matplotlib
os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "delivery_route_mpl"))

# Ensure project root is on sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.gui.app import DeliveryRouteOptimizerApp


def setup_logging():
    """Configure structured console logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )


def main():
    """Parse CLI arguments and start application."""
    setup_logging()

    parser = argparse.ArgumentParser(
        description="Delivery Route Optimizer on a Real City Map (Karachi)"
    )
    parser.add_argument(
        "--experiment",
        action="store_true",
        help="Run standalone benchmark experiment suite without launching GUI."
    )
    parser.add_argument(
        "--instances",
        type=int,
        default=10,
        help="Number of test instances for experiment (default: 10)."
    )
    args = parser.parse_args()

    if args.experiment:
        import experiment_runner
        print("\n=== Running Standalone Benchmark Experiment ===")
        experiment_runner.run_experiments(num_instances=args.instances)
        print("=== Benchmark Finished Successfully ===\n")
        return

    # Start Tkinter GUI
    root = tk.Tk()
    app = DeliveryRouteOptimizerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
