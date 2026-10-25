"""Command-line interface: ``graphsat solve|gen|bench``.

Exit codes follow the SAT-competition convention: 10 = SAT, 20 = UNSAT, 0 = unknown.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence

from graphsat.cnf import CNF
from graphsat.config import SolverConfig
from graphsat.core import HybridSolver
from graphsat.generators import pigeonhole, random_ksat
from graphsat.proof import write_drup


def _cmd_solve(args: argparse.Namespace) -> int:
    cfg = SolverConfig.from_toml(args.config) if args.config else SolverConfig()
    if args.timeout is not None:
        cfg.timeout_s = args.timeout
    if args.no_relax:
        cfg.relax_steps = 0
    if args.seed is not None:
        cfg.seed = args.seed
    cfg.certify = cfg.certify or args.certify or bool(args.proof)
    if args.file == "-":
        text = sys.stdin.read()
    else:
        with open(args.file, encoding="utf-8") as fh:
            text = fh.read()
    cnf = CNF.from_dimacs(text)
    res = HybridSolver(cnf, cfg).solve()
    if args.proof and res.proof is not None:
        with open(args.proof, "w", encoding="utf-8") as fh:
            fh.write(write_drup(res.proof))
    if args.json:
        out = res.to_dict()
        if res.status == "SAT":
            out["model"] = [v if b else -v for v, b in enumerate(res.assignment, start=1)]
        print(json.dumps(out, indent=2))
    else:
        print(f"s {'SATISFIABLE' if res.status == 'SAT' else 'UNSATISFIABLE' if res.status == 'UNSAT' else 'UNKNOWN'}")
        if res.status == "SAT":
            print("v " + " ".join(str(v if b else -v) for v, b in enumerate(res.assignment, start=1)) + " 0")
        print(f"c decided_by={res.decided_by} certified={res.certified}")
    return {"SAT": 10, "UNSAT": 20}.get(res.status, 0)


def _cmd_gen(args: argparse.Namespace) -> int:
    if args.kind == "random":
        cnf = random_ksat(args.n, round(args.alpha * args.n), k=args.k, seed=args.seed)
    else:
        cnf = pigeonhole(args.n + 1, args.n)
    sys.stdout.write(cnf.to_dimacs())
    return 0


def _cmd_bench(args: argparse.Namespace) -> int:
    from graphsat.benchmarks.phase_transition import print_phase_table, run_phase_transition

    rows = []
    for n in args.n:
        part = run_phase_transition(
            n_vars=n, alpha_range=(args.alpha_min, args.alpha_max), alpha_steps=args.steps, n_trials=args.trials
        )
        print_phase_table(part)
        rows.extend(part)
    if args.json:
        import json
        from pathlib import Path

        Path(args.json).write_text(json.dumps(rows, indent=2))
    if args.plot:
        from graphsat.benchmarks.plots import plot_phase

        plot_phase(rows, args.plot)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    p = argparse.ArgumentParser(prog="graphsat", description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("solve", help="solve a DIMACS CNF file ('-' for stdin)")
    s.add_argument("file")
    s.add_argument("--config", help="TOML config file")
    s.add_argument("--timeout", type=float)
    s.add_argument("--seed", type=int)
    s.add_argument("--no-relax", action="store_true", help="skip the continuous relaxation")
    s.add_argument("--certify", action="store_true", help="check UNSAT answers with a DRUP proof")
    s.add_argument("--proof", help="write the DRUP proof to this path")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=_cmd_solve)

    g = sub.add_parser("gen", help="generate an instance to stdout")
    g.add_argument("kind", choices=["random", "pigeonhole"])
    g.add_argument("--n", type=int, default=20, help="variables (random) or holes (pigeonhole)")
    g.add_argument("--alpha", type=float, default=4.26)
    g.add_argument("--k", type=int, default=3)
    g.add_argument("--seed", type=int, default=0)
    g.set_defaults(func=_cmd_gen)

    b = sub.add_parser("bench", help="random 3-SAT phase-transition sweep")
    b.add_argument("--n", type=int, nargs="+", default=[30], help="one or more variable counts")
    b.add_argument("--alpha-min", type=float, default=3.0)
    b.add_argument("--alpha-max", type=float, default=6.0)
    b.add_argument("--steps", type=int, default=7)
    b.add_argument("--trials", type=int, default=20)
    b.add_argument("--json", help="write all rows as JSON")
    b.add_argument("--plot", help="write the phase-transition figure (PNG); needs matplotlib")
    b.set_defaults(func=_cmd_bench)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
