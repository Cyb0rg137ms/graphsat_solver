"""Polynomial energy of a CNF, a sound (but weak) lower bound, and QUBO export.

For a clause ``C`` define the violation indicator ``P_C(x) = prod_{l in C} f_l(x)``
with ``f_l = 1 - x_v`` for a positive literal and ``f_l = x_v`` for a negative one.
For binary ``x`` the energy ``E(x) = sum_C P_C(x)`` equals the number of violated
clauses, so ``min_x E(x) > 0`` iff the formula is UNSAT.

:func:`energy_lower_bound` expands ``E`` into a multilinear polynomial (using
``x^2 = x``) and bounds every monomial from below by ``min(0, coefficient)``. Since
every monomial of binary variables lies in ``{0, 1}`` this is a valid lower bound;
if it is positive the formula is certainly UNSAT. The bound is *weak*: it only
fires on very small or degenerate contradictions (e.g. ``x`` and ``not x``) and is
``<= 0`` for essentially all non-trivial instances (e.g. random 3-SAT, pigeonhole).
It is a cheap pre-check, not a general UNSAT oracle.

:func:`to_qubo` produces an exact quadratic (QUBO) reformulation for clauses with
at most three literals using Rosenberg's substitution ``w = x*y`` with penalty
``M*(xy - 2xw - 2yw + 3w)``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

Monomial = frozenset[int]


def multilinear_energy(clauses: Sequence[Sequence[int]]) -> dict[Monomial, float]:
    """Expand ``E(x)`` into ``{monomial (set of 0-based var ids): coefficient}``."""
    poly: dict[Monomial, float] = defaultdict(float)
    for clause in clauses:
        terms: dict[Monomial, float] = {frozenset(): 1.0}
        for lit in clause:
            v = abs(lit) - 1
            new: dict[Monomial, float] = defaultdict(float)
            for mono, coef in terms.items():
                if lit > 0:  # (1 - x_v)
                    new[mono] += coef
                    new[mono | {v}] -= coef
                else:  # x_v
                    new[mono | {v}] += coef
            terms = new
        for mono, coef in terms.items():
            poly[mono] += coef
    return {m: c for m, c in poly.items() if abs(c) > 1e-12}


def energy_lower_bound(clauses: Sequence[Sequence[int]], max_clause_len: int = 8) -> float:
    """Sound lower bound on the minimum number of violated clauses.

    Clauses longer than ``max_clause_len`` are skipped (their energy is
    non-negative, so dropping them keeps the bound valid while avoiding the
    ``2^k`` expansion).
    """
    poly = multilinear_energy([c for c in clauses if len(c) <= max_clause_len])
    bound = poly.get(frozenset(), 0.0)
    bound += sum(min(0.0, c) for m, c in poly.items() if m)
    return bound


def to_qubo(
    clauses: Sequence[Sequence[int]], num_vars: int, penalty_scale: float = 2.0
) -> tuple[dict[tuple[int, int], float], float, int]:
    """Exact QUBO for formulas with clauses of length <= 3.

    Returns:
        ``(Q, offset, n_total)`` where ``Q[(i, j)]`` (``i <= j``) are coefficients of
        ``z_i z_j`` (diagonal = linear terms), ``offset`` is the constant and
        ``n_total`` counts original plus auxiliary variables. For every binary
        ``x``: ``min_w QUBO(x, w) == E(x)``.
    """
    if any(len(c) > 3 for c in clauses):
        raise ValueError("to_qubo supports clauses with at most 3 literals")
    poly = multilinear_energy(clauses)
    q: dict[tuple[int, int], float] = defaultdict(float)
    offset = 0.0
    aux: dict[tuple[int, int], int] = {}
    n_total = num_vars
    for mono, coef in poly.items():
        vs = sorted(mono)
        if not vs:
            offset += coef
        elif len(vs) == 1:
            q[(vs[0], vs[0])] += coef
        elif len(vs) == 2:
            q[(vs[0], vs[1])] += coef
        else:
            x, y, z = vs
            if (x, y) not in aux:
                aux[(x, y)] = n_total
                n_total += 1
            w = aux[(x, y)]
            m = penalty_scale * max(1.0, abs(coef))
            q[(min(w, z), max(w, z))] += coef
            q[(x, y)] += m
            q[(x, w)] -= 2 * m
            q[(y, w)] -= 2 * m
            q[(w, w)] += 3 * m
    return dict(q), offset, n_total


def qubo_value(q: dict[tuple[int, int], float], offset: float, z: Sequence[int]) -> float:
    """Evaluate a QUBO at a binary vector ``z``."""
    return offset + sum(c * z[i] * z[j] for (i, j), c in q.items())
