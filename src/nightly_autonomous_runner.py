import ctypes
import numpy as np
import time
import os
import sys
import datetime

DLL_PATH = r"E:\POLYDIM_EINSOF\src\pmtp_kernel.dll"

def log_telemetry(msg):
    log_file = r"E:\POLYDIM_EINSOF\NOCTURNO_TELEMETRIA_CONTINUA.md"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.strip(), flush=True)

def run_continuous_silicon_test():
    log_telemetry("=== INICIANDO PROTOCOLO AUTÓNOMO MODO NOCTURNO ===")
    
    if not os.path.exists(DLL_PATH):
        log_telemetry(f"ERROR FATAL: DLL not found at {DLL_PATH}")
        sys.exit(1)
        
    dll = ctypes.CDLL(DLL_PATH)
    c_double_p = ctypes.POINTER(ctypes.c_double)
    
    dll.cayley_step_global_isometry.restype = ctypes.c_int
    dll.cayley_step_global_isometry.argtypes = [
        c_double_p, c_double_p,  # S_in, V_in
        c_double_p, c_double_p,  # S_next, V_next
        c_double_p,              # W_scratch
        ctypes.c_size_t,         # dim
        ctypes.c_double          # dt
    ]

    D = 1_000_000
    DT = 0.001
    log_telemetry(f"Instanciando Stiefel manifold D={D}")
    
    S = np.random.randn(D).astype(np.float64)
    S /= np.linalg.norm(S)
    V = np.random.randn(D).astype(np.float64)
    V -= np.dot(V, S) * S  # Ortogonalizar
    
    S_next = np.empty(D, dtype=np.float64)
    V_next = np.empty(D, dtype=np.float64)
    W_scratch = np.empty(D, dtype=np.float64)
    
    cycle = 0
    while True:
        cycle += 1
        start_t = time.perf_counter()
        
        rc = dll.cayley_step_global_isometry(
            S.ctypes.data_as(c_double_p), V.ctypes.data_as(c_double_p),
            S_next.ctypes.data_as(c_double_p), V_next.ctypes.data_as(c_double_p),
            W_scratch.ctypes.data_as(c_double_p),
            ctypes.c_size_t(D),
            ctypes.c_double(DT)
        )
        
        end_t = time.perf_counter()
        
        if rc != 0:
            log_telemetry(f"CRASH: Error code {rc} en ciclo {cycle}")
            sys.exit(1)
            
        norm_s = np.linalg.norm(S_next)
        drift = abs(1.0 - norm_s)
        
        # Swap memory via direct assignment is safe here for continuous test
        np.copyto(S, S_next)
        np.copyto(V, V_next)
        
        if cycle % 1000 == 0:
            log_telemetry(f"Ciclo {cycle} | D={D} | Drift_S={drift:.2e} | Latencia={((end_t-start_t)*1000):.2f}ms")
            
        if drift > 1e-10:
            log_telemetry(f"ALERTA TOPOLÓGICA: Drift asintótico superado en ciclo {cycle}: {drift:.2e}")
            S /= norm_s # Auto-repair
            
        # Pequeño delay para no freir la CPU en modo continuo 24/7
        time.sleep(0.001)

if __name__ == "__main__":
    try:
        run_continuous_silicon_test()
    except Exception as e:
        log_telemetry(f"CRASH FATAL en Runner: {e}")
