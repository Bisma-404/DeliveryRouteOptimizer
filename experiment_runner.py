"""Standalone Experiment Runner for Delivery Route Optimizer.

Executes a rigorous benchmark comparing 4 optimization algorithms:
    1. Nearest Neighbor (Greedy Baseline)
    2. Hill Climbing (2-opt Local Search)
    3. Simulated Annealing (Stochastic Exploration)
    4. Genetic Algorithm (Evolutionary Permutation Search)

Evaluates on 10 random problem instances with fixed seed 42.
Saves outputs to:
    - outputs/results/results.csv
    - outputs/results/summary_metrics.csv
Generates 4 publication-quality Matplotlib figures in outputs/figures/:
    1. 1_avg_route_length.png
    2. 2_avg_runtime.png
    3. 3_convergence_sa_ga.png
    4. 4_pct_improvement_vs_nn.png
"""

import os
import sys
import random
import tempfile
import logging
from typing import List, Dict, Any, Tuple
import numpy as np
import pandas as pd

# Direct Matplotlib to a writable temporary directory
os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "delivery_route_mpl"))
import matplotlib
matplotlib.use("Agg")  # Non-interactive headless backend for automated chart generation
import matplotlib.pyplot as plt

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.data.graph_loader import GraphLoader
from src.data.stop_generator import StopGenerator
from src.core.astar import AStarPlanner
from src.core.problem import RouteProblem
from src.core.solvers import (
    NearestNeighborSolver,
    HillClimbSolver,
    SimulatedAnnealingSolver,
    GeneticSolver
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("ExperimentRunner")


def run_experiments(
    num_instances: int = 10,
    stops_per_instance: int = 15,
    master_seed: int = 42
) -> Tuple[pd.DataFrame, List[str]]:
    """Run full benchmark experiment suite.

    Args:
        num_instances: Number of problem instances to evaluate (default: 10).
        stops_per_instance: Number of stops in each instance (default: 15).
        master_seed: Global random seed for reproducibility (default: 42).

    Returns:
        Tuple[pd.DataFrame, List[str]]:
            - results_df: Detailed results DataFrame.
            - figure_paths: List of absolute filepaths of generated charts.
    """
    # Set global seeds
    random.seed(master_seed)
    np.random.seed(master_seed)

    # Directories
    results_dir = os.path.join(project_root, "outputs", "results")
    figures_dir = os.path.join(project_root, "outputs", "figures")
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(figures_dir, exist_ok=True)

    logger.info("Initializing GraphLoader for Karachi road network...")
    graph_loader = GraphLoader("Karachi")
    G = graph_loader.load_graph()
    planner = AStarPlanner(G)
    stop_gen = StopGenerator(graph_loader)

    records: List[Dict[str, Any]] = []

    # Store sample convergence traces for plotting Figure 3
    sample_sa_history: List[float] = []
    sample_ga_history: List[float] = []

    solver_classes = [
        ("Nearest Neighbor", NearestNeighborSolver),
        ("Hill Climbing", HillClimbSolver),
        ("Simulated Annealing", SimulatedAnnealingSolver),
        ("Genetic Algorithm", GeneticSolver)
    ]

    logger.info(
        "Starting benchmark across %d instances (%d stops each, seed=%d)...",
        num_instances, stops_per_instance, master_seed
    )

    for inst_idx in range(1, num_instances + 1):
        # Deterministic per-instance seed
        inst_seed = master_seed + (inst_idx * 17)

        # Generate stops for this instance
        stops = stop_gen.generate_stops(num_stops=stops_per_instance, seed=inst_seed)

        # Build distance matrix with A*
        dist_matrix, detailed_paths, nodes_expanded = planner.build_distance_matrix(stops)
        problem = RouteProblem(stops, dist_matrix, depot=0)

        # Run Nearest Neighbor first to establish baseline
        nn_solver = NearestNeighborSolver(problem, seed=inst_seed)
        nn_tour, nn_cost, _, nn_time = nn_solver.solve()

        logger.info(
            "Instance %02d/%02d | NN Baseline: %.2f km in %.4fs (A* Nodes: %d)",
            inst_idx, num_instances, nn_cost, nn_time, nodes_expanded
        )

        for solver_name, SolverClass in solver_classes:
            solver = SolverClass(problem, seed=inst_seed)
            tour, cost, history, runtime = solver.solve()

            # Calculate improvement percentage over NN baseline
            # Positive % means shorter / superior route than NN
            improvement_pct = ((nn_cost - cost) / nn_cost) * 100.0

            records.append({
                "instance_id": inst_idx,
                "instance_seed": inst_seed,
                "stops_count": stops_per_instance,
                "solver": solver_name,
                "route_length_km": round(cost, 3),
                "runtime_seconds": round(runtime, 5),
                "astar_nodes_expanded": nodes_expanded,
                "improvement_vs_nn_pct": round(improvement_pct, 2),
                "tour_valid": problem.validate_tour(tour)
            })

            # Save representative convergence trace from instance 1
            if inst_idx == 1:
                if solver_name == "Simulated Annealing":
                    sample_sa_history = list(history)
                elif solver_name == "Genetic Algorithm":
                    sample_ga_history = list(history)

    df_results = pd.DataFrame(records)

    # Save detailed results CSV
    results_csv_path = os.path.join(results_dir, "results.csv")
    df_results.to_csv(results_csv_path, index=False)
    logger.info("Saved detailed results to: %s", results_csv_path)

    # Compute and save summary metrics
    summary_df = df_results.groupby("solver").agg(
        mean_length_km=("route_length_km", "mean"),
        std_length_km=("route_length_km", "std"),
        min_length_km=("route_length_km", "min"),
        mean_runtime_s=("runtime_seconds", "mean"),
        std_runtime_s=("runtime_seconds", "std"),
        mean_improvement_pct=("improvement_vs_nn_pct", "mean"),
        max_improvement_pct=("improvement_vs_nn_pct", "max")
    ).reset_index()

    # Reorder rows logically
    solver_order = ["Nearest Neighbor", "Hill Climbing", "Simulated Annealing", "Genetic Algorithm"]
    summary_df["order"] = summary_df["solver"].map(lambda s: solver_order.index(s) if s in solver_order else 99)
    summary_df = summary_df.sort_values("order").drop(columns=["order"])

    summary_csv_path = os.path.join(results_dir, "summary_metrics.csv")
    summary_df.to_csv(summary_csv_path, index=False)
    logger.info("Saved summary metrics to: %s", summary_csv_path)

    # Print summary table to console
    print("\n" + "=" * 80)
    print("                  BENCHMARK EXPERIMENT RESULTS SUMMARY (N=10)                  ")
    print("=" * 80)
    print(summary_df.to_string(index=False))
    print("=" * 80 + "\n")

    # Generate the 4 required figures
    figure_paths = generate_figures(df_results, summary_df, sample_sa_history, sample_ga_history, figures_dir)

    return df_results, figure_paths


def generate_figures(
    df: pd.DataFrame,
    summary_df: pd.DataFrame,
    sa_history: List[float],
    ga_history: List[float],
    figures_dir: str
) -> List[str]:
    """Generate and save the 4 required experimental Matplotlib figures.

    1. Avg Route Length
    2. Avg Runtime
    3. Convergence (SA & GA)
    4. % Improvement vs NN baseline
    """
    fig_paths: List[str] = []

    # Styling settings
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "figure.titlesize": 14,
        "figure.dpi": 300
    })

    colors = ["#4A90E2", "#50E3C2", "#F5A623", "#9013FE"]
    solvers = summary_df["solver"].tolist()

    # -------------------------------------------------------------
    # Figure 1: Average Route Length (km)
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(
        solvers,
        summary_df["mean_length_km"],
        yerr=summary_df["std_length_km"],
        capsize=6,
        color=colors,
        edgecolor="#333333",
        linewidth=1.2,
        alpha=0.9
    )
    ax.set_ylabel("Total Route Length (km)")
    ax.set_title("Average Delivery Route Length Across 10 Instances\n(Lower is Better)", fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.6)

    # Annotate value labels
    for bar in bars:
        height = bar.get_height()
        ax.annotate(
            f"{height:.2f} km",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 7),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontweight="bold"
        )

    plt.tight_layout()
    f1_path = os.path.join(figures_dir, "1_avg_route_length.png")
    fig.savefig(f1_path, dpi=300)
    plt.close(fig)
    fig_paths.append(f1_path)
    logger.info("Generated Figure 1: %s", f1_path)

    # -------------------------------------------------------------
    # Figure 2: Average Runtime (seconds)
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5))
    runtimes = summary_df["mean_runtime_s"].tolist()

    bars = ax.bar(
        solvers,
        runtimes,
        color=colors,
        edgecolor="#333333",
        linewidth=1.2,
        alpha=0.9
    )
    ax.set_ylabel("Execution Time (seconds)")
    ax.set_title("Average Solver Computation Time (N=10)\n(Speed vs. Optimization Trade-off)", fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.6)

    # Format annotations
    for bar in bars:
        h = bar.get_height()
        ax.annotate(
            f"{h:.4f}s" if h < 0.1 else f"{h:.2f}s",
            xy=(bar.get_x() + bar.get_width() / 2, h),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontweight="bold"
        )

    plt.tight_layout()
    f2_path = os.path.join(figures_dir, "2_avg_runtime.png")
    fig.savefig(f2_path, dpi=300)
    plt.close(fig)
    fig_paths.append(f2_path)
    logger.info("Generated Figure 2: %s", f2_path)

    # -------------------------------------------------------------
    # Figure 3: Convergence Trajectory (SA & GA)
    # -------------------------------------------------------------
    fig, (ax_sa, ax_ga) = plt.subplots(1, 2, figsize=(12, 5))

    # SA Convergence
    if sa_history:
        ax_sa.plot(sa_history, color="#F5A623", linewidth=2.0, label="Simulated Annealing")
        ax_sa.set_xlabel("Iteration Step")
        ax_sa.set_ylabel("Best Tour Length (km)")
        ax_sa.set_title("Simulated Annealing Convergence\n(T_0=100.0, α=0.995)", fontweight="bold")
        ax_sa.grid(True, linestyle="--", alpha=0.6)
        ax_sa.legend(loc="upper right")
        # Annotate initial vs final
        ax_sa.annotate(
            f"Initial: {sa_history[0]:.2f} km",
            xy=(0, sa_history[0]),
            xytext=(30, -10),
            textcoords="offset points",
            arrowprops=dict(arrowstyle="->", color="#333333")
        )
        ax_sa.annotate(
            f"Final: {sa_history[-1]:.2f} km",
            xy=(len(sa_history) - 1, sa_history[-1]),
            xytext=(-80, 20),
            textcoords="offset points",
            arrowprops=dict(arrowstyle="->", color="#333333"),
            fontweight="bold"
        )

    # GA Convergence
    if ga_history:
        ax_ga.plot(ga_history, color="#9013FE", linewidth=2.0, label="Genetic Algorithm")
        ax_ga.set_xlabel("Generation")
        ax_ga.set_ylabel("Best Tour Length (km)")
        ax_ga.set_title("Genetic Algorithm Convergence\n(Pop=80, Gens=200, OX Recombination)", fontweight="bold")
        ax_ga.grid(True, linestyle="--", alpha=0.6)
        ax_ga.legend(loc="upper right")
        # Annotate initial vs final
        ax_ga.annotate(
            f"Initial: {ga_history[0]:.2f} km",
            xy=(0, ga_history[0]),
            xytext=(20, -10),
            textcoords="offset points",
            arrowprops=dict(arrowstyle="->", color="#333333")
        )
        ax_ga.annotate(
            f"Final: {ga_history[-1]:.2f} km",
            xy=(len(ga_history) - 1, ga_history[-1]),
            xytext=(-70, 20),
            textcoords="offset points",
            arrowprops=dict(arrowstyle="->", color="#333333"),
            fontweight="bold"
        )

    plt.tight_layout()
    f3_path = os.path.join(figures_dir, "3_convergence_sa_ga.png")
    fig.savefig(f3_path, dpi=300)
    plt.close(fig)
    fig_paths.append(f3_path)
    logger.info("Generated Figure 3: %s", f3_path)

    # -------------------------------------------------------------
    # Figure 4: % Improvement vs NN Baseline
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5))

    # Filter out NN (since NN is baseline 0%)
    ai_solvers = summary_df[summary_df["solver"] != "Nearest Neighbor"]
    ai_names = ai_solvers["solver"].tolist()
    mean_impr = ai_solvers["mean_improvement_pct"].tolist()
    max_impr = ai_solvers["max_improvement_pct"].tolist()
    impr_colors = ["#50E3C2", "#F5A623", "#9013FE"]

    x = np.arange(len(ai_names))
    width = 0.35

    rects1 = ax.bar(x - width/2, mean_impr, width, label="Mean Improvement (%)", color=impr_colors, alpha=0.85, edgecolor="#333333")
    rects2 = ax.bar(x + width/2, max_impr, width, label="Peak Improvement (%)", color=impr_colors, hatch="//", alpha=0.5, edgecolor="#333333")

    ax.set_ylabel("% Route Distance Saved vs NN")
    ax.set_title("Percentage Route Length Improvement over Nearest Neighbor Baseline\n(Higher is Better)", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(ai_names)
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.6)

    # Add value annotations
    for rect in rects1:
        h = rect.get_height()
        ax.annotate(
            f"{h:.1f}%",
            xy=(rect.get_x() + rect.get_width() / 2, h),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontweight="bold"
        )
    for rect in rects2:
        h = rect.get_height()
        ax.annotate(
            f"{h:.1f}%",
            xy=(rect.get_x() + rect.get_width() / 2, h),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9
        )

    plt.tight_layout()
    f4_path = os.path.join(figures_dir, "4_pct_improvement_vs_nn.png")
    fig.savefig(f4_path, dpi=300)
    plt.close(fig)
    fig_paths.append(f4_path)
    logger.info("Generated Figure 4: %s", f4_path)

    return fig_paths


if __name__ == "__main__":
    run_experiments()
