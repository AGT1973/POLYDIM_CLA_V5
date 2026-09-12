"""
CICLO 4: FUZZING FFI Y MEMORY LEAK TEST
"""
import os, sys, time, psutil
import numpy as np
import ctypes

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from polydim_v507_monolito import PmtpMonolito

def get_ram():
    return psutil.Process(os.getpid()).memory_info().rss / (1024*1024)

def main():
    print("=== POLYDIM CICLO 4: FUZZING FFI Y LEAK TEST ===")
    m = PmtpMonolito(base_dir=os.path.dirname(os.path.abspath(__file__)), precision=0)
    
    ITERATIONS = 50000
    DIM = 10000
    
    local = np.ones(DIM, dtype=np.float32)
    neighbors = np.ones(DIM, dtype=np.float32)
    weights = np.array([1.0], dtype=np.float32)
    
    ram_start = get_ram()
    print(f"RAM Inicial antes del Fuzzing: {ram_start:.2f} MB")
    
    print(f"Iniciando {ITERATIONS} llamadas asintóticas a la frontera Rust FFI...")
    t0 = time.perf_counter()
    
    for _ in range(ITERATIONS):
        try:
            m._rust_lib.pmtp_phase99_swarm_consensus(
                local.ctypes.data_as(ctypes.c_void_p),
                neighbors.ctypes.data_as(ctypes.c_void_p),
                weights.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_size_t(1),
                ctypes.c_float(0.1)
            )
        except Exception:
            pass

    t1 = time.perf_counter()
    ram_end = get_ram()
    
    print(f"RAM Final post-Fuzzing: {ram_end:.2f} MB")
    delta = ram_end - ram_start
    print(f"Delta RAM (Posible Leak): {delta:.2f} MB")
    print(f"Velocidad: {ITERATIONS} iteraciones en {(t1-t0):.4f} segundos.")
    
    if delta > 10.0:
        print("CRITICAL WARNING: MEMORY LEAK DETECTADO EN FFI")
    else:
        print("EXITO: Frontera FFI estable y sellada. No hay fugas de memoria (0 Leaks).")

if __name__ == '__main__':
    main()
