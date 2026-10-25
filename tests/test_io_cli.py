"""DIMACS parsing, config and CLI tests."""

from __future__ import annotations

import json

import pytest

from graphsat import CNF, DimacsError, SolverConfig, parse_dimacs
from graphsat.cli import main
from graphsat.core import PrimeSequence


def test_multiline_and_shared_line_clauses() -> None:
    cnf = CNF.from_dimacs("c hi\np cnf 3 3\n1 -2\n 3 0 -1 0\n2 3 0\n%\n0\n")
    assert cnf.clauses == [[1, -2, 3], [-1], [2, 3]]
    assert cnf.comments == ["hi"]


def test_roundtrip() -> None:
    cnf = CNF(num_vars=4, clauses=[[1, -4], [2], [-3, 4, 1]])
    assert CNF.from_dimacs(cnf.to_dimacs()).clauses == cnf.clauses


def test_strict_header_checks() -> None:
    with pytest.raises(DimacsError):
        CNF.from_dimacs("p cnf 2 5\n1 2 0\n", strict=True)
    with pytest.raises(DimacsError):
        CNF.from_dimacs("p cnf 1 1\n1 x 0\n")
    assert CNF.from_dimacs("p cnf 1 1\n1 5 0\n").num_vars == 5


def test_validation() -> None:
    with pytest.raises(ValueError):
        CNF(num_vars=2, clauses=[[3]])
    assert parse_dimacs("p cnf 2 1\n1 2 0") == (2, [[1, 2]])


def test_config_toml(tmp_path) -> None:
    p = tmp_path / "c.toml"
    p.write_text("[solver]\nrelax_steps = 5\ncertify = true\n")
    cfg = SolverConfig.from_toml(p)
    assert cfg.relax_steps == 5 and cfg.certify
    with pytest.raises(ValueError):
        SolverConfig.from_dict({"nope": 1})


def test_prime_sequence() -> None:
    assert PrimeSequence().get_nth_prime(100) == 541


def test_cli_solve_sat_and_unsat(tmp_path, capsys) -> None:
    sat = tmp_path / "s.cnf"
    sat.write_text("p cnf 2 2\n1 2 0\n-1 0\n")
    assert main(["solve", str(sat), "--json"]) == 10
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "SAT" and out["model"] == [-1, 2]

    php = tmp_path / "php.cnf"
    assert main(["gen", "pigeonhole", "--n", "3"]) == 0
    php.write_text(capsys.readouterr().out)
    proof = tmp_path / "p.drup"
    assert main(["solve", str(php), "--no-relax", "--proof", str(proof)]) == 20
    assert "certified=True" in capsys.readouterr().out
    assert proof.read_text().strip().endswith("0")


def test_cli_gen_random(capsys) -> None:
    main(["gen", "random", "--n", "10", "--alpha", "4", "--seed", "3"])
    cnf = CNF.from_dimacs(capsys.readouterr().out)
    assert cnf.num_vars == 10 and cnf.num_clauses == 40
