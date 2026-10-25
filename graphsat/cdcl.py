"""Conflict-Driven Clause Learning (CDCL) SAT solver.

A compact, pure-Python CDCL implementation intended for research and teaching.
It follows the standard MiniSat-style architecture:

* two-watched-literal (TWL) unit propagation,
* VSIDS variable activity with a lazy binary heap,
* first-UIP conflict analysis with non-chronological backjumping,
* phase saving (optionally seeded with external phase hints),
* Luby restarts and activity-based learned-clause deletion,
* optional DRUP proof logging so that UNSAT answers can be independently checked
  (see :mod:`graphsat.proof`).

References
----------
* J. Marques-Silva, K. Sakallah. "GRASP: A Search Algorithm for Propositional
  Satisfiability", IEEE Trans. Computers, 1999.
* N. Een, N. Sorensson. "An Extensible SAT-solver", SAT 2003.
* M. Luby, A. Sinclair, D. Zuckerman. "Optimal speedup of Las Vegas algorithms", 1993.
"""

from __future__ import annotations

import heapq
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

UNASSIGNED = -1
TRUE = 1
FALSE = 0

LUBY_UNIT = 100
"""Base restart interval in conflicts (multiplied by the Luby sequence)."""

MAX_LEARNED_MULT = 2
"""Learned-clause budget, as a multiple of the number of original clauses."""


@dataclass
class Clause:
    """A clause stored as a list of DIMACS literals."""

    lits: list[int]
    activity: float = 0.0
    is_learned: bool = False

    def __len__(self) -> int:
        return len(self.lits)


@dataclass
class SolveStats:
    """Search statistics collected during :meth:`CDCLSolver.solve`."""

    decisions: int = 0
    propagations: int = 0
    conflicts: int = 0
    restarts: int = 0
    learned_clauses: int = 0
    deleted_clauses: int = 0
    max_decision_level: int = 0
    solve_time_ms: float = 0.0

    def to_dict(self) -> dict[str, float]:
        """Return the statistics as a plain dictionary (JSON-serialisable)."""
        return {
            "decisions": self.decisions,
            "propagations": self.propagations,
            "conflicts": self.conflicts,
            "restarts": self.restarts,
            "learned_clauses": self.learned_clauses,
            "deleted_clauses": self.deleted_clauses,
            "max_decision_level": self.max_decision_level,
            "solve_time_ms": round(self.solve_time_ms, 3),
        }


@dataclass
class SolveResult:
    """Outcome of a CDCL run."""

    status: str
    """``"SAT"``, ``"UNSAT"`` or ``"UNKNOWN"`` (resource limit hit)."""
    model: list[int]
    """Signed literals (positive = True) for every variable when SAT, else empty."""
    stats: SolveStats
    proof: list[tuple[str, list[int]]] | None = field(default=None, repr=False)
    """DRUP proof steps ``("a"|"d", clause)`` when proof logging is enabled."""

    def is_sat(self) -> bool:
        """True iff the formula was proven satisfiable."""
        return self.status == "SAT"

    def is_unsat(self) -> bool:
        """True iff the formula was proven unsatisfiable."""
        return self.status == "UNSAT"

    def __repr__(self) -> str:
        return (
            f"SolveResult(status={self.status!r}, decisions={self.stats.decisions}, "
            f"conflicts={self.stats.conflicts}, learned={self.stats.learned_clauses})"
        )


def _luby(i: int) -> int:
    """Return the i-th (1-indexed) element of the Luby restart sequence."""
    if i < 1:
        raise ValueError("Luby sequence is 1-indexed")
    while True:
        k = 1
        while (1 << k) - 1 < i:
            k += 1
        if (1 << k) - 1 == i:
            return 1 << (k - 1)
        i -= (1 << (k - 1)) - 1


def _lit_index(lit: int) -> int:
    return 2 * abs(lit) + (1 if lit < 0 else 0)


class CDCLSolver:
    """MiniSat-style CDCL solver.

    Example::

        solver = CDCLSolver(num_vars=3, clauses=[[1, -2, 3], [-1, 2]])
        result = solver.solve()
        assert result.is_sat() and solver.verify(result.model)

    Args:
        num_vars: Number of variables (variables are ``1..num_vars``).
        clauses: Clauses as lists of non-zero DIMACS literals.
        vsids_decay: VSIDS decay factor in ``(0, 1)``.
        restart_luby_unit: Conflicts per Luby restart unit.
        max_learned_mult: Learned-clause budget relative to the original clause count.
        verbose: Emit per-restart progress at INFO level.
        phase_hints: Optional initial polarity per variable (index ``v - 1``);
            ``True`` means "try the positive literal first".
        proof: Record a DRUP proof (available as ``SolveResult.proof``).
    """

    def __init__(
        self,
        num_vars: int,
        clauses: Sequence[Sequence[int]],
        vsids_decay: float = 0.95,
        restart_luby_unit: int = LUBY_UNIT,
        max_learned_mult: float = MAX_LEARNED_MULT,
        verbose: bool = False,
        phase_hints: Sequence[bool] | None = None,
        proof: bool = False,
    ) -> None:
        if num_vars < 0:
            raise ValueError("num_vars must be non-negative")
        if not 0.0 < vsids_decay < 1.0:
            raise ValueError("vsids_decay must lie in (0, 1)")
        self.num_vars = num_vars
        self.vsids_decay = vsids_decay
        self.restart_luby_unit = max(1, int(restart_luby_unit))
        self.max_learned_mult = max_learned_mult
        self.verbose = verbose

        self.original_clauses: list[list[int]] = []
        for raw in clauses:
            lits = [int(x) for x in raw]
            for lit in lits:
                if lit == 0 or abs(lit) > num_vars:
                    raise ValueError(f"literal {lit} out of range for num_vars={num_vars}")
            self.original_clauses.append(lits)

        self.val: list[int] = [UNASSIGNED] * (num_vars + 1)
        self.level: list[int] = [-1] * (num_vars + 1)
        self.reason: list[int | None] = [None] * (num_vars + 1)
        self.phase: list[bool] = [False] * (num_vars + 1)
        if phase_hints is not None:
            if len(phase_hints) != num_vars:
                raise ValueError("phase_hints must have length num_vars")
            for v, p in enumerate(phase_hints, start=1):
                self.phase[v] = bool(p)

        self.trail: list[int] = []
        self.trail_lim: list[int] = []
        self._prop_head = 0

        self.clauses: list[Clause] = []
        self.watches: list[list[int]] = [[] for _ in range(2 * num_vars + 2)]
        self._trivially_unsat = False
        self._pending_units: list[int] = []
        for lits in self.original_clauses:
            simplified = list(dict.fromkeys(lits))  # dedupe, keep order
            if any(-lit in simplified for lit in simplified):
                continue  # tautology
            if not simplified:
                self._trivially_unsat = True
                continue
            self._add_clause(simplified, learned=False)
        self.n_original = len(self.clauses)

        self.activity: list[float] = [0.0] * (num_vars + 1)
        for c in self.clauses:
            for lit in c.lits:
                self.activity[abs(lit)] += 1.0
        self.bump_increment = 1.0
        self.clause_bump = 1.0
        self._heap: list[tuple[float, int]] = [(-self.activity[v], v) for v in range(1, num_vars + 1)]
        heapq.heapify(self._heap)

        self.stats = SolveStats()
        self._restart_idx = 1
        self._conflicts_since_restart = 0
        self._proof: list[tuple[str, list[int]]] | None = [] if proof else None

    # ------------------------------------------------------------------ clauses
    def _add_clause(self, lits: list[int], learned: bool) -> int:
        ci = len(self.clauses)
        self.clauses.append(Clause(lits=lits, activity=self.clause_bump if learned else 0.0, is_learned=learned))
        if len(lits) >= 2:
            self.watches[_lit_index(lits[0])].append(ci)
            self.watches[_lit_index(lits[1])].append(ci)
        elif not learned:
            self._pending_units.append(ci)
        return ci

    # --------------------------------------------------------------- assignment
    def _current_level(self) -> int:
        return len(self.trail_lim)

    def _lit_value(self, lit: int) -> int:
        v = self.val[abs(lit)]
        if v == UNASSIGNED:
            return UNASSIGNED
        return v if lit > 0 else 1 - v

    def _assign(self, lit: int, reason_clause: int | None) -> None:
        var = abs(lit)
        self.val[var] = TRUE if lit > 0 else FALSE
        self.level[var] = self._current_level()
        self.reason[var] = reason_clause
        self.trail.append(lit)

    # -------------------------------------------------------------- propagation
    def _propagate(self) -> int | None:
        """Two-watched-literal BCP. Returns a conflicting clause index or ``None``."""
        clauses = self.clauses
        while self._prop_head < len(self.trail):
            lit = self.trail[self._prop_head]
            self._prop_head += 1
            self.stats.propagations += 1
            false_lit = -lit
            ws = self.watches[_lit_index(false_lit)]
            i = j = 0
            n = len(ws)
            while i < n:
                ci = ws[i]
                i += 1
                lits = clauses[ci].lits
                if lits[0] == false_lit:
                    lits[0], lits[1] = lits[1], lits[0]
                first = lits[0]
                if self._lit_value(first) == TRUE:
                    ws[j] = ci
                    j += 1
                    continue
                moved = False
                for k in range(2, len(lits)):
                    if self._lit_value(lits[k]) != FALSE:
                        lits[1], lits[k] = lits[k], lits[1]
                        self.watches[_lit_index(lits[1])].append(ci)
                        moved = True
                        break
                if moved:
                    continue
                ws[j] = ci
                j += 1
                if self._lit_value(first) == FALSE:
                    while i < n:
                        ws[j] = ws[i]
                        j += 1
                        i += 1
                    del ws[j:]
                    self._prop_head = len(self.trail)
                    return ci
                self._assign(first, ci)
            del ws[j:]
        return None

    # ----------------------------------------------------------------- analysis
    def _bump_var(self, var: int) -> None:
        self.activity[var] += self.bump_increment
        if self.activity[var] > 1e100:
            for v in range(1, self.num_vars + 1):
                self.activity[v] *= 1e-100
            self.bump_increment *= 1e-100
            self._heap = [(-self.activity[v], v) for v in range(1, self.num_vars + 1) if self.val[v] == UNASSIGNED]
            heapq.heapify(self._heap)
        elif self.val[var] == UNASSIGNED:
            heapq.heappush(self._heap, (-self.activity[var], var))

    def _analyze(self, conflict_ci: int) -> tuple[list[int], int]:
        """First-UIP conflict analysis.

        Returns:
            ``(learned_clause, backjump_level)`` where ``learned_clause[0]`` is the
            asserting literal and ``learned_clause[1]`` (if any) has the highest
            decision level among the remaining literals.
        """
        cur = self._current_level()
        seen: set[int] = set()
        learned: list[int] = [0]
        counter = 0
        p: int | None = None
        idx = len(self.trail) - 1
        ci: int | None = conflict_ci
        while True:
            assert ci is not None
            clause = self.clauses[ci]
            if clause.is_learned:
                clause.activity += self.clause_bump
            for q in clause.lits:
                if p is not None and q == p:
                    continue
                v = abs(q)
                if v in seen or self.level[v] <= 0:
                    continue
                seen.add(v)
                self._bump_var(v)
                if self.level[v] == cur:
                    counter += 1
                else:
                    learned.append(q)
            while abs(self.trail[idx]) not in seen:
                idx -= 1
            p = self.trail[idx]
            idx -= 1
            seen.discard(abs(p))
            counter -= 1
            if counter == 0:
                break
            ci = self.reason[abs(p)]
        assert p is not None
        learned[0] = -p
        if len(learned) == 1:
            return learned, 0
        best = max(range(1, len(learned)), key=lambda k: self.level[abs(learned[k])])
        learned[1], learned[best] = learned[best], learned[1]
        return learned, self.level[abs(learned[1])]

    # ---------------------------------------------------------------- backjump
    def _backjump(self, level: int) -> None:
        """Undo every assignment made above decision ``level`` (phase saving)."""
        if self._current_level() <= level:
            return
        cut = self.trail_lim[level]
        for lit in self.trail[cut:]:
            var = abs(lit)
            self.phase[var] = lit > 0
            self.val[var] = UNASSIGNED
            self.level[var] = -1
            self.reason[var] = None
            heapq.heappush(self._heap, (-self.activity[var], var))
        del self.trail[cut:]
        del self.trail_lim[level:]
        self._prop_head = cut

    # ------------------------------------------------------------------- VSIDS
    def _decay_activities(self) -> None:
        self.bump_increment /= self.vsids_decay
        self.clause_bump /= 0.999

    def _pick_decision_var(self) -> int | None:
        """Pop the unassigned variable with the highest VSIDS activity."""
        while self._heap:
            neg_act, var = heapq.heappop(self._heap)
            if self.val[var] == UNASSIGNED and -neg_act == self.activity[var]:
                return var
        for var in range(1, self.num_vars + 1):  # safety net (stale heap)
            if self.val[var] == UNASSIGNED:
                return var
        return None

    # -------------------------------------------------------- clause database
    def _reduce_learned_db(self) -> None:
        """At decision level 0: drop satisfied clauses and the less active half of learned ones."""
        assert self._current_level() == 0
        learned = [i for i, c in enumerate(self.clauses) if c.is_learned]
        budget = self.n_original * self.max_learned_mult + 100
        drop: set[int] = set()
        if len(learned) > budget:
            learned.sort(key=lambda i: self.clauses[i].activity)
            drop.update(i for i in learned[: len(learned) // 2] if len(self.clauses[i].lits) > 2)
        new: list[Clause] = []
        for i, c in enumerate(self.clauses):
            if i in drop:
                if self._proof is not None:
                    self._proof.append(("d", list(c.lits)))
                self.stats.deleted_clauses += 1
                continue
            if c.is_learned and any(self._lit_value(lit) == TRUE for lit in c.lits):
                continue  # satisfied at level 0: redundant forever
            new.append(c)
        self.clauses = new
        self.watches = [[] for _ in range(2 * self.num_vars + 2)]
        for ci, c in enumerate(self.clauses):
            if len(c.lits) >= 2:
                c.lits.sort(key=lambda lit: self._lit_value(lit) == FALSE)
                self.watches[_lit_index(c.lits[0])].append(ci)
                self.watches[_lit_index(c.lits[1])].append(ci)
        for v in range(1, self.num_vars + 1):
            self.reason[v] = None  # only level-0 assignments remain; reasons unused

    # -------------------------------------------------------------- main loop
    def _finish(self, status: str, t0: float) -> SolveResult:
        self.stats.solve_time_ms = (time.perf_counter() - t0) * 1000.0
        model: list[int] = []
        if status == "SAT":
            model = [v if self.val[v] == TRUE else -v for v in range(1, self.num_vars + 1)]
        if status == "UNSAT" and self._proof is not None:
            self._proof.append(("a", []))
        return SolveResult(status=status, model=model, stats=self.stats, proof=self._proof)

    def solve(self, timeout_s: float = 30.0, max_conflicts: int | None = None) -> SolveResult:
        """Run CDCL search.

        Args:
            timeout_s: Wall-clock budget in seconds; ``UNKNOWN`` is returned if exceeded.
            max_conflicts: Optional conflict budget; ``UNKNOWN`` is returned if exceeded.

        Returns:
            A :class:`SolveResult`. SAT models are always checked against the
            original clauses before being returned.
        """
        t0 = time.perf_counter()
        if self._trivially_unsat:
            return self._finish("UNSAT", t0)
        for ci in self._pending_units:
            lit = self.clauses[ci].lits[0]
            value = self._lit_value(lit)
            if value == FALSE:
                return self._finish("UNSAT", t0)
            if value == UNASSIGNED:
                self._assign(lit, ci)
        self._pending_units.clear()
        if self._propagate() is not None:
            return self._finish("UNSAT", t0)

        next_restart = _luby(self._restart_idx) * self.restart_luby_unit
        while True:
            if time.perf_counter() - t0 > timeout_s:
                return self._finish("UNKNOWN", t0)
            if max_conflicts is not None and self.stats.conflicts >= max_conflicts:
                return self._finish("UNKNOWN", t0)

            var = self._pick_decision_var()
            if var is None:
                result = self._finish("SAT", t0)
                if not self.verify(result.model):  # pragma: no cover - internal invariant
                    raise RuntimeError("CDCL produced a model that violates the input formula")
                return result

            self.trail_lim.append(len(self.trail))
            self.stats.decisions += 1
            self.stats.max_decision_level = max(self.stats.max_decision_level, self._current_level())
            self._assign(var if self.phase[var] else -var, None)

            conflict = self._propagate()
            while conflict is not None:
                self.stats.conflicts += 1
                self._conflicts_since_restart += 1
                if self._current_level() == 0:
                    return self._finish("UNSAT", t0)
                learned, bj = self._analyze(conflict)
                self._decay_activities()
                self._backjump(bj)
                ci = self._add_clause(learned, learned=True)
                self.stats.learned_clauses += 1
                if self._proof is not None:
                    self._proof.append(("a", list(learned)))
                self._assign(learned[0], ci)
                conflict = self._propagate()

            if self._conflicts_since_restart >= next_restart:
                self.stats.restarts += 1
                self._conflicts_since_restart = 0
                self._restart_idx += 1
                next_restart = _luby(self._restart_idx) * self.restart_luby_unit
                self._backjump(0)
                self._reduce_learned_db()
                if self.verbose:
                    logger.info("restart %d: %s", self.stats.restarts, self.stats.to_dict())
                if self._propagate() is not None:
                    return self._finish("UNSAT", t0)

    def verify(self, model: Sequence[int]) -> bool:
        """Check that ``model`` (signed literals) satisfies every original clause."""
        assignment = {abs(lit): lit > 0 for lit in model}
        return all(any(assignment.get(abs(lit), False) == (lit > 0) for lit in c) for c in self.original_clauses)
