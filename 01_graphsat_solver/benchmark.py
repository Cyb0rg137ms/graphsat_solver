"""
benchmark.py
============
Benchmarking script for GraphSAT. Generates random 3-SAT instances
to measure topological relaxation and search scaling characteristics.
"""

import time
import random
from typing import List, Tuple
from graphsat.core import ManifoldConstraintSolver

def generate_random_3sat(num_vars: int, num_clauses: int) -> List[List[int]]:
    """Generates a random 3-SAT clause list."""
    clauses = []
    for _ in range(num_clauses):
        # Pick 3 unique variables
        vars_selected = random.sample(range(1, num_vars + 1), 3)
        # Randomly negate literals
        clause = [v if random.random() > 0.5 else -v for v in vars_selected]
        clauses.append(clause)
    return clauses

def run_benchmark_suite(num_tests: int = 5, num_vars: int = 15, clause_ratio: float = 4.2):
    """Runs a series of random 3-SAT instances and logs solve metrics."""
    num_clauses = int(num_vars * clause_ratio)
    print(f"==================================================")
    print(f" GraphSAT Benchmark: {num_vars} Vars, {num_clauses} Clauses")
    print(f"==================================================")
    
    total_time = 0.0
    solved_count = 0
    sat_count = 0
    unsat_count = 0
    
    for i in range(num_tests):
        clauses = generate_random_3sat(num_vars, num_clauses)
        solver = ManifoldConstraintSolver(num_vars, clauses)
        
        t0 = time.perf_counter()
        status, result = solver.solve()
        t1 = time.perf_counter()
        
        elapsed = (t1 - t0) * 1000.0
        total_time += elapsed
        
        if status == "SAT":
            sat_count += 1
            is_valid = solver.verify(result)
            verif_str = "Verified Valid" if is_valid else "Verification Failed"
            print(f"Test {i+1:02d}: SAT   ({elapsed:6.2f} ms) | {verif_str}")
            if is_valid:
                solved_count += 1
        else:
            unsat_count += 1
            print(f"Test {i+1:02d}: UNSAT ({elapsed:6.2f} ms) | Mass Gap: {result:.4f}")
            solved_count += 1
            
    avg_time = total_time / num_tests
    print(f"--------------------------------------------------")
    print(f"Benchmark Complete:")
    print(f"  Total Run Time: {total_time:.2f} ms")
    print(f"  Average Solve Time: {avg_time:.2f} ms")
    print(f"  Solvers Consistency: {solved_count}/{num_tests} Successful")
    print(f"  Distribution: {sat_count} SAT, {unsat_count} UNSAT")
    print(f"==================================================")

if __name__ == "__main__":
    # Seed for reproducibility
    random.seed(42)
    run_benchmark_suite(num_tests=5, num_vars=20, clause_ratio=4.3)
