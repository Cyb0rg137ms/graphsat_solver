"""DRUP proof output and a small reference checker.

When :class:`graphsat.cdcl.CDCLSolver` runs with ``proof=True`` it records each
learned clause (``"a"``) and each deleted clause (``"d"``). A refutation ends with
the empty clause. Every added clause must be a *reverse unit propagation* (RUP)
consequence of the clauses currently in the database, which is what
:func:`check_drup` verifies.

The checker is deliberately simple (naive unit propagation, quadratic time) and is
meant for small/medium instances and tests. For large proofs write the proof with
:func:`write_drup` and use an external checker such as ``drat-trim``.
"""

from __future__ import annotations

from collections.abc import Sequence


def _unit_propagate(clauses: list[list[int]], assignment: dict[int, bool]) -> bool:
    """Naive BCP. Returns True if a conflict was derived."""
    changed = True
    while changed:
        changed = False
        for clause in clauses:
            unassigned: int | None = None
            n_unassigned = 0
            satisfied = False
            for lit in clause:
                v = assignment.get(abs(lit))
                if v is None:
                    n_unassigned += 1
                    unassigned = lit
                elif v == (lit > 0):
                    satisfied = True
                    break
            if satisfied:
                continue
            if n_unassigned == 0:
                return True
            if n_unassigned == 1:
                assert unassigned is not None
                assignment[abs(unassigned)] = unassigned > 0
                changed = True
    return False


def is_rup(clauses: list[list[int]], clause: Sequence[int]) -> bool:
    """Return True if ``clause`` follows from ``clauses`` by reverse unit propagation."""
    assignment: dict[int, bool] = {}
    for lit in clause:
        if assignment.get(abs(lit)) == (lit > 0):
            return True  # tautology
        assignment[abs(lit)] = lit < 0
    return _unit_propagate(clauses, assignment)


def check_drup(clauses: Sequence[Sequence[int]], proof: Sequence[tuple[str, Sequence[int]]]) -> bool:
    """Check a DRUP refutation of ``clauses``.

    Returns True iff every added clause is RUP w.r.t. the current database and the
    proof contains the empty clause.
    """
    db = [list(c) for c in clauses]
    for op, clause in proof:
        if op == "a":
            if not is_rup(db, clause):
                return False
            if len(clause) == 0:
                return True
            db.append(list(clause))
        elif op == "d":
            key = sorted(clause)
            for i, c in enumerate(db):
                if sorted(c) == key:
                    del db[i]
                    break
        else:
            raise ValueError(f"unknown proof op {op!r}")
    return False


def write_drup(proof: Sequence[tuple[str, Sequence[int]]]) -> str:
    """Serialise a proof in the textual DRUP format understood by ``drat-trim``."""
    lines = []
    for op, clause in proof:
        prefix = "d " if op == "d" else ""
        lines.append(prefix + " ".join(map(str, clause)) + (" 0" if clause else "0"))
    return "\n".join(lines) + "\n"
