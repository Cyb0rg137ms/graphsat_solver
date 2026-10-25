"""Property tests: solvers vs brute force, proofs, bounds, relaxation gradients."""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from graphsat import CNF, CDCLSolver, HybridSolver, SolverConfig, check_drup, energy_lower_bound, to_qubo
from graphsat.bounds import multilinear_energy, qubo_value
from graphsat.generators import graph_coloring, pigeonhole, planted_ksat, random_ksat
from graphsat.proof import is_rup, write_drup
from graphsat.relaxation import ClauseTensor, first_primes, relax


def brute_force_sat(cnf: CNF) -> bool:
    return any(cnf.evaluate(bits) for bits in itertools.product([0, 1], repeat=cnf.num_vars))


def min_violations(cnf: CNF) -> int:
    return min(cnf.num_violated(bits) for bits in itertools.product([0, 1], repeat=cnf.num_vars))


@pytest.mark.parametrize("seed", range(60))
def test_cdcl_matches_brute_force(seed: int) -> None:
    n = 4 + seed % 7
    m = int(n * (3.0 + (seed % 5) * 0.6))
    cnf = random_ksat(n, m, 3, seed=seed)
    r = CDCLSolver(n, cnf.clauses, restart_luby_unit=2).solve(timeout_s=10)
    assert r.status == ("SAT" if brute_force_sat(cnf) else "UNSAT")
    if r.is_sat():
        assert cnf.evaluate([lit > 0 for lit in r.model])


@pytest.mark.parametrize("seed", range(30))
def test_unsat_proofs_check(seed: int) -> None:
    cnf = random_ksat(8, 60, 3, seed=1000 + seed)
    r = CDCLSolver(cnf.num_vars, cnf.clauses, proof=True, restart_luby_unit=3).solve()
    if r.is_unsat():
        assert r.proof is not None and r.proof[-1] == ("a", [])
        assert check_drup(cnf.clauses, r.proof)


def test_pigeonhole_family_unsat_with_proof() -> None:
    for h in range(1, 5):
        cnf = pigeonhole(h + 1, h)
        r = CDCLSolver(cnf.num_vars, cnf.clauses, proof=True).solve(timeout_s=20)
        assert r.is_unsat()
        assert check_drup(cnf.clauses, r.proof or [])
    assert CDCLSolver(9, pigeonhole(3, 3).clauses).solve().is_sat()


def test_bogus_proof_rejected() -> None:
    cnf = CNF.from_clauses([[1, 2], [-1, 2], [1, -2]])  # SAT (x1=x2=1)
    assert not check_drup(cnf.clauses, [("a", [])])
    assert not is_rup(cnf.clauses, [-2])
    assert is_rup(cnf.clauses, [2])
    assert "d 1 2 0" in write_drup([("d", [1, 2]), ("a", [])])


def test_k4_not_3_colourable_and_c5_is() -> None:
    k4 = [(a, b) for a in range(4) for b in range(a + 1, 4)]
    assert CDCLSolver(12, graph_coloring(k4, 4, 3).clauses).solve().is_unsat()
    c5 = [(i, (i + 1) % 5) for i in range(5)]
    assert CDCLSolver(15, graph_coloring(c5, 5, 3).clauses).solve().is_sat()


@pytest.mark.parametrize("seed", range(15))
def test_hybrid_matches_cdcl_and_is_certified(seed: int) -> None:
    cnf = random_ksat(12, 51, 3, seed=seed)
    h = HybridSolver(cnf, SolverConfig(certify=True, seed=seed)).solve()
    assert h.status == CDCLSolver(12, cnf.clauses).solve().status
    assert h.certified
    if h.status == "SAT":
        assert cnf.evaluate(h.assignment)


def test_planted_instances_are_sat() -> None:
    for s in range(5):
        cnf, hidden = planted_ksat(40, 160, seed=s)
        assert cnf.evaluate(hidden)
        h = HybridSolver(cnf).solve()
        assert h.status == "SAT" and cnf.evaluate(h.assignment)


@pytest.mark.parametrize("seed", range(25))
def test_lower_bound_is_sound(seed: int) -> None:
    cnf = random_ksat(5, 5 + seed, 3, seed=seed)
    cnf.clauses += [[1], [-1, 2]] if seed % 2 else [[-3, 4]]
    assert energy_lower_bound(cnf.clauses) <= min_violations(cnf) + 1e-9


def test_lower_bound_detects_trivial_contradiction_and_duplicates() -> None:
    assert energy_lower_bound([[1], [-1]]) == pytest.approx(1.0)
    # duplicate literal inside a clause must not break soundness (x or x) & (not x)
    assert energy_lower_bound([[1, 1], [-1]]) <= 1.0 + 1e-9
    poly = multilinear_energy([[1, 1]])
    assert poly == {frozenset(): 1.0, frozenset({0}): -1.0}


@pytest.mark.parametrize("seed", range(10))
def test_qubo_is_exact(seed: int) -> None:
    cnf = random_ksat(4, 6, 3, seed=seed)
    cnf.clauses.append([2, -3])
    q, off, n_total = to_qubo(cnf.clauses, cnf.num_vars)
    for x in itertools.product([0, 1], repeat=cnf.num_vars):
        best = min(
            qubo_value(q, off, list(x) + list(w)) for w in itertools.product([0, 1], repeat=n_total - cnf.num_vars)
        )
        assert best == pytest.approx(cnf.num_violated(x))


def test_relaxation_gradient_matches_finite_differences() -> None:
    cnf = random_ksat(6, 20, 3, seed=3)
    ct = ClauseTensor.from_clauses(6, cnf.clauses)
    theta = np.random.default_rng(0).uniform(0.1, 0.9, 6)
    g = ct.gradient(theta)
    eps = 1e-6
    for i in range(6):
        d = np.zeros(6)
        d[i] = eps
        fd = (ct.energy(theta + d) - ct.energy(theta - d)) / (2 * eps)
        assert g[i] == pytest.approx(fd, rel=1e-5, abs=1e-7)


def test_relaxation_energy_equals_violations_at_binary_points() -> None:
    cnf = random_ksat(6, 25, 3, seed=11)
    ct = ClauseTensor.from_clauses(6, cnf.clauses)
    for bits in itertools.product([0, 1], repeat=6):
        assert ct.energy(np.array(bits, float)) == pytest.approx(cnf.num_violated(bits))


def test_relaxation_is_seeded_and_decreases_energy() -> None:
    cnf = random_ksat(30, 90, 3, seed=5)
    a = relax(30, cnf.clauses, steps=50, seed=1)
    b = relax(30, cnf.clauses, steps=50, seed=1)
    assert np.array_equal(a.theta, b.theta)
    assert a.energy_history[-1] < a.energy_history[0]
    assert ((a.theta >= 0) & (a.theta <= 1)).all()


def test_first_primes() -> None:
    assert first_primes(10).tolist() == [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
    assert first_primes(1000)[-1] == 7919
