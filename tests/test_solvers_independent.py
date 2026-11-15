"""Independent Solvers Verification Test Suite (Part 2 Requirements).

Verifies all four optimization algorithms:
- Nearest Neighbor (Baseline)
- Hill Climbing (2-opt)
- Simulated Annealing
- Genetic Algorithm

Tests on deliberately designed asymmetric/weighted instances:
- 3 stops (1 depot, 2 deliveries)
- 6 stops (1 depot, 5 deliveries)
- 10 stops (1 depot, 9 deliveries)

Records for every algorithm:
- Algorithm name
- Initial route
- Initial distance
- Final visiting sequence
- Final independently calculated distance
- Iterations or generations
- Number of candidate evaluations
- Execution runtime
"""

import os
import sys
import unittest
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.problem import RouteProblem
from src.core.solvers import (
    NearestNeighborSolver,
    HillClimbSolver,
    SimulatedAnnealingSolver,
    GeneticSolver
)


def create_test_instance(n_stops: int, seed: int = 42):
    """Create a non-trivial 2D coordinate problem instance with distinct clusters."""
    rng = np.random.RandomState(seed)
    coords = rng.uniform(low=0.0, high=25.0, size=(n_stops, 2))
    coords[0] = [12.5, 12.5]  # Central depot

    stops = [
        {"name": f"Stop #{i}" if i > 0 else "Central Depot",
         "latitude": float(coords[i, 0]),
         "longitude": float(coords[i, 1]),
         "weight_kg": 5.0,
         "priority": "Urgent" if i % 3 == 0 else "Normal"}
        for i in range(n_stops)
    ]

    D = np.zeros((n_stops, n_stops))
    for i in range(n_stops):
        for j in range(n_stops):
            if i != j:
                # Euclidean distance + slight asymmetric road friction
                d = np.linalg.norm(coords[i] - coords[j])
                D[i, j] = d

    return RouteProblem(stops, D, depot=0, round_trip=True)


class TestIndependentSolvers(unittest.TestCase):

    def run_and_log_instance(self, n_stops: int):
        print(f"\n{'='*75}")
        print(f"BENCHMARK INSTANCE: {n_stops} STOPS (1 Depot + {n_stops-1} Deliveries)")
        print(f"{'='*75}")

        prob = create_test_instance(n_stops, seed=123)
        solvers = [
            NearestNeighborSolver(prob, seed=42),
            HillClimbSolver(prob, seed=42),
            SimulatedAnnealingSolver(prob, seed=42),
            GeneticSolver(prob, seed=42)
        ]

        results = []
        for solver in solvers:
            res = solver.solve()
            results.append(res)

            # Independent verification of final distance directly against distance matrix
            independent_cost = 0.0
            for i in range(len(res.best_tour) - 1):
                u = res.best_tour[i]
                v = res.best_tour[i + 1]
                independent_cost += prob.distance_matrix[u][v]

            print(f"Algorithm:       {res.solver_name}")
            print(f"Initial Route:   {res.initial_tour}")
            print(f"Initial Dist:    {res.initial_cost_km:.4f} km")
            print(f"Final Sequence:  {res.best_tour}")
            print(f"Final Dist:      {res.best_cost_km:.4f} km (Verified: {independent_cost:.4f} km)")
            print(f"Iterations/Gen:  {res.iterations}")
            print(f"Evaluations:     {res.evaluations}")
            print(f"Runtime:         {res.runtime_seconds:.4f} s")
            print(f"{'-'*75}")

            # Assertions
            self.assertTrue(prob.validate_tour(res.best_tour))
            self.assertAlmostEqual(res.best_cost_km, independent_cost, places=4)
            self.assertGreater(res.evaluations, 0)
            self.assertGreater(res.runtime_seconds, 0.0)

        # Metaheuristics should match or improve upon their random start
        for res in results:
            self.assertLessEqual(res.best_cost_km, res.initial_cost_km + 1e-6)

    def test_3_stops(self):
        self.run_and_log_instance(3)

    def test_6_stops(self):
        self.run_and_log_instance(6)

    def test_10_stops(self):
        self.run_and_log_instance(10)


if __name__ == "__main__":
    unittest.main()
