import time
import numpy as np
import os
import cv2
from multiprocessing import shared_memory

print('=== INICIANDO BUCLE CONTINUO PMTP MULTIMODAL (TEXTO, IMAGEN, VIDEO) ===')
print('Abre tu Administrador de Tareas. Presiona Ctrl+C para detener.')

def create_shared_memory(name, size):
    try:
        shm = shared_memory.SharedMemory(name=name, create=True, size=size)
    except FileExistsError:
        shm = shared_memory.SharedMemory(name=name)
    return shm

# Configuración de Tensores
TEXT_SHAPE = (1, 1024)         # Simulación de Embeddings de Texto
IMAGE_SHAPE = (512, 512, 3)    # Imagen RGB
VIDEO_SHAPE = (30, 256, 256, 3)# 30 frames de Video RGB

size_text = int(np.prod(TEXT_SHAPE) * 4)
size_image = int(np.prod(IMAGE_SHAPE) * 4)
size_video = int(np.prod(VIDEO_SHAPE) * 4)

shm_text = create_shared_memory('pmtp_text', size_text)
shm_image = create_shared_memory('pmtp_image', size_image)
shm_video = create_shared_memory('pmtp_video', size_video)

iteration = 0
try:
    while True:
        iteration += 1
        print(f'\n--- ITERACION {iteration} ---')
        
        # ==========================================
        # NODO A (EMISOR)
        # ==========================================
        # 1. TEXTO
        text_tensor_A = np.random.rand(*TEXT_SHAPE).astype(np.float32)
        buffer_text = np.ndarray(TEXT_SHAPE, dtype=np.float32, buffer=shm_text.buf)
        buffer_text[:] = text_tensor_A[:]
        
        # 2. IMAGEN (Generamos un patron visual que cambia con la iteracion)
        img_tensor_A = np.zeros(IMAGE_SHAPE, dtype=np.float32)
        img_tensor_A[:, :, 0] = (np.sin(np.linspace(0, 10, 512) + iteration) + 1) * 127.5
        img_tensor_A[:, :, 1] = (np.cos(np.linspace(0, 10, 512) - iteration) + 1) * 127.5
        img_tensor_A[:, :, 2] = 150.0
        buffer_image = np.ndarray(IMAGE_SHAPE, dtype=np.float32, buffer=shm_image.buf)
        buffer_image[:] = img_tensor_A[:]
        
        # 3. VIDEO (Frames fluctuantes)
        video_tensor_A = np.random.randint(0, 255, VIDEO_SHAPE).astype(np.float32)
        buffer_video = np.ndarray(VIDEO_SHAPE, dtype=np.float32, buffer=shm_video.buf)
        buffer_video[:] = video_tensor_A[:]
        
        print('NODO A: Tensores Multimodales inyectados en Memoria Compartida (Zero-Copy).')
        
        # Simular latencia de transmisión IPC
        time.sleep(0.05)
        
        # ==========================================
        # NODO B (RECEPTOR Y DECODIFICADOR)
        # ==========================================
        
        # Leer Texto
        text_tensor_B = np.ndarray(TEXT_SHAPE, dtype=np.float32, buffer=shm_text.buf).copy()
        drift_text = np.max(np.abs(text_tensor_A - text_tensor_B))
        
        # Leer Imagen
        img_tensor_B = np.ndarray(IMAGE_SHAPE, dtype=np.float32, buffer=shm_image.buf).copy()
        drift_img = np.max(np.abs(img_tensor_A - img_tensor_B))
        cv2.imwrite('output_nodeB_image.png', img_tensor_B.astype(np.uint8))
        
        # Leer Video
        video_tensor_B = np.ndarray(VIDEO_SHAPE, dtype=np.float32, buffer=shm_video.buf).copy()
        drift_vid = np.max(np.abs(video_tensor_A - video_tensor_B))
        # Guardamos un frame del video para comprobar output
        cv2.imwrite('output_nodeB_video_frame.png', video_tensor_B[0].astype(np.uint8))
        
        print(f'NODO B (Recepción Exitosa):')
        print(f' -> Drift Texto:  {drift_text}')
        print(f' -> Drift Imagen: {drift_img}')
        print(f' -> Drift Video:  {drift_vid}')
        print(f'Archivos reconstruidos en disco (output_nodeB_image.png, output_nodeB_video_frame.png)')
        
        # Forzar consumo de CPU
        np.matmul(img_tensor_B, img_tensor_B)
        
        time.sleep(0.5) # Ritmo observable en Task Manager

except KeyboardInterrupt:
    print('Bucle detenido por el usuario.')
finally:
    shm_text.close()
    shm_image.close()
    shm_video.close()
    shm_text.unlink()
    shm_image.unlink()
    shm_video.unlink()
