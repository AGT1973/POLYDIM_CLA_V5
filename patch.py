import os
filepath = r'E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V600\polydim_v600_monolito.py'
with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('assert ctypes.alignment(ShmHeader) == 128', 'assert ctypes.sizeof(ShmHeader) == 128')

old_lib_load = 'rcu_lib = ctypes.CDLL(f"E:\\\\POLYDIM_EINSOF\\\\ENTREGA_2026_09_12_V600\\\\pmtp_kernel_v600{dll_ext}")'
new_lib_load = 'rcu_lib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"pmtp_kernel_v600{dll_ext}")\nrcu_lib = ctypes.CDLL(rcu_lib_path)'
text = text.replace(old_lib_load, new_lib_load)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(text)
