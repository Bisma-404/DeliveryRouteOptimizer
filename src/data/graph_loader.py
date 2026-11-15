"""Graph loader and caching manager using OSMnx and NetworkX.

This module loads the Karachi road network, caches it offline as a GraphML file,
keeps the largest strongly connected component, and snaps GPS coordinates to road nodes.
"""

import os
import time
import logging
from typing import Tuple, Optional
import networkx as nx
import osmnx as ox

logger = logging.getLogger(__name__)


class GraphLoader:
    """Manages downloading, offline caching, and graph preprocessing for city road networks.

    Attributes:
        city_name (str): Road network to load. This application uses Karachi.
        cache_dir (str): Directory where .graphml files are stored offline.
        cache_path (str): Full filesystem path to the cached graphml file.
        graph (Optional[nx.MultiDiGraph]): The loaded NetworkX/OSMnx road graph.
    """

    # Primary and fallback Overpass API endpoints to handle server busy/502 errors
    OVERPASS_ENDPOINTS = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    ]

    # City road network presets (center_lat, center_lon, radius_meters).
    CITY_PRESETS = {
        "Karachi": (24.8607, 67.0011, 1500),   # Saddar / Kharadar area
        "Lahore":  (31.5204, 74.3587, 1500),   # Gulberg / Liberty Market area
    }

    def __init__(self, city_name: str = "Karachi", cache_dir: Optional[str] = None):
        """Initialize the GraphLoader.

        Args:
            city_name: City road network to load. Only Karachi is supported.
            cache_dir: Optional path to data/raw cache directory. If None, resolves
                       relative to the project root.
        """
        self.city_name = city_name.capitalize()
        if cache_dir is None:
            # Resolve to <project_root>/data/raw
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
            self.cache_dir = os.path.join(project_root, "data", "raw")
        else:
            self.cache_dir = cache_dir

        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache_path = os.path.join(self.cache_dir, f"{self.city_name.lower()}.graphml")
        self.graph: Optional[nx.MultiDiGraph] = None

    def load_graph(self, force_download: bool = False) -> nx.MultiDiGraph:
        """Load the road network graph from cache or download from OpenStreetMap.

        Args:
            force_download: If True, ignores existing cache and redownloads from OSM.

        Returns:
            nx.MultiDiGraph: The loaded road network restricted to its largest SCC.

        Raises:
            RuntimeError: If downloading fails across all endpoints and no cache exists.
        """
        if not force_download and os.path.exists(self.cache_path):
            try:
                logger.info("Loading cached road network from: %s", self.cache_path)
                G = ox.load_graphml(self.cache_path)
                self.graph = self._ensure_strongly_connected(G)
                return self.graph
            except (OSError, ValueError) as err:
                logger.warning("Failed to load cached graphml (%s). Redownloading...", err)

        # Download from OpenStreetMap via OSMnx
        logger.info("Downloading road network for %s from OpenStreetMap...", self.city_name)
        if self.city_name not in self.CITY_PRESETS:
            raise ValueError(
                f"Unsupported city '{self.city_name}'. "
                f"Supported cities: {list(self.CITY_PRESETS.keys())}"
            )
        center_lat, center_lon, radius_m = self.CITY_PRESETS[self.city_name]

        downloaded_graph = None
        last_error: Optional[Exception] = None

        for endpoint in self.OVERPASS_ENDPOINTS:
            try:
                logger.info("Attempting download using Overpass endpoint: %s", endpoint)
                ox.settings.overpass_endpoint = endpoint
                ox.settings.timeout = 60
                ox.settings.requests_timeout = 60

                downloaded_graph = ox.graph_from_point(
                    (center_lat, center_lon),
                    dist=radius_m,
                    network_type="drive",
                    simplify=True
                )
                if downloaded_graph is not None and len(downloaded_graph.nodes) > 0:
                    logger.info(
                        "Download succeeded: %d nodes, %d edges.",
                        len(downloaded_graph.nodes),
                        len(downloaded_graph.edges)
                    )
                    break
            except Exception as err:
                logger.warning("Endpoint %s failed: %s", endpoint, err)
                last_error = err
                time.sleep(2)

        if downloaded_graph is None or len(downloaded_graph.nodes) == 0:
            raise RuntimeError(
                f"Failed to download road network for {self.city_name} from all OSM endpoints. "
                f"Last error: {last_error}"
            )

        # Ensure largest strongly connected component
        self.graph = self._ensure_strongly_connected(downloaded_graph)

        # Cache locally for offline execution
        try:
            ox.save_graphml(self.graph, self.cache_path)
            logger.info("Cached processed road graph to: %s", self.cache_path)
        except (OSError, ValueError) as save_err:
            logger.warning("Could not write cache to %s: %s", self.cache_path, save_err)

        return self.graph

    def _ensure_strongly_connected(self, G: nx.MultiDiGraph) -> nx.MultiDiGraph:
        """Filter the graph to its largest strongly connected component (SCC).

        This guarantees that every node can reach every other node, preventing
        disconnected dead ends in delivery routes.

        Args:
            G: The input MultiDiGraph.

        Returns:
            nx.MultiDiGraph: Subgraph containing only the largest SCC.
        """
        sccs = list(nx.strongly_connected_components(G))
        if not sccs:
            return G
        largest_scc = max(sccs, key=len)
        subgraph = G.subgraph(largest_scc).copy()
        logger.info(
            "Retained largest strongly connected component: %d / %d nodes (%.1f%%).",
            len(subgraph.nodes),
            len(G.nodes),
            (len(subgraph.nodes) / len(G.nodes)) * 100.0
        )
        return subgraph

    def get_nearest_node(self, lat: float, lon: float) -> int:
        """Find the nearest road network node to a given GPS coordinate.

        Args:
            lat: Latitude of the point.
            lon: Longitude of the point.

        Returns:
            int: Node ID of the nearest intersection or road junction.

        Raises:
            ValueError: If the graph has not been loaded yet.
        """
        if self.graph is None:
            raise ValueError("Graph has not been loaded. Call load_graph() first.")

        # OSMnx nearest_nodes accepts X=lon, Y=lat
        nearest = ox.nearest_nodes(self.graph, X=lon, Y=lat)
        return int(nearest)

    def get_node_coordinates(self, node_id: int) -> Tuple[float, float]:
        """Get (latitude, longitude) for a given road network node ID.

        Args:
            node_id: Node ID in the road graph.

        Returns:
            Tuple[float, float]: (lat, lon) coordinates of the node.

        Raises:
            KeyError: If node_id does not exist in graph.
        """
        if self.graph is None or node_id not in self.graph.nodes:
            raise KeyError(f"Node ID {node_id} not found in the loaded graph.")
        node_data = self.graph.nodes[node_id]
        return float(node_data["y"]), float(node_data["x"])

    def get_graph_bounds(self) -> Tuple[float, float, float, float]:
        """Compute the bounding coordinates (min_lat, max_lat, min_lon, max_lon).

        Returns:
            Tuple[float, float, float, float]: (min_lat, max_lat, min_lon, max_lon).

        Raises:
            ValueError: If graph is not loaded.
        """
        if self.graph is None:
            raise ValueError("Graph has not been loaded. Call load_graph() first.")

        lats = [d["y"] for _, d in self.graph.nodes(data=True)]
        lons = [d["x"] for _, d in self.graph.nodes(data=True)]
        return min(lats), max(lats), min(lons), max(lons)
