# Delivery Route Optimizer on a Real City Map

An artificial intelligence software application for urban logistics and courier delivery planning across the real-world road network of Karachi, Pakistan. The system integrates a custom **A\* search algorithm** using the admissible spherical **Haversine heuristic** to calculate exact road distances on OpenStreetMap street topology, alongside baseline graph search methods (**UCS**, **BFS**, **DFS**), four combinatorial optimization metaheuristics (**Nearest Neighbor baseline**, **Hill Climbing with 2-opt**, **Simulated Annealing**, and a **Genetic Algorithm**), **CSP-style delivery constraints** (vehicle payload capacity, priority delivery ordering, time windows), **K-Means spatial clustering**, and an intelligent **delivery simulation engine** with full **SQLite route persistence**.

An executive dark-themed desktop GUI built with **Tkinter** and **`tkintermapview`** allows delivery managers to interactively search addresses or click on the map to set depots and customer deliveries, inspect visiting itineraries with realistic journey time estimates, simulate route progress with interactive stop completion checkoffs, and inspect historic trips in SQLite.

---

## Authors & Contribution

| Name | Roll Number | Section | Contribution & Modules Owned |
| :--- | :---: | :---: | :--- |
| **Bisma Shahid** | 24K-3012 | BSE-5A | **100% (Solo Leader)**: Architected OOP design (`RouteProblem`, `AStarPlanner`, `MetaheuristicSolver`, `LocationGeocoder`, `DatabaseManager`), implemented custom `heapq` A\* search and Haversine heuristic, implemented UCS/BFS/DFS search methods, built all 4 metaheuristic solvers, designed Tkinter + `tkintermapview` GUI with 3-tab architecture (Route Planner, Results, History), integrated K-Means spatial clustering, implemented delivery simulation with stop checkoffs, built SQLite database storage, designed benchmark runner, and authored documentation. |

---

## Key Application Sections

The application is structured into three dedicated, highly focused sections:

### 1. 📋 Route Planner (Main Screen)
- **Custom Depot Selection**: Search for any address or business landmark, or right-click anywhere on the interactive map to set the depot.
- **Dynamic Customer Deliveries**: Search for customer addresses or right-click on the map.
  - Set customer name and delivery address.
  - Set delivery priority: **Normal** or **Urgent** (urgent deliveries are prioritized early in the sequence).
  - Specify package payload weight in kilograms.
  - Specify delivery time windows (e.g. `09:00 - 11:00` or `60 min`).
- **Stop Management**: Edit customer details or remove individual stops dynamically.
- **Tour Format Choice**: Select whether the vehicle returns to depot (**Round Trip**) or finishes at the last customer stop (**Open Tour**).
- **Delivery Constraints & Settings**:
  - Configurable maximum vehicle capacity (kg) — prevents infeasible overload routes.
  - Configurable average vehicle speed (km/h) for realistic journey time estimation.
  - Stop service/dwell time (minutes per stop).
  - Road search algorithm selection: **A\*** (Recommended, optimal), **UCS** (Dijkstra), **BFS** (Hop-minimal), or **DFS** (Depth-bounded).
  - Optimization algorithm selection: **Simulated Annealing**, **Genetic Algorithm**, **Hill Climbing (2-opt)**, or **Nearest Neighbor**.
  - **⚡ Spatial Clustering (K-Means)**: Group delivery locations into geographic zones with distinct map marker colors.
  - **Quick Sample Presets**: Instantly load 3, 5, 10, or 15 realistic Karachi delivery stops for testing and presentation demonstrations.

### 2. 🏁 Route Results
- **Road Network Route Polyline**: Continuous red route hugging every street curve, turn, and junction.
- **Numbered Visited Sequence**: Delivery markers numbered matching their optimal sequence (#1, #2, ...).
- **Telemetry Scorecards**:
  - Total road distance (km).
  - Estimated journey time (calculated from road distance, vehicle speed, and stop service times; clearly labeled as realistic estimate).
  - Original vs. optimized distance saved (in km and %).
  - Solver execution time (seconds) and pathfinder nodes expanded.
  - CSP constraints status (capacity adherence, urgent delivery priority, time windows).
- **Step-by-Step Delivery Itinerary**: Table displaying stop order, customer name, leg distance, cumulative distance, estimated arrival time (ETA), and status.
- **Intelligent Delivery Simulation**:
  - Live animated delivery van (🚚) traveling along real road curves.
  - Simulation controls: Start, Pause, Resume, Reset.
  - Active customer highlight card showing package weight, priority, and time window.
  - Interactive delivery actions: courier can click **"✓ Mark Completed"** or **"⏭ Skip Delivery"** at each stop, dynamically updating itinerary status.
  - **Save to SQLite**: Persists the planned route, stops, and delivery statuses directly into the database.

### 3. 📜 Route History
- **SQLite Persistence**: Stores customer delivery records, depots, planned routes, sequences, distances, estimated times, and statuses in `data/delivery_history.db`.
- **Route Browser (Treeview)**: Table listing past routes with timestamp, depot, stops count, distance, estimated time, savings %, algorithm, and completion status.
- **Route Inspection**: Click any historical trip to view its delivery stops and delivery completion statuses.
- **Load Route to Planner & Map**: One-click restore of any historical trip back into the active Route Planner and map display.
- **Performance Summary**: Aggregates average route distance, savings %, and compares performance across algorithms.

---

## AI & Search Concepts Implemented

1. **A\* Shortest Path Search (Lab 05)**:
   - Priority queue implemented with Python's `heapq` (strictly no `networkx.astar_path`).
   - Heuristic: Spherical great-circle **Haversine distance** ($h(u, goal) \le h^*(u, goal)$).
   - Proven strictly admissible and consistent (monotonic), reducing node expansions by **60.7%** compared to UCS while guaranteeing optimal road paths.
2. **Uninformed Search Baselines (Lab 04)**:
   - **Uniform Cost Search (UCS / Dijkstra)**: Explores lowest cumulative road cost $g(u)$.
   - **Breadth-First Search (BFS)**: Explores level-by-level for hop-minimal road paths.
   - **Depth-First Search (DFS)**: Stack-based exploration with depth bounding.
3. **Combinatorial Optimization Metaheuristics (Lab 06 & 07)**:
   - **Nearest Neighbor**: Greedy $O(N^2)$ baseline.
   - **Hill Climbing (2-opt)**: Local search neighborhood descent inverting sub-tours.
   - **Simulated Annealing**: Stochastic temperature cooling with Boltzmann acceptance probability $P(\text{accept}) = \exp(-\Delta / T)$ to escape local optima.
   - **Genetic Algorithm**: Evolutionary population search with Ordered Crossover (OX), 2-opt inversion mutation, tournament selection, and elitism.
4. **Constraint Satisfaction (CSP)**:
   - Vehicle payload capacity constraint (hard check rejecting infeasible overloading).
   - Priority delivery constraint (penalizes scheduling urgent orders late in tour).
   - Time window constraint (evaluates arrival time against promised delivery deadlines).
5. **Machine Learning / Spatial Clustering (K-Means)**:
   - Unsupervised K-Means clustering partitions delivery coordinates into geographic clusters/zones for organized regional delivery and cluster-first heuristics.

---

## Repository Structure

```
Delivery-Route-Optimizer/
├── run.py                         <- ROOT-LEVEL LAUNCHER (python run.py)
├── README.md                      <- Comprehensive project documentation
├── requirements.txt               <- Pinned project dependencies
├── .gitignore                     <- Caches, venvs, and temporary files exclusions
├── experiment_runner.py           <- Standalone 10-instance benchmark script
├── docs/                          <- Project Proposal and Final Report (MD + PDF)
│   ├── PROJECT_PROPOSAL.md
│   ├── PROJECT_PROPOSAL.pdf
│   ├── PROJECT_REPORT.md
│   └── PROJECT_REPORT.pdf
├── src/                           <- Application source code
│   ├── __init__.py
│   ├── main.py                    <- Entry point
│   ├── core/
│   │   ├── __init__.py
│   │   ├── astar.py               <- Custom heapq A*, UCS, BFS, DFS & Haversine
│   │   ├── problem.py             <- RouteProblem formulation, CSP constraints & fitness
│   │   ├── solvers.py             <- MetaheuristicSolver hierarchy (NN, HC, SA, GA)
│   │   └── clustering.py          <- K-Means spatial clustering & zone ordering
│   ├── data/
│   │   ├── __init__.py
│   │   ├── graph_loader.py        <- OSMnx graph loader & GraphML cache
│   │   ├── stop_generator.py      <- Stop generation & CSV parsing
│   │   ├── geocoder.py            <- Address search & road network snapping
│   │   └── database.py            <- SQLite database persistence manager
│   └── gui/
│       ├── __init__.py
│       └── app.py                 <- 3-Section dark-themed Tkinter + TkinterMapView GUI
├── data/
│   ├── delivery_history.db        <- SQLite database for route history
│   ├── raw/                       <- karachi.graphml, lahore.graphml, stops_*.csv
│   └── processed/
├── tests/
│   ├── test_all.py                <- Core unit test suite
│   ├── test_delivery_suite.py     <- Integration test suite (3, 5, 10, 15 stops, SQLite, geocoding)
│   └── quick_test.py              <- Backend validation script
└── outputs/
    ├── figures/                   <- 4 Matplotlib evaluation figures
    └── results/                   <- results.csv, summary_metrics.csv
```

---

## Setup and Installation

### 1. Prerequisites
- Python 3.10, 3.11, 3.12, or 3.13.
- Windows, macOS, or Linux.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## Exact Run Commands

### 1. Launch the Desktop Application
From the project root directory, run:
```powershell
python run.py
```
*(Alternatively: `python src/main.py`)*

### 2. Run the Automated Test Suites
```powershell
python tests/test_all.py           # 5 core unit tests
python tests/test_delivery_suite.py # 7 integration tests
python tests/quick_test.py          # 20 backend checks
python tests/test_gui_workflow.py   # Full GUI workflow test (empty start, search, optimize, SQLite)
```

### 3. Run the Benchmark Experiment Suite
```powershell
python experiment_runner.py
```

---

## Data Source & Attribution

- **Road Data**: OpenStreetMap contributors via [OSMnx](https://osmnx.readthedocs.io/), licensed under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/).
- **Map Tiles**: Google Maps Standard & CartoDB basemaps.
- **Attribution**: Map data © OpenStreetMap contributors, ODbL.

---

## Limitations

- **Traffic Dynamics**: Journey times are realistic estimates based on road distance, configurable vehicle speed (e.g. 30 km/h), and stop service times. Live GPS traffic congestion feeds are not claimed.
- **Road Boundary**: The Karachi road network covers Saddar, Kharadar, Clifton, DHA, Gulshan, PECHS, Burns Road, and surrounding areas. Locations far outside Pakistan (e.g. Lahore Fort) will raise an `UnreachableLocationError` and are rejected gracefully.
- **Tile Server**: Application defaults to **Google Maps Standard** tiles to avoid OpenStreetMap 403 "Access Blocked" errors that occur when tile requests don't comply with OSM usage policy.
- **Python 3.13 Threading**: The app uses a thread-safe `queue.Queue`-based UI dispatcher (`_poll_ui_queue`) to safely dispatch background computation results to the Tkinter main thread, fully compatible with Python 3.13+.

