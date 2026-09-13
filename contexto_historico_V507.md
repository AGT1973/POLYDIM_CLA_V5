# CONTEXTO HISTÓRICO - POLYDIM V507 (REGLA 13)
**Fecha:** 12 de Septiembre de 2026
**Estado:** Límite crítico de tokens alcanzado tras ingestión masiva (Regla 19).

## 1. HALLAZGOS VERIFICADOS (SOTA) A IMPLEMENTAR
Tras filtrar decenas de alucinaciones sintéticas de modelos web (Qwen, ChatGPT), los problemas matemáticos y arquitectónicos *reales* que debemos corregir en la entrega final de 1000 líneas son:
* **FFI Signature Mismatch:** pmtp_phase99_swarm_consensus recibe 7 parámetros en Python pero Rust solo acepta 5, causando corrupción de pila.
* **Shared Memory OS Bug:** mmap.mmap(0, ...) lanza error en Windows; debe ser d=-1.
* **D_DIM Inconsistente:** Conflictos de declaración que pueden llevar a desbordamientos silenciosos.
* **Falso SeqLock:** La sincronización actual de Python no usa primitivas atómicas reales y no protege contra doble escritor. Requiere el diseño de un State Machine real (Acquire/Release con ownership).
* **Ausencia de chequeos numéricos (Subnormales/NaN):** La proyección en Rust (SLERP / Consenso) no aborta a tiempo si la entrada degrada el espacio tangente.

## 2. ESTADO DE LOS EXPERIMENTOS EMPÍRICOS (FASE 9)
* **Kaggle (Cloud):** Node A V1 falló porque Kaggle corta el DNS externo con la GPU activa (MQTT bloqueado). El plan migró a guardar 	ensor_node_a.bin crudo y usar Kaggle Datasets como puente.
* **Local Full-Duplex V2 (Edge):** Se reescribió la prueba puenteando los bloques de Attention y usando directamente las MLP para evitar el colapso posicional (RoPE). Actualmente crashea por **Timeout**: Node B (TinyLlama) tarda más de 300 segundos en cargar los pesos en RAM, y Node A (Qwen) corta la conexión prematuramente.

## 3. TAREAS PENDIENTES EXCLUSIVAS PARA LA NUEVA SESIÓN
1. **Generación Monolítica (Las 1000 líneas):** Imprimir la versión definitiva de los 4 archivos base (kernel C++, kernel Rust, Triton, Python Monolito) purgados de los defectos arriba mencionados.
2. **Reparar Timeout de Duplex V2:** Aumentar el tiempo de espera del IPC para que la prueba de "Telepatía Latente" finalice con éxito.
3. **Consolidar Puente Cloud:** Verificar la extracción del tensor binario en Kaggle.

## ÚLTIMA ACTUALIZACIÓN (SYSTEM TASK)
* Se confirmó empíricamente el motivo del crasheo en duplex_v2: **TinyLlama no llega a cargar sus pesos en RAM a tiempo** (quedó al 75% cuando Qwen disparó el timeout). En la nueva sesión solo debemos aumentar el 'timeout' en el script.
