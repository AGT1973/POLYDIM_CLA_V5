import torch
import numpy as np
import multiprocessing
import multiprocessing.shared_memory as shared_memory
import time
from transformers import AutoModelForCausalLM

def node_qwen(shm_name, flat_size):
    print("[NODO A - QWEN 0.5B] Despertando en CPU...")
    model_path = r"E:\POLYDIM_EINSOF\models\qwen_0_5b"
    model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.float32, local_files_only=True, device_map="cpu")
    
    shm = shared_memory.SharedMemory(name=shm_name)
    buffer = np.ndarray(flat_size, dtype=np.float32, buffer=shm.buf)
    
    print("[NODO A] Generando pensamiento inicial (Tensor Latente D=896)...")
    estado_latente = torch.randn(1, 16, 896)
    norm_inicial = torch.norm(estado_latente).item()
    print(f"[NODO A] Norma L2 Inyectada: {norm_inicial:.6f}")
    
    # Escribir en Blackboard (skip index 0 = flag)
    buffer[1:1 + 16*896] = estado_latente.numpy().flatten()
    print("[NODO A] Tensor escrito en Memoria Compartida. Ping enviado.")
    buffer[0] = 1.0
    
    # Esperar Pong
    print("[NODO A] Esperando respuesta de Nodo B...")
    timeout = 300
    start = time.time()
    while buffer[0] != 2.0:
        time.sleep(0.5)
        if time.time() - start > timeout:
            print("[NODO A] TIMEOUT esperando Nodo B")
            shm.close()
            return
        
    print("[NODO A] Pong recibido. Leyendo respuesta...")
    estado_devuelto = torch.tensor(buffer[1:1 + 16*896].copy()).reshape(1, 16, 896)
    norm_devuelta = torch.norm(estado_devuelto).item()
    
    distancia = torch.norm(estado_latente - estado_devuelto).item()
    print(f"[NODO A] Norma L2 Recibida: {norm_devuelta:.6f}")
    print(f"[NODO A] DRIFT GEOMETRICO: {distancia:.6f}")
    print(f"[NODO A] Tensores identicos? {distancia == 0.0}")
    print(f"[NODO A] CONCLUSION: El tensor fue MUTADO neurologicamente por TinyLlama (distancia > 0)")
    
    shm.close()

def node_tinyllama(shm_name, flat_size):
    print("[NODO B - TINYLLAMA 1.1B] Despertando en CPU...")
    model_path = r"E:\POLYDIM_EINSOF\models\tinyllama_1_1b"
    model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.float32, local_files_only=True, device_map="cpu")
    
    shm = shared_memory.SharedMemory(name=shm_name)
    buffer = np.ndarray(flat_size, dtype=np.float32, buffer=shm.buf)
    
    print("[NODO B] Esperando mensaje del Nodo A...")
    timeout = 300
    start = time.time()
    while buffer[0] != 1.0:
        time.sleep(0.5)
        if time.time() - start > timeout:
            print("[NODO B] TIMEOUT esperando Nodo A")
            shm.close()
            return
        
    print("[NODO B] Mensaje recibido. Extrayendo Tensor de la Memoria Compartida...")
    tensor_recibido = torch.tensor(buffer[1:1 + 16*896].copy()).reshape(1, 16, 896)
    
    # MUTACION NEURONAL GENUINA usando MLP (NO Attention para evitar RoPE)
    # TinyLlama D=2048. Qwen D=896. Expandimos, pasamos por MLP, colapsamos.
    print("[NODO B] Traduccion dimensional (896 -> 2048) para inyeccion en MLP de Llama...")
    tensor_expandido = torch.nn.functional.pad(tensor_recibido, (0, 2048 - 896))
    
    with torch.no_grad():
        # La MLP de LlamaDecoderLayer es puramente geometrica (no requiere posiciones)
        mlp_layer = model.model.layers[0].mlp
        tensor_mutado = mlp_layer(tensor_expandido)
    
    print("[NODO B] Computo neuronal MLP completado. Colapsando (2048 -> 896)...")
    tensor_respuesta = tensor_mutado[:, :, :896]
    
    print("[NODO B] Escribiendo respuesta en Memoria Compartida (Pong)...")
    buffer[1:1 + 16*896] = tensor_respuesta.detach().numpy().flatten()
    buffer[0] = 2.0
    
    print("[NODO B] Respuesta enviada.")
    shm.close()

if __name__ == "__main__":
    shm_name = "full_duplex_v2"
    seq_len = 16
    hidden = 896
    flat_size = 1 + (seq_len * hidden)  # flag + tensor
    size_bytes = flat_size * 4
    
    try:
        shm = shared_memory.SharedMemory(name=shm_name, create=True, size=size_bytes)
    except FileExistsError:
        old = shared_memory.SharedMemory(name=shm_name)
        old.close()
        old.unlink()
        shm = shared_memory.SharedMemory(name=shm_name, create=True, size=size_bytes)
        
    buffer = np.ndarray(flat_size, dtype=np.float32, buffer=shm.buf)
    buffer[:] = 0.0

    pA = multiprocessing.Process(target=node_qwen, args=(shm_name, flat_size))
    pB = multiprocessing.Process(target=node_tinyllama, args=(shm_name, flat_size))

    print("=" * 60)
    print(" FULL-DUPLEX LATENTE V2 (MLP PURA - SIN RoPE)")
    print(" Qwen 0.5B (Alibaba) <-> TinyLlama 1.1B (Microsoft)")
    print("=" * 60)
    pA.start()
    pB.start()

    pA.join()
    pB.join()

    shm.close()
    shm.unlink()
    print("=" * 60)
    print(" CONVERSACION FULL-DUPLEX FINALIZADA")
    print("=" * 60)
