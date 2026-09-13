import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import re

def extract_code(text):
    match = re.search(r'`python(.*?)`', text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()

print("[NODO A] Cargando TinyLlama en CPU pura (Sin riesgo GPU)...")
path = r"E:\POLYDIM_EINSOF\models\tinyllama_1_1b"
tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
model = AutoModelForCausalLM.from_pretrained(path, torch_dtype=torch.float32, low_cpu_mem_usage=True, device_map="cpu")

prompt = '''<|system|>
You are Node A in a PMTP architecture. You share a multiprocessing.shared_memory block with Node B.
Task: Write a Python function def node_a_producer(shm_name, tensor_shape):
1. Attach to multiprocessing.shared_memory.SharedMemory(name=shm_name)
2. Map a NumPy float32 array of 	ensor_shape to shm.buf
3. Fill the array from index 1 onwards with some random float data representing a latent state.
4. Set the very first element (index 0) to 1.0. This is the flag that tells Node B the data is ready.
5. Close the shared memory.
Output ONLY the raw Python code.</s>
<|user|>
Write the function now.</s>
<|assistant|>
'''
print("[NODO A] Generando codigo...")
inputs = tokenizer(prompt, return_tensors="pt")
outputs = model.generate(**inputs, max_new_tokens=256, do_sample=False)
text = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

with open(r"E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V507\codigo_nodo_A.txt", "w", encoding="utf-8") as f:
    f.write(extract_code(text))
print("[NODO A] Finalizado. Autodestruccion de proceso.")
