"""
TRITON GPU KERNEL v508 - SOTA COMPLIANT
Fixes: #21 (grid), #22 (mask), #23 (eps), #28 (pool), #29 (pin), #44 (async), #45 (thread explosion)
"""

import asyncio
import torch
import triton
import triton.language as tl
from concurrent.futures import ThreadPoolExecutor


@triton.jit
def _partial_sq_kernel(x_ptr, partial_ptr, D: tl.constexpr, BLOCK: tl.constexpr):
    pid = tl.program_id(0)
    offs = pid * BLOCK + tl.arange(0, BLOCK)
    mask = offs < D
    x = tl.load(x_ptr + offs, mask=mask, other=0.0)
    psq = tl.sum(x * x, axis=0)
    tl.store(partial_ptr + pid, psq)


@triton.jit
def _finalize_inv_norm_kernel(partial_ptr, inv_norm_ptr, N: tl.constexpr):
    offs = tl.arange(0, N)
    mask = offs < N
    ps = tl.load(partial_ptr + offs, mask=mask, other=0.0)
    total = tl.sum(ps, axis=0)
    inv = tl.where(total > 1e-24, tl.rsqrt(total), 0.0)
    tl.store(inv_norm_ptr, inv)


@triton.jit
def _scale_kernel(x_ptr, out_ptr, inv_norm_ptr, D: tl.constexpr, BLOCK: tl.constexpr):
    pid = tl.program_id(0)
    offs = pid * BLOCK + tl.arange(0, BLOCK)
    mask = offs < D
    x = tl.load(x_ptr + offs, mask=mask, other=0.0)
    inv = tl.load(inv_norm_ptr)
    tl.store(out_ptr + offs, x * inv, mask=mask)


class TwoPassNormalizer:
    def __init__(self, dim: int, device: str = "cuda:0", block: int = 2048):
        assert dim > 0
        self.dim = dim
        self.device = device
        self.block = min(block, triton.next_power_of_2(dim))
        self.n_partials = (dim + self.block - 1) // self.block
        self.n_partials_pow2 = triton.next_power_of_2(self.n_partials)
        self._partials = torch.zeros(self.n_partials_pow2, dtype=torch.float32, device=device)
        self._inv_norm = torch.empty(1, dtype=torch.float32, device=device)

    def run(self, x: torch.Tensor, out: torch.Tensor):
        assert x.is_cuda and x.dtype == torch.float32 and x.is_contiguous()
        assert x.numel() == self.dim and out.numel() == self.dim
        grid = (self.n_partials,)
        _partial_sq_kernel[grid](x, self._partials, D=self.dim, BLOCK=self.block)
        _finalize_inv_norm_kernel[(1,)](self._partials, self._inv_norm, N=self.n_partials_pow2)
        _scale_kernel[grid](x, out, self._inv_norm, D=self.dim, BLOCK=self.block)
        return out


class AsyncTritonIngestorv508:
    """v508: ThreadPoolExecutor persistente en lugar de Thread() por frame."""

    def __init__(self, dim: int, device: str = "cuda:0", block: int = 2048, num_slots: int = 4):
        self.dim = dim
        self.device = device
        self.normalizer = TwoPassNormalizer(dim, device=device, block=block)
        self.stream = torch.cuda.Stream(device=device)
        self._staging = [torch.empty(dim, dtype=torch.float32, device=device) for _ in range(num_slots)]
        self._outputs = [torch.empty(dim, dtype=torch.float32, device=device) for _ in range(num_slots)]
        self._events = [torch.cuda.Event(enable_timing=False) for _ in range(num_slots)]
        self._free = list(range(num_slots))
        self._lock = asyncio.Lock()
        self._sync_pool = ThreadPoolExecutor(max_workers=1)

    async def _acquire(self) -> int:
        async with self._lock:
            while not self._free:
                await asyncio.sleep(0.0001)
            return self._free.pop()

    async def _release(self, idx: int):
        async with self._lock:
            self._free.append(idx)

    async def ingest_and_normalize(self, cpu_tensor: torch.Tensor) -> torch.Tensor:
        if cpu_tensor.numel() != self.dim:
            raise ValueError(f"dim mismatch: {cpu_tensor.numel()} != {self.dim}")
        if cpu_tensor.dtype != torch.float32:
            raise TypeError(f"only f32, got {cpu_tensor.dtype}")
        if not cpu_tensor.is_pinned():
            cpu_tensor = cpu_tensor.pin_memory()

        idx = await self._acquire()
        staging, output, event = self._staging[idx], self._outputs[idx], self._events[idx]
        try:
            with torch.cuda.stream(self.stream):
                staging.copy_(cpu_tensor, non_blocking=True)
                self.normalizer.run(staging, output)
                event.record()

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
        try:
            asyncio.get_running_loop()
            fut = self._sync_pool.submit(asyncio.run, self.ingest_and_normalize(cpu_tensor))
            return fut.result()
        except RuntimeError:
            return asyncio.run(self.ingest_and_normalize(cpu_tensor))

    def close(self):
        self._sync_pool.shutdown(wait=True)


def self_test():
    if not torch.cuda.is_available():
        print("[TRITON v508] no CUDA -> skip")
        return
    ing = AsyncTritonIngestorv508(dim=10_000, block=1024)
    x = torch.randn(10_000, dtype=torch.float32)
    y = ing.ingest_sync(x)
    n = torch.linalg.norm(y).item()
    ok = abs(n - 1.0) < 1e-3
    status = "PASS" if ok else "FAIL"
    print(f"[TRITON v508] norm={n:.6f}  {status}")
    assert ok, f"Norm broken: {n}"
    ing.close()


if __name__ == "__main__":
    self_test()
