import time
import torch
import os
from transformers import AutoTokenizer, AutoModelForCausalLM
import multiprocessing.shared_memory as shared_memory
import numpy as np

model_path = r"E:\POLYDIM_EINSOF\models\qwen_0_5b"
print('====================================================')
print(f'CARGANDO MODELO LOCAL ESTRICTO DESDE: {model_path}')
print('====================================================')

# Forzamos la carga local. Si el path no existe o no tiene los safetensors, fallará miserablemente.
tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
model_A = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.float32, local_files_only=True)
model_B = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.float32, local_files_only=True)

print('LOS DOS MODELOS QWEN FUERON CARGADOS EN RAM SATISFACTORIAMENTE.')

HIDDEN_SIZE = model_A.config.hidden_size
SEQ_LEN = 32
SHM_SIZE = SEQ_LEN * HIDDEN_SIZE * 4 

try:
    shm = shared_memory.SharedMemory(name='pmtp_qwen_local', create=True, size=SHM_SIZE)
except FileExistsError:
    shm = shared_memory.SharedMemory(name='pmtp_qwen_local')

iteration = 0
try:
    while True:
        iteration += 1
        
        # 1. TAREA EN NODO A
        prompt = f"El usuario exige resultados empíricos reales en la iteración {iteration}."
        inputs = tokenizer(prompt, return_tensors="pt", max_length=SEQ_LEN, padding="max_length", truncation=True)
        
        with torch.no_grad():
            outputs_A = model_A(**inputs, output_hidden_states=True)
            latent_tensor_A = outputs_A.hidden_states[-1].numpy().astype(np.float32) 
        
        # 2. TRANSFERENCIA PMTP
        buffer = np.ndarray((1, SEQ_LEN, HIDDEN_SIZE), dtype=np.float32, buffer=shm.buf)
        buffer[:] = latent_tensor_A[:]
        
        # 3. NODO B LEE Y DECODIFICA
        latent_tensor_B = np.ndarray((1, SEQ_LEN, HIDDEN_SIZE), dtype=np.float32, buffer=shm.buf).copy()
        drift = np.max(np.abs(latent_tensor_A - latent_tensor_B))
        
        with torch.no_grad():
            latent_pt = torch.tensor(latent_tensor_B)
            logits_B = model_B.lm_head(latent_pt)
            predicted_ids = torch.argmax(logits_B, dim=-1)
            decoded_text = tokenizer.decode(predicted_ids[0], skip_special_tokens=True)
            
        output_str = f"[ITER {iteration}] | DRIFT: {drift} | DECODIFICACION NODO B: {decoded_text}\n"
        print(output_str.strip())
        
        with open('E:\\POLYDIM_EINSOF\\ENTREGA_2026_09_12_V507\\output_qwen_estricto_log.txt', 'a', encoding='utf-8') as f:
            f.write(output_str)
            
        time.sleep(1)

except KeyboardInterrupt:
    pass
finally:
    shm.close()
    shm.unlink()
