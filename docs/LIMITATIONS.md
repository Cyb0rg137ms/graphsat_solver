# Limitations

* **Pure Python.** The CDCL core is a faithful MiniSat-style design but runs ~2–3 orders of magnitude slower than C/C++ solvers (MiniSat, CaDiCaL, Kissat). It is meant for research prototyping, teaching and verified small/medium instances, not for competition workloads.
* **The continuous relaxation is a heuristic.** In our measurements (see README) phase hints from the relaxation reduced CDCL conflicts only marginally and did not reduce wall-clock time on random 3-SAT; the prime-spaced coupling term showed no consistent benefit. Both are kept as ablatable, measurable options, not as claimed improvements.
* **The polynomial lower bound is weak.** It is sound, but it only proves UNSAT for trivial contradictions; it is ≤ 0 for random 3-SAT and pigeonhole formulas.
* **Proof checking** uses a naive quadratic RUP checker; for large proofs use `--proof out.drup` and an external checker such as `drat-trim`.
* No preprocessing (BVE, subsumption), no learned-clause minimisation, no inprocessing, no incremental/assumption interface yet.
* Nothing in this project changes the worst-case complexity of SAT (NP-complete).
