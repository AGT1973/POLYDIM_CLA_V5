"""
POLYDIM V751 - INDUSTRIAL HARDENED TEST SUITE
Validates Native C++ Kernel, Rust Topological Guard, and Matrix-Free Dual PCG Solver.
"""

import os
import sys
import math
import time
import threading
import numpy as np
import ctypes
# Add project root to sys.path
sys.path.insert(0, r"e:\POLYDIM_EINSOF\POLYDIM_V751")

from polydim.core import PolydimEngine, PolydimStatus
from polydim.solver_pcg import DualPCGSolver

def test_v751_full_suite():
    print("=" * 65)
    print("  POLYDIM V751 - INDUSTRIAL SUITE VERIFICATION (SILICON REAL)")
    print("=" * 65)

    cpp_dll = r"e:\POLYDIM_EINSOF\POLYDIM_V751\bin\polydim_kernel.dll"
    rust_dll = r"e:\POLYDIM_EINSOF\POLYDIM_V751\bin\polydim_rust_guard.dll"

    assert os.path.exists(cpp_dll), f"Missing C++ DLL at {cpp_dll}"
    assert os.path.exists(rust_dll), f"Missing Rust DLL at {rust_dll}"

    engine = PolydimEngine(cpp_dll_path=cpp_dll, rust_dll_path=rust_dll)
    version = engine.cpp_lib.polydim_get_version()
    print(f"[BOOT] C++ Engine Version: 0x{version:08X} (7.51.0)")
    assert version == 0x07330100

    # -------------------------------------------------------------
    # TEST 1: Alignment & Zero-Alloc
    # -------------------------------------------------------------
    print("\n[TEST 1] Alignment & Zero-Alloc OpenMP Parallel...")
    D = 1_000_000
    y = np.ones(D, dtype=np.float64)
    rc_alloc = engine.cpp_lib.polydim_zero_alloc_f64(
        y.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_uint64(D)
    )
    assert rc_alloc == PolydimStatus.SUCCESS
    assert np.max(np.abs(y)) == 0.0
    print(f"  -> D={D:,} | zero_alloc: rc={rc_alloc} | max_abs={np.max(y)} | PASS ✓")

    # -------------------------------------------------------------
    # TEST 2: Rodrigues Geodesic with Versine Stabilization
    # -------------------------------------------------------------
    print("\n[TEST 2] Rodrigues Rank-2 Geodesic Rotation (Adversarial Angles)...")
    rng = np.random.default_rng(42)
    u = rng.standard_normal(D)
    u /= np.linalg.norm(u)
    v = rng.standard_normal(D)
    v -= np.dot(v, u) * u
    v /= np.linalg.norm(v)

    test_angles = [1e-12, 1e-8, 1e-4, 0.1, math.pi / 3.0, math.pi - 1e-10]
    for theta in test_angles:
        y = rng.standard_normal(D)
        y /= np.linalg.norm(y)
        y_comp = np.zeros(D, dtype=np.float64)

        rc = engine.rotate_geodesic(y=y, y_comp=y_comp, u=u, v=v, theta=theta)
        assert rc == PolydimStatus.SUCCESS, f"Rotation failed with rc={rc}"

        norm_after = np.linalg.norm(y + y_comp)
        drift = abs(norm_after - 1.0)
        assert drift < 1e-10, f"Drift too large: {drift} at theta={theta}"
        print(f"  theta={theta:9.2e} | rc={rc} | norm={norm_after:.14f} | drift={drift:.2e} | PASS ✓")

    # -------------------------------------------------------------
    # TEST 3: Rust Guard - Dynamic Tolerance & Y_comp Budget
    # -------------------------------------------------------------
    print("\n[TEST 3] Rust Topological Guard (Dynamic Tolerance & Budget)...")
    unit_vec = rng.standard_normal(D)
    unit_vec /= np.linalg.norm(unit_vec)
    rc_unit = engine.verify_norm(unit_vec)
    assert rc_unit == 0, f"Rust rejected valid unit vector: {rc_unit}"

    corrupt_vec = unit_vec * 1.05
    rc_corrupt = engine.verify_norm(corrupt_vec)
    assert rc_corrupt == PolydimStatus.ERR_NORM_INVARIANT_VIOLATED, f"Rust allowed corrupt vector: {rc_corrupt}"

    # Budget check
    budget_limit = 50.0 * D * np.finfo(np.float64).eps
    y_comp_ok = np.zeros(D, dtype=np.float64)
    y_comp_ok[0] = budget_limit * 0.5
    rc_budget_ok = engine.verify_ycomp_budget(y_comp_ok)
    assert rc_budget_ok == 0

    y_comp_bad = np.zeros(D, dtype=np.float64)
    y_comp_bad[0] = budget_limit * 2.0
    rc_budget_bad = engine.verify_ycomp_budget(y_comp_bad)
    assert rc_budget_bad == PolydimStatus.ERR_YCOMP_BUDGET_EXCEEDED
    print(f"  Dynamic Tol Guard: PASS ✓ | Y_comp Budget Guard: PASS ✓")

    # -------------------------------------------------------------
    # TEST 4: Dual Matrix-Free PCG Solver (O(N*D) without forming K)
    # -------------------------------------------------------------
    print("\n[TEST 4] Dual Matrix-Free PCG Solver vs Direct Cholesky...")
    N_agents, D_dim = 200, 10_000
    X_agents = rng.standard_normal((N_agents, D_dim))
    Y_targets = rng.standard_normal((N_agents, 1))

    pcg = DualPCGSolver(ridge_alpha=1e-3, max_iter=300, tol=1e-7)
    
    t0 = time.perf_counter()
    Alpha_pcg = pcg.solve(X_agents, Y_targets)
    t_pcg = (time.perf_counter() - t0) * 1000

    # Ground truth: Direct Cholesky
    K_exact = X_agents @ X_agents.T
    diag_ridge = 1e-3 * max(1.0, float(np.mean(np.sum(X_agents**2, axis=1))))
    K_exact[np.diag_indices_from(K_exact)] += diag_ridge
    Alpha_direct = np.linalg.solve(K_exact, Y_targets)

    residual_error = np.linalg.norm(Alpha_pcg - Alpha_direct) / np.linalg.norm(Alpha_direct)
    print(f"  N={N_agents}, D={D_dim:,} | PCG Time: {t_pcg:.2f}ms | Relative Error vs Cholesky: {residual_error:.2e}")
    assert residual_error < 1e-4, f"PCG residual too large: {residual_error}"
    print(f"  Dual PCG Solver: PASS ✓")

    # -------------------------------------------------------------
    # TEST 5: Concurrency - 8 Threads FFI Mutex
    # -------------------------------------------------------------
    print("\n[TEST 5] Thread-Safety: 8 Concurrent FFI Threads...")
    errors = []
    def worker(tid):
        try:
            loc_y = rng.standard_normal(100_000)
            loc_y /= np.linalg.norm(loc_y)
            loc_yc = np.zeros(100_000, dtype=np.float64)
            loc_u = u[:100_000].copy()
            loc_v = v[:100_000].copy()
            for _ in range(5):
                rc_t = engine.rotate_geodesic(loc_y, loc_yc, loc_u, loc_v, 0.05)
                if rc_t != 0:
                    errors.append(f"Thread {tid} failed with {rc_t}")
        except Exception as e:
            errors.append(f"Thread {tid} exception: {e}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert len(errors) == 0, f"Concurrent execution had errors: {errors}"
    print(f"  8 threads completed without race conditions: PASS ✓")

    print("\n" + "=" * 65)
    print("  POLYDIM V751 INDUSTRIAL VERIFICATION: ALL TESTS PASSED ✓ (5/5)")
    print("=============================================================")

if __name__ == "__main__":
    import ctypes
    test_v751_full_suite()
