"""Vectorised continuous relaxation of SAT (NumPy).

Each Boolean variable ``x_v`` is relaxed to ``theta_v in [0, 1]`` and we minimise
the clause-violation energy ``E(theta) = sum_C prod_{l in C} f_l(theta)`` (see
:mod:`graphsat.bounds`) with projected gradient descent.

The optional *prime-spaced coupling* term is the project's original heuristic:
variable ``i`` gets coordinate ``p_i`` (the i-th prime) and a pairwise potential
``eps / |p_i - p_j| * sin(pi * (theta_i - theta_j))`` is added to the gradient, with
per-variable step size scaled by ``1 / ln(p_i)``. It has no theoretical guarantee;
it is kept as an ablatable knob (``coupling=0`` disables it) so its effect can be
measured (see ``benchmarks/``).

The relaxation is used only as a *heuristic*: its rounded point is checked
exactly, and otherwise its coordinates seed the phases of the complete CDCL search.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


def first_primes(n: int) -> NDArray[np.int64]:
    """Return the first ``n`` primes (sieve of Eratosthenes)."""
    if n <= 0:
        return np.zeros(0, dtype=np.int64)
    limit = max(15, int(n * (np.log(n + 1) + np.log(np.log(n + 2)) + 3)))
    while True:
        sieve = np.ones(limit + 1, dtype=bool)
        sieve[:2] = False
        for p in range(2, int(limit**0.5) + 1):
            if sieve[p]:
                sieve[p * p :: p] = False
        primes = np.flatnonzero(sieve)
        if len(primes) >= n:
            return primes[:n].astype(np.int64)
        limit *= 2


@dataclass
class ClauseTensor:
    """Padded tensor view of a CNF: ``var[m, k]``, ``pos[m, k]``, ``mask[m, k]``."""

    var: NDArray[np.int64]
    pos: NDArray[np.bool_]
    mask: NDArray[np.bool_]
    num_vars: int

    @classmethod
    def from_clauses(cls, num_vars: int, clauses: Sequence[Sequence[int]]) -> ClauseTensor:
        """Pack clauses into padded arrays (padding entries are masked out)."""
        m = len(clauses)
        k = max((len(c) for c in clauses), default=1) or 1
        var = np.zeros((m, k), dtype=np.int64)
        pos = np.zeros((m, k), dtype=bool)
        mask = np.zeros((m, k), dtype=bool)
        for i, c in enumerate(clauses):
            for j, lit in enumerate(c):
                var[i, j] = abs(lit) - 1
                pos[i, j] = lit > 0
                mask[i, j] = True
        return cls(var=var, pos=pos, mask=mask, num_vars=num_vars)

    def falseness(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """``f_l`` per literal slot (1 for padding so products are unaffected)."""
        t = theta[self.var]
        f = np.where(self.pos, 1.0 - t, t)
        return np.where(self.mask, f, 1.0)

    def energy(self, theta: NDArray[np.float64]) -> float:
        """Relaxed energy; equals the number of violated clauses at 0/1 points."""
        if self.var.shape[0] == 0:
            return 0.0
        return float(self.falseness(theta).prod(axis=1).sum())

    def gradient(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Exact gradient of :meth:`energy` (leave-one-out products, no division)."""
        grad = np.zeros(self.num_vars)
        if self.var.shape[0] == 0:
            return grad
        f = self.falseness(theta)
        k = f.shape[1]
        for j in range(k):
            others = np.prod(np.delete(f, j, axis=1), axis=1) if k > 1 else np.ones(f.shape[0])
            d = np.where(self.pos[:, j], -1.0, 1.0) * others * self.mask[:, j]
            np.add.at(grad, self.var[:, j], d)
        return grad


@dataclass
class RelaxationResult:
    """Outcome of :func:`relax`."""

    theta: NDArray[np.float64]
    energy_history: list[float]
    rounded: list[int]
    rounded_violations: int


def relax(
    num_vars: int,
    clauses: Sequence[Sequence[int]],
    steps: int = 300,
    lr: float = 0.1,
    coupling: float = 0.086,
    seed: int | None = 0,
    init_noise: float = 0.01,
    tol: float = 1e-4,
) -> RelaxationResult:
    """Projected gradient descent on the relaxed energy.

    Args:
        num_vars: Number of variables.
        clauses: DIMACS clauses.
        steps: Maximum gradient steps.
        lr: Step size.
        coupling: Strength of the prime-spaced coupling heuristic (0 disables).
        seed: RNG seed for the initial perturbation around 0.5.
        init_noise: Half-width of the uniform initial perturbation.
        tol: Stop once the relaxed energy drops below this value.
    """
    rng = np.random.default_rng(seed)
    theta = 0.5 + rng.uniform(-init_noise, init_noise, size=num_vars)
    ct = ClauseTensor.from_clauses(num_vars, clauses)
    primes = first_primes(num_vars).astype(np.float64)
    scale = 1.0 / np.log(np.maximum(primes, 2.0)) if num_vars else np.zeros(0)
    inv_dist: NDArray[np.float64] | None = None
    if coupling > 0 and num_vars > 1:
        dist = np.abs(primes[:, None] - primes[None, :])
        np.fill_diagonal(dist, np.inf)
        inv_dist = coupling / dist
    history: list[float] = []
    for _ in range(steps):
        e = ct.energy(theta)
        history.append(e)
        if e < tol:
            break
        g = ct.gradient(theta)
        if inv_dist is not None:
            g += (inv_dist * np.sin(np.pi * (theta[:, None] - theta[None, :]))).sum(axis=1)
        theta = np.clip(theta - lr * g * scale, 0.0, 1.0)
    rounded = (theta > 0.5).astype(int).tolist()
    violations = round(ct.energy(np.asarray(rounded, dtype=float)))
    return RelaxationResult(theta=theta, energy_history=history, rounded=rounded, rounded_violations=violations)
