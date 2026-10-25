"""CNF formula container and DIMACS I/O."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field


class DimacsError(ValueError):
    """Raised for malformed DIMACS CNF input."""


@dataclass
class CNF:
    """A CNF formula over variables ``1..num_vars`` in DIMACS literal convention."""

    num_vars: int
    clauses: list[list[int]] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.validate()

    @property
    def num_clauses(self) -> int:
        """Number of clauses."""
        return len(self.clauses)

    def validate(self) -> None:
        """Raise :class:`ValueError` if a literal is zero or references an undeclared variable."""
        if self.num_vars < 0:
            raise ValueError("num_vars must be non-negative")
        for i, clause in enumerate(self.clauses):
            for lit in clause:
                if lit == 0 or abs(lit) > self.num_vars:
                    raise ValueError(f"clause {i}: literal {lit} outside 1..{self.num_vars}")

    def evaluate(self, assignment: Sequence[bool] | Sequence[int]) -> bool:
        """Evaluate under a 0/1 or bool assignment indexed by ``var - 1``."""
        return all(any(bool(assignment[abs(lit) - 1]) == (lit > 0) for lit in c) for c in self.clauses)

    def num_violated(self, assignment: Sequence[bool] | Sequence[int]) -> int:
        """Count clauses violated by an assignment indexed by ``var - 1``."""
        return sum(not any(bool(assignment[abs(lit) - 1]) == (lit > 0) for lit in c) for c in self.clauses)

    def to_dimacs(self) -> str:
        """Serialise to DIMACS CNF text."""
        lines = [f"c {c}" for c in self.comments]
        lines.append(f"p cnf {self.num_vars} {len(self.clauses)}")
        lines.extend(" ".join(map(str, c)) + " 0" for c in self.clauses)
        return "\n".join(lines) + "\n"

    @classmethod
    def from_dimacs(cls, content: str, strict: bool = False) -> CNF:
        """Parse DIMACS CNF text.

        Clauses may span several lines and several clauses may share a line; a
        clause ends at the token ``0``. A trailing clause without ``0`` is accepted.
        The ``%`` end marker used by SATLIB files is honoured.

        Args:
            content: DIMACS text.
            strict: If True, a header mismatch (variable or clause count) raises.
        """
        num_vars: int | None = None
        declared_clauses: int | None = None
        clauses: list[list[int]] = []
        comments: list[str] = []
        current: list[int] = []
        for lineno, raw in enumerate(content.splitlines(), start=1):
            line = raw.strip()
            if not line:
                continue
            if line.startswith("c"):
                comments.append(line[1:].strip())
                continue
            if line.startswith("%"):
                break
            if line.startswith("p"):
                parts = line.split()
                if len(parts) != 4 or parts[1] != "cnf":
                    raise DimacsError(f"line {lineno}: bad problem line {line!r}")
                try:
                    num_vars, declared_clauses = int(parts[2]), int(parts[3])
                except ValueError as exc:
                    raise DimacsError(f"line {lineno}: bad problem line {line!r}") from exc
                continue
            for tok in line.split():
                try:
                    lit = int(tok)
                except ValueError as exc:
                    raise DimacsError(f"line {lineno}: invalid literal {tok!r}") from exc
                if lit == 0:
                    clauses.append(current)
                    current = []
                else:
                    current.append(lit)
        if current:
            clauses.append(current)
        max_var = max((abs(lit) for c in clauses for lit in c), default=0)
        if num_vars is None:
            num_vars = max_var
        if max_var > num_vars:
            if strict:
                raise DimacsError(f"literal uses variable {max_var} > declared {num_vars}")
            num_vars = max_var
        if strict and declared_clauses is not None and declared_clauses != len(clauses):
            raise DimacsError(f"header declares {declared_clauses} clauses, found {len(clauses)}")
        return cls(num_vars=num_vars, clauses=clauses, comments=comments)

    @classmethod
    def from_clauses(cls, clauses: Iterable[Iterable[int]], num_vars: int | None = None) -> CNF:
        """Build from an iterable of clauses, inferring ``num_vars`` if omitted."""
        cl = [list(c) for c in clauses]
        n = max((abs(lit) for c in cl for lit in c), default=0)
        return cls(num_vars=n if num_vars is None else num_vars, clauses=cl)
