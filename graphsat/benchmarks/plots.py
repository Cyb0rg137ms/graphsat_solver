"""Phase-transition figure from ``graphsat bench --json`` rows (matplotlib optional)."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any


def plot_phase(rows: list[dict[str, Any]], path: str | Path) -> Path:
    """P(SAT) and mean CDCL conflicts vs clause density, one curve per n."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    by_n: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_n[int(r["n_vars"])].append(r)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    for n, rs in sorted(by_n.items()):
        rs.sort(key=lambda r: r["alpha"])
        al = [r["alpha"] for r in rs]
        a1.plot(al, [r["sat_probability"] for r in rs], "o-", label=f"n = {n}")
        a2.semilogy(al, [max(r["mean_conflicts"], 0.1) for r in rs], "o-", label=f"n = {n}")
    for ax in (a1, a2):
        ax.axvline(4.267, color="grey", ls="--", lw=1)
        ax.set_xlabel("clause density alpha = m / n")
        ax.grid(alpha=0.3)
        ax.legend()
    a1.set(ylabel="P(SAT)", title="Random 3-SAT: satisfiability threshold")
    a2.set(ylabel="mean CDCL conflicts", title="Hardness peaks at the threshold")
    fig.tight_layout()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path
