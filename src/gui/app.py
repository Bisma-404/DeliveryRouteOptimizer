"""
Delivery Route Optimizer — User-Centric Dispatcher Application
================================================================
Student : Bisma Shahid   |  Roll: 24K-3012  |  BSE-5A
Course  : AI Lab (Fall 2026)  |  FAST-NUCES

Key Workflows:
1. Starts with an EMPTY route — no predefined stops or depot.
2. Real-time location search with responsive autocomplete as you type (e.g. FAST, DHA, Clifton).
3. Clicking a suggestion centers the map and displays "Set as Depot" and "Add as Delivery Stop".
4. Clean side panel managing depot and customer delivery cards with priority, weight, and removal.
5. Large interactive map as the primary focal point of the application.
6. Route optimization with road-following polyline, distance, estimated time, and savings.
7. Delivery simulation with active stop checkoffs ("Mark Completed" / "Skip Stop").
8. SQLite Route History modal for reviewing and re-loading saved trips.
"""

from __future__ import annotations

import os
import sys
import time
import math
import random
import queue
import threading
import logging
from typing import List, Tuple, Dict, Any, Optional

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk

import tkintermapview

from ..data.graph_loader import GraphLoader
from ..data.geocoder import LocationGeocoder
from ..data.database import DatabaseManager
from ..core.astar import AStarPlanner, haversine_distance
from ..core.problem import RouteProblem
from ..core.solvers import (
    NearestNeighborSolver,
    HillClimbSolver,
    SimulatedAnnealingSolver,
    GeneticSolver,
)

logger = logging.getLogger(__name__)

TILE_SERVERS: Dict[str, str] = {
    "Google Maps (Standard)":
        "https://mt0.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}&s=Ga",
    "CartoDB Voyager (Modern)":
        "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
    "CartoDB Positron (Clean)":
        "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
    "OpenStreetMap Standard":
        "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
}
DEFAULT_TILE = "Google Maps (Standard)"

C = {
    "bg":           "#0D1117",
    "sidebar":      "#161B22",
    "card":         "#1C2333",
    "card_border":  "#30363D",
    "header":       "#0F172A",
    "primary":      "#3B82F6",
    "primary_dark": "#1D4ED8",
    "success":      "#10B981",
    "warning":      "#F59E0B",
    "danger":       "#EF4444",
    "purple":       "#8B5CF6",
    "cyan":         "#06B6D4",
    "text":         "#E6EDF3",
    "muted":        "#8B949E",
    "accent":       "#58A6FF",
}

SOLVER_MAP = {
    "SA": ("Simulated Annealing", SimulatedAnnealingSolver),
    "GA": ("Genetic Algorithm", GeneticSolver),
    "HC": ("Hill Climbing (2-opt)", HillClimbSolver),
    "NN": ("Nearest Neighbor (Baseline)", NearestNeighborSolver),
}


def _btn(parent, text, cmd, bg=C["card"], fg=C["text"], font_size=9,
         bold=True, pady=5, padx=10, cursor="hand2", **kw) -> tk.Button:
    """Helper to create flat styled button with hover effect."""
    weight = "bold" if bold else "normal"
    b = tk.Button(
        parent, text=text, command=cmd,
        bg=bg, fg=fg, activebackground=bg, activeforeground="#FFFFFF",
        font=("Segoe UI", font_size, weight),
        relief=tk.FLAT, padx=padx, pady=pady, cursor=cursor, **kw
    )
    b.bind("<Enter>", lambda e: b.config(bg=_lighten(bg)))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b


def _lighten(hex_col: str, amount: int = 18) -> str:
    """Lighten a hex color string for hover state."""
    try:
        r = min(255, int(hex_col[1:3], 16) + amount)
        g = min(255, int(hex_col[3:5], 16) + amount)
        b = min(255, int(hex_col[5:7], 16) + amount)
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return hex_col


def _lbl(parent, text, size=9, fg=C["text"], bg=C["card"], bold=False,
         anchor="w", **kw) -> tk.Label:
    weight = "bold" if bold else "normal"
    return tk.Label(parent, text=text, font=("Segoe UI", size, weight),
                    fg=fg, bg=bg, anchor=anchor, **kw)


class DeliveryRouteOptimizerApp:
    """Production-quality Delivery Route Planner application."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Delivery Route Optimizer · FAST-NUCES · Bisma Shahid (24K-3012)")
        self.root.configure(bg=C["bg"])

        # Window geometry
        try:
            self.root.state("zoomed")
        except tk.TclError:
            self.root.geometry("1440x920")
        self.root.minsize(1100, 680)
        self._is_fullscreen = False
        self.root.bind("<F11>", self._toggle_fullscreen)
        self.root.bind("<Escape>", self._exit_fullscreen)

        # ── State (Starts completely EMPTY as requested) ───────────────────────
        self.graph_loader: Optional[GraphLoader] = None
        self.astar_planner: Optional[AStarPlanner] = None
        self.geocoder: Optional[LocationGeocoder] = None
        self.db: DatabaseManager = DatabaseManager()

        # Route locations (EMPTY at launch)
        self.depot_stop: Optional[Dict[str, Any]] = None
        self.customer_deliveries: List[Dict[str, Any]] = []
        self.current_stops: List[Dict[str, Any]] = []

        # Currently inspected/previewed location from search
        self.preview_location: Optional[Dict[str, Any]] = None
        self.preview_marker: Optional[Any] = None

        # Autocomplete search debounce timer
        self._search_debounce_job: Optional[str] = None
        self._current_suggestions: List[Dict[str, Any]] = []

        # Route results
        self.problem: Optional[RouteProblem] = None
        self.distance_matrix = None
        self.detailed_paths = None
        self.total_nodes_expanded = 0
        self.optimized_tour: Optional[List[int]] = None
        self.optimized_cost_km: float = 0.0
        self.baseline_cost_km: float = 0.0
        self.saved_distance_km: float = 0.0
        self.saved_pct: float = 0.0
        self.solver_runtime: float = 0.0
        self.route_coords: List[Tuple[float, float]] = []
        self.active_solver_name = "Simulated Annealing"

        # Simulation
        self._simulating = False
        self._sim_paused = False
        self._sim_stop_requested = False
        self._sim_van_marker: Optional[Any] = None
        self._delivery_statuses: Dict[int, str] = {}

        # Map display handles
        self._stop_markers: List[Any] = []
        self._route_path: Optional[Any] = None

        # Thread-safe UI queue for Python 3.13 cross-thread updates
        self._ui_queue: queue.Queue = queue.Queue()

        # ── Build Interface ───────────────────────────────────────────────────
        self._setup_ttk_styles()
        self._build_header()
        self._build_main_layout()

        # Start thread-safe UI dispatcher loop
        self._poll_ui_queue()

        # Load Karachi road graph in background
        self.root.after(200, self._init_road_graph)

    def _setup_ttk_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "TCombobox",
            fieldbackground=C["card"],
            background=C["sidebar"],
            foreground=C["text"],
            arrowcolor=C["accent"],
            selectbackground=C["primary"]
        )
        style.configure(
            "TSpinbox",
            fieldbackground=C["card"],
            background=C["sidebar"],
            foreground=C["text"],
            arrowcolor=C["accent"]
        )
        style.configure(
            "Blue.Horizontal.TProgressbar",
            troughcolor=C["card"],
            background=C["primary"]
        )
        style.map("TCombobox", fieldbackground=[("readonly", C["card"])])

    # ──────────────────────────────────────────────────────────────────────────
    #  Compact Header Bar
    # ──────────────────────────────────────────────────────────────────────────
    def _build_header(self) -> None:
        hdr = tk.Frame(self.root, bg=C["header"], height=52)
        hdr.pack(side=tk.TOP, fill=tk.X)
        hdr.pack_propagate(False)

        # Left branding
        left = tk.Frame(hdr, bg=C["header"])
        left.pack(side=tk.LEFT, padx=14, fill=tk.Y)

        tk.Label(
            left, text=" 🚀 FAST-NUCES ",
            font=("Segoe UI", 10, "bold"),
            bg="#1E3A8A", fg="#93C5FD", padx=4, pady=3
        ).pack(side=tk.LEFT, padx=(0, 10), pady=10)

        tk.Label(
            left, text="Delivery Route Optimizer",
            font=("Segoe UI", 13, "bold"),
            bg=C["header"], fg=C["text"]
        ).pack(side=tk.LEFT)

        tk.Label(
            left, text="Karachi City Logistics",
            font=("Segoe UI", 8),
            bg=C["header"], fg=C["muted"]
        ).pack(side=tk.LEFT, padx=10, pady=16)

        # Right utility buttons
        right = tk.Frame(hdr, bg=C["header"])
        right.pack(side=tk.RIGHT, padx=14, fill=tk.Y)

        tk.Label(
            right, text="Bisma Shahid · 24K-3012 · BSE-5A",
            font=("Segoe UI", 9), bg=C["header"], fg=C["muted"]
        ).pack(side=tk.LEFT, padx=(0, 12), pady=16)

        _btn(
            right, "📜 Route History (SQLite)", self._open_history_modal,
            bg="#1E293B", fg=C["accent"], font_size=8, pady=4
        ).pack(side=tk.LEFT, padx=4, pady=10)

        _btn(
            right, "⛶ Fullscreen (F11)", self._toggle_fullscreen,
            bg="#1E293B", fg=C["muted"], font_size=8, pady=4
        ).pack(side=tk.LEFT, pady=10)

    # ──────────────────────────────────────────────────────────────────────────
    #  Main Split Layout: Left Control Panel + Right Map & Search
    # ──────────────────────────────────────────────────────────────────────────
    def _build_main_layout(self) -> None:
        self.body_container = tk.Frame(self.root, bg=C["bg"])
        self.body_container.pack(fill=tk.BOTH, expand=True)

        # ── LEFT SIDEBAR: Route Locations & Parameters ────────────────────────
        sidebar_w = 430
        self.sidebar_outer = tk.Frame(self.body_container, bg=C["sidebar"], width=sidebar_w)
        self.sidebar_outer.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar_outer.pack_propagate(False)

        # Scrollable container for stops
        self.sb_canvas = tk.Canvas(self.sidebar_outer, bg=C["sidebar"], highlightthickness=0, bd=0)
        self.sb_scroll = tk.Scrollbar(self.sidebar_outer, orient=tk.VERTICAL, command=self.sb_canvas.yview)
        self.sb_inner = tk.Frame(self.sb_canvas, bg=C["sidebar"])

        self.sb_inner.bind(
            "<Configure>",
            lambda e: self.sb_canvas.configure(scrollregion=self.sb_canvas.bbox("all"))
        )
        self.sb_canvas.create_window((0, 0), window=self.sb_inner, anchor="nw", width=sidebar_w - 14)
        self.sb_canvas.configure(yscrollcommand=self.sb_scroll.set)
        self.sb_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.sb_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.sb_canvas.bind_all(
            "<MouseWheel>",
            lambda e: self.sb_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        )

        # Left Panel Sections:
        self._build_depot_section()
        self._build_stops_section()
        self._build_settings_section()
        self._build_results_section()

        # ── RIGHT PANEL: Search Bar + Autocomplete + Interactive Map ──────────
        self.right_panel = tk.Frame(self.body_container, bg=C["bg"])
        self.right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Location Search Container
        self._build_search_and_action_bar()

        # Main Map Widget
        self.map_container = tk.Frame(self.right_panel, bg="#000000")
        self.map_container.pack(fill=tk.BOTH, expand=True)

        self.map_widget = tkintermapview.TkinterMapView(self.map_container, corner_radius=0)
        self.map_widget.pack(fill=tk.BOTH, expand=True)
        self.map_widget.set_tile_server(TILE_SERVERS[DEFAULT_TILE])
        self.map_widget.set_position(24.8607, 67.0011)  # Center Karachi
        self.map_widget.set_zoom(13)

        # Right-click context menu on map
        self.map_widget.add_right_click_menu_command(
            label="🚩 Set as Starting Depot",
            command=self._on_map_set_depot,
            pass_coords=True
        )
        self.map_widget.add_right_click_menu_command(
            label="📦 Add Customer Delivery Here",
            command=self._on_map_add_delivery,
            pass_coords=True
        )

        # Simulation Bar overlay (bottom of map)
        self._build_simulation_dock()

        # Status text bar at bottom of left panel
        self.status_var = tk.StringVar(value="Search for a location to add your depot and deliveries.")
        status_bar = tk.Frame(self.sidebar_outer, bg="#0A0E17", height=26)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Label(
            status_bar, textvariable=self.status_var,
            font=("Segoe UI", 8), bg="#0A0E17", fg=C["accent"], anchor="w", padx=8
        ).pack(fill=tk.BOTH, expand=True)

    # ──────────────────────────────────────────────────────────────────────────
    #  Top Location Autocomplete Search Bar & Action Ribbon
    # ──────────────────────────────────────────────────────────────────────────
    def _build_search_and_action_bar(self) -> None:
        """Build the prominent location search bar with live autocomplete as you type."""
        self.search_bar_frame = tk.Frame(self.right_panel, bg=C["header"], padx=12, pady=8)
        self.search_bar_frame.pack(side=tk.TOP, fill=tk.X)

        # Search row
        s_row = tk.Frame(self.search_bar_frame, bg=C["header"])
        s_row.pack(fill=tk.X)

        tk.Label(
            s_row, text="🔍", font=("Segoe UI", 12),
            bg=C["header"], fg=C["accent"]
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.search_input_var = tk.StringVar()
        self.search_entry = tk.Entry(
            s_row, textvariable=self.search_input_var,
            font=("Segoe UI", 10), bg="#0D1117", fg=C["text"],
            insertbackground=C["accent"], relief=tk.FLAT
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", self._on_search_key_release)
        self.search_entry.bind("<FocusOut>", self._on_search_focus_out)

        # Map layer switcher
        _lbl(s_row, "Map:", size=8, fg=C["muted"], bg=C["header"]).pack(side=tk.LEFT, padx=(4, 2))
        self.tile_var = tk.StringVar(value=DEFAULT_TILE)
        tile_cb = ttk.Combobox(
            s_row, textvariable=self.tile_var, values=list(TILE_SERVERS.keys()),
            state="readonly", width=18, font=("Segoe UI", 8)
        )
        tile_cb.pack(side=tk.LEFT, padx=2)
        tile_cb.bind("<<ComboboxSelected>>", self._on_tile_server_changed)

        # Autocomplete Dropdown Listbox (appears as you type)
        self.autocomplete_dropdown = tk.Listbox(
            self.search_bar_frame, height=5,
            bg="#161B22", fg=C["text"], selectbackground=C["primary"],
            font=("Segoe UI", 9), highlightthickness=1,
            highlightbackground=C["card_border"], relief=tk.FLAT
        )
        self.autocomplete_dropdown.bind("<<ListboxSelect>>", self._on_select_suggestion)

        # Action Ribbon (appears after a suggestion is clicked or map is clicked)
        self.action_ribbon = tk.Frame(self.search_bar_frame, bg=C["card"], bd=1, relief=tk.SOLID, padx=10, pady=8)

        self.lbl_selected_place = tk.Label(
            self.action_ribbon, text="Selected Location: --",
            font=("Segoe UI", 9, "bold"), bg=C["card"], fg=C["accent"], anchor="w"
        )
        self.lbl_selected_place.pack(fill=tk.X)

        self.lbl_selected_addr = tk.Label(
            self.action_ribbon, text="Address: --",
            font=("Segoe UI", 8), bg=C["card"], fg=C["muted"], anchor="w"
        )
        self.lbl_selected_addr.pack(fill=tk.X, pady=(1, 6))

        # Inputs for adding customer stop
        ribbon_inputs = tk.Frame(self.action_ribbon, bg=C["card"])
        ribbon_inputs.pack(fill=tk.X, pady=(0, 6))

        _lbl(ribbon_inputs, "Customer Name:", size=8, fg=C["muted"]).pack(side=tk.LEFT)
        self.cust_name_var = tk.StringVar()
        tk.Entry(
            ribbon_inputs, textvariable=self.cust_name_var,
            bg="#0D1117", fg=C["text"], insertbackground=C["accent"],
            font=("Segoe UI", 8), width=18, relief=tk.FLAT
        ).pack(side=tk.LEFT, padx=(4, 12), ipady=2)

        _lbl(ribbon_inputs, "Priority:", size=8, fg=C["muted"]).pack(side=tk.LEFT)
        self.cust_priority_var = tk.StringVar(value="Normal")
        ttk.Combobox(
            ribbon_inputs, textvariable=self.cust_priority_var,
            values=["Normal", "Urgent"], state="readonly", width=8,
            font=("Segoe UI", 8)
        ).pack(side=tk.LEFT, padx=(4, 12))

        _lbl(ribbon_inputs, "Weight (kg):", size=8, fg=C["muted"]).pack(side=tk.LEFT)
        self.cust_weight_var = tk.DoubleVar(value=5.0)
        ttk.Spinbox(
            ribbon_inputs, from_=0.5, to=50.0, increment=0.5,
            textvariable=self.cust_weight_var, width=5
        ).pack(side=tk.LEFT, padx=4)

        # Two primary workflow buttons
        ribbon_btns = tk.Frame(self.action_ribbon, bg=C["card"])
        ribbon_btns.pack(fill=tk.X)

        self.btn_set_depot = _btn(
            ribbon_btns, "🚩 Set as Starting Depot", self._on_confirm_set_depot,
            bg=C["success"], fg="#fff", font_size=9, pady=5
        )
        self.btn_set_depot.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.btn_add_stop = _btn(
            ribbon_btns, "📦 Add as Delivery Stop", self._on_confirm_add_stop,
            bg=C["primary"], fg="#fff", font_size=9, pady=5
        )
        self.btn_add_stop.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(4, 0))

    # ──────────────────────────────────────────────────────────────────────────
    #  Left Sidebar Sections
    # ──────────────────────────────────────────────────────────────────────────
    def _make_card(self, title: str, icon: str = "") -> tk.Frame:
        wrapper = tk.Frame(self.sb_inner, bg=C["sidebar"], padx=8, pady=4)
        wrapper.pack(fill=tk.X)

        hrow = tk.Frame(wrapper, bg=C["sidebar"])
        hrow.pack(fill=tk.X, pady=(0, 3))
        if icon:
            tk.Label(hrow, text=icon, font=("Segoe UI", 10), bg=C["sidebar"], fg=C["accent"]).pack(side=tk.LEFT)
        tk.Label(hrow, text=f" {title}", font=("Segoe UI", 9, "bold"), bg=C["sidebar"], fg=C["accent"]).pack(side=tk.LEFT)

        card = tk.Frame(
            wrapper, bg=C["card"], bd=0, highlightthickness=1,
            highlightbackground=C["card_border"], padx=10, pady=8
        )
        card.pack(fill=tk.X)
        return card

    def _build_depot_section(self) -> None:
        """Card for displaying active starting depot."""
        self.depot_card = self._make_card("STARTING DEPOT", icon="🚩")

        self.lbl_depot_name = tk.Label(
            self.depot_card, text="No depot selected yet.",
            font=("Segoe UI", 9, "bold"), bg=C["card"], fg=C["muted"], anchor="w"
        )
        self.lbl_depot_name.pack(fill=tk.X)

        self.lbl_depot_addr = tk.Label(
            self.depot_card, text="Search for a location above to set your depot.",
            font=("Segoe UI", 8), bg=C["card"], fg=C["muted"], anchor="w", wraplength=380
        )
        self.lbl_depot_addr.pack(fill=tk.X, pady=(2, 4))

        self.depot_actions_row = tk.Frame(self.depot_card, bg=C["card"])

        self.btn_clear_depot = _btn(
            self.depot_actions_row, "Clear Depot", self._on_clear_depot,
            bg="#374151", fg=C["danger"], font_size=7, pady=2
        )
        self.btn_clear_depot.pack(side=tk.LEFT)

    def _build_stops_section(self) -> None:
        """Card for listing and managing customer delivery stops."""
        self.stops_card = self._make_card("CUSTOMER DELIVERIES", icon="📦")

        # Top row: counter + clear button
        top_r = tk.Frame(self.stops_card, bg=C["card"])
        top_r.pack(fill=tk.X, pady=(0, 4))

        self.lbl_stops_counter = tk.Label(
            top_r, text="0 Delivery Stops Added",
            font=("Segoe UI", 8, "bold"), bg=C["card"], fg=C["muted"]
        )
        self.lbl_stops_counter.pack(side=tk.LEFT)

        self.btn_clear_all_stops = _btn(
            top_r, "Clear All", self._on_clear_all_stops,
            bg="#374151", fg=C["muted"], font_size=7, pady=2, padx=6
        )
        self.btn_clear_all_stops.pack(side=tk.RIGHT)

        # Dynamic scrollable stops list container
        self.stops_list_frame = tk.Frame(self.stops_card, bg=C["card"])
        self.stops_list_frame.pack(fill=tk.BOTH, expand=True)

        self.lbl_empty_stops_notice = tk.Label(
            self.stops_list_frame,
            text="No delivery stops added yet.\nSearch locations above and click 'Add as Delivery Stop'.",
            font=("Segoe UI", 8, "italic"), bg=C["card"], fg=C["muted"], pady=12, justify=tk.CENTER
        )
        self.lbl_empty_stops_notice.pack(fill=tk.X)

    def _build_settings_section(self) -> None:
        """Routing parameters and Optimize Route action button."""
        card = self._make_card("ROUTING PARAMETERS", icon="⚙️")

        r1 = tk.Frame(card, bg=C["card"])
        r1.pack(fill=tk.X, pady=2)

        _lbl(r1, "AI Optimizer:", size=8, fg=C["muted"]).pack(side=tk.LEFT)
        self.solver_var = tk.StringVar(value="Simulated Annealing")
        s_cb = ttk.Combobox(
            r1, textvariable=self.solver_var,
            values=[
                "Simulated Annealing",
                "Genetic Algorithm",
                "Hill Climbing (2-opt)",
                "Nearest Neighbor (Baseline)"
            ],
            state="readonly", width=22, font=("Segoe UI", 8)
        )
        s_cb.pack(side=tk.RIGHT)

        r2 = tk.Frame(card, bg=C["card"])
        r2.pack(fill=tk.X, pady=3)

        self.round_trip_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            r2, text="Round Trip (Return to depot)",
            variable=self.round_trip_var, bg=C["card"], fg=C["text"],
            selectcolor="#0D1117", activebackground=C["card"],
            font=("Segoe UI", 8)
        ).pack(side=tk.LEFT)

        r3 = tk.Frame(card, bg=C["card"])
        r3.pack(fill=tk.X, pady=2)
        _lbl(r3, "Max Vehicle Capacity (kg):", size=8, fg=C["muted"]).pack(side=tk.LEFT)
        self.capacity_var = tk.DoubleVar(value=50.0)
        ttk.Spinbox(r3, from_=10.0, to=500.0, increment=5.0, textvariable=self.capacity_var, width=6).pack(side=tk.RIGHT)

        # Prominent Optimize Route Button (Disabled until depot + 1 stop)
        btn_wrap = tk.Frame(self.sb_inner, bg=C["sidebar"], padx=8, pady=6)
        btn_wrap.pack(fill=tk.X)

        self.btn_optimize = _btn(
            btn_wrap, "🚀  OPTIMIZE ROUTE", self._on_optimize_route_clicked,
            bg="#238636", fg="#FFFFFF", font_size=11, bold=True, pady=9
        )
        self.btn_optimize.pack(fill=tk.X)
        self.btn_optimize.config(state=tk.DISABLED)

    def _build_results_section(self) -> None:
        """Card for displaying optimization metrics and results (hidden until solved)."""
        self.results_card_wrapper = tk.Frame(self.sb_inner, bg=C["sidebar"], padx=8, pady=4)
        # Will pack upon route optimization

        hrow = tk.Frame(self.results_card_wrapper, bg=C["sidebar"])
        hrow.pack(fill=tk.X, pady=(0, 3))
        tk.Label(hrow, text="🏁", font=("Segoe UI", 10), bg=C["sidebar"], fg=C["success"]).pack(side=tk.LEFT)
        tk.Label(hrow, text=" ROUTE SUMMARY & METRICS", font=("Segoe UI", 9, "bold"), bg=C["sidebar"], fg=C["success"]).pack(side=tk.LEFT)

        card = tk.Frame(
            self.results_card_wrapper, bg=C["card"], bd=0, highlightthickness=1,
            highlightbackground=C["card_border"], padx=10, pady=8
        )
        card.pack(fill=tk.X)

        # 2x2 grid of metrics
        grid = tk.Frame(card, bg=C["card"])
        grid.pack(fill=tk.X)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        def make_box(parent, title, default, row, col, fg):
            b = tk.Frame(parent, bg="#0D1117", bd=1, relief=tk.SOLID, padx=6, pady=5)
            b.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")
            tk.Label(b, text=title, font=("Segoe UI", 7, "bold"), bg="#0D1117", fg=C["muted"]).pack(anchor="w")
            v = tk.Label(b, text=default, font=("Segoe UI", 12, "bold"), bg="#0D1117", fg=fg)
            v.pack(anchor="w")
            return v

        self.res_val_dist = make_box(grid, "ROAD DISTANCE", "-- km", 0, 0, C["warning"])
        self.res_val_time = make_box(grid, "EST. JOURNEY TIME", "-- min", 0, 1, C["cyan"])
        self.res_val_saved = make_box(grid, "SAVED vs BASELINE", "-- %", 1, 0, C["success"])
        self.res_val_runtime = make_box(grid, "SOLVER RUNTIME", "-- s", 1, 1, C["purple"])

        self.lbl_disclaimer = tk.Label(
            card, text="* Estimated at 30 km/h average city speed + 5 min per stop.",
            font=("Segoe UI", 7), bg=C["card"], fg=C["muted"], justify=tk.LEFT
        )
        self.lbl_disclaimer.pack(anchor="w", pady=(4, 6))

        # Actions
        r_btns = tk.Frame(card, bg=C["card"])
        r_btns.pack(fill=tk.X)

        self.btn_sim_toggle = _btn(
            r_btns, "▶ Start Delivery Simulation", self._on_start_simulation_clicked,
            bg=C["primary"], fg="#fff", font_size=8, pady=4
        )
        self.btn_sim_toggle.pack(fill=tk.X, pady=(0, 4))

        _btn(
            r_btns, "💾 Save Route to SQLite History", self._on_save_route_to_sqlite,
            bg=C["purple"], fg="#fff", font_size=8, pady=3
        ).pack(fill=tk.X)

    def _build_simulation_dock(self) -> None:
        """Bottom simulation dock floating over the map when simulation is active."""
        self.sim_dock = tk.Frame(self.map_container, bg=C["card"], bd=1, relief=tk.SOLID, padx=12, pady=6)
        # Hidden until simulation starts

        self.lbl_sim_status = tk.Label(
            self.sim_dock, text="Delivery Simulation: Active",
            font=("Segoe UI", 9, "bold"), bg=C["card"], fg=C["accent"]
        )
        self.lbl_sim_status.pack(side=tk.LEFT, padx=(0, 12))

        self.lbl_sim_stop_name = tk.Label(
            self.sim_dock, text="Current Stop: --",
            font=("Segoe UI", 8), bg=C["card"], fg=C["text"]
        )
        self.lbl_sim_stop_name.pack(side=tk.LEFT, padx=(0, 12))

        _btn(
            self.sim_dock, "✓ Mark Completed", self._on_sim_mark_done,
            bg=C["success"], fg="#fff", font_size=8, pady=2, padx=8
        ).pack(side=tk.LEFT, padx=3)

        _btn(
            self.sim_dock, "⏭ Skip Stop", self._on_sim_skip_stop,
            bg=C["warning"], fg="#000", font_size=8, pady=2, padx=8
        ).pack(side=tk.LEFT, padx=3)

        _btn(
            self.sim_dock, "⏸ Pause", self._on_sim_pause,
            bg="#374151", fg=C["text"], font_size=8, pady=2, padx=6
        ).pack(side=tk.LEFT, padx=3)

        _btn(
            self.sim_dock, "⏹ Stop", self._on_sim_stop,
            bg="#374151", fg=C["danger"], font_size=8, pady=2, padx=6
        ).pack(side=tk.RIGHT)

    # ══════════════════════════════════════════════════════════════════════════
    #  Autocomplete & Search Logic (Live while typing)
    # ══════════════════════════════════════════════════════════════════════════
    def _on_search_key_release(self, event=None) -> None:
        """Triggered on every keystroke in search bar with debounce."""
        if event and event.keysym in ("Up", "Down", "Return", "Escape"):
            return

        q = self.search_input_var.get().strip()
        if len(q) < 1:
            self.autocomplete_dropdown.pack_forget()
            return

        # Cancel previous debounce timer
        if self._search_debounce_job is not None:
            self.root.after_cancel(self._search_debounce_job)

        # Schedule search after 250ms
        self._search_debounce_job = self.root.after(250, lambda: self._execute_search(q))

    def _execute_search(self, query: str) -> None:
        """Execute autocomplete matching and display suggestions."""
        if not self.geocoder:
            return

        self.autocomplete_dropdown.delete(0, tk.END)
        results = self.geocoder.search_places(query, limit=7)
        self._current_suggestions = results

        if not results:
            self.autocomplete_dropdown.insert(tk.END, "  No matching Karachi locations found.")
            self.autocomplete_dropdown.pack(fill=tk.X, pady=(2, 4))
            return

        for r in results:
            display_txt = f"  📍 {r['name']} — {r.get('category', 'Place')}"
            self.autocomplete_dropdown.insert(tk.END, display_txt)

        self.autocomplete_dropdown.pack(fill=tk.X, pady=(2, 4))

    def _on_select_suggestion(self, event=None) -> None:
        """When user clicks a suggestion from the dropdown."""
        sel = self.autocomplete_dropdown.curselection()
        if not sel or not self._current_suggestions:
            return

        idx = sel[0]
        if idx >= len(self._current_suggestions):
            return

        place = self._current_suggestions[idx]
        self.preview_location = place

        # Update search bar and hide dropdown
        self.search_input_var.set(place["name"])
        self.autocomplete_dropdown.pack_forget()

        # Center map on selected location and zoom in
        lat, lon = place["latitude"], place["longitude"]
        self.map_widget.set_position(lat, lon)
        self.map_widget.set_zoom(15)

        # Place temporary preview pin
        if self.preview_marker:
            try:
                self.preview_marker.delete()
            except Exception:
                pass
        self.preview_marker = self.map_widget.set_marker(
            lat, lon, text=f"📍 {place['name'][:24]}",
            marker_color_circle=C["cyan"], marker_color_outside="#0E7490"
        )

        # Show Action Ribbon with location details and buttons
        self.lbl_selected_place.config(text=f"Selected: {place['name']}")
        self.lbl_selected_addr.config(text=f"Address: {place['address']}")
        self.cust_name_var.set(place["name"])
        self.action_ribbon.pack(fill=tk.X, pady=(6, 0))
        self._set_status(f"Selected: {place['name']}. Choose 'Set as Depot' or 'Add as Delivery Stop'.")

    def _on_search_focus_out(self, event=None) -> None:
        """Hide dropdown when focus leaves search area after slight delay."""
        def check_focus():
            try:
                focused = self.root.focus_get()
                if focused != self.autocomplete_dropdown:
                    self.autocomplete_dropdown.pack_forget()
            except Exception:
                pass
        self.root.after(250, check_focus)

    # ──────────────────────────────────────────────────────────────────────────
    #  Location Action Handlers (Set Depot / Add Stop)
    # ──────────────────────────────────────────────────────────────────────────
    def _on_confirm_set_depot(self) -> None:
        """Set preview location as starting depot."""
        if not self.preview_location or not self.geocoder:
            return

        loc = self.preview_location
        snapped = self.geocoder.snap_location(loc["name"], loc["address"], loc["latitude"], loc["longitude"])
        snapped["type"] = "depot"
        snapped["priority"] = "Normal"
        snapped["weight_kg"] = 0.0
        self.depot_stop = snapped

        # Update depot card
        self.lbl_depot_name.config(text=f"🚩 {snapped['name']}", fg=C["success"])
        self.lbl_depot_addr.config(text=snapped["address"])
        self.depot_actions_row.pack(fill=tk.X, pady=(2, 0))

        # Clear preview ribbon & marker
        self._clear_preview()
        self._render_all_map_markers()
        self._check_optimization_ready()
        self._set_status(f"✓ Depot set: {snapped['name']}.")

    def _on_confirm_add_stop(self) -> None:
        """Add preview location as a customer delivery stop."""
        if not self.preview_location or not self.geocoder:
            return

        loc = self.preview_location
        c_name = self.cust_name_var.get().strip() or loc["name"]
        prio = self.cust_priority_var.get()
        wt = self.cust_weight_var.get()

        snapped = self.geocoder.snap_location(c_name, loc["address"], loc["latitude"], loc["longitude"])
        snapped["priority"] = prio
        snapped["weight_kg"] = wt
        snapped["type"] = "delivery"

        self.customer_deliveries.append(snapped)
        self._refresh_stops_panel()
        self._clear_preview()
        self._render_all_map_markers()
        self._check_optimization_ready()
        self._set_status(f"✓ Added delivery stop #{len(self.customer_deliveries)}: {c_name}.")

    def _clear_preview(self) -> None:
        """Hide action ribbon and clear temporary preview marker."""
        self.action_ribbon.pack_forget()
        self.search_input_var.set("")
        if self.preview_marker:
            try:
                self.preview_marker.delete()
            except Exception:
                pass
            self.preview_marker = None
        self.preview_location = None

    def _on_clear_depot(self) -> None:
        """Clear active depot."""
        self.depot_stop = None
        self.lbl_depot_name.config(text="No depot selected yet.", fg=C["muted"])
        self.lbl_depot_addr.config(text="Search for a location above to set your depot.")
        self.depot_actions_row.pack_forget()
        self._render_all_map_markers()
        self._check_optimization_ready()
        self._set_status("Depot cleared. Search a location to set a new depot.")

    def _on_clear_all_stops(self) -> None:
        """Clear all customer delivery stops."""
        if not self.customer_deliveries:
            return
        if messagebox.askyesno("Clear Deliveries", "Remove all customer delivery stops?"):
            self.customer_deliveries.clear()
            self._refresh_stops_panel()
            self._render_all_map_markers()
            self._clear_route_polyline()
            self._check_optimization_ready()
            self._set_status("All delivery stops cleared.")

    def _refresh_stops_panel(self) -> None:
        """Re-render the list of delivery cards in the left panel."""
        for child in self.stops_list_frame.winfo_children():
            child.destroy()

        count = len(self.customer_deliveries)
        self.lbl_stops_counter.config(text=f"{count} Delivery Stop{'s' if count != 1 else ''} Added")

        if count == 0:
            self.lbl_empty_stops_notice = tk.Label(
                self.stops_list_frame,
                text="No delivery stops added yet.\nSearch locations above and click 'Add as Delivery Stop'.",
                font=("Segoe UI", 8, "italic"), bg=C["card"], fg=C["muted"], pady=12, justify=tk.CENTER
            )
            self.lbl_empty_stops_notice.pack(fill=tk.X)
            return

        for idx, stop in enumerate(self.customer_deliveries, 1):
            s_card = tk.Frame(self.stops_list_frame, bg="#0D1117", bd=1, relief=tk.SOLID, padx=8, pady=6)
            s_card.pack(fill=tk.X, pady=3)

            # Top row: Stop number & name + remove button
            top_line = tk.Frame(s_card, bg="#0D1117")
            top_line.pack(fill=tk.X)

            is_urgent = str(stop.get("priority")).lower() == "urgent"
            prio_badge = "⚡ " if is_urgent else ""
            title_col = C["danger"] if is_urgent else C["text"]

            tk.Label(
                top_line, text=f"#{idx} {prio_badge}{stop['name'][:22]}",
                font=("Segoe UI", 9, "bold"), bg="#0D1117", fg=title_col
            ).pack(side=tk.LEFT)

            _btn(
                top_line, "✕", lambda i=idx-1: self._on_remove_single_stop(i),
                bg="#0D1117", fg=C["danger"], font_size=8, bold=True, pady=0, padx=4
            ).pack(side=tk.RIGHT)

            _btn(
                top_line, "✏", lambda i=idx-1: self._on_edit_single_stop(i),
                bg="#0D1117", fg=C["accent"], font_size=8, pady=0, padx=4
            ).pack(side=tk.RIGHT, padx=4)

            # Details: Address + Weight + Priority
            addr_txt = stop.get("address", "")[:35]
            wt_txt = f"{stop.get('weight_kg', 5.0):.1f} kg"
            p_txt = "Urgent" if is_urgent else "Normal"

            tk.Label(
                s_card, text=f"{addr_txt}\nPayload: {wt_txt} · Priority: {p_txt}",
                font=("Segoe UI", 7), bg="#0D1117", fg=C["muted"], justify=tk.LEFT
            ).pack(anchor="w", pady=(2, 0))

    def _on_remove_single_stop(self, index: int) -> None:
        """Remove a single delivery stop by index."""
        if 0 <= index < len(self.customer_deliveries):
            removed = self.customer_deliveries.pop(index)
            self._refresh_stops_panel()
            self._render_all_map_markers()
            self._clear_route_polyline()
            self._check_optimization_ready()
            self._set_status(f"Removed stop: {removed['name']}.")

    def _on_edit_single_stop(self, index: int) -> None:
        """Edit priority or weight of a single stop."""
        if not (0 <= index < len(self.customer_deliveries)):
            return
        stop = self.customer_deliveries[index]

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Edit Stop #{index+1} · {stop['name']}")
        dlg.geometry("340x220")
        dlg.configure(bg=C["sidebar"])
        dlg.grab_set()

        _lbl(dlg, f"Edit Stop #{index+1}: {stop['name'][:24]}", size=9, bold=True, bg=C["sidebar"], fg=C["accent"]).pack(pady=8)

        r1 = tk.Frame(dlg, bg=C["sidebar"])
        r1.pack(fill=tk.X, padx=16, pady=4)
        _lbl(r1, "Priority:", bg=C["sidebar"]).pack(side=tk.LEFT)
        p_var = tk.StringVar(value=stop.get("priority", "Normal"))
        ttk.Combobox(r1, textvariable=p_var, values=["Normal", "Urgent"], state="readonly", width=10).pack(side=tk.RIGHT)

        r2 = tk.Frame(dlg, bg=C["sidebar"])
        r2.pack(fill=tk.X, padx=16, pady=4)
        _lbl(r2, "Payload (kg):", bg=C["sidebar"]).pack(side=tk.LEFT)
        w_var = tk.DoubleVar(value=float(stop.get("weight_kg", 5.0)))
        ttk.Spinbox(r2, from_=0.5, to=50.0, increment=0.5, textvariable=w_var, width=8).pack(side=tk.RIGHT)

        def save():
            stop["priority"] = p_var.get()
            stop["weight_kg"] = w_var.get()
            dlg.destroy()
            self._refresh_stops_panel()
            self._render_all_map_markers()
            self._set_status(f"Updated stop #{index+1}.")

        _btn(dlg, "Save Changes", save, bg=C["primary"], fg="#fff", font_size=9, pady=5).pack(pady=14)

    def _check_optimization_ready(self) -> None:
        """Enable Optimize button ONLY when depot AND at least 1 delivery stop exist."""
        has_depot = self.depot_stop is not None
        has_deliveries = len(self.customer_deliveries) >= 1

        if has_depot and has_deliveries:
            self.btn_optimize.config(state=tk.NORMAL)
            self._set_status(f"Ready: Depot + {len(self.customer_deliveries)} deliveries. Click 'OPTIMIZE ROUTE'.")
        else:
            self.btn_optimize.config(state=tk.DISABLED)
            if not has_depot:
                self._set_status("Please select a starting depot to proceed.")
            else:
                self._set_status("Please add at least 1 customer delivery stop to optimize.")

    # ──────────────────────────────────────────────────────────────────────────
    #  Map Clicking Handlers
    # ──────────────────────────────────────────────────────────────────────────
    def _on_map_set_depot(self, coords: Tuple[float, float]) -> None:
        lat, lon = coords
        if not self.geocoder:
            return
        snapped = self.geocoder.snap_location(f"Depot ({lat:.4f}, {lon:.4f})", f"GPS: {lat:.4f}, {lon:.4f}", lat, lon)
        snapped["type"] = "depot"
        snapped["priority"] = "Normal"
        snapped["weight_kg"] = 0.0
        self.depot_stop = snapped

        self.lbl_depot_name.config(text=f"🚩 {snapped['name']}", fg=C["success"])
        self.lbl_depot_addr.config(text=snapped["address"])
        self.depot_actions_row.pack(fill=tk.X, pady=(2, 0))
        self._render_all_map_markers()
        self._check_optimization_ready()
        self._set_status(f"✓ Depot set via map at ({lat:.4f}, {lon:.4f}).")

    def _on_map_add_delivery(self, coords: Tuple[float, float]) -> None:
        lat, lon = coords
        if not self.geocoder:
            return
        idx = len(self.customer_deliveries) + 1
        snapped = self.geocoder.snap_location(f"Customer #{idx}", f"Point ({lat:.4f}, {lon:.4f})", lat, lon)
        self.customer_deliveries.append(snapped)
        self._refresh_stops_panel()
        self._render_all_map_markers()
        self._check_optimization_ready()
        self._set_status(f"✓ Added delivery stop #{idx} via map click.")

    # ──────────────────────────────────────────────────────────────────────────
    #  Route Optimization Execution
    # ──────────────────────────────────────────────────────────────────────────
    def _on_optimize_route_clicked(self) -> None:
        """Run optimization algorithm across depot and customer stops."""
        if not self.depot_stop or not self.customer_deliveries:
            messagebox.showwarning("Incomplete", "Both a depot and at least one delivery stop are required.")
            return

        stops = [dict(self.depot_stop)] + [dict(s) for s in self.customer_deliveries]
        self.current_stops = stops

        # Capacity check
        total_payload = sum(float(s.get("weight_kg", 0.0)) for s in self.customer_deliveries)
        cap = self.capacity_var.get()
        if total_payload > cap:
            messagebox.showerror(
                "Capacity Exceeded",
                f"Total package weight ({total_payload:.1f} kg) exceeds vehicle payload capacity ({cap:.1f} kg)."
            )
            return

        solver_label = self.solver_var.get()
        if "Genetic" in solver_label:
            solver_code = "GA"
        elif "Hill" in solver_label:
            solver_code = "HC"
        elif "Nearest" in solver_label:
            solver_code = "NN"
        else:
            solver_code = "SA"

        solver_name, solver_cls = SOLVER_MAP[solver_code]
        self.active_solver_name = solver_name
        round_trip = self.round_trip_var.get()

        self._set_status(f"Optimizing route using {solver_name}...")
        self.btn_optimize.config(state=tk.DISABLED)

        def _worker():
            try:
                # 1. Distance matrix via A*
                dist_matrix, detailed_paths, nodes_exp = self.astar_planner.build_distance_matrix(
                    stops, search_method="astar"
                )
                self.distance_matrix = dist_matrix
                self.detailed_paths = detailed_paths
                self.total_nodes_expanded = nodes_exp

                # 2. Problem formulation
                prob = RouteProblem(
                    stops, dist_matrix, depot=0, round_trip=round_trip,
                    vehicle_capacity_kg=cap, vehicle_speed_kmh=30.0, service_time_mins=5.0
                )
                self.problem = prob

                # 3. NN Baseline
                nn_solver = NearestNeighborSolver(prob, seed=42)
                _, nn_cost, _, _ = nn_solver.solve()
                self.baseline_cost_km = nn_cost

                # 4. Metaheuristic solve
                solver = solver_cls(prob, seed=42)
                tour, cost, hist, runtime = solver.solve()
                self.optimized_tour = tour
                self.optimized_cost_km = cost
                self.solver_runtime = runtime

                saved_km = max(0.0, nn_cost - cost)
                saved_pct = (saved_km / nn_cost * 100.0) if nn_cost > 0 else 0.0
                self.saved_distance_km = saved_km
                self.saved_pct = saved_pct

                # 5. Extract continuous road coordinates
                coords = self.astar_planner.get_detailed_route_coordinates(tour, detailed_paths, stops=stops)
                self.route_coords = coords

                def _done():
                    self.btn_optimize.config(state=tk.NORMAL)
                    self._show_results(prob.estimate_journey_time(tour))
                    self._draw_route_polyline()
                    self._render_all_map_markers()
                    self._set_status(f"✓ Route optimized: {cost:.2f} km in {runtime:.4f}s ({saved_pct:.1f}% saved).")

                self.ui_call(_done)

            except Exception as e:
                logger.exception("Optimize error:")
                def _err(err=e):
                    self.btn_optimize.config(state=tk.NORMAL)
                    self._set_status(f"Error: {err}")
                    messagebox.showerror("Optimization Error", str(err))
                self.ui_call(_err)

        threading.Thread(target=_worker, daemon=True).start()

    def _show_results(self, est_mins: float) -> None:
        """Display the route summary metrics card in left panel."""
        self.res_val_dist.config(text=f"{self.optimized_cost_km:.2f} km")
        hrs = int(est_mins // 60)
        mins = int(est_mins % 60)
        t_str = f"{hrs}h {mins}m" if hrs > 0 else f"{mins} min"
        self.res_val_time.config(text=t_str)

        self.res_val_saved.config(text=f"-{self.saved_distance_km:.2f} km ({self.saved_pct:.1f}%)")
        self.res_val_runtime.config(text=f"{self.solver_runtime:.4f} s")

        self.results_card_wrapper.pack(fill=tk.X, pady=(6, 0))

    # ──────────────────────────────────────────────────────────────────────────
    #  Map Polyline & Markers Rendering
    # ──────────────────────────────────────────────────────────────────────────
    def _render_all_map_markers(self) -> None:
        """Clear and re-render map markers for depot and stops."""
        for m in self._stop_markers:
            try:
                m.delete()
            except Exception:
                pass
        self._stop_markers.clear()

        # Render Depot
        if self.depot_stop:
            dm = self.map_widget.set_marker(
                self.depot_stop["latitude"], self.depot_stop["longitude"],
                text=f"🚩 DEPOT: {self.depot_stop['name'][:18]}",
                marker_color_circle=C["success"], marker_color_outside="#047857"
            )
            self._stop_markers.append(dm)

        # Render Deliveries
        for idx, s in enumerate(self.customer_deliveries, 1):
            is_urgent = str(s.get("priority")).lower() == "urgent"
            c_circ = C["danger"] if is_urgent else C["primary"]
            c_out = "#991B1B" if is_urgent else C["primary_dark"]
            badge = f"#{idx} {s['name'][:18]}"
            if is_urgent:
                badge = f"⚡ {badge}"

            m = self.map_widget.set_marker(
                s["latitude"], s["longitude"], text=badge,
                marker_color_circle=c_circ, marker_color_outside=c_out
            )
            self._stop_markers.append(m)

    def _draw_route_polyline(self) -> None:
        """Draw road polyline curve."""
        self._clear_route_polyline()
        if len(self.route_coords) >= 2:
            self._route_path = self.map_widget.set_path(
                self.route_coords, color=C["danger"], width=5
            )

    def _clear_route_polyline(self) -> None:
        if self._route_path:
            try:
                self._route_path.delete()
            except Exception:
                pass
            self._route_path = None

    # ──────────────────────────────────────────────────────────────────────────
    #  Delivery Simulation
    # ──────────────────────────────────────────────────────────────────────────
    def _on_start_simulation_clicked(self) -> None:
        """Launch vehicle simulation traversing road coordinates."""
        if not self.route_coords:
            messagebox.showinfo("Simulation", "Please optimize a route first.")
            return

        self._simulating = True
        self._sim_paused = False
        self._sim_stop_requested = False
        self._delivery_statuses.clear()

        for s_idx in self.optimized_tour:
            if s_idx != 0:
                self._delivery_statuses[s_idx] = "Pending"

        self.sim_dock.place(relx=0.5, rely=0.93, anchor="center")
        self.btn_sim_toggle.config(text="⏸ Simulation In Progress...", state=tk.DISABLED)
        self._set_status("Delivery simulation started: van in transit along real roads...")

        threading.Thread(target=self._sim_worker_thread, daemon=True).start()

    def _sim_worker_thread(self) -> None:
        coords = self.route_coords
        total_pts = len(coords)
        step_skip = max(1, total_pts // 160)

        for i in range(0, total_pts, step_skip):
            if self._sim_stop_requested:
                break
            while self._sim_paused:
                if self._sim_stop_requested:
                    break
                time.sleep(0.1)

            lat, lon = coords[i]

            def _move(lt=lat, ln=lon):
                if self._sim_van_marker:
                    try:
                        self._sim_van_marker.delete()
                    except Exception:
                        pass
                self._sim_van_marker = self.map_widget.set_marker(
                    lt, ln, text="🚚 Van",
                    marker_color_circle=C["warning"], marker_color_outside="#B45309"
                )

            self.ui_call(_move)

            # Check arrival at delivery stops
            for stop_idx in self.optimized_tour:
                if stop_idx == 0:
                    continue
                s_data = self.current_stops[stop_idx]
                dist = haversine_distance(lat, lon, s_data["latitude"], s_data["longitude"])
                if dist < 50.0 and self._delivery_statuses.get(stop_idx) == "Pending":
                    def _reach(name=s_data["name"]):
                        self.lbl_sim_stop_name.config(text=f"Arrived: {name[:24]}", fg=C["warning"])
                    self.ui_call(_reach)
                    time.sleep(0.5)

            time.sleep(0.04)

        def _finish():
            self._simulating = False
            self.sim_dock.place_forget()
            self.btn_sim_toggle.config(text="▶ Replay Simulation", state=tk.NORMAL)
            self._set_status("Delivery simulation completed.")

        self.ui_call(_finish)

    def _on_sim_mark_done(self) -> None:
        for si, st in self._delivery_statuses.items():
            if st == "Pending":
                self._delivery_statuses[si] = "Delivered"
                self._set_status(f"✓ Marked {self.current_stops[si]['name']} as Completed.")
                return

    def _on_sim_skip_stop(self) -> None:
        for si, st in self._delivery_statuses.items():
            if st == "Pending":
                self._delivery_statuses[si] = "Skipped"
                self._set_status(f"Skipped {self.current_stops[si]['name']}.")
                return

    def _on_sim_pause(self) -> None:
        self._sim_paused = not self._sim_paused
        self._set_status("Simulation paused." if self._sim_paused else "Simulation resumed.")

    def _on_sim_stop(self) -> None:
        self._sim_stop_requested = True
        self._simulating = False
        self.sim_dock.place_forget()
        self.btn_sim_toggle.config(text="▶ Start Delivery Simulation", state=tk.NORMAL)
        if self._sim_van_marker:
            try:
                self._sim_van_marker.delete()
            except Exception:
                pass
            self._sim_van_marker = None
        self._set_status("Simulation stopped.")

    # ──────────────────────────────────────────────────────────────────────────
    #  SQLite Database Persistence & History Modal
    # ──────────────────────────────────────────────────────────────────────────
    def _on_save_route_to_sqlite(self) -> None:
        """Save active route into SQLite."""
        if not self.problem or not self.optimized_tour:
            return

        route_meta = {
            "route_name": f"{self.depot_stop['name'][:16]} Route",
            "depot_name": self.depot_stop["name"],
            "depot_lat": self.depot_stop["latitude"],
            "depot_lon": self.depot_stop["longitude"],
            "num_stops": len(self.current_stops),
            "total_distance_km": self.optimized_cost_km,
            "est_time_mins": self.problem.estimate_journey_time(self.optimized_tour),
            "baseline_distance_km": self.baseline_cost_km,
            "saved_distance_km": self.saved_distance_km,
            "saved_pct": self.saved_pct,
            "algorithm": self.active_solver_name,
            "search_method": "A*",
            "round_trip": self.round_trip_var.get(),
            "vehicle_capacity_kg": self.capacity_var.get(),
            "total_weight_kg": sum(float(s.get("weight_kg", 0)) for s in self.customer_deliveries),
            "status": "Planned"
        }
        stops_in_order = [self.current_stops[si] for si in self.optimized_tour]
        r_id = self.db.save_route(route_meta, stops_in_order)
        messagebox.showinfo("Saved", f"Route successfully saved to SQLite database (Trip #{r_id})!")
        self._set_status(f"✓ Saved Route #{r_id} to SQLite database.")

    def _open_history_modal(self) -> None:
        """Modal dialog for browsing and restoring historical routes from SQLite."""
        modal = tk.Toplevel(self.root)
        modal.title("SQLite Route History · FAST-NUCES")
        modal.geometry("960x580")
        modal.configure(bg=C["sidebar"])
        modal.grab_set()

        _lbl(modal, "📜 Saved Delivery Trips (SQLite Database)", size=11, bold=True, bg=C["sidebar"], fg=C["accent"]).pack(padx=14, pady=(12, 6), anchor="w")

        # Table
        cols = ("id", "date", "depot", "stops", "dist", "saved", "algo", "status")
        tree = ttk.Treeview(modal, columns=cols, show="headings", height=8)
        tree.heading("id", text="ID")
        tree.heading("date", text="Date/Time")
        tree.heading("depot", text="Starting Depot")
        tree.heading("stops", text="Stops")
        tree.heading("dist", text="Distance (km)")
        tree.heading("saved", text="Saved %")
        tree.heading("algo", text="Algorithm")
        tree.heading("status", text="Status")

        tree.column("id", width=30, anchor="center")
        tree.column("date", width=110, anchor="center")
        tree.column("depot", width=120, anchor="w")
        tree.column("stops", width=40, anchor="center")
        tree.column("dist", width=60, anchor="center")
        tree.column("saved", width=55, anchor="center")
        tree.column("algo", width=85, anchor="w")
        tree.column("status", width=65, anchor="center")
        tree.pack(fill=tk.BOTH, expand=True, padx=14, pady=6)

        routes = self.db.get_all_routes()
        for r in routes:
            tree.insert(
                "", tk.END,
                values=(r["id"], r["created_at"][:16], r["depot_name"][:16], r["num_stops"]-1, f"{r['total_distance_km']:.2f}", f"{r['saved_pct']:.1f}%", r["algorithm"][:14], r["status"])
            )

        # Bottom buttons
        b_row = tk.Frame(modal, bg=C["sidebar"], padx=14, pady=10)
        b_row.pack(fill=tk.X)

        def restore():
            sel = tree.selection()
            if not sel:
                return
            item = tree.item(sel[0])
            r_id = int(item["values"][0])
            meta, stops = self.db.get_route_details(r_id)
            if not stops or not self.geocoder:
                return

            # Set depot
            depot_raw = stops[0]
            self.depot_stop = self.geocoder.snap_location(
                depot_raw["name"], depot_raw["address"], depot_raw["latitude"], depot_raw["longitude"]
            )
            self.depot_stop["type"] = "depot"
            self.lbl_depot_name.config(text=f"🚩 {self.depot_stop['name']}", fg=C["success"])
            self.lbl_depot_addr.config(text=self.depot_stop["address"])
            self.depot_actions_row.pack(fill=tk.X, pady=(2, 0))

            # Set deliveries
            self.customer_deliveries.clear()
            for s in stops[1:]:
                if s["name"] == depot_raw["name"]:
                    continue
                sn = self.geocoder.snap_location(s["name"], s["address"], s["latitude"], s["longitude"])
                sn["priority"] = s.get("priority", "Normal")
                sn["weight_kg"] = s.get("weight_kg", 5.0)
                self.customer_deliveries.append(sn)

            self._refresh_stops_panel()
            self._render_all_map_markers()
            self._clear_route_polyline()
            self._check_optimization_ready()
            modal.destroy()
            self._set_status(f"✓ Restored Route #{r_id} ({len(self.customer_deliveries)} stops).")

        _btn(b_row, "📥 Load Selected Route to Map", restore, bg=C["primary"], fg="#fff", font_size=9, pady=5).pack(side=tk.LEFT)
        _btn(b_row, "Close", modal.destroy, bg="#374151", fg=C["text"], font_size=9, pady=5).pack(side=tk.RIGHT)

    def ui_call(self, fn, *args, **kwargs) -> None:
        """Enqueue a callback to execute safely on the main Tkinter UI thread."""
        self._ui_queue.put((fn, args, kwargs))

    def _poll_ui_queue(self) -> None:
        """Poll queued UI functions dispatched from background threads."""
        while not self._ui_queue.empty():
            try:
                fn, args, kwargs = self._ui_queue.get_nowait()
                fn(*args, **kwargs)
            except Exception as e:
                logger.debug("UI queue task execution error: %s", e)
        try:
            self.root.after(30, self._poll_ui_queue)
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────────
    #  General Helpers
    # ──────────────────────────────────────────────────────────────────────────
    def _init_road_graph(self) -> None:
        """Background loader for Karachi graph."""
        def _worker():
            try:
                loader = GraphLoader("Karachi")
                G = loader.load_graph(force_download=False)
                self.graph_loader = loader
                self.astar_planner = AStarPlanner(G)
                self.geocoder = LocationGeocoder(loader)
                self.ui_call(lambda: self._set_status("✓ Karachi road network loaded. Search above to begin."))
            except Exception as e:
                logger.exception("Graph load failed:")
                self.ui_call(lambda err=e: self._set_status(f"Notice: {err}"))
        threading.Thread(target=_worker, daemon=True).start()

    def _on_tile_server_changed(self, event=None) -> None:
        val = self.tile_var.get()
        url = TILE_SERVERS.get(val)
        if url:
            self.map_widget.set_tile_server(url)

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _toggle_fullscreen(self, event=None) -> None:
        self._is_fullscreen = not self._is_fullscreen
        self.root.attributes("-fullscreen", self._is_fullscreen)

    def _exit_fullscreen(self, event=None) -> None:
        if self._is_fullscreen:
            self._is_fullscreen = False
            self.root.attributes("-fullscreen", False)
