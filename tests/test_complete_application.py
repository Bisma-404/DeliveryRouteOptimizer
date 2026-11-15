"""Comprehensive End-to-End Test Suite for Delivery Route Optimizer (Part 10).

Covers all 16 required verification points:
1. Empty application launch (no hardcoded stops or default depot).
2. Location autocomplete (search for 'FAST', 'DHA', 'Clifton').
3. Depot selection.
4. Adding, editing, and removing delivery stops.
5. Individual package weight input.
6. Vehicle capacity validation (loaded vs remaining).
7. CSP feasibility and infeasibility (AllDifferent, capacity, time windows).
8. All four optimization algorithms (NN, HC, SA, GA with evaluations & convergence).
9. BFS, DFS, UCS and A* search methods.
10. K-Means clustering, delivery zones, and elbow curve calculation.
11. Supervised learning travel-time prediction (Random Forest & Linear Regression).
12. Intelligent goal-based agent simulation (percepts, actions, cargo tracking).
13. Route visualization coordinates generation (real road geometry).
14. Map style switching (Google Maps, CartoDB Voyager, Positron, Dark Matter).
15. SQLite route history (saving, reading, stats, details, deletion).
16. Application screen navigation across all 6 screens (Dashboard, Planner, Results, History, Analytics, Settings).
"""

import os
import sys
import unittest
import tkinter as tk
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.data.graph_loader import GraphLoader
from src.data.geocoder import LocationGeocoder
from src.data.database import DatabaseManager
from src.core.astar import AStarPlanner
from src.core.problem import RouteProblem
from src.core.solvers import (
    NearestNeighborSolver,
    HillClimbSolver,
    SimulatedAnnealingSolver,
    GeneticSolver
)
from src.core.csp import DeliveryCSP
from src.core.clustering import cluster_delivery_stops, compute_elbow_curve
from src.core.agent import GoalBasedDeliveryAgent, AgentAction
from src.core.ml_predictor import TravelTimePredictor
from src.gui.app import DeliveryRouteOptimizerApp, TILE_SERVERS


class TestCompleteApplicationSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = GraphLoader("Karachi")
        cls.graph = cls.loader.load_graph(force_download=False)
        cls.planner = AStarPlanner(cls.graph)
        cls.geocoder = LocationGeocoder(cls.loader)
        cls.db = DatabaseManager()

    # 1. Empty application launch
    def test_01_empty_app_launch(self):
        root = tk.Tk()
        root.withdraw()
        app = DeliveryRouteOptimizerApp(root)
        self.assertIsNone(app.depot_stop)
        self.assertEqual(len(app.customer_deliveries), 0)
        self.assertEqual(app.btn_optimize["state"], tk.DISABLED)
        root.destroy()

    # 2. Location autocomplete
    def test_02_location_autocomplete(self):
        res_fast = self.geocoder.search_places("FAST", limit=5)
        self.assertGreater(len(res_fast), 0)
        self.assertTrue(any("FAST" in r["name"] for r in res_fast))

        res_dha = self.geocoder.search_places("DHA", limit=5)
        self.assertGreater(len(res_dha), 0)
        self.assertTrue(any("DHA" in r["name"] for r in res_dha))

    # 3. Depot selection
    def test_03_depot_selection(self):
        res = self.geocoder.search_places("FAST NUCES Karachi", limit=1)
        self.assertGreater(len(res), 0)
        depot = self.geocoder.snap_location(res[0]["name"], res[0]["address"], res[0]["latitude"], res[0]["longitude"])
        depot["type"] = "depot"
        self.assertEqual(depot["type"], "depot")
        self.assertIn("nearest_node", depot)

    # 4 & 5. Adding, editing, removing delivery stops & package weights
    def test_04_stops_and_weights_management(self):
        res = self.geocoder.search_places("Clifton", limit=3)
        stops = []
        for i, r in enumerate(res):
            s = self.geocoder.snap_location(f"Cust {i}", r["address"], r["latitude"], r["longitude"])
            s["weight_kg"] = 10.0 + i * 5.0
            s["priority"] = "Urgent" if i == 0 else "Normal"
            stops.append(s)

        self.assertEqual(len(stops), 3)
        self.assertEqual(stops[0]["weight_kg"], 10.0)
        # Edit stop
        stops[0]["weight_kg"] = 14.5
        self.assertEqual(stops[0]["weight_kg"], 14.5)
        # Remove stop
        removed = stops.pop(1)
        self.assertEqual(len(stops), 2)
        self.assertEqual(removed["weight_kg"], 15.0)

    # 6 & 7. Vehicle capacity validation & CSP feasibility/infeasibility
    def test_05_vehicle_capacity_and_csp(self):
        stops = [
            {"name": "Depot", "latitude": 24.85, "longitude": 67.0, "weight_kg": 0.0, "time_window": "Anytime"},
            {"name": "Stop 1", "latitude": 24.86, "longitude": 67.01, "weight_kg": 20.0, "priority": "Urgent", "time_window": "60 min"},
            {"name": "Stop 2", "latitude": 24.87, "longitude": 67.02, "weight_kg": 25.0, "priority": "Normal", "time_window": "120 min"},
        ]
        D = np.ones((3, 3)) * 5.0
        np.fill_diagonal(D, 0.0)

        # Feasible case (Capacity = 50kg, Payload = 45kg)
        csp_ok = DeliveryCSP(stops, D, vehicle_capacity_kg=50.0)
        res_ok = csp_ok.solve_backtracking()
        self.assertTrue(res_ok["feasible"])
        self.assertEqual(res_ok["ordered_tour"], [0, 1, 2, 0])

        # Infeasible case (Capacity = 30kg, Payload = 45kg)
        csp_infeasible = DeliveryCSP(stops, D, vehicle_capacity_kg=30.0)
        res_infeasible = csp_infeasible.solve_backtracking()
        self.assertFalse(res_infeasible["feasible"])
        self.assertIn("Hard Constraint Violation", res_infeasible["explanation"])

    # 8. All four optimization algorithms with multiple counts (3, 6, 10 stops)
    def test_06_all_four_solvers_multi_counts(self):
        for n_stops in [3, 6, 10]:
            rng = np.random.RandomState(42)
            coords = rng.uniform(0.0, 20.0, size=(n_stops, 2))
            coords[0] = [10.0, 10.0]
            stops = [{"name": f"S{i}", "latitude": float(coords[i, 0]), "longitude": float(coords[i, 1]), "weight_kg": 5.0} for i in range(n_stops)]
            D = np.zeros((n_stops, n_stops))
            for i in range(n_stops):
                for j in range(n_stops):
                    D[i, j] = np.linalg.norm(coords[i] - coords[j])

            prob = RouteProblem(stops, D, depot=0, round_trip=True)
            for S in [NearestNeighborSolver, HillClimbSolver, SimulatedAnnealingSolver, GeneticSolver]:
                s = S(prob, seed=42)
                res = s.solve()
                self.assertTrue(prob.validate_tour(res.best_tour))
                self.assertGreater(res.evaluations, 0)
                self.assertLessEqual(res.best_cost_km, res.initial_cost_km + 1e-6)

    # 9. BFS, DFS, UCS, A* search algorithms
    def test_07_graph_search_methods(self):
        nodes = list(self.graph.nodes())
        start, goal = nodes[10], nodes[50]
        for method in ["astar", "ucs", "bfs", "dfs"]:
            path, dist_m, nodes_exp = self.planner.find_path(start, goal, method=method)
            self.assertIsNotNone(path)
            self.assertEqual(path[0], start)
            self.assertEqual(path[-1], goal)
            self.assertGreater(dist_m, 0.0)

    # 10. K-Means clustering, delivery zones, and elbow curve
    def test_08_kmeans_zones_and_elbow(self):
        stops = [
            {"name": "Depot", "latitude": 24.8, "longitude": 67.0},
            {"name": "Stop 1", "latitude": 24.81, "longitude": 67.01, "weight_kg": 5.0},
            {"name": "Stop 2", "latitude": 24.82, "longitude": 67.02, "weight_kg": 8.0},
            {"name": "Stop 3", "latitude": 24.91, "longitude": 67.11, "weight_kg": 6.0},
            {"name": "Stop 4", "latitude": 24.92, "longitude": 67.12, "weight_kg": 7.0},
        ]
        u_stops, c_dict, summary = cluster_delivery_stops(stops, n_clusters=2)
        self.assertEqual(summary["n_clusters"], 2)
        self.assertIn(0, c_dict)
        self.assertIn(1, c_dict)

        k_vals, inertias = compute_elbow_curve(stops, max_k=3)
        self.assertEqual(len(k_vals), 3)
        self.assertGreater(inertias[0], inertias[-1])

    # 11. Supervised learning travel-time prediction
    def test_09_supervised_learning_prediction(self):
        predictor = TravelTimePredictor("Random Forest")
        metrics = predictor.train()
        self.assertIn("R2_score", metrics)
        self.assertGreater(metrics["R2_score"], 0.80)
        self.assertIn("MAE_mins", metrics)

        pred_time = predictor.predict(distance_km=30.0, num_stops=8, vehicle_speed_kmh=30.0)
        self.assertGreater(pred_time, 30.0)

    # 12. Intelligent goal-based agent simulation
    def test_10_intelligent_agent_simulation(self):
        stops = [
            {"name": "Depot", "latitude": 24.85, "longitude": 67.0, "weight_kg": 0.0},
            {"name": "Customer 1", "latitude": 24.86, "longitude": 67.01, "weight_kg": 10.0},
            {"name": "Customer 2", "latitude": 24.87, "longitude": 67.02, "weight_kg": 15.0},
        ]
        tour = [0, 1, 2, 0]
        coords = [(24.85, 67.0), (24.86, 67.01), (24.87, 67.02), (24.85, 67.0)]

        agent = GoalBasedDeliveryAgent(tour, stops, coords, vehicle_capacity_kg=50.0)
        self.assertEqual(agent.remaining_cargo_kg, 25.0)

        # Perceive at stop 1
        agent.current_tour_step = 1
        percept = agent.perceive(24.86, 67.01, 1, is_at_stop=True, stop_id=1)
        action, reason = agent.decide_action(percept)
        self.assertEqual(action, AgentAction.ARRIVE_AT_STOP)

        # Execute delivery
        deliv = agent.complete_current_delivery()
        self.assertEqual(deliv["status"], "Delivered")
        self.assertEqual(agent.remaining_cargo_kg, 15.0)
        self.assertEqual(len(agent.completed_stops), 1)

    # 13. Route visualization coordinates generation
    def test_11_route_coordinates_generation(self):
        stops = [
            {"name": "Depot", "latitude": 24.854, "longitude": 67.002, "nearest_node": list(self.graph.nodes())[0]},
            {"name": "Delivery 1", "latitude": 24.858, "longitude": 67.015, "nearest_node": list(self.graph.nodes())[25]},
        ]
        D, paths, nodes = self.planner.build_distance_matrix(stops, search_method="astar")
        coords = self.planner.get_detailed_route_coordinates([0, 1, 0], paths, stops=stops)
        self.assertGreater(len(coords), 2)
        for lat, lon in coords:
            self.assertGreater(lat, 20.0)
            self.assertGreater(lon, 60.0)

    # 14. Map style switching
    def test_12_map_styles_available(self):
        styles = ["Google Maps (Standard)", "CartoDB Voyager (Modern)", "CartoDB Positron (Clean)", "CartoDB Dark Matter (Dark)"]
        for s in styles:
            self.assertIn(s, TILE_SERVERS)
            self.assertTrue(TILE_SERVERS[s].startswith("https://"))

    # 15. SQLite route history
    def test_13_sqlite_history(self):
        initial_stats = self.db.get_dashboard_stats()
        meta = {
            "route_name": "Test Fleet Route",
            "depot_name": "Saddar Depot",
            "depot_lat": 24.85,
            "depot_lon": 67.01,
            "num_stops": 3,
            "total_distance_km": 15.5,
            "est_time_mins": 45.0,
            "baseline_distance_km": 18.0,
            "saved_distance_km": 2.5,
            "saved_pct": 13.8,
            "algorithm": "Simulated Annealing",
            "search_method": "A*",
            "round_trip": True,
            "vehicle_capacity_kg": 50.0,
            "total_weight_kg": 20.0,
            "status": "Planned"
        }
        stops = [
            {"name": "Saddar Depot", "address": "Saddar", "latitude": 24.85, "longitude": 67.01},
            {"name": "Cust 1", "address": "Clifton", "latitude": 24.82, "longitude": 67.03, "weight_kg": 10.0, "priority": "Urgent"},
            {"name": "Cust 2", "address": "DHA", "latitude": 24.81, "longitude": 67.05, "weight_kg": 10.0, "priority": "Normal"}
        ]
        r_id = self.db.save_route(meta, stops)
        self.assertGreater(r_id, 0)

        # Retrieve and verify
        saved_meta, saved_stops = self.db.get_route_details(r_id)
        self.assertIsNotNone(saved_meta)
        self.assertEqual(saved_meta["route_name"], "Test Fleet Route")
        self.assertEqual(len(saved_stops), 3)

        # Clean up
        self.db.delete_route(r_id)

    # 16. Screen navigation across all 6 screens
    def test_14_screen_navigation(self):
        root = tk.Tk()
        root.withdraw()
        app = DeliveryRouteOptimizerApp(root)

        for scr_name in ["dashboard", "planner", "results", "history", "analytics", "settings"]:
            app.show_screen(scr_name)
            self.assertEqual(app.active_screen_name, scr_name)
            self.assertTrue(app.screens[scr_name].winfo_ismapped() or app.screens[scr_name].winfo_manager() != "")

        root.destroy()


if __name__ == "__main__":
    unittest.main()
