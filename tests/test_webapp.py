"""HTTP workflow checks for the Flask route-planning interface."""

import os
import tempfile
import unittest

from src.core.astar import AStarPlanner
from src.data.geocoder import LocationGeocoder
from src.data.graph_loader import GraphLoader
from src.data.stop_generator import StopGenerator
from src.webapp import create_app
import src.webapp as webapp


class FlaskRouteWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loader = GraphLoader("Karachi")
        loader.load_graph()
        cls.graph_loader = loader

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "AUTO_LOAD_GRAPH": False,
            "DATABASE_PATH": os.path.join(self.temp_dir.name, "history.db"),
        })
        webapp.runtime.graph_loader = self.graph_loader
        webapp.runtime.planner = AStarPlanner(self.graph_loader.graph)
        webapp.runtime.geocoder = LocationGeocoder(self.graph_loader)
        webapp.runtime.stop_generator = StopGenerator(self.graph_loader)
        webapp.runtime.graph_status = "online"
        webapp.runtime.graph_error = None
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def place(name, lat, lon):
        return {
            "name": name,
            "address": name,
            "latitude": lat,
            "longitude": lon,
        }

    def test_complete_route_planning_and_history_workflow(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Route planner", response.data)
        initial_state = self.client.get("/api/state").json
        self.assertEqual(initial_state["settings"]["map_style"], "Google Maps (Standard)")

        depot = self.place("Wazir Mansion", 24.8512, 66.9974)
        first_stop = self.place("Merewether Clock Tower", 24.8490, 66.9935)
        second_stop = self.place("Bolton Market", 24.8540, 67.0022)
        response = self.client.post("/api/depot", json={"place": depot})
        self.assertEqual(response.status_code, 200)
        for place, priority in ((first_stop, "Normal"), (second_stop, "Urgent")):
            response = self.client.post("/api/stops", json={
                "place": place,
                "name": place["name"],
                "weight_kg": 3.5,
                "priority": priority,
                "time_window": "Anytime",
            })
            self.assertEqual(response.status_code, 201)
        response = self.client.patch("/api/stops/0", json={
            "name": "Merewether Clock",
            "weight_kg": 3.5,
            "priority": "Normal",
            "time_window": "Anytime",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["deliveries"][0]["name"], "Merewether Clock")

        response = self.client.post("/api/settings", json={
            "solver": "Nearest Neighbor (Baseline)",
            "capacity_kg": 20,
        })
        self.assertEqual(response.status_code, 200)

        response = self.client.post("/api/clusters", json={"k": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["clusters"]["n_clusters"], 2)

        response = self.client.post("/api/optimize", json={})
        self.assertEqual(response.status_code, 200, response.json)
        result = response.json["result"]
        self.assertGreater(result["distance_km"], 0)
        self.assertGreaterEqual(len(result["coordinates"]), 2)
        self.assertEqual(len(result["itinerary"]), 4)
        response = self.client.post("/api/settings", json={"map_style": "Positron (Light)"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json["result"])

        response = self.client.post("/api/simulation/start", json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["agent"]["current_goal_index"], 1)
        response = self.client.post("/api/simulation/stop", json={})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["simulation_active"])
        response = self.client.post("/api/simulation/start", json={})
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/simulation/action", json={"action": "skip"})
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/simulation/action", json={"action": "deliver"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["agent"]["is_finished"])

        response = self.client.post("/api/save", json={})
        self.assertEqual(response.status_code, 201)
        route_id = response.json["route_id"]
        history = self.client.get("/api/history").json
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "Partial")
        details = self.client.get(f"/api/history/{route_id}").json
        self.assertEqual(len(details["stops"]), 4)

        response = self.client.post(f"/api/history/{route_id}/load", json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["deliveries"]), 2)

    def test_invalid_fleet_settings_are_rejected(self):
        response = self.client.post("/api/settings", json={"capacity_kg": 0})
        self.assertEqual(response.status_code, 400)
        self.assertIn("capacity", response.json["error"].lower())

    def test_analytics_includes_model_chart_data(self):
        response = self.client.get("/api/analytics")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json["test_actual_mins"], list)
        self.assertIsInstance(response.json["test_predicted_mins"], list)
        self.assertEqual(
            len(response.json["test_actual_mins"]),
            len(response.json["test_predicted_mins"]),
        )


if __name__ == "__main__":
    unittest.main()
