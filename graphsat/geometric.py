"""Continuous-relaxation heuristics exposed as per-variable preferences."""

from __future__ import annotations

from graphsat.relaxation import relax


def extract_relaxation_heuristics(
    num_vars: int, clauses: list[list[int]], steps: int = 300, seed: int | None = 0, coupling: float = 0.086
) -> list[float]:
    """Run only the relaxation and return ``theta_v in [0, 1]`` per variable.

    Values near 1 mean the relaxation prefers ``x_v = True``. These are heuristic
    scores, not probabilities.
    """
    return relax(num_vars, clauses, steps=steps, seed=seed, coupling=coupling).theta.tolist()
