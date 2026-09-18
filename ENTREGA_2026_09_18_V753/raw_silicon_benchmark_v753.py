import sys, os, time, math, platform
import numpy as np
import ctypes

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

lib_cpp = ctypes.CDLL(v753_bin)
lib_cpp.polydim_apply_rodrigues_geodesic_f64.argtypes = [ctypes.POINTER(PolydimRodriguesParams)]
lib_cpp.polydim_apply_rodrigues_geodesic_f64.restype = ctypes.c_int32

lib_rust = ctypes.CDLL(rust_bin)
lib_rust.polydim_rust_verify_unit_norm_invariant_f64.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_uint64, ctypes.c_double]
lib_rust.polydim_rust_verify_unit_norm_invariant_f64.restype = ctypes.c_int32

print("================================================================================")
print("     POLYDIM EMPIRICAL SILICON BENCHMARK: FUSED 2-PASS + NEUMAIER COMPOSITE     ")
print("================================================================================")

dims = [1_000, 5_000, 10_000, 50_000, 100_000, 500_000, 1_000_000]

print(f"{'D':>10} | {'Method':<20} | {'Time (ms)':>10} | {'Memory (MB)':>12} | {'Drift (|norm-1|)':>18} | {'Status'}")
print("-" * 88)

for D in dims:
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
    mem_poly = (D * 8 * 4) / (1024**2)

    # Vector completo integrado con su compensacion Neumaier
    y_final = (y + y_comp).astype(np.float64)
    norm_after = np.linalg.norm(y_final)
    drift = abs(norm_after - 1.0)

    rc_rust = lib_rust.polydim_rust_verify_unit_norm_invariant_f64(
        y_final.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_uint64(D),
        ctypes.c_double(0.0)
    )

    status_str = "PASS (Rust OK)" if rc_rust == 0 else f"FAIL (Rust rc={rc_rust})"
    print(f"{D:>10,} | {'POLYDIM Rodrigues':<20} | {t_poly:>10.2f} | {mem_poly:>12.2f} | {drift:>18.2e} | {status_str}")

print("================================================================================")
