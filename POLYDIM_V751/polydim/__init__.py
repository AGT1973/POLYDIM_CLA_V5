"""
POLYDIM V751 - High-Dimensional Geometric Tensor & Native Agent Swarm Engine
"""

from .core import PolydimEngine, PolydimStatus
from .solver_pcg import DualPCGSolver

__version__ = "7.51.0"
__all__ = ["PolydimEngine", "PolydimStatus", "DualPCGSolver"]
