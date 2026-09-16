"""
POLYDIM V727 — TEST EMPÍRICO REAL (NO STUBS)
Compila: cl.exe /O2 /openmp /LD pmtp_kernel.cpp → pmtp_kernel.dll
         rustc --crate-type cdylib pmtp_kernel.rs → pmtp_kernel_rs.dll
Ejecuta: python test_v727_real.py
Genera:  test_v727_results.csv  (logs crudos)
"""
import ctypes, numpy as np, time, csv, sys, os

# ============================================================================
# CONFIG
# ============================================================================
DIM = 1_000_000      # D = 10^6
N_STEPS = 100        # 100 iteraciones Cayley
DT = 0.001           # paso temporal
TOLERANCE = 1e-10    # umbral de drift aceptable
CSV_PATH = os.path.join(os.path.dirname(__file__), "test_v727_results.csv")

# ============================================================================
# LOAD DLLs
# ============================================================================
src_dir = os.path.dirname(os.path.abspath(__file__))

cpp_dll_path = os.path.join(src_dir, "pmtp_kernel.dll")
rs_dll_path  = os.path.join(src_dir, "pmtp_kernel_rs.dll")

if not os.path.exists(cpp_dll_path):
    print(f"FATAL: No existe {cpp_dll_path}")
    sys.exit(1)
if not os.path.exists(rs_dll_path):
    print(f"FATAL: No existe {rs_dll_path}")
    sys.exit(1)

cpp_lib = ctypes.CDLL(cpp_dll_path)
rs_lib  = ctypes.CDLL(rs_dll_path)

# Prototype: int cayley_step_global_isometry(
#   const double* S, const double* V, double* S_next, double* V_next,
#   double* W_scratch, size_t dim, double dt)
c_double_p = ctypes.POINTER(ctypes.c_double)
for lib in [cpp_lib, rs_lib]:
    lib.cayley_step_global_isometry.restype = ctypes.c_int
    lib.cayley_step_global_isometry.argtypes = [
        c_double_p, c_double_p,  # S_in, V_in
        c_double_p, c_double_p,  # S_next, V_next
        c_double_p,              # W_scratch
        ctypes.c_size_t,         # dim
        ctypes.c_double          # dt
    ]

# ============================================================================
# NEUMAIER DOT (Python reference — compensated)
# ============================================================================
def neumaier_dot(x, y):
    s = 0.0; c = 0.0
    for i in range(len(x)):
        val = x[i] * y[i]
        t = s + val
        if abs(s) >= abs(val):
            c += (s - t) + val
        else:
            c += (val - t) + s
        s = t
    return s + c

# ============================================================================
# INIT VECTORS ON S^(D-1)
# ============================================================================
print(f"[POLYDIM V727 TEST] D={DIM:,}, N_STEPS={N_STEPS}, dt={DT}")
print(f"[INIT] Generando S aleatorio en S^(D-1)...")

rng = np.random.default_rng(seed=42)
S = rng.standard_normal(DIM)
norm_S = np.sqrt(np.sum(S * S))
S /= norm_S  # ||S|| = 1.0

# V tangente a S: V = V_rand - <V_rand, S>*S
V = rng.standard_normal(DIM)
V -= np.dot(V, S) * S

print(f"[INIT] ||S||={np.sqrt(np.sum(S*S)):.16e}  <S,V>={np.dot(S,V):.4e}")

# ============================================================================
# ALLOCATE BUFFERS
# ============================================================================
S_next = np.empty(DIM, dtype=np.float64)
V_next = np.empty(DIM, dtype=np.float64)
W_scratch = np.empty(DIM, dtype=np.float64)

def get_ptr(arr):
    return arr.ctypes.data_as(c_double_p)

# ============================================================================
# RUN CAYLEY LOOP — BOTH KERNELS
# ============================================================================
def run_kernel(lib, label, S0, V0):
    S_cur = S0.copy()
    V_cur = V0.copy()
    S_nxt = np.empty(DIM, dtype=np.float64)
    V_nxt = np.empty(DIM, dtype=np.float64)
    W_scr = np.empty(DIM, dtype=np.float64)
    
    results = []
    energy_0 = np.sum(V_cur * V_cur)
    
    print(f"\n{'='*70}")
    print(f"  KERNEL: {label}")
    print(f"  Energía inicial ||V||² = {energy_0:.16e}")
    print(f"{'='*70}")
    
    total_time = 0.0
    for step in range(1, N_STEPS + 1):
        t0 = time.perf_counter()
        rc = lib.cayley_step_global_isometry(
            get_ptr(S_cur), get_ptr(V_cur),
            get_ptr(S_nxt), get_ptr(V_nxt),
            get_ptr(W_scr),
            ctypes.c_size_t(DIM),
            ctypes.c_double(DT)
        )
        elapsed = time.perf_counter() - t0
        total_time += elapsed
        
        if rc != 0:
            print(f"  [STEP {step}] ERROR CODE {rc} — ABORTANDO")
            results.append([label, step, rc, 0, 0, 0, 0, elapsed])
            return results
        
        # Métricas
        norm_s = np.sqrt(np.sum(S_nxt * S_nxt))
        drift_s = abs(1.0 - norm_s)
        dot_sv = abs(np.dot(S_nxt, V_nxt))
        energy = np.sum(V_nxt * V_nxt)
        energy_drift = abs(energy - energy_0) / max(energy_0, 1e-300)
        
        results.append([label, step, rc, drift_s, dot_sv, energy, energy_drift, elapsed])
        
        if step <= 5 or step % 20 == 0 or step == N_STEPS:
            print(f"  [STEP {step:3d}] rc={rc}  ||S||-1={drift_s:.4e}  "
                  f"<S,V>={dot_sv:.4e}  ||V||²={energy:.6e}  "
                  f"E_drift={energy_drift:.4e}  t={elapsed*1000:.2f}ms")
        
        # Swap
        S_cur[:] = S_nxt
        V_cur[:] = V_nxt
    
    print(f"\n  TOTAL TIME: {total_time:.3f}s  AVG: {total_time/N_STEPS*1000:.2f}ms/step")
    
    # VEREDICTO
    max_drift = max(r[3] for r in results)
    max_tang  = max(r[4] for r in results)
    max_edrift = max(r[6] for r in results)
    
    PASS = max_drift < TOLERANCE and max_tang < TOLERANCE
    verdict = "[PASS]" if PASS else "[FAIL]"
    print(f"\n  VEREDICTO {label}: {verdict}")
    print(f"    max_drift_S  = {max_drift:.4e}  (tol={TOLERANCE:.0e})")
    print(f"    max_tang_SV  = {max_tang:.4e}  (tol={TOLERANCE:.0e})")
    print(f"    max_E_drift  = {max_edrift:.4e}")
    
    return results

all_results = []

# C++ kernel
all_results.extend(run_kernel(cpp_lib, "C++_cl.exe", S, V))

# Rust kernel
all_results.extend(run_kernel(rs_lib, "Rust_rustc", S, V))

# ============================================================================
# WRITE CSV
# ============================================================================
print(f"\n[CSV] Escribiendo {CSV_PATH}...")
with open(CSV_PATH, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(["kernel", "step", "rc", "drift_S", "tangencia_SV", 
                "energy_VV", "energy_drift_rel", "time_s"])
    w.writerows(all_results)

print(f"[CSV] {len(all_results)} filas escritas.")

# ============================================================================
# FINAL SUMMARY
# ============================================================================
cpp_rows = [r for r in all_results if r[0] == "C++_cl.exe"]
rs_rows  = [r for r in all_results if r[0] == "Rust_rustc"]

print(f"\n{'='*70}")
print(f"  RESUMEN FINAL V727 — {DIM:,} dimensiones × {N_STEPS} steps")
print(f"{'='*70}")

for label, rows in [("C++", cpp_rows), ("Rust", rs_rows)]:
    if not rows: continue
    errors = [r for r in rows if r[2] != 0]
    max_d = max(r[3] for r in rows)
    max_t = max(r[4] for r in rows)
    avg_ms = np.mean([r[7] for r in rows]) * 1000
    print(f"  {label:6s}: errors={len(errors)}  max_drift={max_d:.4e}  "
          f"max_tang={max_t:.4e}  avg_time={avg_ms:.2f}ms")

print(f"\n[DONE] Logs crudos en: {CSV_PATH}")
