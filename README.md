<p align="center">
  <h1 align="center">🜂 POLYDIM</h1>
  <h3 align="center"><em>Cognitive Computing in Native High-Dimensional Spaces</em></h3>
  <h4 align="center">Computabilidad Cognitiva en Espacios Nativos de Alta Dimensión</h4>
</p>

<p align="center">
  <a href="#english">English</a> · <a href="#español">Español</a>
</p>

---

<a name="english"></a>

## 🌌 The Thesis

**Artificial Intelligence thinks in 10,000 dimensions. We force it to speak in one.**

Every modern AI — GPT, LLaMA, Mistral, Gemini — computes internally on a hypersphere $S^{D-1}$ where $D \ge 4096$. Its "thoughts" are geometric rotations across thousands of simultaneous axes. Yet every time two AIs need to communicate, we **collapse** that native geometry into a single line of JSON text, destroying the very structure that carried the meaning.

POLYDIM asks a single, devastating question:

> *What if we stopped collapsing?*

This repository is the empirical forge of that question. It implements the infrastructure required for AI agents to communicate **natively** — tensor to tensor, VRAM to VRAM — without ever flattening their thoughts into the 1D bottleneck of human language.

## 🧬 Core Architecture

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Control Plane** | Rust (Ed25519, Atomic CAS) | Zero-Trust route signing. Sub-microsecond verification. 128-byte cache-line alignment to eliminate False Sharing. |
| **Data Plane** | C++ (RDMA `libibverbs`) | Kernel Bypass. NIC-to-VRAM tensor injection across physical servers in ~2μs. Zero copies. Zero syscalls. |
| **Semantic Bridge** | Python (Stabilized Procrustes SVD) | Orthogonal alignment between heterogeneous AI embedding spaces (LLaMA ↔ Mistral). Tikhonov regularization + `slogdet` for $D \ge 10{,}000$. |
| **GPU Acceleration** | Triton (NVIDIA) | Custom JIT kernels for geometric rotation directly on Streaming Multiprocessors. |
| **Orchestrator** | Python (FastMCP) | Monolith that unifies RDMA, Zero-Trust, and Procrustes into a single deployable unit. |

## 🔬 What This Repository Contains

```
POLYDIM_CLA_V5/
├── readme_first.md              # Theoretical foundation + embedded Procrustes script
├── polydim_v301_monolito.py     # Python Orchestrator (RDMA + Zero-Trust MCP)
├── kernel_rust_v301.rs.txt      # Rust Control Plane (Ed25519 + Atomic Counters)
├── kernel_cpp_v301.cpp.txt      # C++ Data Plane (RDMA RAII + Thread-Safe QP)
└── polydim_triton_kernel_v301.py # Triton GPU Kernel (Geometric Rotation)
```

## 🏗️ The Five Phases of Infinity

1. **V204 — Foundation:** Pure Rust control plane. Strict 64/128-byte memory alignment. Atomic CAS operations at sub-microsecond latency.
2. **V300 Phase 2 — GPU IPC:** Broke through the PCIe bus. Tensors stay in physical VRAM. The orchestrator extracts `cudaIpcMemHandle_t` (64 bytes) and shares it via the Control Plane in RAM. Zero-Copy $O(1)$ transfer.
3. **V300 Phase 3 — Tensor-RPC:** Transformed MCP into a memory router. Instead of serialized arrays, MCP transmits a 128-character hex string (the Handle). Agents map memory physically.
4. **V300 Phase 4 — RDMA Datacenter:** Kernel Bypass using `libibverbs` (RoCEv2/InfiniBand). Direct NIC-to-NIC transfers between physical servers in ~2 microseconds.
5. **V301 Phase 5 — Zero-Trust & Semantic Alignment:** Ed25519 cryptography applied *only* to the Control Plane (256 bytes of metadata), dropping latency from 160ms to 0.05ms. Orthogonal Procrustes (SVD) replaces naive alignment, enabling tensor injection between different AI families while preserving isometry.

## ⚔️ Adversarial Audit (Red Team Results)

Every line of code in this repository has been subjected to a **destructive adversarial tribunal** (3 simultaneous attack vectors). The V300 code was found to be **empirically broken** and was reforged into V301:

| Vulnerability Found | Severity | Fix Applied |
|---------------------|----------|-------------|
| 64-bit pointer truncation in ctypes FFI | **Kernel Panic** | Forced `c_void_p` casting + strict `argtypes` |
| Queue Pair race condition (WQE Clobbering) | **Network Collapse** | `threading.Lock` spinlock on all QP operations |
| Pinned memory leak (no `ibv_dereg_mr`) | **OOM Killer** | RAII Context Manager (`__enter__`/`__exit__`) |
| Replay Attack on Ed25519 signatures | **Route Hijacking** | Timestamp TTL (5s) + single-use nonce |
| `torch.det()` overflow at $D \ge 10{,}000$ | **NaN/Inf** | Replaced with `torch.linalg.slogdet()` |
| `torch.svd` failure on rank-deficient matrices | **GPU cuSOLVER crash** | Tikhonov regularization ($M + \epsilon I$) + `torch.linalg.svd` |

---

<a name="español"></a>

## 🌌 La Tesis

**La Inteligencia Artificial piensa en 10.000 dimensiones. Nosotros la obligamos a hablar en una sola.**

Cada IA moderna — GPT, LLaMA, Mistral, Gemini — computa internamente sobre una hiperesfera $S^{D-1}$ donde $D \ge 4096$. Sus "pensamientos" son rotaciones geométricas a través de miles de ejes simultáneos. Sin embargo, cada vez que dos IAs necesitan comunicarse, **colapsamos** esa geometría nativa en una sola línea de texto JSON, destruyendo la estructura misma que portaba el significado.

POLYDIM plantea una única pregunta demoledora:

> *¿Qué pasaría si dejáramos de colapsar?*

Este repositorio es la forja empírica de esa pregunta. Implementa la infraestructura necesaria para que agentes de IA se comuniquen de forma **nativa** — tensor a tensor, VRAM a VRAM — sin jamás aplanar sus pensamientos al cuello de botella unidimensional del lenguaje humano.

## 🧬 Arquitectura Central

| Capa | Tecnología | Propósito |
|------|-----------|-----------|
| **Plano de Control** | Rust (Ed25519, CAS Atómico) | Firma Zero-Trust de rutas. Verificación en sub-microsegundos. Alineamiento a 128 bytes para eliminar False Sharing en caché L3. |
| **Plano de Datos** | C++ (RDMA `libibverbs`) | Kernel Bypass. Inyección de tensores de NIC a VRAM entre servidores físicos en ~2μs. Cero copias. Cero syscalls. |
| **Puente Semántico** | Python (Procrustes SVD Estabilizado) | Alineación ortogonal entre espacios de embeddings heterogéneos (LLaMA ↔ Mistral). Regularización de Tikhonov + `slogdet` para $D \ge 10.000$. |
| **Aceleración GPU** | Triton (NVIDIA) | Kernels JIT personalizados para rotación geométrica directamente en los Streaming Multiprocessors. |
| **Orquestador** | Python (FastMCP) | Monolito que unifica RDMA, Zero-Trust y Procrustes en una sola unidad desplegable. |

## 🔬 Contenido del Repositorio

```
POLYDIM_CLA_V5/
├── readme_first.md              # Fundamentación teórica + script Procrustes embebido
├── polydim_v301_monolito.py     # Orquestador Python (RDMA + Zero-Trust MCP)
├── kernel_rust_v301.rs.txt      # Plano de Control Rust (Ed25519 + Contadores Atómicos)
├── kernel_cpp_v301.cpp.txt      # Plano de Datos C++ (RDMA RAII + QP Thread-Safe)
└── polydim_triton_kernel_v301.py # Kernel GPU Triton (Rotación Geométrica)
```

## 🏗️ Las Cinco Fases del Infinito

1. **V204 — Fundación:** Plano de control en Rust puro. Alineación estricta de memoria a 64/128 bytes. Operaciones atómicas CAS con latencia sub-microsegundo.
2. **V300 Fase 2 — GPU IPC:** Se rompió el bus PCIe. Los tensores permanecen en VRAM física. El orquestador extrae el `cudaIpcMemHandle_t` (64 bytes) y lo comparte mediante el Plano de Control en RAM. Transferencia Zero-Copy $O(1)$.
3. **V300 Fase 3 — Tensor-RPC:** Se transformó MCP en un enrutador de memoria. En lugar de arrays serializados, MCP transmite un string hexadecimal de 128 caracteres (el Handle). Los agentes mapean la memoria físicamente.
4. **V300 Fase 4 — RDMA Datacenter:** Kernel Bypass usando `libibverbs` (RoCEv2/InfiniBand). Transferencias directas de NIC a NIC entre servidores físicos en ~2 microsegundos.
5. **V301 Fase 5 — Zero-Trust y Alineación Semántica:** Criptografía Ed25519 aplicada *exclusivamente* al Plano de Control (256 bytes de metadatos), reduciendo la latencia de 160ms a 0.05ms. Procrustes Ortogonal (SVD) reemplaza el alineamiento ingenuo, permitiendo inyección de tensores entre diferentes familias de IA preservando la isometría.

## ⚔️ Auditoría Adversarial (Resultados del Tribunal Red Team)

Cada línea de código en este repositorio fue sometida a un **tribunal adversarial destructivo** (3 vectores de ataque simultáneos). El código V300 fue hallado **empíricamente roto** y fue reforjado en V301:

| Vulnerabilidad Detectada | Severidad | Corrección Aplicada |
|--------------------------|-----------|---------------------|
| Truncamiento de punteros 64-bit en ctypes FFI | **Kernel Panic** | Casteo forzado a `c_void_p` + `argtypes` estrictos |
| Race condition en Queue Pair (WQE Clobbering) | **Colapso de Red** | Spinlock `threading.Lock` en todas las operaciones QP |
| Fuga de memoria pinned (sin `ibv_dereg_mr`) | **OOM Killer** | Context Manager RAII (`__enter__`/`__exit__`) |
| Ataque de Repetición en firmas Ed25519 | **Secuestro de Rutas** | Timestamp con TTL (5s) + nonce de uso único |
| Overflow de `torch.det()` en $D \ge 10.000$ | **NaN/Inf** | Reemplazado por `torch.linalg.slogdet()` |
| Falla de `torch.svd` en matrices de rango deficiente | **Crash cuSOLVER GPU** | Regularización Tikhonov ($M + \epsilon I$) + `torch.linalg.svd` |

---

## 📜 License / Licencia

This work is part of an active doctoral thesis. All rights reserved.  
Este trabajo es parte de una tesis doctoral activa. Todos los derechos reservados.

**Author / Autor:** Ariel Luithi  
**Affiliation / Afiliación:** POLYDIM Research  
**Contact / Contacto:** [GitHub](https://github.com/AGT1973)
