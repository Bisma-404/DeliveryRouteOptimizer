"""Optimization solvers for the Delivery Route Optimizer.

Implements the object-oriented hierarchy:
    MetaheuristicSolver (ABC)
        ├── NearestNeighborSolver (Baseline greedy)
        ├── HillClimbSolver (Local search 2-opt)
        ├── SimulatedAnnealingSolver (Stochastic cooling schedule)
        └── GeneticSolver (Evolutionary order crossover & mutation)

All solvers record:
- Initial tour & initial cost
- Final best tour & best cost
- Number of iterations / generations
- Total candidate route evaluations
- Full convergence history
- Execution runtime
"""

from __future__ import annotations

import time
import math
import random
import logging
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Any, Dict
from dataclasses import dataclass
from .problem import RouteProblem

logger = logging.getLogger(__name__)


@dataclass
class SolverResult:
    """Rich result object holding complete solver execution metrics."""
    solver_name: str
    initial_tour: List[int]
    initial_cost_km: float
    best_tour: List[int]
    best_cost_km: float
    iterations: int
    evaluations: int
    convergence_history: List[float]
    runtime_seconds: float

    # Support tuple-like unpacking (best_tour, best_cost, history, runtime) for backwards compatibility
    def __iter__(self):
        yield self.best_tour
        yield self.best_cost_km
        yield self.convergence_history
        yield self.runtime_seconds

    def __getitem__(self, index):
        legacy = [self.best_tour, self.best_cost_km, self.convergence_history, self.runtime_seconds]
        return legacy[index]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "solver_name": self.solver_name,
            "initial_tour": self.initial_tour,
            "initial_cost_km": self.initial_cost_km,
            "best_tour": self.best_tour,
            "best_cost_km": self.best_cost_km,
            "iterations": self.iterations,
            "evaluations": self.evaluations,
            "convergence_history": self.convergence_history,
            "runtime_seconds": self.runtime_seconds,
        }


class MetaheuristicSolver(ABC):
    """Abstract base class for delivery route optimization solvers.

    Encapsulates the problem instance, random seed, execution timing,
    candidate evaluations count, and convergence tracking.
    """

    def __init__(self, problem: RouteProblem, seed: Optional[int] = 42, name: str = "MetaheuristicSolver"):
        """Initialize base solver.

        Args:
            problem: Instance of RouteProblem with stops and distance matrix.
            seed: Integer random seed for reproducibility (or None for random).
            name: Display name for the solver.
        """
        self.problem = problem
        self.seed = seed
        self.rng = random.Random(seed if seed is not None else random.randint(1, 1000000))
        self.name = name
        self.last_result: Optional[SolverResult] = None

    @abstractmethod
    def solve(self) -> SolverResult:
        """Execute the optimization algorithm.

        Returns:
            SolverResult: Unpacks as (best_tour, best_cost_km, history, runtime_seconds).
        """
        pass


class NearestNeighborSolver(MetaheuristicSolver):
    """Greedy baseline solver (Nearest Neighbor heuristic).

    Starting at the depot, the algorithm iteratively visits the closest
    unvisited stop based on the A* road distance matrix, finally returning
    to the depot (if round-trip).
    """

    def __init__(self, problem: RouteProblem, seed: Optional[int] = 42):
        super().__init__(problem, seed=seed, name="Nearest Neighbor (Baseline)")

    def solve(self) -> SolverResult:
        start_time = time.perf_counter()

        n = self.problem.num_stops
        depot = self.problem.depot
        unvisited = set(range(n))
        unvisited.remove(depot)

        current = depot
        tour = [depot]
        evaluations = 0

        while unvisited:
            best_dist = float("inf")
            next_stop = None
            for s in unvisited:
                evaluations += 1
                d = float(self.problem.distance_matrix[current][s])
                if d < best_dist:
                    best_dist = d
                    next_stop = s
            tour.append(next_stop)
            unvisited.remove(next_stop)
            current = next_stop

        final_tour = self.problem.to_full_tour(tour)
        cost = self.problem.route_length(final_tour)
        history = [cost]
        runtime = time.perf_counter() - start_time

        result = SolverResult(
            solver_name=self.name,
            initial_tour=list(final_tour),
            initial_cost_km=cost,
            best_tour=list(final_tour),
            best_cost_km=cost,
            iterations=1,
            evaluations=evaluations,
            convergence_history=history,
            runtime_seconds=runtime,
        )
        self.last_result = result
        logger.info("[%s] Completed in %.4fs | Distance: %.2f km | Evaluations: %d",
                    self.name, runtime, cost, evaluations)
        return result


class HillClimbSolver(MetaheuristicSolver):
    """Local Search Solver using 2-opt neighborhood descent.

    Iteratively evaluates neighboring permutations generated by reversing
    sub-tours. Accepts strictly improving neighbors until a local optimum
    is reached.
    """

    def __init__(
        self,
        problem: RouteProblem,
        max_iterations: int = 600,
        seed: Optional[int] = 42
    ):
        super().__init__(problem, seed=seed, name="Hill Climbing (2-opt)")
        self.max_iterations = max_iterations

    def solve(self) -> SolverResult:
        start_time = time.perf_counter()

        # Generate a distinct random initial tour
        initial_tour = self.problem.random_solution(self.rng)
        initial_cost = self.problem.route_length(initial_tour)

        current_tour = list(initial_tour)
        current_cost = initial_cost
        best_tour = list(initial_tour)
        best_cost = initial_cost

        history: List[float] = [best_cost]
        iteration = 0
        evaluations = 0

        while iteration < self.max_iterations:
            iteration += 1
            improved = False

            neighbors = self.problem.generate_neighbors(current_tour, method="2-opt")
            self.rng.shuffle(neighbors)

            for neighbor in neighbors:
                evaluations += 1
                neighbor_cost = self.problem.route_length(neighbor)
                if neighbor_cost < current_cost - 1e-6:
                    current_tour = list(neighbor)
                    current_cost = neighbor_cost
                    improved = True
                    if current_cost < best_cost:
                        best_tour = list(current_tour)
                        best_cost = current_cost
                    break  # First-improvement descent

            history.append(best_cost)

            if not improved:
                logger.info("[%s] Converged to local optimum at iteration %d.", self.name, iteration)
                break

        runtime = time.perf_counter() - start_time
        result = SolverResult(
            solver_name=self.name,
            initial_tour=initial_tour,
            initial_cost_km=initial_cost,
            best_tour=best_tour,
            best_cost_km=best_cost,
            iterations=iteration,
            evaluations=evaluations,
            convergence_history=history,
            runtime_seconds=runtime,
        )
        self.last_result = result
        logger.info("[%s] Completed in %.4fs | Init: %.2f km -> Best: %.2f km | Evals: %d",
                    self.name, runtime, initial_cost, best_cost, evaluations)
        return result


class SimulatedAnnealingSolver(MetaheuristicSolver):
    """Simulated Annealing metaheuristic solver.

    Escapes local optima by probabilistically accepting worsening solutions
    based on the Boltzmann acceptance criterion:
        P(accept) = exp(-Δ / T)
    with geometric temperature decay T_{k+1} = α * T_k.
    """

    def __init__(
        self,
        problem: RouteProblem,
        initial_temp: float = 120.0,
        cooling_rate: float = 0.995,
        min_temp: float = 0.001,
        max_iterations: int = 3000,
        seed: Optional[int] = 42
    ):
        super().__init__(problem, seed=seed, name="Simulated Annealing")
        self.initial_temp = initial_temp
        self.cooling_rate = cooling_rate
        self.min_temp = min_temp
        self.max_iterations = max_iterations

    def solve(self) -> SolverResult:
        start_time = time.perf_counter()

        initial_tour = self.problem.random_solution(self.rng)
        initial_cost = self.problem.route_length(initial_tour)

        current_tour = list(initial_tour)
        current_cost = initial_cost
        best_tour = list(initial_tour)
        best_cost = initial_cost

        history: List[float] = [best_cost]
        temp = self.initial_temp
        iteration = 0
        evaluations = 0

        while iteration < self.max_iterations and temp > self.min_temp:
            iteration += 1

            candidate_tour = self.problem.sample_neighbor(current_tour, self.rng, method="2-opt")
            evaluations += 1
            candidate_cost = self.problem.route_length(candidate_tour)

            delta = candidate_cost - current_cost

            if delta < 0:
                current_tour = candidate_tour
                current_cost = candidate_cost
                if current_cost < best_cost:
                    best_tour = list(current_tour)
                    best_cost = current_cost
            else:
                acceptance_prob = math.exp(-delta / max(temp, 1e-9))
                if self.rng.random() < acceptance_prob:
                    current_tour = candidate_tour
                    current_cost = candidate_cost

            history.append(best_cost)
            temp *= self.cooling_rate

        runtime = time.perf_counter() - start_time
        result = SolverResult(
            solver_name=self.name,
            initial_tour=initial_tour,
            initial_cost_km=initial_cost,
            best_tour=best_tour,
            best_cost_km=best_cost,
            iterations=iteration,
            evaluations=evaluations,
            convergence_history=history,
            runtime_seconds=runtime,
        )
        self.last_result = result
        logger.info("[%s] Completed in %.4fs | Init: %.2f km -> Best: %.2f km | Evals: %d",
                    self.name, runtime, initial_cost, best_cost, evaluations)
        return result


class GeneticSolver(MetaheuristicSolver):
    """Genetic Algorithm metaheuristic solver.

    Evolves a population of delivery route permutations using:
        - Tournament selection based on fitness (1 / route_length)
        - Ordered Crossover (OX) with cyclic filling to preserve permutation validity
        - 2-opt inversion mutation
        - Elitism preserving top chromosomes across generations
    """

    def __init__(
        self,
        problem: RouteProblem,
        population_size: int = 80,
        generations: int = 200,
        crossover_rate: float = 0.85,
        mutation_rate: float = 0.22,
        tournament_size: int = 5,
        elite_count: int = 2,
        seed: Optional[int] = 42
    ):
        super().__init__(problem, seed=seed, name="Genetic Algorithm")
        self.population_size = population_size
        self.generations = generations
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate
        self.tournament_size = tournament_size
        self.elite_count = elite_count

    def _create_individual(self) -> List[int]:
        deliveries = [i for i in range(self.problem.num_stops) if i != self.problem.depot]
        self.rng.shuffle(deliveries)
        return deliveries

    def _ordered_crossover(self, parent1: List[int], parent2: List[int]) -> List[int]:
        size = len(parent1)
        if size <= 2:
            return list(parent1)

        idx1, idx2 = sorted(self.rng.sample(range(size), 2))

        child = [None] * size
        child[idx1:idx2 + 1] = parent1[idx1:idx2 + 1]
        copied_set = set(child[idx1:idx2 + 1])

        p2_idx = 0
        for i in range(size):
            if child[i] is None:
                while p2_idx < len(parent2) and parent2[p2_idx] in copied_set:
                    p2_idx += 1
                if p2_idx < len(parent2):
                    child[i] = parent2[p2_idx]
                    copied_set.add(parent2[p2_idx])
                    p2_idx += 1

        # Fallback if any unassigned slots
        for i in range(size):
            if child[i] is None:
                missing = [x for x in parent1 if x not in copied_set]
                if missing:
                    val = missing[0]
                    child[i] = val
                    copied_set.add(val)

        return child  # type: ignore

    def _mutate(self, individual: List[int]) -> List[int]:
        size = len(individual)
        if size <= 2:
            return list(individual)

        idx1, idx2 = sorted(self.rng.sample(range(size), 2))
        mutant = list(individual)
        mutant[idx1:idx2 + 1] = mutant[idx1:idx2 + 1][::-1]
        return mutant

    def solve(self) -> SolverResult:
        start_time = time.perf_counter()

        population = [self._create_individual() for _ in range(self.population_size)]

        initial_tour = self.problem.to_full_tour(population[0])
        initial_cost = self.problem.route_length(initial_tour)

        best_tour = list(initial_tour)
        best_cost = initial_cost
        history: List[float] = [best_cost]
        evaluations = 0

        for gen in range(self.generations):
            scored = []
            for ind in population:
                evaluations += 1
                full_t = self.problem.to_full_tour(ind)
                cost = self.problem.route_length(full_t)
                fit = 1.0 / (cost + 1e-9)
                scored.append((cost, fit, ind, full_t))
                if cost < best_cost:
                    best_cost = cost
                    best_tour = list(full_t)

            history.append(best_cost)
            scored.sort(key=lambda item: item[0])

            # Elitism
            new_population = [item[2] for item in scored[:self.elite_count]]

            def tournament() -> List[int]:
                candidates = self.rng.sample(scored, min(self.tournament_size, len(scored)))
                candidates.sort(key=lambda c: c[0])
                return list(candidates[0][2])

            while len(new_population) < self.population_size:
                p1 = tournament()
                p2 = tournament()

                if self.rng.random() < self.crossover_rate:
                    child = self._ordered_crossover(p1, p2)
                else:
                    child = list(p1)

                if self.rng.random() < self.mutation_rate:
                    child = self._mutate(child)

                new_population.append(child)

            population = new_population

        runtime = time.perf_counter() - start_time
        result = SolverResult(
            solver_name=self.name,
            initial_tour=initial_tour,
            initial_cost_km=initial_cost,
            best_tour=best_tour,
            best_cost_km=best_cost,
            iterations=self.generations,
            evaluations=evaluations,
            convergence_history=history,
            runtime_seconds=runtime,
        )
        self.last_result = result
        logger.info("[%s] Completed in %.4fs | Init: %.2f km -> Best: %.2f km | Generations: %d | Evals: %d",
                    self.name, runtime, initial_cost, best_cost, self.generations, evaluations)
        return result
