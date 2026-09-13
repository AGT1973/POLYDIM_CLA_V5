import time
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import multiprocessing.shared_memory as shared_memory
import numpy as np

print('=== INICIANDO CARGA FÍSICA DE MODELOS EN RAM ===')
print('Cargando Qwen/Qwen1.5-0.5B (Nodo A y Nodo B)... Esto disparará tu RAM.')

# Cargar Modelo A y B reales en memoria (consumirá ~2GB de RAM)
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen1.5-0.5B")
model_A = AutoModelForCausalLM.from_pretrained("Qwen/Qwen1.5-0.5B", torch_dtype=torch.float32)
model_B = AutoModelForCausalLM.from_pretrained("Qwen/Qwen1.5-0.5B", torch_dtype=torch.float32)

print('Modelos cargados exitosamente. Observa tu Administrador de Tareas.')

# Configurar memoria compartida
HIDDEN_SIZE = model_A.config.hidden_size # 1024 para Qwen 0.5B
SEQ_LEN = 16
SHM_SIZE = SEQ_LEN * HIDDEN_SIZE * 4 # float32

try:
    shm = shared_memory.SharedMemory(name='pmtp_real_model', create=True, size=SHM_SIZE)
except FileExistsError:
    shm = shared_memory.SharedMemory(name='pmtp_real_model')

iteration = 0
try:
    while True:
        iteration += 1
        print(f'\n--- ITERACION {iteration} ---')
        
        # NODO A: Ingiere texto, tokeniza y extrae el estado latente real
        input_text = f"La telemetria tensorial en iteracion {iteration} es absoluta."
        inputs = tokenizer(input_text, return_tensors="pt", max_length=SEQ_LEN, padding="max_length", truncation=True)
        
        with torch.no_grad():
            # Extraemos el hidden_state real (la cognicion en S^(D-1))
            outputs_A = model_A(**inputs, output_hidden_states=True)
            latent_tensor_A = outputs_A.hidden_states[-1].numpy().astype(np.float32) # (1, 16, 1024)
        
        # Nodo A escribe a PMTP (Memoria Compartida)
        buffer = np.ndarray((1, SEQ_LEN, HIDDEN_SIZE), dtype=np.float32, buffer=shm.buf)
        buffer[:] = latent_tensor_A[:]
        print(f'NODO A: Texto "{input_text}" inyectado como Tensor Real.')
        
        time.sleep(0.1) # Simulacion latencia IPC
        
        # NODO B: Lee el tensor de la PMTP
        latent_tensor_B = np.ndarray((1, SEQ_LEN, HIDDEN_SIZE), dtype=np.float32, buffer=shm.buf).copy()
        
        # Verificacion del Drift
        drift = np.max(np.abs(latent_tensor_A - latent_tensor_B))
        print(f'NODO B: Tensor recibido. Drift Isométrico: {drift}')
        
        # Extraemos un pseudo-output (proyectando el tensor de vuelta a logits usando Nodo B)
        with torch.no_grad():
            latent_pt = torch.tensor(latent_tensor_B)
            logits_B = model_B.lm_head(latent_pt)
            predicted_ids = torch.argmax(logits_B, dim=-1)
            decoded_text = tokenizer.decode(predicted_ids[0], skip_special_tokens=True)
            
        print(f'NODO B Decodificó: {decoded_text}')
        
        # Guardamos log en disco para cumplir con el output
        with open('output_real_models.txt', 'a', encoding='utf-8') as f:
            f.write(f"Iter {iteration} | Nodo A: {input_text} | Nodo B Decode: {decoded_text} | Drift: {drift}\n")
            
        time.sleep(1)

except KeyboardInterrupt:
    print('Bucle detenido.')
finally:
    shm.close()
    shm.unlink()
