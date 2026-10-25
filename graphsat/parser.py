"""Backward-compatible DIMACS parsing helpers."""

from __future__ import annotations

from graphsat.cnf import CNF


def parse_dimacs(content: str) -> tuple[int, list[list[int]]]:
    """Parse DIMACS CNF text and return ``(num_vars, clauses)``.

    Thin wrapper over :meth:`graphsat.cnf.CNF.from_dimacs` kept for API stability.
    """
    cnf = CNF.from_dimacs(content)
    return cnf.num_vars, cnf.clauses


def read_dimacs(path: str) -> CNF:
    """Read a DIMACS CNF file from disk."""
    with open(path, encoding="utf-8") as fh:
        return CNF.from_dimacs(fh.read())
