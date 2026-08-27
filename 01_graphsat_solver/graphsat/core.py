"""
core.py
=======
Core solver engine for the GraphSAT Prime-Manifold Topological SAT Solver.
Combines exact algebraic lower-bounds (via Rosenberg reduction) with continuous 
coordinate relaxations and DPLL topological propagation.
"""

import math
import random
import time
from typing import List, Tuple, Dict, Optional, Union

class PrimeSequence:
    """Generates deterministic prime coordinates for constraint spacing."""
    
    def __init__(self):
        self._primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
        
    def get_nth_prime(self, n: int) -> int:
        """Get the nth prime (1-indexed)."""
        while len(self._primes) < n:
            candidate = self._primes[-1] + 2
            while True:
                is_prime = True
                for p in self._primes:
                    if p * p > candidate:
                        break
                    if candidate % p == 0:
                        is_prime = False
                        break
                if is_prime:
                    self._primes.append(candidate)
                    break
                candidate += 2
        return self._primes[n - 1]

class ManifoldConstraintSolver:
    """
    Solves boolean satisfiability problems by embedding discrete constraints
    into a continuous prime-vector coordinate manifold.
    """
    
    def __init__(self, num_vars: int, clauses: List[List[int]], coupling_strength: float = 0.086):
        """
        Args:
            num_vars: Total number of boolean variables.
            clauses: List of boolean clauses (DIMACS format).
            coupling_strength: Strength of prime-coordinate manifold spacing constraints.
        """
        self.num_vars = num_vars
        self.clauses = clauses
        self.coupling = coupling_strength
        
        # Initialize prime coordinate spacings
        prime_seq = PrimeSequence()
        self.prime_coordinates = [prime_seq.get_nth_prime(i + 1) for i in range(num_vars)]
        
        # Initialize continuous coordinates in [0, 1] with small random perturbation
        self.coords = [0.5 + random.uniform(-0.01, 0.01) for _ in range(num_vars)]
        
    def _evaluate_penalty(self, coords: List[float], clause: List[int]) -> float:
        """Evaluates the penalty polynomial for a given clause at current coordinates."""
        penalty = 1.0
        for lit in clause:
            var_idx = abs(lit) - 1
            if lit > 0:
                penalty *= (1.0 - coords[var_idx])
            else:
                penalty *= coords[var_idx]
        return penalty

    def compute_algebraic_lower_bound(self) -> float:
        """
        Computes the exact algebraic lower bound of the 3-SAT constraint energy
        via a Rosenberg cubic-to-quadratic reduction.
        
        Returns:
            The minimum energy bound. If > 0, the instance is mathematically UNSAT.
        """
        c_term = 0.0
        lin_terms = [0.0] * self.num_vars
        quad_terms = [[0.0] * self.num_vars for _ in range(self.num_vars)]
        
        y_lin_terms = []
        y_quad_terms = []
        
        for clause in self.clauses:
            def expand_lit(lit):
                # Returns (constant, linear_multiplier, variable_index)
                return (1.0, -1.0, abs(lit) - 1) if lit > 0 else (0.0, 1.0, abs(lit) - 1)
                
            if len(clause) == 1:
                c1, l1, idx1 = expand_lit(clause[0])
                c_term += c1
                lin_terms[idx1] += l1
                
            elif len(clause) == 2:
                c1, l1, idx1 = expand_lit(clause[0])
                c2, l2, idx2 = expand_lit(clause[1])
                c_term += c1 * c2
                lin_terms[idx2] += c1 * l2
                lin_terms[idx1] += c2 * l1
                quad_terms[idx1][idx2] += l1 * l2
                
            elif len(clause) == 3:
                # 3-SAT exact QUBO Rosenberg Reduction
                c1, l1, idx1 = expand_lit(clause[0])
                c2, l2, idx2 = expand_lit(clause[1])
                c3, l3, idx3 = expand_lit(clause[2])
                
                # Expand: (c1 + l1*x)(c2 + l2*y)(c3 + l3*z)
                c_term += c1 * c2 * c3
                lin_terms[idx3] += c1 * c2 * l3
                lin_terms[idx2] += c1 * c3 * l2
                lin_terms[idx1] += c2 * c3 * l1
                
                quad_terms[idx2][idx3] += c1 * l2 * l3
                quad_terms[idx1][idx3] += c2 * l1 * l3
                quad_terms[idx1][idx2] += c3 * l1 * l2
                
                # Introduce auxiliary variable w = x * y to reduce cubic product (l1*l2*l3 * x * y * z)
                coeff = l1 * l2 * l3
                if coeff != 0:
                    y_idx = len(y_lin_terms)
                    y_lin_terms.append(0.0)
                    y_quad_terms.append([0.0] * self.num_vars)
                    
                    # Add penalty: 2 * |coeff| * (x*y - 2*x*w - 2*y*w + 3*w)
                    penalty = abs(coeff) * 2.0
                    quad_terms[idx1][idx2] += penalty
                    y_quad_terms[y_idx][idx1] += -2.0 * penalty
                    y_quad_terms[y_idx][idx2] += -2.0 * penalty
                    y_lin_terms[y_idx] += 3.0 * penalty
                    
                    # original cubic coeff * x * y * z becomes quadratic: coeff * w * z
                    y_quad_terms[y_idx][idx3] += coeff
                    
        # Calculate algebraic L1 minimum over [0,1] hypercube
        min_bound = c_term
        for i in range(self.num_vars):
            worst_lin = min(0.0, lin_terms[i])
            worst_quad = sum(min(0.0, quad_terms[i][j]) for j in range(self.num_vars) if i != j)
            min_bound += (worst_lin + worst_quad)
            
        for y in range(len(y_lin_terms)):
            worst_lin = min(0.0, y_lin_terms[y])
            worst_quad = sum(min(0.0, y_quad_terms[y][j]) for j in range(self.num_vars))
            min_bound += (worst_lin + worst_quad)
            
        return min_bound

    def _dpll(self, clauses: List[List[int]], assignment: List[Optional[int]], depth: int = 0) -> bool:
        """Topological DPLL backtracking search with continuous relaxation heuristics."""
        # 1. Unit propagation loop
        while True:
            unit_found = False
            for c in clauses:
                unassigned = [lit for lit in c if assignment[abs(lit) - 1] is None]
                is_sat = any(assignment[abs(lit) - 1] == (1 if lit > 0 else 0) for lit in c if assignment[abs(lit) - 1] is not None)
                if not is_sat and len(unassigned) == 1:
                    lit = unassigned[0]
                    assignment[abs(lit) - 1] = 1 if lit > 0 else 0
                    unit_found = True
            if not unit_found:
                break
                
        # 2. Check conflicts and satisfaction status
        all_satisfied = True
        for c in clauses:
            is_sat = False
            is_conflict = True
            for lit in c:
                val = assignment[abs(lit) - 1]
                if val is None:
                    is_conflict = False
                elif val == (1 if lit > 0 else 0):
                    is_sat = True
                    is_conflict = False
                    break
            if is_conflict:
                return False
            if not is_sat:
                all_satisfied = False
                
        if all_satisfied:
            return True
            
        # 3. Decision phase: select variables using coordinates from relaxation
        unassigned_vars = [i for i, v in enumerate(assignment) if v is None]
        if not unassigned_vars:
            return False
            
        # Branch on the variable whose continuous coordinate is furthest from 0.5 (highest certainty)
        decision_var = max(unassigned_vars, key=lambda i: abs(self.coords[i] - 0.5))
        decision_val = 1 if self.coords[decision_var] > 0.5 else 0
        
        # Try preferred choice
        assignment[decision_var] = decision_val
        if self._dpll(clauses, assignment, depth + 1):
            return True
            
        # Backtrack and try alternative choice
        assignment[decision_var] = 1 - decision_val
        if self._dpll(clauses, assignment, depth + 1):
            return True
            
        # Reset and backtrack
        assignment[decision_var] = None
        return False

    def solve(self, max_steps: int = 500, lr: float = 0.1) -> Tuple[str, Union[float, List[int]]]:
        """
        Solves the satisfiability problem.
        
        Returns:
            A tuple containing:
                - status: "SAT" or "UNSAT"
                - solution/bound: A list of variable assignments if SAT, or the mass gap bound if UNSAT.
        """
        # Step 1: Compute algebraic energy bound to detect quick UNSAT
        mass_gap = self.compute_algebraic_lower_bound()
        if mass_gap > 1e-3:
            return "UNSAT", mass_gap
            
        # Step 2: Continuous coordinates optimization via gradient descent
        for _ in range(max_steps):
            energy = sum(self._evaluate_penalty(self.coords, c) for c in self.clauses)
            if energy < 1e-4:
                break
                
            grads = [0.0] * self.num_vars
            for c in self.clauses:
                p = self._evaluate_penalty(self.coords, c)
                if p > 0:
                    for lit in c:
                        var_idx = abs(lit) - 1
                        p_i = (1.0 - self.coords[var_idx]) if lit > 0 else self.coords[var_idx]
                        if p_i > 1e-9:
                            grads[var_idx] += (p / p_i) * (-1.0 if lit > 0 else 1.0)
                            
            # Add topological coupling constraint gradients
            if self.coupling > 0:
                for i in range(self.num_vars):
                    for j in range(self.num_vars):
                        if i != j:
                            coordinate_distance = abs(self.prime_coordinates[i] - self.prime_coordinates[j])
                            grads[i] += (self.coupling / coordinate_distance) * math.sin(math.pi * (self.coords[i] - self.coords[j]))
                            
            # Apply coordinate update
            for i in range(self.num_vars):
                self.coords[i] -= lr * grads[i] / math.log(max(self.prime_coordinates[i], 2))
                self.coords[i] = max(0.0, min(1.0, self.coords[i]))
                
        # Step 3: Complete Backtracking DPLL
        assignment = [None] * self.num_vars
        is_sat = self._dpll(self.clauses, assignment)
        
        if is_sat:
            return "SAT", [v if v is not None else 0 for v in assignment]
        else:
            return "UNSAT", -1.0

    def verify(self, assignment: List[int]) -> bool:
        """Verifies if the given variable assignment satisfies all clauses."""
        for c in self.clauses:
            if not any(assignment[abs(lit) - 1] == (1 if lit > 0 else 0) for lit in c):
                return False
        return True
