# Delivery Route Optimizer

A commercial-grade artificial intelligence software application for urban logistics and courier fleet route planning across the real-world road network of Karachi, Pakistan.

The platform integrates:
- **Exact Road Network Pathfinding**: Custom `heapq` **A\* search** using an admissible spherical **Haversine heuristic** ($h \le h^*$), with comparative baselines (**UCS / Dijkstra**, **BFS**, and **DFS**).
- **Combinatorial Metaheuristics**: Four independent optimization algorithms (**Nearest Neighbor baseline**, **Hill Climbing with 2-opt descent**, **Simulated Annealing with Boltzmann cooling**, and a **Genetic Algorithm with Ordered Crossover (OX) and Elitism**).
- **Constraint Satisfaction (CSP)**: Genuine constraint satisfaction solver with Minimum Remaining Values (MRV) and Forward Checking (FC), enforcing hard vehicle capacity limits and delivery time windows, alongside soft urgent-order prioritization.
- **Spatial Clustering (K-Means)**: Automated partitioning of customer stops into geographic delivery zones (Zone A, Zone B, etc.) with cluster center computation and inertia/elbow analysis.
- **Supervised Machine Learning**: Regression models (Random Forest and Linear Regression) predicting real-world journey times based on route distance, stop counts, vehicle speed, payload, and hour-of-day traffic dynamics.
- **Intelligent Delivery Agent**: Rational goal-based courier agent operating within the vehicle simulation, perceiving location milestones, executing package handovers, adjusting cargo weight, and returning to the depot.
- **Executive 6-Screen GUI**: Desktop interface with a slim collapsible sidebar, working location autocomplete, layer styles, live simulation HUD, and SQLite persistence.

---

## Architecture & Screen Structure

The application features six dedicated screens:

### 1. 📊 Executive Dashboard
- **Fleet KPI Scorecards**: Total routes planned, completed deliveries, pending deliveries, and cumulative fleet distance logged in SQLite.
- **Quick Dispatch Actions**: One-click jump to Plan a Delivery, with preset demo loaders (3 Stops, 6 Stops, 10 Stops).
- **Recent Trips Table**: Real-time view of recent dispatches, delivery counts, road distance, savings %, and statuses.
- **AI Engine Health Monitor**: Live readiness status for road graphs, database connections, and solvers.

### 2. 🗺️ Plan a Delivery
- **Custom Starting Depot Selection**: Search for any Karachi address, business, or landmark, or right-click directly on the interactive map.
- **Dynamic Customer Deliveries**: Add customer name, street address, individual package weight (kg), delivery priority (**Normal** vs **⚡ Urgent**), and time window constraints (e.g. `45 min` or `09:00 - 11:00`).
- **Vehicle Capacity & CSP Gauge**: Dynamic visual payload bar tracking loaded vs remaining capacity in kilograms. Automatically blocks invalid overload routes.
- **Delivery Zones (K-Means Clustering)**: Select cluster count $k \in [2, 5]$ and group stops into colored spatial zones with zone badges on the map.
- **Working Location Autocomplete**: Real-time suggestion dropdown as you type (e.g. `FAST`, `DHA`, `Clifton`, `Saddar`, `Burns Road`, `Gulshan`) without requiring Enter.
- **Interactive Road Map**: Embedded GIS map supporting Google Maps Standard, CartoDB Voyager, CartoDB Positron, and CartoDB Dark Matter.
- **Prominent Optimize Route Button**: Automatically triggers A* distance matrix computation, CSP constraint validation, and metaheuristic optimization in a background thread.

### 3. 🏁 Route Results & Simulation
- **Continuous Road Polyline**: Real street-following geometry hugging curves and intersections (not straight lines).
- **Numbered Stop Markers**: Visual pins numbered matching their exact optimal sequence (#1, #2, ...).
- **Telemetry KPI Summary**: Total road distance (km), estimated journey time, baseline distance, saved distance (km and %), solver runtime, and nodes expanded.
- **Step-by-Step Itinerary Table**: Sequence order, customer name, address, package weight, priority, leg distance, and ETA.
- **Intelligent Goal-Based Agent Simulation**:
  - Live animated delivery vehicle traversing real road coordinates.
  - Agent Telemetry HUD: Agent Action (`NAVIGATE_ROAD`, `ARRIVE_AT_STOP`, `DELIVER_PACKAGE`), Rational Decision Reason, Current Goal, and Remaining Cargo (kg).
  - Courier Actions: Click **"✓ Mark Completed"** to unload package weight and complete delivery, or **"⏭ Skip Stop"** to retain package.
  - Persistence: **"💾 Save Route to SQLite History"** button.

### 4. 📜 Delivery History
- **SQLite Database Storage**: Complete route metadata and individual customer stop logs stored in `data/delivery_history.db`.
- **Searchable Routes Table**: Filter and sort past trips by date, depot, stop count, distance, savings %, and algorithm.
- **Stop Inspection Drawer**: Inspect package weights, priorities, and delivery completion statuses.
- **Load to Planner**: One-click restore of any historical trip back into the active Plan a Delivery map.

### 5. 📈 Insights & Analytics
- **Algorithm Benchmark Comparison**: Grouped Matplotlib charts comparing Tour Distance (km) and Runtime (seconds) across Nearest Neighbor, Hill Climbing, Simulated Annealing, and Genetic Algorithm.
- **Convergence Curves**: Iteration/generation vs distance curves for Simulated Annealing cooling and Genetic Algorithm evolution.
- **K-Means Spatial Zones & Elbow Curve**: 2D coordinate scatter colored by geographic zone with centroids, plus the $k$ vs Inertia elbow plot.
- **Supervised Learning Travel-Time Analysis**: Actual vs Predicted regression scatter plot with $R^2$ score and feature importance rankings.

### 6. ⚙️ Fleet Settings
- Vehicle maximum payload capacity (kg).
- Average city driving speed (km/h) and service dwell time per stop (mins).
- Route format: Round Trip (Return to depot) vs Open Tour (Finish at last stop).
- Map style preferences and default optimization solver selection.

---

## AI & Search Concepts Implemented

| Lab / AI Topic | Technique | Implementation Details |
| :--- | :--- | :--- |
| **Search (Informed)** | **A\* Search** | Custom `heapq` priority queue with spherical **Haversine heuristic** ($h \le h^*$, strictly admissible). Counts nodes expanded. |
| **Search (Uninformed)** | **UCS, BFS, DFS** | Explores cumulative road weights (UCS / Dijkstra), hop-minimal levels (BFS), and depth-bounded stack exploration (DFS). |
| **Metaheuristics** | **Nearest Neighbor** | Greedy baseline selecting closest unvisited stop in $O(N^2)$. |
| **Local Search** | **Hill Climbing** | Evaluates 2-opt sub-tour reversals with first-improvement descent to local optima. |
| **Stochastic Search**| **Simulated Annealing** | Boltzmann acceptance probability $P(\text{accept}) = \exp(-\Delta / T)$ with geometric cooling schedule $T_{k+1} = \alpha T_k$. |
| **Evolutionary Search**| **Genetic Algorithm** | Population of 80 individuals, Ordered Crossover (OX), 2-opt inversion mutation, tournament selection, and elitism. |
| **CSP** | **Constraint Satisfaction** | AllDifferent, hard vehicle payload capacity, arrival time windows, and soft priority ordering solved via Backtracking Search with Forward Checking (FC) and MRV. |
| **Clustering** | **K-Means Clustering** | Unsupervised spatial clustering grouping delivery coordinates into regional zones, plus Elbow Method curve. |
| **Supervised Learning**| **Random Forest Regressor** | Predicts trip travel time based on distance, stop counts, speed, payload, and hour-of-day traffic patterns ($R^2 > 0.90$). |
| **Intelligent Agent** | **Goal-Based Agent** | Sensor percepts, rational decision mapping, dynamic cargo weight reduction, and goal completion state machine. |

---

## Setup & Execution

### 1. Prerequisites
- Python 3.10, 3.11, 3.12, or 3.13.
- Windows, macOS, or Linux.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Launch the Application
From the project root:
```powershell
python run.py
```
*(Press **F11** for full-screen presentation mode).*

### 4. Run Automated Test Suites
```powershell
# 16-point comprehensive verification suite:
python tests/test_complete_application.py

# Independent solver verification (records initial/final routes, evaluations, runtime):
python tests/test_solvers_independent.py

# Integration and regression test suites:
python tests/test_all.py
python tests/test_delivery_suite.py
python tests/quick_test.py
```

### 5. Run the Benchmark Experiment Suite
```powershell
python experiment_runner.py
```

---

## Data Attribution & Limitations

- **Road Data**: OpenStreetMap contributors via [OSMnx](https://osmnx.readthedocs.io/), licensed under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/).
- **Map Tiles**: Google Maps Standard & CartoDB basemaps.
- **Attribution**: Map data © OpenStreetMap contributors, ODbL.

---

## Limitations

- **Traffic Dynamics**: Journey times are realistic estimates based on road distance, configurable vehicle speed (e.g. 30 km/h), and stop service times. Live GPS traffic congestion feeds are not claimed.
- **Road Boundary**: The Karachi road network covers Saddar, Kharadar, Clifton, DHA, Gulshan, PECHS, Burns Road, and surrounding areas. Locations far outside Pakistan (e.g. Lahore Fort) will raise an `UnreachableLocationError` and are rejected gracefully.
- **Tile Server**: Application defaults to **Google Maps Standard** tiles to avoid OpenStreetMap 403 "Access Blocked" errors that occur when tile requests don't comply with OSM usage policy.
- **Python 3.13 Threading**: The app uses a thread-safe `queue.Queue`-based UI dispatcher (`_poll_ui_queue`) to safely dispatch background computation results to the Tkinter main thread, fully compatible with Python 3.13+.

## Authors & Contribution
- Bisma Shahid
- **Travel Time Estimates**: Realistic travel time estimates calculated from road network distances, configurable vehicle speed (e.g. 30 km/h), stop service dwell times, and supervised machine learning traffic multipliers. Live GPS telemetry is simulated through the Goal-Based Agent.
