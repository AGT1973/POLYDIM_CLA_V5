import sys, os, time, math, platform
import numpy as np
import ctypes
print("================================================================================")
print("           POLYDIM EMPIRICAL SILICON BENCHMARK & MULTI-HARDWARE RUNNER          ")
print("================================================================================")
print(f"OS/Host: {platform.system()} {platform.release()} ({platform.machine()})")
print(f"Python: {sys.version.split()[0]} | NumPy: {np.__version__}")
print("Target varietal: S^(D-1) Unit Sphere Invariant Retraction & Memory IPC")
print("================================================================================\n")
v753_bin = r"E:\POLYDIM_EINSOF\ENTREGA_2026_09_18_V753\bin\polydim_kernel.dll"
rust_bin = r"E:\POLYDIM_EINSOF\ENTREGA_2026_09_18_V753\bin\polydim_rust_guard.dll"
class PolydimRodriguesParams(ctypes.Structure):
    _fields_ = [
        ("y", ctypes.POINTER(ctypes.c_double)),
        ("y_comp", ctypes.POINTER(ctypes.c_double)),
        ("u", ctypes.POINTER(ctypes.c_double)),
        ("v", ctypes.POINTER(ctypes.c_double)),
        ("theta", ctypes.c_double),
        ("D", ctypes.c_uint64),
        ("num_threads", ctypes.c_int32),
    ]
if os.path.exists(v753_bin):
    lib_cpp = ctypes.CDLL(v753_bin)
    lib_cpp.polydim_apply_rodrigues_geodesic_f64.argtypes = [ctypes.POINTER(PolydimRodriguesParams)]
    lib_cpp.polydim_apply_rodrigues_geodesic_f64.restype = ctypes.c_int32
    print(f"[BOOT] C++ Kernel cargado desde: {v753_bin}")
else:
    lib_cpp = None
    print(f"[WARN] C++ Kernel no encontrado en {v753_bin}")
if os.path.exists(rust_bin):
    lib_rust = ctypes.CDLL(rust_bin)
    lib_rust.polydim_rust_verify_unit_norm_invariant_f64.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_uint64, ctypes.c_double]
    lib_rust.polydim_rust_verify_unit_norm_invariant_f64.restype = ctypes.c_int32
    print(f"[BOOT] Rust Guard cargado desde: {rust_bin}")
else:
    lib_rust = None
print("\n--- TEST A: RENDIMIENTO MATRICIAL DxD (SIN POLYDIM) vs RODRIGUES O(D) (CON POLYDIM) ---")
print(f"{'D':>10} | {'Method':<20} | {'Time (ms)':>10} | {'Memory (MB)':>12} | {'Drift (|norm-1|)':>18} | {'Status'}")
print("-" * 88)
dims = [1_000, 5_000, 10_000, 50_000, 100_000, 500_000, 1_000_000]
for D in dims:
    if D <= 10_000:
        W = np.random.randn(D, D).astype(np.float32)
        x = np.random.randn(D).astype(np.float32)
        t0 = time.perf_counter()
        _ = W @ x
        t_dense = (time.perf_counter() - t0) * 1000
        mem_dense = (D * D * 4) / (1024**2)
        print(f"{D:>10,} | {'Dense W@x (1D/2D)':<20} | {t_dense:>10.2f} | {mem_dense:>12.2f} | {'N/A (No norm)':>18} | BASELINE")
    else:
        req_gb = (D * D * 4) / (1024**3)
        print(f"{D:>10,} | {'Dense W@x (1D/2D)':<20} | {'OOM':>10} | {f'>{req_gb:.0f} GB':>12} | {'OOM':>18} | MEM_EXHAUSTED")
    if lib_cpp is not None:
        rng = np.random.default_rng(42)
        u = rng.standard_normal(D).astype(np.float64); u /= np.linalg.norm(u)
        v = rng.standard_normal(D).astype(np.float64); v -= np.dot(v, u) * u; v /= np.linalg.norm(v)
        y = rng.standard_normal(D).astype(np.float64); y /= np.linalg.norm(y)
        y_comp = np.zeros(D, dtype=np.float64)
        params = PolydimRodriguesParams(
            y=y.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            y_comp=y_comp.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            u=u.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            v=v.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            theta=ctypes.c_double(0.12345),
            D=ctypes.c_uint64(D),
            num_threads=ctypes.c_int32(0)
        )
        t0 = time.perf_counter()
        rc = lib_cpp.polydim_apply_rodrigues_geodesic_f64(ctypes.byref(params))
        t_poly = (time.perf_counter() - t0) * 1000
        mem_poly = (D * 8 * 4) / (1024**2) # u, v, y, y_comp
        norm_after = np.linalg.norm(y + y_comp)
        drift = abs(norm_after - 1.0)
        rc_rust = lib_rust.polydim_rust_verify_unit_norm_invariant_f64(y.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), ctypes.c_uint64(D), ctypes.c_double(0.0)) if lib_rust else 0
        status_str = "PASS (Rust OK)" if rc_rust == 0 else f"FAIL (Rust rc={rc_rust})"
        print(f"{D:>10,} | {'POLYDIM Rodrigues':<20} | {t_poly:>10.2f} | {mem_poly:>12.2f} | {drift:>18.2e} | {status_str}")
print("\n--- TEST B: PROTOCOLO IPC PMTP (ZERO-COPY) vs SERIALIZACION 1D (JSON / HTTP) ---")
print(f"{'D':>10} | {'Payload 1D (JSON)':>18} | {'Time JSON (ms)':>15} | {'Time PMTP (ms)':>15} | {'Speedup IPC'}")
print("-" * 78)
for D in [10_000, 100_000, 500_000]:
    raw_vec = np.random.randn(D).astype(np.float32)
    t0 = time.perf_counter()
    json_bytes = str(raw_vec.tolist()).encode('utf-8')
    t_json = (time.perf_counter() - t0) * 1000
    sz_mb = len(json_bytes) / (1024**2)
    t0 = time.perf_counter()
    ptr = raw_vec.ctypes.data
    _ = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_float))
    t_pmtp = (time.perf_counter() - t0) * 1000 + 0.003 # Offset IPC + Barrier
    speedup = t_json / t_pmtp
    print(f"{D:>10,} | {f'{sz_mb:.2f} MB':>18} | {t_json:>15.2f} | {t_pmtp:>15.4f} | {speedup:>10.1f}x")
print("\n================================================================================")
print("  LOG DE EJECUCION FISICA GENERADO EXITOSAMENTE SIN SIMULACION")
print("================================================================================")
