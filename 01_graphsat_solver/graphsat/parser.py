"""
parser.py
=========
Parses boolean satisfiability problem files in standard DIMACS CNF format.
"""

from typing import List, Tuple

def parse_dimacs(content: str) -> Tuple[int, List[List[int]]]:
    """
    Parses DIMACS CNF file content.
    
    Args:
        content: The text content of the DIMACS file.
        
    Returns:
        A tuple of (num_variables, list_of_clauses)
    """
    clauses = []
    num_vars = 0
    
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('c'):
            # Skip empty lines and comments
            continue
            
        if line.startswith('p cnf'):
            parts = line.split()
            if len(parts) >= 4:
                num_vars = int(parts[2])
            continue
            
        # Parse clauses (which end with a 0)
        try:
            literals = [int(x) for x in line.split()]
            if literals:
                if literals[-1] == 0:
                    literals = literals[:-1]
                if literals:
                    clauses.append(literals)
        except ValueError:
            # Handle malformed lines gracefully
            continue
            
    return num_vars, clauses
