import os

with open(r"E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V507\codigo_nodo_A.txt", "r", encoding="utf-8") as f:
    code_A = f.read()

with open(r"E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V507\codigo_nodo_B.txt", "r", encoding="utf-8") as f:
    code_B = f.read()

final_script = f'''import multiprocessing
import multiprocessing.shared_memory as shared_memory
import numpy as np
import time

# --- MENTE OCCIDENTAL (TINYLLAMA) ---
{code_A}

# --- MENTE ORIENTAL (QWEN) ---
{code_B}

if __name__ == "__main__":
    shm_name = "blackboard_historico"
    tensor_shape = (500,)
    size = int(np.prod(tensor_shape) * 4)
    
    print(">> [SISTEMA] Creando Memoria Compartida Ciega...")
    try:
        shm = shared_memory.SharedMemory(name=shm_name, create=True, size=size)
    except FileExistsError:
        shm = shared_memory.SharedMemory(name=shm_name)
        
    buffer = np.ndarray(tensor_shape, dtype=np.float32, buffer=shm.buf)
    buffer[0] = 0.0

    print(">> [SISTEMA] Disparando IA Occidental (A) y Oriental (B)...")
    pA = multiprocessing.Process(target=node_a_producer, args=(shm_name, tensor_shape))
    pB = multiprocessing.Process(target=node_b_consumer, args=(shm_name, tensor_shape))

    pB.start()
    time.sleep(1)
    pA.start()

    pA.join()
    pB.join()

    print(">> [SISTEMA] Consenso alcanzado exitosamente.")
    shm.close()
    shm.unlink()
'''

with open(r"E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V507\consenso_ciego_final.py", "w", encoding="utf-8") as f:
    f.write(final_script)
print("Ensamblaje del codigo cruzado finalizado con exito.")
