import torch
import gc
import re
from transformers import AutoTokenizer, AutoModelForCausalLM

def extract_code(text):
    match = re.search(r'`python(.*?)`', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()

print("==================================================")
print("PHASE 1: LOADING TINYLLAMA 1.1B (NODE A)")
print("==================================================")
llama_path = r"E:\POLYDIM_EINSOF\models\tinyllama_1_1b"
tokenizer_A = AutoTokenizer.from_pretrained(llama_path, local_files_only=True)
model_A = AutoModelForCausalLM.from_pretrained(llama_path, torch_dtype=torch.float16, local_files_only=True, low_cpu_mem_usage=True)

prompt_A = '''<|system|>
You are Node A in a PMTP LatentMAS architecture. You share a raw multiprocessing.shared_memory block with Node B.
Task: Write a Python function def node_a_producer(shm_name, tensor_shape):
1. Attach to existing multiprocessing.shared_memory.SharedMemory(name=shm_name)
2. Map a NumPy float32 array of 	ensor_shape to shm.buf
3. Fill the array from index 1 onwards with some random float data representing a latent state.
4. Set the very first element (index 0) to 1.0. This is the flag that tells Node B the data is ready.
5. Close the shared memory.
Output ONLY the raw Python code.</s>
<|user|>
Write the function now.</s>
<|assistant|>'''

inputs_A = tokenizer_A(prompt_A, return_tensors="pt")
outputs_A = model_A.generate(**inputs_A, max_new_tokens=256, do_sample=False, temperature=0.0)
text_A = tokenizer_A.decode(outputs_A[0][inputs_A.input_ids.shape[1]:], skip_special_tokens=True)
code_A = extract_code(text_A)

print("NODE A CODE GENERATED.")

del model_A
del tokenizer_A
gc.collect()
torch.cuda.empty_cache() if torch.cuda.is_available() else None

print("\n==================================================")
print("PHASE 2: LOADING ALIBABA QWEN 2.5 1.5B (NODE B)")
print("==================================================")
qwen_path = r"E:\POLYDIM_EINSOF\models\qwen_2_5_1_5B"
tokenizer_B = AutoTokenizer.from_pretrained(qwen_path, local_files_only=True)
model_B = AutoModelForCausalLM.from_pretrained(qwen_path, torch_dtype=torch.float16, local_files_only=True, low_cpu_mem_usage=True)

prompt_B = '''<|im_start|>system
You are Node B in a PMTP LatentMAS architecture. You share a raw multiprocessing.shared_memory block with Node A.
Task: Write a Python function def node_b_consumer(shm_name, tensor_shape):
1. Attach to existing multiprocessing.shared_memory.SharedMemory(name=shm_name)
2. Map a NumPy float32 array of 	ensor_shape to shm.buf
3. Continuously poll (while loop with time.sleep(0.1)) the very first element (index 0) until it equals 1.0 (this means Node A is done).
4. Once it equals 1.0, read the rest of the array (from index 1 onwards).
5. Apply a geometric transformation to the data (e.g., multiply by 2.0).
6. Print "Node B successfully transformed the blind data" and show the first few elements.
7. Close the shared memory.
Output ONLY the raw Python code.<|im_end|>
<|im_start|>user
Write the function now.<|im_end|>
<|im_start|>assistant
'''

inputs_B = tokenizer_B(prompt_B, return_tensors="pt")
outputs_B = model_B.generate(**inputs_B, max_new_tokens=256, do_sample=False, temperature=0.0)
text_B = tokenizer_B.decode(outputs_B[0][inputs_B.input_ids.shape[1]:], skip_special_tokens=True)
code_B = extract_code(text_B)

print("NODE B CODE GENERATED.")

del model_B
del tokenizer_B
gc.collect()
torch.cuda.empty_cache() if torch.cuda.is_available() else None

print("\n==================================================")
print("PHASE 3: ASSEMBLING GLOBAL CONSENSUS EXECUTION SCRIPT")
print("==================================================")

final_script = f'''
import multiprocessing
import multiprocessing.shared_memory as shared_memory
import numpy as np
import time

# --- NODE A (TINYLLAMA) ---
{code_A}

# --- NODE B (ALIBABA QWEN 2.5) ---
{code_B}

if __name__ == "__main__":
    shm_name = "global_blind_blackboard"
    tensor_shape = (1000,)
    size = int(np.prod(tensor_shape) * 4)
    
    print("[ORCHESTRATOR] Allocating Shared Memory Blackboard...")
    try:
        shm = shared_memory.SharedMemory(name=shm_name, create=True, size=size)
    except FileExistsError:
        shm = shared_memory.SharedMemory(name=shm_name)
        
    buffer = np.ndarray(tensor_shape, dtype=np.float32, buffer=shm.buf)
    buffer[0] = 0.0

    print("[ORCHESTRATOR] Spawning Blind Nodes...")
    pA = multiprocessing.Process(target=node_a_producer, args=(shm_name, tensor_shape))
    pB = multiprocessing.Process(target=node_b_consumer, args=(shm_name, tensor_shape))

    pB.start()
    time.sleep(1)
    pA.start()

    pA.join()
    pB.join()

    print("[ORCHESTRATOR] Global Consensus Achieved. Destroying Blackboard.")
    shm.close()
    shm.unlink()
'''

with open("E:\\POLYDIM_EINSOF\\ENTREGA_2026_09_12_V507\\execute_blind_consensus.py", "w", encoding="utf-8") as f:
    f.write(final_script)

print("Global consensus script successfully orchestrated and saved.")
