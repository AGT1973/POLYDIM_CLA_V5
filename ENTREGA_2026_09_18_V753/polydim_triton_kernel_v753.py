"""
POLYDIM V751 - TRITON GPU KERNEL 
SOTA COMPLIANT: FlashAttention IO-aware tiling, SRAM local caching, fused normalization.
Implements rigorous numel bounds checking (Silicon Contract).
Addresses DxD OOM avoidance in dual representation via matrix-free tiled operator.
"""

import torch
import triton
import contextlib
import triton.language as tl

# ==============================================================================
# FUSED NORMALIZATION (2-PASS) WITH SRAM CACHING & NUMEL BOUNDS CHECKING
# ==============================================================================
@triton.jit
def _fused_norm_kernel_pass1(x_ptr, partial_ptr, numel: tl.constexpr, BLOCK_SIZE: tl.constexpr):
    pid = tl.program_id(0)
    offs = pid * BLOCK_SIZE + tl.arange(0, BLOCK_SIZE)
    mask = offs < numel  # PROPER BOUNDS CHECKING
    
    # SRAM local caching
    x = tl.load(x_ptr + offs, mask=mask, other=0.0)
    psq = tl.sum(x * x, axis=0)
    tl.store(partial_ptr + pid, psq)

@triton.jit
def _fused_norm_kernel_pass2(x_ptr, out_ptr, partial_ptr, numel: tl.constexpr, n_partials: tl.constexpr, BLOCK_SIZE: tl.constexpr):
    offs_p = tl.arange(0, BLOCK_SIZE)
    mask_p = offs_p < n_partials
    partials = tl.load(partial_ptr + offs_p, mask=mask_p, other=0.0)
    total_sq = tl.sum(partials, axis=0)
    inv_norm = tl.where(total_sq > 1e-24, tl.rsqrt(total_sq), 0.0)

    pid = tl.program_id(0)
    offs = pid * BLOCK_SIZE + tl.arange(0, BLOCK_SIZE)
    mask = offs < numel
    x = tl.load(x_ptr + offs, mask=mask, other=0.0)
    
    tl.store(out_ptr + offs, x * inv_norm, mask=mask)

# ==============================================================================
# DxD OOM AVOIDANCE: FLASH-ATTENTION TILED DUAL PCG OPERATOR
# Memory: O(N*D) exactly. Avoids materializing X @ X^T
# ==============================================================================
@triton.jit
def _xt_v_kernel(
    X_ptr, v_ptr, w_ptr,
    N, D,
    stride_xn, stride_xd,
    BLOCK_N: tl.constexpr, BLOCK_D: tl.constexpr
):
    pid_d = tl.program_id(0)
    offs_d = pid_d * BLOCK_D + tl.arange(0, BLOCK_D)
    mask_d = offs_d < D
    
    acc = tl.zeros((BLOCK_D,), dtype=tl.float32)
    
    # IO-aware tiling over N (FlashAttention concept)
    for n_idx in range(0, N, BLOCK_N):
        offs_n = n_idx + tl.arange(0, BLOCK_N)
        mask_n = offs_n < N
        
        v = tl.load(v_ptr + offs_n, mask=mask_n, other=0.0)
        
        x_ptrs = X_ptr + offs_n[:, None] * stride_xn + offs_d[None, :] * stride_xd
        x_mask = mask_n[:, None] & mask_d[None, :]
        x = tl.load(x_ptrs, mask=x_mask, other=0.0)  # SRAM block
        
        acc += tl.sum(x * v[:, None], axis=0)
        
    tl.store(w_ptr + offs_d, acc, mask=mask_d)

@triton.jit
def _x_w_kernel(
    X_ptr, w_ptr, v_ptr, out_ptr,
    N, D, ridge_alpha,
    stride_xn, stride_xd,
    BLOCK_N: tl.constexpr, BLOCK_D: tl.constexpr
):
    pid_n = tl.program_id(0)
    offs_n = pid_n * BLOCK_N + tl.arange(0, BLOCK_N)
    mask_n = offs_n < N
    
    acc = tl.zeros((BLOCK_N,), dtype=tl.float32)
    
    # IO-aware tiling over D
    for d_idx in range(0, D, BLOCK_D):
        offs_d = d_idx + tl.arange(0, BLOCK_D)
        mask_d = offs_d < D
        
        w = tl.load(w_ptr + offs_d, mask=mask_d, other=0.0)
        
        x_ptrs = X_ptr + offs_n[:, None] * stride_xn + offs_d[None, :] * stride_xd
        x_mask = mask_n[:, None] & mask_d[None, :]
        x = tl.load(x_ptrs, mask=x_mask, other=0.0) # SRAM block
        
        acc += tl.sum(x * w[None, :], axis=1)
        
    v = tl.load(v_ptr + offs_n, mask=mask_n, other=0.0)
    out = acc + ridge_alpha * v
    tl.store(out_ptr + offs_n, out, mask=mask_n)


class TritonPolydimV751:
    def normalize(self, x: torch.Tensor, stream: torch.cuda.Stream = None) -> torch.Tensor:
        ctx = torch.cuda.stream(stream) if stream else contextlib.nullcontext()
        with ctx:
            numel = x.numel()
            if numel == 0:
                return x
            out = torch.empty_like(x)
            BLOCK = triton.next_power_of_2(min(numel, 4096))
            n_partials = (numel + BLOCK - 1) // BLOCK
            partials = torch.empty(n_partials, dtype=torch.float32, device=x.device)
            _fused_norm_kernel_pass1[(n_partials,)](x, partials, numel=numel, BLOCK_SIZE=BLOCK)
            BLOCK2 = triton.next_power_of_2(max(n_partials, BLOCK))
            _fused_norm_kernel_pass2[(n_partials,)](x, out, partials, numel=numel, n_partials=n_partials, BLOCK_SIZE=BLOCK2)
            return out
        
    def dual_pcg_matvec(self, X: torch.Tensor, v: torch.Tensor, ridge_alpha: float, stream: torch.cuda.Stream = None) -> torch.Tensor:
        ctx = torch.cuda.stream(stream) if stream else contextlib.nullcontext()
        with ctx:
            N, D = X.shape
            assert v.shape == (N,)
            w = torch.zeros(D, dtype=torch.float32, device=X.device)
            out = torch.zeros(N, dtype=torch.float32, device=X.device)
            BLOCK_N = 64
            BLOCK_D = 128
            grid_d = triton.cdiv(D, BLOCK_D)
            _xt_v_kernel[(grid_d,)](
                X, v, w, N, D,
                X.stride(0), X.stride(1),
                BLOCK_N=BLOCK_N, BLOCK_D=BLOCK_D
            )
            grid_n = triton.cdiv(N, BLOCK_N)
            _x_w_kernel[(grid_n,)](
                X, w, v, out, N, D, ridge_alpha,
                X.stride(0), X.stride(1),
                BLOCK_N=BLOCK_N, BLOCK_D=BLOCK_D
            )
            return out
