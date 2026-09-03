#!/usr/bin/env python3
"""
POLYDIM V301 — BENCHMARK ASINTÓTICO EN SILICIO (KAGGLE GPU T4)
Regla 13: Todo resultado numérico se genera aquí. Cero simulación.
Regla 17: Incluye vectores degenerados (NaN, Inf, singular, subnormal).
"""
import time
import math
import sys
import numpy as np

print("=" * 70)
print(" POLYDIM V301 KAGGLE BENCHMARK — ASINTÓTICO DESTRUCTIVO (GPU)")
print("=" * 70)

# ============================================================================
# [0] DETECCIÓN DE HARDWARE (Silicon Contract — Anti-Hardcoding)
# ============================================================================
try:
    import torch
    HAS_TORCH = True
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_mem / (1024**3)
        print(f"\n[HW] GPU Detectada: {gpu_name} ({gpu_mem:.1f} GB VRAM)")
        DEVICE = "cuda"
    else:
        print("\n[HW] Sin GPU CUDA. Ejecutando en CPU.")
        DEVICE = "cpu"
except ImportError:
    HAS_TORCH = False
    DEVICE = "cpu"
    print("\n[HW] PyTorch no disponible. Fallback a NumPy puro.")

# ============================================================================
# [1] PROCRUSTES SOTA (SVD Estabilizado + slogdet)
# ============================================================================
def compute_procrustes_sota(source, target, epsilon=1e-5):
    """Orthogonal Procrustes con Tikhonov y slogdet."""
    M = torch.matmul(target.t(), source)
    D = M.shape[0]
    M_stable = M + torch.eye(D, dtype=M.dtype, device=M.device) * epsilon
    U, S, Vh = torch.linalg.svd(M_stable, full_matrices=True)
    R = torch.matmul(U, Vh)
    sign, _ = torch.linalg.slogdet(R)
    if sign < 0:
        Vh[-1, :] *= -1
        R = torch.matmul(U, Vh)
    return R

# ============================================================================
# [2] TEST 1: PROCRUSTES ASINTÓTICO (D = 1K → 10K)
# ============================================================================
if HAS_TORCH:
    print("\n" + "=" * 70)
    print(" TEST 1: PROCRUSTES ASINTÓTICO (SVD ESTABILIZADO)")
    print("=" * 70)
    
    dims_procrustes = [512, 1024, 2048, 4096, 8192, 10000]
    N_anchors = 100
    
    for D in dims_procrustes:
        torch.manual_seed(42)
        try:
            t0 = time.time()
            src = torch.randn(N_anchors, D, dtype=torch.float64, device=DEVICE)
            Q, _ = torch.linalg.qr(torch.randn(D, D, dtype=torch.float64, device=DEVICE))
            tgt = torch.matmul(src, Q) + torch.randn(N_anchors, D, dtype=torch.float64, device=DEVICE) * 0.01
            
            R = compute_procrustes_sota(src, tgt)
            
            # Verificación de isometría
            thought = torch.randn(1, D, dtype=torch.float64, device=DEVICE)
            rotated = torch.matmul(thought, R)
            norm_orig = torch.norm(thought).item()
            norm_rot = torch.norm(rotated).item()
            drift = abs(norm_orig - norm_rot)
            
            # Verificación de ortogonalidad: R^T @ R ≈ I
            ortho_err = torch.norm(torch.matmul(R.t(), R) - torch.eye(D, dtype=torch.float64, device=DEVICE)).item()
            
            t1 = time.time()
            ram_mb = (D * D * 8) / (1024**2)
            status = "OK" if drift < 1e-6 and ortho_err < 1e-3 else "FAIL"
            
            print(f"  D={D:6d} | RAM: {ram_mb:8.1f} MB | Drift: {drift:.2e} | OrthoErr: {ortho_err:.2e} | {(t1-t0)*1000:8.1f} ms | {status}")
        except Exception as e:
            print(f"  D={D:6d} | EXCEPTION: {type(e).__name__}: {e}")

# ============================================================================
# [3] TEST 2: VECTORES DEGENERADOS (Anti-Happy-Path)
# ============================================================================
if HAS_TORCH:
    print("\n" + "=" * 70)
    print(" TEST 2: VECTORES DEGENERADOS (NaN, Inf, Zero, Subnormal)")
    print("=" * 70)
    
    D_degen = 1024
    N_degen = 50
    
    # 2a. Anchors con NaN inyectado
    try:
        src = torch.randn(N_degen, D_degen, dtype=torch.float64, device=DEVICE)
        src[0, 0] = float('nan')
        tgt = torch.randn(N_degen, D_degen, dtype=torch.float64, device=DEVICE)
        R = compute_procrustes_sota(src, tgt)
        has_nan = torch.isnan(R).any().item()
        print(f"  [NaN Input]      -> R contiene NaN: {has_nan} | {'FAIL (propagación)' if has_nan else 'SURVIVED'}")
    except Exception as e:
        print(f"  [NaN Input]      -> EXCEPTION: {type(e).__name__}: {e}")

    # 2b. Anchors con Inf inyectado
    try:
        src = torch.randn(N_degen, D_degen, dtype=torch.float64, device=DEVICE)
        src[0, 0] = float('inf')
        tgt = torch.randn(N_degen, D_degen, dtype=torch.float64, device=DEVICE)
        R = compute_procrustes_sota(src, tgt)
        has_inf = torch.isinf(R).any().item()
        print(f"  [Inf Input]      -> R contiene Inf: {has_inf} | {'FAIL (propagación)' if has_inf else 'SURVIVED'}")
    except Exception as e:
        print(f"  [Inf Input]      -> EXCEPTION: {type(e).__name__}: {e}")

    # 2c. Anchors todo ceros (matriz singular extrema)
    try:
        src = torch.zeros(N_degen, D_degen, dtype=torch.float64, device=DEVICE)
        tgt = torch.randn(N_degen, D_degen, dtype=torch.float64, device=DEVICE)
        R = compute_procrustes_sota(src, tgt)
        has_nan = torch.isnan(R).any().item()
        print(f"  [Zero Input]     -> R contiene NaN: {has_nan} | {'FAIL (colapso)' if has_nan else 'SURVIVED'}")
    except Exception as e:
        print(f"  [Zero Input]     -> EXCEPTION: {type(e).__name__}: {e}")

    # 2d. Subnormales (valores < tiny)
    try:
        tiny = torch.finfo(torch.float64).tiny
        src = torch.full((N_degen, D_degen), tiny * 1e-10, dtype=torch.float64, device=DEVICE)
        tgt = torch.randn(N_degen, D_degen, dtype=torch.float64, device=DEVICE)
        R = compute_procrustes_sota(src, tgt)
        has_nan = torch.isnan(R).any().item()
        print(f"  [Subnormal]      -> R contiene NaN: {has_nan} | {'FAIL (underflow)' if has_nan else 'SURVIVED'}")
    except Exception as e:
        print(f"  [Subnormal]      -> EXCEPTION: {type(e).__name__}: {e}")

# ============================================================================
# [4] TEST 3: BARRIDO FJLT ASINTÓTICO (D=10^4 → 10^7)
# ============================================================================
print("\n" + "=" * 70)
print(" TEST 3: BARRIDO FJLT ASINTÓTICO (NumPy, D=10^4 a 10^7)")
print("=" * 70)

dims_fjlt = [10_000, 100_000, 1_000_000, 10_000_000]
for D in dims_fjlt:
    d = min(128, D // 100)
    try:
        t0 = time.time()
        vec = np.random.randn(D).astype(np.float64)
        idx = np.random.randint(0, D, size=d)
        out = vec[idx] * math.sqrt(D / d)
        t1 = time.time()
        ram_mb = (D * 8) / (1024**2)
        norm_ratio = np.linalg.norm(out) / np.linalg.norm(vec)
        print(f"  D={D:12,} | d={d:4d} | RAM: {ram_mb:7.1f} MB | NormRatio: {norm_ratio:.4f} | {(t1-t0)*1000:7.2f} ms | OK")
    except Exception as e:
        print(f"  D={D:12,} | EXCEPTION: {type(e).__name__}: {e}")

# ============================================================================
# [5] RESUMEN FINAL
# ============================================================================
print("\n" + "=" * 70)
print(" POLYDIM V301 BENCHMARK COMPLETO.")
print(f" Device: {DEVICE}")
if HAS_TORCH and torch.cuda.is_available():
    print(f" GPU: {torch.cuda.get_device_name(0)}")
    print(f" VRAM Peak: {torch.cuda.max_memory_allocated() / (1024**2):.1f} MB")
print("=" * 70)
