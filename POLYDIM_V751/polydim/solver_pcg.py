"""
POLYDIM V751 - Dual Preconditioned Conjugate Gradient (PCG) Solver
Evaluates dual ridge alignment in O(N * D) space without materializing the Gram matrix K = X X^T.
"""

import numpy as np
from typing import Tuple, Optional

class DualPCGSolver:
    """
    Solves (X X^T + ridge * I) Alpha = Y in the dual subspace.
    Uses Matrix-Free Preconditioned Conjugate Gradient (PCG) with Jacobi preconditioning.
    
    Memory: O(N * D + N * output_dim), NEVER O(D * D) or explicit O(N * N) if N is massive.
    """
    def __init__(self, ridge_alpha: float = 1e-4, max_iter: int = 500, tol: float = 1e-6):
        self.ridge_alpha = float(ridge_alpha)
        self.max_iter = int(max_iter)
        self.tol = float(tol)

    def solve(self, X: np.ndarray, Y: np.ndarray) -> np.ndarray:
        """
        Args:
            X: Agent state matrix of shape (N, D)
            Y: Target response matrix of shape (N, M)
        Returns:
            Alpha: Dual coefficients matrix of shape (N, M)
        """
        N, D = X.shape
        if N == 0 or D == 0:
            raise ValueError("Dimensions must be positive non-zero.")
        if Y.shape[0] != N:
            raise ValueError(f"Shape mismatch: X has {N} rows, Y has {Y.shape[0]} rows.")

        X_f64 = np.ascontiguousarray(X, dtype=np.float64)
        Y_f64 = np.ascontiguousarray(Y, dtype=np.float64)
        
        # Diagonal preconditioned Jacobi weights: diag(K) = sum(X_i^2, axis=1)
        row_norms_sq = np.einsum('ij,ij->i', X_f64, X_f64)
        scaled_ridge = self.ridge_alpha * max(1.0, float(np.mean(row_norms_sq)))
        diag_K = row_norms_sq + scaled_ridge
        inv_diag_M = 1.0 / np.maximum(diag_K, 1e-12) # Preconditioner M^{-1}

        M_targets = Y_f64.shape[1] if Y_f64.ndim > 1 else 1
        Alpha = np.zeros((N, M_targets), dtype=np.float64)
        
        # Matrix-free linear operator: A(v) = (X @ (X.T @ v)) + scaled_ridge * v
        def matvec(v: np.ndarray) -> np.ndarray:
            # Step 1: w = X.T @ v  (D, cols) -> intermediate vector in R^D
            w = X_f64.T @ v
            # Step 2: out = X @ w  (N, cols) -> back to dual space R^N
            return (X_f64 @ w) + (scaled_ridge * v)

        # Solve for each target column (or vectorized)
        for col in range(M_targets):
            b = Y_f64[:, col] if Y_f64.ndim > 1 else Y_f64
            x = np.zeros(N, dtype=np.float64)
            r = b - matvec(x)
            z = inv_diag_M * r # Apply Jacobi preconditioner
            p = z.copy()
            rz_old = np.dot(r, z)

            norm_b = np.linalg.norm(b)
            if norm_b == 0.0:
                continue

            for iteration in range(self.max_iter):
                Ap = matvec(p)
                pAp = np.dot(p, Ap)
                if pAp <= 1e-30:
                    break # Reached numerical limit

                alpha = rz_old / pAp
                x += alpha * p
                r -= alpha * Ap

                if np.linalg.norm(r) / norm_b < self.tol:
                    break # Converged

                z = inv_diag_M * r
                rz_new = np.dot(r, z)
                beta = rz_new / rz_old
                p = z + beta * p
                rz_old = rz_new

            if Y_f64.ndim > 1:
                Alpha[:, col] = x
            else:
                Alpha[:, 0] = x

        return Alpha

def apply_dual_alignment(X: np.ndarray, Y: np.ndarray, ridge_alpha: float = 1e-4) -> np.ndarray:
    return DualPCGSolver(ridge_alpha).solve(X, Y)
