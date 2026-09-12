""" NODE A: Creador de la Memoria Compartida OS (Zero-Copy) """
from multiprocessing import shared_memory
import numpy as np
import time

DIM = 10000
SHM_NAME = 'polydim_pmtp_bus_v507'

print(f"[NODE A] Creando Memoria Compartida OS '{SHM_NAME}'...")
try:
    shm = shared_memory.SharedMemory(create=True, name=SHM_NAME, size=DIM * 4)
    tensor_a = np.ndarray((DIM,), dtype=np.float32, buffer=shm.buf)
    
    # Generar data
    tensor_a[:] = np.random.randn(DIM).astype(np.float32)
    hash_val = np.sum(tensor_a)
    print(f"[NODE A] Tensor escrito directamente en el Bus de Memoria OS.")
    print(f"[NODE A] Hash de envío: {hash_val:.6f}")
    
    print("[NODE A] Esperando 10 segundos para que Node B se conecte y lea...")
    time.sleep(10)
    
finally:
    print("[NODE A] Cerrando y liberando memoria OS compartida...")
    shm.close()
    shm.unlink()
    print("[NODE A] Finalizado.")
