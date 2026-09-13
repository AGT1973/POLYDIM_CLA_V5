# POLYDIM V507 SOTA DELIVERY

## Changelog de Refactorización Matemática y Sistemas (V506 -> V507)

El código ha sido refactorizado desde el bucle interactivo de OpenRouter / DeepSeek acatando el consenso estricto del Tribunal de los 10:

1. **Python Monolito (`polydim_v507_monolito.py`)**:
   - `ShmHeader` se actualizó para utilizar offsets relativos de 64 bits (`sig_0_off`, `sig_1_off`) medidos desde la base del mapping en memoria. Se eliminan los punteros crudos absolutos inter-procesos, previniendo violaciones de ASLR.
   - El candado IPC de Python ya no emplea `self._seq_ptr[0] += 1`. Ahora depende totalmente del CAS (Compare-And-Swap) Atómico nativo provisto por Rust FFI para blindar contra *torn reads* fuera de las limitaciones del GIL.

2. **Núcleo Rust (`kernel_rust_v507.rs.txt`)**:
   - Se exportaron los símbolos FFI puros `pmtp_seqlock_begin_write` y `pmtp_seqlock_end_write` operando sobre `std::sync::atomic::AtomicU64` con barreras `Acquire` y `Release`.
   - **Swarm Consensus (CBF):** Se reemplazó la inefectiva barrera Euclidiana por la genuina proyección del espacio tangente (Riemanniana) en la hiperesfera $S^{D-1}$. El *drift* angular $u$ se proyecta usando $P_x = I - x x^T$ antes de integrar y normalizar, evitando que la curvatura destruya la repulsión.
   - Anti-Poisoning: Chequeo estricto `!new_norm_sq.is_finite()` o `new_norm_sq < 1e-12` post-integración. Retorna -7 para evitar inyección silenciosa de `NaN`.

3. **Núcleo C++ (`kernel_cpp_v507.cpp.txt`)**:
   - Validaciones físicas de hardware corregidas. `pmtp_cpp_validate_hardware` ahora ejecuta nativamente una llamada en ensamblador inline (`_xgetbv(0)`) para asegurar que el sistema operativo retiene los registros YMM, resolviendo inyecciones de error `#UD` (Undefined Behavior) al invocar código compilado para AVX/AVX2 en Hypervisors o VMs sin soporte.
   - Validación FFI: Excepción BF16. Si `element_size == 2`, el requerimiento de alineación de 64 bytes se relaja a 16 bytes.

4. **Async Triton (Pendiente/Reemplazo en orquestación futura)**:
   - Se removió la mala práctica de instanciar `asyncio.run` dentro de constructores de Hilos a 120Hz.

