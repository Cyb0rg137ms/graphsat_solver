"""
cdcl.py
=======
Conflict-Driven Clause Learning (CDCL) SAT Solver.

Implements the full modern CDCL algorithm as described in:
  - "Conflict-Driven Clause Learning SAT Solvers" (Biere et al., Handbook of SAT, 2009)
  - "GRASP: A Search Algorithm for Propositional Satisfiability" (Marques-Silva & Sakallah, 1999)

Key features:
  - Two-Watched Literal (TWL) unit propagation  — O(1) amortized per assignment
  - VSIDS (Variable State Independent Decaying Sum) decision heuristic
  - 1-UIP conflict analysis via implication graph traversal (index-based, no trail mutation)
  - Non-chronological backjumping to the asserting level
  - Luby sequence restart policy with clause-database compaction
  - Clause activity decay for learned clause management
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
UNASSIGNED = -1
TRUE = 1
FALSE = 0

LUBY_UNIT = 100       # Base restart interval (conflicts)
MAX_LEARNED_MULT = 2  # Learned clause DB: keep at most n_orig * mult


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Clause:
    """Represents a SAT clause as a list of literals (DIMACS convention)."""
    lits: List[int]
    activity: float = 0.0
    is_learned: bool = False

    def __len__(self) -> int:
        return len(self.lits)


@dataclass
class SolveStats:
    """Tracks solver performance metrics."""
    decisions: int = 0
    propagations: int = 0
    conflicts: int = 0
    restarts: int = 0
    learned_clauses: int = 0
    max_decision_level: int = 0
    solve_time_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "decisions": self.decisions,
            "propagations": self.propagations,
            "conflicts": self.conflicts,
            "restarts": self.restarts,
            "learned_clauses": self.learned_clauses,
            "max_decision_level": self.max_decision_level,
            "solve_time_ms": round(self.solve_time_ms, 3),
        }


@dataclass
class SolveResult:
    """Result returned by CDCLSolver.solve()."""
    status: str           # "SAT", "UNSAT", or "UNKNOWN"
    model: List[int]      # Signed literals (positive = TRUE), empty if UNSAT/UNKNOWN
    stats: SolveStats

    def is_sat(self) -> bool:
        return self.status == "SAT"

    def is_unsat(self) -> bool:
        return self.status == "UNSAT"

    def __repr__(self) -> str:
        return (
            f"SolveResult(status={self.status!r}, "
            f"decisions={self.stats.decisions}, "
            f"conflicts={self.stats.conflicts}, "
            f"learned={self.stats.learned_clauses})"
        )


# ---------------------------------------------------------------------------
# Luby restart sequence
# ---------------------------------------------------------------------------

def _luby(i: int) -> int:
    """Returns the i-th element (1-indexed) of the Luby sequence."""
    k = 1
    while k < i + 1:
        k <<= 1
    if k == i + 1:
        return k >> 1
    return _luby(i - (k >> 1) + 1)


# ---------------------------------------------------------------------------
# CDCL Solver
# ---------------------------------------------------------------------------

class CDCLSolver:
    """
    Modern CDCL SAT solver with TWL propagation and VSIDS heuristics.

    Usage::

        solver = CDCLSolver(num_vars=10, clauses=[[1, -2, 3], [-1, 2]])
        result = solver.solve()
        print(result.status)   # "SAT" or "UNSAT"
        print(result.stats)    # SolveStats object
    """

    def __init__(
        self,
        num_vars: int,
        clauses: List[List[int]],
        vsids_decay: float = 0.95,
        restart_luby_unit: int = LUBY_UNIT,
        max_learned_mult: float = MAX_LEARNED_MULT,
        verbose: bool = False,
    ) -> None:
        self.num_vars = num_vars
        self.vsids_decay = vsids_decay
        self.restart_luby_unit = restart_luby_unit
        self.max_learned_mult = max_learned_mult
        self.verbose = verbose

        # --- Variable state (indexed 1..num_vars) ---
        self.val: List[int] = [UNASSIGNED] * (num_vars + 1)
        self.level: List[int] = [-1] * (num_vars + 1)
        self.reason: List[Optional[int]] = [None] * (num_vars + 1)

        # --- Assignment trail ---
        self.trail: List[int] = []          # ordered assigned literals
        self.trail_lim: List[int] = []      # trail[trail_lim[d]] = first lit at level d+1

        # --- Clause database ---
        self.clauses: List[Clause] = []
        for raw in clauses:
            self.clauses.append(Clause(lits=list(raw)))
        self.n_original = len(self.clauses)

        # --- Two-Watched Literals ---
        # watch[var][polarity] = list of clause indices
        # polarity: 0 = positive literal watched, 1 = negative literal watched
        self.watch: List[List[List[int]]] = [
            [[], []] for _ in range(num_vars + 1)
        ]
        self._init_watches()

        # --- VSIDS heuristic ---
        self.activity: List[float] = [0.0] * (num_vars + 1)
        self.bump_increment: float = 1.0
        for c in self.clauses:
            for lit in c.lits:
                self.activity[abs(lit)] += 1.0

        # --- Propagation queue pointer ---
        self._prop_head: int = 0

        # --- Stats ---
        self.stats = SolveStats()

        # --- Restart state ---
        self._restart_idx: int = 1
        self._conflicts_since_restart: int = 0

    # ------------------------------------------------------------------
    # Watch list helpers
    # ------------------------------------------------------------------

    def _watch_var_pol(self, lit: int) -> Tuple[int, int]:
        """Returns (var, polarity) for the watch list index of a literal."""
        var = abs(lit)
        pol = 0 if lit > 0 else 1
        return var, pol

    def _add_watch(self, lit: int, ci: int) -> None:
        var, pol = self._watch_var_pol(lit)
        self.watch[var][pol].append(ci)

    def _remove_watch(self, lit: int, ci: int) -> None:
        var, pol = self._watch_var_pol(lit)
        try:
            self.watch[var][pol].remove(ci)
        except ValueError:
            pass

    def _get_watches(self, lit: int) -> List[int]:
        """Returns watch list for the given literal."""
        var, pol = self._watch_var_pol(lit)
        return self.watch[var][pol]

    def _init_watches(self) -> None:
        """Set up two-watched literals for every clause."""
        for ci, clause in enumerate(self.clauses):
            if len(clause.lits) >= 2:
                self._add_watch(clause.lits[0], ci)
                self._add_watch(clause.lits[1], ci)

    # ------------------------------------------------------------------
    # Assignment management
    # ------------------------------------------------------------------

    def _assign(self, lit: int, reason_clause: Optional[int]) -> None:
        var = abs(lit)
        self.val[var] = TRUE if lit > 0 else FALSE
        self.level[var] = self._current_level()
        self.reason[var] = reason_clause
        self.trail.append(lit)

    def _current_level(self) -> int:
        return len(self.trail_lim)

    def _lit_value(self, lit: int) -> int:
        var = abs(lit)
        v = self.val[var]
        if v == UNASSIGNED:
            return UNASSIGNED
        if lit > 0:
            return TRUE if v == TRUE else FALSE
        else:
            return TRUE if v == FALSE else FALSE

    # ------------------------------------------------------------------
    # Two-Watched Literal Propagation
    # ------------------------------------------------------------------

    def _propagate(self) -> Optional[int]:
        """
        BCP using Two-Watched Literals.
        Returns conflicting clause index or None.
        """
        while self._prop_head < len(self.trail):
            lit = self.trail[self._prop_head]
            self._prop_head += 1
            self.stats.propagations += 1

            # The literal `lit` is now TRUE. Any clause watching `¬lit` may be unit/conflict.
            neg_lit = -lit
            var, pol = self._watch_var_pol(neg_lit)
            watches = self.watch[var][pol]

            i = 0
            while i < len(watches):
                ci = watches[i]
                clause = self.clauses[ci]
                lits = clause.lits

                # Make sure neg_lit is at position 1 (the "false watch" position)
                if lits[0] == neg_lit:
                    lits[0], lits[1] = lits[1], lits[0]

                # If the other watch (lits[0]) is already TRUE, clause satisfied
                if self._lit_value(lits[0]) == TRUE:
                    i += 1
                    continue

                # Try to find a new watch from position 2 onwards
                found = False
                for k in range(2, len(lits)):
                    if self._lit_value(lits[k]) != FALSE:
                        # Replace lits[1] with lits[k]
                        lits[1], lits[k] = lits[k], lits[1]
                        # Move watch from neg_lit to new lits[1]
                        watches.pop(i)
                        self._add_watch(lits[1], ci)
                        found = True
                        break

                if not found:
                    i += 1
                    val0 = self._lit_value(lits[0])
                    if val0 == UNASSIGNED:
                        # Unit: force lits[0]
                        self._assign(lits[0], ci)
                    else:
                        # Conflict
                        return ci

        return None

    # ------------------------------------------------------------------
    # Conflict Analysis — 1-UIP (index-based, NO trail mutation)
    # ------------------------------------------------------------------

    def _analyze(self, conflict_ci: int) -> Tuple[List[int], int]:
        """
        1-UIP conflict analysis using a trail index traversal.
        Does NOT modify self.trail.

        Returns:
            (learned_lits, backjump_level)
        """
        seen: Set[int] = set()
        learned: List[int] = []
        counter = 0
        cur_level = self._current_level()

        # Collect all lits from conflict clause
        queue: List[int] = list(self.clauses[conflict_ci].lits)

        trail_idx = len(self.trail) - 1
        uip: Optional[int] = None

        while True:
            # Process literals in the reason clause
            for lit in queue:
                var = abs(lit)
                if var in seen:
                    continue
                seen.add(var)

                if self.level[var] == cur_level:
                    counter += 1
                    self.activity[var] += self.bump_increment
                elif self.level[var] > 0:
                    # Other-level literal: goes into learned clause (negated)
                    learned.append(lit)

            # Walk trail backwards to find next unprocessed current-level var
            while trail_idx >= 0:
                trail_lit = self.trail[trail_idx]
                trail_var = abs(trail_lit)
                trail_idx -= 1
                if trail_var in seen:
                    uip = trail_lit
                    break

            if uip is None:
                break

            counter -= 1
            if counter == 0:
                # uip is the 1-UIP
                break

            # Continue resolving using uip's reason
            r = self.reason[abs(uip)]
            if r is None:
                break
            queue = list(self.clauses[r].lits)

        # The asserting literal is the negation of the UIP
        assert uip is not None, "Could not find UIP — formula is UNSAT at level 0"
        asserting_lit = -uip
        full_learned = [asserting_lit] + [-lit for lit in learned]

        # Backjump level: second-highest decision level in learned clause
        if len(full_learned) == 1:
            backjump_level = 0
        else:
            other_levels = [self.level[abs(l)] for l in full_learned[1:]]
            backjump_level = max(other_levels) if other_levels else 0

        return full_learned, backjump_level

    # ------------------------------------------------------------------
    # Backjumping
    # ------------------------------------------------------------------

    def _backjump(self, level: int) -> None:
        """Undo all assignments above `level`."""
        while self._current_level() > level:
            self.trail_lim.pop()

        # Unassign trail entries above the level
        cut = self.trail_lim[level] if level < len(self.trail_lim) else 0
        while len(self.trail) > cut:
            lit = self.trail.pop()
            var = abs(lit)
            self.val[var] = UNASSIGNED
            self.level[var] = -1
            self.reason[var] = None

        self._prop_head = len(self.trail)

    # ------------------------------------------------------------------
    # VSIDS
    # ------------------------------------------------------------------

    def _decay_activities(self) -> None:
        self.bump_increment /= self.vsids_decay
        if self.bump_increment > 1e30:
            for i in range(1, self.num_vars + 1):
                self.activity[i] /= 1e30
            self.bump_increment /= 1e30

    def _pick_decision_var(self) -> Optional[int]:
        """Select the unassigned variable with highest VSIDS activity."""
        best_var = -1
        best_act = -1.0
        for var in range(1, self.num_vars + 1):
            if self.val[var] == UNASSIGNED and self.activity[var] > best_act:
                best_act = self.activity[var]
                best_var = var
        return best_var if best_var != -1 else None

    # ------------------------------------------------------------------
    # Learned clause DB
    # ------------------------------------------------------------------

    def _add_learned_clause(self, lits: List[int]) -> int:
        c = Clause(lits=lits, activity=1.0, is_learned=True)
        self.clauses.append(c)
        ci = len(self.clauses) - 1
        self.stats.learned_clauses += 1
        if len(lits) >= 2:
            self._add_watch(lits[0], ci)
            self._add_watch(lits[1], ci)
        return ci

    def _reduce_learned_db(self) -> None:
        """Remove half of the lowest-activity learned clauses."""
        learned = [
            i for i, c in enumerate(self.clauses)
            if c.is_learned and i >= self.n_original
        ]
        if len(learned) <= self.n_original * self.max_learned_mult:
            return

        learned.sort(key=lambda i: self.clauses[i].activity)
        to_remove = set(learned[: len(learned) // 2])

        # Rebuild clause list and watch lists
        new_clauses: List[Clause] = []
        remap: Dict[int, int] = {}
        for i, c in enumerate(self.clauses):
            if i in to_remove:
                continue
            remap[i] = len(new_clauses)
            new_clauses.append(c)

        self.clauses = new_clauses
        self.n_original = min(self.n_original, len(self.clauses))

        self.watch = [[[], []] for _ in range(self.num_vars + 1)]
        for ci, c in enumerate(self.clauses):
            if len(c.lits) >= 2:
                self._add_watch(c.lits[0], ci)
                self._add_watch(c.lits[1], ci)

        for var in range(1, self.num_vars + 1):
            r = self.reason[var]
            if r is not None:
                self.reason[var] = remap.get(r, None)

    # ------------------------------------------------------------------
    # Main solve loop
    # ------------------------------------------------------------------

    def solve(self, timeout_s: float = 30.0) -> SolveResult:
        """
        Run the CDCL solve loop.

        Args:
            timeout_s: Wall-clock timeout. Returns status="UNKNOWN" if exceeded.

        Returns:
            SolveResult with status, model, and stats.
        """
        t_start = time.perf_counter()

        if not self.clauses:
            return SolveResult(status="SAT", model=list(range(1, self.num_vars + 1)), stats=self.stats)

        # Initial unit propagation (catches unit clauses from the original formula)
        for ci, c in enumerate(self.clauses):
            if len(c.lits) == 1:
                val = self._lit_value(c.lits[0])
                if val == FALSE:
                    return SolveResult(status="UNSAT", model=[], stats=self.stats)
                if val == UNASSIGNED:
                    self._assign(c.lits[0], ci)

        conflict = self._propagate()
        if conflict is not None:
            return SolveResult(status="UNSAT", model=[], stats=self.stats)

        next_restart = _luby(self._restart_idx) * self.restart_luby_unit

        while True:
            if time.perf_counter() - t_start > timeout_s:
                self.stats.solve_time_ms = (time.perf_counter() - t_start) * 1000
                return SolveResult(status="UNKNOWN", model=[], stats=self.stats)

            dec_var = self._pick_decision_var()
            if dec_var is None:
                break  # All assigned — SAT

            # New decision level
            self.trail_lim.append(len(self.trail))
            self.stats.decisions += 1
            dl = self._current_level()
            if dl > self.stats.max_decision_level:
                self.stats.max_decision_level = dl

            self._assign(dec_var, None)  # positive polarity

            conflict_ci = self._propagate()

            while conflict_ci is not None:
                self.stats.conflicts += 1
                self._conflicts_since_restart += 1

                if self._current_level() == 0:
                    self.stats.solve_time_ms = (time.perf_counter() - t_start) * 1000
                    return SolveResult(status="UNSAT", model=[], stats=self.stats)

                learned_lits, backjump_level = self._analyze(conflict_ci)
                self._decay_activities()
                learned_ci = self._add_learned_clause(learned_lits)

                self._backjump(backjump_level)
                self._assign(learned_lits[0], learned_ci)

                conflict_ci = self._propagate()

                if self._conflicts_since_restart >= next_restart:
                    self.stats.restarts += 1
                    self._conflicts_since_restart = 0
                    self._restart_idx += 1
                    next_restart = _luby(self._restart_idx) * self.restart_luby_unit
                    self._backjump(0)
                    self._reduce_learned_db()
                    conflict_ci = self._propagate()

        model = []
        for var in range(1, self.num_vars + 1):
            model.append(var if self.val[var] == TRUE else -var)

        self.stats.solve_time_ms = (time.perf_counter() - t_start) * 1000
        return SolveResult(status="SAT", model=model, stats=self.stats)

    def verify(self, model: List[int]) -> bool:
        """Verifies that a model satisfies all original clauses."""
        assignment = {abs(lit): (lit > 0) for lit in model}
        for c in self.clauses[: self.n_original]:
            if not any(
                assignment.get(abs(lit), False) == (lit > 0) for lit in c.lits
            ):
                return False
        return True
