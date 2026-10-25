"""Reproducible CNF instance generators for tests and benchmarks."""

from __future__ import annotations

import itertools
import random

from graphsat.cnf import CNF


def random_ksat(num_vars: int, num_clauses: int, k: int = 3, seed: int | None = None) -> CNF:
    """Uniform random k-SAT: each clause picks k distinct variables and random signs."""
    if k > num_vars:
        raise ValueError("k must not exceed num_vars")
    rng = random.Random(seed)
    clauses = []
    for _ in range(num_clauses):
        vs = rng.sample(range(1, num_vars + 1), k)
        clauses.append([v if rng.random() < 0.5 else -v for v in vs])
    return CNF(num_vars=num_vars, clauses=clauses)


def pigeonhole(pigeons: int, holes: int) -> CNF:
    """PHP(p, h): p pigeons into h holes, at most one pigeon per hole. UNSAT iff p > h."""

    def var(i: int, j: int) -> int:
        return i * holes + j + 1

    clauses = [[var(i, j) for j in range(holes)] for i in range(pigeons)]
    for j in range(holes):
        for a, b in itertools.combinations(range(pigeons), 2):
            clauses.append([-var(a, j), -var(b, j)])
    return CNF(num_vars=pigeons * holes, clauses=clauses)


def graph_coloring(edges: list[tuple[int, int]], num_nodes: int, colors: int) -> CNF:
    """Proper ``colors``-colouring of a graph with nodes ``0..num_nodes-1``."""

    def var(node: int, c: int) -> int:
        return node * colors + c + 1

    clauses: list[list[int]] = [[var(n, c) for c in range(colors)] for n in range(num_nodes)]
    for n in range(num_nodes):
        for a, b in itertools.combinations(range(colors), 2):
            clauses.append([-var(n, a), -var(n, b)])
    for u, v in edges:
        for c in range(colors):
            clauses.append([-var(u, c), -var(v, c)])
    return CNF(num_vars=num_nodes * colors, clauses=clauses)


def planted_ksat(num_vars: int, num_clauses: int, k: int = 3, seed: int | None = None) -> tuple[CNF, list[int]]:
    """Random k-SAT guaranteed satisfiable by a hidden (planted) 0/1 assignment."""
    rng = random.Random(seed)
    hidden = [rng.randint(0, 1) for _ in range(num_vars)]
    clauses: list[list[int]] = []
    while len(clauses) < num_clauses:
        vs = rng.sample(range(1, num_vars + 1), k)
        clause = [v if rng.random() < 0.5 else -v for v in vs]
        if any((lit > 0) == bool(hidden[abs(lit) - 1]) for lit in clause):
            clauses.append(clause)
    return CNF(num_vars=num_vars, clauses=clauses), hidden
