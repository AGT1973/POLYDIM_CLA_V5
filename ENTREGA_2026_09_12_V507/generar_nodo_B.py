import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import re

def extract_code(text):
    match = re.search(r'`python(.*?)`', text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()

print("[NODO B] Cargando Qwen 2.5 1.5B en CPU pura (Sin riesgo GPU)...")
path = r"E:\POLYDIM_EINSOF\models\qwen_2_5_1_5B"
tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
model = AutoModelForCausalLM.from_pretrained(path, torch_dtype=torch.float32, low_cpu_mem_usage=True, device_map="cpu")

prompt = '''<|im_start|>system
You are Node B in a PMTP architecture. You share a multiprocessing.shared_memory block with Node A.
Task: Write a Python function def node_b_consumer(shm_name, tensor_shape):
1. Attach to multiprocessing.shared_memory.SharedMemory(name=shm_name)
2. Map a NumPy float32 array of 	ensor_shape to shm.buf
3. Continuously poll using a while loop and time.sleep(0.1) checking if the first element (index 0) equals 1.0 (Node A is done).
4. Once it equals 1.0, read the rest of the array (from index 1 onwards).
5. Apply a geometric transformation to the data (e.g., multiply by 2.0).
6. Print "Node B transformed the data" and show the first 3 elements.
7. Close the shared memory.
Output ONLY the raw Python code.<|im_end|>
<|im_start|>user
Write the function now.<|im_end|>
<|im_start|>assistant
'''
print("[NODO B] Generando codigo...")
inputs = tokenizer(prompt, return_tensors="pt")
outputs = model.generate(**inputs, max_new_tokens=256, do_sample=False)
text = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

with open(r"E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V507\codigo_nodo_B.txt", "w", encoding="utf-8") as f:
    f.write(extract_code(text))
print("[NODO B] Finalizado. Autodestruccion de proceso.")
