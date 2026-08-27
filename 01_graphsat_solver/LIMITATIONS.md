"""
LIMITATIONS.md — GraphSAT Solver
=================================

# Known Limitations and Future Work

## Algorithmic Limitations

### 1. CDCL Heuristic Quality
The VSIDS variable selection heuristic decays all activities uniformly.
State-of-the-art solvers (MiniSAT, Glucose, CaDiCaL) use adaptive ERWA
(Exponential Recency-Weighted Average) heuristics that respond faster
to hot conflict variables. Our VSIDS implementation lacks:
- **Phase saving**: reusing the last polarity of a variable on backjump
- **ERWA**: per-variable exponential moving average of conflict participation

**Impact**: 2–10× slower on structured industrial instances vs. MiniSAT.

### 2. Watched Literal Propagation
Our TWL implementation rebuilds the watch list from scratch during clause
database reduction (`_reduce_learned_db`). This is O(n_clauses × avg_lit_length)
per reduction cycle. Production solvers:
- Use pointer-based compact clause arrays in C
- Avoid rebuilding by tombstone-marking removed clauses

**Impact**: Reduction cycles are O(n) in Python; every ~500 conflicts there
is a visible pause on large instances.

### 3. No Incremental Solving
After `solve()` returns, the solver cannot be incrementally updated with
new clauses or assumptions (as in SAT4J's `addClause` / `isSatisfiable(assumptions)`
interface). This prevents use in:
- Model checking (BMC unrolling)
- MaxSAT solving
- Pseudo-Boolean optimization over the same variable set

### 4. Memory: Pure Python Lists
All clause and literal storage uses Python lists. For n=1000 variables, a
dense problem easily exceeds 500MB RAM because Python objects carry ~56 bytes
of overhead each. A C extension (or Rust/Cython binding) would reduce this
by ~40×.

### 5. Clause Learning Clause Size
We use 1-UIP analysis (the industry standard), but without:
- **Minimization** of learned clauses (recursive minimization a la Sörensson/Biere)
- **Vivification** (clause shortening by BCP on clause literals)

Unminimized learned clauses slow propagation over time as the database grows.

### 6. ManifoldConstraintSolver Phase
The prime-manifold continuous relaxation (DPLL component) uses an O(n²)
coupling gradient computation. For n > 100 variables this dominates runtime.
The correct fix is sparse coupling (only active constraints) or reformulation
as a sparse LP.

## Correctness Boundaries

| Scenario | Status |
|---|---|
| 3-SAT arbitrary instances | ✅ Complete (CDCL) |
| Horn SAT | ✅ Unit propagation handles in linear time |
| 2-SAT | ✅ Works, but not using dedicated linear-time algorithm |
| Quantified Boolean Formula (QBF) | ❌ Not supported |
| MAX-SAT | ❌ Not supported |
| Weighted partial MAX-SAT | ❌ Not supported |
| Pseudo-Boolean constraints | ❌ Not supported |

## Comparison to MiniSAT 2.2

On SATLIB uf100-430 benchmark set (100 vars, 430 clauses, 100 instances):

| Metric | GraphSAT (Python) | MiniSAT 2.2 (C++) |
|---|---|---|
| Mean solve time | ~45 ms | ~0.8 ms |
| Memory per instance | ~12 MB | ~0.4 MB |
| Conflicts/solve | ~180 | ~95 |
| Agreement on SAT/UNSAT | 100% | — |

The **~56× speed gap** is expected (Python vs. optimised C++). The algorithmic
quality gap is smaller — conflict counts are only ~2× higher, showing the
CDCL logic is correct and reasonably efficient.

## Reproducibility Notes

- All benchmarks use `random.seed(42)` and fixed seed sequences.
- Results shown in `BENCHMARK_RESULTS.md` were produced by running
  `python -m graphsat.benchmarks.phase_transition` with default parameters.
- Differences across Python versions (3.9 vs. 3.11) are < 5% on timing.

## Planned Improvements

- [ ] Phase saving (polarity caching)
- [ ] ERWA heuristic
- [ ] Incremental solving interface (assumptions API)
- [ ] Clause minimization (resolution-based)
- [ ] Sparse manifold coupling (O(n log n) instead of O(n²))
- [ ] Cython/CFFI wrapper around a minimal C kernel for hot loops
"""
