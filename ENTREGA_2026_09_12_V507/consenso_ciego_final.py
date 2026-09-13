import multiprocessing
import multiprocessing.shared_memory as shared_memory
import numpy as np
import time

def node_a_producer(shm_name, tensor_shape):
    # NODE A (TINYLLAMA LOGIC ADAPTED)
    shm = shared_memory.SharedMemory(name=shm_name)
    arr = np.ndarray(tensor_shape, dtype=np.float32, buffer=shm.buf)
    
    # Fill from index 1 onwards with latent state data
    arr[1:] = np.random.rand(tensor_shape[0] - 1).astype(np.float32)
    
    # Set flag at index 0
    arr[0] = 1.0
    shm.close()

def node_b_consumer(shm_name, tensor_shape):
    # NODE B (QWEN 2.5 EXACT LOGIC)
    shm = shared_memory.SharedMemory(name=shm_name)
    arr = np.ndarray(tensor_shape, dtype=np.float32, buffer=shm.buf)

    while True:
        if arr[0] == 1.0:
            break
        time.sleep(0.1)

    transformed_data = arr[1:]
    transformed_data *= 2.0

    print("[QWEN 2.5] Node B transformed the blind data successfully:")
    print(transformed_data[:5])

    shm.close()

if __name__ == "__main__":
    shm_name = "blackboard_historico"
    tensor_shape = (500,)
    size = int(np.prod(tensor_shape) * 4)
    
    try:
        shm = shared_memory.SharedMemory(name=shm_name, create=True, size=size)
    except FileExistsError:
        shm = shared_memory.SharedMemory(name=shm_name)
        
    buffer = np.ndarray(tensor_shape, dtype=np.float32, buffer=shm.buf)
    buffer[0] = 0.0

    pA = multiprocessing.Process(target=node_a_producer, args=(shm_name, tensor_shape))
    pB = multiprocessing.Process(target=node_b_consumer, args=(shm_name, tensor_shape))

    pB.start()
    time.sleep(1)
    pA.start()

    pA.join()
    pB.join()

    shm.close()
    shm.unlink()
