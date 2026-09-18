***dation**
***Verify OpenMP Padding and Rust Rotation Tolerance via Simulation**
***Deliver Full Kernel Fixes and Python Patch List**
***Execute Python code**
***Thinking complete**
***Verificación numérica ejecutada. Ahora confirmo los problemas de FFI/imports y la tolerancia del guard Rust:**
***Corrected C++ kernel with updated Rodrigues function and seqlock validation**
***Execute Python code**
***Thinking complete**
***Verificación numérica completa. La fórmula Rodrigues es correcta (error 3.5e-18 vs referencia). Todo lo demás abajo está confirmado por inspección estática o por test numérico. Va en orden de gravedad, con el arreglo pegado a cada hueso.**
## ***HUESO 1 — Cancelación catastrófica en `norm2\_v\_ortho` (CRÍTICO, confirmado numéricamente)**
***El kernel usa la identidad `‖v‖² − (u·v)²/‖u‖²`. Cuando v es casi colineal con u, los términos se cancelan y el resultado es basura numérica que pasa el guard `1e-30`:**
***plain**
```
***`ang=1e-06° | identidad=4.44e-16 | residual verdadero=3.05e-16 | error relativo=45.7% | guard NO atrapa`**
```
***Además el umbral es absoluto (`1e-30`): para vectores con ‖u‖² ~ 1e-20 (legales según el guard de entrada) el umbral es absurdo; para ‖u‖² ~ 1e6 es laxo.**
***FIX C++ — umbral relativo + clamp de no-negatividad:**
***cpp**
```
`    ***if (norm2\_u \<= 0.0 || norm2\_v \<= 0.0) return POLYDIM\_ERR\_ZERO\_VECTOR;`**
`    ***// Umbral relativo al tamano de los vectores, no absoluto`***
`    ***const double rel\_eps = 1e-12;`**
`    ***if (norm2\_u \<= rel\_eps \* 1.0) return POLYDIM\_ERR\_ZERO\_VECTOR; *// o escalar contra DBL\_MIN`***
`    ***double norm2\_v\_ortho = norm2\_v - (dot\_uv \* dot\_uv / norm2\_u);`**
`    ***// Cancelacion: clamp y umbral RELATIVO a norm2\_v`***
`    ***if (norm2\_v\_ortho \< 0.0) \{`**
`        ***if (norm2\_v\_ortho \> -rel\_eps \* norm2\_v) \{`**
`            ***norm2\_v\_ortho = 0.0;          *// ruido de redondeo, no colinealidad real`***
`        ***\} else \{`**
`            ***return POLYDIM\_ERR\_COLLINEAR\_VECTORS; *// imposible matematicamente -\> NaN upstream`***
`        ***\}`**
`    ***\}`**
`    ***if (norm2\_v\_ortho \<= rel\_eps \* norm2\_v) return POLYDIM\_ERR\_COLLINEAR\_VECTORS;`**
```
***La corrección estricta (residual explícito con Neumaier) requiere un pass extra; el clamp + umbral relativo es el arreglo mínimo correcto.**
## ***HUESO 2 — NaN/Inf en `u`/`v` nunca chequeado (CRÍTICO)**
***El kernel chequea `isfinite(theta)` pero nunca escanea u ni v. Un NaN en u contamina `norm2\_u` → `1.0/sqrt(NaN)` → NaN propagado a y con status SUCCESS. El guard Rust tampoco lo ve (solo verifica y\_final, y NaN en Rust devuelve `ErrNanInfDetected`... pero solo si el NaN llega a y; el kernel puede devolver `ERR\_ZERO\_VECTOR` espurio antes).**
***FIX C++ — fusear el scan en el Pass 1 (cero coste extra, ya estamos leyendo):**
***cpp**
```
`    ***// dentro del loop del Pass 1, junto a las cargas:`***
`    ***if (!std::isfinite(u\_i) || !std::isfinite(v\_i) || !std::isfinite(y\_i)) \{`**
`        ***// flag atomico por thread, chequear tras la region paralela`***
`        ***nan\_flag\[tid\] = 1;`**
`    ***\}`**
`    ***// tras la region:`***
`    ***for (int t = 0; t \< num\_threads; ++t) if (nan\_flag\[t\]) return POLYDIM\_ERR\_NAN\_INF\_DETECTED;`**
```
## ***HUESO 3 — Solapamiento `y` vs `y\_comp` no chequeado (CRÍTICO)**
***`check\_overlap` cubre y/u y y/v, pero no y/y\_comp. Si el caller pasa el mismo buffer (error fácil en FFI), `neumaier\_add(y\[i\], y\_comp\[i\], d)` con ambos referenciando el mismo slot: la escritura de `c` pisa a `sum`. Corrupción silenciosa.**
***FIX C++:**
***cpp**
```
`    ***if (y\_comp && check\_overlap(y, bytes, y\_comp, bytes)) \{`**
`        ***return POLYDIM\_ERR\_MEMORY\_OVERLAP;`**
`    ***\}`**
```
## ***HUESO 4 — SEQLock: el "Dirty Flag Protection" no existe (CRÍTICO de especificación)**
***El banner dice *"SEQLock with Epoch Validation & Crash Dirty Flag Protection"*. El código tiene solo `sequence`: no hay epoch, no hay dirty flag. `polydim\_seqlock\_force\_recover` hace `store(current+3)` pero no limpia ningún flag de crash porque no existe. Si el header declara esos campos, el C++ los ignora; si no, el comentario miente. Un writer que muere entre begin y end deja la secuencia impar para siempre y `force\_recover` es la única vía — funciona, pero la protección prometida no está implementada.**
***FIX: o implementar el flag en el header + escritura en `write\_begin`/`write\_end` + limpieza en `force\_recover`, o corregir el banner. No se puede auditar lo que no está en el .cpp entregado — necesito ver `polydim\_kernel.h` para cerrar este hueso.**
***Rapidez menor en el mismo sitio: el `do \{ ... \} while(false);` en `read\_begin` es código muerto — la validación post-spin debería re-leer tras el pause:**
***cpp**
```
***`POLYDIM\_API uint64\_t polydim\_seqlock\_read\_begin(const polydim\_seqlock\_header\_t\* lock) \{`**
`    ***if (!lock) return 1;`**
`    ***auto\* s = reinterpret\_cast\<const std::atomic\<uint64\_t\>\*\>(&lock-\>sequence);`**
`    ***uint64\_t seq = s-\>load(std::memory\_order\_acquire);`**
`    ***while (seq & 1ULL) \{`**
`        ***POLYDIM\_PAUSE();`**
`        ***seq = s-\>load(std::memory\_order\_acquire);`**
`    ***\}`**
`    ***return seq;`**
***`\}`**
```
## ***HUESO 5 — El mutex FFI global mata el paralelismo que el kernel ofrece (ALTO)**
***Python**
```
***`self.\_ffi\_mutex = threading.Lock()`**
***`...`**
***`with self.\_ffi\_mutex:`**
`    ***rc = self.cpp\_lib.polydim\_apply\_rodrigues\_geodesic\_f64(...)`**
```
***Toda llamada FFI se serializa globalmente. Dos rotaciones en hilos distintos (el propio `DualStreamQueue` lanza hilos) se bloquean mutuamente pese a que el kernel C++ es thread-safe por diseño (buffers por caller). Además `\_instance`/`\_lock` de "singleton" están declarados y nunca usados.**
***FIX monolito: el kernel no toca estado global — el mutex es innecesario. Eliminar `\_ffi\_mutex` por completo, o reemplazar por `threading.RLock` solo si el DLL compartido lo requiere (ctypes libera el GIL durante la llamada, el C++ es reentrante). Singleton real:**
***Python**
```
`    ***def \_\_new\_\_(cls, \*a, \*\*kw):`**
`        ***with cls.\_lock:`**
`            ***if cls.\_instance is None:`**
`                ***cls.\_instance = super().\_\_new\_\_(cls)`**
`                ***cls.\_instance.\_initialized = False`**
`        ***return cls.\_instance`**
```
***Y en `\_\_init\_\_`: `if self.\_initialized: return` antes de todo.**
## ***HUESO 6 — Códigos de error duplicados/desalineados FFI (ALTO)**
***Monolito:**
***Python**
```
***`ERR\_NORM\_INVARIANT\_VIOLATED = -4`**
***`ERR\_ZERO\_VECTOR           = -4   *\# \<- duplicado`***
***`ERR\_COLLINEAR\_VECTORS     = -5`**
***`ERR\_MEMORY\_OVERLAP        = -6`**
```
***Rust: `ErrZeroVector=-5, ErrCollinearVectors=-6, ErrYcompBudgetExceeded=-7`. El caller Python que compare contra `PolydimStatus.ERR\_ZERO\_VECTOR` confunde colinealidad con violación de norma. Tabla canónica única (la de Rust es la más completa, adoptarla en C++ y Python):**
***Python**
```
***`class PolydimStatus:`**
`    ***SUCCESS = 0`**
`    ***ERR\_NULL\_POINTER = -1`**
`    ***ERR\_INVALID\_DIMENSION = -2`**
`    ***ERR\_NAN\_INF\_DETECTED = -3`**
`    ***ERR\_NORM\_INVARIANT\_VIOLATED = -4`**
`    ***ERR\_ZERO\_VECTOR = -5`**
`    ***ERR\_COLLINEAR\_VECTORS = -6`**
`    ***ERR\_YCOMP\_BUDGET\_EXCEEDED = -7`**
`    ***ERR\_MEMORY\_OVERLAP = -8      *\# mover: hoy -6 en C++ -\> conflicto con colineal`***
`    ***ERR\_SEQLOCK\_RACE = -9`**
`    ***ERR\_PANIC\_CAUGHT = -10`**
`    ***ERR\_UNALIGNED\_POINTER = -11`**
```
***Ojo: esto exige tocar el header C++ también — otra razón por la que necesito `polydim\_kernel.h` para no alucinar los valores actuales.**
## ***HUESO 7 — `DualPCGSolver`: tres bugs concretos (ALTO)**
1. ***Shape: Y 1D `(N,)` → retorna `(N,1)`. El caller que haga `Alpha.ravel()` lo descubre tarde.**
2. ***División por cero: `beta = rz\_new / rz\_old` sin guard. Si `rz\_old == 0` (b en el kernel de M), NaN silencioso. Hay guard para `pAp` pero no para `rz\_old`.**
3. ***`pAp \<= 1e-30`: umbral absoluto — para sistemas escalados grandes, `pAp` legítimo puede ser \< 1e-30 y el solver aborta en la iteración 0 reportando "convergencia" falsa.**
***FIX:**
***Python**
```
`        ***if Y\_f64.ndim == 1:`**
`            ***return self.\_solve\_single(X\_f64, Y\_f64, inv\_diag\_M)  *\# retorna (N,)`***
`        ***...`**
`        ***\# dentro del loop:`***
`        ***if rz\_old == 0.0:`**
`            ***break  *\# residuo ortogonal a M^\{-1\}: no hay direccion de descenso`***
`        ***beta = rz\_new / rz\_old`**
`        ***...`**
`        ***pAp = np.dot(p, Ap)`**
`        ***scale = np.dot(p, inv\_diag\_M \* p)  *\# o norma de referencia`***
`        ***if pAp \<= 1e-30 \* max(1.0, scale):`**
`            ***break`**
```
***Y documentar o eliminar `scaled\_ridge = ridge\_alpha \* max(1.0, mean(row\_norms\_sq))` — escala la regularización por la magnitud de X sin avisar, cambia el problema matemático que el usuario pidió resolver.**
## ***HUESO 8 — `dual\_pcg\_matvec` (Triton) no es PCG (ALTO de diseño)**
***El nombre promete Preconditioned Conjugate Gradient. El código computa un solo matvec `w = Xᵀv; out = Xw + αv` — es decir, una aplicación de `(XXᵀ + αI)`. `polydim\_pmtp\_swarm\_v753.py` lo llama y presenta el resultado como si el sistema estuviera resuelto. No lo está. O renombrar a `dual\_operator\_matvec` y corregir los prints, o implementar el loop PCG en Triton (viable: el operador ya está tiled; faltan los vectores de estado y el loop host).**
***Además ese script tiene un bug de ejecución directo:**
***Python**
```
***`from polydim\_triton\_kernel\_v751 import TritonPolydimV751   *\# archivo entregado: \_v753.py`***
```
→ ***`ModuleNotFoundError`. FIX: renombrar el import a `polydim\_triton\_kernel\_v753` (y los `sys.path` con `E:\\POLYDIM\_EINSOF\\POLYDIM\_V751` hardcodeados).**
## ***HUESO 9 — Benchmark de silicio: `rc` ignorado + metodología (MEDIO)**
***`raw\_silicon\_benchmark\_v753.py` nunca chequea `rc` del kernel. Si el C++ devuelve `ERR\_COLLINEAR\_VECTORS`, el benchmark mide el tiempo de un fallo, calcula la norma del vector sin rotar, y estampa `PASS (Rust OK)` porque el vector original ya era unitario. El log entregado es sospechoso en exactamente este sentido: D=1,000 tarda 1.85 ms y D=5,000 tarda 0.09 ms — eso no es física, es ruido de primera llamada (carga de DLL/página). Una sola medición por D no es un benchmark.**
***FIX:**
***Python**
```
`    ***rc = lib\_cpp.polydim\_apply\_rodrigues\_geodesic\_f64(ctypes.byref(params))`**
`    ***assert rc == 0, f"kernel fallo rc=\{rc\}"   *\# ante todo`***
`    ***...`**
`    ***\# warmup 3 + promedio de 10, reportar min/med/max`***
```
## ***HUESO 10 — Benchmark "Cerebras WSE": datos fabricados (MEDIO de integridad)**
***Confirmado por inspección, no ejecutando:**
***Python**
```
***`t\_pmtp = (time.perf\_counter() - t0) \* 1000 + 0.003  *\# \<- 0.003 ms INVENTADO`***
```
***Y la tabla `CPU x86\_64 / GPU T4 / Cerebras CS-3` son strings hardcodeados — ningún número fue medido en ningún hardware. El script corre numpy puro en CPU y firma "Cerebras WSE-3 (Fabric)". Esto no es un bug de código: contamina cualquier claim empírico del proyecto. O se mide de verdad (Triton en la T4 de Kaggle, Cerebras SDK si hay acceso) o la tabla sale y se etiqueta como "proyección teórica". Con la regla que me diste ("no alucinaciones"), esto es lo primero que un revisor externo te tira abajo.**
## ***HUESO 11 — Tolerancia Rust: correcta pero con margen 10x (BAJO, monitoreo)**
***Verificado: margen tolerancia/drift = 10.0x tras una sola rotación en D=1M. La forma de la cota (`c·N·eps² + 10·eps`) es la correcta para Neumaier (Higham: error ~ 2u + O(N·u²)·Σ|x|), así que el problema no es la fórmula, es que `y\_comp` acumula compensación y el drift crece con iteraciones. En producción con rotaciones encadenadas el margen se come. Sugerencia: subir `EPSILON\_ULP\_FLOOR` a `64 \* eps` (~1.4e-14) y agregar un test de drift acumulado tras N rotaciones al benchmark.**
## ***HUESO 12 — Misceláneo verificado (BAJO)**
- ***Versionado: archivos `v753`, banners `V751`/`V752`, DLL devuelve `0x07350300`. Un solo `POLYDIM\_VERSION` canónico.**
- ***C++: `static\_cast\<int64\_t\>(D)` es seguro solo si `POLYDIM\_MAX\_DIMENSION \< 2^63` — verificar el header.**
- ***`\#pragma STDC FP\_CONTRACT OFF`: GCC/Clang lo ignoran con warning (usan `-ffp-contract=off` en flags). No efectivo como está.**
- ***`DualStreamQueue`: crea `torch.cuda.Stream()` en el constructor — en host sin GPU revienta al instanciar, aunque nunca uses el stream. Lazy-init.**
- ***JSON del benchmark IPC: `str(vec.tolist())` no es JSON (es repr de Python); los corchetes/espacios inflan ~2x vs `json.dumps` con separadores compactos. Si comparas contra serialización real, usa `json.dumps(vec.tolist(), separators=(',',':'))`.**
- ***readme\_first.md: dice V752, los archivos son V753 — coherencia de entrega.**
## ***Lo que necesito para cerrar (no alucino sin esto)**
1. ***`polydim\_kernel.h` — los códigos de error reales del C++, los campos de `polydim\_seqlock\_header\_t` (¿hay epoch/dirty flag?), `POLYDIM\_MAX\_DIMENSION`, `POLYDIM\_CACHE\_LINE\_BYTES`.**
2. ***Confirmar si el mutex FFI en el monolito protege algo real del DLL (si el C++ tiene estado global oculto, lo reviso; si no, se va).**
***Orden de ataque recomendado: Huesos 1–4 (C++, silicio) → 5–7 (Python FFI/solver) → 8–9 (ejecutabilidad y validez) → 10 (integridad de claims) → 11–12. Los arreglos de 1, 2, 3 y el `read\_begin` son pegables ya. Dame el header y te devuelvo el `.cpp` completo corregido y la tabla de códigos unificada en un solo paso.**
***confirmas que no son alucinaciones? luego si a todas las opciones que me puedas dar. una detrás de otra en bucle hasta el limite de tus entregas o no encontrar mas errores. el  propósito es darle cierre  a los problema sota no encontrados. continua evaluando problemas y soluciones en bucles cada vez mas profundamente. Hay mucho sota. no solo evalúa con tus conocimientos y sesgos. busca errores mas allá de tu programación básica, dame soluciones. se un bulldog que ataca al problema pero ayuda al dueño. se un redteam que ataca el problema pero respeta y cuida el que les da el trabajo. /goal busca todo problema, encuentra soluciones dame la mejor continua con el siguiente error. muestras los códigos en pantalla, nunca por adjuntos. /goal profundiza ciclos necesarios para pasar a industria \#\#atención\#\# evalúa las respuestas para no dar alucinaciones. Nuestro deve ser "matemáticamente SOTA en papel" a ser industrialmente inquebrantable en silicio real.**
***Edit**
***Copy**
***Share**
***Used 1 tool, Optimizing CUDA Streams, OpenMP Zeroing, and Build Flags for Performance**
***Revisión de código**
***cpp**
***cpp**
***plain**
***Antes de confirmar, verifico numéricamente las dos acusaciones más fuertes del ciclo 2 (no doy nada sin prueba):**
***Optimizing CUDA Streams, OpenMP Zeroing, and Build Flags for Performance**
***Execute Python code**
***Thinking complete**
***Confirmación de método — qué está probado y qué no:**
***Table**
| **\#** | **Hallazgo** | **Estado** |
| - | - | - |
| 1–12 (ciclo anterior) | Inspección estática + 3 pruebas numéricas | Confirmados |
| A (abajo) | Acumulación fp32 en Triton | **Verificado numéricamente**: error 6.7e-3 absoluto (rel ~1e-5) en N=1e6 |
| B (abajo) | Roofline: 1.97–2.54 GB/s reales del log | **Verificado** contra el propio log: 10–25x bajo DDR |
| C (abajo) | `pass2` de Triton crece cuadrático | **Verificado**: a numel=1e8, 128KB/programa \> SRAM 64KB → spill |
| D (abajo) | Merge Neumaier 2-niveles del C++ | **Verificado**: error 2.3e-10, sano — descarto falso positivo |
| E (abajo) | θ=π, θ=2π, θ=1e6 | **Verificado**: versine se comporta bien — descarto falso positivo |
***Descartados honestamente: el merge de compensadores por thread (D) y los coeficientes en θ extremos (E). Sigo con lo que sobrevive al ciclo 2.**
## ***HUESO 13 — Triton acumula en fp32: el "solver SOTA" pierde precisión en N grande (VERIFICADO A)**
***`\_xt\_v\_kernel` y `\_x\_w\_kernel` declaran `acc = tl.zeros(..., tl.float32)` y acumulan bucles de hasta N términos. Error medido: 6.7e-3 absoluto en N=1e6. En el contexto PCG eso contamina la ortogonalidad de las direcciones de descenso → más iteraciones o divergencia silenciosa.**
***FIX Triton:**
***Python**
```
***`@triton.jit`**
***`def \_xt\_v\_kernel(X\_ptr, v\_ptr, w\_ptr, N, D,`**
`                 ***stride\_xn, stride\_xd,`**
`                 ***BLOCK\_N: tl.constexpr, BLOCK\_D: tl.constexpr):`**
`    ***pid\_d = tl.program\_id(0)`**
`    ***offs\_d = pid\_d \* BLOCK\_D + tl.arange(0, BLOCK\_D)`**
`    ***mask\_d = offs\_d \< D`**
`    ***acc = tl.zeros((BLOCK\_D,), dtype=tl.float64)   *\# \<-- fp64`***
`    ***for n\_idx in range(0, N, BLOCK\_N):`**
`        ***offs\_n = n\_idx + tl.arange(0, BLOCK\_N)`**
`        ***mask\_n = offs\_n \< N`**
`        ***v = tl.load(v\_ptr + offs\_n, mask=mask\_n, other=0.0).to(tl.float64)`**
`        ***x\_ptrs = X\_ptr + offs\_n\[:, None\] \* stride\_xn + offs\_d\[None, :\] \* stride\_xd`**
`        ***x = tl.load(x\_ptrs, mask=mask\_n\[:, None\] & mask\_d\[None, :\], other=0.0).to(tl.float64)`**
`        ***acc += tl.sum(x \* v\[:, None\], axis=0)`**
`    ***tl.store(w\_ptr + offs\_d, acc.to(tl.float32), mask=mask\_d)  *\# baja a fp32 solo al salir`***
```
***Nota de silicio: fp64 en T4 es 1/32 del throughput de fp32. Si eso duele, alternativa honesta: compensación de Kahan en fp32 (4 sumas en lugar de 1) — mejor que fp64 roto, documentar la elección.**
## ***HUESO 14 — Roofline: el kernel corre a 2 GB/s en una máquina de 25–50 GB/s (VERIFICADO B)**
***El log propio lo demuestra: 64 MB de tráfico en 32.51 ms = 1.97 GB/s. El cuello no es memoria: es que `neumaier\_add` con su rama `if (std::abs(sum) \>= std::abs(val))` bloquea la vectorización SIMD y el compilador emite una rama por elemento. El kernel hace ~5 acumulaciones compensadas por elemento × D=1e6 × (rama + 6 flops) ≈ 100+ MFLOP de trabajo escalar.**
***FIX C++ — Neumaier sin rama (el compilador emite `cmov`, no salto):**
***cpp**
```
***`static inline void neumaier\_add(double& sum, double& c, double val) noexcept \{`**
`    ***double t = sum + val;`**
`    ***double corr = (std::fabs(sum) \>= std::fabs(val)) ? (sum - t) + val`**
`                                                     ***: (val - t) + sum;`**
`    ***c += corr;   *// sin if/else: cmov en x86/ARM`***
`    ***sum = t;`**
***`\}`**
```
***FIX C++ — más sangre del cuello, tres golpes juntos:**
***cpp**
```
***`// 1. \_\_restrict: el kernel YA valida overlap, así que el compilador puede asumir no-alias`***
***`polydim\_status\_t polydim\_apply\_rodrigues\_geodesic\_f64(...) \{`**
`    ***...`**
`    ***double\* \_\_restrict y = params-\>y;`**
`    ***double\* \_\_restrict y\_comp = params-\>y\_comp;`**
`    ***const double\* \_\_restrict u\_raw = params-\>u;`**
`    ***const double\* \_\_restrict v\_raw = params-\>v;`**
***`// 2. El branch 'y\_comp ? y\_comp\[i\] : 0.0' dentro del loop del Pass 1:`***
***`//    partir en DOS kernels (con/sin compensador). El loop sin comp se vectoriza entero.`***
***`// 3. Fast-path contractual: si params-\>assume\_unit\_norm (nuevo flag), saltarse norm2\_u/`***
***`//    norm2\_v/dot\_uv y leer c\_u/c\_v directos: ahorra 3 de 5 acumulaciones por elemento.`***
```
***Y medir con `perf stat` / VTune antes/después. Un claim de "50% menos tráfico" con 2 GB/s efectivos no sobrevive a un revisor SOTA — el tráfico está bien, el cómputo escalar es el problema.**
## ***HUESO 15 — `normalize()` de Triton se destruye a escala: reducción cuadrática (VERIFICADO C)**
***`pass2` lanza `n\_partials` programas, cada uno cargando todos los parciales. En numel=1e8 cada programa carga 128 KB (SRAM de un SM en T4: 64 KB) → spill a local memory, 3.2 GB de carga redundante. En 1e9: 256 GB redundantes. Colapsa.**
***FIX Triton — reducción jerárquica:**
***Python**
```
`    ***def normalize(self, x: torch.Tensor, stream=None) -\> torch.Tensor:`**
`        ***ctx = torch.cuda.stream(stream) if stream else contextlib.nullcontext()`**
`        ***with ctx:`**
`            ***numel = x.numel()`**
`            ***if numel == 0: return x`**
`            ***out = torch.empty\_like(x)`**
`            ***BLOCK = 4096`**
`            ***partials = torch.empty((numel + BLOCK - 1) // BLOCK,`**
`                                   ***dtype=torch.float32, device=x.device)`**
`            ***\_fused\_norm\_kernel\_pass1\[((numel + BLOCK - 1) // BLOCK,)\](`**
`                ***x, partials, numel=numel, BLOCK\_SIZE=BLOCK)`**
`            ***\# Segundo nivel: UN solo programa reduce los parciales (son pocos: \<= 2^20)`***
`            ***total = torch.empty(1, dtype=torch.float32, device=x.device)`**
`            ***n = partials.numel()`**
`            ***\_reduce\_partials\[(1,)\](partials, total, n,`**
`                                   ***BLOCK\_SIZE=triton.next\_power\_of\_2(min(n, 8192)))`**
`            ***\# Tercer nivel: normalizar reutilizando pass2 pero con total pre-reducido`***
`            ***\_fused\_norm\_kernel\_apply\[((numel + BLOCK - 1) // BLOCK,)\](`**
`                ***x, out, total, numel=numel, BLOCK\_SIZE=BLOCK)`**
`            ***return out`**
```
***La regla de oro que se violó: un kernel nunca debe cargar más de un bloque SRAM por programa en su fase de reducción global. FlashAttention respeta eso; este `pass2` no.**
## ***HUESO 16 — `catch\_unwind` en Rust es teatro si compilan con `panic = "abort"` (ALTO)**
***`catch\_unwind` solo funciona con `panic = "unwind"`. En release muchos perfiles FFI usan `panic = "abort"` por binario más chico — y entonces el guard de Rust aborta el proceso entero en vez de devolver `ErrPanicCaught`. Silicio industrial: el peor fallo es el que no se puede capturar.**
***FIX Cargo.toml (obligatorio, verificable):**
***toml**
```
***`\[profile.release\]`**
***`panic = "unwind"          *\# REQUERIDO por polydim\_rust\_guard: catch\_unwind es contrato FFI`***
***`lto = true`**
***`codegen-units = 1`**
***`opt-level = 3`**
```
***Y test de contrato: un test FFI que dispare un pánico deliberado (vía puntero nulo forzado en entorno controlado) y verifique que el proceso sobrevive con rc=-9. Sin ese test, no sabés si el guard existe.**
## ***HUESO 17 — Truncación en 32-bit del guard Rust (MEDIO)**
***rust**
```
***`if len == 0 || len \> ((1u64 \<\< 32)) \{ ... \}`**
***`let slice = unsafe \{ slice::from\_raw\_parts(tensor\_ptr, len as usize) \};`**
```
***`len as usize` en un target de 32 bits trunca `2^32` a `0` — y el chequeo permite `len == 2^32`. Undefined behavior de FFI silencioso en ARMv7/Windows-32.**
***FIX Rust:**
***rust**
```
***`const MAX\_LEN: u64 = 1 \<\< 32;`**
***`if len == 0 || len \> MAX\_LEN \{ return PolydimStatus::ErrInvalidDimension as i32; \}`**
***`let len\_usize = match usize::try\_from(len) \{`**
`    ***Ok(v) =\> v,`**
`    ***Err(\_) =\> return PolydimStatus::ErrInvalidDimension as i32,  *// truncacion imposible ya`***
***`\};`**
***`let slice = unsafe \{ slice::from\_raw\_parts(tensor\_ptr, len\_usize) \};`**
```
***Aplica a las dos funciones exportadas (`verify\_unit\_norm`, `verify\_ycomp\_budget`).**
## ***HUESO 18 — Mensaje de error engañoso en el guard Rust ante overflow (MEDIO-BAJO)**
***rust**
```
***`let sq = val \* val;   *// val = 1e200 (finite) -\> sq = inf`***
```
***Un vector malformado con |val| grande da `sq = inf`, la suma se va a inf, y el veredicto es `ErrNormInvariantViolated` cuando lo correcto es `ErrNanInfDetected`. En un sistema donde cada código dispara un camino de recuperación distinto, esto manda al operador por la rama equivocada.**
***FIX Rust:**
***rust**
```
***`let sq = val \* val;`**
***`if !sq.is\_finite() \{`**
`    ***return PolydimStatus::ErrNanInfDetected as i32;`**
***`\}`**
```
## ***HUESO 19 — FFI Python acepta arrays que el kernel interpreta mal (ALTO)**
***`rotate\_geodesic` y `verify\_norm` no validan dtype ni contigüidad. Un caller que pase `float32`, una vista Fortran-order o un slice estridado (`y\[::2\]`) produce resultados silenciosamente equivocados — el puntero base apunta a datos que el kernel recorre como si fueran contiguos float64.**
***FIX monolito:**
***Python**
```
***`def \_as\_validated\_f64(self, arr: np.ndarray, name: str) -\> np.ndarray:`**
`    ***if not isinstance(arr, np.ndarray):`**
`        ***raise TypeError(f"\{name\}: se esperaba np.ndarray")`**
`    ***if arr.dtype != np.float64:`**
`        ***raise TypeError(f"\{name\}: dtype \{arr.dtype\} != float64 (FFI silencioso)")`**
`    ***if not arr.flags\['C\_CONTIGUOUS'\]:`**
`        ***arr = np.ascontiguousarray(arr)`**
`    ***if arr.ndim != 1:`**
`        ***raise ValueError(f"\{name\}: se esperaba vector 1-D")`**
`    ***return arr`**
***`def rotate\_geodesic(self, y, y\_comp, u, v, theta, num\_threads=0):`**
`    ***y  = self.\_as\_validated\_f64(y, "y")`**
`    ***u  = self.\_as\_validated\_f64(u, "u")`**
`    ***v  = self.\_as\_validated\_f64(v, "v")`**
`    ***if y\_comp is not None:`**
`        ***y\_comp = self.\_as\_validated\_f64(y\_comp, "y\_comp")`**
`    ***...`**
```
***Un solo array mal pasado en producción vale más que todos los bugs de carrera.**
## ***HUESO 20 — `DualPCGSolver` no distingue convergencia de agotamiento (MEDIO)**
***`solve()` retorna solo `Alpha`. Si agotó `max\_iter` sin converger, el caller lo usa igual — coeficientes subóptimos consumidos como si fueran la solución. Y el `scaled\_ridge` heurístico (escalar α por la media de ‖x\_i‖²) cambia el operador según los datos sin declararlo.**
***FIX:**
***Python**
```
***`from dataclasses import dataclass`**
***`@dataclass`**
***`class PCGResult:`**
`    ***alpha: np.ndarray`**
`    ***converged: bool`**
`    ***iterations: int`**
`    ***residual\_rel: float`**
***`def solve(self, X, Y) -\> PCGResult:`**
`    ***...`**
`    ***for iteration in range(self.max\_iter):`**
`        ***...`**
`        ***if np.linalg.norm(r) / norm\_b \< self.tol:`**
`            ***return PCGResult(x, True, iteration + 1, np.linalg.norm(r)/norm\_b)`**
`    ***return PCGResult(x, False, self.max\_iter, np.linalg.norm(r)/norm\_b)`**
```
***Y eliminar el `scaled\_ridge` mágico o documentarlo como parte del contrato del operador (`ridge\_alpha` efectivo = `ridge\_alpha · max(1, mean‖x\_i‖²)`), con test que lo fije.**
## ***HUESO 21 — El "PMTP Zero-Copy" no existe en código (ALTO de entrega)**
***`polydim\_pmtp\_swarm\_v753.py` y el benchmark "Cerebras" lo que hacen es `raw\_vec.ctypes.data` — leer un puntero en el mismo proceso. Eso no es IPC: no hay `mmap`, no hay `SharedMemory`, no hay segundo proceso, no hay ciclo de vida del slab. El claim "\>20,000x" mide un no-evento.**
***FIX — PMTP real (misma máquina, multi-proceso):**
***Python**
```
***`import multiprocessing.shared\_memory as shm`**
***`import struct`**
***`class PMTPSlab:`**
`    ***"""Slab compartido con handoff de handles de 16 bytes (no de tensores)."""`**
`    ***def \_\_init\_\_(self, name: str, n\_bytes: int):`**
`        ***self.sl = shm.SharedMemory(name=name, create=True, size=n\_bytes + 4096)`**
`        ***self.meta = self.sl.buf                          *\# cabecera: refcount + shape`***
`        ***self.data\_offset = 4096`**
`    ***def deposit(self, arr: np.ndarray) -\> bytes:`**
`        ***"""Devuelve un handle opaco para pasar por socket/queue (16 bytes)."""`**
`        ***if arr.nbytes \> self.sl.size - self.data\_offset:`**
`            ***raise ValueError("slab lleno")`**
`        ***off = self.data\_offset`**
`        ***np.copyto(np.ndarray(arr.shape, arr.dtype, buffer=self.sl.buf\[off:off+arr.nbytes\]), arr)`**
`        ***handle = struct.pack('\<QQ', off, arr.nbytes)     *\# (offset, bytes)`***
`        ***return handle`**
`    ***def withdraw(self, handle: bytes, shape, dtype) -\> np.ndarray:`**
`        ***off, n = struct.unpack('\<QQ', handle)`**
`        ***return np.ndarray(shape, dtype, buffer=self.sl.buf\[off:off+n\])`**
```
***Y el benchmark honesto mide: depositar en proceso A, pasar handle por `multiprocessing.Queue`, leer en proceso B — con `perf\_counter` en ambos lados. 0.003 ms inventados fuera; latencia real medida adentro.**
## ***HUESO 22 — `DualStreamQueue`: doble submit y CUDA eager (MEDIO)**
***Python**
```
***`def submit\_cpu(self, func, ...):`**
`    ***self.cpu\_thread = threading.Thread(...)   *\# segundo submit\_cpu pisa el primero: result perdido`***
```
***Y `torch.cuda.Stream()` en `\_\_init\_\_` revienta en host sin GPU aunque solo uses el CPU.**
***FIX:**
***Python**
```
***`class DualStreamQueue:`**
`    ***def \_\_init\_\_(self, device: str = "cuda"):`**
`        ***self.\_device = device`**
`        ***self.\_gpu\_stream = None          *\# lazy`***
`        ***self.\_cpu\_pending = False`**
`    ***@property`**
`    ***def gpu\_stream(self):`**
`        ***if self.\_gpu\_stream is None:`**
`            ***if not torch.cuda.is\_available():`**
`                ***raise RuntimeError("gpu\_stream requerido pero no hay CUDA")`**
`            ***self.\_gpu\_stream = torch.cuda.Stream()`**
`        ***return self.\_gpu\_stream`**
`    ***def submit\_cpu(self, func, \*a, \*\*k):`**
`        ***if self.\_cpu\_pending:`**
`            ***raise RuntimeError("submit\_cpu doble sin synchronize()")`**
`        ***self.\_cpu\_pending = True`**
`        ***...`**
`    ***def synchronize(self):`**
`        ***self.\_cpu\_pending = False`**
`        ***...`**
```
## ***HUESO 23 — Build flags: el pragma de contracción no hace nada (MEDIO, verificado contra el código)**
***cpp**
```
***`\#elif defined(\_\_GNUC\_\_) || defined(\_\_clang\_\_)`**
`  ***\#pragma STDC FP\_CONTRACT OFF`**
```
***GCC y Clang ignoran esta pragma (warning `unknown pragma` o silencio) — la contracción FMA se controla con `-ffp-contract=off` en la línea de compilación. Con FMA activo, `(sum - t) + val` puede contraerse y romper la compensación exacta de Neumaier: el error dejado de ser el modelado.**
***FIX — CMakeLists / flags documentados:**
***cmake**
```
***`\# GCC / Clang`***
***`target\_compile\_options(polydim\_kernel PRIVATE -O3 -march=native -ffp-contract=off -fno-math-errno)`**
***`\# PROHIBIDO: -ffast-math / -Ofast (reordenan y asumen asociatividad: mata Neumaier/Kahan)`***
***`\# MSVC`***
***`\# /O2 /fp:precise /openmp — nunca /fp:fast`***
```
***Y un test canario: sumar 1e8 términos con y sin los flags; con FMA mal configurado el drift saltará de ~1e-16 a ~1e-8.**
## ***HUESO 24 — Cerebras benchmark: sin semilla, irreproducible (BAJO, un línea)**
***Python**
```
***`W = np.random.randn(D, D)          *\# RNG global sin seed`***
```
***Dos corridas, dos "speedups" distintos. El log de silicio sí usa `default\_rng(42)` — el benchmark de marketing no.**
***FIX:**
***Python**
```
***`rng = np.random.default\_rng(42)`**
***`W = rng.standard\_normal((D, D), dtype=np.float32)`**
```
## ***HUESO 25 — Códigos muertos que prometen protección (BAJO, deuda)**
- ***Python define `ERR\_SEQLOCK\_RACE = -8` — ningún API nativo lo devuelve jamás. El lector de seqlock gira en `PAUSE()` sin límite: un writer pegado deja al lector en bucle infinito. FIX: contador de reintentos → `ERR\_SEQLOCK\_RACE` tras N vueltas, o documentar que el spin es infinito por diseño.**
- ***`polydim\_zero\_alloc\_f64` paraleliza con OpenMP lo que `std::memset` hace mejor por debajo de ~L3: FIX — `if (bytes \< (1\<\<22)) \{ std::memset(tensor, 0, bytes); \} else \{ /\* omp \*/ \}`.**
## ***HUESO 26 — Test de invariante que falta: round-trip (regalo, no bug)**
***Nada verifica que rotar θ y luego −θ devuelva y al punto de partida a ~1e-15. Es el test que atrapa errores de signo y de fórmula en un solo golpe, más fuerte que mirar la norma:**
***Python**
```
***`def test\_roundtrip(engine, D=1\_000\_000, theta=0.12345):`**
`    ***rng = np.random.default\_rng(42)`**
`    ***u = rng.standard\_normal(D); u /= np.linalg.norm(u)`**
`    ***v = rng.standard\_normal(D); v -= np.dot(v, u)\*u; v /= np.linalg.norm(v)`**
`    ***y0 = rng.standard\_normal(D); y0 /= np.linalg.norm(y0)`**
`    ***y\_fw = y0.copy(); yc = np.zeros(D)`**
`    ***assert engine.rotate\_geodesic(y\_fw, yc, u, v, +theta) == 0`**
`    ***y\_fw += yc`**
`    ***y\_bw = y\_fw.copy(); yc2 = np.zeros(D)`**
`    ***assert engine.rotate\_geodesic(y\_bw, yc2, u, v, -theta) == 0`**
`    ***y\_bw += yc2`**
`    ***err = np.max(np.abs(y\_bw - y0))`**
`    ***assert err \< 1e-12, f"roundtrip roto: \{err:.2e\}"`**
```
***Nota: aplica la corrección del Hueso 9 (chequear `rc` y resetear y\_comp entre llamadas) o el test mide basura.**
## ***Estado del cerco**
***Cerrados con fix pegable: 1, 2, 3, 5, 6, 7, 8 (parcial), 9, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26. Bloqueados sin archivos: Hueso 4 (dirty flag — falta `polydim\_kernel.h`), Hueso 6 (tabla canónica — falta el header para los códigos C++ reales), Hueso 16 (falta `Cargo.toml` para confirmar el perfil), Hueso 10 (decisión de integridad: medir o etiquetar como proyección).**
***Para el ciclo 3 — si me pasás `polydim\_kernel.h` y `Cargo.toml`, cierro 4, 6 y 16 con certeza absoluta en lugar de contra el vacío. Y si querés, el siguiente ciclo profundiza en: (a) modelo de memoria ARM64 del seqlock contra el perfil de reordering real, (b) análisis de error a priori del merge por bloques vs por elementos en el Pass 1, (c) diseño del bench estadístico con IC del 95% para los claims de speedup. Sin esos dos archivos, todo lo que diga de ellos sería alucinación — y esa no es la consigna.**
***confirmas que no son alucinaciones? luego si a todas las opciones que me puedas dar. una detrás de otra en bucle hasta el limite de tus entregas o no encontrar mas errores. el  propósito es darle cierre  a los problema sota no encontrados. continua evaluando problemas y soluciones en bucles cada vez mas profundamente. Hay mucho sota. no solo evalúa con tus conocimientos y sesgos. busca errores mas allá de tu programación básica, dame soluciones. se un bulldog que ataca al problema pero ayuda al dueño. se un redteam que ataca el problema pero respeta y cuida el que les da el trabajo. /goal busca todo problema, encuentra soluciones dame la mejor continua con el siguiente error. muestras los códigos en pantalla, nunca por adjuntos. /goal profundiza ciclos necesarios para pasar a industria \#\#atención\#\# evalúa las respuestas para no dar alucinaciones. Nuestro debe ser "matemáticamente SOTA en papel" a ser industrialmente inquebrantable en silicio real**
***Edit**
***Copy**
***Share**
***Used 5 tools, Addressing HUESO non‑isometry, OpenMP duplication, and performance optimizations**
***Write Cycle 3 Add Benchmark Harness Context-Handle API Reiterate Blocked Items**
***Ciclo 3. Verifico numéricamente los hallazgos nuevos antes de escribirlos — el más importante: el envelope de producción (¿cuántas rotaciones aguanta el guard Rust antes de rechazar estados legítimos?):**
***Optimize Numpy Loop Reduce Dimensions Iterations and Vectorize Operations**
***Failed to execute Python code**
***Thinking complete**
***El bucle con D=1e6 en numpy puro excedió el tiempo. Reduzco escala (D=100k, el fenómeno es independiente de D) y optimizo:**
***Verify angle error Neumaier equivalence then generate CI harness**
***Execute Python code**
***Thinking complete**
***Corrección mía primero (anti-alucinación en serio): en el ciclo 2, Hueso 11 advertí que el margen 10x "se comería bajo acumulación". La prueba F recién corrida lo refuta: con el par compensado `(y, y\_comp)` el drift satura en 1 ulp (2.22e-16) y no crece en 300 rotaciones — Neumaier absorbe todo; el budget de `y\_comp` tiene margen \>10⁸x. Retiro la preocupación: el pipeline compensado es estable, eso es lo SOTA. La advertencia real es otra y más fina (Hueso 27 abajo). Ahora verifico los dos hallazgos nuevos del ciclo 3:**
***Correcting Angle Error Calculation and Demonstrating Anti-Hallucination Discipli…**
***Execute Python code**
***Thinking complete**
***Prueba H tiene un bug mío en el medidor (atan2 con signo cruzado — devolvió `−θ` y reporté `|−θ−θ|=2θ=1.0`). Lo corrijo y agrego la prueba del Hueso 27 (folding) antes de escribir:**
***Rerun J with orthonormal u v to compare folding vs pair**
***Execute Python code**
***Thinking complete**
***plain**
***Prueba J quedó contaminada (reutilicé `u`,`v` casi colineales del probe H — demostró otra cosa: la corrupción de base silenciosa acumula drift de norma, 3.5e-8 a las 199 rotaciones sin ningún error). La repito limpia para el folding:**
***Addressing HUESO non‑isometry, OpenMP duplication, and performance optimizations**
***Execute Python code**
***Thinking complete**
***Ciclo 3 cerrado con verificación completa. Otra retracción honesta: el "folding hazard" que iba a declarar como Hueso 27 es refutado por la medición — 300 rotaciones sin compensador y el drift sigue en 1 ulp (2.22e-16). La rotación por reconstrucción trigonométrica es autoestabilizante en norma; no es una potencia de matriz. Lo que sí crece con rotaciones repetidas es la corrupción de base del Hueso 1 — ahora con segunda evidencia. Estado del ciclo:**
***Table**
| **Prueba** | **Resultado** | **Consecuencia** |
| - | - | - |
| F (drift con par, 300 rot) | Saturado en 1 ulp | Retiro preocupación H11 ✔ |
| H corregida (angulo efectivo) | Error **1.7e-1 rad** en banda 1e-6° con `n2vo=5.6e-16 \> 1e-30` → **silencio total** | Hueso 1 confirmado 2x |
| J contaminada→limpia (folding) | Flat 1 ulp ambos escenarios | Retiro "folding rompe contrato" ✔ |
| K (θ=0) | Identidad exacta (0.0) | Early-out seguro |
| I (Neumaier ternario) | 0 mismatches / 1e6, mismo error | Hueso 14 verificado |
| **J contaminada (regalo)** | Con base corrupta: drift de norma **3.5e-8 @ 199 rot, sin error** | La corrupción de base es la única fuente de deriva encontrada |
## ***HUESO 27 (reformulado con datos) — La banda de corrupción silenciosa es la única fuente de deriva real**
***Medición conjunta de las pruebas H y J-contaminada: con `n2vo = 5.6e-16` (pasa el guard `1e-30`), la base `(û, v̂)` se desvía 3.8e-3, el ángulo efectivo se desvía 0.17 radianes, y bajo rotación repetida la norma deriva 3.5e-8 acumulados — ningún código de error en ningún lado. La corrección del Hueso 1 (umbral relativo `1e-12·‖v‖²`) rechaza `n2vo=5.6e-16` correctamente. Este es el hueso que cierra el ciclo numérico: sin él, el sistema es silenciosamente no-isométrico exactamente en el régimen que el guard debería proteger.**
## ***HUESO 28 — Landmine de deployment Windows: doble runtime OpenMP (VERIFICADO como riesgo conocido, test de confirmación incluido)**
***El DLL C++ usa OpenMP (vcomp140 si MSVC, libomp si LLVM/Clang). NumPy con MKL carga libiomp5md.dll; PyTorch carga libomp (LLVM). Windows no versionea estas DLL por ruta — el loader toma la primera que encuentra. Tres runtimes OpenMP en un proceso = corrupción de estado interno, deadlocks esporádicos, o el clásico `OMP: Error \#15: Initializing libiomp5md.dll, but found libiomp5md.dll already initialized` (mitigación burda: `KMP\_DUPLICATE\_LIB\_OK=TRUE`, que solo silencia el aborto, no la corrupción).**
***Verificación en el host del usuario (5 minutos):**
***Python**
```
***`import ctypes, os`**
***`\# Despues de cargar numpy + tu DLL:`***
***`for mod in ("libiomp5md.dll", "libomp.dll", "vcomp140.dll"):`**
`    ***h = ctypes.windll.kernel32.GetModuleHandleW(mod)`**
`    ***if h:`**
`        ***buf = ctypes.create\_unicode\_buffer(260)`**
`        ***ctypes.windll.psapi.GetModuleFileNameExW(ctypes.windll.kernel32.GetCurrentProcess(), h, buf, 260)`**
`        ***print(f"\{mod\}: \{buf.value\}")   *\# si libiomp5 aparece DOS veces desde paths distintos -\> bomba`***
```
***FIX según diagnóstico:**
- ***Si hay colisión: compilar el kernel con MSVC (vcomp140 no colisiona con libiomp5 por nombre distinto — pero sí comparten el planificador... en la práctica vcomp+libiomp5 coexisten mal también).**
- ***Solución robusta: eliminar OpenMP del kernel y usar `std::thread` con tu propio pool persistente (el kernel ya tiene estructura de two-pass; el pool queda ~50 líneas) → cero dependencias de runtime, cero colisiones, control determinista del pinning (necesario para el Hueso 29):**
***cpp**
```
***`// Pool mínimo persistente (sketch): workers con barrier por fase, sin OpenMP`***
***`class PolydimThreadPool \{`**
`    ***std::vector\<std::thread\> workers;`**
`    ***std::atomic\<uint64\_t\> epoch\{0\};`**
`    ***std::function\<void(int)\> job;              *// fase actual`***
`    ***std::atomic\<int\> pending\{0\};`**
`    ***std::condition\_variable cv; std::mutex m;`**
***`public:`**
`    ***explicit PolydimThreadPool(int n) \{`**
`        ***for (int t = 0; t \< n; ++t)`**
`            ***workers.emplace\_back(\[this, t\] \{`**
`                ***uint64\_t seen = 0;`**
`                ***for (;;) \{`**
`                    ***\{ std::unique\_lock\<std::mutex\> lk(m);`**
`                      ***cv.wait(lk, \[&\]\{ return epoch.load() != seen; \}); \}`**
`                    ***seen = epoch.load();`**
`                    ***job(t);                    *// ojo: job debe ser estable antes de bump`***
`                    ***if (--pending == 0) \{ std::lock\_guard\<std::mutex\> lk(m); cv\_done.notify\_all(); \}`**
`                ***\}`**
`            ***\});`**
`    ***\}`**
`    ***void run(std::function\<void(int)\> j, int nthreads) \{`**
`        ***job = std::move(j);`**
`        ***pending = nthreads;`**
`        ***epoch.fetch\_add(1);`**
`        ***cv.notify\_all();`**
`        ***\{ std::unique\_lock\<std::mutex\> lk(m); cv\_done.wait(lk, \[&\]\{ return pending == 0; \}); \}`**
`    ***\}`**
***`\};`**
```
***(Simplificación para pantalla; la versión industrial necesita shutdown, excepciones, y publicación segura de `job` — fence de secuencia igual que el seqlock que ya tenés.)**
## ***HUESO 29 — El "benchmark" actual no puede respaldar un claim SOTA (MEDIO de método)**
***El log muestra D=1,000 más lento que D=5,000 (1.85 ms vs 0.09 ms) — eso es ruido de primera llamada, no física. Un claim industrial necesita: warmup, mediana sobre ≥30 repeticiones, dispersión, pinning, y intervalo de confianza del speedup (razón de medianas con bootstrap). Harness de reemplazo:**
***Python**
```
***`import time, numpy as np, statistics`**
***`from multiprocessing import cpu\_count`**
***`def bench(fn, iters=50, warmup=5, pin=True):`**
`    ***for \_ in range(warmup): fn()`**
`    ***ts = \[\]`**
`    ***for \_ in range(iters):`**
`        ***t0 = time.perf\_counter\_ns()`**
`        ***fn()`**
`        ***ts.append(time.perf\_counter\_ns() - t0)`**
`    ***ts = np.array(ts) / 1e6  *\# ms`***
`    ***med = np.median(ts)`**
`    ***\# IC95% de la mediana por bootstrap`***
`    ***rng = np.random.default\_rng(42)`**
`    ***boots = \[np.median(rng.choice(ts, size=len(ts))) for \_ in range(10\_000)\]`**
`    ***lo, hi = np.percentile(boots, \[2.5, 97.5\])`**
`    ***return dict(median\_ms=med, ci95=(lo, hi), mad=np.median(np.abs(ts - med)),`**
`                ***p99=np.percentile(ts, 99), min=ts.min())`**
***`def speedup\_ci(t\_base, t\_new, iters=10\_000):`**
`    ***"""IC95% de la razon de medianas, bootstrap pareado."""`**
`    ***rng = np.random.default\_rng(7)`**
`    ***b = np.array(\[np.median(rng.choice(t\_base, len(t\_base))) for \_ in range(iters)\])`**
`    ***n = np.array(\[np.median(rng.choice(t\_new,  len(t\_new)))  for \_ in range(iters)\])`**
`    ***r = b / n`**
`    ***return np.median(r), np.percentile(r, \[2.5, 97.5\])`**
```
***Y en Windows, pinning real:**
***Python**
```
***`import ctypes`**
***`def pin\_current\_core(core: int):`**
`    ***mask = 1 \<\< core`**
`    ***ctypes.windll.kernel32.SetThreadAffinityMask(ctypes.windll.kernel32.GetCurrentThread(), mask)`**
```
***Regla de publicación: ningún speedup se reporta sin `IC95%` que excluya 1.0. Los números hardcodeados de la tabla Cerebras violan esto dos veces (fabricados + sin IC).**
## ***HUESO 30 — API de contexto: cachear la base ortonormal (ALTO de performance, la alternativa correcta al fast-path)**
***Cinco acumulaciones compensadas por elemento (Hueso 14) existen porque cada llamada re-ortogonaliza u,v. Si el swarm rota sobre el mismo plano millones de veces (caso de uso real: handoffs iterativos entre los mismos dos agentes), lo SOTA es factorizar la base una vez:**
***cpp**
```
***`// Nuevo handle opaco en el header (VERSIONADO -\> rompe ABI: POLYDIM\_ABI\_V2)`***
***`typedef struct polydim\_plane\_context polydim\_plane\_context\_t;`**
***`POLYDIM\_API polydim\_status\_t polydim\_plane\_context\_create(`**
`    ***const double\* u, const double\* v, uint64\_t D,`**
`    ***polydim\_plane\_context\_t\*\* out\_ctx);`**
***`POLYDIM\_API polydim\_status\_t polydim\_plane\_context\_apply(`**
`    ***polydim\_plane\_context\_t\* ctx,`**
`    ***double\* y, double\* y\_comp,   *// opcional`***
`    ***double theta, int num\_threads);`**
***`POLYDIM\_API void polydim\_plane\_context\_destroy(polydim\_plane\_context\_t\* ctx);`**
```
***Implementación: en `create` se hace el Pass 1 completo una vez (con la corrección del Hueso 1) y se guardan `û, v̂` en buffers propios alineados a 64B. En `apply` quedan 2 acumulaciones por elemento en vez de 5 (solo `dot\_yu`, `dot\_yv`), y el Pass 2 lee la base ya ortonormal — sin re-normalizar. Reducción de cómputo escalar ~60% en el loop caliente, y la base queda congelada y validada (incluye el guard relativo del Hueso 1 en `create`, que devuelve `ERR\_COLLINEAR\_VECTORS` en construcción, no en caliente).**
***Costo: +2 vectores de memoria por contexto (16D bytes). El FFI Python expone `PlaneContext` con `\_\_enter\_\_/\_\_exit\_\_`.**
## ***HUESO 31 — El guard Rust es serial: a D=1e7 la auditoría cuesta lo mismo que la rotación (MEDIO)**
***`verify\_unit\_norm\_invariant\_f64` es un loop escalar single-thread O(N). A D=10⁷: lee 80 MB + ~6 flops/elemento escalares ≈ 20–60 ms, contra ~300–350 ms de rotación (extrapolando el log). Es decir, la verificación consume un 10–20% del presupuesto de cómputo del sistema y crece lineal con D igual que el kernel. Para "industrialmente inquebrantable" es aceptable (auditar todo, siempre), pero hay que hacerlo deliberado:**
***toml**
```
***`\# Cargo.toml`***
***`\[dependencies\]`**
***`rayon = "1.10"   *\# paralelizacion determinista del guard`***
```
***rust**
```
***`use rayon::prelude::\*;`**
***`// dentro de verify\_unit\_norm\_invariant\_f64, reemplazar el loop serial por:`***
***`let (sum, c) = slice`**
`    ***.par\_chunks(1 \<\< 16)                       *// bloques de 65536: sin false sharing`***
`    ***.map(|chunk| \{`**
`        ***let (mut s, mut cc) = (0.0f64, 0.0f64);`**
`        ***for &val in chunk \{`**
`            ***if !val.is\_finite() \{ return None; \}          *// propagar NaN/Inf`***
`            ***let sq = val \* val;`**
`            ***if !sq.is\_finite() \{ return None; \}           *// Hueso 18`***
`            ***let t = s + sq;`**
`            ***cc += if s.abs() \>= sq.abs() \{ (s - t) + sq \} else \{ (sq - t) + s \};`**
`            ***s = t;`**
`        ***\}`**
`        ***Some((s, cc))`**
`    ***\})`**
`    ***.collect::\<Option\<Vec\<(f64, f64)\>\>\>()     *// None si NaN/Inf en cualquier bloque`***
`    ***.ok\_or(PolydimStatus::ErrNanInfDetected as i32)?`**
`    ***.iter()`**
`    ***.fold((0.0f64, 0.0f64), |(mut S, mut C), &(s, cc)| \{`**
`        ***let v = s + cc;                            *// merge 2-niveles, probado en Prueba D`***
`        ***let t = S + v;`**
`        ***C += if S.abs() \>= v.abs() \{ (S - t) + v \} else \{ (v - t) + S \};`**
`        ***(t, C)`**
`    ***\});`**
***`let final\_norm\_sq = sum + c;`**
```
***Determinismo: `par\_chunks` con reducción por orden de índice preserva reproducibilidad (merge por posición, no por orden de terminación — usar `collect` + fold secuencial como arriba, no `reduce`, que no garantiza orden). Esto mantiene el bit-exactness run-a-run que el guard audita.**
## ***HUESO 32 — Early-out θ=0 y umbral de no-op (BAJO, verificado en Prueba K)**
***`θ=0` produce `coeff\_p = -2·sin²(0) = 0`, `coeff\_j = sin(0) = 0` → `delta = 0` → con compensador, `neumaier\_add(y, yc, 0)` deja el par exactamente igual (Prueba K: `max|y'−y| = 0.0`). El kernel hace los dos passes igual: es un no-op que cuesta 2·O(D). FIX:**
***cpp**
```
`    ***if (theta == 0.0) return POLYDIM\_SUCCESS;   *// identidad exacta, verificada`***
```
***Y considerar el caso de uso inverso: si `|theta| \< 1e-8`, `coeff\_j ≈ theta` con error relativo θ²/6 \< 1e-17 — bajo el piso de precisión: documentar que el primer orden es exacto en ese régimen y que no hay nada que ganar con un early-out aproximado (el costo está en los passes, no en los coeficientes).**
## ***Cierre del ciclo 3 — estado real del sistema**
***Verificado sano (con prueba, no con confianza): fórmula Rodrigues (3.5e-18 vs referencia), versine en θ extremos, merge Neumaier 2-niveles (2.3e-10), Neumaier ternario equivalente, par compensado estable 300 rot, folding estable 300 rot, θ=0 identidad exacta, catch de `n2vo` negativo por el guard actual.**
***Confirmados y con fix pegable: Huesos 1 (umbral relativo), 2 (scan NaN), 3 (overlap y/yc), 13 (fp32→fp64 en Triton), 14 (rama Neumaier + restrict + split), 15 (reducción jerárquica Triton), 16 (panic=unwind), 17 (try\_from), 18 (sq no finito), 19 (validación FFI), 20 (PCGResult), 21 (PMTP real), 22 (lazy stream), 23 (flags de build), 27 (banda de silencio — la única deriva real), 28 (pool propio vs OpenMP), 29 (harness estadístico), 30 (contexto de plano), 31 (rayon determinista), 32 (early-out θ=0).**
***Bloqueados (sin alucinar): Hueso 4 y 6 (cierro con `polydim\_kernel.h` en mano), Hueso 16-parcial (confirmar `Cargo.toml`), Hueso 10 (decisión de integridad: medir la tabla en hardware real o etiquetarla "proyección teórica no medida" — no hay tercera opción honesta).**
***Lo que queda para el ciclo 4 (en profundidad creciente, no repetición): (a) modelo de memoria ARM64 del seqlock con análisis de reordenamiento instrucción por instrucción, (b) diseño del pool de threads con prueba de ausencia de data races (prueba de que `job` se publica con el mismo patrón de secuencia que el seqlock), (c) harness de stress: rotaciones aleatorias con verificación de isometría ‖y'‖=‖y‖ para vectores NO unitarios (el invariante real del operador, más fuerte que la norma 1) — esto atrapa lo que la norma-1 no ve. Pasame el header y el Cargo.toml y los tres caen con certeza absoluta.**
