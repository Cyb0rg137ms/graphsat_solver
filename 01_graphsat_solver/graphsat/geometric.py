"""
geometric.py
============
Helper functions for continuous coordinate relaxations of discrete satisfiability problems.
Exposes tools to run raw coordinate descent and output probability-like heuristics.
"""

from typing import List
from graphsat.core import ManifoldConstraintSolver

def extract_relaxation_heuristics(num_vars: int, clauses: List[List[int]], steps: int = 300) -> List[float]:
    """
    Runs only the continuous prime-coordinate mapping optimization phase of GraphSAT.
    Returns a list of float weights in the range [0.0, 1.0] indicating the 
    preferred probability of each variable being set to True (1).
    
    Args:
        num_vars: Number of boolean variables.
        clauses: List of DIMACS clauses.
        steps: Number of continuous gradient descent steps.
        
    Returns:
        List of continuous coordinates/probabilities for each variable.
    """
    solver = ManifoldConstraintSolver(num_vars, clauses)
    # Run the continuous solver phase
    solver.solve(max_steps=steps)
    return solver.coords
