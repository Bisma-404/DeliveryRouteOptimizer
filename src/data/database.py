"""SQLite Database Manager for Delivery Route Optimizer.

Persists planned routes, customer deliveries, delivery statuses,
and performance metrics for the Route History section.
"""

from __future__ import annotations

import os
import sqlite3
import datetime
import logging
from contextlib import contextmanager
from typing import List, Dict, Any, Optional, Tuple, Generator

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "delivery_history.db")
)


class DatabaseManager:
    """Manages SQLite persistence for delivery routes and stops."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize DatabaseManager with database file path."""
        self.db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_db()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager that guarantees connection is closed after use."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self) -> None:
        """Create tables and indices if they do not exist."""
        with self._connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS routes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    route_name TEXT NOT NULL,
                    depot_name TEXT NOT NULL,
                    depot_lat REAL NOT NULL,
                    depot_lon REAL NOT NULL,
                    num_stops INTEGER NOT NULL,
                    total_distance_km REAL NOT NULL,
                    est_time_mins REAL NOT NULL,
                    baseline_distance_km REAL NOT NULL,
                    saved_distance_km REAL NOT NULL,
                    saved_pct REAL NOT NULL,
                    algorithm TEXT NOT NULL,
                    search_method TEXT NOT NULL,
                    round_trip INTEGER NOT NULL DEFAULT 1,
                    vehicle_capacity_kg REAL NOT NULL DEFAULT 50.0,
                    total_weight_kg REAL NOT NULL DEFAULT 0.0,
                    status TEXT NOT NULL DEFAULT 'Planned'
                );

                CREATE TABLE IF NOT EXISTS route_stops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_id INTEGER NOT NULL,
                    stop_order INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    address TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'Normal',
                    weight_kg REAL NOT NULL DEFAULT 0.0,
                    time_window TEXT NOT NULL DEFAULT 'Anytime',
                    delivery_status TEXT NOT NULL DEFAULT 'Pending',
                    leg_distance_km REAL NOT NULL DEFAULT 0.0,
                    est_arrival_min REAL NOT NULL DEFAULT 0.0,
                    FOREIGN KEY (route_id) REFERENCES routes (id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_routes_created ON routes(created_at);
                CREATE INDEX IF NOT EXISTS idx_route_stops_route ON route_stops(route_id);
            """)
            conn.commit()
            logger.info("Database initialized at %s", self.db_path)

    def save_route(
        self,
        route_meta: Dict[str, Any],
        stops_list: List[Dict[str, Any]]
    ) -> int:
        """Save a planned route and its ordered stops into the database."""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        route_name = route_meta.get("route_name") or f"Route-{now[:10]}-{route_meta.get('algorithm', 'OPT')}"

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO routes (
                    created_at, route_name, depot_name, depot_lat, depot_lon,
                    num_stops, total_distance_km, est_time_mins, baseline_distance_km,
                    saved_distance_km, saved_pct, algorithm, search_method,
                    round_trip, vehicle_capacity_kg, total_weight_kg, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now,
                route_name,
                str(route_meta.get("depot_name", "Depot")),
                float(route_meta.get("depot_lat", 0.0)),
                float(route_meta.get("depot_lon", 0.0)),
                int(route_meta.get("num_stops", len(stops_list))),
                float(route_meta.get("total_distance_km", 0.0)),
                float(route_meta.get("est_time_mins", 0.0)),
                float(route_meta.get("baseline_distance_km", 0.0)),
                float(route_meta.get("saved_distance_km", 0.0)),
                float(route_meta.get("saved_pct", 0.0)),
                str(route_meta.get("algorithm", "Unknown")),
                str(route_meta.get("search_method", "A*")),
                1 if route_meta.get("round_trip", True) else 0,
                float(route_meta.get("vehicle_capacity_kg", 50.0)),
                float(route_meta.get("total_weight_kg", 0.0)),
                str(route_meta.get("status", "Planned"))
            ))
            route_id = cursor.lastrowid

            for idx, stop in enumerate(stops_list):
                cursor.execute("""
                    INSERT INTO route_stops (
                        route_id, stop_order, name, address, latitude, longitude,
                        priority, weight_kg, time_window, delivery_status,
                        leg_distance_km, est_arrival_min
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    route_id,
                    idx,
                    str(stop.get("name", f"Stop {idx}")),
                    str(stop.get("address", stop.get("name", ""))),
                    float(stop.get("latitude", 0.0)),
                    float(stop.get("longitude", 0.0)),
                    str(stop.get("priority", "Normal")),
                    float(stop.get("weight_kg", 0.0)),
                    str(stop.get("time_window", "Anytime")),
                    str(stop.get("delivery_status", "Pending")),
                    float(stop.get("leg_distance_km", 0.0)),
                    float(stop.get("est_arrival_min", 0.0))
                ))

            conn.commit()
            logger.info("Saved route #%d with %d stops", route_id, len(stops_list))
            return route_id

    def get_all_routes(self) -> List[Dict[str, Any]]:
        """Retrieve summary list of all planned routes, newest first."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, created_at, route_name, depot_name, num_stops,
                       total_distance_km, est_time_mins, baseline_distance_km,
                       saved_distance_km, saved_pct, algorithm, search_method,
                       round_trip, vehicle_capacity_kg, total_weight_kg, status
                FROM routes
                ORDER BY id DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_route_details(self, route_id: int) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """Retrieve full details of a route and its ordered stops."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM routes WHERE id = ?", (route_id,))
            route_row = cursor.fetchone()
            if not route_row:
                return None, []

            cursor.execute("""
                SELECT * FROM route_stops
                WHERE route_id = ?
                ORDER BY stop_order ASC
            """, (route_id,))
            stops = [dict(row) for row in cursor.fetchall()]
            return dict(route_row), stops

    def update_stop_status(self, stop_id: int, new_status: str) -> bool:
        """Update delivery status of a stop ('Delivered', 'Skipped', 'Pending')."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE route_stops
                SET delivery_status = ?
                WHERE id = ?
            """, (new_status, stop_id))
            conn.commit()
            return cursor.rowcount > 0

    def update_route_status(self, route_id: int, new_status: str) -> bool:
        """Update overall status of a route ('Planned', 'In Progress', 'Completed', 'Partial')."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE routes
                SET status = ?
                WHERE id = ?
            """, (new_status, route_id))
            conn.commit()
            return cursor.rowcount > 0

    def delete_route(self, route_id: int) -> bool:
        """Delete a route and its stops."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM routes WHERE id = ?", (route_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_performance_summary(self) -> Dict[str, Any]:
        """Compute aggregated performance metrics across all historical routes."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_routes,
                    AVG(total_distance_km) as avg_distance,
                    AVG(saved_pct) as avg_saved_pct,
                    AVG(est_time_mins) as avg_time,
                    SUM(num_stops) as total_stops_planned
                FROM routes
            """)
            row = cursor.fetchone()
            if not row or row["total_routes"] == 0:
                return {
                    "total_routes": 0,
                    "avg_distance": 0.0,
                    "avg_saved_pct": 0.0,
                    "avg_time": 0.0,
                    "total_stops_planned": 0,
                    "algorithm_breakdown": []
                }

            summary = dict(row)
            cursor.execute("""
                SELECT algorithm, COUNT(*) as count, AVG(saved_pct) as avg_savings, AVG(total_distance_km) as avg_dist
                FROM routes
                GROUP BY algorithm
            """)
            summary["algorithm_breakdown"] = [dict(r) for r in cursor.fetchall()]
            return summary
