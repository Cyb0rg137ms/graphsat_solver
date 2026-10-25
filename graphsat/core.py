"""Hybrid relaxation + CDCL solver with verified answers.

Pipeline (see ``docs/ARCHITECTURE.md``):

1. **Lower-bound pre-check** (:mod:`graphsat.bounds`): if the sound polynomial
   lower bound on the number of violated clauses is positive, answer UNSAT.
2. **Continuous relaxation** (:mod:`graphsat.relaxation`): projected gradient
   descent; if the rounded point satisfies the formula, answer SAT.
3. **Complete CDCL search** (:mod:`graphsat.cdcl`) whose initial phases come from
   the relaxation.
4. **Verification**: SAT models are always re-checked against the input clauses;
   with ``certify=True`` UNSAT answers carry a DRUP proof that is checked by
   :func:`graphsat.proof.check_drup`.

Nothing here changes the worst-case complexity of SAT; the relaxation is a
heuristic and completeness comes from CDCL.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from graphsat.bounds import energy_lower_bound
from graphsat.cdcl import CDCLSolver, SolveStats
from graphsat.cnf import CNF
from graphsat.config import SolverConfig
from graphsat.proof import check_drup
from graphsat.relaxation import first_primes, relax

logger = logging.getLogger(__name__)


@dataclass
class HybridResult:
    """Result of :meth:`HybridSolver.solve`."""

    status: str
    assignment: list[int] = field(default_factory=list)
    """0/1 value per variable (index ``v - 1``) when SAT."""
    decided_by: str = ""
    """Which stage produced the answer: ``lower_bound``, ``relaxation`` or ``cdcl``."""
    lower_bound: float | None = None
    relax_violations: int | None = None
    cdcl_stats: SolveStats | None = None
    certified: bool = False
    """SAT: model verified. UNSAT: lower bound > 0 or DRUP proof checked."""
    timings_ms: dict[str, float] = field(default_factory=dict)
    proof: list[tuple[str, list[int]]] | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, object]:
        """JSON-friendly summary."""
        return {
            "status": self.status,
            "decided_by": self.decided_by,
            "certified": self.certified,
            "lower_bound": self.lower_bound,
            "relax_violations": self.relax_violations,
            "cdcl_stats": self.cdcl_stats.to_dict() if self.cdcl_stats else None,
            "timings_ms": {k: round(v, 3) for k, v in self.timings_ms.items()},
        }


class HybridSolver:
    """Relaxation-guided, complete SAT solver."""

    def __init__(self, cnf: CNF, config: SolverConfig | None = None) -> None:
        self.cnf = cnf
        self.config = config or SolverConfig()

    def solve(self) -> HybridResult:
        """Run the pipeline and return a :class:`HybridResult`."""
        cfg, cnf = self.config, self.cnf
        res = HybridResult(status="UNKNOWN")
        if any(len(c) == 0 for c in cnf.clauses):
            res.status, res.decided_by, res.certified = "UNSAT", "input", True
            return res

        if cfg.use_lower_bound:
            t = time.perf_counter()
            res.lower_bound = energy_lower_bound(cnf.clauses)
            res.timings_ms["lower_bound"] = (time.perf_counter() - t) * 1e3
            if res.lower_bound > 1e-9:
                res.status, res.decided_by, res.certified = "UNSAT", "lower_bound", True
                return res

        hints: list[bool] | None = None
        if cfg.relax_steps > 0 and cnf.num_vars > 0:
            t = time.perf_counter()
            rr = relax(
                cnf.num_vars, cnf.clauses, steps=cfg.relax_steps, lr=cfg.lr, coupling=cfg.coupling, seed=cfg.seed
            )
            res.timings_ms["relaxation"] = (time.perf_counter() - t) * 1e3
            res.relax_violations = rr.rounded_violations
            if rr.rounded_violations == 0 and cnf.evaluate(rr.rounded):
                res.status, res.assignment, res.decided_by, res.certified = "SAT", rr.rounded, "relaxation", True
                return res
            if cfg.use_phase_hints:
                hints = [bool(b) for b in rr.rounded]

        t = time.perf_counter()
        solver = CDCLSolver(cnf.num_vars, cnf.clauses, phase_hints=hints, proof=cfg.certify)
        out = solver.solve(timeout_s=cfg.timeout_s, max_conflicts=cfg.max_conflicts)
        res.timings_ms["cdcl"] = (time.perf_counter() - t) * 1e3
        res.cdcl_stats, res.decided_by, res.status = out.stats, "cdcl", out.status
        if out.is_sat():
            res.assignment = [1 if lit > 0 else 0 for lit in out.model]
            res.certified = cnf.evaluate(res.assignment)
        elif out.is_unsat() and cfg.certify:
            t = time.perf_counter()
            res.proof = out.proof
            res.certified = check_drup(cnf.clauses, out.proof or [])
            res.timings_ms["proof_check"] = (time.perf_counter() - t) * 1e3
        return res


def solve(
    clauses: Sequence[Sequence[int]] | CNF, num_vars: int | None = None, config: SolverConfig | None = None
) -> HybridResult:
    """Convenience entry point: ``solve([[1, -2], [2]])``."""
    cnf = clauses if isinstance(clauses, CNF) else CNF.from_clauses(clauses, num_vars)
    return HybridSolver(cnf, config).solve()


class PrimeSequence:
    """Deterministic prime generator (kept for backward compatibility)."""

    def __init__(self) -> None:
        self._primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]

    def get_nth_prime(self, n: int) -> int:
        """Return the n-th prime (1-indexed)."""
        if n < 1:
            raise ValueError("n must be >= 1")
        if n > len(self._primes):
            self._primes = [int(p) for p in first_primes(n)]
        return self._primes[n - 1]


class ManifoldConstraintSolver:
    """Original public API, now backed by :class:`HybridSolver`.

    ``solve()`` returns ``("SAT", assignment01)`` or ``("UNSAT", bound)`` where
    ``bound`` is the positive lower bound when the pre-check fired, else ``-1.0``.
    ``("UNKNOWN", -1.0)`` is returned only if the CDCL time budget is exhausted.
    """

    def __init__(
        self,
        num_vars: int,
        clauses: list[list[int]],
        coupling_strength: float = 0.086,
        seed: int | None = 0,
        timeout_s: float = 60.0,
    ) -> None:
        self.num_vars = num_vars
        self.clauses = clauses
        self.coupling = coupling_strength
        self.seed = seed
        self.timeout_s = timeout_s
        self.prime_coordinates = [int(p) for p in first_primes(num_vars)]
        self.coords: list[float] = [0.5] * num_vars
        self.last_result: HybridResult | None = None

    def _evaluate_penalty(self, coords: Sequence[float], clause: Sequence[int]) -> float:
        """Relaxed violation of one clause at ``coords``."""
        p = 1.0
        for lit in clause:
            x = coords[abs(lit) - 1]
            p *= (1.0 - x) if lit > 0 else x
        return p

    def compute_algebraic_lower_bound(self) -> float:
        """Sound lower bound on the number of violated clauses (see :mod:`graphsat.bounds`)."""
        return energy_lower_bound(self.clauses)

    def solve(self, max_steps: int = 500, lr: float = 0.1) -> tuple[str, float | list[int]]:
        """Solve; see class docstring for the return convention."""
        cfg = SolverConfig(
            relax_steps=max_steps, lr=lr, coupling=self.coupling, seed=self.seed, timeout_s=self.timeout_s
        )
        cnf = CNF(num_vars=self.num_vars, clauses=[list(c) for c in self.clauses])
        if max_steps > 0 and self.num_vars > 0:
            rr = relax(self.num_vars, self.clauses, steps=max_steps, lr=lr, coupling=self.coupling, seed=self.seed)
            self.coords = rr.theta.tolist()
        result = HybridSolver(cnf, cfg).solve()
        self.last_result = result
        if result.status == "SAT":
            return "SAT", result.assignment
        if result.status == "UNSAT":
            return "UNSAT", result.lower_bound if result.decided_by == "lower_bound" and result.lower_bound else -1.0
        return "UNKNOWN", -1.0

    def verify(self, assignment: Sequence[int]) -> bool:
        """Check a 0/1 assignment against all clauses."""
        return all(any(assignment[abs(lit) - 1] == (1 if lit > 0 else 0) for lit in c) for c in self.clauses)
