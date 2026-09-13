import os
import re

# 1. Fix kernel_rust_v508.rs.txt
rust_path = 'E:/POLYDIM_EINSOF/ENTREGA_2026_09_12_V508/kernel_rust_v508.rs.txt'
with open(rust_path, 'r', encoding='utf-8') as f:
    r_code = f.read()

r_code = r_code.replace(
    'pub unsafe extern "C" fn pmtp_phase99_swarm_consensus(\n    local_tensor: *mut f32,\n    neighbors: *const f32,\n    weights: *const f32,\n    num_neighbors: usize,\n    gamma: f32,\n) -> i32 {',
    'pub unsafe extern "C" fn pmtp_phase99_swarm_consensus(\n    local_tensor: *mut f32,\n    neighbors: *const f32,\n    weights: *const f32,\n    num_neighbors: usize,\n    dim: usize,\n    dt: f32,\n    cbf_gamma: f32,\n) -> i32 {'
)

with open(rust_path, 'w', encoding='utf-8') as f:
    f.write(r_code)

# 2. Fix polydim_v508_monolito_full.py
py_path = 'E:/POLYDIM_EINSOF/ENTREGA_2026_09_12_V508/polydim_v508_monolito_full.py'
with open(py_path, 'r', encoding='utf-8') as f:
    p_code = f.read()

p_code = p_code.replace(
    'lib.pmtp_phase99_swarm_consensus.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_float]',
    'lib.pmtp_phase99_swarm_consensus.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_float, ctypes.c_float]'
)

p_code = p_code.replace(
    'mmap.mmap(0, self.total_bytes, tagname=f"Local\\\\POLYDIM_SLAB_{slab_id}")',
    'mmap.mmap(-1, self.total_bytes, tagname=f"Local\\\\POLYDIM_SLAB_{slab_id}")'
)

# Also fix the incorrect edges call in python
p_code = re.sub(
    r'return self\._rust_lib\.pmtp_phase99_swarm_consensus\(\s*edges\.ctypes\.data_as\(ctypes\.c_void_p\),\s*ctypes\.c_size_t\(edges\.size // 2\),\s*ctypes\.c_size_t\(num_vertices\),\s*ctypes\.cast\(parent, ctypes\.c_void_p\),\s*ctypes\.cast\(rank, ctypes\.c_void_p\),\s*ctypes\.c_size_t\(num_vertices\),\s*\)',
    r'''# Removed invalid call for edges''',
    p_code
)

with open(py_path, 'w', encoding='utf-8') as f:
    f.write(p_code)

print("Fixes applied.")
