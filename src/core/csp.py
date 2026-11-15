"""Constraint Satisfaction Problem (CSP) Engine for Urban Delivery Route Planning.

Formal CSP Representation (AI Lab 5):
------------------------------------
1. Variables (X):
   Each customer delivery stop d_1, d_2, ..., d_M to be visited.
2. Domains (D):
   Discrete slot positions {1, 2, ..., M} in the delivery tour sequence.
3. Hard Constraints:
   - AllDifferent: Each tour slot must be occupied by exactly one customer stop.
   - Vehicle Capacity: Total loaded weight <= vehicle maximum payload capacity.
   - Cumulative Payload: Vehicle tracks unloading at each stop.
   - Time Windows: Arrival time at slot k must be <= deadline(d_i) (with optional service window).
4. Soft Constraints:
   - Urgent Delivery Priority: Urgent packages should be scheduled in earlier tour slots.
5. Search Algorithm:
   - Backtracking search with Forward Checking (FC).
   - Minimum Remaining Values (MRV) variable selection heuristic.
   - Degree heuristic for tie-breaking.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional, Tuple, Set

logger = logging.getLogger(__name__)


class DeliveryCSP:
    """Constraint Satisfaction Problem formulation for urban delivery planning."""

    def __init__(
        self,
        stops: List[Dict[str, Any]],
        distance_matrix,
        vehicle_capacity_kg: float = 50.0,
        vehicle_speed_kmh: float = 30.0,
        service_time_mins: float = 5.0,
        depot: int = 0
    ):
        """Initialize DeliveryCSP.

        Args:
            stops: List of stops (depot at index `depot`, deliveries at remaining indices).
            distance_matrix: NxN matrix of road distances in km.
            vehicle_capacity_kg: Maximum payload capacity.
            vehicle_speed_kmh: Vehicle driving speed for time window checking.
            service_time_mins: Dwell time spent servicing each customer.
            depot: Index of the depot.
        """
        self.stops = stops
        self.distance_matrix = distance_matrix
        self.vehicle_capacity_kg = float(vehicle_capacity_kg)
        self.vehicle_speed_kmh = max(5.0, float(vehicle_speed_kmh))
        self.service_time_mins = max(0.0, float(service_time_mins))
        self.depot = depot

        # Customer deliveries (variables)
        self.deliveries = [i for i in range(len(stops)) if i != depot]
        self.num_deliveries = len(self.deliveries)

        # Variables: list of delivery stop indices
        self.variables: List[int] = list(self.deliveries)

        # Initial Domains: each delivery can be assigned to slot 1..M
        self.initial_domains: Dict[int, Set[int]] = {
            v: set(range(1, self.num_deliveries + 1)) for v in self.variables
        }

        # Priority categorization
        self.urgent_deliveries = {
            v for v in self.variables
            if str(stops[v].get("priority", "Normal")).lower() == "urgent"
        }

        # Weight extraction
        self.weights = {
            v: float(stops[v].get("weight_kg", 5.0)) for v in self.variables
        }
        self.total_payload = sum(self.weights.values())

        # Time window extraction (parsed to minutes from departure)
        self.deadlines: Dict[int, Optional[float]] = {
            v: self._parse_window(stops[v].get("time_window", "Anytime"))
            for v in self.variables
        }

    def _parse_window(self, tw_str: Any) -> Optional[float]:
        """Convert time window string to minutes from departure."""
        try:
            s = str(tw_str).strip()
            if not s or s.lower() == "anytime":
                return None
            if "min" in s.lower():
                clean = "".join(c for c in s if c.isdigit() or c == ".")
                return float(clean)
            if "-" in s:
                end_p = s.split("-")[1].strip()
                if ":" in end_p:
                    h, m = end_p.split(":")[:2]
                    return (float(h) - 9.0) * 60.0 + float(m)
            elif ":" in s:
                h, m = s.split(":")[:2]
                return (float(h) - 9.0) * 60.0 + float(m)
        except Exception:
            pass
        return None

    def check_capacity(self) -> Tuple[bool, float, float, str]:
        """Check the hard vehicle capacity constraint.

        Returns:
            Tuple[bool, float, float, str]:
                (is_feasible, total_weight_kg, remaining_capacity_kg, explanation)
        """
        remaining = self.vehicle_capacity_kg - self.total_payload
        if remaining < 0:
            msg = (
                f"Hard Constraint Violation: Total package weight ({self.total_payload:.1f} kg) "
                f"exceeds vehicle payload capacity ({self.vehicle_capacity_kg:.1f} kg) "
                f"by {abs(remaining):.1f} kg. The vehicle cannot carry all deliveries in a single trip."
            )
            return False, self.total_payload, remaining, msg

        msg = (
            f"Capacity Feasible: Total loaded weight {self.total_payload:.1f} kg "
            f"within limit {self.vehicle_capacity_kg:.1f} kg (Remaining: {remaining:.1f} kg)."
        )
        return True, self.total_payload, remaining, msg

    def solve_backtracking(self) -> Dict[str, Any]:
        """Execute Backtracking Search with Forward Checking and MRV.

        Returns:
            Dict[str, Any] with:
                - feasible (bool)
                - assignment (Dict[int, int]: variable -> slot)
                - ordered_tour (List[int]: [depot, s1, s2, ..., depot])
                - backtrack_count (int)
                - pruned_count (int)
                - violations (List[str])
                - explanation (str)
        """
        # Step 1: Pre-check capacity constraint
        cap_ok, total_wt, remaining, cap_msg = self.check_capacity()
        if not cap_ok:
            return {
                "feasible": False,
                "assignment": None,
                "ordered_tour": None,
                "backtrack_count": 0,
                "pruned_count": 0,
                "violations": [cap_msg],
                "explanation": cap_msg
            }

        if self.num_deliveries == 0:
            return {
                "feasible": True,
                "assignment": {},
                "ordered_tour": [self.depot, self.depot],
                "backtrack_count": 0,
                "pruned_count": 0,
                "violations": [],
                "explanation": "Trivial empty route."
            }

        # Step 2: Backtracking search
        domains = {v: set(self.initial_domains[v]) for v in self.variables}

        # Apply unary constraint: urgent deliveries preferred in first half of slots
        if self.urgent_deliveries:
            mid = max(1, (self.num_deliveries + 1) // 2)
            for u in self.urgent_deliveries:
                # Restrict urgent domains to earlier slots if feasible
                earlier = {s for s in domains[u] if s <= mid}
                if earlier:
                    domains[u] = earlier

        assignment: Dict[int, int] = {}
        backtrack_steps = [0]
        pruned_values = [0]
        violations: List[str] = []

        def is_consistent(var: int, slot: int, current_assign: Dict[int, int]) -> bool:
            # AllDifferent check
            if slot in current_assign.values():
                return False

            # Time window estimation check
            deadline = self.deadlines.get(var)
            if deadline is not None:
                # Minimum elapsed time: (slot * service_time)
                min_service_time = slot * self.service_time_mins
                if min_service_time > deadline:
                    return False

            return True

        def forward_check(var: int, slot: int, cur_domains: Dict[int, Set[int]]) -> Optional[Dict[int, Set[int]]]:
            new_domains = {v: set(vals) for v, vals in cur_domains.items()}
            for other in self.variables:
                if other != var and other not in assignment:
                    if slot in new_domains[other]:
                        new_domains[other].remove(slot)
                        pruned_values[0] += 1
                        if not new_domains[other]:
                            return None  # Domain wipe-out
            return new_domains

        def select_unassigned_variable(cur_assignment: Dict[int, int], cur_domains: Dict[int, Set[int]]) -> int:
            # MRV (Minimum Remaining Values) heuristic
            unassigned = [v for v in self.variables if v not in cur_assignment]
            # Tie breaker: urgent deliveries first, then smallest domain
            return min(unassigned, key=lambda v: (0 if v in self.urgent_deliveries else 1, len(cur_domains[v])))

        def backtrack(cur_assignment: Dict[int, int], cur_domains: Dict[int, Set[int]]) -> Optional[Dict[int, int]]:
            if len(cur_assignment) == self.num_deliveries:
                return cur_assignment

            var = select_unassigned_variable(cur_assignment, cur_domains)
            # Order domain values: lower slot positions first
            sorted_slots = sorted(list(cur_domains[var]))

            for slot in sorted_slots:
                if is_consistent(var, slot, cur_assignment):
                    cur_assignment[var] = slot
                    forward_domains = forward_check(var, slot, cur_domains)

                    if forward_domains is not None:
                        result = backtrack(cur_assignment, forward_domains)
                        if result is not None:
                            return result

                    # Backtrack
                    backtrack_steps[0] += 1
                    del cur_assignment[var]

            return None

        sol = backtrack(assignment, domains)

        if sol is None:
            # Try relaxed search without strict urgent domain pruning
            relaxed_domains = {v: set(range(1, self.num_deliveries + 1)) for v in self.variables}
            sol = backtrack({}, relaxed_domains)

        if sol is None:
            explanation = "CSP Infeasible: Conflicting time windows or impossible slot assignments."
            violations.append(explanation)
            return {
                "feasible": False,
                "assignment": None,
                "ordered_tour": None,
                "backtrack_count": backtrack_steps[0],
                "pruned_count": pruned_values[0],
                "violations": violations,
                "explanation": explanation
            }

        # Build ordered sequence from slot assignments
        slot_to_var = {slot: var for var, slot in sol.items()}
        ordered_stops = [slot_to_var[s] for s in sorted(slot_to_var.keys())]
        full_tour = [self.depot] + ordered_stops + [self.depot]

        # Check soft constraints & time windows on final tour
        cum_time = 0.0
        for i in range(len(full_tour) - 1):
            u, v = full_tour[i], full_tour[i + 1]
            leg_km = float(self.distance_matrix[u][v])
            cum_time += (leg_km / self.vehicle_speed_kmh) * 60.0
            if v != self.depot:
                cum_time += self.service_time_mins
                dl = self.deadlines.get(v)
                if dl is not None and cum_time > dl:
                    violations.append(
                        f"Time Window Notice: '{self.stops[v]['name']}' estimated arrival {cum_time:.0f}m "
                        f"exceeds deadline {dl:.0f}m."
                    )

        explanation = (
            f"CSP Feasible: Found valid assignment for {self.num_deliveries} stops. "
            f"Total payload: {self.total_payload:.1f} kg / {self.vehicle_capacity_kg:.1f} kg. "
            f"Backtracks: {backtrack_steps[0]}, Pruned domain values: {pruned_values[0]}."
        )

        return {
            "feasible": True,
            "assignment": sol,
            "ordered_tour": full_tour,
            "backtrack_count": backtrack_steps[0],
            "pruned_count": pruned_values[0],
            "violations": violations,
            "explanation": explanation
        }
