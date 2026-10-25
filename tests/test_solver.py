from graphsat.core import ManifoldConstraintSolver
from graphsat.geometric import extract_relaxation_heuristics
from graphsat.parser import parse_dimacs


def test_parse_dimacs():
    cnf_content = """
    c Simple DIMACS example
    p cnf 3 2
    1 -2 3 0
    -1 2 0
    """
    num_vars, clauses = parse_dimacs(cnf_content)
    assert num_vars == 3
    assert len(clauses) == 2
    assert clauses[0] == [1, -2, 3]
    assert clauses[1] == [-1, 2]


def test_simple_sat():
    # Clause: (x1 or x2) and (not x1 or x2)
    clauses = [[1, 2], [-1, 2]]
    solver = ManifoldConstraintSolver(2, clauses)
    status, assignment = solver.solve()
    assert status == "SAT"
    assert solver.verify(assignment)
    assert assignment[1] == 1  # x2 must be True to satisfy both


def test_simple_unsat():
    # Clause: (x1) and (not x1)
    clauses = [[1], [-1]]
    solver = ManifoldConstraintSolver(1, clauses)
    status, _result = solver.solve()
    assert status == "UNSAT"


def test_pigeonhole_completeness():
    # Pigeonhole principle: 3 pigeons in 2 holes (UNSAT)
    # 6 variables: P_ij represents pigeon i in hole j
    # 1: P1H1, 2: P1H2, 3: P2H1, 4: P2H2, 5: P3H1, 6: P3H2
    clauses_php = [
        [1, 2],
        [3, 4],
        [5, 6],  # Every pigeon must go to at least one hole
        [-1, -3],
        [-1, -5],
        [-3, -5],  # Hole 1 can have at most one pigeon
        [-2, -4],
        [-2, -6],
        [-4, -6],  # Hole 2 can have at most one pigeon
    ]
    solver = ManifoldConstraintSolver(6, clauses_php)
    status, _result = solver.solve()
    assert status == "UNSAT"


def test_heuristics_generation():
    clauses = [[1, 2], [-1, 2]]
    coords = extract_relaxation_heuristics(2, clauses, steps=10)
    assert len(coords) == 2
    assert all(0.0 <= c <= 1.0 for c in coords)
