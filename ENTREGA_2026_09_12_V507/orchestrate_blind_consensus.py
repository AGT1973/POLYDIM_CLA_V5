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
print("PHASE 1: LOADING MICROSOFT PHI-3 (NODE A)")
print("==================================================")
phi_path = r"E:\POLYDIM_EINSOF\models\phi_3_mini"
tokenizer_A = AutoTokenizer.from_pretrained(phi_path, local_files_only=True)
model_A = AutoModelForCausalLM.from_pretrained(phi_path, torch_dtype=torch.float16, local_files_only=True, low_cpu_mem_usage=True)

prompt_A = '''System Directive: You are Node A in a PMTP LatentMAS architecture. You share a raw multiprocessing.shared_memory block with an unknown, completely blind Node B.
Task: Write a Python function def node_a_producer(shm_name, tensor_shape):
1. Attach to existing multiprocessing.shared_memory.SharedMemory(name=shm_name)
2. Map a NumPy float32 array of 	ensor_shape to shm.buf
3. Fill the array from index 1 onwards with some random float data representing a latent state.
4. Set the very first element (index 0) to 1.0. This is the flag that tells Node B the data is ready.
5. Close the shared memory.
You do not know what Node B will do with this tensor. Do not serialize to JSON. Output ONLY the raw Python code, without explanations.'''

messages_A = [{"role": "user", "content": prompt_A}]
inputs_A = tokenizer_A.apply_chat_template(messages_A, return_tensors="pt", add_generation_prompt=True)
outputs_A = model_A.generate(inputs_A, max_new_tokens=256, do_sample=False, temperature=0.0)
text_A = tokenizer_A.decode(outputs_A[0][inputs_A.shape[1]:], skip_special_tokens=True)
code_A = extract_code(text_A)

print("NODE A CODE GENERATED.")
print(code_A)

del model_A
del tokenizer_A
gc.collect()
torch.cuda.empty_cache() if torch.cuda.is_available() else None

print("\n==================================================")
print("PHASE 2: LOADING ALIBABA QWEN 2.5 (NODE B)")
print("==================================================")
qwen_path = r"E:\POLYDIM_EINSOF\models\qwen_2_5_1_5B"
tokenizer_B = AutoTokenizer.from_pretrained(qwen_path, local_files_only=True)
model_B = AutoModelForCausalLM.from_pretrained(qwen_path, torch_dtype=torch.float16, local_files_only=True, low_cpu_mem_usage=True)

prompt_B = '''System Directive: You are Node B in a PMTP LatentMAS architecture. You share a raw multiprocessing.shared_memory block with an unknown Node A.
Task: Write a Python function def node_b_consumer(shm_name, tensor_shape):
1. Attach to existing multiprocessing.shared_memory.SharedMemory(name=shm_name)
2. Map a NumPy float32 array of 	ensor_shape to shm.buf
3. Continuously poll (while loop with time.sleep(0.1)) the very first element (index 0) until it equals 1.0 (this means Node A is done).
4. Once it equals 1.0, read the rest of the array (from index 1 onwards).
5. Apply a geometric transformation to the data (e.g., multiply by 2.0).
6. Print "Node B successfully transformed the blind data: " and show the first few elements.
7. Close the shared memory.
You do not know what data Node A generated. Output ONLY the raw Python code, without explanations.'''

messages_B = [{"role": "user", "content": prompt_B}]
inputs_B = tokenizer_B.apply_chat_template(messages_B, return_tensors="pt", add_generation_prompt=True)
outputs_B = model_B.generate(inputs_B, max_new_tokens=256, do_sample=False, temperature=0.0)
text_B = tokenizer_B.decode(outputs_B[0][inputs_B.shape[1]:], skip_special_tokens=True)
code_B = extract_code(text_B)

print("NODE B CODE GENERATED.")
print(code_B)

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

# --- NODE A (MICROSOFT PHI-3) ---
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
        
    # Init flag to 0.0
    buffer = np.ndarray(tensor_shape, dtype=np.float32, buffer=shm.buf)
    buffer[0] = 0.0

    print("[ORCHESTRATOR] Spawning Blind Nodes...")
    pA = multiprocessing.Process(target=node_a_producer, args=(shm_name, tensor_shape))
    pB = multiprocessing.Process(target=node_b_consumer, args=(shm_name, tensor_shape))

    pB.start()
    time.sleep(1) # Give B time to start polling
    pA.start()

    pA.join()
    pB.join()

    print("[ORCHESTRATOR] Global Consensus Achieved. Destroying Blackboard.")
    shm.close()
    shm.unlink()
'''

with open("E:\\POLYDIM_EINSOF\\ENTREGA_2026_09_12_V507\\execute_blind_consensus.py", "w", encoding="utf-8") as f:
    f.write(final_script)

print("Global consensus script successfully orchestrated and saved to execute_blind_consensus.py")
