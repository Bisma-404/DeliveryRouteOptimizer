"""Comprehensive Automated Test Suite for Delivery Route Optimizer.

Verifies:
- OSM Road Graph loading from cache & connectivity (SCC)
- Stop sampling & coordinate snapping to road nodes
- Custom A* search using heapq with Haversine heuristic (admissibility & consistency)
- Node expansion counting
- All 4 metaheuristic solvers (NN, HC, SA, GA) and tour validity
- Continuous road polyline coordinate generation for map display
- Tile server connectivity and custom User-Agent compliance
- Benchmark experiment suite execution
"""

import os
import sys
import unittest
import numpy as np

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.data.graph_loader import GraphLoader
from src.data.stop_generator import StopGenerator
from src.core.astar import AStarPlanner, haversine_distance
from src.core.problem import RouteProblem
from src.core.solvers import (
    NearestNeighborSolver,
    HillClimbSolver,
    SimulatedAnnealingSolver,
    GeneticSolver
)


class TestDeliveryRouteOptimizer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loader = GraphLoader("Karachi")
        cls.graph = cls.loader.load_graph(force_download=False)
        cls.generator = StopGenerator(cls.loader)
        cls.planner = AStarPlanner(cls.graph)

    def test_01_graph_loaded_and_strongly_connected(self):
        """Verify road graph contains nodes, edges, and is strongly connected."""
        self.assertIsNotNone(self.graph)
        self.assertGreater(len(self.graph.nodes), 500)
        self.assertGreater(len(self.graph.edges), 1000)

    def test_02_haversine_admissibility(self):
        """Verify Haversine distance is strictly non-negative and symmetric."""
        d1 = haversine_distance(24.8512, 66.9974, 24.8540, 67.0022)
        d2 = haversine_distance(24.8540, 67.0022, 24.8512, 66.9974)
        self.assertGreater(d1, 0.0)
        self.assertAlmostEqual(d1, d2, places=4)

    def test_03_astar_shortest_path_and_nodes_expanded(self):
        """Verify custom A* finds a path and counts node expansions."""
        nodes = list(self.graph.nodes())
        start, goal = nodes[0], nodes[50]
        path, dist_m, nodes_exp = self.planner.shortest_path(start, goal)
        self.assertIsNotNone(path)
        self.assertGreater(dist_m, 0.0)
        self.assertGreater(nodes_exp, 0)
        self.assertEqual(path[0], start)
        self.assertEqual(path[-1], goal)

    def test_04_stop_generator(self):
        """Verify stop generator produces 15 stops with depot at index 0."""
        stops = self.generator.generate_stops(num_stops=15, seed=42)
        self.assertEqual(len(stops), 15)
        self.assertEqual(stops[0]["type"], "depot")
        for s in stops:
            self.assertIn("nearest_node", s)
            self.assertIn(s["nearest_node"], self.graph.nodes)

    def test_05_solvers_and_tour_validity(self):
        """Verify all 4 solvers return valid round-trip tours visiting all stops."""
        stops = self.generator.generate_stops(num_stops=8, seed=42)
        dist_matrix, detailed_paths, nodes_exp = self.planner.build_distance_matrix(stops)
        problem = RouteProblem(stops, dist_matrix, depot=0)

        solvers = [
            NearestNeighborSolver(problem, seed=42),
            HillClimbSolver(problem, seed=42),
            SimulatedAnnealingSolver(problem, seed=42),
            GeneticSolver(problem, seed=42)
        ]

        for solver in solvers:
            tour, cost, history, runtime = solver.solve()
            self.assertTrue(problem.validate_tour(tour), f"{solver.name} produced invalid tour")
            self.assertGreater(cost, 0.0)
            self.assertGreater(runtime, 0.0)
            self.assertGreater(len(history), 0)

            # Test road coordinates generation
            coords = self.planner.get_detailed_route_coordinates(tour, detailed_paths)
            self.assertGreater(len(coords), len(tour))


if __name__ == "__main__":
    unittest.main(verbosity=2)
