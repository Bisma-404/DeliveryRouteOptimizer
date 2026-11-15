# Project Proposal: Delivery Route Optimizer on a Real City Map

**Course**: AL-2002 Artificial Intelligence (Laboratory) · Fall 2026  
**Institution**: FAST — National University of Computer and Emerging Sciences  
**Department**: FAST School of Computing · Karachi Campus · Department of Software Engineering  
**Project Idea**: Idea No. 14 from Project Ideas list (Applied / Data)  

---

## Group Information

| Field | Details |
| :--- | :--- |
| **Leader (solo)** | Bisma Shahid |
| **Roll Number** | 24K-3012 |
| **Section** | BSE-5A |
| **Role in Project** | Leader (solo) — 100% Contribution |
| **Project Title** | Delivery Route Optimizer on a Real City Map |
| **GitHub Repository** | `https://github.com/Bisma-404/Delivery-Route-Optimizer-on-a-Real-City-Map.git` |
| **Date of Submission** | 20/10/2026 |

---

## 1. Project Title and Summary

**Title**: Delivery Route Optimizer on a Real City Map

This software assists delivery riders and logistics courier companies in planning the shortest possible delivery tour through 10 to 20 stops on the actual road network of a real city (Lahore). Given a set of addresses, the system determines the optimal visiting order and renders the complete route on an interactive map.

A naive approach cannot scale: the permutation space of 15 stops contains $15! \approx 1.3 \times 10^{12}$ (over one trillion) possible routes. The AI core consists of a two-stage approach:
1. **Low-Level Informed Search**: Custom **A\* search** using the **Haversine heuristic** calculates the true shortest road path between every pair of stops directly on the OpenStreetMap road graph.
2. **High-Level Metaheuristic Optimization**: Three optimization algorithms (**Hill Climbing with 2-opt**, **Simulated Annealing**, and **Genetic Algorithm**) compete against a greedy **Nearest Neighbor baseline** to minimize the total round-trip delivery length.

The user interacts through a desktop Tkinter application featuring an embedded `tkintermapview` widget showing the optimal route traced along real streets.

---

## 2. Problem Statement and Motivation

Urban delivery couriers routinely operate under tight schedules, limited fuel budgets, and complex road topologies featuring one-way streets, roundabouts, and varying road lengths. Small logistics operators in Pakistan typically rely on intuition or a simple greedy "nearest stop first" strategy. Greedy routing often creates long, wasteful backtracking legs that increase travel distance by 20% to 40%.

By formulating the routing challenge as a Traveling Salesperson Delivery Problem on the real road graph, this project delivers tangible fuel savings, reduces carbon emissions, and automates courier dispatching.

---

## 3. Problem Formulation

### 3.1 PEAS Description

| Component | Description for this Project |
| :--- | :--- |
| **Performance measure** | Total route length in kilometers (lower is better), and computation runtime in seconds. |
| **Environment** | The real road network of Lahore (Gulberg area), downloaded via OSMnx from OpenStreetMap, plus 10–20 delivery stops. |
| **Actuators** | Software display: ordered sequence of stops, metric telemetry table, and red polyline drawn on the interactive map widget. |
| **Sensors** | GPS coordinates (latitude, longitude) of stops and OpenStreetMap road nodes and edge distances. |

### 3.2 Environment and Agent Type

| Property | Classification |
| :--- | :--- |
| **Observability** | Fully Observable |
| **Determinism** | Deterministic (Road network edge lengths and coordinates are fixed) |
| **Change over time** | Static |
| **State and actions** | Discrete |
| **Agents** | Single-agent |
| **Agent type** | Utility-based agent (Maximizing route fitness = $1 / \text{total\_route\_length}$) |

### 3.3 Problem Representation

- **State**: A sequence of visited stops starting and ending at the depot: $[s_0, s_1, s_2, \dots, s_{n-1}, s_0]$.
- **Actions**: Transition from current stop $u$ to any unvisited stop $v$.
- **Initial State**: Vehicle at depot $s_0$ with all delivery destinations unvisited.
- **Goal Test**: All $n$ stops visited exactly once, returning to depot $s_0$.
- **Cost Function**: Total road distance:
  $$\text{Cost}(\text{order}) = \sum_{i=0}^{n-1} d_{\text{road}}(s_i, s_{i+1}) \quad \text{where } s_n = s_0$$
- **Fitness Function**:
  $$\text{Fitness}(\text{order}) = \frac{1}{\text{Cost}(\text{order})}$$

---

## 4. Proposed AI Approach

| # | Technique | Role in the Project | Implementation Type |
| :-: | :--- | :--- | :--- |
| 1 | **A\* Search** | Calculates shortest road distance and node path between every pair of stops | **Own code** using Python `heapq` and Haversine heuristic (No `networkx.astar_path`) |
| 2 | **Nearest Neighbor** | Baseline greedy benchmark | **Own code** |
| 3 | **Hill Climbing** | Local search using 2-opt inversion moves | **Own code** |
| 4 | **Simulated Annealing** | Metaheuristic exploring order space and escaping local minima | **Own code** (Exponential cooling schedule) |
| 5 | **Genetic Algorithm** | Population-based evolutionary optimizer | **Own code** (Ordered Crossover OX, Inversion mutation) |

### 4.1 Planned Class Design

- `RouteProblem`: Holds list of stops, distance matrix, and depot; provides `route_length()`, `fitness()`, `generate_neighbors()`.
- `AStarPlanner`: Builds road graph and computes shortest paths; own `heapq` A\* implementation; counts node expansions; extracts detailed road geometries.
- `MetaheuristicSolver` (ABC): Abstract base class defining `solve()` and timing utilities.
  - `NearestNeighborSolver`: Baseline greedy solver.
  - `HillClimbSolver`: 2-opt descent search.
  - `SimulatedAnnealingSolver`: Probabilistic cooling metaheuristic.
  - `GeneticSolver`: Evolutionary chromosome recombination.
- `GraphLoader`: OSMnx road network fetcher and offline `.graphml` caching.
- `StopGenerator`: Samples and maps delivery coordinates to connected graph nodes.
- `DeliveryRouteOptimizerApp`: Tkinter GUI with embedded `tkintermapview`.
- `ExperimentRunner`: Automated benchmark running 10 random instances and generating Matplotlib figures.

---

## 5. Scope and Boundaries

### In Scope
- Real OpenStreetMap road network for Lahore (Gulberg) loaded via OSMnx.
- Offline `.graphml` caching in `data/raw/` for 100% offline reproducibility.
- Custom A\* algorithm with admissibility proof.
- 4 optimization algorithms compared on 10 random problem instances.
- Interactive Tkinter desktop GUI with embedded `tkintermapview` polyline road display.
- Matplotlib analytical charts and CSV results logging.

### Deliberately Out of Scope
- No live traffic sensors or mobile GPS trackers.
- No paid third-party routing APIs (Google Maps API).
- No database authentication or multi-tenant user logins.
- Restricting stops to $\le 20$ stops to keep semester project execution interactive.

---

## 6. Data Source

- **Source**: OpenStreetMap via OSMnx (`https://osmnx.readthedocs.io`).
- **License**: Open Database License (ODbL) with OpenStreetMap contributors attribution.
- **Offline Fallback**: First download caches graph to `data/raw/lahore.graphml`. Stops stored locally in `data/raw/stops_lahore.csv`.

---

## 7. Evaluation Plan

- **Comparison**: Nearest Neighbor vs. Hill Climbing vs. Simulated Annealing vs. Genetic Algorithm.
- **Metrics**: Total route length in kilometers and runtime in seconds.
- **Instances**: 10 random stop sets (15 stops each) generated using fixed seed 42.
- **Required Charts**:
  1. Average Route Length per solver (bar chart with error bars).
  2. Average Runtime per solver (bar chart).
  3. Convergence Trajectory for SA and GA (iteration vs. distance line chart).
  4. Percentage Improvement vs. Nearest Neighbor baseline.
