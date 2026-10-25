"""Random 3-SAT phase-transition sweep and solver comparisons.

Run ``python -m graphsat.benchmarks.phase_transition`` (or ``graphsat bench``).
All instances are generated from fixed seeds, so results are reproducible up to
machine speed.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time

from graphsat.cdcl import CDCLSolver
from graphsat.config import SolverConfig
from graphsat.core import HybridSolver
from graphsat.generators import random_ksat


def generate_random_3sat(n_vars: int, n_clauses: int, seed: int = 0) -> list[list[int]]:
    """Random 3-SAT clauses (kept for backward compatibility)."""
    return random_ksat(n_vars, n_clauses, 3, seed).clauses


def run_phase_transition(
    n_vars: int = 30,
    alpha_range: tuple[float, float] = (3.0, 6.0),
    alpha_steps: int = 7,
    n_trials: int = 20,
    seed_base: int = 42,
    use_cdcl: bool = True,
) -> list[dict[str, float]]:
    """Sweep the clause/variable ratio; return one row of statistics per alpha.

    ``use_cdcl=True`` runs plain CDCL; otherwise the full hybrid pipeline.
    """
    step = (alpha_range[1] - alpha_range[0]) / max(1, alpha_steps - 1)
    rows = []
    for si in range(alpha_steps):
        alpha = alpha_range[0] + si * step
        m = round(n_vars * alpha)
        sat = 0
        times, decs, cfls = [], [], []
        for t in range(n_trials):
            cnf = random_ksat(n_vars, m, 3, seed=seed_base + si * 1000 + t)
            t0 = time.perf_counter()
            if use_cdcl:
                r = CDCLSolver(n_vars, cnf.clauses).solve(timeout_s=30)
                ok, d, c = r.is_sat(), r.stats.decisions, r.stats.conflicts
            else:
                h = HybridSolver(cnf, SolverConfig(timeout_s=30)).solve()
                ok = h.status == "SAT"
                d = h.cdcl_stats.decisions if h.cdcl_stats else 0
                c = h.cdcl_stats.conflicts if h.cdcl_stats else 0
            times.append((time.perf_counter() - t0) * 1e3)
            sat += ok
            decs.append(d)
            cfls.append(c)
        rows.append(
            {
                "alpha": round(alpha, 3),
                "n_vars": n_vars,
                "n_clauses": m,
                "sat_probability": sat / n_trials,
                "mean_time_ms": round(statistics.mean(times), 3),
                "median_time_ms": round(statistics.median(times), 3),
                "mean_decisions": round(statistics.mean(decs), 1),
                "mean_conflicts": round(statistics.mean(cfls), 1),
            }
        )
    return rows


def print_phase_table(rows: list[dict[str, float]]) -> None:
    """Print rows as a Markdown table."""
    print(f"| alpha | m | P(SAT) | mean ms | median ms | mean decisions | mean conflicts |  (n={rows[0]['n_vars']})")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['alpha']:.2f} | {r['n_clauses']} | {r['sat_probability']:.2f} | {r['mean_time_ms']:.2f} | "
            f"{r['median_time_ms']:.2f} | {r['mean_decisions']:.1f} | {r['mean_conflicts']:.1f} |"
        )


def run_solver_comparison(n_vars: int = 50, alpha: float = 4.26, n_trials: int = 20, seed_base: int = 7) -> dict:
    """Ablation at fixed alpha: CDCL vs hybrid (with/without prime coupling)."""
    variants = {
        "cdcl": None,
        "hybrid_coupling": SolverConfig(coupling=0.086),
        "hybrid_no_coupling": SolverConfig(coupling=0.0),
        "hybrid_no_hints": SolverConfig(use_phase_hints=False),
    }
    out: dict[str, dict[str, float]] = {}
    m = round(alpha * n_vars)
    instances = [random_ksat(n_vars, m, 3, seed=seed_base + t) for t in range(n_trials)]
    statuses: dict[str, list[str]] = {}
    for name, cfg in variants.items():
        times, cfls, st = [], [], []
        for cnf in instances:
            t0 = time.perf_counter()
            if cfg is None:
                r = CDCLSolver(n_vars, cnf.clauses).solve(timeout_s=60)
                status, c = r.status, r.stats.conflicts
            else:
                h = HybridSolver(cnf, cfg).solve()
                status, c = h.status, (h.cdcl_stats.conflicts if h.cdcl_stats else 0)
            times.append((time.perf_counter() - t0) * 1e3)
            cfls.append(c)
            st.append(status)
        statuses[name] = st
        out[name] = {
            "mean_ms": round(statistics.mean(times), 2),
            "median_ms": round(statistics.median(times), 2),
            "mean_conflicts": round(statistics.mean(cfls), 1),
            "n_sat": st.count("SAT"),
        }
    ref = statuses["cdcl"]
    out["_agreement"] = {k: float(all(a == b for a, b in zip(v, ref, strict=True))) for k, v in statuses.items()}
    return out


def main() -> None:
    """CLI for the benchmark module."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--compare", action="store_true")
    a = ap.parse_args()
    print(f"python {platform.python_version()} on {platform.machine()}")
    print_phase_table(run_phase_transition(n_vars=a.n, n_trials=a.trials))
    if a.compare:
        print(json.dumps(run_solver_comparison(), indent=2))


if __name__ == "__main__":
    main()
