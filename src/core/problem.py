"""Problem formulation, state representation, and CSP constraints for the Route Optimizer.

Formulates the Delivery Route Problem on real road networks with:
- Configurable Round Trip (return to depot) vs Open Tour (finish at last delivery)
- Vehicle Capacity constraint (max package weight)
- Delivery Priority constraints (Urgent vs Normal delivery sequencing)
- Delivery Time Window checking and penalty calculation
- Realistic Journey Time estimation based on road distance and configurable speed
"""

from __future__ import annotations

import random
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class RouteProblem:
    """Encapsulates the delivery route optimization problem instance.

    Attributes:
        stops (List[Dict[str, Any]]): List of stop dictionaries.
        distance_matrix (np.ndarray): N x N matrix of road distances in km.
        depot (int): Index of the starting depot (default: 0).
        num_stops (int): Total number of stops (including depot).
        round_trip (bool): True if vehicle returns to depot, False if open tour.
        vehicle_capacity_kg (float): Maximum load capacity of delivery vehicle.
        vehicle_speed_kmh (float): Average vehicle travel speed in city traffic.
        service_time_mins (float): Unload/handover time at each delivery stop.
    """

    def __init__(
        self,
        stops: List[Dict[str, Any]],
        distance_matrix: np.ndarray,
        depot: int = 0,
        round_trip: bool = True,
        vehicle_capacity_kg: float = 50.0,
        vehicle_speed_kmh: float = 30.0,
        service_time_mins: float = 5.0
    ):
        """Initialize RouteProblem.

        Args:
            stops: List of stops (each must contain 'name', 'latitude', 'longitude').
            distance_matrix: N x N square numpy array of shortest road distances in km.
            depot: Index of the starting depot. Defaults to 0.
            round_trip: If True, vehicle must return to depot at end of route.
            vehicle_capacity_kg: Max payload weight in kilograms.
            vehicle_speed_kmh: Average city driving speed for journey time estimation.
            service_time_mins: Dwell/service time per delivery stop in minutes.
        """
        if len(stops) < 2:
            raise ValueError("RouteProblem requires at least 2 stops (1 depot and 1 delivery).")
        if distance_matrix.shape[0] != len(stops) or distance_matrix.shape[1] != len(stops):
            raise ValueError(
                f"Distance matrix shape {distance_matrix.shape} does not match stop count {len(stops)}."
            )
        if depot < 0 or depot >= len(stops):
            raise ValueError(f"Depot index {depot} is out of bounds [0, {len(stops)-1}].")

        self.stops = stops
        self.distance_matrix = distance_matrix
        self.depot = depot
        self.num_stops = len(stops)
        self.round_trip = round_trip
        self.vehicle_capacity_kg = float(vehicle_capacity_kg)
        self.vehicle_speed_kmh = max(5.0, float(vehicle_speed_kmh))
        self.service_time_mins = max(0.0, float(service_time_mins))

    def route_length(self, order: List[int]) -> float:
        """Compute total road distance of a given visiting order in km.

        Respects the `round_trip` setting.

        Args:
            order: List of stop indices.

        Returns:
            float: Total route road distance in kilometers.
        """
        if not order:
            raise ValueError("Route order cannot be empty.")

        full_tour = self.to_full_tour(order)

        total_distance = 0.0
        for i in range(len(full_tour) - 1):
            u = full_tour[i]
            v = full_tour[i + 1]
            total_distance += float(self.distance_matrix[u][v])

        return total_distance

    def estimate_journey_time(self, order: List[int]) -> float:
        """Compute estimated journey time in minutes.

        Formula:
            Travel Time = (Total Road Distance / Speed) * 60 minutes
            Total Time = Travel Time + (Service Time * Number of Deliveries)

        Returns:
            float: Estimated total journey time in minutes.
        """
        dist_km = self.route_length(order)
        travel_mins = (dist_km / self.vehicle_speed_kmh) * 60.0
        num_deliveries = self.num_stops - 1
        service_mins = num_deliveries * self.service_time_mins
        return travel_mins + service_mins

    def check_constraints(self, order: List[int]) -> Dict[str, Any]:
        """Evaluate CSP constraints: vehicle capacity, urgent priority, time windows.

        Args:
            order: Proposed visiting order.

        Returns:
            Dict[str, Any]: Constraint check summary with keys:
                - feasible (bool)
                - total_weight_kg (float)
                - capacity_ok (bool)
                - urgent_prioritized (bool)
                - time_windows_ok (bool)
                - violations (List[str])
                - est_journey_time_mins (float)
        """
        violations: List[str] = []
        full_tour = self.to_full_tour(order)

        # 1. Vehicle Capacity Constraint
        total_weight = 0.0
        for i in range(self.num_stops):
            if i != self.depot:
                total_weight += float(self.stops[i].get("weight_kg", 0.0))

        capacity_ok = total_weight <= self.vehicle_capacity_kg
        if not capacity_ok:
            violations.append(
                f"Capacity Exceeded: Total package weight ({total_weight:.1f} kg) "
                f"exceeds maximum vehicle payload ({self.vehicle_capacity_kg:.1f} kg)."
            )

        # 2. Priority Constraint (Urgent deliveries should be served before normal ones)
        # Find indices of urgent and normal deliveries in tour
        delivery_order = [s for s in full_tour if s != self.depot]
        urgent_positions = []
        normal_positions = []
        for pos, stop_idx in enumerate(delivery_order):
            prio = str(self.stops[stop_idx].get("priority", "Normal")).lower()
            if prio == "urgent":
                urgent_positions.append(pos)
            else:
                normal_positions.append(pos)

        urgent_prioritized = True
        if urgent_positions and normal_positions:
            # Check if any urgent delivery appears after a normal delivery
            latest_urgent = max(urgent_positions)
            earliest_normal = min(normal_positions)
            if latest_urgent > earliest_normal:
                urgent_prioritized = False
                violations.append(
                    f"Priority Notice: {len(urgent_positions)} urgent package(s) scheduled "
                    f"after regular deliveries in visiting order."
                )

        # 3. Time Windows Check
        time_windows_ok = True
        cum_time = 0.0
        for i in range(len(full_tour) - 1):
            u, v = full_tour[i], full_tour[i + 1]
            leg_km = float(self.distance_matrix[u][v])
            leg_travel_mins = (leg_km / self.vehicle_speed_kmh) * 60.0
            cum_time += leg_travel_mins

            if v != self.depot:
                cum_time += self.service_time_mins
                tw = self.stops[v].get("time_window", "Anytime")
                if tw and tw != "Anytime":
                    # Parse simple window format like "09:00 - 11:00" or integer minutes e.g. "60"
                    end_min = self._parse_time_window_end_min(tw)
                    if end_min is not None and cum_time > end_min:
                        time_windows_ok = False
                        violations.append(
                            f"Time Window Delayed: Delivery #{v} ('{self.stops[v]['name']}') "
                            f"arrives at ~{cum_time:.0f} mins, missing target window ({tw})."
                        )

        feasible = capacity_ok and (len(violations) == 0 or urgent_prioritized)

        return {
            "feasible": feasible,
            "total_weight_kg": total_weight,
            "capacity_ok": capacity_ok,
            "urgent_prioritized": urgent_prioritized,
            "time_windows_ok": time_windows_ok,
            "violations": violations,
            "est_journey_time_mins": self.estimate_journey_time(order)
        }

    def _parse_time_window_end_min(self, tw_str: str) -> Optional[float]:
        """Helper to parse time window deadline into elapsed minutes from departure."""
        try:
            s = str(tw_str).strip()
            if "min" in s.lower():
                return float(s.lower().replace("min", "").replace("s", "").strip())
            if "-" in s:
                parts = s.split("-")
                end_part = parts[1].strip()
                if ":" in end_part:
                    h, m = end_part.split(":")[:2]
                    # Assume shift starts at 09:00
                    return (float(h) - 9.0) * 60.0 + float(m)
            elif ":" in s:
                h, m = s.split(":")[:2]
                return (float(h) - 9.0) * 60.0 + float(m)
        except Exception:
            pass
        return None

    def fitness(self, order: List[int]) -> float:
        """Compute fitness of a route order for metaheuristic optimizers.

        Incorporates road distance, priority penalties, and time window delays:
            total_penalty_cost = road_length + priority_penalties
            fitness = 1.0 / (total_penalty_cost + 1e-9)

        Returns:
            float: Higher fitness indicates a superior route.
        """
        length = self.route_length(order)
        full_tour = self.to_full_tour(order)
        delivery_order = [s for s in full_tour if s != self.depot]

        # Priority penalty: penalize urgent orders that are placed late in sequence
        priority_penalty = 0.0
        n_del = len(delivery_order)
        for pos, stop_idx in enumerate(delivery_order):
            prio = str(self.stops[stop_idx].get("priority", "Normal")).lower()
            if prio == "urgent":
                # Position penalty: urgent stops placed later incur a small virtual distance penalty
                priority_penalty += (pos / max(1, n_del)) * 1.5

        total_cost = length + priority_penalty
        return 1.0 / (total_cost + 1e-9)

    def to_full_tour(self, order: List[int]) -> List[int]:
        """Convert a stop sequence into the canonical tour.

        If round_trip is True: [depot, s1, s2, ..., depot]
        If round_trip is False: [depot, s1, s2, ..., sm]
        """
        deliveries = [s for s in order if s != self.depot]

        if self.round_trip:
            return [self.depot] + deliveries + [self.depot]
        else:
            return [self.depot] + deliveries

    def random_solution(self, rng: Optional[random.Random] = None) -> List[int]:
        """Generate a random valid full delivery tour."""
        if rng is None:
            rng = random.Random(42)

        deliveries = [i for i in range(self.num_stops) if i != self.depot]
        rng.shuffle(deliveries)

        if self.round_trip:
            return [self.depot] + deliveries + [self.depot]
        else:
            return [self.depot] + deliveries

    def generate_neighbors(
        self,
        order: List[int],
        method: str = "2-opt"
    ) -> List[List[int]]:
        """Generate neighboring routes using 2-opt inversion or swap moves."""
        full_tour = self.to_full_tour(order)
        n = len(full_tour)
        neighbors: List[List[int]] = []

        if self.round_trip:
            # Internal delivery stops are indices 1 to n-2
            if n <= 3:
                return [list(full_tour)]
            end_limit = n - 1
        else:
            # Open tour: delivery stops are indices 1 to n-1
            if n <= 2:
                return [list(full_tour)]
            end_limit = n

        if method == "2-opt":
            for i in range(1, end_limit - 1):
                for j in range(i + 1, end_limit):
                    new_tour = full_tour[:i] + full_tour[i:j + 1][::-1] + full_tour[j + 1:]
                    neighbors.append(new_tour)
        elif method == "swap":
            for i in range(1, end_limit - 1):
                for j in range(i + 1, end_limit):
                    new_tour = list(full_tour)
                    new_tour[i], new_tour[j] = new_tour[j], new_tour[i]
                    neighbors.append(new_tour)
        else:
            raise ValueError(f"Unknown neighborhood operator '{method}'. Use '2-opt' or 'swap'.")

        return neighbors

    def sample_neighbor(
        self,
        order: List[int],
        rng: random.Random,
        method: str = "2-opt"
    ) -> List[int]:
        """Stochastically sample a single neighbor route for Simulated Annealing."""
        full_tour = self.to_full_tour(order)
        n = len(full_tour)

        if self.round_trip:
            if n <= 3:
                return list(full_tour)
            i = rng.randint(1, max(1, n - 3))
            j = rng.randint(i + 1, max(i + 1, n - 2))
        else:
            if n <= 2:
                return list(full_tour)
            i = rng.randint(1, max(1, n - 2))
            j = rng.randint(i + 1, max(i + 1, n - 1))

        if method == "2-opt":
            return full_tour[:i] + full_tour[i:j + 1][::-1] + full_tour[j + 1:]
        else:
            new_tour = list(full_tour)
            new_tour[i], new_tour[j] = new_tour[j], new_tour[i]
            return new_tour

    def validate_tour(self, order: List[int]) -> bool:
        """Verify that a tour visits every stop exactly once."""
        full_tour = self.to_full_tour(order)
        if self.round_trip:
            if len(full_tour) != self.num_stops + 1:
                return False
            if full_tour[0] != self.depot or full_tour[-1] != self.depot:
                return False
            deliveries = set(full_tour[1:-1])
        else:
            if len(full_tour) != self.num_stops:
                return False
            if full_tour[0] != self.depot:
                return False
            deliveries = set(full_tour[1:])

        expected = {i for i in range(self.num_stops) if i != self.depot}
        return deliveries == expected
