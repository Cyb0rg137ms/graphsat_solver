"""Solver configuration (dataclass + TOML loading)."""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


@dataclass
class SolverConfig:
    """Configuration for :class:`graphsat.core.HybridSolver`.

    Attributes:
        relax_steps: Gradient steps of the continuous relaxation (0 disables it).
        lr: Relaxation step size.
        coupling: Prime-spaced coupling strength (0 disables the heuristic).
        seed: RNG seed for the relaxation's initial point.
        use_lower_bound: Run the polynomial lower-bound pre-check.
        use_phase_hints: Seed CDCL phases from the relaxation.
        timeout_s: CDCL wall-clock budget.
        max_conflicts: Optional CDCL conflict budget.
        certify: Record a DRUP proof and check UNSAT answers with the built-in checker.
    """

    relax_steps: int = 200
    lr: float = 0.1
    coupling: float = 0.086
    seed: int | None = 0
    use_lower_bound: bool = True
    use_phase_hints: bool = True
    timeout_s: float = 60.0
    max_conflicts: int | None = None
    certify: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return the configuration as a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SolverConfig:
        """Create from a dictionary, rejecting unknown keys."""
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        return cls(**data)

    @classmethod
    def from_toml(cls, path: str | Path) -> SolverConfig:
        """Load from a TOML file (keys at top level or under ``[solver]``)."""
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        return cls.from_dict(data.get("solver", data))
