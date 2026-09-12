""" NODE B: Lector de la Memoria Compartida OS (Zero-Copy) """
from multiprocessing import shared_memory
import numpy as np
import time

DIM = 10000
SHM_NAME = 'polydim_pmtp_bus_v507'

print(f"[NODE B] Intentando conectar a la Memoria Compartida OS '{SHM_NAME}'...")
# Retry loop por si A tarda en levantar
for _ in range(5):
    try:
        shm = shared_memory.SharedMemory(name=SHM_NAME)
        break
    except FileNotFoundError:
        print("[NODE B] Memoria aún no disponible. Reintentando en 1s...")
        time.sleep(1)
else:
    print("[NODE B] ERROR: No se pudo conectar al bus OS.")
    exit(1)

try:
    tensor_b = np.ndarray((DIM,), dtype=np.float32, buffer=shm.buf)
    hash_val = np.sum(tensor_b)
    print(f"[NODE B] Tensor interceptado vía ZERO-COPY IPC (Sin deserializar).")
    print(f"[NODE B] Hash de recepción: {hash_val:.6f}")
    print("[NODE B] ¡Transmisión PMTP OS-Level exitosa!")
finally:
    shm.close()
    print("[NODE B] Desconectado del Bus.")
