# CONTEXTO HISTÓRICO - POLYDIM (Hacia V733 INDUSTRIAL)

## 1. Estado Actual
El proyecto **POLYDIM** se encuentra en el umbral de la versión **V733 Industrial**. 
Acabamos de finalizar el escrutinio de la fase **V732**, en la cual se resolvieron las peores deficiencias matemáticas (Paradoja Involutiva, Amnesia BSC, Colapso de Mantisa, y Rango de Bits Congelado) mediante el uso de acumulación de doble precisión y puentes FFI estrictos.
Sin embargo, la auditoría del **Tribunal de los 10** (incluyendo DeepSeek, Claude, Kimi, etc.) identificó brechas estructurales y de ingeniería de alto nivel bajo las exigencias matemáticas de la arquitectura GCGT (Computabilidad Geométrica).

## 2. Hallazgos Críticos a Resolver (El "Debe" Técnico)
1. **Fallback Isométrico Silencioso (C++)**: La función de isometría BSC enmascara índices erróneos o duplicados en lugar de abortar, destruyendo la información biyectiva en silencio.
2. **Ghost Orchestrator / Cross-Validation Real**: El backend Rust se carga en memoria pero no se invoca en el bucle principal. Se debe aplicar el modelo *REFERENCE ≠ VALIDATOR* (invocar a Rust en CADA corrida de C++ para contrastar distancias y normas exactas).
3. **Peligros del PRNG**: 
   - El estado XorShift64 colapsa a `0` si `seed = UINT64_MAX`.
   - La semilla `seed + thread_id` acopla la matemática generada a la cantidad de cores (Hardware-Dependent).
4. **Pérdida de Precisión en Triton**: Los kernels de GPU están materializando productos en `float32` antes de reducir, perdiendo el beneficio anti-colapso que aportaba `f64`.

## 3. Elementos SOTA (State of the Art) por Implementar en V733
El orquestador de la nueva sesión debe inyectar directamente las siguientes estrategias matemáticas acordadas en la fase de ingesta (Regla 19):
*   **PRNG Philox4x32**: Reemplazar XorShift64. Es un PRNG contador (stateless) que garantiza decorrelación estricta sin importar la configuración de hilos (thread count).
*   **Árbol Fijo KBN (estilo ReproBLAS)**: Sustituir el pragma `reduction(+)` de OpenMP por un árbol binario estructurado usando Knuth TwoSum. Asegura determinismo bit-exacto en hardware de distinta topología.
*   **FMA en Householder**: Utilizar la instrucción de hardware FMA (`std::fma`) y vectores aleatorios `v` generados en `f64` estricto (Mezzadri RNG) para realizar reflexiones isométricas mucho más limpias.
*   **Composición de Isometría $T^{50}$ O(n)**: Eliminar el bucle de 50 pasos de la isometría BSC. Se puede reducir analíticamente a un solo pase lineal mediante sumas de prefijos y saltos de permutaciones, logrando un speedup empírico estimado de 33x.

## 4. Próxima Tarea (Arranque de Sesión)
**Objetivo de la próxima sesión:** Generar el parche **V733**.
1. Inicializar el código base a partir de la entrega `V732_INDUSTRIAL`.
2. Implementar los fixes del Árbol Fijo KBN, FMA y Philox en C++.
3. Restructurar el monolito en Python (`polydim_v733_monolito.py`) para soportar benchmarks emparejados (paired benchmarks) y conectar estrictamente el validador Rust (`kernel_rust_v733.rs`).
4. Auditar nuevamente con pruebas asintóticas extremas ($D \ge 10,000,000$).
