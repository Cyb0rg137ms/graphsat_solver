"""Quickstart: solve formulas, certify UNSAT with a DRUP proof, inspect the relaxation."""

from graphsat import CNF, HybridSolver, SolverConfig, solve
from graphsat.generators import pigeonhole, random_ksat

# 1. Tiny formula from Python lists
print(solve([[1, -2], [2, 3], [-1, -3]]).to_dict())

# 2. Random 3-SAT near the phase transition
cnf = random_ksat(num_vars=80, num_clauses=340, seed=1)
res = HybridSolver(cnf, SolverConfig(seed=1, certify=True)).solve()
print(res.status, res.decided_by, "certified:", res.certified, res.timings_ms)

# 3. UNSAT with a machine-checked proof (pigeonhole 6 -> 5)
php = pigeonhole(6, 5)
res = HybridSolver(php, SolverConfig(certify=True, relax_steps=0)).solve()
print("PHP(6,5):", res.status, "proof steps:", len(res.proof or []), "proof checked:", res.certified)

# 4. DIMACS round trip
print(CNF.from_dimacs(php.to_dimacs()).num_clauses, "clauses")
