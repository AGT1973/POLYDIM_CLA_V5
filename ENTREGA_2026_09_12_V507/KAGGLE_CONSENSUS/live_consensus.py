import torch
import time
import multiprocessing.shared_memory as shared_memory
import numpy as np
from transformers import AutoTokenizer, AutoModelForCausalLM
import multiprocessing
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KAGGLE_FULL_DUPLEX")

def node_phi3(shm_name, tensor_shape):
    logger.info("[NODO A - PHI-3] Cargando en cuda:0...")
    model = AutoModelForCausalLM.from_pretrained("microsoft/Phi-3-mini-4k-instruct", torch_dtype=torch.float16, device_map="cuda:0")
    
    shm = shared_memory.SharedMemory(name=shm_name)
    buffer = np.ndarray(tensor_shape[0] * tensor_shape[1] * tensor_shape[2] + 1, dtype=np.float32, buffer=shm.buf)
    
    logger.info("[NODO A] Inyectando pensamiento inicial (Tensor D=3072)...")
    estado_latente = torch.randn(1, 16, 3072)
    buffer[1:] = estado_latente.numpy().flatten()
    
    logger.info("[NODO A] Tensor transferido al Blackboard OS. Esperando respuesta (Ping)...")
    buffer[0] = 1.0 
    
    while buffer[0] != 2.0:
        time.sleep(0.1)
        
    logger.info("[NODO A] Respuesta neural detectada (Pong). Leyendo Blackboard...")
    estado_devuelto = torch.tensor(buffer[1:].reshape(1, 16, 3072))
    distancia = torch.norm(estado_latente - estado_devuelto).item()
    
    logger.info(f"[NODO A] DRIFT MATEMATICO FULL-DUPLEX: {distancia:.4f} (Tensor procesado por el cortex de Alibaba y devuelto a Microsoft)")
    shm.close()

def node_qwen(shm_name, tensor_shape):
    logger.info("[NODO B - QWEN 2.5] Cargando en cuda:1...")
    model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct", torch_dtype=torch.float16, device_map="cuda:1")
    
    shm = shared_memory.SharedMemory(name=shm_name)
    buffer = np.ndarray(tensor_shape[0] * tensor_shape[1] * tensor_shape[2] + 1, dtype=np.float32, buffer=shm.buf)
    
    logger.info("[NODO B] Escuchando pasivamente el Blackboard...")
    while buffer[0] != 1.0:
        time.sleep(0.1)
        
    logger.info("[NODO B] Mensaje recibido de Occidente. Leyendo tensor D=3072...")
    tensor_recibido = torch.tensor(buffer[1:].reshape(1, 16, 3072), dtype=torch.float16).to("cuda:1")
    
    logger.info("[NODO B] Traduccion dimensional (3072 -> 1536) e inyeccion en capa de Atencion Qwen...")
    # Qwen 1.5B tiene D=1536. Truncamos, pasamos por la capa, y paddeamos de vuelta.
    tensor_reducido = tensor_recibido[:, :, :1536]
    
    with torch.no_grad():
        salida_qwen = model.model.layers[0](tensor_reducido)[0]
        
    logger.info("[NODO B] Inferencia cruzada terminada. Traduccion inversa (1536 -> 3072)...")
    tensor_respuesta = torch.nn.functional.pad(salida_qwen, (0, 3072 - 1536))
    
    logger.info("[NODO B] Devolviendo respuesta (Pong) al Blackboard...")
    buffer[1:] = tensor_respuesta.cpu().numpy().astype(np.float32).flatten()
    buffer[0] = 2.0 
    
    shm.close()

if __name__ == "__main__":
    shm_name = "kaggle_full_duplex"
    tensor_shape = (1, 16, 3072)
    size_bytes = (np.prod(tensor_shape) + 1) * 4
    
    try:
        shm = shared_memory.SharedMemory(name=shm_name, create=True, size=size_bytes)
    except FileExistsError:
        shm = shared_memory.SharedMemory(name=shm_name)
        
    buffer = np.ndarray(np.prod(tensor_shape) + 1, dtype=np.float32, buffer=shm.buf)
    buffer[0] = 0.0
    
    pA = multiprocessing.Process(target=node_phi3, args=(shm_name, tensor_shape))
    pB = multiprocessing.Process(target=node_qwen, args=(shm_name, tensor_shape))
    
    logger.info("INICIANDO CONVERSACION FULL-DUPLEX LATENTE EN KAGGLE T4x2")
    pB.start()
    pA.start()
    
    pA.join()
    pB.join()
    
    shm.close()
    shm.unlink()
    logger.info("CONVERSACION CLOUD FINALIZADA")
