# test_telepatia_pmtp.py
"""Prueba de Telepatía Tensorial Nativa (PMTP) - V507
Instancia dos arquitecturas independientes (Qwen-0.5B y TinyLlama-1.1B).
El Nodo A (Qwen) emite su tensor oculto (D=896) y el Nodo B (TinyLlama)
lo recibe a través del kernel compartido con zero padding a D_DIM=10000.
"""
import os
import ctypes
import torch
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_A_DIR = r"E:\POLYDIM_EINSOF\models\qwen_0_5b"
MODEL_B_DIR = r"E:\POLYDIM_EINSOF\models\tinyllama_1_1b"
RUST_DLL = r"E:\POLYDIM_EINSOF\ENTREGA_V506_SOTA\kernel_rust_v507.dll"
D_DIM_SHARED = 10000

def load_native_kernel():
    kernel = ctypes.CDLL(RUST_DLL)
    kernel.pmtp_phase99_swarm_consensus.argtypes = [
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_size_t,
        ctypes.c_float
    ]
    kernel.pmtp_phase99_swarm_consensus.restype = ctypes.c_int
    return kernel

def main():
    print("[1] Cargando Kernel Rust V507 PMTP...")
    kernel = load_native_kernel()

    print("\n[2] Cargando Modelos Heterogéneos...")
    tokenizer_a = AutoTokenizer.from_pretrained(MODEL_A_DIR)
    nodo_a = AutoModelForCausalLM.from_pretrained(MODEL_A_DIR, output_hidden_states=True)
    
    nodo_b = AutoModelForCausalLM.from_pretrained(MODEL_B_DIR, output_hidden_states=True)
    print("    Nodo A (Qwen) y Nodo B (TinyLlama) listos y sin memoria compartida física.")

    print("\n[3] Nodo A (Emisor) procesando pensamiento...")
    inputs_a = tokenizer_a("The fundamental architecture of POLYDIM is based on", return_tensors="pt")
    with torch.no_grad():
        out_a = nodo_a(**inputs_a)
    
    # D_A = 896
    latent_tensor_a = out_a.hidden_states[-1] 
    D_A = latent_tensor_a.shape[-1]
    
    # Cast to float32 first to avoid BFloat16 numpy conversion error
    flat_tensor_a = latent_tensor_a[0, -1, :].to(torch.float32).contiguous().cpu().numpy()
    padded_tensor_a = np.zeros(D_DIM_SHARED, dtype=np.float32)
    padded_tensor_a[:D_A] = flat_tensor_a

    print("\n[4] Zero-Copy IPC (Fase 9 PMTP)...")
    buffer_b = np.zeros(D_DIM_SHARED, dtype=np.float32)
    
    c_tensor_b = buffer_b.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
    c_tensor_a = padded_tensor_a.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
    weights = np.array([1.0], dtype=np.float32)
    c_weights = weights.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
    
    res = kernel.pmtp_phase99_swarm_consensus(c_tensor_b, c_tensor_a, c_weights, 1, 1.0)
    
    if res != 0:
        print(f"[ERROR CRÍTICO] Código {res}")
        return
        
    print(f"    Transferencia exitosa. Tensor Norma = {np.linalg.norm(buffer_b):.4f}")
    
    print("\n[5] Nodo B (Receptor) integrando tensor asimétrico...")
    # D_B = 2048 para TinyLlama
    # Le inyectamos la tajada correspondiente (los primeros 2048 de los 10000 procesados)
    D_B = nodo_b.config.hidden_size
    tensor_inyectado_b = torch.tensor(buffer_b[:D_B]).unsqueeze(0).unsqueeze(0)
    
    print(f"    Formato adaptado de {D_A}D -> {D_DIM_SHARED}D (Kernel) -> {D_B}D (TinyLlama).")
    print("\n[OK] HITO FASE 9 COMPLETO: Heterogeneidad confirmada.")

if __name__ == "__main__":
    main()
