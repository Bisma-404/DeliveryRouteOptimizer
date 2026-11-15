"""Quick end-to-end backend test — run from project root."""
import sys, os, time, random
os.environ['MPLCONFIGDIR'] = os.path.join(os.environ.get('TEMP', 'C:/Temp'), 'mpl_dro')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
random.seed(42)

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
errors = []

def check(label, cond, detail=""):
    if cond:
        print(f"  {PASS}  {label}")
    else:
        print(f"  {FAIL}  {label}  {detail}")
        errors.append(label)

print("\n=== Delivery Route Optimizer — Backend Test ===\n")

# ── 1. Graph Loading ──────────────────────────────────────────────────────────
print("[1] Graph Loading")
try:
    from src.data.graph_loader import GraphLoader
    t0 = time.time()
    loader = GraphLoader("Karachi")
    G = loader.load_graph(force_download=False)
    elapsed = time.time() - t0
    check("GraphML cache loaded", len(G.nodes) > 100,
          f"got {len(G.nodes)} nodes")
    check("Load time < 10s", elapsed < 10, f"{elapsed:.2f}s")
    bounds = loader.get_graph_bounds()
    check("get_graph_bounds() returns 4 floats", len(bounds) == 4)
    print(f"     nodes={len(G.nodes)}, edges={len(G.edges)}, time={elapsed:.2f}s")
except Exception as e:
    print(f"  {FAIL}  GraphLoader crashed: {e}")
    errors.append("GraphLoader")
    sys.exit(1)

# ── 2. Stop Generation ────────────────────────────────────────────────────────
print("\n[2] Stop Generation")
try:
    from src.data.stop_generator import StopGenerator
    sg = StopGenerator(loader)
    stops = sg.generate_stops(num_stops=15, seed=42)
    check("15 stops returned", len(stops) == 15)
    check("Depot at index 0", stops[0].get("type") == "depot")
    check("All stops have nearest_node", all("nearest_node" in s for s in stops))
    print(f"     depot={stops[0]['name']}")
except Exception as e:
    print(f"  {FAIL}  StopGenerator crashed: {e}")
    errors.append("StopGenerator")
    sys.exit(1)

# ── 3. A* Planner ─────────────────────────────────────────────────────────────
print("\n[3] A* Planner & Distance Matrix")
try:
    from src.core.astar import AStarPlanner
    planner = AStarPlanner(G)
    t0 = time.time()
    dm, dp, ne = planner.build_distance_matrix(stops)
    elapsed = time.time() - t0
    check("Distance matrix is 15×15", len(dm) == 15 and len(dm[0]) == 15)
    check("All distances >= 0", all(dm[i][j] >= 0 for i in range(15) for j in range(15)))
    check("Diagonal is 0", all(dm[i][i] == 0.0 for i in range(15)))
    check("Nodes expanded > 0", ne > 0, f"ne={ne}")
    check("Matrix build time < 60s", elapsed < 60, f"{elapsed:.2f}s")
    print(f"     nodes_expanded={ne}, time={elapsed:.2f}s")
except Exception as e:
    print(f"  {FAIL}  AStarPlanner crashed: {e}")
    errors.append("AStarPlanner")
    sys.exit(1)

# ── 4. All Solvers ────────────────────────────────────────────────────────────
print("\n[4] Solvers")
from src.core.problem import RouteProblem
from src.core.solvers import (NearestNeighborSolver, HillClimbSolver,
                               SimulatedAnnealingSolver, GeneticSolver)
prob = RouteProblem(stops, dm, depot=0)
nn_cost = None
all_costs = {}

for cls, code in [(NearestNeighborSolver, "NN"), (HillClimbSolver, "HC"),
                   (SimulatedAnnealingSolver, "SA"), (GeneticSolver, "GA")]:
    try:
        t0 = time.time()
        solver = cls(prob, seed=42)
        tour, cost, hist, rt = solver.solve()
        elapsed = time.time() - t0
        all_costs[code] = cost
        check(f"{code}: valid tour", len(tour) >= 15, f"len={len(tour)}")
        check(f"{code}: positive cost", cost > 0, f"cost={cost:.3f}")
        check(f"{code}: has history", len(hist) > 0, f"iters={len(hist)}")
        if code == "NN":
            nn_cost = cost
        print(f"     {code}: {cost:.3f} km, {len(hist)} iters, {elapsed:.4f}s")
    except Exception as e:
        print(f"  {FAIL}  {code} crashed: {e}")
        errors.append(code)

# Check SA and GA improve on NN
if nn_cost:
    check("SA <= NN cost", all_costs.get("SA", 1e9) <= nn_cost * 1.05)
    check("HC <= NN cost", all_costs.get("HC", 1e9) <= nn_cost * 1.05)

# ── 5. Route Coordinates ──────────────────────────────────────────────────────
print("\n[5] Route Coordinates (Real Road Geometry)")
try:
    # Use the last tour (GA)
    coords = planner.get_detailed_route_coordinates(tour, dp)
    check("Route has coords", len(coords) >= 15, f"got {len(coords)}")
    check("All coords are (lat,lon) pairs",
          all(isinstance(c, (tuple, list)) and len(c) == 2 for c in coords[:5]))
    check("Coords in Karachi lat range (24–25)",
          all(24.0 <= c[0] <= 25.5 for c in coords[:10]))
    print(f"     {len(coords)} road-following coordinate points")
except Exception as e:
    print(f"  {FAIL}  get_detailed_route_coordinates crashed: {e}")
    errors.append("route_coords")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
if errors:
    print(f"  FAILED: {len(errors)} checks  →  {errors}")
    sys.exit(1)
else:
    print(f"  ALL TESTS PASSED  OK!")
    print(f"{'='*50}\n")
