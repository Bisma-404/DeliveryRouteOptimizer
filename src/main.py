"""Command-line entry point for the web application and benchmark suite."""

import os
import sys
import argparse
import logging

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


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
        description="Delivery Route Optimizer web application for Karachi"
    )
    parser.add_argument(
        "--experiment",
        action="store_true",
        help="Run standalone benchmark experiment suite instead of the web application."
    )
    parser.add_argument(
        "--instances",
        type=int,
        default=10,
        help="Number of test instances for experiment (default: 10)."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Web server interface (default: localhost).")
    parser.add_argument("--port", type=int, default=5000, help="Web server port (default: 5000).")
    args = parser.parse_args()

    if args.experiment:
        import experiment_runner
        print("\n=== Running Standalone Benchmark Experiment ===")
        experiment_runner.run_experiments(num_instances=args.instances)
        print("=== Benchmark Finished Successfully ===\n")
        return

    from src.webapp import create_app

    app = create_app()
    logging.getLogger(__name__).info("Starting Route Desk at http://%s:%d", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=False, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
