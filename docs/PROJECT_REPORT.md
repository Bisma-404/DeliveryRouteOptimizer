# Project Report: Delivery Route Optimizer on a Real City Map

**Course**: AL-2002 Artificial Intelligence (Laboratory) · Fall 2026  
**Institution**: FAST — National University of Computer and Emerging Sciences  
**Department**: FAST School of Computing · Karachi Campus · Department of Software Engineering  
**Project Title**: Delivery Route Optimizer on a Real City Map  
**Student**: Bisma Shahid (Roll No: 24K-3012) · Section: BSE-5A · Leader (solo)  
**GitHub Repository**: `https://github.com/Bisma-404/Delivery-Route-Optimizer-on-a-Real-City-Map.git`  

---

## Executive Summary

Urban logistics delivery operations require solving two interconnected algorithmic challenges: calculating true ground driving distances across real, curved road networks, and ordering dozens of delivery stops to minimize fuel and transit time. 

This project implements a complete, production-grade desktop application using **Tkinter** and **`tkintermapview`** for real road delivery optimization in **Lahore, Pakistan**. Road data is retrieved directly from OpenStreetMap via **OSMnx** and cached locally in GraphML format. 

The algorithmic core operates in two stages:
1. **Low-level informed graph search**: A custom **A\* algorithm** using the spherical **Haversine heuristic** calculates exact road network distances while tracking expanded nodes.
2. **High-level metaheuristic combinatorial optimization**: Three optimization algorithms (**Hill Climbing with 2-opt**, **Simulated Annealing**, and a **Genetic Algorithm**) compete against a greedy **Nearest Neighbor baseline** to minimize the total round-trip delivery length.

Extensive empirical evaluation across 10 randomized 15-stop test instances (seed 42) demonstrates that **Simulated Annealing** and the **Genetic Algorithm** outperform the Nearest Neighbor baseline by an average of **12.26%** and **11.97%** respectively, achieving up to **23.57%** route reduction on challenging instances while maintaining sub-second execution speeds.

---

## 1. Problem Formulation and PEAS Model

### 1.1 PEAS Description (Lab 03)
- **Performance Measure**:
  - Primary: Total delivery tour length in kilometers (lower is better).
  - Secondary: Computation runtime in seconds.
  - Search Efficiency: Number of nodes expanded during A\* pathfinding.
- **Environment**:
  - The actual road network of Lahore (Gulberg area, 1,227 nodes and 3,226 road segments).
  - A depot (Liberty Market) and 14 delivery stops.
- **Actuators**:
  - Tkinter desktop GUI rendering delivery metrics, stop tables, and an interactive embedded map displaying the optimal route traced along real road geometry in red.
- **Sensors**:
  - OpenStreetMap nodes (latitude, longitude, intersection IDs) and directed edges (street lengths in meters, curvature geometries).

### 1.2 Environment Properties
- **Fully Observable**: The complete road network topology and all delivery coordinates are known in advance.
- **Deterministic**: Given an ordering of stops, the road distance matrix and path are invariant and reproducible.
- **Static**: The road network does not change during solver execution.
- **Discrete**: Stops, intersections, and route permutations are distinct, discrete entities.
- **Single-Agent**: The optimization agent acts independently without competing traffic agents.
- **Agent Type**: **Utility-based Agent**, seeking a tour that maximizes the utility function:
  $$U(\text{order}) = \text{Fitness}(\text{order}) = \frac{1}{\text{Route Length in km}}$$

---

## 2. System Architecture and Class Hierarchy

The project is structured according to strict Object-Oriented Programming (OOP) principles, emphasizing encapsulation, modularity, and inheritance:

```
src/
├── core/
│   ├── astar.py       <- Custom A* planner with heapq & Haversine heuristic
│   ├── problem.py     <- RouteProblem encapsulating stops, distance matrix & fitness
│   └── solvers.py     <- MetaheuristicSolver (ABC) & 4 concrete solver implementations
├── data/
│   ├── graph_loader.py   <- OSMnx road graph downloading, SCC filtering & GraphML cache
│   └── stop_generator.py <- Stop sampling, CSV reading & road node snapping
├── gui/
│   └── app.py         <- Tkinter GUI with embedded TkinterMapView and threading
└── main.py            <- Program entry point with CLI and GUI modes
```

### 2.1 Class Diagram & Responsibilities

1. **`RouteProblem`**:
   - Attributes: `stops`, `distance_matrix`, `depot`, `num_stops`.
   - Methods: `route_length(order)`, `fitness(order)`, `to_full_tour(order)`, `generate_neighbors(order, method="2-opt")`, `sample_neighbor()`, `validate_tour()`.
2. **`AStarPlanner`**:
   - Attributes: `graph`, `heuristic`.
   - Methods: `shortest_path(start, goal)` (own `heapq` code), `uninformed_search(start, goal)` (UCS baseline), `build_distance_matrix(stops)`, `get_detailed_route_coordinates(order, paths)`.
3. **`MetaheuristicSolver` (Abstract Base Class)**:
   - Attributes: `problem`, `seed`, `rng`, `name`.
   - Abstract Method: `@abstractmethod solve() -> Tuple[List[int], float, List[float], float]`.
4. **Concrete Solvers**:
   - `NearestNeighborSolver`: Implements greedy nearest-unvisited heuristic.
   - `HillClimbSolver`: Implements 2-opt local search descent.
   - `SimulatedAnnealingSolver`: Implements geometric cooling with Boltzmann acceptance.
   - `GeneticSolver`: Implements Ordered Crossover (OX), inversion mutation, and tournament selection.
5. **`GraphLoader`**:
   - Caches graph to `data/raw/lahore.graphml`. Extracts largest Strongly Connected Component (1,227 nodes) to guarantee 100% path existence.
6. **`DeliveryRouteOptimizerApp`**:
   - Threaded GUI avoiding interface freezing during A\* matrix generation and solver execution.

---

## 3. Algorithmic Implementation Details

### 3.1 Custom A\* Search with Admissible Haversine Heuristic

In compliance with project specifications, **`networkx.astar_path` was NOT used**. The search is implemented from scratch using Python's `heapq` module.

#### Mathematical Admissibility & Consistency Proof (Lab 05)
The heuristic calculates the great-circle spherical distance:
$$h(u, v) = 2 R \arcsin \left( \sqrt{\sin^2\left(\frac{\Delta \phi}{2}\right) + \cos \phi_u \cos \phi_v \sin^2\left(\frac{\Delta \lambda}{2}\right)} \right)$$
where $R = 6,371,000\text{ m}$.

- **Admissibility**: The great-circle distance is the shortest possible path between any two coordinates in three-dimensional physical space. Since vehicles must navigate along existing street geometry, curves, and turns:
  $$d_{\text{road}}^*(u, v) \ge h(u, v) \quad \forall u, v \in V$$
  Therefore, $h(u, v)$ never overestimates the true remaining distance, proving strict admissibility.
- **Consistency (Monotonicity)**: By the spherical triangle inequality:
  $$h(u, v) \le c(u, w) + h(w, v)$$
  Every edge cost $c(u, w) \ge h(u, w)$, ensuring that once a node is expanded from the priority queue, the discovered path to that node is globally optimal.

#### Empirical Node Expansion: A\* vs. Uniform Cost Search (UCS)
On a representative path across Lahore between node 2382893441 and node 11825680696:
- **UCS (Dijkstra, $h=0$)**: 710 nodes expanded, Distance: 2,443.1 m.
- **Custom A\* (Haversine)**: 279 nodes expanded, Distance: 2,443.1 m.
- **Node Reduction**: **60.7% fewer nodes explored**, proving superior search pruning.

---

### 3.2 Optimization Solvers

#### 1. Nearest Neighbor Baseline (Greedy)
- Starts at depot $s_0$.
- Repeatedly selects $s^* = \arg\min_{v \in \text{Unvisited}} d_{\text{road}}(u, v)$.
- Returns to depot.
- Time Complexity: $O(N^2)$.
- Fast ($< 0.0001\text{s}$), but highly susceptible to greedy "myopia", causing costly return legs.

#### 2. Hill Climbing (2-opt Local Search)
- Starts with a random tour.
- Explores all possible 2-opt edge inversions ($O(N^2)$ neighborhood size):
  $$\text{tour}' = [s_0, \dots, s_{i-1}, s_j, s_{j-1}, \dots, s_i, s_{j+1}, \dots, s_0]$$
- Employs a first-improvement strategy to descend towards local minima.
- Converges in 15–30 iterations ($0.0028\text{s}$ average).

#### 3. Simulated Annealing
- Hyperparameters:
  - Initial temperature: $T_0 = 100.0$
  - Cooling schedule: $T_{k+1} = 0.995 \times T_k$
  - Stopping temperature: $T_{\min} = 0.001$
  - Max iterations: 2,500
- Acceptance Criterion:
  $$\Delta = \text{cost}(\text{candidate}) - \text{cost}(\text{current})$$
  If $\Delta < 0$, the move is accepted unconditionally. If $\Delta \ge 0$, it is accepted with probability $P = \exp(-\Delta / T)$.
- Early iterations accept uphill moves, escaping sub-optimal local traps before cooling into high-quality tours.

#### 4. Genetic Algorithm
- Hyperparameters:
  - Population size: 80 individuals
  - Generations: 200
  - Crossover operator: Ordered Crossover (OX) with probability $p_c = 0.85$
  - Mutation operator: Inversion mutation (sub-segment reversal) with probability $p_m = 0.20$
  - Selection: Tournament selection (size $k = 5$) based on fitness $1 / \text{cost}$
  - Elitism: Preserves top 2 individuals directly into the next generation.

---

## 4. Experimental Results and Analysis

A full benchmark experiment was conducted across **10 independent problem instances**, each containing **15 stops** sampled with deterministic seeds derived from master seed 42.

### 4.1 Benchmark Summary Table (N=10 Instances)

| Solver | Mean Route Length (km) | Std Dev (km) | Min Route (km) | Mean Runtime (s) | Mean Improvement vs NN | Peak Improvement vs NN |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Nearest Neighbor** | 19.40 km | 1.64 km | 16.31 km | 0.00005 s | 0.00% (Baseline) | 0.00% |
| **Hill Climbing** | 17.35 km | 1.59 km | 13.85 km | 0.00287 s | **10.52%** | **16.32%** |
| **Simulated Annealing** | **17.05 km** | 2.09 km | 13.57 km | 0.01530 s | **12.26%** | **23.57%** |
| **Genetic Algorithm** | **17.08 km** | 1.86 km | **13.53 km** | 0.24857 s | **11.97%** | **23.25%** |

### 4.2 Analysis of the 4 Generated Figures

1. **Figure 1 (`1_avg_route_length.png`)**:
   - Nearest Neighbor averages **19.40 km**.
   - Hill Climbing achieves **17.35 km** (2.05 km saved per tour).
   - Simulated Annealing achieves **17.05 km** (2.35 km saved per tour).
   - Genetic Algorithm achieves **17.08 km** (2.32 km saved per tour).
   - Error bars confirm consistent superiority of metaheuristics across all instances.

2. **Figure 2 (`2_avg_runtime.png`)**:
   - Illustrates the classic speed vs. quality Pareto trade-off:
     - NN runs in 0.00005s (instantaneous).
     - Hill Climbing takes ~0.0029s.
     - Simulated Annealing achieves the best distance in just 0.0153s.
     - Genetic Algorithm requires ~0.25s due to population evaluations, still well under 1 second.

3. **Figure 3 (`3_convergence_sa_ga.png`)**:
   - **Simulated Annealing** starts at ~22.5 km, rapidly accepts exploratory moves, and gradually stabilizes as $T$ drops below 1.0, converging to a sharp optimum.
   - **Genetic Algorithm** begins with diverse random chromosomes and steadily descends generation by generation as crossover concentrates high-fitness building blocks.

4. **Figure 4 (`4_pct_improvement_vs_nn.png`)**:
   - Shows that AI metaheuristics consistently cut delivery distance by 10% to 12% on average.
   - On challenging spatial configurations, peak improvements reached **23.57%** (Simulated Annealing) and **23.25%** (Genetic Algorithm), validating the hypothesis stated in the proposal.

---

## 5. Graphical User Interface (GUI)

The application provides an intuitive desktop interface built with **Tkinter** and **`tkintermapview`**:
- **Sidebar Controls**:
  - City dropdown (Lahore pre-configured).
  - One-click road network loader with graph statistics.
  - Interactive stop generator (customizable count up to 20).
  - Radio button selector for all 4 solvers.
  - "Run Solver" and "Run Full Experiment" triggers.
  - Comprehensive telemetry panel displaying route distance, runtime, and A\* nodes expanded.
- **Embedded Interactive Map**:
  - Automatically centers and zooms into the road network.
  - Color-coded pins: Green marker for depot, Blue markers for delivery stops.
  - **Accurate Road Polyline**: Traces the actual curves, roundabouts, and turns along OpenStreetMap road geometries using an unbroken red line.
- **Non-Freezing Concurrency**:
  - All graph downloads, distance matrix calculations, and metaheuristic executions run inside daemon threads, updating the GUI safely via `root.after()`.

---

## 6. Limitations and Ethical Considerations

### 6.1 Limitations
1. **Static Graph Weights**: Edge lengths reflect geometric road distances. Real-time traffic congestion, signal delays, and road closures are not modeled.
2. **Instance Size Boundary**: Computing the full all-pairs A\* distance matrix takes $O(N^2 \cdot (|V| \log |V| + |E|))$. For $N \le 20$, this completes in $< 1\text{ second}$. For $N > 100$, one-to-all Dijkstra or contraction hierarchies would be required.
3. **Vehicle Constraints**: The current formulation assumes an unconstrained vehicle capacity (single vehicle tour).

### 6.2 Ethical and Environmental Considerations
- **Fuel & Carbon Reduction**: Reducing delivery distances by 10%–25% directly curtails vehicle carbon emissions, particulate pollution, and operating expenses.
- **Rider Well-Being**: Eliminating backtracking and confusing routes reduces courier stress and navigation fatigue.
- **Data Attribution**: All map data is sourced from OpenStreetMap contributors under the Open Database License (ODbL).

---

## 7. Individual Contribution & Viva Preparation

### 7.1 Student Contribution Table
| Member | Modules Owned & Built | Share |
| :--- | :--- | :---: |
| **Bisma Shahid (24K-3012)** | GraphLoader, StopGenerator, custom A\* planner with heapq, Haversine heuristic proof, RouteProblem formulation, NearestNeighborSolver, HillClimbSolver, SimulatedAnnealingSolver, GeneticSolver, TkinterMapView GUI, ExperimentRunner, Matplotlib figures, documentation. | **100%** |

### 7.2 Viva Preparation Questions & Key Answers
1. **Why is your Haversine heuristic admissible?**  
   *Answer*: The great-circle distance is the shortest possible path between two coordinates in 3D physical space. Because real road paths must follow curved street segments, road distance is always $\ge$ Haversine distance. It never overestimates remaining cost ($h(u) \le h^*(u)$).
2. **What does the temperature parameter $T$ do in Simulated Annealing?**  
   *Answer*: $T$ controls the probability of accepting worse solutions ($P = e^{-\Delta / T}$). At high initial $T$, the probability is high, enabling broad exploration and escaping local optima. As $T$ cools geometrically ($T \leftarrow 0.995 \cdot T$), the search transitions into pure exploitation.
3. **How does Ordered Crossover (OX) avoid duplicate stops?**  
   *Answer*: OX copies a contiguous slice from parent 1 directly into the child, and fills the remaining slots using the relative ordering of parent 2 while skipping elements already present in the copied slice.
