"""Flask interface for the delivery route optimizer."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template, request, session

from .core.agent import AgentAction, GoalBasedDeliveryAgent
from .core.astar import AStarPlanner
from .core.clustering import cluster_delivery_stops, compute_elbow_curve
from .core.csp import DeliveryCSP
from .core.ml_predictor import TravelTimePredictor
from .core.problem import RouteProblem
from .core.solvers import (
    GeneticSolver,
    HillClimbSolver,
    NearestNeighborSolver,
    SimulatedAnnealingSolver,
)
from .data.database import DatabaseManager
from .data.geocoder import LocationGeocoder
from .data.graph_loader import GraphLoader
from .data.stop_generator import StopGenerator

logger = logging.getLogger(__name__)

SOLVERS = {
    "Simulated Annealing": SimulatedAnnealingSolver,
    "Genetic Algorithm": GeneticSolver,
    "Hill Climbing (2-opt)": HillClimbSolver,
    "Nearest Neighbor (Baseline)": NearestNeighborSolver,
}
SEARCH_METHODS = {"A*": "astar", "UCS": "ucs", "BFS": "bfs", "DFS": "dfs"}
MAP_STYLES = {
    "Google Maps (Standard)": "https://mt0.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}&s=Ga",
    "Voyager": "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
    "Positron (Light)": "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
    "Dark Matter": "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
}

DEFAULT_SETTINGS: Dict[str, Any] = {
    "capacity_kg": 50.0,
    "speed_kmh": 30.0,
    "service_mins": 5.0,
    "round_trip": True,
    "solver": "Simulated Annealing",
    "search_method": "A*",
    "map_style": "Google Maps (Standard)",
}


class WebRuntime:
    """Owns shared services and isolated per-browser planning sessions."""

    def __init__(self, database_path: Optional[str] = None) -> None:
        self.db = DatabaseManager(database_path)
        self.graph_loader: Optional[GraphLoader] = None
        self.planner: Optional[AStarPlanner] = None
        self.geocoder: Optional[LocationGeocoder] = None
        self.stop_generator: Optional[StopGenerator] = None
        self.graph_status = "loading"
        self.graph_error: Optional[str] = None
        self._graph_lock = threading.Lock()
        self._sessions_lock = threading.Lock()
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self.predictor = TravelTimePredictor("Random Forest")
        self.predictor.train()

    def start_graph_loader(self) -> None:
        thread = threading.Thread(target=self._load_graph, name="road-graph-loader", daemon=True)
        thread.start()

    def _load_graph(self) -> None:
        try:
            loader = GraphLoader("Karachi")
            graph = loader.load_graph()
            with self._graph_lock:
                self.graph_loader = loader
                self.planner = AStarPlanner(graph)
                self.geocoder = LocationGeocoder(loader)
                self.stop_generator = StopGenerator(loader)
                self.graph_status = "online"
                self.graph_error = None
            logger.info("Karachi road network ready (%d nodes)", len(graph.nodes))
        except Exception as exc:
            logger.exception("Could not initialize Karachi road network")
            with self._graph_lock:
                self.graph_status = "offline"
                self.graph_error = str(exc)

    def get_session(self, session_id: str) -> Dict[str, Any]:
        with self._sessions_lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = {
                    "lock": threading.RLock(),
                    "settings": dict(DEFAULT_SETTINGS),
                    "depot": None,
                    "deliveries": [],
                    "stops": [],
                    "result": None,
                    "distance_matrix": None,
                    "detailed_paths": None,
                    "problem": None,
                    "agent": None,
                    "clusters": None,
                    "simulation_active": False,
                }
            return self._sessions[session_id]


def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _request_payload() -> Dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    return payload


def _place_data(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Choose a location from the search results.")
    name = str(value.get("name", "")).strip()
    address = str(value.get("address", name)).strip()
    try:
        lat = float(value["latitude"])
        lon = float(value["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("The selected location has invalid coordinates.") from exc
    if not name or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise ValueError("The selected location has invalid coordinates.")
    return {"name": name, "address": address, "latitude": lat, "longitude": lon}


def _invalidate_result(state: Dict[str, Any]) -> None:
    state["result"] = None
    state["distance_matrix"] = None
    state["detailed_paths"] = None
    state["problem"] = None
    state["agent"] = None
    state["simulation_active"] = False


def _settings_payload(payload: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    settings = dict(current)
    if "capacity_kg" in payload:
        settings["capacity_kg"] = float(payload["capacity_kg"])
    if "speed_kmh" in payload:
        settings["speed_kmh"] = float(payload["speed_kmh"])
    if "service_mins" in payload:
        settings["service_mins"] = float(payload["service_mins"])
    if "round_trip" in payload:
        if not isinstance(payload["round_trip"], bool):
            raise ValueError("Round-trip preference must be true or false.")
        settings["round_trip"] = payload["round_trip"]
    if "solver" in payload:
        settings["solver"] = str(payload["solver"])
    if "search_method" in payload:
        settings["search_method"] = str(payload["search_method"])
    if "map_style" in payload:
        settings["map_style"] = str(payload["map_style"])

    if not 10 <= settings["capacity_kg"] <= 500:
        raise ValueError("Vehicle capacity must be between 10 and 500 kg.")
    if not 10 <= settings["speed_kmh"] <= 80:
        raise ValueError("Average speed must be between 10 and 80 km/h.")
    if not 0 <= settings["service_mins"] <= 30:
        raise ValueError("Service time must be between 0 and 30 minutes.")
    if settings["solver"] not in SOLVERS:
        raise ValueError("Select a supported optimization solver.")
    if settings["search_method"] not in SEARCH_METHODS:
        raise ValueError("Select a supported road search method.")
    if settings["map_style"] not in MAP_STYLES:
        raise ValueError("Select a supported map style.")
    return settings


def _planner_response(state: Dict[str, Any]) -> Dict[str, Any]:
    agent = state["agent"]
    result = state["result"]
    telemetry = agent.get_telemetry() if agent else None
    if telemetry and result:
        telemetry.update({
            "has_started": state["simulation_active"] or agent.current_tour_step > 0,
            "current_goal_index": agent.current_goal_stop_idx,
            "delivered_indices": list(agent.completed_stops),
            "skipped_indices": list(agent.skipped_stops),
        })
    return {
        "settings": state["settings"],
        "depot": state["depot"],
        "deliveries": state["deliveries"],
        "stops": state["stops"],
        "result": result,
        "clusters": state["clusters"],
        "agent": telemetry,
        "simulation_active": state["simulation_active"],
        "graph_status": runtime.graph_status,
        "graph_error": runtime.graph_error,
    }


def _serialize_result(
    state: Dict[str, Any],
    solver_result: Any,
    nodes_expanded: int,
    csp_result: Dict[str, Any],
) -> Dict[str, Any]:
    stops = state["stops"]
    tour = solver_result.best_tour
    matrix = state["distance_matrix"]
    problem = state["problem"]
    itinerary: List[Dict[str, Any]] = []
    for sequence, stop_index in enumerate(tour):
        stop = stops[stop_index]
        previous = tour[sequence - 1] if sequence else stop_index
        itinerary.append({
            "sequence": sequence,
            "stop_index": stop_index,
            "name": stop["name"],
            "address": stop.get("address", ""),
            "latitude": stop["latitude"],
            "longitude": stop["longitude"],
            "weight_kg": float(stop.get("weight_kg", 0.0)),
            "priority": stop.get("priority", "Normal"),
            "time_window": stop.get("time_window", "Anytime"),
            "leg_distance_km": float(matrix[previous][stop_index]),
            "type": stop.get("type", "delivery"),
        })

    estimate = problem.estimate_journey_time(tour)
    baseline = state["baseline_cost_km"]
    return {
        "solver_name": solver_result.solver_name,
        "tour": tour,
        "coordinates": state["route_coords"],
        "itinerary": itinerary,
        "distance_km": float(solver_result.best_cost_km),
        "baseline_km": float(baseline),
        "saved_km": max(0.0, float(baseline - solver_result.best_cost_km)),
        "saved_pct": (
            max(0.0, float(baseline - solver_result.best_cost_km)) / baseline * 100.0
            if baseline > 0 else 0.0
        ),
        "estimated_mins": float(estimate),
        "runtime_seconds": float(solver_result.runtime_seconds),
        "iterations": int(solver_result.iterations),
        "evaluations": int(solver_result.evaluations),
        "nodes_expanded": int(nodes_expanded),
        "convergence_history": [float(value) for value in solver_result.convergence_history],
        "csp": csp_result,
    }


def create_app(test_config: Optional[Dict[str, Any]] = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=uuid.uuid4().hex,
        JSON_SORT_KEYS=False,
        AUTO_LOAD_GRAPH=True,
        DATABASE_PATH=None,
    )
    if test_config:
        app.config.update(test_config)
    global runtime
    runtime = WebRuntime(app.config["DATABASE_PATH"])
    if app.config["AUTO_LOAD_GRAPH"]:
        runtime.start_graph_loader()

    def current_state() -> Dict[str, Any]:
        planner_id = session.get("planner_id")
        if not planner_id:
            planner_id = uuid.uuid4().hex
            session["planner_id"] = planner_id
        return runtime.get_session(planner_id)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/state")
    def get_state():
        state = current_state()
        with state["lock"]:
            payload = _planner_response(state)
        payload["dashboard"] = runtime.db.get_dashboard_stats()
        return jsonify(payload)

    @app.get("/api/search")
    def search_places():
        query = request.args.get("q", "").strip()
        if not query:
            return jsonify([])
        if runtime.geocoder is None:
            return _json_error(runtime.graph_error or "The Karachi road network is still loading.", 503)
        return jsonify(runtime.geocoder.search_places(query, limit=7))

    @app.post("/api/depot")
    def set_depot():
        if runtime.geocoder is None:
            return _json_error(runtime.graph_error or "The road network is still loading.", 503)
        try:
            payload = _request_payload()
            place = _place_data(payload.get("place"))
            depot = runtime.geocoder.snap_location(
                place["name"], place["address"], place["latitude"], place["longitude"]
            )
            depot.update({"type": "depot", "priority": "Normal", "weight_kg": 0.0})
            state = current_state()
            with state["lock"]:
                state["depot"] = depot
                state["stops"] = [depot] + list(state["deliveries"])
                _invalidate_result(state)
            return jsonify(_planner_response(state))
        except ValueError as exc:
            return _json_error(str(exc))

    @app.delete("/api/depot")
    def remove_depot():
        state = current_state()
        with state["lock"]:
            state["depot"] = None
            state["stops"] = list(state["deliveries"])
            _invalidate_result(state)
            return jsonify(_planner_response(state))

    @app.post("/api/stops")
    def add_delivery():
        if runtime.geocoder is None:
            return _json_error(runtime.graph_error or "The road network is still loading.", 503)
        try:
            payload = _request_payload()
            place = _place_data(payload.get("place"))
            name = str(payload.get("name") or place["name"]).strip()
            weight = float(payload.get("weight_kg", 5.0))
            priority = str(payload.get("priority", "Normal"))
            time_window = str(payload.get("time_window", "Anytime")).strip() or "Anytime"
            if not name:
                raise ValueError("Enter a name for this delivery.")
            if not 0 <= weight <= 500:
                raise ValueError("Package weight must be between 0 and 500 kg.")
            if priority not in {"Normal", "Urgent"}:
                raise ValueError("Delivery priority must be Normal or Urgent.")
            delivery = runtime.geocoder.snap_location(
                name, place["address"], place["latitude"], place["longitude"]
            )
            delivery.update({
                "type": "delivery",
                "priority": priority,
                "weight_kg": weight,
                "time_window": time_window,
            })
            state = current_state()
            with state["lock"]:
                state["deliveries"].append(delivery)
                state["stops"] = ([state["depot"]] if state["depot"] else []) + state["deliveries"]
                state["clusters"] = None
                _invalidate_result(state)
            return jsonify(_planner_response(state)), 201
        except (TypeError, ValueError) as exc:
            return _json_error(str(exc))

    @app.delete("/api/stops/<int:delivery_index>")
    def remove_delivery(delivery_index: int):
        state = current_state()
        with state["lock"]:
            if delivery_index < 0 or delivery_index >= len(state["deliveries"]):
                return _json_error("That delivery stop no longer exists.", 404)
            state["deliveries"].pop(delivery_index)
            state["stops"] = ([state["depot"]] if state["depot"] else []) + state["deliveries"]
            state["clusters"] = None
            _invalidate_result(state)
            return jsonify(_planner_response(state))

    @app.patch("/api/stops/<int:delivery_index>")
    def edit_delivery(delivery_index: int):
        state = current_state()
        try:
            payload = _request_payload()
            name = str(payload.get("name", "")).strip()
            weight = float(payload.get("weight_kg", 0.0))
            priority = str(payload.get("priority", "Normal"))
            time_window = str(payload.get("time_window", "Anytime")).strip() or "Anytime"
            if not name:
                raise ValueError("Enter a name for this delivery.")
            if not 0 <= weight <= 500:
                raise ValueError("Package weight must be between 0 and 500 kg.")
            if priority not in {"Normal", "Urgent"}:
                raise ValueError("Delivery priority must be Normal or Urgent.")
            with state["lock"]:
                if delivery_index >= len(state["deliveries"]):
                    return _json_error("That delivery stop no longer exists.", 404)
                state["deliveries"][delivery_index].update({
                    "name": name,
                    "weight_kg": weight,
                    "priority": priority,
                    "time_window": time_window,
                })
                state["stops"] = ([state["depot"]] if state["depot"] else []) + state["deliveries"]
                state["clusters"] = None
                _invalidate_result(state)
                return jsonify(_planner_response(state))
        except (TypeError, ValueError) as exc:
            return _json_error(str(exc))

    @app.delete("/api/stops")
    def clear_route():
        state = current_state()
        with state["lock"]:
            state["depot"] = None
            state["deliveries"] = []
            state["stops"] = []
            state["clusters"] = None
            _invalidate_result(state)
            return jsonify(_planner_response(state))

    @app.delete("/api/deliveries")
    def clear_deliveries():
        state = current_state()
        with state["lock"]:
            state["deliveries"] = []
            state["stops"] = [state["depot"]] if state["depot"] else []
            state["clusters"] = None
            _invalidate_result(state)
            return jsonify(_planner_response(state))

    @app.post("/api/sample")
    def load_sample():
        if runtime.stop_generator is None:
            return _json_error(runtime.graph_error or "The road network is still loading.", 503)
        try:
            payload = _request_payload()
            count = int(payload.get("count", 3))
            if count not in {3, 6, 10}:
                raise ValueError("Choose a sample with 3, 6, or 10 delivery stops.")
            generated = runtime.stop_generator.generate_stops(num_stops=count + 1, seed=42 + count)
            depot = dict(generated[0])
            depot.update({"type": "depot", "priority": "Normal", "weight_kg": 0.0})
            deliveries = []
            for index, stop in enumerate(generated[1:], 1):
                delivery = dict(stop)
                delivery.update({
                    "type": "delivery",
                    "priority": "Urgent" if index % 4 == 0 else "Normal",
                    "weight_kg": round(4.0 + (index % 5) * 1.5, 1),
                    "time_window": "Anytime",
                })
                deliveries.append(delivery)
            state = current_state()
            with state["lock"]:
                state["depot"] = depot
                state["deliveries"] = deliveries
                state["stops"] = [depot] + deliveries
                state["clusters"] = None
                _invalidate_result(state)
            return jsonify(_planner_response(state))
        except (ValueError, RuntimeError) as exc:
            return _json_error(str(exc))

    @app.post("/api/settings")
    def save_settings():
        try:
            payload = _request_payload()
            state = current_state()
            with state["lock"]:
                previous = state["settings"]
                updated = _settings_payload(payload, previous)
                state["settings"] = updated
                route_keys = ("capacity_kg", "speed_kmh", "service_mins", "round_trip", "solver", "search_method")
                if any(previous[key] != updated[key] for key in route_keys):
                    _invalidate_result(state)
            return jsonify(_planner_response(state))
        except (TypeError, ValueError) as exc:
            return _json_error(str(exc))

    @app.post("/api/clusters")
    def cluster_stops():
        state = current_state()
        try:
            with state["lock"]:
                if len(state["deliveries"]) < 2:
                    raise ValueError("Add at least two delivery stops before creating zones.")
                if state["depot"] is None:
                    raise ValueError("Set the depot before creating delivery zones.")
                payload = _request_payload()
                k = int(payload.get("k", 2))
                if not 2 <= k <= 5:
                    raise ValueError("Choose between 2 and 5 delivery zones.")
                stops = [dict(state["depot"])] + [dict(stop) for stop in state["deliveries"]]
                updated, _, summary = cluster_delivery_stops(stops, n_clusters=k)
                state["depot"] = updated[0]
                state["deliveries"] = updated[1:]
                state["stops"] = updated
                state["clusters"] = summary
                _invalidate_result(state)
                return jsonify(_planner_response(state))
        except (TypeError, ValueError) as exc:
            return _json_error(str(exc))

    @app.post("/api/optimize")
    def optimize_route():
        if runtime.planner is None:
            return _json_error(runtime.graph_error or "The road network is still loading.", 503)
        state = current_state()
        with state["lock"]:
            if state["depot"] is None or not state["deliveries"]:
                return _json_error("Set a depot and add at least one delivery before optimizing.")
            stops = [dict(state["depot"])] + [dict(stop) for stop in state["deliveries"]]
            settings = dict(state["settings"])
            total_weight = sum(float(stop.get("weight_kg", 0.0)) for stop in stops[1:])
            if total_weight > settings["capacity_kg"]:
                return _json_error(
                    f"Cargo load ({total_weight:.1f} kg) exceeds vehicle capacity "
                    f"({settings['capacity_kg']:.1f} kg)."
                )
            method = SEARCH_METHODS[settings["search_method"]]
            matrix, paths, nodes_expanded = runtime.planner.build_distance_matrix(
                stops, search_method=method
            )
            csp_result = DeliveryCSP(
                stops,
                matrix,
                vehicle_capacity_kg=settings["capacity_kg"],
                vehicle_speed_kmh=settings["speed_kmh"],
                service_time_mins=settings["service_mins"],
            ).solve_backtracking()
            if not csp_result["feasible"]:
                return _json_error(csp_result["explanation"], 422)

            problem = RouteProblem(
                stops,
                matrix,
                depot=0,
                round_trip=settings["round_trip"],
                vehicle_capacity_kg=settings["capacity_kg"],
                vehicle_speed_kmh=settings["speed_kmh"],
                service_time_mins=settings["service_mins"],
            )
            baseline = NearestNeighborSolver(problem, seed=42).solve()
            solver_result = SOLVERS[settings["solver"]](problem, seed=42).solve()
            coordinates = runtime.planner.get_detailed_route_coordinates(
                solver_result.best_tour, paths, stops=stops
            )
            state["stops"] = stops
            state["distance_matrix"] = matrix
            state["detailed_paths"] = paths
            state["problem"] = problem
            state["baseline_cost_km"] = baseline.best_cost_km
            state["route_coords"] = coordinates
            state["agent"] = GoalBasedDeliveryAgent(
                solver_result.best_tour,
                stops,
                coordinates,
                vehicle_capacity_kg=settings["capacity_kg"],
            )
            result = _serialize_result(state, solver_result, nodes_expanded, csp_result)
            state["result"] = result
            state["simulation_active"] = False
            return jsonify(_planner_response(state))

    @app.post("/api/simulation/start")
    def start_simulation():
        state = current_state()
        with state["lock"]:
            agent = state["agent"]
            if agent is None:
                return _json_error("Optimize a route before starting the delivery run.")
            if agent.is_finished:
                return _json_error("This delivery run has already finished.")
            if agent.current_tour_step == 0 and agent.current_goal_stop_idx == 0:
                agent.current_tour_step = 1
                agent.current_action = AgentAction.NAVIGATE_ROAD
                agent.action_reason = "Leaving the depot and heading to the first delivery."
            state["simulation_active"] = True
            return jsonify(_planner_response(state))

    @app.post("/api/simulation/action")
    def simulation_action():
        state = current_state()
        try:
            action = _request_payload().get("action")
        except ValueError as exc:
            return _json_error(str(exc))
        with state["lock"]:
            agent = state["agent"]
            if agent is None or not state["simulation_active"]:
                return _json_error("Start the delivery run before recording stop actions.")
            if agent.is_finished or agent.current_goal_stop_idx == 0:
                return _json_error("There is no active delivery stop.")
            try:
                if action == "deliver":
                    event = agent.complete_current_delivery()
                elif action == "skip":
                    event = agent.skip_current_delivery()
                else:
                    return _json_error("Choose either deliver or skip.")
            except (IndexError, ValueError) as exc:
                return _json_error(str(exc))
            if agent.current_goal_stop_idx == 0 and not agent.is_finished:
                agent.current_tour_step = len(agent.tour)
                agent.current_action = AgentAction.FINISH_TOUR
                agent.action_reason = "All scheduled stops processed; the delivery run has returned to the depot."
            if agent.is_finished:
                state["simulation_active"] = False
            return jsonify({"event": event, **_planner_response(state)})

    @app.post("/api/simulation/stop")
    def stop_simulation():
        state = current_state()
        with state["lock"]:
            if state["agent"] is None or not state["simulation_active"]:
                return _json_error("There is no active delivery run to stop.")
            state["simulation_active"] = False
            return jsonify(_planner_response(state))

    @app.post("/api/save")
    def save_route():
        state = current_state()
        with state["lock"]:
            if state["problem"] is None or state["result"] is None or state["depot"] is None:
                return _json_error("Optimize a route before saving it.")
            result = state["result"]
            settings = state["settings"]
            agent = state["agent"]
            completed = set(agent.completed_stops) if agent else set()
            skipped = set(agent.skipped_stops) if agent else set()
            ordered_stops = []
            for index in result["tour"]:
                stop = dict(state["stops"][index])
                stop["delivery_status"] = (
                    "Delivered" if index in completed else "Skipped" if index in skipped else "Pending"
                )
                ordered_stops.append(stop)
            status = "Planned"
            if agent:
                status = (
                    "Partial" if agent.skipped_stops
                    else "Completed" if agent.is_finished
                    else "In Progress" if agent.completed_stops
                    else "Planned"
                )
            route_id = runtime.db.save_route({
                "route_name": f"{state['depot']['name'][:24]} route",
                "depot_name": state["depot"]["name"],
                "depot_lat": state["depot"]["latitude"],
                "depot_lon": state["depot"]["longitude"],
                "num_stops": len(state["deliveries"]),
                "total_distance_km": result["distance_km"],
                "est_time_mins": result["estimated_mins"],
                "baseline_distance_km": result["baseline_km"],
                "saved_distance_km": result["saved_km"],
                "saved_pct": result["saved_pct"],
                "algorithm": result["solver_name"],
                "search_method": settings["search_method"],
                "round_trip": settings["round_trip"],
                "vehicle_capacity_kg": settings["capacity_kg"],
                "total_weight_kg": sum(float(stop.get("weight_kg", 0.0)) for stop in state["deliveries"]),
                "status": status,
            }, ordered_stops)
            return jsonify({"route_id": route_id, "dashboard": runtime.db.get_dashboard_stats()}), 201

    @app.get("/api/history")
    def history():
        return jsonify(runtime.db.get_all_routes())

    @app.get("/api/history/<int:route_id>")
    def history_details(route_id: int):
        metadata, stops = runtime.db.get_route_details(route_id)
        if metadata is None:
            return _json_error("That saved route was not found.", 404)
        return jsonify({"route": metadata, "stops": stops})

    @app.delete("/api/history/<int:route_id>")
    def delete_history_route(route_id: int):
        if not runtime.db.delete_route(route_id):
            return _json_error("That saved route was not found.", 404)
        return jsonify({"deleted": True})

    @app.post("/api/history/<int:route_id>/load")
    def load_history_route(route_id: int):
        if runtime.geocoder is None:
            return _json_error(runtime.graph_error or "The road network is still loading.", 503)
        metadata, saved_stops = runtime.db.get_route_details(route_id)
        if metadata is None or not saved_stops:
            return _json_error("That saved route has no stops to load.", 404)
        depot_data = saved_stops[0]
        try:
            depot = runtime.geocoder.snap_location(
                depot_data["name"], depot_data["address"],
                float(depot_data["latitude"]), float(depot_data["longitude"]),
            )
            depot.update({"type": "depot", "priority": "Normal", "weight_kg": 0.0})
            deliveries = []
            for stop in saved_stops[1:]:
                if stop["name"] == metadata["depot_name"] and float(stop["latitude"]) == float(metadata["depot_lat"]) and float(stop["longitude"]) == float(metadata["depot_lon"]):
                    continue
                delivery = runtime.geocoder.snap_location(
                    stop["name"], stop["address"], float(stop["latitude"]), float(stop["longitude"])
                )
                delivery.update({
                    "type": "delivery",
                    "priority": stop["priority"],
                    "weight_kg": float(stop["weight_kg"]),
                    "time_window": stop["time_window"],
                })
                deliveries.append(delivery)
            state = current_state()
            with state["lock"]:
                state["depot"] = depot
                state["deliveries"] = deliveries
                state["stops"] = [depot] + deliveries
                state["settings"]["capacity_kg"] = float(metadata["vehicle_capacity_kg"])
                state["settings"]["round_trip"] = bool(metadata["round_trip"])
                state["settings"]["search_method"] = metadata["search_method"] if metadata["search_method"] in SEARCH_METHODS else "A*"
                _invalidate_result(state)
            return jsonify(_planner_response(state))
        except (KeyError, TypeError, ValueError) as exc:
            return _json_error(f"Could not load this route: {exc}")

    @app.get("/api/analytics")
    def analytics():
        summary = runtime.db.get_performance_summary()
        routes = runtime.db.get_all_routes()
        return jsonify({
            "summary": summary,
            "routes": routes,
            "model_metrics": runtime.predictor.metrics,
            "feature_importances": runtime.predictor.feature_importances,
            "test_actual_mins": runtime.predictor.last_test_y.tolist() if runtime.predictor.last_test_y is not None else [],
            "test_predicted_mins": runtime.predictor.last_pred_y.tolist() if runtime.predictor.last_pred_y is not None else [],
        })

    @app.get("/api/zones")
    def zone_analysis():
        state = current_state()
        with state["lock"]:
            if len(state["deliveries"]) < 2:
                return jsonify({"k": [], "inertia": [], "stops": state["deliveries"]})
            stops = [dict(state["depot"] or {"type": "depot"})] + [
                dict(stop) for stop in state["deliveries"]
            ]
            k_values, inertias = compute_elbow_curve(stops, max_k=5)
            return jsonify({
                "k": k_values,
                "inertia": inertias,
                "stops": state["deliveries"],
                "clusters": state["clusters"],
            })

    return app


runtime: WebRuntime
