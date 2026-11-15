"""Location search, real-time autocomplete, and road network snapping service for Karachi.

Provides instantaneous, high-precision autocomplete matching for Karachi locations
(FAST NUCES, DHA Phases, Clifton, Saddar, Gulshan, Airport, Hospitals, Markets, etc.)
backed by OpenStreetMap Nominatim for general queries.
"""

from __future__ import annotations

import time
import math
import logging
import threading
from typing import List, Dict, Any, Optional, Tuple
import requests

from ..core.astar import haversine_distance
from .graph_loader import GraphLoader

logger = logging.getLogger(__name__)

USER_AGENT = "DeliveryRouteOptimizer/2.0 (FAST-NUCES Karachi AI Lab Project; contact: bisma.shahid@student.nu.edu.pk)"


class UnreachableLocationError(Exception):
    """Raised when a location is outside the reachable city road network."""
    pass

# ── Comprehensive Real-World Karachi Landmarks & Areas ─────────────────────────
KARACHI_LOCATIONS_DATABASE: List[Dict[str, Any]] = [
    # FAST NUCES
    {
        "name": "FAST NUCES Karachi (Main Campus)",
        "address": "Shah Latif Town, National Highway, Karachi, 75030",
        "latitude": 24.8569,
        "longitude": 67.2646,
        "category": "University / FAST"
    },
    {
        "name": "FAST NUCES City Campus",
        "address": "22-G, Block 6, PECHS, Shahrah-e-Faisal, Karachi",
        "latitude": 24.8615,
        "longitude": 67.0682,
        "category": "University / FAST"
    },
    {
        "name": "FAST University CS & AI Department",
        "address": "Faculty of Computer Science, FAST NUCES Main Campus, Karachi",
        "latitude": 24.8572,
        "longitude": 67.2650,
        "category": "University / FAST"
    },
    {
        "name": "FAST University Library & Student Center",
        "address": "FAST NUCES Main Campus, National Highway, Karachi",
        "latitude": 24.8565,
        "longitude": 67.2640,
        "category": "University / FAST"
    },

    # DHA (Defence Housing Authority)
    {
        "name": "DHA Phase 1",
        "address": "Korangi Road, DHA Phase 1, Karachi",
        "latitude": 24.8360,
        "longitude": 67.0620,
        "category": "DHA / Residential"
    },
    {
        "name": "DHA Phase 2 (Sunset Boulevard)",
        "address": "Sunset Boulevard, DHA Phase 2, Karachi",
        "latitude": 24.8320,
        "longitude": 67.0680,
        "category": "DHA / Residential"
    },
    {
        "name": "DHA Phase 4 Commercial Area",
        "address": "9th Commercial Street, DHA Phase 4, Karachi",
        "latitude": 24.8250,
        "longitude": 67.0650,
        "category": "DHA / Commercial"
    },
    {
        "name": "DHA Phase 5 Commercial (Badar)",
        "address": "Khayaban-e-Badar, DHA Phase 5, Karachi",
        "latitude": 24.8210,
        "longitude": 67.0580,
        "category": "DHA / Commercial"
    },
    {
        "name": "DHA Phase 6 (Ittehad)",
        "address": "Khayaban-e-Ittehad, DHA Phase 6, Karachi",
        "latitude": 24.8115,
        "longitude": 67.0690,
        "category": "DHA / Commercial"
    },
    {
        "name": "DHA Phase 7 (Khayaban-e-Jami)",
        "address": "Khayaban-e-Jami, DHA Phase 7, Karachi",
        "latitude": 24.8154,
        "longitude": 67.0718,
        "category": "DHA / Residential"
    },
    {
        "name": "DHA Phase 8 (Creek Vistas)",
        "address": "Khayaban-e-Faisal, DHA Phase 8, Karachi",
        "latitude": 24.7890,
        "longitude": 67.0850,
        "category": "DHA / Luxury"
    },
    {
        "name": "DHA Suffa University",
        "address": "DG-78, Off Khayaban-e-Tufail, DHA Phase 7 Extension, Karachi",
        "latitude": 24.8146,
        "longitude": 67.0800,
        "category": "University / DHA"
    },
    {
        "name": "DHA Creek Club",
        "address": "Zulfiqar Street 1, DHA Phase 8, Karachi",
        "latitude": 24.8020,
        "longitude": 67.0720,
        "category": "DHA / Leisure"
    },
    {
        "name": "DHA Golf Club (Karachi Golf Club)",
        "address": "Karsaz Road, Near DHA, Karachi",
        "latitude": 24.8870,
        "longitude": 67.0980,
        "category": "DHA / Sports"
    },

    # Clifton
    {
        "name": "Dolmen Mall Clifton",
        "address": "HC-3, Marine Drive, Block 4, Clifton, Karachi",
        "latitude": 24.8130,
        "longitude": 67.0310,
        "category": "Shopping Mall / Clifton"
    },
    {
        "name": "Clifton Block 2 (Bilawal House)",
        "address": "Khayaban-e-Saadi, Block 2, Clifton, Karachi",
        "latitude": 24.8240,
        "longitude": 67.0260,
        "category": "Clifton / Landmark"
    },
    {
        "name": "Boat Basin Food Street Clifton",
        "address": "Khayaban-e-Roomi, Block 5, Clifton, Karachi",
        "latitude": 24.8260,
        "longitude": 67.0330,
        "category": "Food Street / Clifton"
    },
    {
        "name": "Sea View Beach Clifton",
        "address": "Abdul Sattar Edhi Avenue, Clifton, Karachi",
        "latitude": 24.8050,
        "longitude": 67.0420,
        "category": "Beach / Clifton"
    },
    {
        "name": "Do Talwar Chowrangi",
        "address": "Khayaban-e-Iqbal, Block 9, Clifton, Karachi",
        "latitude": 24.8305,
        "longitude": 67.0305,
        "category": "Monument / Clifton"
    },
    {
        "name": "Teen Talwar Chowrangi",
        "address": "Main Clifton Road, Clifton, Karachi",
        "latitude": 24.8350,
        "longitude": 67.0315,
        "category": "Monument / Clifton"
    },

    # Saddar & Old City
    {
        "name": "Burns Road Food Street",
        "address": "Shahrah-e-Liaquat, Burns Road, Saddar, Karachi",
        "latitude": 24.8578,
        "longitude": 67.0152,
        "category": "Food Street / Saddar"
    },
    {
        "name": "Waheed Kabab House (Burns Road)",
        "address": "Burns Road, Saddar, Karachi",
        "latitude": 24.8580,
        "longitude": 67.0148,
        "category": "Restaurant / Burns Road"
    },
    {
        "name": "Fresco Sweets Burns Road",
        "address": "Burns Road Chowk, Saddar, Karachi",
        "latitude": 24.8575,
        "longitude": 67.0150,
        "category": "Sweets / Burns Road"
    },
    {
        "name": "Empress Market Saddar",
        "address": "Preedy Street, Saddar, Karachi",
        "latitude": 24.8607,
        "longitude": 67.0260,
        "category": "Historic Market / Saddar"
    },
    {
        "name": "Atrium Mall & Cinemas",
        "address": "249 Staff Lines, Fatima Jinnah Road, Saddar, Karachi",
        "latitude": 24.8560,
        "longitude": 67.0280,
        "category": "Shopping Mall / Saddar"
    },
    {
        "name": "Zainab Market Saddar",
        "address": "Abdullah Haroon Road, Saddar, Karachi",
        "latitude": 24.8530,
        "longitude": 67.0250,
        "category": "Shopping / Saddar"
    },
    {
        "name": "Wazir Mansion (Quaid Birthplace)",
        "address": "Newnham Road, Kharadar, Karachi",
        "latitude": 24.8512,
        "longitude": 66.9974,
        "category": "Heritage / Kharadar"
    },
    {
        "name": "Merewether Clock Tower",
        "address": "I.I. Chundrigar Road, Karachi",
        "latitude": 24.8490,
        "longitude": 66.9935,
        "category": "Landmark / Chundrigar"
    },
    {
        "name": "Bolton Market",
        "address": "M.A. Jinnah Road, Kharadar, Karachi",
        "latitude": 24.8540,
        "longitude": 67.0022,
        "category": "Market / Kharadar"
    },
    {
        "name": "Denso Hall Heritage Library",
        "address": "M.A. Jinnah Road, Saddar, Karachi",
        "latitude": 24.8551,
        "longitude": 67.0104,
        "category": "Heritage / Saddar"
    },
    {
        "name": "City Courts Karachi",
        "address": "M.A. Jinnah Road, Karachi",
        "latitude": 24.8566,
        "longitude": 67.0124,
        "category": "Government / Courts"
    },
    {
        "name": "Pakistan Chowk",
        "address": "Aram Bagh, Saddar, Karachi",
        "latitude": 24.8554,
        "longitude": 67.0136,
        "category": "Chowk / Saddar"
    },
    {
        "name": "Lea Market Kharadar",
        "address": "Lea Market Chowk, Kharadar, Karachi",
        "latitude": 24.8594,
        "longitude": 66.9904,
        "category": "Market / Kharadar"
    },
    {
        "name": "Jodia Bazaar Wholesale",
        "address": "Jodia Bazaar, Kharadar, Karachi",
        "latitude": 24.8572,
        "longitude": 67.0054,
        "category": "Wholesale Market"
    },
    {
        "name": "Civil Hospital Karachi (CHK)",
        "address": "Mission Road, Nanak Wara, Karachi",
        "latitude": 24.8662,
        "longitude": 67.0108,
        "category": "Hospital"
    },
    {
        "name": "Dow Medical College (DUHS)",
        "address": "Baba-e-Urdu Road, Karachi",
        "latitude": 24.8646,
        "longitude": 67.0126,
        "category": "Medical College"
    },
    {
        "name": "Sindh High Court",
        "address": "Court Road, Saddar, Karachi",
        "latitude": 24.8590,
        "longitude": 67.0150,
        "category": "Judiciary"
    },
    {
        "name": "Sindh Assembly Building",
        "address": "Court Road, Saddar, Karachi",
        "latitude": 24.8585,
        "longitude": 67.0145,
        "category": "Government"
    },
    {
        "name": "Arts Council of Pakistan",
        "address": "M.R. Kiyani Road, Saddar, Karachi",
        "latitude": 24.8560,
        "longitude": 67.0158,
        "category": "Culture / Saddar"
    },
    {
        "name": "Karachi City Railway Station",
        "address": "I.I. Chundrigar Road, McLeod Road, Karachi",
        "latitude": 24.8498,
        "longitude": 67.0092,
        "category": "Railway Station"
    },
    {
        "name": "Habib Bank Plaza (HBL)",
        "address": "I.I. Chundrigar Road, Karachi",
        "latitude": 24.8510,
        "longitude": 67.0040,
        "category": "Banking / Finance"
    },
    {
        "name": "MCB Tower",
        "address": "I.I. Chundrigar Road, Karachi",
        "latitude": 24.8505,
        "longitude": 67.0005,
        "category": "Banking / Finance"
    },
    {
        "name": "Port Grand Food & Leisure",
        "address": "MT Khan Road, Karachi",
        "latitude": 24.8480,
        "longitude": 66.9910,
        "category": "Leisure / Harbor"
    },
    {
        "name": "Karachi Port Trust (KPT) Head Office",
        "address": "Eduljee Dinshaw Road, Karachi",
        "latitude": 24.8492,
        "longitude": 66.9890,
        "category": "Port / Maritime"
    },

    # PECHS & Tariq Road
    {
        "name": "Tariq Road Commercial Area",
        "address": "Tariq Road, Block 2, PECHS, Karachi",
        "latitude": 24.8710,
        "longitude": 67.0620,
        "category": "Commercial / Shopping"
    },
    {
        "name": "Dolmen Mall Tariq Road",
        "address": "Main Tariq Road, PECHS, Karachi",
        "latitude": 24.8690,
        "longitude": 67.0610,
        "category": "Shopping Mall / PECHS"
    },
    {
        "name": "Rabi Center Tariq Road",
        "address": "Tariq Road, PECHS, Karachi",
        "latitude": 24.8705,
        "longitude": 67.0615,
        "category": "Shopping / Clothing"
    },
    {
        "name": "Char Minar Chowrangi Bahadurabad",
        "address": "Bahadur Shah Zafar Road, Bahadurabad, Karachi",
        "latitude": 24.8820,
        "longitude": 67.0670,
        "category": "Chowrangi / Bahadurabad"
    },

    # Gulshan-e-Iqbal & Universities
    {
        "name": "University of Karachi (KU)",
        "address": "Main University Road, Gulshan-e-Iqbal, Karachi",
        "latitude": 24.9420,
        "longitude": 67.1180,
        "category": "University / Public"
    },
    {
        "name": "NED University of Engineering",
        "address": "University Road, Gulshan-e-Iqbal, Karachi",
        "latitude": 24.9340,
        "longitude": 67.1120,
        "category": "Engineering University"
    },
    {
        "name": "NIPA Chowrangi Gulshan",
        "address": "Rashid Minhas Road, Gulshan-e-Iqbal, Karachi",
        "latitude": 24.9180,
        "longitude": 67.0970,
        "category": "Chowrangi / Gulshan"
    },
    {
        "name": "Disco Bakery Gulshan",
        "address": "Allama Shabbir Ahmed Usmani Road, Block 5, Gulshan, Karachi",
        "latitude": 24.9220,
        "longitude": 67.0940,
        "category": "Bakery / Gulshan"
    },
    {
        "name": "Hassan Square Gulshan",
        "address": "University Road, Gulshan-e-Iqbal, Karachi",
        "latitude": 24.8980,
        "longitude": 67.0760,
        "category": "Chowrangi / Gulshan"
    },

    # Major Hospitals
    {
        "name": "Aga Khan University Hospital (AKUH)",
        "address": "National Stadium Road, Karachi, 74800",
        "latitude": 24.8920,
        "longitude": 67.0750,
        "category": "Hospital / Healthcare"
    },
    {
        "name": "Liaquat National Hospital (LNH)",
        "address": "National Stadium Road, Karachi",
        "latitude": 24.8940,
        "longitude": 67.0710,
        "category": "Hospital / Healthcare"
    },
    {
        "name": "Jinnah Postgraduate Medical Centre (JPMC)",
        "address": "Rafiqui Shaheed Road, Karachi Cantt, Karachi",
        "latitude": 24.8520,
        "longitude": 67.0360,
        "category": "Hospital / Healthcare"
    },
    {
        "name": "NICVD Heart Hospital",
        "address": "Rafiqui Shaheed Road, Karachi Cantt, Karachi",
        "latitude": 24.8510,
        "longitude": 67.0340,
        "category": "Specialized Hospital"
    },
    {
        "name": "Indus Hospital Korangi",
        "address": "Plot C-76, Sector 31/5, Korangi Crossing, Karachi",
        "latitude": 24.8280,
        "longitude": 67.1260,
        "category": "Hospital / Healthcare"
    },

    # Transport, Airport, Bahria
    {
        "name": "Jinnah International Airport (JIAP)",
        "address": "Airport Road, Faisal Cantt, Karachi",
        "latitude": 24.9065,
        "longitude": 67.1608,
        "category": "Airport / Terminal"
    },
    {
        "name": "North Nazimabad Hyderi Market",
        "address": "Block H, North Nazimabad, Karachi",
        "latitude": 24.9350,
        "longitude": 67.0380,
        "category": "Market / Nazimabad"
    },
    {
        "name": "Five Star Chowrangi Nazimabad",
        "address": "Shahrah-e-Humayun, North Nazimabad, Karachi",
        "latitude": 24.9410,
        "longitude": 67.0420,
        "category": "Chowrangi / Nazimabad"
    },
    {
        "name": "Johar Chowrangi",
        "address": "Prof Ghafoor Ahmed Road, Block 14, Johar, Karachi",
        "latitude": 24.9170,
        "longitude": 67.1350,
        "category": "Chowrangi / Johar"
    },
    {
        "name": "Millennium Mall Johar",
        "address": "Rashid Minhas Road, Gulistan-e-Johar, Karachi",
        "latitude": 24.9010,
        "longitude": 67.1150,
        "category": "Shopping Mall / Johar"
    },
    {
        "name": "Shahrah-e-Faisal FTC Building",
        "address": "Shahrah-e-Faisal, Karachi",
        "latitude": 24.8610,
        "longitude": 67.0480,
        "category": "Commercial / Shahrah-e-Faisal"
    },
    {
        "name": "Bahria Town Karachi Gateway",
        "address": "M-9 Karachi-Hyderabad Motorway, Karachi",
        "latitude": 25.0080,
        "longitude": 67.3190,
        "category": "Township / Bahria"
    }
]


class LocationGeocoder:
    """Location search and autocomplete engine with road network snapping."""

    def __init__(self, graph_loader: Optional[GraphLoader] = None):
        """Initialize LocationGeocoder."""
        self.graph_loader = graph_loader
        self._last_nominatim_time = 0.0

    def search_places(self, query: str, limit: int = 7) -> List[Dict[str, Any]]:
        """Instant fuzzy prefix search across curated Karachi locations, plus OSM.

        Args:
            query: Typed search text (e.g. 'FAST', 'DHA', 'Burns', 'Clifton').
            limit: Maximum suggestions to return.

        Returns:
            List[Dict[str, Any]]: Matched locations with 'name', 'address', 'latitude', 'longitude'.
        """
        query_clean = query.strip()
        if not query_clean:
            return []

        q_lower = query_clean.lower()
        results: List[Dict[str, Any]] = []

        # 1. High-priority exact and prefix matching in local Karachi knowledge base
        exact_matches = []
        substring_matches = []

        for loc in KARACHI_LOCATIONS_DATABASE:
            name_low = loc["name"].lower()
            addr_low = loc["address"].lower()
            cat_low = loc.get("category", "").lower()

            # Check if query matches abbreviation like "DHA" or "FAST"
            is_word_match = any(w.startswith(q_lower) for w in name_low.split())
            if name_low.startswith(q_lower) or is_word_match:
                exact_matches.append(loc)
            elif q_lower in name_low or q_lower in addr_low or q_lower in cat_low:
                substring_matches.append(loc)

        for loc in exact_matches + substring_matches:
            item = {
                "name": loc["name"],
                "address": loc["address"],
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "category": loc.get("category", "Landmark"),
                "source": "Karachi Directory"
            }
            if not any(r["name"] == item["name"] for r in results):
                results.append(item)
            if len(results) >= limit:
                return results

        # 2. Query OpenStreetMap Nominatim for general addresses (rate-limited)
        if len(results) < limit and len(query_clean) >= 3:
            try:
                now = time.time()
                if now - self._last_nominatim_time >= 0.8:
                    self._last_nominatim_time = now
                    url = "https://nominatim.openstreetmap.org/search"
                    params = {
                        "q": f"{query_clean}, Karachi, Pakistan",
                        "format": "json",
                        "limit": limit - len(results),
                        "countrycodes": "pk",
                    }
                    headers = {"User-Agent": USER_AGENT}
                    resp = requests.get(url, params=params, headers=headers, timeout=2.0)
                    if resp.status_code == 200:
                        for entry in resp.json():
                            name = entry.get("name") or entry.get("display_name", "").split(",")[0]
                            item = {
                                "name": name,
                                "address": entry.get("display_name", ""),
                                "latitude": float(entry["lat"]),
                                "longitude": float(entry["lon"]),
                                "category": entry.get("type", "Address"),
                                "source": "OpenStreetMap"
                            }
                            if not any(r["name"] == item["name"] for r in results):
                                results.append(item)
            except Exception as e:
                logger.debug("Nominatim search skipped: %s", e)

        return results[:limit]

    def snap_location(
        self,
        name: str,
        address: str,
        lat: float,
        lon: float
    ) -> Dict[str, Any]:
        """Snap coordinate to the nearest road network node and return verified stop dict.

        Args:
            name: Location name.
            address: Street address.
            lat: Latitude.
            lon: Longitude.

        Returns:
            Dict[str, Any]: Stop dictionary with 'nearest_node', 'node_latitude', 'node_longitude'.
        """
        if self.graph_loader is None or self.graph_loader.graph is None:
            raise ValueError("Road network graph is not loaded.")

        G = self.graph_loader.graph
        node_id = self.graph_loader.get_nearest_node(lat, lon)
        node_lat = float(G.nodes[node_id]["y"])
        node_lon = float(G.nodes[node_id]["x"])
        snap_dist = haversine_distance(lat, lon, node_lat, node_lon)

        return {
            "name": name,
            "address": address or name,
            "latitude": lat,
            "longitude": lon,
            "nearest_node": node_id,
            "node_latitude": node_lat,
            "node_longitude": node_lon,
            "snap_distance_m": snap_dist,
            "type": "delivery",
            "priority": "Normal",
            "weight_kg": 5.0,
            "time_window": "Anytime"
        }

    def snap_and_validate(
        self,
        name: str,
        address: str,
        lat: float,
        lon: float,
        max_snap_distance_m: float = 60000.0
    ) -> Dict[str, Any]:
        """Validate that the location is within the active city road network region and snap it.

        Args:
            name: Location name.
            address: Street address.
            lat: Latitude.
            lon: Longitude.
            max_snap_distance_m: Maximum acceptable snap distance in meters (default 60 km).

        Returns:
            Dict[str, Any]: Snapped location dictionary.

        Raises:
            UnreachableLocationError: If location is beyond max_snap_distance_m.
        """
        stop = self.snap_location(name, address, lat, lon)
        if stop["snap_distance_m"] > max_snap_distance_m:
            raise UnreachableLocationError(
                f"Location '{name}' ({lat:.4f}, {lon:.4f}) is {stop['snap_distance_m']/1000:.1f} km away "
                f"from the road network. Please select a location within the active city boundaries."
            )
        return stop

