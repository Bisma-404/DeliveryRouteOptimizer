"""Intelligent Goal-Based Delivery Agent (AI Lab 2).

Implements a rational, goal-driven courier agent architecture operating within
the delivery vehicle simulation:
- Sensors & Percepts: Observes vehicle coordinates, road waypoint, stop proximity,
  cargo load, and customer order constraints.
- Goal Hierarchy:
    1. Primary Goal: Deliver all customer packages safely along the optimized road path.
    2. Priority Goal: Deliver urgent orders promptly.
    3. Terminal Goal: Return to starting depot with empty/accounted cargo.
- Action Selection: Rational decision function mapping current percepts to actions:
    NAVIGATE, ARRIVE, DELIVER, SKIP, RETURN_DEPOT, COMPLETE.
- State Maintenance: Tracks delivered stops, skipped packages, unloaded cargo weight,
  cumulative kilometers, and remaining capacity.
"""

from __future__ import annotations

import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)


class AgentAction(Enum):
    """Actions the delivery agent can choose to execute."""
    IDLE = "IDLE"
    NAVIGATE_ROAD = "NAVIGATE_ROAD"
    ARRIVE_AT_STOP = "ARRIVE_AT_STOP"
    DELIVER_PACKAGE = "DELIVER_PACKAGE"
    SKIP_PACKAGE = "SKIP_PACKAGE"
    RETURN_TO_DEPOT = "RETURN_TO_DEPOT"
    FINISH_TOUR = "FINISH_TOUR"


@dataclass
class DeliveryPercept:
    """Perceptual sensory input observed by the agent at the current time step."""
    current_lat: float
    current_lon: float
    waypoint_index: int
    total_waypoints: int
    current_stop_id: Optional[int]
    is_at_stop: bool
    distance_to_current_goal_m: float
    goal_stop_data: Optional[Dict[str, Any]]
    remaining_cargo_kg: float
    pending_count: int


class GoalBasedDeliveryAgent:
    """Intelligent goal-driven delivery vehicle agent."""

    def __init__(
        self,
        tour: List[int],
        stops: List[Dict[str, Any]],
        route_coords: List[Tuple[float, float]],
        vehicle_capacity_kg: float = 50.0
    ):
        """Initialize GoalBasedDeliveryAgent.

        Args:
            tour: Optimized visiting order [depot, s1, s2, ..., depot].
            stops: List of all stop dictionaries.
            route_coords: Fine-grained road coordinates curve.
            vehicle_capacity_kg: Maximum payload capacity.
        """
        self.tour = list(tour)
        self.stops = stops
        self.route_coords = route_coords
        self.vehicle_capacity_kg = float(vehicle_capacity_kg)

        # Calculate initial loaded cargo
        self.total_initial_cargo_kg = sum(
            float(self.stops[s].get("weight_kg", 5.0))
            for s in self.tour if s != 0
        )
        self.remaining_cargo_kg = self.total_initial_cargo_kg

        # Progress tracking
        self.current_tour_step = 0  # Index into self.tour
        self.completed_stops: List[int] = []
        self.skipped_stops: List[int] = []
        self.current_action: AgentAction = AgentAction.IDLE
        self.action_reason: str = "Agent initialized at starting depot."
        self.total_distance_traveled_km = 0.0

    @property
    def current_goal_stop_idx(self) -> int:
        """Stop index of the current target goal."""
        if self.current_tour_step < len(self.tour):
            return self.tour[self.current_tour_step]
        return self.tour[-1]

    @property
    def current_goal_stop_data(self) -> Dict[str, Any]:
        """Data dict for the current target stop."""
        idx = self.current_goal_stop_idx
        return self.stops[idx] if idx < len(self.stops) else {}

    @property
    def is_finished(self) -> bool:
        """True if all tour stops have been completed and vehicle has returned to depot."""
        return self.current_tour_step >= len(self.tour)

    def perceive(
        self,
        lat: float,
        lon: float,
        waypoint_idx: int,
        is_at_stop: bool,
        stop_id: Optional[int]
    ) -> DeliveryPercept:
        """Formulate a percept from simulator environment readings."""
        goal_data = self.current_goal_stop_data
        goal_lat = float(goal_data.get("latitude", lat))
        goal_lon = float(goal_data.get("longitude", lon))

        # Rough distance to current target goal
        from .astar import haversine_distance
        dist_m = haversine_distance(lat, lon, goal_lat, goal_lon)

        pending = max(0, len(self.tour) - 1 - len(self.completed_stops) - len(self.skipped_stops))

        return DeliveryPercept(
            current_lat=lat,
            current_lon=lon,
            waypoint_index=waypoint_idx,
            total_waypoints=len(self.route_coords),
            current_stop_id=stop_id,
            is_at_stop=is_at_stop,
            distance_to_current_goal_m=dist_m,
            goal_stop_data=goal_data,
            remaining_cargo_kg=self.remaining_cargo_kg,
            pending_count=pending
        )

    def decide_action(self, percept: DeliveryPercept) -> Tuple[AgentAction, str]:
        """Rational decision function selecting the optimal action toward the current goal."""
        if self.is_finished:
            self.current_action = AgentAction.FINISH_TOUR
            self.action_reason = "Mission accomplished: All deliveries processed and vehicle parked at depot."
            return self.current_action, self.action_reason

        goal_data = percept.goal_stop_data or {}
        is_depot = (self.current_goal_stop_idx == 0)

        if percept.is_at_stop and percept.current_stop_id == self.current_goal_stop_idx:
            if is_depot:
                if self.current_tour_step == 0:
                    # Starting dispatch
                    self.current_action = AgentAction.NAVIGATE_ROAD
                    self.action_reason = "Departing depot; accelerating onto road network toward Stop #1."
                else:
                    # Final return
                    self.current_action = AgentAction.FINISH_TOUR
                    self.action_reason = "Returned to depot. Mission complete."
            else:
                self.current_action = AgentAction.ARRIVE_AT_STOP
                cust = goal_data.get("name", "Customer")
                wt = float(goal_data.get("weight_kg", 5.0))
                prio = goal_data.get("priority", "Normal")
                self.action_reason = f"Arrived at {cust} (Weight: {wt}kg, Priority: {prio}). Ready to deliver."
            return self.current_action, self.action_reason

        # In transit along road
        if is_depot and self.current_tour_step == len(self.tour) - 1:
            self.current_action = AgentAction.RETURN_TO_DEPOT
            self.action_reason = f"All customers served. Navigating back to depot ({percept.distance_to_current_goal_m:.0f}m away)."
        else:
            self.current_action = AgentAction.NAVIGATE_ROAD
            target_name = goal_data.get("name", f"Stop #{self.current_goal_stop_idx}")
            self.action_reason = f"Driving to {target_name} ({percept.distance_to_current_goal_m:.0f}m remaining)."

        return self.current_action, self.action_reason

    def complete_current_delivery(self) -> Dict[str, Any]:
        """Execute delivery action at the current stop."""
        idx = self.current_goal_stop_idx
        data = self.current_goal_stop_data
        pkg_wt = float(data.get("weight_kg", 5.0))

        self.remaining_cargo_kg = max(0.0, self.remaining_cargo_kg - pkg_wt)
        self.completed_stops.append(idx)
        self.current_tour_step += 1
        self.current_action = AgentAction.DELIVER_PACKAGE
        self.action_reason = f"Delivered package to {data.get('name', f'Stop #{idx}')} (-{pkg_wt:.1f}kg unloaded)."

        return {
            "status": "Delivered",
            "stop_id": idx,
            "name": data.get("name"),
            "unloaded_kg": pkg_wt,
            "remaining_cargo_kg": self.remaining_cargo_kg,
            "next_goal": self.current_goal_stop_data.get("name")
        }

    def skip_current_delivery(self) -> Dict[str, Any]:
        """Execute skip action (customer absent, access restricted)."""
        idx = self.current_goal_stop_idx
        data = self.current_goal_stop_data

        self.skipped_stops.append(idx)
        self.current_tour_step += 1
        self.current_action = AgentAction.SKIP_PACKAGE
        self.action_reason = f"Skipped delivery at {data.get('name', f'Stop #{idx}')}; package retained in cargo."

        return {
            "status": "Skipped",
            "stop_id": idx,
            "name": data.get("name"),
            "remaining_cargo_kg": self.remaining_cargo_kg,
            "next_goal": self.current_goal_stop_data.get("name")
        }

    def get_telemetry(self) -> Dict[str, Any]:
        """Structured telemetry dictionary for GUI simulation overlay."""
        total_deliveries = max(1, len(self.tour) - 2 if self.tour[0] == self.tour[-1] else len(self.tour) - 1)
        delivered_count = len([s for s in self.completed_stops if s != 0])
        skipped_count = len([s for s in self.skipped_stops if s != 0])
        pct_done = ((delivered_count + skipped_count) / total_deliveries) * 100.0

        return {
            "action": self.current_action.value,
            "reason": self.action_reason,
            "current_goal": self.current_goal_stop_data.get("name", "Depot"),
            "remaining_cargo_kg": self.remaining_cargo_kg,
            "total_initial_cargo_kg": self.total_initial_cargo_kg,
            "delivered_count": delivered_count,
            "skipped_count": skipped_count,
            "total_deliveries": total_deliveries,
            "progress_pct": min(100.0, pct_done),
            "is_finished": self.is_finished
        }
