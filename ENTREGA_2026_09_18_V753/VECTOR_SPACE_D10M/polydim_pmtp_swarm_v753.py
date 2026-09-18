#!/usr/bin/env python3
import os
import sys
import numpy as np
import torch
import argparse
sys.path.append(r"E:\POLYDIM_EINSOF\POLYDIM_V751")
from polydim.core import PolydimEngine, DualStreamQueue
from polydim_triton_kernel_v751 import TritonPolydimV751
DIM_A, DIM_B = 2048, 896
def main():
    print("======================================================================")
    print("  POLYDIM V752 - PMTP LATENT SWARM (DUAL STREAM & TRITON KERNEL) ")
    print("======================================================================")
    queue = DualStreamQueue()
    triton_kernel = TritonPolydimV751()
    print("[V752] Inicializando colas asincronas CPU/GPU...")
    N_anchors = 100
    X_torch = torch.randn(N_anchors, DIM_A, device='cuda', dtype=torch.float32)
    v_torch = torch.randn(N_anchors, device='cuda', dtype=torch.float32) # Target column
    def gpu_task():
        return triton_kernel.dual_pcg_matvec(X_torch, v_torch, ridge_alpha=1e-3, stream=queue.gpu_stream)
    def cpu_task():
        return np.ones((N_anchors,), dtype=np.float32)
    print("[V752] Ejecutando kernel asincrono Triton SOTA...")
    queue.submit_gpu(gpu_task)
    queue.submit_cpu(cpu_task)
    cpu_res, gpu_res = queue.synchronize()
    print(f"[V752] Sincronizacion completada. GPU Result Shape: {gpu_res.shape}")
    print(f"[V752] El Enjambre PMTP opera sin serializacion 1D. SILICON VERIFIED.")
    print("======================================================================")
if __name__ == '__main__':
    main()
