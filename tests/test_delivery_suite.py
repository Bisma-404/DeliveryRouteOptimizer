"""End-to-End Test Suite for Enhanced Delivery Route Optimizer.

Tests:
- Dynamic stop numbers: 3, 5, 10, and 15 stops.
- All 4 optimization solvers: NN, HC, SA, GA.
- Road search algorithms: A*, UCS, BFS, DFS.
- Constraints: vehicle capacity, priority, and time windows.
- Round Trip vs Open Tour.
- K-Means spatial clustering.
- Location search, snapping, and unreachable location detection.
- SQLite Route History saving, querying, status updating, and deletion.
- Real road-following coordinates generation.
"""

from __future__ import annotations

import os
import sys
import unittest
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.data.graph_loader import GraphLoader
from src.data.stop_generator import StopGenerator
from src.data.geocoder import LocationGeocoder, UnreachableLocationError
from src.data.database import DatabaseManager
from src.core.astar import AStarPlanner
from src.core.problem import RouteProblem
from src.core.solvers import (
    NearestNeighborSolver,
    HillClimbSolver,
    SimulatedAnnealingSolver,
    GeneticSolver
)
from src.core.clustering import cluster_delivery_stops, get_cluster_first_tour


class TestEnhancedDeliveryOptimizer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loader = GraphLoader("Karachi")
        cls.graph = cls.loader.load_graph(force_download=False)
        cls.planner = AStarPlanner(cls.graph)
        cls.generator = StopGenerator(cls.loader)
        cls.geocoder = LocationGeocoder(cls.loader)

        # Temporary test database
        cls.test_db_path = os.path.join(PROJECT_ROOT, "data", "test_suite_history.db")
        if os.path.exists(cls.test_db_path):
            os.remove(cls.test_db_path)
        cls.db = DatabaseManager(cls.test_db_path)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

    def test_01_geocoder_search_and_unreachable_error(self):
        """Verify address search, valid snapping, and error on unreachable location."""
        # 1. Search landmark
        results = self.geocoder.search_places("Bolton Market")
        self.assertGreater(len(results), 0)
        self.assertIn("Bolton Market", results[0]["name"])

        # 2. Valid snap
        snapped = self.geocoder.snap_and_validate("Bolton Market", "M.A. Jinnah Rd", 24.8540, 67.0022)
        self.assertIn("nearest_node", snapped)
        self.assertLess(snapped["snap_distance_m"], 500.0)

        # 3. Unreachable location (far outside Karachi)
        with self.assertRaises(UnreachableLocationError):
            self.geocoder.snap_and_validate("Lahore Fort", "Lahore", 31.5880, 74.3150)

    def test_02_search_methods_astar_ucs_bfs_dfs(self):
        """Verify all 4 pathfinding methods: A*, UCS, BFS, DFS."""
        nodes = list(self.graph.nodes())
        start, goal = nodes[5], nodes[45]

        for method in ["astar", "ucs", "bfs", "dfs"]:
            path, dist_m, nodes_exp = self.planner.find_path(start, goal, method=method)
            self.assertIsNotNone(path)
            self.assertEqual(path[0], start)
            self.assertEqual(path[-1], goal)
            self.assertGreater(dist_m, 0.0)
            self.assertGreater(nodes_exp, 0)

    def test_03_scale_3_stops(self):
        """Test routing with 3 stops (1 depot + 2 customer deliveries)."""
        stops = self.generator.generate_stops(num_stops=3, seed=42)
        stops[1]["weight_kg"] = 8.0
        stops[1]["priority"] = "Urgent"
        stops[2]["weight_kg"] = 12.0
        stops[2]["priority"] = "Normal"

        dm, dp, ne = self.planner.build_distance_matrix(stops, search_method="astar")
        prob = RouteProblem(stops, dm, depot=0, round_trip=True, vehicle_capacity_kg=50.0)

        for solver_cls in [NearestNeighborSolver, HillClimbSolver, SimulatedAnnealingSolver, GeneticSolver]:
            solver = solver_cls(prob, seed=42)
            tour, cost, hist, rt = solver.solve()
            self.assertEqual(len(tour), 4)  # 0, s1, s2, 0
            self.assertEqual(tour[0], 0)
            self.assertEqual(tour[-1], 0)
            self.assertGreater(cost, 0.0)

    def test_04_scale_5_stops_and_open_tour(self):
        """Test routing with 5 stops in Open Tour mode (finish at last delivery)."""
        stops = self.generator.generate_stops(num_stops=5, seed=42)
        for i, s in enumerate(stops[1:], 1):
            s["weight_kg"] = float(i * 3.5)
            s["priority"] = "Urgent" if i % 2 == 1 else "Normal"

        dm, dp, ne = self.planner.build_distance_matrix(stops, search_method="astar")
        prob_open = RouteProblem(stops, dm, depot=0, round_trip=False, vehicle_capacity_kg=50.0)

        sa_solver = SimulatedAnnealingSolver(prob_open, seed=42)
        tour, cost, hist, rt = sa_solver.solve()
        self.assertEqual(len(tour), 5)  # 0, s1, s2, s3, s4
        self.assertEqual(tour[0], 0)
        self.assertNotEqual(tour[-1], 0)
        self.assertGreater(cost, 0.0)

        # Road coordinates
        coords = self.planner.get_detailed_route_coordinates(tour, dp)
        self.assertGreater(len(coords), 10)

    def test_05_scale_10_stops_and_constraints(self):
        """Test routing with 10 stops and CSP constraint checks."""
        stops = self.generator.generate_stops(num_stops=10, seed=42)
        total_w = 0.0
        for i, s in enumerate(stops[1:], 1):
            w = float(i * 2.0)
            s["weight_kg"] = w
            s["priority"] = "Urgent" if i in (1, 2) else "Normal"
            s["time_window"] = f"09:00 - {10 + i}:00"
            total_w += w

        dm, dp, ne = self.planner.build_distance_matrix(stops, search_method="astar")

        # Feasible problem (capacity 100 kg > total_w)
        prob = RouteProblem(stops, dm, depot=0, round_trip=True, vehicle_capacity_kg=100.0)
        c_check = prob.check_constraints(prob.random_solution())
        self.assertTrue(c_check["capacity_ok"])
        self.assertAlmostEqual(c_check["total_weight_kg"], total_w)
        self.assertGreater(c_check["est_journey_time_mins"], 0.0)

        # Infeasible problem (capacity 20 kg < total_w)
        prob_infeasible = RouteProblem(stops, dm, depot=0, round_trip=True, vehicle_capacity_kg=20.0)
        c_check_inf = prob_infeasible.check_constraints(prob_infeasible.random_solution())
        self.assertFalse(c_check_inf["capacity_ok"])

    def test_06_scale_15_stops_and_kmeans_clustering(self):
        """Test routing with 15 stops and K-Means spatial grouping."""
        stops = self.generator.generate_stops(num_stops=15, seed=42)
        for i, s in enumerate(stops[1:], 1):
            s["weight_kg"] = 4.0
            s["priority"] = "Urgent" if i % 4 == 0 else "Normal"

        # K-Means clustering
        clustered_stops, clusters_dict, summary = cluster_delivery_stops(stops, n_clusters=3)
        self.assertEqual(summary["n_clusters"], 3)
        self.assertEqual(len(clusters_dict), 3)

        dm, dp, ne = self.planner.build_distance_matrix(clustered_stops, search_method="astar")
        prob = RouteProblem(clustered_stops, dm, depot=0, round_trip=True, vehicle_capacity_kg=150.0)

        # Cluster-first initial tour
        cluster_tour = get_cluster_first_tour(prob, clusters_dict)
        self.assertEqual(len(cluster_tour), 16)
        cluster_cost = prob.route_length(cluster_tour)

        # SA optimization
        sa = SimulatedAnnealingSolver(prob, seed=42)
        opt_tour, opt_cost, _, _ = sa.solve()
        self.assertLessEqual(opt_cost, cluster_cost * 1.1)

    def test_07_sqlite_database_lifecycle(self):
        """Test complete SQLite lifecycle: save route, list, inspect, update stop, delete."""
        route_meta = {
            "route_name": "Test Karachi Central Delivery",
            "depot_name": "Wazir Mansion",
            "depot_lat": 24.8512,
            "depot_lon": 66.9974,
            "num_stops": 4,
            "total_distance_km": 6.85,
            "est_time_mins": 22.5,
            "baseline_distance_km": 8.50,
            "saved_distance_km": 1.65,
            "saved_pct": 19.4,
            "algorithm": "Simulated Annealing",
            "search_method": "A*",
            "round_trip": True,
            "vehicle_capacity_kg": 50.0,
            "total_weight_kg": 18.0,
            "status": "Planned"
        }
        stops_list = [
            {"name": "Wazir Mansion", "address": "Kharadar", "latitude": 24.8512, "longitude": 66.9974, "priority": "Normal", "weight_kg": 0.0, "time_window": "Anytime", "delivery_status": "Depot", "leg_distance_km": 0.0, "est_arrival_min": 0.0},
            {"name": "Bolton Market", "address": "M.A. Jinnah", "latitude": 24.8540, "longitude": 67.0022, "priority": "Urgent", "weight_kg": 6.0, "time_window": "09:30-10:30", "delivery_status": "Pending", "leg_distance_km": 1.5, "est_arrival_min": 8.0},
            {"name": "Denso Hall", "address": "Saddar", "latitude": 24.8551, "longitude": 67.0104, "priority": "Normal", "weight_kg": 12.0, "time_window": "10:00-12:00", "delivery_status": "Pending", "leg_distance_km": 1.8, "est_arrival_min": 15.0},
            {"name": "Wazir Mansion", "address": "Kharadar", "latitude": 24.8512, "longitude": 66.9974, "priority": "Normal", "weight_kg": 0.0, "time_window": "Anytime", "delivery_status": "Return", "leg_distance_km": 3.55, "est_arrival_min": 22.5}
        ]

        # 1. Save
        route_id = self.db.save_route(route_meta, stops_list)
        self.assertGreater(route_id, 0)

        # 2. Query All
        routes = self.db.get_all_routes()
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0]["id"], route_id)

        # 3. Details
        meta, saved_stops = self.db.get_route_details(route_id)
        self.assertIsNotNone(meta)
        self.assertEqual(len(saved_stops), 4)

        # 4. Update Stop Delivery Status (Delivered / Skipped)
        stop_to_update = saved_stops[1]["id"]
        ok = self.db.update_stop_status(stop_to_update, "Delivered")
        self.assertTrue(ok)

        # 5. Summary metrics
        perf = self.db.get_performance_summary()
        self.assertEqual(perf["total_routes"], 1)
        self.assertAlmostEqual(perf["avg_distance"], 6.85)

        # 6. Delete
        del_ok = self.db.delete_route(route_id)
        self.assertTrue(del_ok)
        self.assertEqual(len(self.db.get_all_routes()), 0)


if __name__ == "__main__":
    unittest.main()
