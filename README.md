# GraphSAT — verified hybrid SAT solving in Python

> CI workflow lives in `ci/github-actions-ci.yml`; move it to `.github/workflows/ci.yml` to enable GitHub Actions (the push token lacked `workflow` scope).

GraphSAT is a research-oriented SAT solver. It combines a complete **CDCL** core with an experimental **continuous relaxation** of the clause-violation energy. **Every answer is verified:**

- SAT models are re-checked against the input formula.
- UNSAT answers can carry a **DRUP proof** that is checked by a built-in RUP checker. The proof file is also in drat-trim format.

The relaxation is treated as a hypothesis to measure, not a claimed speedup. See the [benchmarks](#measured-benchmarks) for honest numbers.

## Features
- **CDCL solver:**
  - two-watched-literal propagation and a VSIDS heap
  - first-UIP learning with non-chronological backjumping
  - phase saving, Luby restarts and LBD-based learned-clause deletion
  - optional DRUP proof logging
- **Sound polynomial lower bound** on the number of violated clauses, plus an exact **QUBO export** (Rosenberg reduction) for annealers and Ising solvers.
- **Vectorised relaxation** in NumPy:
  - exact gradients and a seeded projected gradient descent
  - an optional prime-spaced coupling heuristic that you can turn off for ablations
  - results feed CDCL phase hints
- **Generators** for random k-SAT, planted k-SAT, pigeonhole and graph colouring instances.
- **Tooling:**
  - `graphsat` CLI with SAT-competition exit codes (10 = SAT, 20 = UNSAT)
  - TOML config file
  - benchmark harness, Dockerfile and typed API (mypy-clean)

Architecture diagram and module map: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Known limitations: [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Install
```bash
pip install -e .            # runtime: numpy only
pip install -r requirements-dev.txt   # ruff, mypy, pytest
```

## Quickstart
```python
from graphsat import HybridSolver, SolverConfig, solve
from graphsat.generators import pigeonhole

print(solve([[1, -2], [2, 3], [-1, -3]]).status)  # SAT
r = HybridSolver(pigeonhole(6, 5), SolverConfig(certify=True)).solve()
print(r.status, r.certified)  # UNSAT True (DRUP-checked)
```
```bash
graphsat gen random --n 100 --alpha 4.26 --seed 0 > f.cnf
graphsat solve f.cnf --config examples/config.toml --certify --proof f.drup
graphsat bench --n 50 --trials 30
```
More examples: [`examples/quickstart.py`](examples/quickstart.py).

## Measured benchmarks
The numbers below were measured on a shared Intel Xeon VM with CPython 3.13.5 and a single thread. Re-run them yourself with `graphsat bench`.

**Random 3-SAT phase transition** (n = 50, 30 instances per ratio):

| alpha | m | P(SAT) | mean ms | median ms | mean decisions | mean conflicts |
|---|---|---|---|---|---|---|
| 3.00 | 150 | 1.00 | 0.89 | 0.46 | 16.9 | 1.6 |
| 3.50 | 175 | 1.00 | 0.73 | 0.58 | 20.4 | 6.6 |
| 4.00 | 200 | 0.93 | 1.20 | 1.14 | 26.4 | 14.4 |
| 4.50 | 225 | 0.47 | 1.85 | 1.78 | 35.9 | 28.1 |
| 5.00 | 250 | 0.07 | 1.66 | 1.66 | 27.5 | 25.3 |
| 5.50 | 275 | 0.00 | 1.85 | 1.78 | 29.2 | 27.1 |
| 6.00 | 300 | 0.00 | 1.66 | 1.65 | 23.7 | 22.8 |

The drop in P(SAT) between α = 4.0 and 5.0 is consistent with the known threshold near α ≈ 4.26. At n = 50 the instances are easy, so harder behaviour shows up in the ablation below.

**Ablation** (n = 150, α = 4.26, 20 instances, 7 SAT / 13 UNSAT; all variants agree on every answer):

| Variant | mean time | mean conflicts |
|---|---|---|
| CDCL only | 514.6 ms | 2843 |
| Hybrid (relaxation hints + prime coupling) | 549 ms | 2787 |
| Hybrid, coupling off | 547 ms | 2921 |
| Hybrid, hints off | 565 ms | 2843 |

**Takeaway:** on random 3-SAT the relaxation does not pay for itself. It cuts conflicts by about 2% at best and adds wall-clock overhead. The prime coupling shows no consistent benefit. PHP(8,7), a classic hard UNSAT family for resolution, solves in about 1.2 s.

## Development
```bash
ruff check . && ruff format --check . && mypy graphsat && pytest
```
There are 221 tests and they run in about 0.5 s. They cover:
- agreement with brute force on random formulas
- DRUP proof validity, including rejection of bogus proofs
- lower-bound soundness and QUBO exactness, checked by brute force
- finite-difference gradient checks
- DIMACS parsing edge cases and the CLI

## Bugs fixed relative to the original version
- The learned clause negated literals from other levels, which made it unsound.
- Backjumping unassigned the entire trail, including level 0.
- The watch invariant was broken for learned clauses. Together with the two bugs above, this made PHP(4,3) and K4 3-colouring hang.
- DPLL did not undo unit propagations on backtrack.
- The lower bound dropped the x² = x terms, which made it unsound.
- Randomness was unseeded, and an O(n²) Python loop is now vectorised.
- The previous README and benchmark claims were not reproducible and have been removed.

## License
MIT
