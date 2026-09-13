import time
import torch
import os
from transformers import AutoTokenizer, AutoModelForCausalLM
import multiprocessing.shared_memory as shared_memory
import numpy as np

model_path = r"E:\POLYDIM_EINSOF\models\qwen_0_5b"

tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
model_A = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.float32, local_files_only=True)
model_B = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.float32, local_files_only=True)

HIDDEN_SIZE = model_A.config.hidden_size
SEQ_LEN = 16
SHM_SIZE = SEQ_LEN * HIDDEN_SIZE * 4 

try:
    shm = shared_memory.SharedMemory(name='pmtp_xray', create=True, size=SHM_SIZE)
except FileExistsError:
    shm = shared_memory.SharedMemory(name='pmtp_xray')

try:
    prompt = "Polydim destruye la serializacion 1D."
    inputs = tokenizer(prompt, return_tensors="pt", max_length=SEQ_LEN, padding="max_length", truncation=True)
    
    with torch.no_grad():
        outputs_A = model_A(**inputs, output_hidden_states=True)
        latent_tensor_A = outputs_A.hidden_states[-1].numpy().astype(np.float32)
    
    l2_norm_A = np.linalg.norm(latent_tensor_A)
    sample_A = latent_tensor_A[0, 0, :5]
    
    buffer = np.ndarray((1, SEQ_LEN, HIDDEN_SIZE), dtype=np.float32, buffer=shm.buf)
    buffer[:] = latent_tensor_A[:]
    
    latent_tensor_B = np.ndarray((1, SEQ_LEN, HIDDEN_SIZE), dtype=np.float32, buffer=shm.buf).copy()
    l2_norm_B = np.linalg.norm(latent_tensor_B)
    sample_B = latent_tensor_B[0, 0, :5]
    drift = np.max(np.abs(latent_tensor_A - latent_tensor_B))
    
    latent_tensor_mutado = latent_tensor_B * 1.5
    
    with torch.no_grad():
        logits_B = model_B.lm_head(torch.tensor(latent_tensor_B))
        decoded_original = tokenizer.decode(torch.argmax(logits_B, dim=-1)[0], skip_special_tokens=True)
        
        logits_mutado = model_B.lm_head(torch.tensor(latent_tensor_mutado))
        decoded_mutado = tokenizer.decode(torch.argmax(logits_mutado, dim=-1)[0], skip_special_tokens=True)

    log = f"""
================= RAYOS-X DEL TENSOR (PMTP) =================
1. FORMA DEL ESPACIO: {latent_tensor_A.shape} (D={HIDDEN_SIZE})
2. BYTES ZERO-COPY:   {SHM_SIZE} bytes en OS IPC
3. NORMA L2 EMISOR:   {l2_norm_A:.6f}
4. NORMA L2 RECEPTOR: {l2_norm_B:.6f}
5. VECTOR CRUDO (Extracto de 5 dimensiones S^D-1):
   -> EMISOR:   {sample_A}
   -> RECEPTOR: {sample_B}
6. DRIFT MATEMATICO:  {drift} (0.0 = Identidad Absoluta)
-------------------------------------------------------------
7. DECODIFICACION INTACTA (Nodo B proyectando el latente crudo):
   [{decoded_original}]
8. DECODIFICACION MUTADA (Tensor deformado por factor Escalar 1.5):
   [{decoded_mutado}]
=============================================================
"""
    with open('E:\\POLYDIM_EINSOF\\ENTREGA_2026_09_12_V507\\telemetria_xray.txt', 'w', encoding='utf-8') as f:
        f.write(log.strip())
        
finally:
    shm.close()
    shm.unlink()
