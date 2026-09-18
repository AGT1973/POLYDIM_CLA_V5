#!/usr/bin/env python3
import os
import sys
import time
import numpy as np
sys.path.append(r"E:\POLYDIM_EINSOF\POLYDIM_V751")
from polydim.core import PolydimEngine
def main():
    print("==========================================================")
    print("  POLYDIM V752 - FFI BENCHMARK (RODRIGUES GEODESIC) ")
    print("==========================================================")
    cpp_dll = r"E:\POLYDIM_EINSOF\POLYDIM_V751\bin\polydim_kernel.dll"
    if not os.path.exists(cpp_dll):
        print(f"[FATAL] DLL not found: {cpp_dll}")
        return
    engine = PolydimEngine(cpp_dll_path=cpp_dll)
    D = 10_000_000
    iters = 10
    print(f"Dimension: {D:,} | Iterations: {iters}")
    y = np.ones(D, dtype=np.float64)
    y /= np.linalg.norm(y)
    y_comp = np.zeros(D, dtype=np.float64)
    u = np.random.randn(D).astype(np.float64)
    u /= np.linalg.norm(u)
    v = np.random.randn(D).astype(np.float64)
    v -= np.dot(u, v) * u
    v /= np.linalg.norm(v)
    theta = 0.1
    engine.rotate_geodesic(y, y_comp, u, v, theta, 0)
    t0 = time.perf_counter()
    for _ in range(iters):
        engine.rotate_geodesic(y, y_comp, u, v, theta, 0)
    t1 = time.perf_counter()
    fps = iters / (t1 - t0)
    print(f"[C++ Native FFI] Time: {t1-t0:.3f}s | FPS: {fps:.2f} iters/s")
    print(f"[Validation] Final L2 Norm: {np.linalg.norm(y):.12f} (Target 1.0)")
    print("==========================================================")
if __name__ == '__main__':
    main()
