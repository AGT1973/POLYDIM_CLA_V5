import torch
import triton
import triton.language as tl

@triton.jit
def pmtp_partial_sums(x_ptr, p_sums_ptr, dim, BLOCK_SIZE: tl.constexpr):
    pid = tl.program_id(0).to(tl.int64)
    offs = pid * BLOCK_SIZE + tl.arange(0, BLOCK_SIZE)
    m = offs < dim
    x = tl.load(x_ptr + offs, mask=m, other=0.0).to(tl.float64)
    tl.store(p_sums_ptr + pid, tl.sum(x * x, axis=0))

@triton.jit
def pmtp_reduce_final(p_sums_ptr, final_norm_ptr, nblocks, BLOCK: tl.constexpr):
    acc = tl.zeros((), dtype=tl.float64)
    for i in range(0, nblocks, BLOCK):
        o = i + tl.arange(0, BLOCK)
        acc += tl.sum(tl.load(p_sums_ptr + o, mask=o < nblocks, other=0.0), axis=0)
    tl.store(final_norm_ptr, acc)

@triton.jit
def pmtp_normalize(x_ptr, out_ptr, final_norm_ptr, dim, BLOCK_SIZE: tl.constexpr):
    total = tl.load(final_norm_ptr).to(tl.float64)
    inv = tl.full((), 1.0, tl.float64) / tl.sqrt(total)
    pid = tl.program_id(0).to(tl.int64)
    offs = pid * BLOCK_SIZE + tl.arange(0, BLOCK_SIZE)
    m = offs < dim
    x = tl.load(x_ptr + offs, mask=m, other=0.0).to(tl.float64)
    tl.store(out_ptr + offs, (x * inv).to(out_ptr.dtype.element_ty), mask=m)

def pmtp_normalize_host(x, out, BLOCK=1024):
    dim = x.numel()
    if dim == 0: return
    assert x.dtype == torch.float64, "Contrato FP64 estricto violado"
    
    nblocks = triton.cdiv(dim, BLOCK)
    ps = torch.empty(nblocks, dtype=torch.float64, device=x.device)
    fn = torch.empty(1, dtype=torch.float64, device=x.device)
    
    pmtp_partial_sums[(nblocks,)](x, ps, dim, BLOCK_SIZE=BLOCK)
    pmtp_reduce_final[(1,)](ps, fn, nblocks, BLOCK=4096)
    pmtp_normalize[(nblocks,)](x, out, fn, dim, BLOCK_SIZE=BLOCK)
