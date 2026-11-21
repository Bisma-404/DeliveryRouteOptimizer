# Delivery Route Optimizer

A Flask web application for planning delivery routes across the local Karachi road network. The interface runs in a browser and uses the existing routing, clustering, simulation, and SQLite services.

The platform integrates:
- **Exact Road Network Pathfinding**: Custom `heapq` **A\* search** using an admissible spherical **Haversine heuristic** ($h \le h^*$), with comparative baselines (**UCS / Dijkstra**, **BFS**, and **DFS**).
- **Combinatorial Metaheuristics**: Four independent optimization algorithms (**Nearest Neighbor baseline**, **Hill Climbing with 2-opt descent**, **Simulated Annealing with Boltzmann cooling**, and a **Genetic Algorithm with Ordered Crossover (OX) and Elitism**).
- **Constraint Satisfaction (CSP)**: Genuine constraint satisfaction solver with Minimum Remaining Values (MRV) and Forward Checking (FC), enforcing hard vehicle capacity limits and delivery time windows, alongside soft urgent-order prioritization.
- **Spatial Clustering (K-Means)**: Automated partitioning of customer stops into geographic delivery zones (Zone A, Zone B, etc.) with cluster center computation and inertia/elbow analysis.
- **Supervised Machine Learning**: Regression models (Random Forest and Linear Regression) predicting real-world journey times based on route distance, stop counts, vehicle speed, payload, and hour-of-day traffic dynamics.
- **Intelligent Delivery Agent**: Rational goal-based courier agent operating within the vehicle simulation, perceiving location milestones, executing package handovers, adjusting cargo weight, and returning to the depot.
- **Six-screen web interface**: Overview, route planner, results, trip history, analytics, and fleet settings, with browser-based light and dark themes.

---

## Architecture & Screen Structure

The application features six browser screens:

### 1. Overview
- **Fleet metrics**: Saved routes, completed and pending deliveries, total distance, and average distance saved.
- **Quick dispatch**: Open the planner or load 3-, 6-, and 10-stop sample routes.
- **Recent Trips Table**: Real-time view of recent dispatches, delivery counts, road distance, savings %, and statuses.
- **Road graph status**: Shows whether the local Karachi graph is ready.

### 2. Plan a Delivery
- **Depot and stop selection**: Search the built-in Karachi place directory and OSM results, or click the map to select coordinates.
- **Dynamic Customer Deliveries**: Add customer name, street address, individual package weight (kg), delivery priority (**Normal** vs **⚡ Urgent**), and time window constraints (e.g. `45 min` or `09:00 - 11:00`).
- **Vehicle capacity**: Payload bar shows loaded and remaining capacity; route calculation is blocked when overloaded.
- **Delivery Zones (K-Means Clustering)**: Select cluster count $k \in [2, 5]$ and group stops into colored spatial zones with zone badges on the map.
- **Location autocomplete**: Suggestions appear while typing names such as `FAST`, `DHA`, `Clifton`, `Saddar`, or `Gulshan`.
- **Interactive map**: Google Maps Standard by default, with CARTO Voyager, Positron, and Dark Matter layers.
- **Route calculation**: Builds the selected road-distance matrix, checks constraints, and runs the selected solver.

### 3. Route Results & Simulation
- **Road route map**: Displays calculated road geometry and stop order.
- **Route metrics**: Distance, estimated time, nearest-neighbor comparison, solver runtime, evaluations, and expanded road nodes.
- **Step-by-step itinerary**: Stop order, address, weight, priority, time window, road leg distance, and delivery status.
- **Delivery run**: Animates between stops, supports pause, resume, and stop, records delivered or skipped packages, and updates cargo and progress.
- **Persistence**: Save route details and delivery outcomes to SQLite history.

### 4. Delivery History
- **SQLite Database Storage**: Complete route metadata and individual customer stop logs stored in `data/delivery_history.db`.
- **Searchable Routes Table**: Filter and sort past trips by date, depot, stop count, distance, savings %, and algorithm.
- **Stop Inspection Drawer**: Inspect package weights, priorities, and delivery completion statuses.
- **Load to Planner**: One-click restore of any historical trip back into the active Plan a Delivery map.

### 5. Insights & Analytics
- **Saved-trip distance chart**: Compare optimized route distances with nearest-neighbor baselines.
- **Solver usage chart**: Count saved trips by solver.
- **Solver convergence**: View the distance trace from the active optimization.
- **Travel-time model metrics**: Holdout evaluation on generated training data; these are not live traffic predictions.

### 6. Fleet Settings
- Vehicle maximum payload capacity (kg).
- Average city driving speed (km/h) and service dwell time per stop (mins).
- Route format: Round Trip (Return to depot) vs Open Tour (Finish at last stop).
- Map style, road search method, and default optimization solver.
- The light or dark interface theme is stored in the browser.

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
From the project root, start the local Flask server:
```powershell
python run.py
```
Then open **http://127.0.0.1:5000** in a browser. The server loads the cached Karachi road graph in the background. Use `python run.py --port 5001` to choose another local port.

The browser theme toggle switches between light and dark palettes and remembers the selection on that browser. Map tiles and autocomplete for locations outside the built-in Karachi directory require an internet connection.

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

# Flask planner, optimization, delivery run, and history:
python -m unittest discover -s tests -p test_webapp.py -v
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
- **Road boundary**: Route distances use the cached Karachi graph, centered on Saddar/Kharadar. Places far from that graph may snap to distant road nodes; check stop coordinates before optimizing.
- **Map tiles and search**: CARTO map tiles and OSM location results need an internet connection. OSM autocomplete is rate-limited.
- **Travel-time estimates**: Estimates use route distance, configured speed, and service time. The model metrics use generated data; live traffic is not available.


## Authors & Contribution
- Bisma Shahid
