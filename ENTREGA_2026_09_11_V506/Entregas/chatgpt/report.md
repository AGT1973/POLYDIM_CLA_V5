# POLYDIM V506 — Auditoría Red-Team / Bulldog

**Fecha de auditoría:** 11-Sep-2026  
**Objeto:** `kernel_cpp_v506.cpp.txt`, `kernel_rust_v506.rs.txt`, `polydim_triton_kernel_v506.py`, `polydim_v506_monolito.py`, `readme_first.md`  
**Método:** lectura estática profunda, búsqueda dirigida de contratos ABI/concurrencia/numerics, reproducción de fallos en Python cuando fue posible y compilación sintáctica C++/Python en el entorno disponible.

## 1. Veredicto ejecutivo

**V506 no pasa un release gate de producción.** La arquitectura tiene piezas buenas y varios fixes reales, pero todavía hay fallos de integración y de modelo de memoria que pueden producir corrupción silenciosa, resultados numéricamente inválidos o falsos positivos de "hardware validado".

Los problemas de mayor gravedad son:

1. **Colisión de nombres de DLL + consulta de hardware falsificada en el orquestador.** Rust y C++ reciben el mismo nombre de biblioteca; `_bind_cpp_ffi()` está vacío y `_query_hardware()` devuelve `64` sin interrogar al hardware.
2. **SeqLock en Python no es atómico ni tiene semántica de memoria entre procesos.** `ctypes.POINTER(c_uint64)` + `+= 1` no equivale a `AtomicU64` con acquire/release/CAS.
3. **El doble buffering prometido no existe en el `PmtpSlabAllocator` Python.** El lector sigue copiando el mismo slab de 320 KB mientras el escritor puede modificarlo; por tanto el protocolo no elimina el riesgo de torn reads.
4. **El ingestor Triton mezcla un `asyncio.Lock` compartido con `asyncio.run()` en hilos distintos.** Esto puede bloquearse por cruce de event loops.
5. **Triton usa un único CUDA stream y `output.clone()` por solicitud.** El supuesto pool de cuatro slots no produce cuatro flujos de ejecución GPU independientes y mantiene una copia/alocación por petición.
6. **El Kahan "f64" del router es en realidad Kahan con acumuladores y compensadores `f32`, convertidos a `f64` sólo al final.** El error es reproducible con un caso adversarial.
7. **Horizontal Lift y Consensus permiten entradas NaN/Inf en buffers principales y pueden mutar el tensor antes de descubrir el error.** Esto viola un contrato razonable de "error => no corrupción parcial".
8. **RDMA sigue dependiendo de layouts C manuales y de punteros internos de `ibv_mr`; además no existe una ruta de completion CQ ni un contrato de sincronización GPU→NIC.**

No se fabricaron benchmarks post-parche. En este entorno no hay `rustc`, Triton ni CUDA funcional, por lo que sólo se reportan pruebas ejecutables y un baseline CPU/SHM realmente medido.

---

## 2. Matriz de hallazgos

| ID | Severidad | Hallazgo | Impacto | Solución principal | Verificación disponible |
|---|---|---|---|---|---|
| P01 | CRÍTICO | Rust/C++ usan el mismo basename de DLL; C++ FFI vacío; hardware hardcodeado | El gateway C++ puede apuntar a la librería equivocada y la "consulta" no consulta nada | Namespaces/filenames distintos, bindings C++ reales, fail-fast | Reproducido estáticamente y por construcción |
| P02 | CRÍTICO | SeqLock Python no es atómico entre procesos | Race, orden de memoria inexistente, posible publicación incoherente | Atomics nativos Rust/C11/C++, índice publicado + double buffer | Reproducido por inspección + test detector |
| P03 | CRÍTICO | Slab Python no implementa double buffer | Torn reads de 320 KB siguen siendo posibles | Front/back buffer + published index atómico | Modelo del protocolo confirma la ventana |
| P04 | CRÍTICO | `asyncio.Lock` compartido entre event loops | Deadlock/atasco del pool | Un solo event loop o primitivas thread-safe | Reproducido con timeout |
| P05 | ALTO | Triton serializado en un único CUDA stream | No hay overlap GPU real entre slots | Stream por slot + scratch por slot | Confirmado por código |
| P06 | ALTO | `output.clone()` en cada ingest | Copia y alocación por request; contradice zero-copy/retorno de slot | Lease explícito de slot o documentar copia | Confirmado por código |
| P07 | ALTO | Scratch `_partials/_inv_norm` compartido | Sólo es seguro porque todo está serializado por el stream único | Scratch por slot si se paraleliza | Confirmado por dependencia implícita |
| P08 | ALTO | NaN/Inf en Triton terminan en `inv=0` | Corrupción silenciosa a vector de ceros | Reject explícito de finitud | Confirmado por análisis del kernel |
| P09 | ALTO | Kahan router es `f32`, no `f64` | Precisión menor de la declarada | Sumas/compensadores `f64` por lane | PoC numérico reproducible |
| P10 | ALTO | Lift muta antes de validar finitud global | Error `-7` puede dejar tensor parcialmente modificado | Validación previa + cálculo temporal + commit | PoC de orden de operaciones |
| P11 | ALTO | Lift singularity threshold absoluto | El mismo `1e-12` significa cosas distintas según escala de J | Umbral relativo/condicionado | Revisión matemática |
| P12 | ALTO | Consensus `Vec<f32>` por llamada | Heap churn en hot path | Workspace/slab reutilizable | Confirmado por código |
| P13 | ALTO | Consensus no valida local/neighbors/weights finitos | NaN puede pasar a ruta de éxito | Validar todos los buffers antes de mutar | PoC de NaN |
| P14 | ALTO | Seqlock Rust `end_write()` sin token de ownership | Un caller puede cerrar una escritura que no inició | Begin retorna token; end consume token | Confirmado por API |
| P15 | ALTO | RDMA sin CQ completion ni fence GPU→NIC | Puede publicar "éxito" antes de transferencia efectiva | CQ + stream/event contract explícito | Confirmado por código |
| P16 | MEDIO/ALTO | ABI RDMA manual | Frágil ante headers/ABI distintos | bindgen / headers target + asserts |
| P17 | MEDIO | C++ AVX2 no verifica XCR0/YMM OS support | Posible `#UD` en OS que no preserva YMM | Verificar XCR0 bits 1:2 para AVX/AVX2 | Confirmado por código |
| P18 | MEDIO | C++ cache query Linux no filtra Level 1 | Puede devolver una caché Data/Unified distinta de L1 | Exigir `level==1` | Confirmado por código |
| P19 | MEDIO | Windows cache info usa buffer fijo de 256 entradas | Puede ser insuficiente | Primera llamada para size + alloc dinámico | Confirmado por API usada |
| P20 | MEDIO | `PmtpTensorHandle` hace copias implícitas | El usuario puede creer que está en zero-copy | API estricta `copy=False` | Confirmado por código |
| P21 | MEDIO | BF16 + validator C++ mide bytes como f32 | Posible rechazo falso por tamaño | Pasar dtype/element-size explícito | Confirmado por contrato |
| P22 | MEDIO | Dart sólo comprueba puntero nulo | No detecta use-after-free/dangling | Ownership + finalizer + disposed state | Confirmado por código |
| P23 | MEDIO | Missing DLL se convierte en `None` y falla después | Error de diagnóstico tardío | Fail-fast o mock real aislado | Reproducido por construcción |
| P24 | MEDIO | `close()` traga `BufferError` | Oculta leases/views vivos | Tracking de leases + cierre determinista | Confirmado por código |
| P25 | BAJO/ARQUITECTURA | Claim "40KB TLB shootdown barrier" no está justificado por el material revisado | Riesgo de tuning basado en una premisa falsa | Tratar tamaño de slab como parámetro empírico | Verificación externa |

---

## 3. P01 — Integración Rust/C++ rota en el orquestador

### Evidencia

El monolito deriva `rust_name` y `cpp_name` al mismo basename según plataforma. Luego carga ambos paths como si fueran librerías distintas. Más abajo `_bind_cpp_ffi()` es `pass` y `_query_hardware()` fija `self._hw_alignment = 64`.

Además, cuando el archivo no existe, el loader imprime `Mockeando...` y almacena `None`; no existe un objeto mock funcional, de modo que el fallo se retrasa hasta el primer acceso a un símbolo.

### Impacto

Esto es P0 porque mezcla dos fallos conceptuales:

- el objeto que el programa cree que es el gateway C++ no está realmente identificado como tal;
- los resultados de "hardware capability" no prueban hardware real.

### Parche

Separar nombres, por ejemplo:

```python
rust_name = "pmtp_kernel_v507.dll" if is_win else "libpmtp_kernel_v507.so"
cpp_name  = "pmtp_cpp_v507.dll"    if is_win else "libpmtp_cpp_v507.so"
```

Y enlazar explícitamente:

```python
self._cpp_lib.pmtp_cpp_query_alignment_requirement.restype = ctypes.c_int
self._cpp_lib.pmtp_cpp_query_alignment_requirement.argtypes = []

self._cpp_lib.pmtp_cpp_query_cache_line_size.restype = ctypes.c_int
self._cpp_lib.pmtp_cpp_query_cache_line_size.argtypes = []

self._hw_alignment = int(self._cpp_lib.pmtp_cpp_query_alignment_requirement())
```

En producción, librería ausente = excepción inmediata con ruta exacta; no `None` silencioso.

### Criterio de aceptación

- Rust y C++ tienen filenames distintos.
- `ctypes.CDLL()` carga dos handles distintos.
- `_query_hardware()` devuelve exactamente lo obtenido del símbolo C++.
- Test modifica artificialmente el mock C++ y demuestra que Python no usa una constante.

---

## 4. P02/P03 — SeqLock Python: no hay atomicidad real ni double buffer

### Evidencia

El slab Python hace:

```python
self._seq_ptr = ctypes.cast(..., ctypes.POINTER(ctypes.c_uint64))
...
self._seq_ptr[0] += 1
```

El propio código reconoce que esto no es un mecanismo cross-platform de atomics. `threading.Lock()` sólo cubre hilos del mismo proceso.

Además, `write_slab_atomic()` escribe directamente sobre `self.tensor_array`, y `read_slab()` hace `self.tensor_array.copy()` mientras verifica `seq` antes/después. Eso es el patrón clásico de SeqLock para lectores reintentables, **no** double buffering.

### Por qué el diseño aún tiene un problema

La validación de `seq` puede detectar que el escritor terminó durante la copia y obligar a reintentar. Eso no convierte el payload en inmutable durante una lectura exitosa. Para una carga de 320 KB el lector seguirá haciendo trabajo repetido mientras el escritor escribe; bajo alta frecuencia se puede inducir starvation. Y en Python no se dispone de acquire/release/CAS reales para coordinar procesos portables.

### Solución recomendada

Diseñar el header con dos buffers y un índice publicado:

```text
seq = número de versión (opcional)
published = 0/1
buffer0 = payload
buffer1 = payload
```

Escritor:

```text
back = 1 - published
write(back)
store_release(published, back)
```

Lector:

```text
front = load_acquire(published)
read(front)
```

No liberar/reutilizar el buffer leído hasta que el protocolo de ownership lo permita. Para múltiples lectores, la opción simple es versioning + refcount/epochs; para un único lector, published-index y disciplina de writer suele bastar.

**Importante:** el atomic debe existir en código nativo, no simularse con `ctypes`.

---

## 5. P04 — Triton: `asyncio.Lock` atado a un event loop, pero `ingest_sync()` crea otros

### Evidencia

El ingestor crea `self._lock = asyncio.Lock()`. El wrapper síncrono detecta un loop activo y crea un hilo nuevo con `asyncio.run(self.ingest_and_normalize(...))`.

Eso significa que el mismo objeto puede usarse desde distintos event loops y el lock no es un coordinador thread-safe universal.

### Solución

Elegir una arquitectura, no las dos:

**Opción A — recomendada:** un event loop dueño del ingestor y API `async` solamente.

**Opción B:** usar `threading.Condition`, `queue.SimpleQueue` o un semáforo thread-safe independiente de asyncio. El trabajo GPU se entrega a la cola y el caller espera por evento/future propio.

No crear un nuevo `asyncio.run()` por request.

### Criterio de aceptación

Test con dos hilos concurrentes llamando el mismo objeto 1000 veces: cero deadlocks, cero índices repetidos, cero liberaciones dobles.

---

## 6. P05/P06/P07/P08 — Triton: falso paralelismo, copia final y NaN silencioso

### Evidencia

El ingestor posee cuatro slots, pero todos usan un único `self.stream`. El normalizer comparte `_partials` y `_inv_norm`. Y cada respuesta hace `output.clone()`.

El kernel final calcula:

```python
inv = tl.where(total > 1e-24, tl.rsqrt(total), 0.0)
```

Si `total` es NaN, la condición no es verdadera y el resultado cae a `0.0`. Si `total` es `+Inf`, `rsqrt(+Inf)` también da `0.0`. El vector de salida puede convertirse en ceros sin que el caller reciba un error.

### Solución

Para verdadero overlap:

- stream por slot;
- scratch por slot;
- event por slot;
- estado `FREE/INFLIGHT/READY` por slot;
- retorno como **lease** que mantiene ocupado el slot hasta que el consumidor haga `release()`.

Para la ruta de seguridad numérica:

1. Kernel `finite_check` que devuelve un flag global o contador de no-finitos.
2. Si el flag falla: no escalar ni publicar resultado.
3. Para vector cero: devolver error de "norma demasiado pequeña" en vez de un vector cero silencioso.

Si se conserva `clone()`, debe documentarse como copy-out explícito y medirse como parte de la latencia.

---

## 7. P09 — Kahan declarado f64 pero implementado con estado f32

### Evidencia

En `dot_kahan_4way()` los acumuladores y compensadores están declarados como `f32` y sólo el resultado final se convierte a `f64`.

Eso no es "Kahan f64". Es Kahan f32 + cast final.

### PoC numérico

Con un patrón adversarial en f32 compuesto por bloques `1e8, 1, -1e8`, la referencia de alta precisión es aproximadamente:

```text
reference = 100003333.000000
current f32-Kahan = 100000000.000000
proposed f64-Kahan = 100003333.000000
```

Error observado del estado actual: **3333 unidades** sobre este caso.

### Parche

```rust
let (mut da, mut db, mut dc, mut dd) = (0.0f64, 0.0, 0.0, 0.0);
let (mut ca, mut cb, mut cc, mut cd) = (0.0f64, 0.0, 0.0, 0.0);
```

y hacer lo mismo para las tres familias de sumas.

Después de corregir, comparar contra `math.fsum`/MPFR en tests deterministas con semillas fijas.

---

## 8. P10/P11 — Horizontal Lift puede dejar una mutación parcial y usa singularidad absoluta

### Evidencia

El kernel comprueba que `delta_x/delta_y` sean finitos, pero no valida antes del loop que todos los valores de `tensor`, `Jx` y `Jy` sean finitos. Durante el loop modifica `tensor[i]` y sólo después revisa si `norm_sq` es finita.

Por tanto, un error detectado al final no implica estado inmutable.

También usa `abs(det) < 1e-12`. Un umbral absoluto de determinante no es invariante a escala del Jacobiano.

### Solución

Usar patrón compute→validate→commit:

```text
1. validar inputs completos
2. calcular M y pseudoinversa en scratch f64
3. calcular delta_nd en scratch / segunda pasada
4. calcular norma futura
5. si todo es finito y estable -> commit
6. normalizar
```

Para singularidad, usar condición relativa, por ejemplo comparando `|det(M)|` contra una escala derivada de `trace(M)^2` y un epsilon configurable, o estimar condición explícitamente.

Si el objetivo es preservar `S^(D-1)`, el caso de norma casi cero no debería devolver `0` con éxito.

---

## 9. P12/P13 — Consensus: heap en hot path + NaN bypass

### Evidencia

Cada llamada crea:

```rust
let mut u_i = vec![0.0f32; d_dim];
```

Y valida finitud sólo de `step_size` y `cbf_gamma`, no de `local_tensor`, vecinos ni pesos.

Con NaN en un buffer, las comparaciones posteriores pueden hacer que `norm_sq > 1e-12` sea falsa y aun así el kernel retorne `0`.

### Solución

- workspace reutilizable por agente/slot;
- validación finita previa;
- acumulación f64 por coordenada si la precisión lo exige;
- commit sólo tras completar todos los checks;
- devolver error explícito para norma inválida.

Además, documentar con precisión la barrera CBF. El comentario habla de "distancia angular al centroide", pero la corrección implementada usa `dot(local, u)`. Es necesario demostrar que esa desigualdad es realmente el CBF que se quiere imponer antes de reclamar formalmente "anti-echo-chamber".

---

## 10. P14 — API SeqLock Rust sin ownership de escritura

### Evidencia

La API expone `begin_write()` y `end_write(lock)` sin token de escritor. Un caller que no inició la escritura puede intentar finalizarla.

### Solución

```rust
pub struct WriteToken { epoch: u64, turn: u64 }

fn begin_write(...) -> Result<WriteToken, i64>;
fn end_write(lock: *mut NodeSignatureSeqLock, token: WriteToken) -> i64;
```

Alternativamente, hacer que `begin_write()` devuelva el valor impar y que `end_write(expected_odd)` sólo pueda cambiar `odd -> odd+1` mediante CAS.

Esto también facilita detectar writers abandonados y recovery controlado.

---

## 11. P15/P16 — RDMA: ABI manual y ausencia de completion / GPU ordering

### Qué sí está bien

Los offsets actuales de `ibv_send_wr` y `ibv_mr` inspeccionados son coherentes con el layout convencional 64-bit de rdma-core revisado externamente. Esto **no** convierte el ABI manual en robusto frente a cualquier plataforma/versión.

### Problemas reales

1. `ibv_post_send()` sólo confirma aceptación del WR por el provider; no demuestra completion remoto/local.
2. No se ve una ruta CQ que espere el completion del WR.
3. Un `fence(Ordering::SeqCst)` de CPU no sustituye una sincronización CUDA stream/event antes de que NIC lea VRAM.
4. Se declara `ibv_dereg_mr`, pero no hay una API equivalente de lifecycle en el código revisado.
5. Los offsets internos (`mr.add(16)`, `mr.add(36)`) deben ser generados/validados contra los headers del target, no mantenidos a mano.

### Solución

- bindgen sobre el `verbs.h` del build target;
- asserts de size/offset sólo como alarmas;
- API `post + poll_completion`;
- contrato explícito `CUDA event -> stream sync/IPC -> RDMA post`;
- lifecycle de MR con `register/deregister` emparejados.

---

## 12. P17/P18/P19 — C++ hardware interrogation

### P17 — AVX2

El detector consulta AVX2 por CPUID y devuelve 32 bytes, pero no comprueba que el OS haya habilitado el estado YMM vía OSXSAVE/XGETBV. La verificación existente de XCR0 sólo se aplica al camino AVX-512.

**Fix:** usar una función genérica `os_supports_avx()` que compruebe OSXSAVE y XCR0 bits 1:2 antes de AVX/AVX2, y bits ZMM adicionales antes de AVX-512.

### P18 — cache line Linux

El loop filtra por `type == Data/Unified`, pero no por `level == 1`, a pesar de que el comentario dice que se busca L1D.

**Fix:** leer `level` y exigir `level == 1`.

### P19 — Windows

`GetLogicalProcessorInformation` se usa con un buffer fijo de 256 estructuras. El patrón robusto es consultar primero el tamaño requerido, reservar y repetir.

---

## 13. P20/P21 — TensorHandle: copias implícitas y BF16 inconsistente

### Evidencia

`PmtpTensorHandle` convierte silenciosamente no-contiguous con `.contiguous()`, FP16/FP64 a FP32 con `.to(torch.float32)`, y puede crear pinned memory con `.pin_memory()`.

Eso es correcto para una API de conveniencia, pero **no** es una API zero-copy.

Además, el path BF16 mantiene element size de 2 bytes, mientras el validator C++ mostrado calcula suficiencia usando `sizeof(float)`.

### Solución

Separar:

```python
PmtpTensorHandle.from_cpu_f32_zero_copy(tensor)
PmtpTensorHandle.from_tensor_copy(tensor)
```

y en el validator pasar `dtype_size` o `byte_len` real.

---

## 14. P22 — Dart FFI: null != alive

### Evidencia

El bridge sólo comprueba `address == 0`. Un puntero liberado/dangling normalmente sigue teniendo una dirección no nula.

Además, `SemanticNode` guarda punteros crudos sin ownership/finalizer explícito.

### Solución

- objeto native owner por nodo;
- `NativeFinalizer` o lifecycle equivalente;
- estado `disposed` y guardas antes de cada FFI call;
- asociar dimensión y capacity al handle, no asumir `D=10000` en el lado Dart;
- no ejecutar trabajo FFI desde una ruta de UI que pueda quedar indefinidamente bloqueada.

---

## 15. P23 — "Mock" de DLL inexistente no es un mock

El código imprime `Mockeando...` y guarda `None`. Eso sólo difiere el fallo.

**Regla recomendada:** production path = fail-fast. Los mocks deben vivir en un módulo separado y tener la misma firma ABI lógica, pero ningún símbolo nativo puede quedar `None` en una instancia productiva.

---

## 16. P24 — cierre de SHM

`close()` atrapa `BufferError` y continúa. Eso puede ocultar views/pointers vivos.

**Fix:** tracking explícito de leases/exported views y un `close()` que falle de manera diagnóstica si quedan referencias prestadas. Añadir `__enter__/__exit__`.

---

## 17. Garbage Collector

No se encontraron llamadas `gc.disable()` / `gc.enable()` en los archivos suministrados.

Eso **no es un error**. No hay evidencia para recomendar desactivar el GC globalmente. En cambio, sí hay hot-path allocations reales: `vec![...]` en Consensus, conversiones implícitas de `TensorHandle`, `clone()` en Triton y estructuras temporales. Esos son los objetivos correctos de optimización.

---

## 18. Alineación FFI / `repr(C, align(128))`

La estructura Rust usa `#[repr(C, align(128))]` y la versión Python usa `_align_ = 128`. En el runtime Python disponible para esta auditoría la estructura resultó `size=128, alignment=128`.

Esto **no** certifica cualquier runtime futuro. Hay que mantener un test binario que compare `sizeof/alignof/offsetof` Rust↔Python en CI.

La alineación no debe confundirse con una garantía de atomicidad ni con una prueba de que un puntero concreto está alineado para una instrucción SIMD.

---

## 19. Sobre el claim del slab de 320 KB

El material del proyecto afirma que existe una "barrera de 40 KB" y que juntar 8 tensores en 320 KB la supera.

La documentación revisada de Mooncake FAST25 no permite concluir una barrera universal de hardware de 40 KB. Una de las pruebas citadas usa una granularidad mínima de transferencia de 128 KB, pero eso no demuestra un umbral universal de "TLB shootdown" en 64 KB/40 KB.

**Conclusión red-team:** 320 KB puede ser un buen valor de tuning; no debe presentarse como una constante física demostrada sin benchmark reproducible por plataforma.

---

## 20. Resultados de pruebas ejecutadas

### Entorno

- Python: 3.13.5
- NumPy: disponible
- PyTorch: 2.10.0+cpu
- CUDA: no disponible
- Triton: no instalado
- rustc: no instalado
- g++: disponible
- pytest: disponible

### Pruebas

- Import de Python: PASS
- Layout SHM: `size=128`, `align=128` — PASS
- Detección estática de colisión Rust/C++: PASS (detector)
- Detección de hardware hardcodeado: PASS (detector)
- Detección de fake atomic Python: PASS (detector)
- Detección de Kahan no-f64: PASS (detector)
- PoC numérico Kahan: PASS (reproduce el error)
- PoC de mutación parcial de Lift: PASS (reproduce la condición)
- PoC de NaN en Consensus: PASS (reproduce la ruta de éxito con estado inválido)
- `py_compile`: PASS
- Sintaxis C++ Linux con warnings: PASS
- Build Rust: **NO EXECUTABLE — `rustc` no instalado**
- GPU/Triton: **NO EXECUTABLE — CUDA/Triton no disponibles**

### Baseline real medido en este entorno

Benchmark de roundtrip del slab SHM/Python, 30 iteraciones:

```text
p50 = 21.7 us
p95 = 35.8 us
min = 21.3 us
max = 343.2 us
```

Este baseline **no** debe interpretarse como benchmark de producción ni compararse con un supuesto post-parche que no se ejecutó.

---

## 21. Qué ya parece correcto / no debe romperse

- El guard de `panic=abort` en Rust evita aceptar una configuración insegura para FFI.
- `catch_unwind` alrededor de exports FFI es una defensa razonable para errores recuperables de Rust.
- `MxcsrGuard` sí restaura MXCSR mediante RAII incluso si el closure entra en panic.
- Los asserts de size/offset del ABI son útiles como alarma, aunque no sustituyen a bindings generados.
- La corrección de `rkey` en el layout documentado coincide con el layout convencional de rdma-core revisado.
- La comprobación `sizeof/alignof` del header merece mantenerse.

No convertir estos puntos buenos en razón para relajar los P0/P1 anteriores.

---

## 22. Plan de reparación recomendado

### Fase A — cortar corrupción / falsos positivos

1. Separar Rust/C++ DLL names.
2. Fail-fast si falta una librería nativa.
3. Eliminar atomics simulados con `ctypes`.
4. Implementar double buffer + published index nativo.
5. Validar finitud completa antes de mutar.
6. Corregir Kahan a estado f64 real.

### Fase B — arreglar concurrencia

7. Un solo event loop para el ingestor o coordinador thread-safe.
8. Stream/scratch por slot Triton.
9. Lease explícito para salida; evitar `clone()` si la ruta exige zero-copy.
10. Token de ownership para `seqlock_end_write`.

### Fase C — endurecer hardware/network

11. AVX2 + XGETBV correcto.
12. L1D real en Linux.
13. Buffer dinámico en Windows.
14. bindgen para rdma-core.
15. CQ completion.
16. CUDA event/stream → RDMA ordering contract.

### Fase D — lifecycle/API

17. Tensor handle zero-copy explícito.
18. BF16/FP32 byte-size contract único.
19. Dart ownership/finalizers.
20. SHM lease tracking + close determinista.

---

## 23. Release gates

No liberar hasta que todos sean PASS:

- [ ] Rust/C++ filenames y handles distintos.
- [ ] Hardware query nunca usa constantes en producción.
- [ ] Missing DLL = error inmediato.
- [ ] SeqLock cross-process usa atomics reales.
- [ ] Payload publicado mediante double buffer o mecanismo equivalente.
- [ ] Ningún `error != 0` deja mutación parcial del tensor.
- [ ] Router Kahan usa acumuladores/compensadores f64.
- [ ] Consensus rechaza NaN/Inf de cualquier buffer.
- [ ] Triton no comparte scratch entre streams.
- [ ] Triton no crea loop por request.
- [ ] Output ownership evita clone involuntario.
- [ ] RDMA espera completion.
- [ ] GPU→NIC ordering está especificado y probado.
- [ ] ABI generado contra headers reales.
- [ ] Dart tiene ownership y finalization.
- [ ] Benchmarks before/after ejecutados sobre el mismo hardware.

---

## 24. Regla de evidencia para la siguiente iteración

Cada parche debe venir acompañado de:

```text
1. bug reproducer
2. patch
3. expected invariant
4. raw log
5. benchmark before
6. benchmark after
7. hardware/software configuration
```

No usar "PASS" como sinónimo de "sistema sano" cuando el test es un detector de vulnerabilidad. En los logs de esta auditoría, `PASS | kahan_not_f64`, por ejemplo, significa "el detector confirmó que el defecto existe".

---

## 25. Evidencia cruda

El siguiente bloque reproduce sin edición el log de la batería ejecutada:

```text
===== POLYDIM V507 REDTEAM TEST OUTPUT =====
PASS | python_imports | monolith imports
PASS | shm_header_layout | size=128 align=128
PASS | dll_name_collision | Rust and C++ use same DLL basename
PASS | mock_missing_dll | missing native libraries are converted to None
PASS | hardware_query_hardcoded | hardware query is constant and C++ binding is empty
PASS | slab_python_atomic_claim | ctypes integer access is used as claimed atomic operation
PASS | kahan_not_f64 | Kahan lanes/compensators are f32
PASS | consensus_heap_alloc | per-call heap allocation
PASS | lift_checks_params_not_tensor | tensor/J finite values not validated before mutation
PASS | rdma_manual_abi | manual ABI offsets
PASS | triton_clone_alloc | per-request output copy/allocation
PASS | triton_shared_async_lock | lock shared across event loops
PASS | triton_nan_unchecked | no explicit NaN/Inf validation
PASS | triton_one_stream | single stream serializes work
PASS | kahan_numeric_poc | ref=100003333.000000 current_f32=100000000.000000 proposed_f64=100003333.000000
PASS | lift_partial_mutation_model | current ordering permits partial mutation before -7
PASS | consensus_nan_model | NaN can pass through to success path
PASS | python_compile |
PASS | cpp_linux_syntax |
FINDING | rust_build_available | rustc not installed in audit container
PASS | slab_baseline_bench | roundtrip_us_p50=21.7 p95=35.8 min=21.3 max=343.2
===== END OUTPUT =====
```

---

## 26. Estado de los parches

El archivo `polydim_v507_redteam.patch` contiene el **parche propuesto completo**, pero no reemplaza silenciosamente los archivos fuente entregados. La auditoría mantiene separación estricta entre:

- fuente original;
- parche recomendado;
- tests que reproducen el defecto;
- evidencia de ejecución.

Eso permite que la siguiente iteración sea auditable y reversible.
