"""Optimization solvers for the Delivery Route Optimizer.

Implements the object-oriented hierarchy:
    MetaheuristicSolver (ABC)
        ├── NearestNeighborSolver (Baseline greedy)
        ├── HillClimbSolver (Local search 2-opt)
        ├── SimulatedAnnealingSolver (Stochastic cooling schedule)
        └── GeneticSolver (Evolutionary order crossover & mutation)

All solvers override solve() and maintain reproducible convergence histories.
"""

import time
import math
import random
import logging
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
from .problem import RouteProblem

logger = logging.getLogger(__name__)


class MetaheuristicSolver(ABC):
    """Abstract base class for delivery route optimization solvers.

    Encapsulates the problem instance, random seed, execution timing,
    and convergence tracking.

    Attributes:
        problem (RouteProblem): The routing problem instance to solve.
        seed (int): Random seed for reproducibility. Default: 42.
        rng (random.Random): Seeded random generator instance.
        name (str): Human-readable name of the solver.
    """

    def __init__(self, problem: RouteProblem, seed: int = 42, name: str = "MetaheuristicSolver"):
        """Initialize base solver.

        Args:
            problem: Instance of RouteProblem with stops and distance matrix.
            seed: Integer random seed for reproducible stochastic operations.
            name: Display name for the solver.
        """
        self.problem = problem
        self.seed = seed
        self.rng = random.Random(seed)
        self.name = name

    @abstractmethod
    def solve(self) -> Tuple[List[int], float, List[float], float]:
        """Execute the optimization algorithm.

        Returns:
            Tuple[List[int], float, List[float], float]:
                - best_order: The best tour discovered [depot, ..., depot].
                - best_cost_km: Total road length of the best tour in kilometers.
                - convergence_history: List of best costs recorded over iterations.
                - runtime_seconds: Total execution time in seconds.
        """
        pass


class NearestNeighborSolver(MetaheuristicSolver):
    """Greedy baseline solver (Nearest Neighbor heuristic).

    Starting at the depot, the algorithm iteratively visits the closest
    unvisited stop based on the A* road distance matrix, finally returning
    to the depot. Serves as the benchmark baseline for AI techniques.
    """

    def __init__(self, problem: RouteProblem, seed: int = 42):
        """Initialize NearestNeighborSolver."""
        super().__init__(problem, seed=seed, name="Nearest Neighbor (Baseline)")

    def solve(self) -> Tuple[List[int], float, List[float], float]:
        """Solve using greedy nearest neighbor rule.

        Returns:
            Tuple[List[int], float, List[float], float]:
                (best_tour, best_cost_km, convergence_history, runtime_seconds)
        """
        start_time = time.perf_counter()

        n = self.problem.num_stops
        depot = self.problem.depot
        unvisited = set(range(n))
        unvisited.remove(depot)

        current = depot
        tour = [depot]
        history: List[float] = []

        while unvisited:
            # Pick unvisited stop with minimum distance from current stop
            next_stop = min(unvisited, key=lambda s: self.problem.distance_matrix[current][s])
            tour.append(next_stop)
            unvisited.remove(next_stop)
            current = next_stop

        # Build canonical tour (returns to depot if round_trip is True)
        tour = self.problem.to_full_tour(tour)
        cost = self.problem.route_length(tour)
        history.append(cost)

        runtime = time.perf_counter() - start_time
        logger.info(
            "[%s] Completed in %.4fs | Best Distance: %.2f km",
            self.name, runtime, cost
        )
        return tour, cost, history, runtime


class HillClimbSolver(MetaheuristicSolver):
    """Local Search Solver using 2-opt neighborhood descent.

    Iteratively searches for a neighboring route that strictly reduces total
    road distance. Terminates when no improving neighbor exists (local optimum).
    """

    def __init__(
        self,
        problem: RouteProblem,
        max_iterations: int = 500,
        seed: int = 42
    ):
        """Initialize HillClimbSolver.

        Args:
            problem: RouteProblem instance.
            max_iterations: Upper bound on descent steps.
            seed: Random seed.
        """
        super().__init__(problem, seed=seed, name="Hill Climbing (2-opt)")
        self.max_iterations = max_iterations

    def solve(self) -> Tuple[List[int], float, List[float], float]:
        """Execute Hill Climbing local search.

        Returns:
            Tuple[List[int], float, List[float], float]:
                (best_tour, best_cost_km, convergence_history, runtime_seconds)
        """
        start_time = time.perf_counter()

        # Start with a random initial solution
        current_tour = self.problem.random_solution(self.rng)
        current_cost = self.problem.route_length(current_tour)

        best_tour = list(current_tour)
        best_cost = current_cost
        history: List[float] = [best_cost]

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            improved = False

            # Explore 2-opt neighbors
            neighbors = self.problem.generate_neighbors(current_tour, method="2-opt")
            # Shuffle neighbors to break ties stochastically
            self.rng.shuffle(neighbors)

            for neighbor in neighbors:
                neighbor_cost = self.problem.route_length(neighbor)
                if neighbor_cost < current_cost - 1e-6:
                    current_tour = neighbor
                    current_cost = neighbor_cost
                    improved = True
                    if current_cost < best_cost:
                        best_tour = list(current_tour)
                        best_cost = current_cost
                    break  # First-improvement strategy

            history.append(best_cost)

            if not improved:
                # Reached a local optimum
                logger.info(
                    "[%s] Converged to local optimum at iteration %d.",
                    self.name, iteration
                )
                break

        runtime = time.perf_counter() - start_time
        logger.info(
            "[%s] Completed in %.4fs | Best Distance: %.2f km (Iterations: %d)",
            self.name, runtime, best_cost, iteration
        )
        return best_tour, best_cost, history, runtime


class SimulatedAnnealingSolver(MetaheuristicSolver):
    """Simulated Annealing metaheuristic solver.

    Escapes local optima by probabilistically accepting worsening solutions
    based on the Boltzmann acceptance probability:
        P(accept) = exp(-Δ / T)
    where T decays following an exponential cooling schedule T_{k+1} = α * T_k.
    """

    def __init__(
        self,
        problem: RouteProblem,
        initial_temp: float = 100.0,
        cooling_rate: float = 0.995,
        min_temp: float = 0.001,
        max_iterations: int = 2500,
        seed: int = 42
    ):
        """Initialize SimulatedAnnealingSolver.

        Args:
            problem: RouteProblem instance.
            initial_temp: Starting temperature T_0.
            cooling_rate: Geometric cooling decay factor alpha (0 < alpha < 1).
            min_temp: Stopping threshold temperature T_min.
            max_iterations: Maximum iterations to execute.
            seed: Random seed.
        """
        super().__init__(problem, seed=seed, name="Simulated Annealing")
        self.initial_temp = initial_temp
        self.cooling_rate = cooling_rate
        self.min_temp = min_temp
        self.max_iterations = max_iterations

    def solve(self) -> Tuple[List[int], float, List[float], float]:
        """Execute Simulated Annealing search.

        Returns:
            Tuple[List[int], float, List[float], float]:
                (best_tour, best_cost_km, convergence_history, runtime_seconds)
        """
        start_time = time.perf_counter()

        current_tour = self.problem.random_solution(self.rng)
        current_cost = self.problem.route_length(current_tour)

        best_tour = list(current_tour)
        best_cost = current_cost
        history: List[float] = [best_cost]

        temp = self.initial_temp
        iteration = 0

        while iteration < self.max_iterations and temp > self.min_temp:
            iteration += 1

            # Sample a neighbor route using 2-opt move
            candidate_tour = self.problem.sample_neighbor(current_tour, self.rng, method="2-opt")
            candidate_cost = self.problem.route_length(candidate_tour)

            delta = candidate_cost - current_cost

            if delta < 0:
                # Improving move: always accept
                current_tour = candidate_tour
                current_cost = candidate_cost
                if current_cost < best_cost:
                    best_tour = list(current_tour)
                    best_cost = current_cost
            else:
                # Worsening move: accept with Boltzmann probability
                acceptance_prob = math.exp(-delta / max(temp, 1e-9))
                if self.rng.random() < acceptance_prob:
                    current_tour = candidate_tour
                    current_cost = candidate_cost

            # Record convergence trajectory
            history.append(best_cost)

            # Cool down
            temp *= self.cooling_rate

        runtime = time.perf_counter() - start_time
        logger.info(
            "[%s] Completed in %.4fs | Best Distance: %.2f km (Iterations: %d, Final T: %.4f)",
            self.name, runtime, best_cost, iteration, temp
        )
        return best_tour, best_cost, history, runtime


class GeneticSolver(MetaheuristicSolver):
    """Genetic Algorithm metaheuristic solver.

    Evolves a population of delivery route permutations using:
        - Tournament selection based on route fitness (1 / route_length)
        - Ordered Crossover (OX) to preserve permutation validity
        - Inversion mutation (2-opt sub-tour reversal)
        - Elitism to preserve the top individuals across generations
    """

    def __init__(
        self,
        problem: RouteProblem,
        population_size: int = 80,
        generations: int = 200,
        crossover_rate: float = 0.85,
        mutation_rate: float = 0.20,
        tournament_size: int = 5,
        elite_count: int = 2,
        seed: int = 42
    ):
        """Initialize GeneticSolver.

        Args:
            problem: RouteProblem instance.
            population_size: Number of individuals in the population.
            generations: Number of evolutionary generations.
            crossover_rate: Probability of recombining parent tours.
            mutation_rate: Probability of mutating an offspring.
            tournament_size: Tournament selection size.
            elite_count: Number of top individuals directly copied to next generation.
            seed: Random seed.
        """
        super().__init__(problem, seed=seed, name="Genetic Algorithm")
        self.population_size = population_size
        self.generations = generations
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate
        self.tournament_size = tournament_size
        self.elite_count = elite_count

    def _create_individual(self) -> List[int]:
        """Create a randomized delivery permutation (excluding depot)."""
        deliveries = [i for i in range(self.problem.num_stops) if i != self.problem.depot]
        self.rng.shuffle(deliveries)
        return deliveries

    def _ordered_crossover(self, parent1: List[int], parent2: List[int]) -> List[int]:
        """Perform Ordered Crossover (OX) between two permutation chromosomes.

        Preserves relative sequence without duplicate stops.

        Args:
            parent1: First parent stop list.
            parent2: Second parent stop list.

        Returns:
            List[int]: Offspring permutation.
        """
        size = len(parent1)
        if size <= 2:
            return list(parent1)

        idx1, idx2 = sorted(self.rng.sample(range(size), 2))

        # Copy slice from parent1
        child = [None] * size
        child[idx1:idx2 + 1] = parent1[idx1:idx2 + 1]
        copied_set = set(child[idx1:idx2 + 1])

        # Fill remaining spots from parent2 in cyclic order
        p2_idx = 0
        for i in range(size):
            if child[i] is None:
                while parent2[p2_idx] in copied_set:
                    p2_idx += 1
                child[i] = parent2[p2_idx]
                copied_set.add(parent2[p2_idx])
                p2_idx += 1

        return child  # type: ignore

    def _mutate(self, individual: List[int]) -> List[int]:
        """Apply inversion mutation (2-opt reversal of random segment)."""
        size = len(individual)
        if size <= 2:
            return list(individual)

        idx1, idx2 = sorted(self.rng.sample(range(size), 2))
        mutant = list(individual)
        mutant[idx1:idx2 + 1] = mutant[idx1:idx2 + 1][::-1]
        return mutant

    def solve(self) -> Tuple[List[int], float, List[float], float]:
        """Execute Genetic Algorithm evolution.

        Returns:
            Tuple[List[int], float, List[float], float]:
                (best_tour, best_cost_km, convergence_history, runtime_seconds)
        """
        start_time = time.perf_counter()

        # Initialize population
        population = [self._create_individual() for _ in range(self.population_size)]

        best_tour = self.problem.to_full_tour(population[0])
        best_cost = self.problem.route_length(best_tour)
        history: List[float] = [best_cost]

        for gen in range(self.generations):
            # Evaluate fitness of each individual
            scored = []
            for ind in population:
                full_t = self.problem.to_full_tour(ind)
                cost = self.problem.route_length(full_t)
                fit = 1.0 / (cost + 1e-9)
                scored.append((cost, fit, ind, full_t))
                if cost < best_cost:
                    best_cost = cost
                    best_tour = list(full_t)

            history.append(best_cost)

            # Sort population by cost ascending (lower cost = higher fitness)
            scored.sort(key=lambda item: item[0])

            # Elitism: retain top elite_count individuals
            new_population = [item[2] for item in scored[:self.elite_count]]

            # Tournament selection pool
            def tournament() -> List[int]:
                candidates = self.rng.sample(scored, min(self.tournament_size, len(scored)))
                candidates.sort(key=lambda c: c[0])
                return list(candidates[0][2])

            # Fill rest of population with offspring
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
        logger.info(
            "[%s] Completed in %.4fs | Best Distance: %.2f km (Generations: %d)",
            self.name, runtime, best_cost, self.generations
        )
        return best_tour, best_cost, history, runtime
