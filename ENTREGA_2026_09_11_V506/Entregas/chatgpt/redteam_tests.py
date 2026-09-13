import asyncio
import ctypes
import importlib.util
import math
import multiprocessing as mp
import os
import pathlib
import subprocess
import sys
import threading
import time

import numpy as np

ROOT = pathlib.Path('/mnt/data')
PY_MONO = ROOT / 'polydim_v506_monolito.py'
PY_TRITON = ROOT / 'polydim_triton_kernel_v506.py'
RUST = ROOT / 'kernel_rust_v506.rs.txt'
CPP = ROOT / 'kernel_cpp_v506.cpp.txt'


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def current_kahan32(values):
    s = np.float32(0.0)
    c = np.float32(0.0)
    for v in values:
        y = np.float32(v) - c
        t = np.float32(s + y)
        c = np.float32((t - s) - y)
        s = t
    return float(s)


def proposed_kahan64(values):
    s = 0.0
    c = 0.0
    for v in values:
        y = float(v) - c
        t = s + y
        c = (t - s) - y
        s = t
    return s


def model_current_horizontal_lift_partial_mutation():
    # Mirrors the current Rust ordering: all validation happens after tensor[i] is written.
    # Use a simple non-singular J where the second row is not collinear with the first.
    tensor = np.ones(8, dtype=np.float32)
    tensor[6] = np.nan
    jac_x = np.ones(8, dtype=np.float32)
    jac_y = np.zeros(8, dtype=np.float32)
    jac_y[0] = 1.0
    # J J^T = [[8,1],[1,1]] => det=7.
    a = float(np.dot(jac_x.astype(np.float64), jac_x.astype(np.float64)))
    b = float(np.dot(jac_x.astype(np.float64), jac_y.astype(np.float64)))
    d = float(np.dot(jac_y.astype(np.float64), jac_y.astype(np.float64)))
    det = a*d - b*b
    if abs(det) < 1e-12:
        return False, 'unexpected singular test setup'
    inv_det = 1.0/det
    inv_a = d*inv_det
    inv_b = -b*inv_det
    inv_d = a*inv_det
    px = inv_a*1.0 + inv_b*0.0
    py = inv_b*1.0 + inv_d*0.0
    before = tensor.copy()
    norm_sq = 0.0
    for i in range(len(tensor)):
        delta_nd = float(jac_x[i])*px + float(jac_y[i])*py
        tensor[i] += np.float32(delta_nd)
        val = float(tensor[i]) * float(tensor[i])
        norm_sq += val
        # At i=6 the NaN poisons norm_sq; current Rust returns -7 only after this mutation.
    changed_before_error = not np.array_equal(before[:6], tensor[:6])
    return changed_before_error and math.isnan(float(tensor[6])) and math.isnan(norm_sq), 'current ordering permits partial mutation before -7'


def model_current_consensus_nan_silent_success():
    local = np.ones(8, dtype=np.float32)
    nbr = np.ones((1, 8), dtype=np.float32)
    weights = np.ones(1, dtype=np.float32)
    nbr[0, 3] = np.nan
    u = weights[0] * (nbr[0] - local)
    centroid_dot = float(np.sum(local.astype(np.float64) * u.astype(np.float64)))
    norm_sq = float(np.sum(local.astype(np.float64) * local.astype(np.float64)))
    proposed_local = local + np.float32(0.01) * u
    out_norm = float(np.sum(proposed_local.astype(np.float64)**2))
    # Current Rust: if norm_sq > 1e-12 then normalize; NaN comparison is false.
    current_returns_zero = not (math.isnan(out_norm) and out_norm > 1e-12)
    return current_returns_zero and math.isnan(float(proposed_local[3])), 'NaN can pass through to success path'


def run():
    pm = load_module(PY_MONO, 'pm_redteam')
    results = []

    # Syntax is already enforced by import here.
    results.append(('python_imports', True, 'monolith imports'))
    results.append(('shm_header_layout', ctypes.sizeof(pm.ShmHeader) == 128 and ctypes.alignment(pm.ShmHeader) == 128,
                    f'size={ctypes.sizeof(pm.ShmHeader)} align={ctypes.alignment(pm.ShmHeader)}'))

    txt = PY_MONO.read_text(encoding='utf-8', errors='replace')
    results.append(('dll_name_collision', txt.count('rust_name = "pmtp_kernel_v506.dll"') == 1 and
                    'cpp_name = "pmtp_kernel_v506.dll"' in txt, 'Rust and C++ use same DLL basename'))
    results.append(('mock_missing_dll', 'Mockeando...' in txt, 'missing native libraries are converted to None'))
    results.append(('hardware_query_hardcoded', 'self._hw_alignment = 64' in txt and 'def _bind_cpp_ffi' in txt, 'hardware query is constant and C++ binding is empty'))
    results.append(('slab_python_atomic_claim', '_seq_ptr[0] += 1' in txt, 'ctypes integer access is used as claimed atomic operation'))

    rust = RUST.read_text(encoding='utf-8', errors='replace')
    results.append(('kahan_not_f64', '0.0f32' in rust[rust.find('dot_kahan_4way'):rust.find('dot_kahan_4way')+2500], 'Kahan lanes/compensators are f32'))
    results.append(('consensus_heap_alloc', 'let mut u_i = vec![0.0f32; d_dim];' in rust, 'per-call heap allocation'))
    results.append(('lift_checks_params_not_tensor', 'delta_x.is_finite()' in rust and 'tensor[i]' in rust, 'tensor/J finite values not validated before mutation'))
    results.append(('rdma_manual_abi', 'mr.add(16)' in rust and 'mr.add(36)' in rust and 'offset_of!(ibv_send_wr, rkey)' in rust, 'manual ABI offsets'))

    tri = PY_TRITON.read_text(encoding='utf-8', errors='replace')
    results.append(('triton_clone_alloc', 'result = output.clone()' in tri, 'per-request output copy/allocation'))
    results.append(('triton_shared_async_lock', 'self._lock = asyncio.Lock()' in tri and 'asyncio.run(' in tri, 'lock shared across event loops'))
    results.append(('triton_nan_unchecked', 'torch.isfinite' not in tri, 'no explicit NaN/Inf validation'))
    results.append(('triton_one_stream', 'self.stream = torch.cuda.Stream' in tri and 'self.stream' in tri, 'single stream serializes work'))

    # Numerical PoC for true f64 Kahan.
    vals = np.tile(np.array([1e8, 1.0, -1e8], dtype=np.float32), 3334)[:10000]
    ref = math.fsum(map(float, vals))
    a = current_kahan32(vals)
    b = proposed_kahan64(vals)
    results.append(('kahan_numeric_poc', abs(a-ref) > 1000.0 and abs(b-ref) < 1e-9,
                    f'ref={ref:.6f} current_f32={a:.6f} proposed_f64={b:.6f}'))

    ok1, msg1 = model_current_horizontal_lift_partial_mutation()
    results.append(('lift_partial_mutation_model', ok1, msg1))
    ok2, msg2 = model_current_consensus_nan_silent_success()
    results.append(('consensus_nan_model', ok2, msg2))

    # Compile checks.
    pyc = subprocess.run([sys.executable, '-m', 'py_compile', str(PY_MONO), str(PY_TRITON)], capture_output=True, text=True)
    results.append(('python_compile', pyc.returncode == 0, pyc.stdout + pyc.stderr))
    cppc = subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Wpedantic', '-fsyntax-only', '-x', 'c++', str(CPP)], capture_output=True, text=True)
    results.append(('cpp_linux_syntax', cppc.returncode == 0, cppc.stdout + cppc.stderr))
    results.append(('rust_build_available', shutil_which('rustc') is not None, 'rustc not installed in audit container'))

    # Slab baseline measurement only; no fake after benchmark.
    sid = f'REDTEAM_BENCH_{os.getpid()}'
    allocator = pm.PmtpSlabAllocator(sid)
    try:
        tensors = [np.full(pm.D_DIM, i, dtype=np.float32) for i in range(pm.SLAB_SIZE)]
        samples = []
        for _ in range(30):
            t0 = time.perf_counter()
            allocator.write_slab_atomic(tensors)
            allocator.read_slab()
            samples.append((time.perf_counter()-t0)*1e6)
        samples.sort()
        p50 = samples[len(samples)//2]
        p95 = samples[int(len(samples)*0.95)-1]
        results.append(('slab_baseline_bench', True, f'roundtrip_us_p50={p50:.1f} p95={p95:.1f} min={samples[0]:.1f} max={samples[-1]:.1f}'))
    finally:
        allocator.close()

    print('===== POLYDIM V507 REDTEAM TEST OUTPUT =====')
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FINDING'} | {name} | {detail.replace(chr(10),' ')}")
    print('===== END OUTPUT =====')


def shutil_which(cmd):
    import shutil
    return shutil.which(cmd)


if __name__ == '__main__':
    run()
