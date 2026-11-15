"""Spatial Clustering for Delivery Route Planning using K-Means.

Groups nearby customer delivery stops into geographic clusters to:
1. Divide deliveries into manageable spatial zones.
2. Provide cluster-first visiting sequence heuristics.
3. Visually distinguish delivery clusters on the interactive map.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from sklearn.cluster import KMeans

logger = logging.getLogger(__name__)

# High-contrast cluster colors for map markers and UI badges
CLUSTER_COLORS = [
    "#3B82F6",  # Blue
    "#F59E0B",  # Amber
    "#10B981",  # Emerald
    "#8B5CF6",  # Purple
    "#EC4899",  # Pink
    "#06B6D4",  # Cyan
]


def cluster_delivery_stops(
    stops: List[Dict[str, Any]],
    n_clusters: Optional[int] = None
) -> Tuple[List[Dict[str, Any]], Dict[int, List[int]], Dict[str, Any]]:
    """Cluster delivery stops using K-Means spatial clustering.

    Depot (stop 0) remains unclustered (cluster -1).

    Args:
        stops: List of stop dictionaries with 'latitude' and 'longitude'.
        n_clusters: Number of clusters (optional, auto-computed if None).

    Returns:
        Tuple:
            - updated_stops: Stops with added 'cluster' and 'cluster_color' keys.
            - clusters_dict: Mapping of cluster_id -> list of stop indices.
            - summary: Dict with cluster statistics (counts, total weights).
    """
    if len(stops) <= 2:
        # Depot + 1 delivery, no meaningful clustering
        updated = [dict(s) for s in stops]
        for s in updated:
            s["cluster"] = 0
            s["cluster_color"] = CLUSTER_COLORS[0]
        return updated, {0: list(range(len(stops)))}, {"n_clusters": 1, "clusters": {}}

    # Deliveries excluding depot
    delivery_indices = [i for i in range(len(stops)) if i != 0 and stops[i].get("type") != "depot"]
    coords = np.array([[stops[i]["latitude"], stops[i]["longitude"]] for i in delivery_indices])

    # Determine optimal k
    num_deliveries = len(delivery_indices)
    if n_clusters is None:
        if num_deliveries <= 4:
            k = 2
        elif num_deliveries <= 9:
            k = 3
        else:
            k = min(4, max(2, num_deliveries // 4))
    else:
        k = max(2, min(n_clusters, num_deliveries))

    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = kmeans.fit_predict(coords)

    updated_stops = [dict(s) for s in stops]
    clusters_dict: Dict[int, List[int]] = {c: [] for c in range(k)}

    # Depot marker
    updated_stops[0]["cluster"] = -1
    updated_stops[0]["cluster_color"] = "#10B981"  # Emerald for depot

    for idx, stop_i in enumerate(delivery_indices):
        c_id = int(labels[idx])
        color = CLUSTER_COLORS[c_id % len(CLUSTER_COLORS)]
        updated_stops[stop_i]["cluster"] = c_id
        updated_stops[stop_i]["cluster_color"] = color
        clusters_dict[c_id].append(stop_i)

    # Build cluster summary
    clusters_info = {}
    for c_id, stop_list in clusters_dict.items():
        tot_wt = sum(float(updated_stops[si].get("weight_kg", 0.0)) for si in stop_list)
        urgent_count = sum(1 for si in stop_list if str(updated_stops[si].get("priority", "")).lower() == "urgent")
        clusters_info[c_id] = {
            "name": f"Zone {chr(65 + c_id)}",  # Zone A, Zone B, etc.
            "color": CLUSTER_COLORS[c_id % len(CLUSTER_COLORS)],
            "count": len(stop_list),
            "total_weight_kg": tot_wt,
            "urgent_count": urgent_count,
            "stop_names": [updated_stops[si]["name"] for si in stop_list]
        }

    summary = {
        "n_clusters": k,
        "clusters": clusters_info
    }

    logger.info("Grouped %d deliveries into %d spatial zones via K-Means", num_deliveries, k)
    return updated_stops, clusters_dict, summary


def get_cluster_first_tour(
    problem,
    clusters_dict: Dict[int, List[int]]
) -> List[int]:
    """Generate a Cluster-First initial delivery tour.

    Visits delivery stops grouped by geographic zone to minimize inter-zone travel.

    Args:
        problem: RouteProblem instance.
        clusters_dict: Cluster mapping from cluster_delivery_stops.

    Returns:
        List[int]: Canonical tour visiting stops cluster-by-cluster.
    """
    depot = problem.depot
    # Sort clusters by distance from depot to cluster centroid
    ordered_deliveries: List[int] = []

    for c_id in sorted(clusters_dict.keys()):
        stops_in_c = clusters_dict[c_id]
        if not stops_in_c:
            continue
        # Greedy ordering within cluster
        current = ordered_deliveries[-1] if ordered_deliveries else depot
        remaining = set(stops_in_c)
        while remaining:
            next_s = min(remaining, key=lambda s: problem.distance_matrix[current][s])
            ordered_deliveries.append(next_s)
            remaining.remove(next_s)
            current = next_s

    return problem.to_full_tour(ordered_deliveries)
