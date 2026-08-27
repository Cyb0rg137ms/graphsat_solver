"""
phase_transition.py
===================
Phase-transition benchmarking for GraphSAT and CDCL solvers.

Sweeps the clause-to-variable ratio (alpha) from 3.5 to 5.5 across random
3-SAT instances, measuring:
  - SAT probability at each alpha
  - Mean solve time (ms)
  - Mean decision count
  - Mean conflict count (CDCL)

The "phase transition" — where SAT probability drops from ~1 to ~0 — occurs
near alpha ≈ 4.267 (empirical from Kirkpatrick & Selman, 1994).

Run:
    python -m graphsat.benchmarks.phase_transition
"""

from __future__ import annotations

import random
import statistics
import time
from typing import Dict, List, Tuple

from graphsat.cdcl import CDCLSolver
from graphsat.core import ManifoldConstraintSolver


def generate_random_3sat(n_vars: int, n_clauses: int, seed: int = 0) -> List[List[int]]:
    """Generates a random 3-SAT instance."""
    rng = random.Random(seed)
    clauses = []
    for _ in range(n_clauses):
        vars_ = rng.sample(range(1, n_vars + 1), 3)
        clause = [v if rng.random() > 0.5 else -v for v in vars_]
        clauses.append(clause)
    return clauses


def run_phase_transition(
    n_vars: int = 30,
    alpha_range: Tuple[float, float] = (3.0, 6.0),
    alpha_steps: int = 16,
    n_trials: int = 50,
    seed_base: int = 42,
    use_cdcl: bool = True,
) -> List[Dict]:
    """
    Runs the phase-transition sweep.

    Args:
        n_vars: Number of variables per instance.
        alpha_range: (min_ratio, max_ratio) clause-to-variable ratio sweep.
        alpha_steps: Number of alpha values to sample.
        n_trials: Instances per alpha value.
        seed_base: Random seed offset.
        use_cdcl: If True, use CDCLSolver; else use ManifoldConstraintSolver (DPLL).

    Returns:
        List of result dicts, one per alpha value.
    """
    step = (alpha_range[1] - alpha_range[0]) / (alpha_steps - 1)
    results = []

    for step_i in range(alpha_steps):
        alpha = alpha_range[0] + step_i * step
        n_clauses = int(n_vars * alpha)

        sat_count = 0
        times_ms: List[float] = []
        decisions: List[int] = []
        conflicts: List[int] = []

        for trial in range(n_trials):
            clauses = generate_random_3sat(n_vars, n_clauses, seed=seed_base + step_i * 1000 + trial)

            t0 = time.perf_counter()
            if use_cdcl:
                solver = CDCLSolver(n_vars, clauses)
                result = solver.solve(timeout_s=5.0)
                elapsed = (time.perf_counter() - t0) * 1000
                is_sat = result.is_sat()
                decisions.append(result.stats.decisions)
                conflicts.append(result.stats.conflicts)
            else:
                solver = ManifoldConstraintSolver(n_vars, clauses)
                status, _ = solver.solve()
                elapsed = (time.perf_counter() - t0) * 1000
                is_sat = status == "SAT"
                decisions.append(0)
                conflicts.append(0)

            times_ms.append(elapsed)
            if is_sat:
                sat_count += 1

        results.append({
            "alpha": round(alpha, 3),
            "n_vars": n_vars,
            "n_clauses": n_clauses,
            "sat_probability": sat_count / n_trials,
            "mean_time_ms": round(statistics.mean(times_ms), 3),
            "median_time_ms": round(statistics.median(times_ms), 3),
            "mean_decisions": round(statistics.mean(decisions), 1),
            "mean_conflicts": round(statistics.mean(conflicts), 1),
        })

    return results


def print_phase_table(results: List[Dict]) -> None:
    """Prints a formatted ASCII table of phase-transition results."""
    header = f"{'alpha':>7}  {'P(SAT)':>8}  {'mean_ms':>9}  {'mean_dec':>10}  {'mean_cfl':>10}"
    print("=" * len(header))
    print(f"  GraphSAT CDCL Phase Transition (n_vars={results[0]['n_vars']})")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['alpha']:>7.3f}  "
            f"{r['sat_probability']:>8.3f}  "
            f"{r['mean_time_ms']:>9.3f}  "
            f"{r['mean_decisions']:>10.1f}  "
            f"{r['mean_conflicts']:>10.1f}"
        )
    print("=" * len(header))


def run_solver_comparison(
    n_vars: int = 20,
    alpha: float = 4.27,
    n_trials: int = 20,
) -> Dict:
    """
    Compares CDCL vs. DPLL+Relaxation (ManifoldConstraintSolver) head-to-head.

    Returns a comparison dict with timing and correctness statistics.
    """
    n_clauses = int(n_vars * alpha)
    cdcl_times: List[float] = []
    dpll_times: List[float] = []
    mismatches = 0

    for trial in range(n_trials):
        clauses = generate_random_3sat(n_vars, n_clauses, seed=9999 + trial)

        # CDCL
        t0 = time.perf_counter()
        cdcl = CDCLSolver(n_vars, clauses)
        cdcl_result = cdcl.solve()
        cdcl_times.append((time.perf_counter() - t0) * 1000)

        # DPLL + Manifold
        t0 = time.perf_counter()
        dpll = ManifoldConstraintSolver(n_vars, clauses)
        dpll_status, _ = dpll.solve()
        dpll_times.append((time.perf_counter() - t0) * 1000)

        if cdcl_result.status != dpll_status:
            mismatches += 1

    return {
        "n_vars": n_vars,
        "alpha": alpha,
        "n_trials": n_trials,
        "cdcl_mean_ms": round(statistics.mean(cdcl_times), 3),
        "dpll_mean_ms": round(statistics.mean(dpll_times), 3),
        "cdcl_median_ms": round(statistics.median(cdcl_times), 3),
        "dpll_median_ms": round(statistics.median(dpll_times), 3),
        "status_mismatches": mismatches,
        "agreement_rate": round((n_trials - mismatches) / n_trials, 3),
    }


if __name__ == "__main__":
    print("\n=== Phase Transition Sweep (CDCL, n=30) ===\n")
    results = run_phase_transition(n_vars=30, n_trials=30)
    print_phase_table(results)

    print("\n=== CDCL vs. DPLL+Manifold Head-to-Head (n=20, alpha=4.27) ===\n")
    cmp = run_solver_comparison(n_vars=20, alpha=4.27, n_trials=20)
    print(f"  CDCL mean:  {cmp['cdcl_mean_ms']:.3f} ms")
    print(f"  DPLL mean:  {cmp['dpll_mean_ms']:.3f} ms")
    print(f"  Agreement:  {cmp['agreement_rate'] * 100:.1f}%")
    print(f"  Mismatches: {cmp['status_mismatches']}")
