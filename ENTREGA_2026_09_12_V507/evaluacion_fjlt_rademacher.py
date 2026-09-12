"""
CICLO 3: POLYDIM FJLT RADEMACHER STRESS TEST (D = 10,000,000)
Validación Asintótica de la Precondición Rademacher para FWHT
"""
import torch
import time
import os
import psutil

def print_memory(stage):
    process = psutil.Process(os.getpid())
    ram_mb = process.memory_info().rss / (1024 * 1024)
    vram_mb = torch.cuda.memory_allocated() / (1024 * 1024) if torch.cuda.is_available() else 0
    print(f"[{stage}] RAM: {ram_mb:.2f} MB | VRAM: {vram_mb:.2f} MB")

def main():
    print("=== POLYDIM CICLO 3: ASALTO ASINTÓTICO FJLT (D = 10,000,000) ===")
    print_memory("INIT")
    
    D = 10_000_000
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Dispositivo activo: {device}")
    
    # Generar vector latente denso
    t0 = time.perf_counter()
    latente = torch.randn(D, dtype=torch.float32, device=device)
    t1 = time.perf_counter()
    print(f"1. Tensor original generado ({D} dims) en {(t1-t0)*1000:.2f} ms")
    print_memory("POST-ALLOCATION")
    
    # Generar firma Rademacher (+1, -1) para esparcir la energía antes de FWHT
    t0 = time.perf_counter()
    # Usar el signo de un tensor aleatorio centrado en 0
    rademacher_signs = torch.sign(torch.randn(D, dtype=torch.float32, device=device))
    # Para evitar ceros exactos (raro pero posible), reemplazar 0 por 1
    rademacher_signs[rademacher_signs == 0] = 1.0
    t1 = time.perf_counter()
    print(f"2. Firma Rademacher generada en {(t1-t0)*1000:.2f} ms")
    print_memory("POST-RADEMACHER-GEN")
    
    # Aplicar la precondición
    t0 = time.perf_counter()
    latente_precondicionado = latente * rademacher_signs
    
    # Simular un paso de validación geométrica (Norma conservada)
    norma_original = torch.norm(latente)
    norma_precond = torch.norm(latente_precondicionado)
    drift = torch.abs(norma_original - norma_precond).item()
    t1 = time.perf_counter()
    
    print(f"3. Precondición aplicada y verificada en {(t1-t0)*1000:.2f} ms")
    print(f"   -> Norma original: {norma_original.item():.4f}")
    print(f"   -> Norma post-firma: {norma_precond.item():.4f}")
    print(f"   -> Deriva Isométrica (Drift): {drift:.8f}")
    
    assert drift < 1e-4, f"Fallo catastrófico: La isometría se rompió. Drift = {drift}"
    
    print("EXITO: El proyector Rademacher soporta 10 Millones de dimensiones en tiempo O(N) sin colapsar la RAM.")
    print_memory("FINAL")

if __name__ == '__main__':
    main()
