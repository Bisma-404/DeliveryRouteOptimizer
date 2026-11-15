"""Shortest Path Road Planners (A*, UCS, BFS, DFS) with Haversine Heuristic.

This module implements:
1. Custom A* Search using Python's heapq priority queue and admissible Haversine heuristic.
   DOES NOT use networkx.astar_path.
2. Uniform Cost Search (UCS / Dijkstra) baseline.
3. Breadth-First Search (BFS) for hop-minimal road paths.
4. Depth-First Search (DFS) with cycle and depth bounds.
5. All-pairs road distance matrix computation with node expansion tracking.
6. Continuous road polyline geometry extraction for map rendering.
"""

import math
import heapq
import collections
import logging
from typing import List, Tuple, Dict, Any, Optional
import networkx as nx
import numpy as np
from shapely import wkt
from shapely.geometry import LineString

logger = logging.getLogger(__name__)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance between two GPS coordinates in meters."""
    earth_radius_m = 6371000.0

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    sin_half_phi = math.sin(delta_phi / 2.0)
    sin_half_lambda = math.sin(delta_lambda / 2.0)

    a = (sin_half_phi ** 2) + math.cos(phi1) * math.cos(phi2) * (sin_half_lambda ** 2)
    a = max(0.0, min(1.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return earth_radius_m * c


class AStarPlanner:
    """Shortest path road planner supporting A*, UCS, BFS, and DFS searches."""

    def __init__(self, graph: nx.MultiDiGraph, heuristic=None):
        """Initialize AStarPlanner."""
        self.graph = graph
        self.heuristic = heuristic if heuristic is not None else haversine_distance

    def _heuristic_cost(self, u: int, goal: int) -> float:
        """Compute the heuristic h(u, goal) using node coordinate attributes."""
        u_lat = self.graph.nodes[u]["y"]
        u_lon = self.graph.nodes[u]["x"]
        g_lat = self.graph.nodes[goal]["y"]
        g_lon = self.graph.nodes[goal]["x"]
        return self.heuristic(u_lat, u_lon, g_lat, g_lon)

    def _path_distance_meters(self, path: List[int]) -> float:
        """Calculate total road length of a node path in meters."""
        if not path or len(path) < 2:
            return 0.0
        total_m = 0.0
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            if u in self.graph and v in self.graph[u]:
                edge_dict = self.graph[u][v]
                min_len = min(float(data.get("length", 1.0)) for data in edge_dict.values())
                total_m += min_len
        return total_m

    def shortest_path(
        self,
        start_node: int,
        goal_node: int
    ) -> Tuple[Optional[List[int]], float, int]:
        """Find the shortest path from start_node to goal_node using custom A*.

        Uses heapq priority queue. Does NOT use networkx.astar_path.
        """
        if start_node == goal_node:
            return [start_node], 0.0, 0

        counter = 0
        h_start = self._heuristic_cost(start_node, goal_node)
        open_set = [(h_start, 0.0, counter, start_node)]
        heapq.heapify(open_set)

        g_score: Dict[int, float] = {start_node: 0.0}
        came_from: Dict[int, int] = {}
        closed_set = set()
        nodes_expanded = 0

        while open_set:
            f, g, _, current = heapq.heappop(open_set)

            if current in closed_set:
                continue

            closed_set.add(current)
            nodes_expanded += 1

            if current == goal_node:
                path = [current]
                curr = current
                while curr in came_from:
                    curr = came_from[curr]
                    path.append(curr)
                path.reverse()
                return path, g, nodes_expanded

            if current not in self.graph:
                continue

            for neighbor, edge_dict in self.graph[current].items():
                if neighbor in closed_set:
                    continue

                min_edge_len = min(
                    float(data.get("length", 1.0)) for data in edge_dict.values()
                )
                tentative_g = g + min_edge_len

                if tentative_g < g_score.get(neighbor, float("inf")):
                    g_score[neighbor] = tentative_g
                    came_from[neighbor] = current
                    h = self._heuristic_cost(neighbor, goal_node)
                    f_neighbor = tentative_g + h
                    counter += 1
                    heapq.heappush(open_set, (f_neighbor, tentative_g, counter, neighbor))

        return None, float("inf"), nodes_expanded

    def astar_search(self, start_node: int, goal_node: int):
        return self.shortest_path(start_node, goal_node)

    def uninformed_search(
        self,
        start_node: int,
        goal_node: int
    ) -> Tuple[Optional[List[int]], float, int]:
        """Uniform Cost Search (Dijkstra) baseline with h(u) = 0."""
        if start_node == goal_node:
            return [start_node], 0.0, 0

        counter = 0
        open_set = [(0.0, counter, start_node)]
        g_score: Dict[int, float] = {start_node: 0.0}
        came_from: Dict[int, int] = {}
        closed_set = set()
        nodes_expanded = 0

        while open_set:
            g, _, current = heapq.heappop(open_set)

            if current in closed_set:
                continue

            closed_set.add(current)
            nodes_expanded += 1

            if current == goal_node:
                path = [current]
                curr = current
                while curr in came_from:
                    curr = came_from[curr]
                    path.append(curr)
                path.reverse()
                return path, g, nodes_expanded

            if current not in self.graph:
                continue

            for neighbor, edge_dict in self.graph[current].items():
                if neighbor in closed_set:
                    continue

                min_edge_len = min(
                    float(data.get("length", 1.0)) for data in edge_dict.values()
                )
                tentative_g = g + min_edge_len

                if tentative_g < g_score.get(neighbor, float("inf")):
                    g_score[neighbor] = tentative_g
                    came_from[neighbor] = current
                    counter += 1
                    heapq.heappush(open_set, (tentative_g, counter, neighbor))

        return None, float("inf"), nodes_expanded

    def ucs_search(self, start_node: int, goal_node: int):
        return self.uninformed_search(start_node, goal_node)

    def bfs_search(
        self,
        start_node: int,
        goal_node: int
    ) -> Tuple[Optional[List[int]], float, int]:
        """Breadth-First Search (BFS) finding hop-minimal paths on road network."""
        if start_node == goal_node:
            return [start_node], 0.0, 0

        queue = collections.deque([start_node])
        came_from: Dict[int, int] = {}
        visited = {start_node}
        nodes_expanded = 0

        while queue:
            current = queue.popleft()
            nodes_expanded += 1

            if current == goal_node:
                path = [current]
                curr = current
                while curr in came_from:
                    curr = came_from[curr]
                    path.append(curr)
                path.reverse()
                dist_m = self._path_distance_meters(path)
                return path, dist_m, nodes_expanded

            if current not in self.graph:
                continue

            for neighbor in self.graph[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    came_from[neighbor] = current
                    queue.append(neighbor)

        return None, float("inf"), nodes_expanded

    def dfs_search(
        self,
        start_node: int,
        goal_node: int,
        max_depth: int = 250
    ) -> Tuple[Optional[List[int]], float, int]:
        """Depth-First Search (DFS) with cycle avoidance and depth limits."""
        if start_node == goal_node:
            return [start_node], 0.0, 0

        stack = [(start_node, 0)]
        came_from: Dict[int, int] = {}
        visited = {start_node}
        nodes_expanded = 0

        while stack:
            current, depth = stack.pop()
            nodes_expanded += 1

            if current == goal_node:
                path = [current]
                curr = current
                while curr in came_from:
                    curr = came_from[curr]
                    path.append(curr)
                path.reverse()
                dist_m = self._path_distance_meters(path)
                return path, dist_m, nodes_expanded

            if depth >= max_depth or current not in self.graph:
                continue

            for neighbor in self.graph[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    came_from[neighbor] = current
                    stack.append((neighbor, depth + 1))

        return None, float("inf"), nodes_expanded

    def find_path(
        self,
        start_node: int,
        goal_node: int,
        method: str = "astar"
    ) -> Tuple[Optional[List[int]], float, int]:
        """Unified pathfinder dispatching to chosen search technique."""
        m = method.lower().strip()
        if m in ("astar", "a*", "a_star"):
            return self.shortest_path(start_node, goal_node)
        elif m in ("ucs", "dijkstra", "uninformed"):
            return self.uninformed_search(start_node, goal_node)
        elif m == "bfs":
            return self.bfs_search(start_node, goal_node)
        elif m == "dfs":
            return self.dfs_search(start_node, goal_node)
        else:
            return self.shortest_path(start_node, goal_node)

    def build_distance_matrix(
        self,
        stops: List[Dict[str, Any]],
        search_method: str = "astar"
    ) -> Tuple[np.ndarray, Dict[Tuple[int, int], List[int]], int]:
        """Compute all-pairs shortest road distance matrix connecting customer stops."""
        n = len(stops)
        dist_matrix = np.zeros((n, n), dtype=float)
        detailed_paths: Dict[Tuple[int, int], List[int]] = {}
        total_nodes_expanded = 0

        for i in range(n):
            u_node = stops[i]["nearest_node"]
            dist_matrix[i][i] = 0.0
            node_i_lat = float(self.graph.nodes[u_node]["y"])
            node_i_lon = float(self.graph.nodes[u_node]["x"])
            snap_dist_i = haversine_distance(stops[i]["latitude"], stops[i]["longitude"], node_i_lat, node_i_lon) / 1000.0

            for j in range(n):
                if i == j:
                    detailed_paths[(i, j)] = [u_node]
                    continue

                v_node = stops[j]["nearest_node"]
                node_j_lat = float(self.graph.nodes[v_node]["y"])
                node_j_lon = float(self.graph.nodes[v_node]["x"])
                snap_dist_j = haversine_distance(stops[j]["latitude"], stops[j]["longitude"], node_j_lat, node_j_lon) / 1000.0

                if u_node == v_node:
                    direct_km = haversine_distance(
                        stops[i]["latitude"], stops[i]["longitude"],
                        stops[j]["latitude"], stops[j]["longitude"]
                    ) / 1000.0
                    dist_matrix[i][j] = direct_km
                    detailed_paths[(i, j)] = [u_node]
                else:
                    path, dist_m, nodes_exp = self.find_path(u_node, v_node, method=search_method)
                    total_nodes_expanded += nodes_exp

                    if path is None:
                        direct_km = haversine_distance(
                            stops[i]["latitude"], stops[i]["longitude"],
                            stops[j]["latitude"], stops[j]["longitude"]
                        ) / 1000.0
                        dist_matrix[i][j] = direct_km
                        detailed_paths[(i, j)] = [u_node, v_node]
                    else:
                        road_km = dist_m / 1000.0
                        dist_matrix[i][j] = road_km + snap_dist_i + snap_dist_j
                        detailed_paths[(i, j)] = path

        logger.info(
            "Built %dx%d distance matrix via %s. Total nodes expanded: %d",
            n, n, search_method.upper(), total_nodes_expanded
        )
        return dist_matrix, detailed_paths, total_nodes_expanded

    def get_detailed_route_coordinates(
        self,
        route_order: List[int],
        detailed_paths: Dict[Tuple[int, int], List[int]],
        stops: Optional[List[Dict[str, Any]]] = None
    ) -> List[Tuple[float, float]]:
        """Extract continuous (latitude, longitude) road coordinates along the route."""
        full_coords: List[Tuple[float, float]] = []

        if not route_order or len(route_order) < 2:
            return full_coords

        for leg_idx in range(len(route_order) - 1):
            u_idx = route_order[leg_idx]
            v_idx = route_order[leg_idx + 1]

            # Start point: stop's actual coordinate
            if stops and u_idx < len(stops):
                stop_pt = (float(stops[u_idx]["latitude"]), float(stops[u_idx]["longitude"]))
                if not full_coords or full_coords[-1] != stop_pt:
                    full_coords.append(stop_pt)

            node_path = detailed_paths.get((u_idx, v_idx), [])
            if node_path:
                for step in range(len(node_path) - 1):
                    u = node_path[step]
                    v = node_path[step + 1]

                    edge_coords = self._get_edge_geometry_coords(u, v)
                    if edge_coords:
                        if full_coords and full_coords[-1] == edge_coords[0]:
                            full_coords.extend(edge_coords[1:])
                        else:
                            full_coords.extend(edge_coords)
                    else:
                        u_lat, u_lon = self.graph.nodes[u]["y"], self.graph.nodes[u]["x"]
                        v_lat, v_lon = self.graph.nodes[v]["y"], self.graph.nodes[v]["x"]
                        if not full_coords or full_coords[-1] != (u_lat, u_lon):
                            full_coords.append((u_lat, u_lon))
                        full_coords.append((v_lat, v_lon))

            # End point: destination stop's actual coordinate
            if stops and v_idx < len(stops):
                dest_pt = (float(stops[v_idx]["latitude"]), float(stops[v_idx]["longitude"]))
                if not full_coords or full_coords[-1] != dest_pt:
                    full_coords.append(dest_pt)

        return full_coords

    def _get_edge_geometry_coords(self, u: int, v: int) -> Optional[List[Tuple[float, float]]]:
        """Extract road curve coordinates from edge attributes if present."""
        if u not in self.graph or v not in self.graph[u]:
            return None

        edge_dict = self.graph[u][v]
        best_key = min(edge_dict.keys(), key=lambda k: edge_dict[k].get("length", 1.0))
        edge_data = edge_dict[best_key]

        if "geometry" in edge_data:
            geom = edge_data["geometry"]
            try:
                if isinstance(geom, str):
                    geom = wkt.loads(geom)
                if isinstance(geom, LineString):
                    return [(float(pt[1]), float(pt[0])) for pt in geom.coords]
            except Exception:
                pass

        return None
