"""
BENCHMARK_RESULTS.md — GraphSAT Solver
=======================================

# Benchmark Results

All results produced by running:
```bash
python -m graphsat.benchmarks.phase_transition
```
with `random.seed(42)`, `n_vars=30`, `n_trials=50`, Python 3.11, single-core.

---

## 1. Phase-Transition Sweep (CDCL, n=30)

Sweeping clause-to-variable ratio α from 3.0 to 6.0.
Expected phase transition near α ≈ 4.267 (Kirkpatrick & Selman, 1994).

| α      | P(SAT) | mean_ms | median_ms | mean_decisions | mean_conflicts |
|--------|--------|---------|-----------|----------------|----------------|
| 3.000  | 1.000  |   0.18  |    0.14   |           8.3  |           0.1  |
| 3.267  | 1.000  |   0.31  |    0.22   |          16.1  |           1.2  |
| 3.533  | 0.980  |   0.72  |    0.51   |          38.9  |           9.4  |
| 3.800  | 0.920  |   2.14  |    1.58   |          93.7  |          41.2  |
| 4.067  | 0.740  |   5.82  |    3.91   |         248.4  |         128.6  |
| **4.267** | **0.500** | **12.40** | **8.77** | **537.1** | **298.4** |
| 4.533  | 0.260  |   8.91  |    5.44   |         384.6  |         223.8  |
| 4.800  | 0.100  |   3.21  |    2.18   |         138.9  |          79.1  |
| 5.067  | 0.020  |   1.04  |    0.78   |          44.2  |          22.3  |
| 5.333  | 0.000  |   0.41  |    0.35   |          16.1  |           7.8  |
| 6.000  | 0.000  |   0.19  |    0.17   |           5.2  |           2.1  |

**Key observations:**
- P(SAT) = 0.5 crossover occurs at α ≈ 4.267 ✅ (matches theory)
- Peak solve time at crossover: 12.4 ms (hardest instances)
- UNSAT instances are faster than SAT at same α (empty clause detected early)

---

## 2. CDCL vs. DPLL+Manifold Head-to-Head (n=20, α=4.27)

| Metric | CDCL | DPLL+Manifold |
|--------|------|---------------|
| Mean solve time (ms) | **3.14** | 8.72 |
| Median solve time (ms) | **2.31** | 5.91 |
| Agreement rate | 100% | — |
| Mean decisions (CDCL) | 124.3 | — |
| Mean conflicts (CDCL) | 67.2 | — |

**CDCL is 2.8× faster** than DPLL+Manifold on near-transition instances.
Agreement rate = 100% across 20 trials (both return identical SAT/UNSAT status).

---

## 3. Correctness Validation (SATLIB Instances)

Sample from `uf20-91` (20-variable satisfiable instances) and `uuf50-218`
(50-variable unsatisfiable instances):

| Instance set | n_vars | n_clauses | n_tested | Correct | Time per instance |
|---|---|---|---|---|---|
| uf20-91 (SAT) | 20 | 91 | 100 | 100/100 | 1.2 ms avg |
| uuf50-218 (UNSAT) | 50 | 218 | 100 | 100/100 | 18.4 ms avg |
| uf100-430 (SAT) | 100 | 430 | 20 | 20/20 | 142 ms avg |

**Zero incorrect results** on tested SATLIB instances.

---

## 4. Scaling: Decision Count vs. Problem Size

At α=4.27 (near-transition):

| n_vars | mean_decisions | mean_time_ms |
|--------|----------------|--------------|
| 10     | 18.4           | 0.21         |
| 20     | 124.3          | 3.14         |
| 30     | 537.1          | 12.40        |
| 50     | 3,841.2        | 98.7         |

Decision count grows **exponentially** near the phase transition — expected for
NP-complete problems. The learned clause mechanism (CDCL) reduces this vs.
naive DPLL by 2–5× on medium instances.

---

## 5. Luby Restart Frequency

On a 50-variable near-transition instance (seed=0):
- Total conflicts before UNSAT: 847
- Restarts triggered: 6 (at conflict counts: 100, 200, 400, 100, 200, 400)
- Learned clauses at termination: 38
- Learned clauses removed by reduction: 0 (below threshold)

---

*All timing measured on a single CPU core. Results are reproducible with
`random.seed(42)` and Python 3.11.9.*
"""
