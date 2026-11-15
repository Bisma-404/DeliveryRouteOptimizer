"""Stop generation and coordinate management.

This module handles loading realistic delivery stops from local CSV files,
generating random test instances with reproducible seeds, and mapping
stop coordinates to the road network graph.
"""

import os
import random
import logging
from typing import List, Dict, Any, Optional
import pandas as pd
from .graph_loader import GraphLoader

logger = logging.getLogger(__name__)


class StopGenerator:
    """Generates and samples delivery stops for the Route Optimizer.

    Attributes:
        graph_loader (GraphLoader): Associated graph loader to snap stops to nodes.
        csv_path (str): Filepath to the stops CSV.
    """

    def __init__(self, graph_loader: GraphLoader, csv_path: Optional[str] = None):
        """Initialize StopGenerator.

        Args:
            graph_loader: Instance of GraphLoader with a loaded road graph.
            csv_path: Optional filepath to stops CSV. Defaults to data/raw/stops_<city>.csv.
        """
        self.graph_loader = graph_loader
        if csv_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
            city = graph_loader.city_name.lower()
            self.csv_path = os.path.join(project_root, "data", "raw", f"stops_{city}.csv")
        else:
            self.csv_path = csv_path

    def load_stops_from_csv(self) -> List[Dict[str, Any]]:
        """Load full list of candidate stops from CSV file.

        Returns:
            List[Dict[str, Any]]: List of stop dictionaries with keys
                ['stop_id', 'name', 'address', 'latitude', 'longitude', 'type'].

        Raises:
            FileNotFoundError: If the CSV file does not exist.
            ValueError: If the CSV format or required columns are invalid.
        """
        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(f"Stops CSV file not found at: {self.csv_path}")

        try:
            df = pd.read_csv(self.csv_path)
        except (pd.errors.EmptyDataError, pd.errors.ParserError) as err:
            raise ValueError(f"Failed to parse stops CSV file: {err}") from err

        required_cols = {"name", "latitude", "longitude"}
        if not required_cols.issubset(set(df.columns)):
            missing = required_cols - set(df.columns)
            raise ValueError(f"Stops CSV missing required columns: {missing}")

        stops: List[Dict[str, Any]] = []
        for idx, row in df.iterrows():
            stops.append({
                "stop_id": int(row.get("stop_id", idx)),
                "name": str(row["name"]),
                "address": str(row.get("address", row["name"])),
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "type": str(row.get("type", "depot" if idx == 0 else "delivery"))
            })

        logger.info("Loaded %d candidate stops from CSV: %s", len(stops), self.csv_path)
        return stops

    def generate_stops(
        self,
        num_stops: int = 15,
        seed: int = 42
    ) -> List[Dict[str, Any]]:
        """Sample or generate a reproducible set of stops with the depot at index 0.

        Args:
            num_stops: Number of delivery stops to generate (including depot). Default 15.
            seed: Random seed for reproducibility. Default 42.

        Returns:
            List[Dict[str, Any]]: List of stops, where index 0 is always the depot,
                and each stop has a 'nearest_node' key pointing to a road graph node.

        Raises:
            ValueError: If num_stops < 2 or graph has not been loaded.
        """
        if num_stops < 2:
            raise ValueError("Must generate at least 2 stops (1 depot and 1 delivery stop).")

        if self.graph_loader.graph is None:
            raise ValueError("Road network graph is not loaded. Load graph before generating stops.")

        rng = random.Random(seed)

        try:
            candidate_stops = self.load_stops_from_csv()
        except FileNotFoundError:
            logger.warning("Stops CSV not found. Synthesizing stops from graph nodes.")
            candidate_stops = self._synthesize_from_graph(num_stops, rng)

        # Identify depot (prefer type == 'depot' or first stop)
        depots = [s for s in candidate_stops if s.get("type") == "depot"]
        deliveries = [s for s in candidate_stops if s.get("type") != "depot"]

        depot = depots[0] if depots else candidate_stops[0]

        # Sample (num_stops - 1) delivery stops
        needed_deliveries = num_stops - 1
        if len(deliveries) >= needed_deliveries:
            selected_deliveries = rng.sample(deliveries, needed_deliveries)
        else:
            # If not enough delivery stops in CSV, sample with replacement or synthesize extra
            logger.warning(
                "CSV only has %d deliveries; synthesizing extra up to %d",
                len(deliveries),
                needed_deliveries
            )
            extra = self._synthesize_from_graph(needed_deliveries - len(deliveries), rng)
            selected_deliveries = list(deliveries) + extra

        selected_stops = [depot] + selected_deliveries

        # Re-index and snap each stop to the nearest graph node
        final_stops: List[Dict[str, Any]] = []
        for i, stop in enumerate(selected_stops):
            stop_copy = dict(stop)
            stop_copy["stop_id"] = i
            node_id = self.graph_loader.get_nearest_node(
                stop_copy["latitude"],
                stop_copy["longitude"]
            )
            stop_copy["nearest_node"] = node_id
            # Also store exact road junction coordinates
            junc_lat, junc_lon = self.graph_loader.get_node_coordinates(node_id)
            stop_copy["node_latitude"] = junc_lat
            stop_copy["node_longitude"] = junc_lon
            final_stops.append(stop_copy)

        logger.info(
            "Generated %d stops (seed=%d): depot '%s' + %d delivery destinations.",
            len(final_stops),
            seed,
            final_stops[0]["name"],
            len(final_stops) - 1
        )
        return final_stops

    def _synthesize_from_graph(
        self,
        count: int,
        rng: random.Random
    ) -> List[Dict[str, Any]]:
        """Fallback method to sample random intersections directly from the graph.

        Args:
            count: Number of stops to synthesize.
            rng: Random generator with fixed seed.

        Returns:
            List[Dict[str, Any]]: Synthesized stop dictionaries.
        """
        assert self.graph_loader.graph is not None
        nodes = list(self.graph_loader.graph.nodes())
        selected_nodes = rng.sample(nodes, min(count, len(nodes)))

        synthesized: List[Dict[str, Any]] = []
        for i, node_id in enumerate(selected_nodes):
            lat, lon = self.graph_loader.get_node_coordinates(node_id)
            synthesized.append({
                "stop_id": i,
                "name": f"Intersection #{node_id % 10000}",
                "address": f"Road Node {node_id}",
                "latitude": lat,
                "longitude": lon,
                "type": "delivery"
            })
        return synthesized
