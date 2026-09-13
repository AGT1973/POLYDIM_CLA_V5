"""
POLYDIM TRITON V504 — TWO-PASS NORMALIZATION + BUFFER POOL
Fixes: #21 (grid), #22 (mask), #23 (eps), #28 (pool), #29 (pin), #44 (async)
"""

import asyncio
import torch
import triton
import triton.language as tl
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# KERNEL 1: Suma parcial de cuadrados por bloque (sin atomic)
# ==============================================================================
@triton.jit
def _partial_sq_kernel(
    x_ptr,
    partial_ptr,
    D: tl.constexpr,
    BLOCK: tl.constexpr,
):
    pid = tl.program_id(0)
    offs = pid * BLOCK + tl.arange(0, BLOCK)
    mask = offs < D
    x = tl.load(x_ptr + offs, mask=mask, other=0.0)
    psq = tl.sum(x * x, axis=0)
    tl.store(partial_ptr + pid, psq)


# ==============================================================================
# KERNEL 2: Finalizar inv_norm (reduce partials, un solo programa)
# ==============================================================================
@triton.jit
def _finalize_inv_norm_kernel(
    partial_ptr,
    inv_norm_ptr,
    N: tl.constexpr,
):
    offs = tl.arange(0, N)
    mask = offs < N
    ps = tl.load(partial_ptr + offs, mask=mask, other=0.0)
    total = tl.sum(ps, axis=0)
    inv = tl.where(total > 1e-24, tl.rsqrt(total), 0.0)
    tl.store(inv_norm_ptr, inv)


# ==============================================================================
# KERNEL 3: Escalar usando inv_norm global
# ==============================================================================
@triton.jit
def _scale_kernel(
    x_ptr,
    out_ptr,
    inv_norm_ptr,
    D: tl.constexpr,
    BLOCK: tl.constexpr,
):
    pid = tl.program_id(0)
    offs = pid * BLOCK + tl.arange(0, BLOCK)
    mask = offs < D
    x = tl.load(x_ptr + offs, mask=mask, other=0.0)
    inv = tl.load(inv_norm_ptr)
    tl.store(out_ptr + offs, x * inv, mask=mask)


# ==============================================================================
# NORMALIZER — Two-pass correcto para cualquier D
# ==============================================================================
class TwoPassNormalizer:
    def __init__(self, dim: int, device: str = "cuda:0", block: int = 2048):
        assert dim > 0
        self.dim = dim
        self.device = device
        self.block = min(block, triton.next_power_of_2(dim))
        self.n_partials = (dim + self.block - 1) // self.block
        self.n_partials_pow2 = triton.next_power_of_2(self.n_partials)

        # Scratch persistente — lifetime = objeto
        self._partials = torch.zeros(
            self.n_partials_pow2, dtype=torch.float32, device=device
        )
        self._inv_norm = torch.empty(1, dtype=torch.float32, device=device)

    def run(self, x: torch.Tensor, out: torch.Tensor):
        """x, out: f32 CUDA contiguous. Same stream del caller."""
        assert x.is_cuda and x.dtype == torch.float32 and x.is_contiguous()
        assert x.numel() == self.dim and out.numel() == self.dim

        grid = (self.n_partials,)
        _partial_sq_kernel[grid](x, self._partials, D=self.dim, BLOCK=self.block)
        _finalize_inv_norm_kernel[(1,)](
            self._partials, self._inv_norm, N=self.n_partials_pow2
        )
        _scale_kernel[grid](x, out, self._inv_norm, D=self.dim, BLOCK=self.block)
        return out


# ==============================================================================
# ASYNC INGESTOR V504 — Genuinamente no bloqueante + pool real
# ==============================================================================
class AsyncTritonIngestorV504:
    """
    Fixes: #28 (pool N buffers), #44 (sin run_in_executor para CUDA),
           #29 (pin explícito), #6 (sin record_stream)
    """
    def __init__(
        self,
        dim: int,
        device: str = "cuda:0",
        block: int = 2048,
        num_slots: int = 4,
    ):
        self.dim = dim
        self.device = device
        self.normalizer = TwoPassNormalizer(dim, device=device, block=block)
        self.stream = torch.cuda.Stream(device=device)

        self._staging = [
            torch.empty(dim, dtype=torch.float32, device=device)
            for _ in range(num_slots)
        ]
        self._outputs = [
            torch.empty(dim, dtype=torch.float32, device=device)
            for _ in range(num_slots)
        ]
        self._events = [
            torch.cuda.Event(enable_timing=False) for _ in range(num_slots)
        ]
        self._free = list(range(num_slots))
        self._lock = asyncio.Lock()

    async def _acquire(self) -> int:
        async with self._lock:
            while not self._free:
                await asyncio.sleep(0.0001)
            return self._free.pop()

    async def _release(self, idx: int):
        async with self._lock:
            self._free.append(idx)

    async def ingest_and_normalize(
        self, cpu_tensor: torch.Tensor
    ) -> torch.Tensor:
        if cpu_tensor.numel() != self.dim:
            raise ValueError(f"dim mismatch: {cpu_tensor.numel()} != {self.dim}")
        if cpu_tensor.dtype != torch.float32:
            raise TypeError(f"only f32, got {cpu_tensor.dtype}")
        if not cpu_tensor.is_pinned():
            cpu_tensor = cpu_tensor.pin_memory()

        idx = await self._acquire()
        staging = self._staging[idx]
        output = self._outputs[idx]
        event = self._events[idx]

        try:
            with torch.cuda.stream(self.stream):
                staging.copy_(cpu_tensor, non_blocking=True)
                self.normalizer.run(staging, output)
                event.record()

            # Polling no-bloqueante — NO run_in_executor
            loop = asyncio.get_running_loop()
            future = loop.create_future()

            def _poll():
                if event.query():
                    loop.call_soon_threadsafe(future.set_result, None)
                else:
                    loop.call_later(0.0001, _poll)

            loop.call_soon(_poll)
            await future
            
            with torch.cuda.stream(self.stream):
                result = output.clone()
                done_event = torch.cuda.Event()
                done_event.record(self.stream)
            
            future2 = loop.create_future()
            def _poll2():
                if done_event.query():
                    loop.call_soon_threadsafe(future2.set_result, None)
                else:
                    loop.call_later(0.0001, _poll2)
            loop.call_soon(_poll2)
            await future2
            
            return result
        finally:
            await self._release(idx)

    def ingest_sync(self, cpu_tensor: torch.Tensor) -> torch.Tensor:
        """Sync wrapper sin crear loops anidados."""
        try:
            asyncio.get_running_loop()
            import threading
            result = {}
            def _run():
                result["v"] = asyncio.run(
                    self.ingest_and_normalize(cpu_tensor)
                )
            t = threading.Thread(target=_run)
            t.start()
            t.join()
            return result["v"]
        except RuntimeError:
            return asyncio.run(self.ingest_and_normalize(cpu_tensor))

# ==============================================================================
# Self-test obligatorio — FALLA si la norma no es 1.0
# ==============================================================================
def self_test():
    if not torch.cuda.is_available():
        print("[TRITON V504] no CUDA — skip")
        return
    ing = AsyncTritonIngestorV504(dim=10_000, block=1024)
    x = torch.randn(10_000, dtype=torch.float32)
    y = ing.ingest_sync(x)
    n = torch.linalg.norm(y).item()
    ok = abs(n - 1.0) < 1e-3
    print(f"[TRITON V504] norm={n:.6f}  {'PASS' if ok else 'FAIL'}")
    assert ok, f"Norm broken: {n} (bug #21 regression)"

if __name__ == "__main__":
    self_test()
