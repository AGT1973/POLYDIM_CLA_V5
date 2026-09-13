import torch
import numpy as np
import multiprocessing
import multiprocessing.shared_memory as shared_memory
import time
from transformers import AutoModelForCausalLM

def node_qwen(shm_name, tensor_shape):
    print("[NODO A - QWEN 0.5B] Despertando en CPU...")
    model_path = r"E:\POLYDIM_EINSOF\models\qwen_0_5b"
    model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.float32, local_files_only=True, device_map="cpu")
    
    shm = shared_memory.SharedMemory(name=shm_name)
    # buffer[0] = Flag, buffer[1:] = Tensor
    buffer = np.ndarray(tensor_shape[0] * tensor_shape[1] * tensor_shape[2] + 1, dtype=np.float32, buffer=shm.buf)
    
    print("[NODO A] Generando pensamiento inicial (Tensor Latente)...")
    # Generamos un estado latente dummy (1, 16, 1024) que simula la salida de Qwen
    estado_latente = torch.randn(1, 16, 1024)
    norm_inicial = torch.norm(estado_latente).item()
    print(f"[NODO A] Norma L2 Inyectada: {norm_inicial:.4f}")
    
    # Escribir en Blackboard
    buffer[1:] = estado_latente.numpy().flatten()
    print("[NODO A] Tensor escrito en Memoria Compartida. Avisando al Nodo B (Ping)...")
    buffer[0] = 1.0 # FLAG: Nodo A terminó de hablar
    
    # Esperar respuesta de Nodo B
    print("[NODO A] Escuchando respuesta pasivamente...")
    while buffer[0] != 2.0:
        time.sleep(0.1)
        
    print("[NODO A] Respuesta detectada (Pong). Leyendo Memoria Compartida...")
    estado_devuelto = torch.tensor(buffer[1:].reshape(1, 16, 1024))
    norm_devuelta = torch.norm(estado_devuelto).item()
    
    distancia = torch.norm(estado_latente - estado_devuelto).item()
    print(f"[NODO A] Norma L2 Recibida: {norm_devuelta:.4f}")
    print(f"[NODO A] DRIFT GEOMETRICO DE LA CONVERSACION: {distancia:.4f} (El tensor fue mutado neurologicamente)")
    
    shm.close()

def node_tinyllama(shm_name, tensor_shape):
    print("[NODO B - TINYLLAMA 1.1B] Despertando en CPU...")
    model_path = r"E:\POLYDIM_EINSOF\models\tinyllama_1_1b"
    model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.float32, local_files_only=True, device_map="cpu")
    
    shm = shared_memory.SharedMemory(name=shm_name)
    buffer = np.ndarray(tensor_shape[0] * tensor_shape[1] * tensor_shape[2] + 1, dtype=np.float32, buffer=shm.buf)
    
    print("[NODO B] Esperando mensaje del Nodo A...")
    while buffer[0] != 1.0:
        time.sleep(0.1)
        
    print("[NODO B] Mensaje recibido. Extrayendo Tensor de la Memoria Compartida...")
    tensor_recibido = torch.tensor(buffer[1:].reshape(1, 16, 1024), dtype=torch.float32)
    
    # Transformacion Neuronal Genuina:
    # TinyLlama tiene D=2048. Qwen tiene D=1024.
    # Expandimos, pasamos por la primera capa de atencion de Llama, y colapsamos.
    print("[NODO B] Traduccion dimensional (1024 -> 2048) e inyeccion en Cortex Llama...")
    tensor_expandido = torch.nn.functional.pad(tensor_recibido, (0, 1024)) # Pad a 2048
    
    with torch.no_grad():
        # Pasamos el tensor por la capa 0 de TinyLlama
        salida_llama, _, _ = model.model.layers[0](tensor_expandido)
    
    print("[NODO B] Computo neuronal completado. Colapsando (2048 -> 1024)...")
    tensor_respuesta = salida_llama[:, :, :1024]
    
    print("[NODO B] Escribiendo respuesta en Memoria Compartida (Pong)...")
    buffer[1:] = tensor_respuesta.numpy().flatten()
    buffer[0] = 2.0 # FLAG: Nodo B terminó de responder
    
    shm.close()

if __name__ == "__main__":
    import numpy as np
    
    shm_name = "full_duplex_blackboard"
    tensor_shape = (1, 16, 1024)
    # Total floats: (1 * 16 * 1024) + 1 (for flag)
    size_bytes = (np.prod(tensor_shape) + 1) * 4
    
    try:
        shm = shared_memory.SharedMemory(name=shm_name, create=True, size=size_bytes)
    except FileExistsError:
        shm = shared_memory.SharedMemory(name=shm_name)
        
    buffer = np.ndarray(np.prod(tensor_shape) + 1, dtype=np.float32, buffer=shm.buf)
    buffer[0] = 0.0 # Estado inicial: silencio
    
    pA = multiprocessing.Process(target=node_qwen, args=(shm_name, tensor_shape))
    pB = multiprocessing.Process(target=node_tinyllama, args=(shm_name, tensor_shape))
    
    print("==================================================")
    print(" INICIANDO CONVERSACION FULL-DUPLEX LATENTE (LOCAL)")
    print("==================================================")
    pB.start()
    pA.start()
    
    pA.join()
    pB.join()
    
    shm.close()
    shm.unlink()
    print("==================================================")
    print(" CONVERSACION FINALIZADA Y MEMORIA PURGADA")
    print("==================================================")
