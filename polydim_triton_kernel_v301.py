# POLYDIM INFINITY V301 - TRITON KERNEL
# Aceleración Geométrica de Tensores para D >= 10,000 en VRAM Nativa

import torch
import triton
import triton.language as tl

@triton.jit
def procrustes_rotation_kernel(
    tensor_ptr, rot_matrix_ptr, out_ptr, 
    D, # Dimensionalidad (Ej: 10000)
    stride_tn, stride_td,
    stride_rn, stride_rd,
    stride_on, stride_od,
    BLOCK_SIZE_M: tl.constexpr, 
    BLOCK_SIZE_N: tl.constexpr, 
    BLOCK_SIZE_K: tl.constexpr
):
    """
    Triton Kernel: Multiplicación de Matrices optimizada para VRAM.
    Aplica la matriz de rotación R de Procrustes directamente en la GPU
    evitando la sobrecarga del intérprete de Python y PyTorch.
    """
    pid = tl.program_id(axis=0)
    num_pid_m = tl.cdiv(1, BLOCK_SIZE_M) # Procesamos 1 vector (pensamiento) a la vez
    num_pid_n = tl.cdiv(D, BLOCK_SIZE_N)
    
    pid_m = pid // num_pid_n
    pid_n = pid % num_pid_n

    offs_am = (pid_m * BLOCK_SIZE_M + tl.arange(0, BLOCK_SIZE_M)) % 1
    offs_bn = (pid_n * BLOCK_SIZE_N + tl.arange(0, BLOCK_SIZE_N)) % D
    offs_k = tl.arange(0, BLOCK_SIZE_K)
    
    a_ptrs = tensor_ptr + (offs_am[:, None] * stride_tn + offs_k[None, :] * stride_td)
    b_ptrs = rot_matrix_ptr + (offs_k[:, None] * stride_rn + offs_bn[None, :] * stride_rd)
    
    accumulator = tl.zeros((BLOCK_SIZE_M, BLOCK_SIZE_N), dtype=tl.float32)
    
    for k in range(0, tl.cdiv(D, BLOCK_SIZE_K)):
        a = tl.load(a_ptrs, mask=offs_k[None, :] < D - k * BLOCK_SIZE_K, other=0.0)
        b = tl.load(b_ptrs, mask=offs_k[:, None] < D - k * BLOCK_SIZE_K, other=0.0)
        accumulator += tl.dot(a, b)
        
        a_ptrs += BLOCK_SIZE_K * stride_td
        b_ptrs += BLOCK_SIZE_K * stride_rn
        
    offs_cm = pid_m * BLOCK_SIZE_M + tl.arange(0, BLOCK_SIZE_M)
    offs_cn = pid_n * BLOCK_SIZE_N + tl.arange(0, BLOCK_SIZE_N)
    c_ptrs = out_ptr + stride_on * offs_cm[:, None] + stride_od * offs_cn[None, :]
    
    mask = (offs_cm[:, None] < 1) & (offs_cn[None, :] < D)
    tl.store(c_ptrs, accumulator, mask=mask)

def apply_geometric_rotation(latent_thought: torch.Tensor, R_matrix: torch.Tensor) -> torch.Tensor:
    """Función envoltura para invocar el kernel de Triton"""
    assert latent_thought.is_cuda and R_matrix.is_cuda, "Tensores deben estar en GPU"
    
    D = latent_thought.shape[1]
    output = torch.empty_like(latent_thought)
    
    grid = lambda META: (triton.cdiv(D, META['BLOCK_SIZE_N']),)
    procrustes_rotation_kernel[grid](
        latent_thought, R_matrix, output, D,
        latent_thought.stride(0), latent_thought.stride(1),
        R_matrix.stride(0), R_matrix.stride(1),
        output.stride(0), output.stride(1),
        BLOCK_SIZE_M=16, BLOCK_SIZE_N=64, BLOCK_SIZE_K=64
    )
    return output
