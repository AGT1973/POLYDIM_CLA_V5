# **CICLO 1 — BLOQUEADORES INDUSTRIALES CONFIRMADOS**
## **Error 1 — El Seqlock no es Multi-Writer seguro**
Código V753:
```
**`void polydim\_seqlock\_write\_begin(polydim\_seqlock\_header\_t\* lock) \{`**
`    **...`**
`    **atomic\_seq-\>fetch\_add(1, std::memory\_order\_acq\_rel);`**
**`\}`**
```
Eso no adquiere la escritura.
Secuencia real:
```
**`seq = 0`**
**`Writer A: fetch\_add(1) -\> 1   // impar`**
**`Writer B: fetch\_add(1) -\> 2   // PAR`**
**`Reader:`**
`    **load() -\> 2`**
`    **2 es par`**
`    **acepta snapshot`**
```
Pero A y B todavía están escribiendo.
Lo reproduje literalmente. Resultado:
```
**`seq after two begin=2`**
**`reader\_start=2`**
**`valid=1`**
```
Es decir: el lector declara válido exactamente el estado que el protocolo pretendía marcar como “writer in progress”.
Esto no es una interpretación. Es un fallo reproducido.
### **Corrección**
Un Multi-Writer Seqlock necesita serializar a los escritores. El **`begin`** debe hacer adquisición CAS de **`even -\> odd`**, no **`fetch\_add`**.
Una forma mínima:
```
**`bool acquire\_writer(std::atomic\<uint64\_t\>& seq) noexcept \{`**
`    **uint64\_t expected = seq.load(std::memory\_order\_acquire);`**
`    **for (;;) \{`**
`        **if (expected & 1ULL) \{`**
`            **POLYDIM\_PAUSE();`**
`            **expected = seq.load(std::memory\_order\_acquire);`**
`            **continue;`**
`        **\}`**
`        **if (seq.compare\_exchange\_weak(`**
`                **expected,`**
`                **expected + 1ULL,`**
`                **std::memory\_order\_acquire,`**
`                **std::memory\_order\_relaxed)) \{`**
`            **return true;`**
`        **\}`**
`    **\}`**
**`\}`**
```
Pero eso todavía deja una cuestión arquitectónica: si quieres verdadero multi-writer con ownership, recomiendo un **`writer\_lock`** separado y la secuencia únicamente como validación de lectores. Eso simplifica muchísimo la prueba formal.
# **Error 2 — El uso de `reinterpret\_cast\<std::atomic\<uint64\_t\>\*\>` es formalmente incorrecto**
V753 hace esto:
```
**`auto\* atomic\_seq =`**
`    **reinterpret\_cast\<std::atomic\<uint64\_t\>\*\>(`**
`        **const\_cast\<uint64\_t\*\>(&lock-\>sequence));`**
```
El warning real del compilador fue:
```
**`warning: dereferencing type-punned pointer might break strict-aliasing rules`**
```
No fue una advertencia inventada por mí: GCC la produjo al compilar este código.
La solución estándar moderna para un **`uint64\_t`** existente es **`std::atomic\_ref\<uint64\_t\>`**, C++20, no convertir el objeto en otro tipo mediante **`reinterpret\_cast`**. **`std::atomic\_ref`** está específicamente diseñado para aplicar operaciones atómicas sobre un objeto existente. 
Ejemplo:
```
**`uint64\_t& seq\_storage = lock-\>sequence;`**
**`std::atomic\_ref\<uint64\_t\> seq(seq\_storage);`**
**`uint64\_t expected = seq.load(std::memory\_order\_acquire);`**
```
Pero atención: **`atomic\_ref`** exige que durante su vida las accesos al objeto sean coherentes con ese mecanismo. 
Por tanto, no basta con cambiar una línea: hay que definir una política única de acceso al **`sequence`**.
# **Error 3 — El Seqlock no protege por sí mismo los datos del payload frente al modelo de memoria C++**
Este es todavía más profundo.
Un patrón:
```
**`reader:`**
`    **seq1 = load()`**
`    **leer struct`**
`    **seq2 = load()`**
```
no convierte mágicamente las lecturas/escrituras ordinarias del **`struct`** en accesos libres de data race.
En C++, dos accesos conflictivos concurrentes sin sincronización apropiada constituyen data race y el comportamiento es indefinido. 
Por tanto:
```
**`uint64\_t sequence;`**
**`Payload payload;`**
```
con:
```
**`writer -\> payload.x = ...`**
**`reader -\> payload.x`**
```
no queda formalmente arreglado sólo porque **`sequence`** sea atómico.
### **Solución industrial**
Tienes tres caminos válidos:
```
**`A) writer lock + snapshot`**
**`B) doble buffer/RCU + publicación atómica`**
**`C) payload compuesto por objetos atómicos`**
```
Para un tensor grande, C es normalmente demasiado caro.
Para POLYDIM elegiría:
```
**`writer`**
`    ↓`
**`escribe buffer privado`**
`    ↓`
**`release publish`**
`    ↓`
**`reader acquire`**
`    ↓`
**`lee snapshot inmutable`**
```
Eso evita pelearte con el modelo de memoria por cada elemento.
# **Error 4 — `force\_recover()` puede liberar un writer que todavía está vivo**
V753:
```
**`if (current & 1ULL) \{`**
`    **atomic\_seq-\>store(current + 3, std::memory\_order\_release);`**
**`\}`**
```
Eso supone:
```
**`impar = writer muerto`**
```
pero también puede significar:
```
**`impar = writer vivo`**
```
Caso:
```
**`Writer A:`**
`    **begin -\> seq=1`**
`    **empieza a modificar payload`**
**`Watchdog:`**
`    **force\_recover()`**
`    **seq=4`**
**`Writer A:`**
`    **termina`**
`    **write\_end()`**
`    **seq=5`**
```
Ahora el sistema queda en estado impar otra vez.
Mucho peor: un lector pudo haber aceptado **`seq=4`** mientras A todavía estaba escribiendo.
### **Solución**
Eliminar recuperación ciega.
La recuperación necesita identidad/lease:
```
**`sequence`**
**`writer\_owner`**
**`heartbeat/deadline`**
**`generation`**
```
y sólo el propietario o un mecanismo externo verificable puede ser revocado.
Para una primera implementación industrial:
```
**`// NO hacer recuperación automática.`**
**`return POLYDIM\_ERR\_RECOVERY\_REQUIRES\_OWNER;`**
```
Más vale una escritura bloqueada que publicar memoria potencialmente corrupta.
# **Error 5 — Entrada NaN/Inf: el kernel devuelve SUCCESS**
Esto sí lo probé.
V753 sólo verifica:
```
**`if (!std::isfinite(theta))`**
`    **return POLYDIM\_ERR\_NAN\_INF\_DETECTED;`**
```
pero no verifica **`u`**, **`v`**, **`y`** ni **`y\_comp`**.
Le pasé:
```
**`double u\[2\] = \{NAN, 0\};`**
```
El resultado reproducido fue:
```
**`nan rc=0`**
**`y=(nan,nan)`**
**`finite=0,0`**
```
Es decir:
```
**`rc == SUCCESS`**
**`output == NaN`**
```
Esto es un bloqueador industrial.
### **Corrección mínima**
Durante el primer pass:
```
**`bool finite\_ok = true;`**
**`\#pragma omp parallel`**
**`\{`**
`    **bool local\_ok = true;`**
`    **\#pragma omp for schedule(static)`**
`    **for (...) \{`**
`        **const double u\_i = u\_raw\[i\];`**
`        **const double v\_i = v\_raw\[i\];`**
`        **const double y\_i = y\[i\];`**
`        **const double c\_i = y\_comp ? y\_comp\[i\] : 0.0;`**
`        **if (!std::isfinite(u\_i) ||`**
`            **!std::isfinite(v\_i) ||`**
`            **!std::isfinite(y\_i) ||`**
`            **!std::isfinite(c\_i)) \{`**
`            **local\_ok = false;`**
`            **continue;`**
`        **\}`**
`        **...`**
`    **\}`**
`    **\#pragma omp critical`**
`    **finite\_ok &= local\_ok;`**
**`\}`**
**`if (!finite\_ok)`**
`    **return POLYDIM\_ERR\_NAN\_INF\_DETECTED;`**
```
Mejor aún: usar un **`std::atomic\<bool\>`** para el flag.
# **Error 6 — `y\_comp` puede aliasar `y`**
V753 comprueba:
```
**`y vs u`**
**`y vs v`**
**`y\_comp vs u`**
**`y\_comp vs v`**
```
pero NO:
```
**`y vs y\_comp`**
```
Lo probé:
```
**`y\_comp == y`**
```
Resultado:
```
**`alias rc=0`**
**`y=(0.99000833055605153,0.19966683329365631)`**
**`norm=1.0099422453229179`**
```
Una rotación que debería mantener norma 1 terminó en:
```
**`1.0099422453`**
```
El fallo no está en Rodrigues: está en el alias.
### **Solución**
Añadir:
```
**`if (y\_comp &&`**
`    **check\_overlap(y, bytes, y\_comp, bytes)) \{`**
`    **return POLYDIM\_ERR\_MEMORY\_OVERLAP;`**
**`\}`**
```
Y en Python hacer también la comprobación:
```
**`if y\_comp is not None and np.shares\_memory(y, y\_comp):`**
`    **raise ValueError("y and y\_comp overlap")`**
```
# **Error 7 — `polydim\_check\_alignment(..., 0)` puede tumbar el proceso**
V753:
```
**`return (reinterpret\_cast\<uintptr\_t\>(ptr) % alignment) == 0;`**
```
Con:
```
**`alignment = 0`**
```
hay división/módulo por cero.
Lo ejecuté en un proceso aislado.
Resultado:
```
**`Floating point exception`**
**`exit=136`**
```
No es una teoría.
### **Corrección**
```
**`if (!ptr)`**
`    **return POLYDIM\_ERR\_NULL\_POINTER;`**
**`if (alignment == 0 ||`**
`    **(alignment & (alignment - 1)) != 0) \{`**
`    **return POLYDIM\_ERR\_INVALID\_ALIGNMENT;`**
**`\}`**
```
Y agregar **`POLYDIM\_ERR\_INVALID\_ALIGNMENT`** al ABI.
# **Error 8 — La FFI Python permite pasar memoria que C++ interpreta con el tipo equivocado**
El wrapper hace:
```
**`D = y.shape\[0\]`**
**`y\_ptr = y.ctypes.data\_as(`**
`    **ctypes.POINTER(ctypes.c\_double)`**
**`)`**
```
No verifica:
```
**`dtype == float64`**
**`ndim == 1`**
**`C-contiguous`**
**`writeable`**
**`shape igual en y/y\_comp/u/v`**
```
Esto es peligrosísimo.
Por ejemplo:
```
**`y = np.ones(100, dtype=np.float32)`**
```
C++ recibe:
```
**`double\*`**
**`D = 100`**
```
y lee aproximadamente:
```
**`800 bytes`**
```
cuando el array tiene:
```
**`400 bytes`**
```
Eso es lectura fuera de límites.
También:
```
**`y = base\[::2\]`**
```
es una vista no contigua. **`ctypes.data`** apunta al primer elemento, mientras C++ hace:
```
**`y\[i\]`**
```
como si fuese contiguo.
### **Solución**
El contrato FFI debe ser explícito:
```
**`def require\_f64\_vector(`**
`    **x: np.ndarray,`**
`    **name: str,`**
`    **\*,`**
`    **writable: bool = False,`**
**`) -\> np.ndarray:`**
`    **if not isinstance(x, np.ndarray):`**
`        **raise TypeError(f"\{name\}: expected numpy.ndarray")`**
`    **if x.ndim != 1:`**
`        **raise ValueError(f"\{name\}: expected 1-D")`**
`    **if x.dtype != np.float64:`**
`        **raise TypeError(f"\{name\}: expected float64")`**
`    **if not x.flags.c\_contiguous:`**
`        **raise ValueError(f"\{name\}: expected C-contiguous")`**
`    **if writable and not x.flags.writeable:`**
`        **raise ValueError(f"\{name\}: expected writable")`**
`    **if not np.all(np.isfinite(x)):`**
`        **raise ValueError(f"\{name\}: NaN/Inf")`**
`    **return x`**
```
Y después:
```
**`y = require\_f64\_vector(y, "y", writable=True)`**
**`u = require\_f64\_vector(u, "u")`**
**`v = require\_f64\_vector(v, "v")`**
**`if y\_comp is not None:`**
`    **y\_comp = require\_f64\_vector(`**
`        **y\_comp,`**
`        **"y\_comp",`**
`        **writable=True,`**
`    **)`**
**`if y\_comp is not None:`**
`    **if np.shares\_memory(y, y\_comp):`**
`        **raise ValueError("y and y\_comp overlap")`**
```
Esto debe suceder ANTES de **`ctypes`**.
# **Error 9 — El header que necesita el C++ no está dentro del ZIP**
El ZIP V753 contiene 10 archivos.
No contiene:
```
**`polydim\_kernel.h`**
```
El C++ hace:
```
**`\#include "polydim\_kernel.h"`**
```
Por tanto, el paquete entregado no es reproducible por sí mismo.
Yo pude hacer un build únicamente creando temporalmente un header de prueba para comprobar la implementación.
Eso significa:
```
**`C++ source audit       = posible`**
**`C++ release reproducible = NO`**
**`ABI exacto certificado   = NO`**
```
Esto es un bloqueador de release, no un detalle administrativo.
### **Solución**
El artefacto final debe contener como mínimo:
```
**`include/`**
`    **polydim\_kernel.h`**
**`cpp/`**
`    **kernel\_cpp\_v754.cpp`**
**`rust/`**
`    **kernel\_rust\_v754.rs`**
**`python/`**
`    **polydim\_core.py`**
`    **...`**
**`triton/`**
`    **...`**
**`tests/`**
`    **...`**
**`build/`**
`    **CMakeLists.txt`**
`    **Cargo.toml`**
```
y una matriz explícita de:
```
**`compiler`**
**`OS`**
**`architecture`**
**`C++ standard`**
**`OpenMP version/runtime`**
**`CUDA`**
**`Triton`**
**`Python`**
**`NumPy`**
**`PyTorch`**
**`Rust`**
```
# **CICLO 2 — MATEMÁTICA / NUMERICS**
## **Error 10 — El test de colinealidad no es scale-invariant**
V753:
```
**`double norm2\_v\_ortho =`**
`    **norm2\_v - (dot\_uv \* dot\_uv / norm2\_u);`**
**`if (norm2\_v\_ortho \<= 1e-30)`**
`    **return POLYDIM\_ERR\_COLLINEAR\_VECTORS;`**
```
Ese umbral es absoluto.
Problema:
```
**`u = 1e-200 \* e1`**
**`v = 1e-200 \* e2`**
```
son perfectamente ortogonales matemáticamente.
Pero:
```
**`u² ≈ 1e-400`**
```
underflowea a cero en binary64.
Resultado:
```
**`ERR\_ZERO\_VECTOR`**
```
aunque el vector no sea cero matemáticamente.
La operación debería ser invariante bajo:
```
**`u -\> αu`**
**`v -\> βv`**
```
y actualmente no lo es.
### **Solución**
Normalizar con una norma robusta tipo **`LASSQ`**, no:
```
**`sum += x\*x;`**
```
Una implementación básica:
```
**`struct ScaledNorm \{`**
`    **double scale = 0.0;`**
`    **double ssq = 1.0;`**
**`\};`**
**`inline void lassq\_add(`**
`    **ScaledNorm& n,`**
`    **double x`**
**`) noexcept \{`**
`    **const double ax = std::abs(x);`**
`    **if (ax == 0.0)`**
`        **return;`**
`    **if (n.scale \< ax) \{`**
`        **const double r = n.scale / ax;`**
`        **n.ssq = 1.0 + n.ssq \* r \* r;`**
`        **n.scale = ax;`**
`    **\} else \{`**
`        **const double r = ax / n.scale;`**
`        **n.ssq += r \* r;`**
`    **\}`**
**`\}`**
**`inline double lassq\_norm(`**
`    **const ScaledNorm& n`**
**`) noexcept \{`**
`    **return n.scale \* std::sqrt(n.ssq);`**
**`\}`**
```
Y el test de degeneración debe ser relativo:
```
**`const double norm\_v\_ortho =`**
`    **stable\_orthogonal\_norm(...);`**
**`if (norm\_v\_ortho \<=`**
`    **collinearity\_tol \* norm\_v) \{`**
`    **return POLYDIM\_ERR\_COLLINEAR\_VECTORS;`**
**`\}`**
```
# **Error 11 — `dot\_uv \* dot\_uv` puede desbordarse aunque el resultado geométrico sea perfectamente válido**
V753:
```
**`dot\_uv \* dot\_uv / norm2\_u`**
```
Con vectores de gran magnitud:
```
**`dot\_uv ~ 1e200`**
```
el cuadrado es:
```
**`1e400 -\> Inf`**
```
aunque:
```
**`dot\_uv² / norm2\_u`**
```
pudiera tener un valor representable.
Esto es un problema clásico de escala.
La solución no es sólo Neumaier.
Necesitas calcular en escala normalizada:
```
**`u = su \* û`**
**`v = sv \* ṽ`**
```
y hacer la geometría sobre:
```
**`û, ṽ`**
```
con **`su`**, **`sv`** separados.
# **Error 12 — Neumaier no hace seguro el producto**
Esta línea:
```
**`u\_i \* u\_i`**
```
se evalúa antes de:
```
**`neumaier\_add(...)`**
```
Por tanto:
```
**`Neumaier protege la suma.`**
**`No protege el producto.`**
```
Esto es importante.
Lo mismo:
```
**`u\_i \* v\_i`**
**`y\_i \* u\_i`**
**`y\_i \* v\_i`**
```
puede producir:
```
**`Inf`**
**`NaN`**
```
antes de que el acumulador pueda hacer absolutamente nada.
El nombre “Neumaier hardened” no resuelve esta capa.
# **Error 13 — La afirmación de “second-order bound” del Rust no está justificada por el algoritmo completo**
El Rust dice:
```
**`|s\_hat - s| \<= c \* N \* eps^2 + 10 \* eps`**
```
y usa:
```
**`100 \* N \* eps^2 + 10 \* eps`**
```
El problema conceptual es que el código calcula:
```
**`let sq = val \* val;`**
```
La multiplicación ya tiene error de redondeo de primer orden.
Neumaier reduce fuertemente el error de la suma, pero no convierte todos los errores de las multiplicaciones en un término de segundo orden.
La parte segura para vender como industrial sería algo del estilo:
```
**`input normalization error`**
**`+`**
**`multiplication rounding`**
**`+`**
**`summation error`**
**`+`**
**`underflow/overflow behavior`**
```
separados.
No afirmaría públicamente:
```
`“**2nd-order bound proven”`**
```
con el código actual.
# **Error 14 — El budget de `y\_comp` no depende del número de actualizaciones**
Rust:
```
**`50.0 \* len \* EPSILON\_MACH\_F64`**
```
Pero **`y\_comp`** es acumulativo.
Si hacemos:
```
**`rotación 1`**
**`rotación 2`**
**`...`**
**`rotación M`**
```
el error puede depender de:
```
**`M`**
```
y de la magnitud/condicionamiento de cada actualización.
El presupuesto actual sólo depende de:
```
**`D`**
```
No existe en la fórmula:
```
**`n\_updates`**
```
Eso no es una cota teórica suficiente para afirmar seguridad indefinida.
De hecho probé 100.000 rotaciones y la compensación se mantuvo razonablemente pequeña en los casos ensayados, pero eso prueba comportamiento empírico de esos casos, no el teorema universal.
# **CICLO 3 — PCG**
Aquí encontramos uno de los errores más importantes porque cambia el problema matemático.
## **Error 15 — El solver no resuelve exactamente el sistema que documenta**
Documentación:
```
**`(X Xᵀ + ridge \* I) Alpha = Y`**
```
Código:
```
**`scaled\_ridge = (`**
`    **self.ridge\_alpha \*`**
`    **max(1.0, float(np.mean(row\_norms\_sq)))`**
**`)`**
```
Por tanto realmente resuelve:
```
**`(X Xᵀ + scaled\_ridge I) α = Y`**
```
No:
```
**`(X Xᵀ + ridge\_alpha I) α = Y`**
```
Lo probé.
Para un ejemplo:
```
**`ridge solicitado = 0.1`**
**`ridge usado      = 0.2933443594515552`**
```
Residual respecto del sistema documentado:
```
**`0.311155...`**
```
Residual respecto al sistema realmente resuelto:
```
**`5.7e-15`**
```
Esto es demostrable.
### **Solución**
Decidir una de dos:
### **Opción industrial A**
**`ridge\_alpha`** significa literalmente ridge:
```
**`ridge = float(self.ridge\_alpha)`**
```
y:
```
**`A = XXT + ridge I`**
```
### **Opción B**
Si quieres escalamiento:
```
**`ridge\_scale\_factor`**
```
y documentarlo explícitamente.
No puedes cambiar la ecuación silenciosamente.
# **Error 16 — `max\_iter=0` y `max\_iter\<0` devuelven una solución cero como si todo estuviera bien**
Lo probé:
```
**`DualPCGSolver(max\_iter=0).solve(...)`**
```
resultado:
```
**`finite=True`**
**`norm=0`**
```
No hay excepción.
Para un solver industrial:
```
**`max\_iter = 0`**
```
debe ser configuración inválida.
### **Solución**
```
**`if max\_iter \< 1:`**
`    **raise ValueError("max\_iter must be \>= 1")`**
**`if not np.isfinite(tol) or not (0.0 \< tol \< 1.0):`**
`    **raise ValueError("tol must be finite and 0 \< tol \< 1")`**
**`if not np.isfinite(ridge\_alpha) or ridge\_alpha \<= 0.0:`**
`    **raise ValueError("ridge\_alpha must be finite and \> 0")`**
```
# **Error 17 — Ridge negativo no se rechaza**
Probado:
```
**`ridge\_alpha=-0.1`**
```
y el solver:
```
**`no explota`**
**`devuelve valores`**
```
pero PCG requiere SPD para que el argumento matemático sea válido.
Un ridge negativo puede destruir la positividad definida.
Esto debe ser rechazo explícito.
# **Error 18 — `pAp \<= 1e-30` es un criterio numérico incorrectamente escalado**
V753:
```
**`if pAp \<= 1e-30:`**
`    **break`**
```
Un operador perfectamente SPD puede tener:
```
**`pAp = 1e-40`**
```
por escala.
Eso no significa:
```
`“**numerical limit”`**
```
Es una comparación absoluta donde debe existir un criterio relativo.
Más apropiado:
```
**`scale = np.linalg.norm(p) \* np.linalg.norm(Ap)`**
**`if not np.isfinite(pAp) or pAp \<= 0.0:`**
`    **raise np.linalg.LinAlgError("PCG breakdown")`**
**`if pAp \<= np.finfo(np.float64).eps \* max(scale, 1.0):`**
`    **raise np.linalg.LinAlgError("PCG numerical breakdown")`**
```
Y no **`break`** silencioso.
# **Error 19 — El solver puede declararse convergente por residual recursivo sin recomputar el residual verdadero**
V753:
```
**`r -= alpha \* Ap`**
**`if np.linalg.norm(r) / norm\_b \< tol:`**
`    **break`**
```
Eso es habitual en PCG, pero en ingeniería numérica de alta exigencia hay que vigilar el drift del residual.
Solución:
```
**`cada K iteraciones:`**
`    **r\_true = b - A(x)`**
`    **comprobar ||r\_true||`**
```
y al final:
```
**`true\_residual = np.linalg.norm(b - matvec(x))`**
```
La salida debe quedar acompañada de:
```
**`converged`**
**`iterations`**
**`relative\_residual`**
**`true\_residual`**
**`breakdown`**
```
No simplemente un ndarray.
# **CICLO 4 — TRITON / GPU**
## **Error 20 — La reducción de norm en `pass2` escala mal**
Código:
```
**`BLOCK2 = triton.next\_power\_of\_2(`**
`    **max(n\_partials, BLOCK)`**
**`)`**
```
y:
```
**`\_fused\_norm\_kernel\_pass2\[(n\_partials,)\](...)`**
```
Cada uno de los **`n\_partials`** programas vuelve a cargar TODOS los **`n\_partials`**.
Conceptualmente:
```
**`program 0 -\> reduce all partials`**
**`program 1 -\> reduce all partials`**
**`program 2 -\> reduce all partials`**
**`...`**
**`program N -\> reduce all partials`**
```
Eso no es una reducción jerárquica.
Es aproximadamente:
```
**`O(n\_partials²)`**
```
en el segundo paso.
Ejemplo:
```
**`numel ≈ 100,000,000`**
**`BLOCK ≈ 4096`**
**`n\_partials ≈ 24,414`**
**`BLOCK2 = 32,768`**
```
y tienes miles de programas repitiendo la misma reducción global.
### **Solución**
Hacer:
```
**`pass1:`**
`    **x -\> partials`**
**`pass2:`**
`    **partials -\> 1 scalar`**
**`pass3:`**
`    **x \* inv\_norm -\> output`**
```
o usar una reducción jerárquica:
```
**`partials`**
`   ↓`
**`partial groups`**
`   ↓`
**`one final scalar`**
```
No repetir la misma reducción para cada bloque de salida.
# **Error 21 — El acumulador de norm está fijado a float32**
Código:
```
**`partials = torch.empty(`**
`    **n\_partials,`**
`    **dtype=torch.float32,`**
**`)`**
```
Por lo tanto, si:
```
**`x = float64`**
```
la suma intermedia termina almacenándose en float32.
Eso contradice cualquier pretensión de precisión FP64 SOTA.
Triton permite especificar explícitamente el dtype de reducción; su documentación incluso señala que esto sirve para prevenir overflow. 
### **Solución**
Seleccionar acumulador:
```
**`if x.dtype == torch.float64:`**
`    **accum\_dtype = tl.float64`**
**`elif x.dtype in (torch.float16, torch.bfloat16, torch.float32):`**
`    **accum\_dtype = tl.float32`**
**`else:`**
`    **raise TypeError(...)`**
```
y almacenar partials en el dtype correcto.
# **Error 22 — `v` no tiene stride**
Kernel:
```
**`tl.load(v\_ptr + offs\_n, ...)`**
```
pero **`v`** llega como Tensor arbitrario.
En cambio **`X`** sí recibe:
```
**`X.stride(0)`**
**`X.stride(1)`**
```
Si:
```
**`v = original\[::2\]`**
```
entonces:
```
**`v.shape == (N,)`**
```
pero no es contiguo.
El kernel lo interpreta como:
```
**`stride = 1`**
```
aunque el stride real sea:
```
**`2`**
```
Por tanto puede leer datos equivocados.
La forma segura es:
```
**`v = v.contiguous()`**
```
o pasar:
```
**`stride\_v`**
```
al kernel.
La documentación de Triton deja claro que **`tl.load`** utiliza el puntero que se le construye; el mask solamente controla qué posiciones se cargan. 
# **Error 23 — `assert` no es un contrato industrial**
```
**`assert v.shape == (N,)`**
```
Con Python optimizado:
```
**`python -O`**
```
el **`assert`** desaparece.
Debe ser:
```
**`if v.ndim != 1 or v.shape\[0\] != N:`**
`    **raise ValueError(...)`**
```
Además faltan:
```
**`dtype`**
**`device`**
**`contiguity/stride`**
**`finite`**
**`ridge`**
```
# **CICLO 5 — PMTP / “ZERO-COPY”**
Aquí hay una falsedad técnica particularmente importante.
El benchmark dice:
```
**`ptr = raw\_vec.ctypes.data`**
```
y lo presenta como:
```
**`PMTP Zero-Copy IPC`**
**`Direct Memory Slab`**
```
Eso NO implementa IPC.
Eso simplemente obtiene un entero:
```
**`dirección virtual del proceso actual`**
```
Un puntero:
```
**`0x7f....`**
```
no es un descriptor portable entre procesos.
Con ASLR, otro proceso puede tener otra dirección virtual.
### **Para IPC real necesitas**
```
**`SharedMemory name/handle`**
**`+`**
**`offset`**
**`+`**
**`shape`**
**`+`**
**`dtype`**
```
por CPU.
Para CUDA:
```
**`CUDA IPC handle`**
```
o un mecanismo equivalente.
Por tanto:
```
**`ptr = raw\_vec.ctypes.data`**
```
no demuestra:
```
**`zero-copy IPC`**
```
ni:
```
**`shared memory`**
```
ni:
```
**`PMTP`**
```
Es una simulación de la medición.
# **CICLO 6 — BENCHMARKS QUE NO SON EVIDENCIA DE SILICIO**
## **Error 24 — El “Cerebras benchmark” no ejecuta Cerebras**
El archivo se presenta como:
```
**`Hardware: CPU, NVIDIA T4, Cerebras WSE-3`**
```
pero el código que se ejecuta usa:
```
**`numpy`**
**`time.perf\_counter()`**
```
y luego imprime una tabla:
```
**`CPU 420 ms`**
**`GPU 18.5 ms`**
**`Cerebras 8.2 ms`**
**`...`**
```
Esos valores no proceden de una ejecución de Cerebras dentro del paquete.
Por tanto:
```
**`tabla = claim`**
```
no:
```
**`tabla = measurement`**
```
No la pondría jamás en una evidencia industrial.
# **Error 25 — La comparación “Sin POLYDIM” vs “Con POLYDIM” no es una comparación de la misma operación**
Se compara aproximadamente:
```
**`W @ x`**
```
contra:
```
**`rank-2 Rodrigues`**
```
Eso no es:
```
**`misma operación`**
**`misma precisión`**
**`mismo resultado`**
```
Por eso:
```
`“**289x”`**
```
no puede presentarse como speedup del mismo algoritmo.
Puede presentarse como:
```
**`reducción de complejidad algorítmica bajo un cambio de representación`**
```
que es una afirmación muy diferente.
Eso sí es defendible si se formaliza correctamente.
# **Error 26 — Incluso una de las cifras de memoria del propio texto está mal generalizada**
Para **`D=100000`**, una matriz:
```
**`D × D × float32`**
```
requiere aproximadamente:
```
**`37.25 GiB`**
```
No:
```
**`\> 400 GB`**
```
La estimación de:
```
**`D = 1,000,000`**
```
sí ronda:
```
**`3.64 TiB`**
```
Por tanto el mensaje:
```
`“**D \> 10,000 =\> 400 GB - 4 TB”`**
```
es falso como afirmación general.
# **CICLO 7 — FFI BENCHMARK**
## **Error 27 — El benchmark V753 importa V751**
Archivo:
```
**`polydim\_ffi\_benchmark\_v753.py`**
```
pero contiene:
```
**`sys.path.append(`**
`    **r"E:\\POLYDIM\_EINSOF\\POLYDIM\_V751"`**
**`)`**
```
y:
```
**`from polydim.core import PolydimEngine`**
```
además:
```
**`cpp\_dll = r"...POLYDIM\_V751\\bin\\polydim\_kernel.dll"`**
```
y la cabecera dice:
```
**`POLYDIM V752`**
```
Esto no es V753 end-to-end.
Es una mezcla:
```
**`V751`**
**`V752`**
**`V753`**
```
Eso invalida la certificación de release.
# **Error 28 — El benchmark FFI no comprueba `rc`**
Hace:
```
**`rc = engine.rotate\_geodesic(...)`**
```
pero no:
```
**`if rc != SUCCESS:`**
`    **...`**
```
Un benchmark puede terminar diciendo:
```
**`FPS = X`**
**`Final norm = Y`**
```
después de que el kernel haya devuelto un error.
Eso no sirve como test de aceptación.
# **Error 29 — El benchmark ignora `y\_comp` al validar la norma**
El C++ mantiene:
```
**`y + y\_comp`**
```
como representación efectiva.
Pero el benchmark hace:
```
**`np.linalg.norm(y)`**
```
en vez de:
```
**`np.linalg.norm(y + y\_comp)`**
```
Por tanto mide una cosa diferente a la que usa el algoritmo.
El benchmark de **`raw\_silicon`** sí reconstruye:
```
**`y\_final = y + y\_comp`**
```
pero el otro no.
# **Error 30 — El benchmark de “silicon” sólo demuestra un único trayecto**
El log contiene:
```
**`1,000`**
**`5,000`**
**`10,000`**
**`...`**
**`1,000,000`**
```
una medición por dimensión.
No prueba:
```
**`repetibilidad`**
```
ni:
```
**`p99 latency`**
```
ni:
```
**`variance`**
```
ni:
```
**`cold start`**
```
ni:
```
**`thermal throttling`**
```
ni:
```
**`NUMA`**
```
ni:
```
**`different thread counts`**
```
ni:
```
**`different compilers`**
```
ni:
```
**`different CPUs`**
```
ni:
```
**`ECC/error injection`**
```
ni:
```
**`concurrent readers/writers`**
```
Así que:
```
**`PASS (Rust OK)`**
```
sólo significa que ese escenario pasó.
No:
```
**`industrial verified`**
```
# **Lo más importante: qué está bien**
No quiero caer en el error contrario y destruir trabajo correcto.
La parte matemática central de Rodrigues sí tiene una buena base.
Con:
```
**`û, v̂`**
```
ortonormales y:
```
**`c\_u = y·û`**
**`c\_v = y·v̂`**
```
la transformación:
```
**`delta\_y =`**
`    **(cos(theta)-1) \* (c\_u\*u\_i + c\_v\*v\_i)`**
`    **+ sin(theta) \* (c\_u\*v\_i - c\_v\*u\_i);`**
```
es la forma correcta de una rotación en el plano generado por **`u`** y **`v`**.
Además:
```
**`-2\*sin(theta/2)^2`**
```
es una buena elección numérica para representar:
```
**`cos(theta)-1`**
```
cuando **`theta`** es pequeño, evitando la cancelación directa de:
```
**`cos(theta) - 1`**
```
Eso sí lo conservaría.
# **La corrección de arquitectura que yo haría**
No intentaría parchear veinte cosas independientemente.
Lo llevaría a este contrato:
```
`                ┌────────────────────┐`
**`Python          │ Strict FFI Contract │`**
`                └─────────┬──────────┘`
`                          │`
`                    **validated f64`**
`                          │`
`                          ▼`
`                ┌────────────────────┐`
`                │ **C++ Numeric Kernel │`**
`                │                    │`
`                │ **finite inputs      │`**
`                │ **stable norm         │`**
`                │ **stable projection   │`**
`                │ **overlap safe        │`**
`                │ **no UB               │`**
`                └─────────┬──────────┘`
`                          │`
`                     **result + status`**
`                          │`
`                          ▼`
`                ┌────────────────────┐`
`                │ **Rust Guard         │`**
`                │                    │`
`                │ **finite              │`**
`                │ **norm invariant      │`**
`                │ **actual tolerance    │`**
`                │ **no fake theorem     │`**
`                └────────────────────┘`
```
Y el Seqlock debe quedar separado:
```
**`writer serialization`**
`        **+`**
**`version publication`**
`        **+`**
**`immutable snapshot`**
```
No mezclado con recuperación ciega.
# **Parche prioritario número 1**
Este es el núcleo que cambiaría antes de absolutamente cualquier benchmark.
```
**`struct PolydimWriterLock \{`**
`    **std::atomic\<uint32\_t\> busy\{0\};`**
**`\};`**
**`static inline void writer\_lock(`**
`    **std::atomic\<uint32\_t\>& busy`**
**`) noexcept \{`**
`    **uint32\_t expected = 0;`**
`    **while (!busy.compare\_exchange\_weak(`**
`        **expected,`**
`        **1,`**
`        **std::memory\_order\_acquire,`**
`        **std::memory\_order\_relaxed)) \{`**
`        **expected = 0;`**
`        **POLYDIM\_PAUSE();`**
`    **\}`**
**`\}`**
**`static inline void writer\_unlock(`**
`    **std::atomic\<uint32\_t\>& busy`**
**`) noexcept \{`**
`    **busy.store(0, std::memory\_order\_release);`**
**`\}`**
```
Y la secuencia:
```
**`std::atomic\_ref\<uint64\_t\> seq(lock-\>sequence);`**
**`writer\_lock(lock-\>writer\_busy);`**
**`uint64\_t old = seq.fetch\_add(`**
`    **1,`**
`    **std::memory\_order\_acquire`**
**`);`**
**`// old debe ser par.`**
**`// después de esto:`**
**`// seq = old + 1 -\> impar`**
**`// escribir snapshot`**
**`std::atomic\_thread\_fence(`**
`    **std::memory\_order\_release`**
**`);`**
**`seq.fetch\_add(`**
`    **1,`**
`    **std::memory\_order\_release`**
**`);`**
**`writer\_unlock(lock-\>writer\_busy);`**
```
Pero aquí hay una decisión de diseño importante: el header actual no contiene ese **`writer\_busy`**. Por lo tanto esto exige cambiar el ABI. No voy a fingir que se puede reparar completamente sin tocar el header.
# **Gate de aceptación que pondría ahora**
La V753 no debería pasar a “industrialmente certificada” hasta que sobreviva, como mínimo:
```
**`\[ \] ZIP autocontenido y reproducible`**
**`\[ \] C++ header incluido`**
**`\[ \] ABI única C++/Rust/Python`**
**`\[ \] dtype/shape/stride contract`**
**`\[ \] NaN/Inf rejection`**
**`\[ \] overlap rejection completa`**
**`\[ \] robust norms`**
**`\[ \] scale-invariant collinearity`**
**`\[ \] Multi-Writer real`**
**`\[ \] payload race-free`**
**`\[ \] crash recovery con ownership`**
**`\[ \] PCG ecuación exacta`**
**`\[ \] PCG breakdown detectable`**
**`\[ \] true residual verification`**
**`\[ \] Triton hierarchical reduction`**
**`\[ \] Triton dtype correctness`**
**`\[ \] Triton stride correctness`**
**`\[ \] real shared-memory IPC`**
**`\[ \] GPU benchmark realmente ejecutado`**
**`\[ \] Cerebras benchmark realmente ejecutado`**
**`\[ \] benchmark reproducible`**
**`\[ \] stress/concurrency tests`**
**`\[ \] sanitizers`**
**`\[ \] fuzzing de ABI`**
**`\[ \] property tests matemáticos`**
**`\[ \] endurance test`**
```
Y hay una distinción fundamental:
```
`“**SOTA matemático”`**
`        ≠`
`“**correcto bajo IEEE-754”`**
`        ≠`
`“**correcto bajo C++ memory model”`**
`        ≠`
`“**correcto bajo CUDA”`**
`        ≠`
`“**correcto bajo IPC”`**
`        ≠`
`“**industrial”`**
```
Para llegar a tu objetivo de **“matemáticamente SOTA en papel” → “industrialmente inquebrantable en silicio real”**, esta separación es obligatoria.
## **Veredicto de esta ronda**
No, no eran simples “posibles problemas”.
Los siguientes están **reproducidos o demostrados directamente**:
```
**`1. Seqlock Multi-Writer roto`**
**`2. reinterpret\_cast a atomic con violation de strict-aliasing`**
**`3. NaN/Inf -\> SUCCESS + NaN output`**
**`4. y/y\_comp alias -\> norma incorrecta`**
**`5. alignment=0 -\> crash`**
**`6. FFI acepta float32/no-contiguous como double\*`**
**`7. ridge del PCG no coincide con la ecuación documentada`**
**`8. max\_iter=0 devuelve solución cero silenciosamente`**
**`9. PMTP benchmark no implementa IPC zero-copy`**
**`10. “Cerebras benchmark” no ejecuta Cerebras`**
**`11. V753 contiene componentes V751/V752`**
**`12. paquete C++ incompleto: falta header`**
**`13. reducción Triton de norma repetida N veces`**
**`14. Triton \`v\` no tiene stride`**
```
Los siguientes quedan clasificados como **riesgo técnico muy alto que requiere validación del entorno real**, no como hechos ya reproducidos:
```
**`15. compilabilidad exacta del kernel Triton en el target CUDA`**
**`16. comportamiento cross-platform del OpenMP runtime`**
**`17. ABI exacta respecto del header real ausente`**
**`18. comportamiento Rust real en Windows/MSVC`**
**`19. rendimiento real de GPU/Cerebras`**
```
Esto es importante: **no voy a contabilizar esos cinco como errores confirmados hasta ejecutarlos**.
Y la evidencia externa coincide con los puntos críticos: C++ define data races como comportamiento indefinido, **`atomic\_ref`** existe precisamente para aplicar atomicidad a objetos existentes, Rust exige que los punteros usados con **`from\_raw\_parts`** cumplan completamente las precondiciones de memoria/alineación/tamaño, y Triton permite controlar explícitamente el dtype de reducción. 
La auditoría, por tanto, **no está cerrada todavía**. El siguiente hueso que atacaría es el más peligroso de la capa numérica: **rehacer la ortonormalización de `u,v` para que sea estable frente a overflow, underflow y casi-colinealidad, y demostrarla con propiedades matemáticas y casos adversariales antes de volver a tocar rendimiento**.
ataca lo que queda. se proactiva. pon agentes a trabajar en cada problema diferente
Sí. Y en esta ronda pude separar todavía mejor lo que está demostrado de lo que sólo requiere hardware real.
No voy a “inventar agentes”. Lo que hice fue dividir la auditoría en hilos independientes y ejecutarlos en paralelo: C++/memoria, matemática numérica, Rust/FFI, Triton/CUDA y trazabilidad/benchmarks. Después crucé los resultados para buscar contradicciones.
La conclusión más importante es ésta: **el núcleo geométrico no necesita ser reemplazado**. En régimen normal lo probé contra una referencia independiente en 100 casos aleatorios: error absoluto máximo **`2.22e-16`** y drift de norma máximo **`2.22e-16`**. Los fallos graves están en los bordes y, sobre todo, en los contratos entre componentes.
## **CICLO 8 — ABI Y CONTRATOS**
### **Error 31 — Los códigos de error no son compatibles entre C++, Python y Rust**
En **`polydim\_v753\_monolito.py`** aparecen:
```
**`ERR\_NORM\_INVARIANT\_VIOLATED = -4`**
**`ERR\_ZERO\_VECTOR             = -4`**
**`ERR\_COLLINEAR\_VECTORS       = -5`**
**`ERR\_MEMORY\_OVERLAP          = -6`**
```
Mientras Rust declara:
```
**`ErrNormInvariantViolated = -4,`**
**`ErrZeroVector            = -5,`**
**`ErrCollinearVectors      = -6,`**
**`ErrYcompBudgetExceeded  = -7,`**
```
Eso significa que, por ejemplo, un **`-5`** procedente de Rust significa **`ErrZeroVector`**, mientras que Python lo interpreta como **`ERR\_COLLINEAR\_VECTORS`**.
No es estilística. Es una ruptura ABI lógica.
### **Solución**
Una única definición canónica:
```
**`typedef enum \{`**
`    **POLYDIM\_SUCCESS                  = 0,`**
`    **POLYDIM\_ERR\_NULL\_POINTER         = -1,`**
`    **POLYDIM\_ERR\_INVALID\_DIMENSION    = -2,`**
`    **POLYDIM\_ERR\_NAN\_INF\_DETECTED     = -3,`**
`    **POLYDIM\_ERR\_NORM\_INVARIANT       = -4,`**
`    **POLYDIM\_ERR\_ZERO\_VECTOR          = -5,`**
`    **POLYDIM\_ERR\_COLLINEAR            = -6,`**
`    **POLYDIM\_ERR\_YCOMP\_BUDGET         = -7,`**
`    **POLYDIM\_ERR\_SEQLOCK\_RACE         = -8,`**
`    **POLYDIM\_ERR\_PANIC\_CAUGHT         = -9,`**
`    **POLYDIM\_ERR\_UNALIGNED             = -10,`**
`    **POLYDIM\_ERR\_MEMORY\_OVERLAP        = -11,`**
`    **POLYDIM\_ERR\_INVALID\_ARGUMENT      = -12,`**
`    **POLYDIM\_ERR\_OUT\_OF\_MEMORY         = -13,`**
`    **POLYDIM\_ERR\_NUMERICAL\_BREAKDOWN   = -14,`**
`    **POLYDIM\_ERR\_NOT\_CONVERGED         = -15,`**
`    **POLYDIM\_ERR\_ABI\_MISMATCH          = -16,`**
`    **POLYDIM\_ERR\_INTERNAL              = -17`**
**`\} polydim\_status\_t;`**
```
Python y Rust deben derivarse de ese contrato, no duplicarlo a mano.
### **Error 32 — No existe handshake de ABI**
C++ expone:
```
**`polydim\_get\_version()`**
```
pero **`PolydimEngine`** nunca lo verifica.
Tampoco se verifica:
```
**`sizeof(polydim\_rodrigues\_params\_t)`**
**`alignof(...)`**
**`offset de cada campo`**
**`versión ABI`**
```
Para **`ctypes`**, esto debe ser explícito.
### **Solución**
C++:
```
**`POLYDIM\_API uint32\_t polydim\_abi\_version(void) \{`**
`    **return 0x00010001;`**
**`\}`**
**`POLYDIM\_API size\_t polydim\_sizeof\_rodrigues\_params(void) \{`**
`    **return sizeof(polydim\_rodrigues\_params\_t);`**
**`\}`**
**`POLYDIM\_API size\_t polydim\_offsetof\_rodrigues\_y(void) \{`**
`    **return offsetof(polydim\_rodrigues\_params\_t, y);`**
**`\}`**
```
Python:
```
**`EXPECTED\_ABI = 0x00010001`**
**`abi = cpp\_lib.polydim\_abi\_version()`**
**`if abi != EXPECTED\_ABI:`**
`    **raise RuntimeError(`**
`        **f"ABI mismatch: got \{abi:\#x\}, "`**
`        **f"expected \{EXPECTED\_ABI:\#x\}"`**
`    **)`**
```
Y conviene verificar tamaño:
```
**`native\_size = cpp\_lib.polydim\_sizeof\_rodrigues\_params()`**
**`if native\_size != ctypes.sizeof(PolydimRodriguesParams):`**
`    **raise RuntimeError(`**
`        **"FFI struct layout mismatch"`**
`    **)`**
```
### **Error 33 — El C++ está expuesto como C ABI pero puede lanzar excepciones C++**
Este bloque:
```
**`std::vector\<PaddedAcc\> acc\_u(num\_threads),`**
`                       **acc\_v(num\_threads),`**
`                       **acc\_uv(num\_threads);`**
```
puede lanzar **`std::bad\_alloc`**.
La función es:
```
**`extern "C"`**
```
y no captura excepciones.
En una frontera FFI industrial, una excepción C++ no debe escapar al consumidor Python/Rust.
### **Solución**
```
**`POLYDIM\_API polydim\_status\_t`**
**`polydim\_apply\_rodrigues\_geodesic\_f64(`**
`    **const polydim\_rodrigues\_params\_t\* params`**
**`) noexcept \{`**
`    **try \{`**
`        **return polydim\_apply\_impl(params);`**
`    **\}`**
`    **catch (const std::bad\_alloc&) \{`**
`        **return POLYDIM\_ERR\_OUT\_OF\_MEMORY;`**
`    **\}`**
`    **catch (...) \{`**
`        **return POLYDIM\_ERR\_INTERNAL;`**
`    **\}`**
**`\}`**
```
La implementación real queda fuera de la frontera ABI:
```
**`static polydim\_status\_t`**
**`polydim\_apply\_impl(`**
`    **const polydim\_rodrigues\_params\_t\* params`**
**`) \{`**
`    **...`**
**`\}`**
```
# **CICLO 9 — SIMD/MEMORIA REAL**
### **Error 34 — La API no sabe cuánto mide `u`, `v` ni `y\_comp`**
C++ recibe:
```
**`y`**
**`u`**
**`v`**
**`y\_comp`**
**`D`**
```
pero no recibe:
```
**`len\_u`**
**`len\_v`**
**`len\_y\_comp`**
```
y presupone que todos tienen al menos **`D`**.
Lo reproduje con ASan:
```
**`mismatch\_len -\> stack-buffer-overflow`**
**`READ of size 8`**
**`kernel\_cpp\_v753.cpp:128`**
```
Es un fallo real de memoria.
### **Solución**
La mejor solución es que el ABI reciba longitudes explícitas:
```
**`struct polydim\_rodrigues\_params\_t \{`**
`    **double\* y;`**
`    **double\* y\_comp;`**
`    **const double\* u;`**
`    **const double\* v;`**
`    **uint64\_t y\_len;`**
`    **uint64\_t y\_comp\_len;`**
`    **uint64\_t u\_len;`**
`    **uint64\_t v\_len;`**
`    **double theta;`**
`    **uint64\_t D;`**
`    **int32\_t num\_threads;`**
**`\};`**
```
y:
```
**`if (params-\>y\_len != D ||`**
`    **params-\>u\_len != D ||`**
`    **params-\>v\_len != D ||`**
`    **(params-\>y\_comp &&`**
`     **params-\>y\_comp\_len != D)) \{`**
`    **return POLYDIM\_ERR\_INVALID\_ARGUMENT;`**
**`\}`**
```
### **Error 35 — El C++ no valida NaN/Inf de los vectores**
Prueba real:
```
**`nan\_u=0`**
**`nan\_y=0`**
**`inf\_u=0`**
```
**`0`** significa **`POLYDIM\_SUCCESS`**.
Con vectores enormes:
```
**`huge\_uv=0`**
**`y=(-nan,-nan)`**
```
Es todavía peor:
```
**`finite input`**
**`+`**
**`SUCCESS`**
**`+`**
**`NaN output`**
```
### **Solución mínima**
Durante pass 1:
```
**`bool finite\_ok = true;`**
**`\#pragma omp parallel num\_threads(num\_threads)`**
**`\{`**
`    **bool local\_ok = true;`**
`    **\#pragma omp for schedule(static)`**
`    **for (int64\_t i = 0;`**
`         **i \< static\_cast\<int64\_t\>(D);`**
`         **++i) \{`**
`        **const double u\_i = u\_raw\[i\];`**
`        **const double v\_i = v\_raw\[i\];`**
`        **const double y\_i =`**
`            **y\[i\] + (y\_comp ? y\_comp\[i\] : 0.0);`**
`        **if (!std::isfinite(u\_i) ||`**
`            **!std::isfinite(v\_i) ||`**
`            **!std::isfinite(y\_i)) \{`**
`            **local\_ok = false;`**
`            **continue;`**
`        **\}`**
`        **...`**
`    **\}`**
`    **\#pragma omp critical`**
`    **\{`**
`        **finite\_ok &= local\_ok;`**
`    **\}`**
**`\}`**
**`if (!finite\_ok)`**
`    **return POLYDIM\_ERR\_NAN\_INF\_DETECTED;`**
```
Y, mejor aún, combinarlo con una reducción de flags atómica o por hilo.
### **Error 36 — `y\_comp` tampoco se valida como finito**
Actualmente:
```
**`double y\_i = y\[i\] + y\_comp\[i\];`**
```
Un único:
```
**`y\_comp\[i\] = NaN`**
```
contamina todos los productos acumulados y no existe una detección específica.
Debe incluirse en el contrato.
### **Error 37 — `y` y `y\_comp` pueden apuntar al mismo buffer**
La implementación rechaza:
```
**`y vs u`**
**`y vs v`**
**`y\_comp vs u`**
**`y\_comp vs v`**
```
pero no:
```
**`y vs y\_comp`**
```
Es un alias especial porque ambas variables tienen semánticas distintas.
### **Solución**
```
**`if (y\_comp &&`**
`    **check\_overlap(y, bytes, y\_comp, bytes)) \{`**
`    **return POLYDIM\_ERR\_MEMORY\_OVERLAP;`**
**`\}`**
```
### **Error 38 — `alignment == 0` hace caer el proceso**
El código actual:
```
**`return (reinterpret\_cast\<uintptr\_t\>(ptr)`**
`        **% alignment) == 0;`**
```
Lo ejecuté con **`alignment=0`**.
ASan/UBSan:
```
**`runtime error: division by zero`**
**`FPE`**
```
### **Solución**
```
**`if (!ptr)`**
`    **return POLYDIM\_ERR\_NULL\_POINTER;`**
**`if (alignment == 0)`**
`    **return POLYDIM\_ERR\_INVALID\_ARGUMENT;`**
**`if ((alignment & (alignment - 1)) != 0)`**
`    **return POLYDIM\_ERR\_INVALID\_ARGUMENT;`**
**`return is\_aligned(ptr, alignment)`**
`    **? POLYDIM\_SUCCESS`**
`    **: POLYDIM\_ERR\_UNALIGNED;`**
```
# **CICLO 10 — NUMERICS EXTREMOS**
### **Error 39 — El cuadrado se calcula antes de que Neumaier pueda ayudar**
Esto:
```
**`neumaier\_add(`**
`    **acc\_u\[tid\].sum,`**
`    **acc\_u\[tid\].c,`**
`    **u\_i \* u\_i`**
**`);`**
```
protege la suma.
No protege:
```
**`u\_i \* u\_i`**
```
contra overflow.
Exactamente el mismo problema existe en:
```
**`v\_i \* v\_i`**
**`u\_i \* v\_i`**
**`y\_i \* u\_i`**
**`y\_i \* v\_i`**
```
Neumaier no convierte una multiplicación potencialmente infinita en una multiplicación segura.
### **Error 40 — Normalización de vectores no es scale-safe**
Actualmente:
```
**`norm2\_u = sum(u\_i\*u\_i)`**
**`inv\_norm\_u = 1/sqrt(norm2\_u)`**
```
Con:
```
**`u\_i ≈ 1e200`**
```
los cuadrados pueden producir:
```
**`Inf`**
```
y luego:
```
**`Inf \* 0 -\> NaN`**
```
La solución correcta es una norma escalada tipo **`LASSQ`**.
```
**`struct ScaledSumSq \{`**
`    **double scale = 0.0;`**
`    **double ssq   = 1.0;`**
**`\};`**
**`static inline void lassq\_add(`**
`    **ScaledSumSq& s,`**
`    **double x`**
**`) noexcept \{`**
`    **const double ax = std::abs(x);`**
`    **if (ax == 0.0)`**
`        **return;`**
`    **if (s.scale \< ax) \{`**
`        **const double r = s.scale / ax;`**
`        **s.ssq = 1.0 + s.ssq \* r \* r;`**
`        **s.scale = ax;`**
`    **\} else \{`**
`        **const double r = ax / s.scale;`**
`        **s.ssq += r \* r;`**
`    **\}`**
**`\}`**
**`static inline double lassq\_norm(`**
`    **const ScaledSumSq& s`**
**`) noexcept \{`**
`    **return s.scale \* std::sqrt(s.ssq);`**
**`\}`**
```
Luego:
```
**`double nu = lassq\_norm(norm\_u);`**
**`if (!std::isfinite(nu) || nu == 0.0)`**
`    **return POLYDIM\_ERR\_ZERO\_VECTOR;`**
**`double inv\_nu = 1.0 / nu;`**
```
### **Error 41 — El test de colinealidad es absolutamente escalado**
Actualmente:
```
**`if (norm2\_v\_ortho \<= 1e-30)`**
```
Eso significa que:
```
**`vector geométricamente válido`**
**`+`**
**`escala suficientemente pequeña`**
**`=`**
**`zero/collinear`**
```
El criterio debería estar relacionado con la escala de **`v`** y con una tolerancia angular/condicionamiento.
Por ejemplo:
```
**`const double rel\_tol =`**
`    **128.0 \* std::numeric\_limits\<double\>::epsilon();`**
**`const double ortho\_norm =`**
`    **stable\_orthogonal\_component(...);`**
**`if (ortho\_norm \<= rel\_tol \* norm\_v)`**
`    **return POLYDIM\_ERR\_COLLINEAR;`**
```
El valor exacto debe salir del contrato matemático que quieras garantizar, no de **`1e-30`** arbitrario.
### **Error 42 — `dot\_uv \* dot\_uv` también puede overflowear**
Código:
```
**`dot\_uv \* dot\_uv / norm2\_u`**
```
Si:
```
**`dot\_uv ≈ 1e200`**
```
entonces:
```
**`dot\_uv² -\> 1e400 -\> Inf`**
```
aunque la expresión final podría ser representable.
Esto exige cálculo escalado, no sólo compensación de suma.
# **CICLO 11 — RUST**
### **Error 43 — `user\_tolerance = +Inf` invalida el guard**
Código:
```
**`let tolerance = if user\_tolerance \> 0.0 \{`**
`    **user\_tolerance`**
**`\} else \{`**
`    **compute\_neumaier\_second\_order\_tolerance(len)`**
**`\};`**
```
Con:
```
**`user\_tolerance = f64::INFINITY`**
```
se acepta cualquier valor finito:
```
**`if (final\_norm\_sq - 1.0).abs() \<= INFINITY`**
```
### **Corrección**
```
**`if !user\_tolerance.is\_finite() || user\_tolerance \< 0.0 \{`**
`    **return PolydimStatus::ErrInvalidArgument as i32;`**
**`\}`**
```
Y distinguir:
```
**`0 = usar tolerancia automática`**
**`\>0 = usar tolerancia suministrada`**
```
### **Error 44 — `catch\_unwind` no convierte un puntero inválido en memoria segura**
Rust hace:
```
**`let slice =`**
`    **unsafe \{`**
`        **slice::from\_raw\_parts(`**
`            **tensor\_ptr,`**
`            **len as usize`**
`        **)`**
`    **\};`**
```
**`catch\_unwind`** sólo captura un panic.
No captura:
```
**`UB`**
**`puntero inválido`**
**`longitud inválida`**
**`rango que sale de la asignación`**
**`alineación incorrecta`**
```
La documentación oficial de Rust exige que **`data`** sea no nulo, correctamente alineado y válido para **`len \* size\_of::\<T\>()`**; toda la región debe pertenecer a una única asignación y la longitud total debe respetar **`isize::MAX`**. 
Por tanto el guard Rust **no es una frontera de seguridad de memoria por sí mismo**.
La seguridad debe garantizarse en el contrato FFI antes de entrar al **`unsafe`**.
### **Error 45 — El límite Rust no es portable a arquitecturas de 32 bits**
Actualmente:
```
**`len \> ((1u64 \<\< 32))`**
```
Pero luego:
```
**`len as usize`**
```
y **`from\_raw\_parts`**.
El contrato correcto debería considerar:
```
**`const MAX\_LEN: u64 =`**
`    **(isize::MAX as u64) / std::mem::size\_of::\<f64\>() as u64;`**
```
y además verificar que cabe en **`usize`**.
### **Error 46 — El nombre “second-order bound” es demasiado fuerte**
Actualmente:
```
**`NEUMAIER\_SAFETY\_FACTOR \* N \* eps²`**
```
se presenta como:
```
**`Rigorous 2nd-Order Bound`**
```
Pero las operaciones:
```
**`let sq = val \* val;`**
```
ya introducen redondeo de multiplicación.
La suma compensada puede controlar muy bien el error de acumulación, pero eso no convierte automáticamente todo el cálculo en:
```
**`O(N ε²)`**
```
La afirmación publicable debe separar:
```
**`error de producto`**
**`+`**
**`error de suma compensada`**
**`+`**
**`error de representación`**
**`+`**
**`overflow/underflow`**
```
No mantendría el claim “rigorous second-order” hasta demostrarlo formalmente para todo el algoritmo.
# **CICLO 12 — PCG**
### **Error 47 — El solver acepta configuración inválida**
Lo ejecuté:
```
**`max\_iter=0`**
`    **-\> SUCCESS-like output, zero vector`**
**`max\_iter=-1`**
`    **-\> SUCCESS-like output, zero vector`**
**`ridge=-0.1`**
`    **-\> produces a result`**
**`tol=+inf`**
`    **-\> accepted`**
```
No hay rechazo.
### **Solución**
```
**`if self.max\_iter \< 1:`**
`    **raise ValueError(`**
`        **"max\_iter must be \>= 1"`**
`    **)`**
**`if (`**
`    **not np.isfinite(self.tol)`**
`    **or not (0.0 \< self.tol \< 1.0)`**
**`):`**
`    **raise ValueError(`**
`        **"tol must satisfy 0 \< tol \< 1"`**
`    **)`**
**`if (`**
`    **not np.isfinite(self.ridge\_alpha)`**
`    **or self.ridge\_alpha \<= 0.0`**
**`):`**
`    **raise ValueError(`**
`        **"ridge\_alpha must be finite and \> 0"`**
`    **)`**
```
### **Error 48 — No hay estado de convergencia**
Si PCG llega a:
```
**`for iteration in range(self.max\_iter):`**
```
sin converger, simplemente sale del loop y devuelve **`Alpha`**.
Eso significa:
```
**`NO CONVERGIÓ`**
```
y el API responde:
```
**`aquí tienes un ndarray`**
```
sin ningún indicador.
### **Solución industrial**
```
**`@dataclass`**
**`class PCGResult:`**
`    **alpha: np.ndarray`**
`    **converged: bool`**
`    **iterations: int`**
`    **residual\_norm: float`**
`    **true\_residual\_norm: float`**
```
O, manteniendo compatibilidad:
```
**`return\_alpha\_only=False`**
```
y:
```
**`if not converged:`**
`    **raise np.linalg.LinAlgError(`**
`        **"PCG did not converge"`**
`    **)`**
```
### **Error 49 — `pAp \<= 1e-30` no está escalado**
Esto:
```
**`if pAp \<= 1e-30:`**
`    **break`**
```
confunde:
```
**`problema SPD bien condicionado pero muy pequeño`**
```
con:
```
**`breakdown`**
```
Debe verificarse:
```
**`if not np.isfinite(pAp) or pAp \<= 0.0:`**
`    **raise np.linalg.LinAlgError(`**
`        **"PCG breakdown: p^T A p \<= 0"`**
`    **)`**
```
y cualquier umbral adicional debe ser relativo.
### **Error 50 — No verifica residual verdadero**
El código usa:
```
**`r -= alpha \* Ap`**
**`if np.linalg.norm(r) / norm\_b \< tol:`**
`    **break`**
```
Eso es un residual recursivo.
En una implementación industrial yo haría:
```
**`if iteration % residual\_refresh == 0:`**
`    **r\_true = b - matvec(x)`**
`    **true\_rel = (`**
`        **np.linalg.norm(r\_true)`**
`        **/ max(norm\_b, np.finfo(np.float64).tiny)`**
`    **)`**
`    **if true\_rel \< tol:`**
`        **converged = True`**
`        **break`**
```
y siempre verificaría una última vez.
### **Error 51 — X/Y con NaN/Inf pasan hasta el álgebra**
Lo probé:
```
**`NaN X -\> devuelve NaN`**
**`Inf X -\> devuelve NaN`**
**`NaN Y -\> devuelve NaN`**
```
sin excepción.
Debe haber un gate:
```
**`if not np.isfinite(X\_f64).all():`**
`    **raise ValueError("X contains NaN/Inf")`**
**`if not np.isfinite(Y\_f64).all():`**
`    **raise ValueError("Y contains NaN/Inf")`**
```
### **Error 52 — CPU y GPU resuelven ecuaciones distintas**
Python:
```
**`scaled\_ridge = (`**
`    **self.ridge\_alpha \*`**
`    **max(1.0, float(np.mean(row\_norms\_sq)))`**
**`)`**
```
Triton:
```
**`out = acc + ridge\_alpha \* v`**
```
CPU resuelve:
```
**`X Xᵀ + scaled\_ridge I`**
```
GPU:
```
**`X Xᵀ + ridge\_alpha I`**
```
No son el mismo operador.
Esto significa que una comparación CPU/GPU puede mostrar diferencia aunque ambos estén “correctos” respecto de su propio código.
Hay que centralizar:
```
**`def effective\_ridge(X, ridge\_alpha):`**
`    **...`**
```
y exportar exactamente ese valor al kernel.
# **CICLO 13 — TRITON**
### **Error 53 — La reducción `pass2` hace trabajo cuadrático en número de parciales**
El kernel lanza:
```
**`\_fused\_norm\_kernel\_pass2\[(n\_partials,)\](...)`**
```
pero cada programa carga:
```
**`partials = tl.load(`**
`    **partial\_ptr + offs\_p,`**
`    **...`**
**`)`**
```
sobre **todos** los parciales.
Y:
```
**`BLOCK2 \>= n\_partials`**
```
por diseño.
Por tanto:
```
**`program 0 -\> todos los partials`**
**`program 1 -\> todos los partials`**
**`program 2 -\> todos los partials`**
**`...`**
```
La reducción global se calcula repetidamente.
La complejidad del pass2 es aproximadamente:
```
**`O(n\_partials²)`**
```
en lecturas/reducción, no una reducción lineal.
### **Solución**
El pass2 debe tener:
```
**`grid = (1,)`**
```
y usar un bloque/árbol de reducción apropiado, o una reducción jerárquica:
```
**`pass1:`**
**`X -\> P parciales`**
**`pass2:`**
**`P -\> Q parciales`**
**`pass3:`**
**`Q -\> 1`**
```
No:
```
**`P programas × P lecturas`**
```
### **Error 54 — La normalización fija los parciales en float32**
Código:
```
**`partials = torch.empty(`**
`    **n\_partials,`**
`    **dtype=torch.float32,`**
`    **device=x.device`**
**`)`**
```
Si:
```
**`x = float64`**
```
la reducción termina almacenándose en float32.
Eso destruye la precisión de la ruta FP64.
La API actual de Triton permite especificar el **`dtype`** de **`tl.sum`**, precisamente para controlar la precisión y prevenir overflow. 
### **Solución**
```
**`if x.dtype == torch.float64:`**
`    **accum\_dtype = tl.float64`**
**`elif x.dtype in (torch.float32, torch.float16, torch.bfloat16):`**
`    **accum\_dtype = tl.float32`**
**`else:`**
`    **raise TypeError(...)`**
```
y:
```
**`psq = tl.sum(`**
`    **x \* x,`**
`    **axis=0,`**
`    **dtype=accum\_dtype,`**
**`)`**
```
### **Error 55 — `normalize()` rompe tensores no contiguos**
El kernel hace:
```
**`x\_ptr + offs`**
```
sin stride.
Por tanto:
```
**`x = base\[::2\]`**
```
tiene:
```
**`shape correcto`**
**`dtype correcto`**
**`pero stride != 1`**
```
y el kernel interpreta memoria no contigua como contigua.
### **Solución fácil**
```
**`if not x.is\_contiguous():`**
`    **x = x.contiguous()`**
```
o, para mantener zero-copy:
```
**`stride\_x = x.stride(0)`**
```
y:
```
**`x\_ptr + offs \* stride\_x`**
```
### **Error 56 — `normalize()` convierte silenciosamente casos inválidos en cero**
Actualmente:
```
**`inv\_norm = tl.where(`**
`    **total\_sq \> 1e-24,`**
`    **tl.rsqrt(total\_sq),`**
`    **0.0`**
**`)`**
```
Consecuencia:
```
**`zero vector -\> output zero`**
**`tiny vector -\> output zero`**
**`NaN norm     -\> condition false -\> output zero`**
**`Inf norm     -\> rsqrt(Inf) = 0`**
```
Eso **oculta errores de entrada**.
Para un núcleo industrial:
```
**`invalid input`**
`≠`
**`vector cero como resultado válido`**
```
Hay que devolver estado o lanzar la validación en host.
### **Error 57 — El matvec Triton no es PCG**
La clase se llama:
```
**`TritonPolydimV751`**
```
y el método:
```
**`dual\_pcg\_matvec`**
```
pero sólo calcula:
```
**`w = Xᵀv`**
**`out = Xw + λv`**
```
No ejecuta:
```
**`r`**
**`z`**
**`p`**
**`alpha`**
**`beta`**
**`convergence`**
```
Por tanto:
```
**`matvec != PCG`**
```
Esto es correcto si el objetivo es proveer un operador para un PCG externo.
Pero no debe venderse como “GPU PCG completo”.
# **CICLO 14 — CUDA STREAMS**
Aquí hay un hallazgo importante que no tenía cerrado antes.
**`DualStreamQueue`** hace:
```
**`with torch.cuda.stream(self.gpu\_stream):`**
`    **self.gpu\_result = func(\*args, \*\*kwargs)`**
```
pero nunca hace:
```
**`self.gpu\_stream.wait\_stream(`**
`    **torch.cuda.current\_stream()`**
**`)`**
```
Antes de consumir tensors producidos en el stream actual.
La documentación oficial de PyTorch señala explícitamente que las operaciones en streams diferentes pueden ejecutarse en distinto orden y que hay que establecer las dependencias con **`wait\_stream()`**. 
El patrón documentado es:
```
**`s.wait\_stream(torch.cuda.default\_stream())`**
**`with torch.cuda.stream(s):`**
`    **use\_tensor()`**
```
y luego gestionar la vida del tensor con **`record\_stream()`**. 
### **Solución**
```
**`def submit\_gpu(self, func, \*args, \*\*kwargs):`**
`    **current = torch.cuda.current\_stream(`**
`        **device=self.gpu\_stream.device`**
`    **)`**
`    **self.gpu\_stream.wait\_stream(current)`**
`    **with torch.cuda.stream(self.gpu\_stream):`**
`        **self.gpu\_result = func(\*args, \*\*kwargs)`**
`        **for obj in (\*args, \*kwargs.values()):`**
`            **if isinstance(obj, torch.Tensor):`**
`                **if obj.is\_cuda:`**
`                    **obj.record\_stream(self.gpu\_stream)`**
`        **self.gpu\_event.record(self.gpu\_stream)`**
```
Y al volver al stream consumidor:
```
**`torch.cuda.current\_stream(`**
`    **device=self.gpu\_stream.device`**
**`).wait\_stream(self.gpu\_stream)`**
```
PyTorch documenta directamente **`wait\_stream()`** para esta sincronización explícita. 
### **Error 59 — Excepción antes de `gpu\_event.record()`**
La estructura es:
```
**`self.gpu\_result = func(...)`**
**`self.gpu\_event.record(...)`**
```
Si **`func()`** lanza:
```
**`func() -\> exception`**
**`record() nunca ocurre`**
```
pero **`synchronize()`** hace:
```
**`self.gpu\_event.synchronize()`**
```
No existe estado explícito:
```
**`gpu\_error`**
**`event\_recorded`**
**`submitted`**
```
### **Solución**
```
**`class DualStreamQueue:`**
`    **def \_\_init\_\_(self):`**
`        **if not torch.cuda.is\_available():`**
`            **raise RuntimeError(`**
`                **"CUDA is required"`**
`            **)`**
`        **self.gpu\_stream = torch.cuda.Stream()`**
`        **self.gpu\_event = None`**
`        **self.gpu\_error = None`**
`        **self.gpu\_result = None`**
`    **def submit\_gpu(self, func, \*args, \*\*kwargs):`**
`        **self.gpu\_error = None`**
`        **self.gpu\_result = None`**
`        **self.gpu\_event = None`**
`        **current = torch.cuda.current\_stream()`**
`        **self.gpu\_stream.wait\_stream(current)`**
`        **try:`**
`            **with torch.cuda.stream(self.gpu\_stream):`**
`                **self.gpu\_result = func(`**
`                    **\*args, \*\*kwargs`**
`                **)`**
`                **self.gpu\_event = (`**
`                    **self.gpu\_stream.record\_event()`**
`                **)`**
`        **except Exception as exc:`**
`            **self.gpu\_error = exc`**
`            **raise`**
`    **def synchronize(self):`**
`        **if self.cpu\_thread is not None:`**
`            **self.cpu\_thread.join()`**
`        **if self.cpu\_error:`**
`            **raise self.cpu\_error`**
`        **if self.gpu\_error:`**
`            **raise self.gpu\_error`**
`        **if self.gpu\_event is not None:`**
`            **self.gpu\_event.synchronize()`**
`        **return self.cpu\_result, self.gpu\_result`**
```
# **CICLO 15 — PMTP / IPC**
### **Error 60 — `ctypes.data` no es IPC**
V753 hace:
```
**`ptr = raw\_vec.ctypes.data`**
```
y lo denomina:
```
**`PMTP Zero-Copy IPC`**
```
Pero eso es una dirección virtual del proceso actual.
No es:
```
**`shared memory`**
**`CUDA IPC`**
**`OS handle`**
**`memfd`**
**`named mapping`**
```
Para IPC CPU real necesitas por ejemplo:
```
**`shared memory object`**
**`+`**
**`offset`**
**`+`**
**`length`**
**`+`**
**`dtype`**
**`+`**
**`shape`**
```
Para CUDA:
```
**`CUDA IPC handle`**
```
El **`ptr`** jamás debe cruzar procesos como si fuera un identificador universal.
### **Error 61 — El benchmark inventa 3 microsegundos**
Código:
```
**`t\_pmtp = (`**
`    **time.perf\_counter() - t0`**
**`) \* 1000 + 0.003`**
```
El **`+ 0.003`** no mide hardware.
Es una constante escrita manualmente.
Eso debe desaparecer completamente de cualquier benchmark certificable.
### **Error 62 — El benchmark no hace IPC**
No crea:
```
**`proceso A`**
**`proceso B`**
**`shared memory`**
**`handoff`**
**`deserialización de metadatos`**
**`lectura en B`**
**`verificación de identidad`**
```
Por lo tanto no puede afirmar:
```
**`IPC ZERO-COPY`**
```
Sólo mide:
```
**`obtener una dirección virtual`**
```
# **CICLO 16 — BENCHMARKS**
### **Error 63 — El benchmark raw ignora el `rc`**
Hace:
```
**`rc = lib\_cpp.polydim\_apply\_rodrigues\_geodesic\_f64(...)`**
```
pero nunca:
```
**`if rc != 0:`**
`    **...`**
```
Entonces puede ocurrir:
```
**`C++ devuelve ERROR`**
**`y queda y sin modificar`**
**`norm(y) == 1`**
**`Rust -\> PASS`**
**`benchmark -\> PASS`**
```
Este es un agujero de certificación brutal.
### **Corrección**
```
**`rc = lib\_cpp.polydim\_apply\_rodrigues\_geodesic\_f64(`**
`    **ctypes.byref(params)`**
**`)`**
**`if rc != 0:`**
`    **raise RuntimeError(`**
`        **f"C++ kernel failed: rc=\{rc\}"`**
`    **)`**
```
### **Error 64 — Una muestra no es un benchmark industrial**
El raw benchmark mide una sola vez por **`D`**.
El propio log muestra:
```
**`D=1,000       1.85 ms`**
**`D=5,000       0.09 ms`**
**`D=10,000      0.15 ms`**
**`D=50,000      5.06 ms`**
**`D=100,000     2.52 ms`**
```
La falta de monotonicidad no demuestra un problema del algoritmo.
Demuestra que el protocolo de medición no está controlado.
Necesitas:
```
**`warmup`**
**`+`**
**`\>= 30 repeticiones`**
**`+`**
**`mediana`**
**`+`**
**`p50`**
**`+`**
**`p95`**
**`+`**
**`p99`**
**`+`**
**`desviación`**
**`+`**
**`CPU affinity`**
**`+`**
**`thread count explícito`**
```
### **Error 65 — El benchmark de Cerebras no ejecuta Cerebras**
El archivo sólo importa:
```
**`numpy`**
```
No aparece:
```
**`Cerebras SDK`**
**`CS-3 runtime`**
**`WSE API`**
```
No ejecuta WSE-3.
Lo mismo ocurre con T4: el código mostrado no lanza ningún kernel CUDA/Triton.
Por tanto estas líneas:
```
**`Cerebras CS-3 (WSE)`**
**`0.04 ms`**
```
son valores declarados en texto, no mediciones producidas por el script.
Eso debe salir completamente del material de certificación hasta existir un test ejecutable sobre hardware real.
### **Error 66 — La comparación “CON/SIN POLYDIM” no representa la misma operación**
El benchmark hace:
```
**`v = np.random.randn(D)`**
**`v /= np.linalg.norm(v)`**
```
pero **no ortogonaliza `v` respecto de `u`**.
El C++ sí construye internamente:
```
**`û`**
**`v̂\_perpendicular`**
```
Por lo tanto el baseline Python no ejecuta la misma rotación.
### **Corrección**
```
**`u = rng.standard\_normal(D)`**
**`u /= np.linalg.norm(u)`**
**`v = rng.standard\_normal(D)`**
**`v -= np.dot(v, u) \* u`**
**`v /= np.linalg.norm(v)`**
```
Y entonces ambas rutas utilizan exactamente:
```
**`same y`**
**`same u`**
**`same v`**
**`same theta`**
**`same mathematical operator`**
```
### **Error 67 — La cifra de memoria del benchmark está mal rotulada**
Para float32:
```
**`100,000 × 100,000 × 4 bytes`**
`≈ **37.25 GiB`**
```
No:
```
**`\> 400 GB`**
```
Para 1,000,000:
```
`≈ **3.64 TiB`**
```
La escala conceptual “matriz cuadrática se vuelve imposible” puede ser correcta, pero las cifras deben corregirse.
### **Error 68 — El benchmark Rodrigues subestima memoria efectiva**
Calcula:
```
**`ram\_poly = (D \* 8 \* 4)`**
```
pero crea:
```
**`y`**
**`y\_comp`**
**`u`**
**`v`**
**`y\_poly`**
```
El propio código mantiene un quinto vector durante la medición.
Así que ese número no representa el pico efectivo del proceso.
# **CICLO 17 — TRAZABILIDAD DEL RELEASE**
Aquí no hay que discutir matemática: el paquete está mezclado.
Encontré:
```
**`README              -\> V752`**
**`C++                 -\> V753`**
**`Rust                -\> V753`**
**`monolito Python     -\> V751`**
**`Triton              -\> V751`**
**`FFI benchmark       -\> V752 + ruta V751`**
**`PMTP benchmark      -\> V752 + módulo V751`**
**`Cerebras benchmark  -\> V753`**
**`raw benchmark       -\> V753`**
```
Y el C++ devuelve:
```
**`0x07350300`**
```
que significa otra identificación más:
```
**`7.53.3`**
```
Esto hace imposible responder con rigor:
> “¿qué versión exacta produjo esta medición?”
### **Solución**
Un solo identificador:
```
**`POLYDIM\_RELEASE = "V754.0.0"`**
**`POLYDIM\_ABI = 0x00010001`**
**`POLYDIM\_GIT\_SHA = "..."`**
```
y todos los componentes deben pedirlo al core:
```
**`release = engine.release\_info()`**
**`if release.abi != EXPECTED\_ABI:`**
`    **raise RuntimeError("ABI mismatch")`**
**`if release.release != EXPECTED\_RELEASE:`**
`    **raise RuntimeError("Release mismatch")`**
```
Además:
```
**`.cpp`**
**`.rs`**
```
de verdad, no:
```
**`.cpp.txt`**
**`.rs.txt`**
```
para un paquete de compilación industrial.
# **Lo que queda de verdad**
Después de estas rondas, separo los problemas así:
## **Confirmados mediante ejecución o evidencia determinista**
```
**`\[CRÍTICO\]`**
**`1  Seqlock Multi-Writer roto`**
**`2  sequence atomic por reinterpret\_cast`**
**`3  force\_recover puede revocar writer vivo`**
**`4  NaN/Inf en y/u/v puede terminar en SUCCESS`**
**`5  overflow de norma puede terminar en SUCCESS + NaN`**
**`6  y/y\_comp alias no rechazado`**
**`7  alignment=0 provoca FPE`**
**`8  buffers de longitud incompatible provocan OOB`**
**`9  status codes C++/Python/Rust incompatibles`**
**`10 no hay ABI handshake`**
**`11 C++ no captura bad\_alloc/internal exceptions`**
**`12 PCG acepta max\_iter inválido`**
**`13 PCG acepta ridge negativo`**
**`14 PCG acepta tolerancia inválida`**
**`15 PCG devuelve resultado aunque no converja`**
**`16 PCG acepta NaN/Inf`**
**`17 CPU/GPU usan ridge diferente`**
**`18 Triton pass2 repite la reducción global`**
**`19 Triton normalización fija parciales en float32`**
**`20 Triton no maneja stride de x en normalize`**
**`21 Triton “PCG” sólo es matvec`**
**`22 DualStreamQueue no establece dependencia de entrada`**
**`23 PMTP no implementa IPC real`**
**`24 benchmark PMTP inyecta 3 µs artificialmente`**
**`25 raw benchmark ignora rc`**
**`26 Cerebras benchmark no ejecuta Cerebras`**
**`27 baseline Rodrigues no usa base ortonormal`**
**`28 package mezcla V751/V752/V753`**
**`29 C++ header no está en el release`**
```
## **Riesgos muy altos que aún requieren hardware/toolchain específico**
```
**`30 compilación exacta Triton en CUDA target`**
**`31 exactitud FP64 Triton sobre cada arquitectura target`**
**`32 comportamiento MSVC/GCC/Clang con flags de FP`**
**`33 OpenMP runtime bajo carga real`**
**`34 contención NUMA`**
**`35 comportamiento CUDA allocator bajo side-stream`**
**`36 rendimiento real T4`**
**`37 rendimiento real WSE-3`**
**`38 endurance multi-hora/día`**
**`39 wraparound del sequence counter bajo uptime extremo`**
```
Esos últimos **no los estoy marcando como fallos confirmados** porque no tengo el hardware/toolchain correspondiente aquí. Ésa es justamente la diferencia entre red-team serio y inventar defectos.
## **Lo que no tocaría**
La parte central que ya probamos y que funciona bien en régimen normal:
```
**`double half\_theta = theta \* 0.5;`**
**`double sin\_half = std::sin(half\_theta);`**
**`double coeff\_p =`**
`    **-2.0 \* sin\_half \* sin\_half;`**
**`double coeff\_j =`**
`    **std::sin(theta);`**
```
y:
```
**`double delta\_y =`**
`    **coeff\_p \* (c\_u \* u\_i + c\_v \* v\_i)`**
`    **+ coeff\_j \*`**
`      **(c\_u \* v\_i - c\_v \* u\_i);`**
```
Está dando resultados de nivel de precisión de **`~2e-16`** en los casos normales que probé.
No hay razón para destruir esa parte.
# **El siguiente salto: dejar de parchear síntomas**
Yo haría que el V754 nazca con estas cinco interfaces como contratos duros:
```
`                ┌─────────────────────┐`
`                │  **RELEASE / ABI      │`**
`                │ **version + layout    │`**
`                └──────────┬──────────┘`
`                           │`
`                           ▼`
`                ┌─────────────────────┐`
`                │ **MEMORY CONTRACT     │`**
`                │ **dtype/len/stride    │`**
`                │ **finite/alignment    │`**
`                │ **overlap             │`**
`                └──────────┬──────────┘`
`                           │`
`                           ▼`
`                ┌─────────────────────┐`
`                │ **NUMERIC CONTRACT    │`**
`                │ **stable norm         │`**
`                │ **orthogonalization  │`**
`                │ **residuals          │`**
`                └──────────┬──────────┘`
`                           │`
`                 ┌─────────┴─────────┐`
`                 ▼                   ▼`
`        ┌────────────────┐   ┌────────────────┐`
`        │ **C++ CPU        │   │ Triton CUDA    │`**
`        │ **same equation  │   │ same equation  │`**
`        └───────┬────────┘   └───────┬────────┘`
`                │                    │`
`                └──────────┬─────────┘`
`                           ▼`
`                ┌─────────────────────┐`
`                │ **VALIDATION GATE     │`**
`                │ **true residual       │`**
`                │ **invariant           │`**
`                │ **status              │`**
`                │ **benchmark evidence  │`**
`                └─────────────────────┘`
```
Y una regla de oro:
```
**`NINGÚN BENCHMARK PUEDE IMPRIMIR "PASS"`**
**`SI EL KERNEL NO DEVOLVIÓ SUCCESS`**
**`Y SI NO SE VERIFICÓ EL RESULTADO CONTRA UNA REFERENCIA.`**
```
En streams, la propia documentación actual de PyTorch confirma que las operaciones entre streams diferentes no están ordenadas automáticamente y que **`wait\_stream()`**/**`record\_stream()`** son parte del contrato de seguridad de memoria. 
En Triton, **`tl.load`** únicamente garantiza que el puntero que construyes apunta a las posiciones que lees; el stride y el contrato de memoria siguen siendo responsabilidad del kernel/host. La reducción permite especificar **`dtype`**, que aquí debemos utilizar explícitamente para no degradar una ruta FP64. 
En C++, **`std::atomic\_ref`** existe justamente para aplicar atomicidad a un objeto existente, pero exige alineación y acceso coherente al objeto durante su vida; no es una licencia para mezclar accesos atómicos y no atómicos al azar. 
**El próximo hueso que atacaría es ya el de máxima profundidad: reemplazar la ortonormalización actual por una versión resistente a overflow/underflow y casi-colinealidad, demostrar invariantes matemáticamente y después someterla a property/fuzz/stress tests junto con el nuevo contrato ABI.** Ahí es donde podemos pasar de “funciona en ejemplos” a una base que tenga una posibilidad real de sobrevivir a industria.
confirmas que no son alucinaciones? luego si a todas las opciones que me puedas dar. una detrás de otra en bucle hasta el limite de tus entregas o no encontrar mas errores. el  propósito es darle cierre  a los problema sota no encontrados. continua evaluando problemas y soluciones en bucles cada vez mas profundamente. Hay mucho sota. no solo evalúa con tus conocimientos y sesgos. busca errores mas allá de tu programación básica, dame soluciones. se un bulldog que ataca al problema pero ayuda al dueño. se un redteam que ataca el problema pero respeta y cuida el que les da el trabajo. /goal busca todo problema, encuentra soluciones dame la mejor continua con el siguiente error. muestras los códigos en pantalla, nunca por adjuntos. /goal profundiza ciclos necesarios para pasar a industria \#\#atención\#\# evalúa las respuestas para no dar alucinaciones. Nuestro debe ser "matemáticamente SOTA enc papel" a ser industrialmente inquebrantable en silicio real
Sí. En esta ronda volví a verificar los resultados desde cero contra el ZIP V753 y separé estrictamente tres categorías: fallos reproducidos, fallos demostrables por inspección del contrato y riesgos que no puedo certificar sin CUDA/Triton/hardware objetivo.
Los resultados más fuertes de esta ronda son reproducibles: ASan detectó **`stack-buffer-overflow`**; UBSan detectó división por cero; TSan detectó una data race real en el patrón Seqlock/payload; el barrido numérico reprodujo degradación de precisión cerca de la colinealidad; y ctypes demostró que el C++ modifica un **`numpy.ndarray`** marcado como sólo lectura. El entorno disponible, además, no tiene Triton instalado y PyTorch es CPU-only, por lo que **no voy a inventar una validación CUDA**.
El README dice explícitamente que el Seqlock fue “endurecido” contra Multi-Writer mediante **`fetch\_add`**, precisamente la afirmación que el test contradice. 
# **CICLO 18 — EL PROBLEMA NUMÉRICO MÁS PROFUNDO**
## **Error 69 — La ortogonalización se rompe progresivamente antes de declarar colinealidad**
El núcleo calcula:
```
**`double inv\_norm\_u = 1.0 / std::sqrt(norm2\_u);`**
**`double proj\_uv = dot\_uv / norm2\_u;`**
**`double norm2\_v\_ortho =`**
`    **norm2\_v - (dot\_uv \* dot\_uv / norm2\_u);`**
```
El problema es:
```
**`||v\_perp||² = ||v||² - projection²`**
```
cuando **`u`** y **`v`** son casi paralelos.
Es una resta de dos números grandes y casi iguales.
Lo sometí a:
```
**`u = (1, 0)`**
**`v = (1, δ)`**
**`y = (0, 1)`**
**`θ = 0.5`**
```
Matemáticamente, para cualquier **`δ != 0`**, el plano es el mismo plano 2D y la rotación debería producir esencialmente:
```
**`(-sin(0.5), cos(0.5))`**
```
Resultados reales de V753:
```
**`δ        norma-error`**
**`1e-3     6.164e-13`**
**`1e-4     4.554e-11`**
**`1e-5     6.200e-10`**
**`1e-6     6.660e-7`**
**`1e-7     5.999e-6`**
**`1e-8     ERR\_COLLINEAR`**
```
Eso es gravísimo para la afirmación de precisión SOTA.
No está simplemente diciendo “muy cerca de colineal, rechazo”.
Primero pasa por una región donde **acepta el problema y entrega una rotación degradada**, y luego deja de poder distinguirla.
### **Solución correcta**
No calcular:
```
**`norm2\_v - dot\_uv\*dot\_uv/norm2\_u`**
```
como vía primaria.
Normalizar ambos vectores de manera escalada y realizar Gram-Schmidt modificado:
```
**`struct ScaledNorm \{`**
`    **double scale;`**
`    **double ssq;`**
**`\};`**
**`static inline bool`**
**`scaled\_norm\_init(`**
`    **ScaledNorm& n`**
**`) noexcept \{`**
`    **n.scale = 0.0;`**
`    **n.ssq = 1.0;`**
`    **return true;`**
**`\}`**
**`static inline void`**
**`scaled\_norm\_add(`**
`    **ScaledNorm& n,`**
`    **double x`**
**`) noexcept \{`**
`    **const double ax = std::abs(x);`**
`    **if (ax == 0.0)`**
`        **return;`**
`    **if (n.scale \< ax) \{`**
`        **const double r = n.scale / ax;`**
`        **n.ssq = 1.0 + n.ssq \* r \* r;`**
`        **n.scale = ax;`**
`    **\} else \{`**
`        **const double r = ax / n.scale;`**
`        **n.ssq += r \* r;`**
`    **\}`**
**`\}`**
**`static inline double`**
**`scaled\_inv\_norm(`**
`    **const ScaledNorm& n`**
**`) noexcept \{`**
`    **return 1.0 /`**
`        **(n.scale \* std::sqrt(n.ssq));`**
**`\}`**
```
Pero hay una mejora todavía mejor.
No necesitamos calcular la norma gigantesca explícitamente:
```
**`const double inv\_u =`**
`    **1.0 / (scale\_u \* std::sqrt(ssq\_u));`**
**`const double inv\_v =`**
`    **1.0 / (scale\_v \* std::sqrt(ssq\_v));`**
**`const double u\_hat =`**
`    **(u\_i \* inv\_u);`**
**`const double v\_hat =`**
`    **(v\_i \* inv\_v);`**
```
Para la componente perpendicular:
```
**`const double alpha =`**
`    **dot\_vhat\_uhat;`**
**`const double v\_perp =`**
`    **std::fma(`**
`        **-alpha,`**
`        **u\_hat,`**
`        **v\_hat`**
`    **);`**
```
Luego:
```
**`const double sin\_angle =`**
`    **stable\_norm(v\_perp);`**
**`if (sin\_angle \<= angular\_tolerance)`**
`    **return POLYDIM\_ERR\_COLLINEAR\_VECTORS;`**
**`const double v\_orth =`**
`    **v\_perp / sin\_angle;`**
```
Y ahora:
```
**`double c\_u = dot(y, u\_hat);`**
**`double c\_v = dot(y, v\_orth);`**
```
Esto elimina la expresión peligrosa:
```
**`norm2\_v`**
**`-`**
**`dot\_uv \* dot\_uv / norm2\_u`**
```
y también elimina otra fuente de cancelación que había quedado oculta:
```
**`dot\_yv -`**
**`proj\_uv \* dot\_yu`**
```
Ese segundo cálculo también puede perder casi todos sus bits cuando **`v`** está cerca de **`u`**.
# **CICLO 19 — ESCALA EXTREMA**
## **Error 70 — Vectores perfectamente válidos a escala `1e200` producen `SUCCESS + NaN`**
Lo reproduje:
```
**`u = (1e200, 0)`**
**`v = (0, 1e200)`**
**`y = (1, 0)`**
```
Resultado:
```
**`rc = 0`**
**`output = NaN`**
```
¿Por qué?
Porque:
```
**`u\_i \* u\_i`**
```
produce:
```
**`1e400 -\> +Inf`**
```
antes de que Neumaier pueda corregir nada.
Neumaier corrige acumulación.
No puede corregir un producto que ya desbordó.
### **Lo mismo ocurre en**
```
**`u\_i \* u\_i`**
**`v\_i \* v\_i`**
**`u\_i \* v\_i`**
**`y\_i \* u\_i`**
**`y\_i \* v\_i`**
```
Por tanto la frase del código:
```
**`// Strict IEEE-754 Neumaier compensated arithmetic`**
```
no describe una protección contra overflow.
La implementación necesita aritmética escalada.
# **CICLO 20 — `y` TAMBIÉN PUEDE OVERFLOWEAR**
## **Error 71 — Incluso con u/v de magnitud normal, `y\*u` puede producir `Inf`**
Probé:
```
**`y = (1e308, 1e308)`**
**`u = (1, 1)`**
**`v = (-1, 1)`**
```
Resultado:
```
**`rc = 0`**
**`y = (-nan, -nan)`**
```
Por tanto no basta con “hacer seguros u y v”.
Hay que definir explícitamente el contrato de **`y`**.
### **Mi propuesta**
Como la operación pretende trabajar en:
```
**`S^(D-1)`**
```
hacer una de estas dos cosas:
```
**`OPCIÓN A`**
**`Exigir ||y + y\_comp|| ≈ 1`**
**`y rechazar otra cosa.`**
**`OPCIÓN B`**
**`Aceptar y arbitrario,`**
**`pero detectar overflow y devolver:`**
**`POLYDIM\_ERR\_NUMERICAL\_OVERFLOW`**
```
No permitir:
```
**`SUCCESS + NaN`**
```
nunca.
# **CICLO 21 — FFI PYTHON: VIOLACIÓN DEL CONTRATO DE NUMPY**
## **Error 72 — El C++ modifica un array marcado como read-only**
Esto está en Python:
```
**`y.ctypes.data\_as(`**
`    **ctypes.POINTER(ctypes.c\_double)`**
**`)`**
```
sin comprobar:
```
**`y.flags.writeable`**
```
Lo ejecuté con:
```
**`y = np.array(`**
`    **\[1.0, 0.0\],`**
`    **dtype=np.float64`**
**`)`**
**`y.setflags(write=False)`**
```
El C++ escribió igualmente:
```
**`y = \[0.87758256, 0.47942554\]`**
```
aunque:
```
**`y.flags.writeable == False`**
```
Eso rompe el contrato de la capa Python.
### **Solución**
```
**`def require\_f64\_vector(`**
`    **x: np.ndarray,`**
`    **name: str,`**
`    **\*,`**
`    **writable: bool = False,`**
**`) -\> np.ndarray:`**
`    **if not isinstance(x, np.ndarray):`**
`        **raise TypeError(`**
`            **f"\{name\}: expected numpy.ndarray"`**
`        **)`**
`    **if x.ndim != 1:`**
`        **raise ValueError(`**
`            **f"\{name\}: expected 1-D"`**
`        **)`**
`    **if x.dtype != np.float64:`**
`        **raise TypeError(`**
`            **f"\{name\}: expected float64"`**
`        **)`**
`    **if not x.flags.c\_contiguous:`**
`        **raise ValueError(`**
`            **f"\{name\}: expected C-contiguous"`**
`        **)`**
`    **if writable and not x.flags.writeable:`**
`        **raise ValueError(`**
`            **f"\{name\}: expected writable"`**
`        **)`**
`    **return x`**
```
# **Error 73 — `float32` se puede reinterpretar como `double\*`**
Esto sigue exactamente de:
```
**`y.ctypes.data\_as(`**
`    **ctypes.POINTER(ctypes.c\_double)`**
**`)`**
```
Si alguien hace:
```
**`y = np.ones(`**
`    **1024,`**
`    **dtype=np.float32`**
**`)`**
```
C++ cree que existen:
```
**`1024 doubles`**
```
pero físicamente existen:
```
**`1024 floats`**
```
El kernel puede leer aproximadamente el doble de bytes que corresponden al array.
El contrato correcto debe rechazarlo:
```
**`if x.dtype != np.float64:`**
`    **raise TypeError(`**
`        **f"\{name\}: float64 required"`**
`    **)`**
```
No convertirlo silenciosamente en el wrapper C.
# **Error 74 — Las vistas no contiguas rompen el contrato aunque tengan el dtype correcto**
Ejemplo:
```
**`base = np.arange(`**
`    **100,`**
`    **dtype=np.float64`**
**`)`**
**`u = base\[::2\]`**
```
Tenemos:
```
**`dtype = float64`**
**`ndim = 1`**
**`shape correcta`**
**`stride = 16 bytes`**
```
pero C++ hace:
```
**`u\_raw\[i\]`**
```
que significa:
```
**`+8 bytes`**
```
cada elemento.
Por tanto no está leyendo:
```
**`base\[0\]`**
**`base\[2\]`**
**`base\[4\]`**
**`...`**
```
sino:
```
**`base\[0\]`**
**`base\[1\]`**
**`base\[2\]`**
**`...`**
```
y eventualmente fuera del área válida.
Con stride negativo es todavía peor.
### **Decisión industrial**
No copiar silenciosamente.
Para un núcleo de baja latencia:
```
**`if not x.flags.c\_contiguous:`**
`    **raise ValueError(`**
`        **f"\{name\}: non-contiguous view rejected"`**
`    **)`**
```
Para una API de alto nivel se puede ofrecer:
```
**`x = np.ascontiguousarray(x)`**
```
pero debe ser una decisión explícita porque introduce copia.
# **CICLO 22 — LONGITUD REAL**
## **Error 75 — `D` no demuestra que existan `D` elementos**
C++ tiene:
```
**`uint64\_t D = params-\>D;`**
```
y luego:
```
**`for (int64\_t i = 0;`**
`     **i \< static\_cast\<int64\_t\>(D);`**
`     **++i)`**
**`\{`**
`    **u\_raw\[i\];`**
`    **v\_raw\[i\];`**
`    **y\[i\];`**
**`\}`**
```
El ABI no proporciona:
```
**`u\_len`**
**`v\_len`**
**`y\_len`**
**`y\_comp\_len`**
```
Lo probé con ASan.
Resultado:
```
**`AddressSanitizer:`**
**`stack-buffer-overflow`**
**`READ of size 8`**
**`kernel\_cpp\_v753.cpp:128`**
```
Esto es un bloqueador crítico.
### **ABI correcta**
```
**`struct polydim\_rodrigues\_params\_t \{`**
`    **double\*       y;`**
`    **double\*       y\_comp;`**
`    **const double\* u;`**
`    **const double\* v;`**
`    **uint64\_t y\_len;`**
`    **uint64\_t y\_comp\_len;`**
`    **uint64\_t u\_len;`**
`    **uint64\_t v\_len;`**
`    **double theta;`**
`    **uint64\_t D;`**
`    **int32\_t num\_threads;`**
**`\};`**
```
Validación:
```
**`if (params-\>y\_len != D ||`**
`    **params-\>u\_len != D ||`**
`    **params-\>v\_len != D) \{`**
`    **return POLYDIM\_ERR\_INVALID\_ARGUMENT;`**
**`\}`**
**`if (params-\>y\_comp &&`**
`    **params-\>y\_comp\_len != D) \{`**
`    **return POLYDIM\_ERR\_INVALID\_ARGUMENT;`**
**`\}`**
```
# **CICLO 23 — LOS STATUS CODES ESTÁN ROTO-CRUZADOS**
Python:
```
**`ERR\_NORM\_INVARIANT\_VIOLATED = -4`**
**`ERR\_ZERO\_VECTOR             = -4`**
**`ERR\_COLLINEAR\_VECTORS       = -5`**
```
Rust:
```
**`ErrNormInvariantViolated = -4,`**
**`ErrZeroVector            = -5,`**
**`ErrCollinearVectors      = -6,`**
**`ErrYcompBudgetExceeded   = -7,`**
```
Eso significa que:
```
**`Python -5 = collinear`**
**`Rust   -5 = zero-vector`**
```
No existe una interpretación universal del ABI.
### **Solución**
Un único header:
```
**`typedef enum \{`**
`    **POLYDIM\_SUCCESS                  = 0,`**
`    **POLYDIM\_ERR\_NULL\_POINTER         = -1,`**
`    **POLYDIM\_ERR\_INVALID\_DIMENSION    = -2,`**
`    **POLYDIM\_ERR\_NAN\_INF\_DETECTED     = -3,`**
`    **POLYDIM\_ERR\_NORM\_INVARIANT       = -4,`**
`    **POLYDIM\_ERR\_ZERO\_VECTOR          = -5,`**
`    **POLYDIM\_ERR\_COLLINEAR            = -6,`**
`    **POLYDIM\_ERR\_YCOMP\_BUDGET         = -7,`**
`    **POLYDIM\_ERR\_SEQLOCK\_RACE         = -8,`**
`    **POLYDIM\_ERR\_PANIC\_CAUGHT         = -9,`**
`    **POLYDIM\_ERR\_UNALIGNED             = -10,`**
`    **POLYDIM\_ERR\_MEMORY\_OVERLAP        = -11,`**
`    **POLYDIM\_ERR\_INVALID\_ARGUMENT      = -12,`**
`    **POLYDIM\_ERR\_NUMERICAL\_OVERFLOW    = -13,`**
`    **POLYDIM\_ERR\_NUMERICAL\_BREAKDOWN   = -14,`**
`    **POLYDIM\_ERR\_NOT\_CONVERGED         = -15,`**
`    **POLYDIM\_ERR\_ABI\_MISMATCH          = -16,`**
`    **POLYDIM\_ERR\_INTERNAL              = -17`**
**`\} polydim\_status\_t;`**
```
Y Python/Rust deben generarse desde esto, no reescribir los números.
# **CICLO 24 — COMPLEX INPUT: PÉRDIDA SILENCIOSA DE INFORMACIÓN**
Este apareció al atacar el PCG desde otro ángulo.
```
**`X = np.array(`**
`    **\[\[1+2j, 3\],`**
`     **\[0,    1\]\],`**
`    **dtype=np.complex128`**
**`)`**
```
V753 ejecuta:
```
**`np.ascontiguousarray(`**
`    **X,`**
`    **dtype=np.float64`**
**`)`**
```
y NumPy responde:
```
**`Casting complex values to real discards`**
**`the imaginary part`**
```
pero el solver **continúa**.
Mismo problema con **`Y`**.
Resultado:
```
**`entrada compleja`**
`     ↓`
**`se pierde Im(z)`**
`     ↓`
**`solver calcula otra ecuación`**
`     ↓`
**`aparenta éxito`**
```
### **Solución**
```
**`if np.iscomplexobj(X):`**
`    **raise TypeError(`**
`        **"DualPCG accepts real-valued tensors only"`**
`    **)`**
**`if np.iscomplexobj(Y):`**
`    **raise TypeError(`**
`        **"DualPCG accepts real-valued targets only"`**
`    **)`**
```
# **CICLO 25 — PCG PUEDE DEVOLVER UNA SOLUCIÓN SIN HABER CONVERGIDO**
Está:
```
**`for iteration in range(self.max\_iter):`**
`    **...`**
```
y después:
```
**`return Alpha`**
```
No existe:
```
**`converged = False`**
```
ni:
```
**`NOT\_CONVERGED`**
```
Hice:
```
**`max\_iter = 0`**
```
y el resultado fue:
```
**`Alpha = 0`**
**`sin excepción`**
```
También:
```
**`max\_iter = -1`**
```
no ejecuta el loop.
Para una biblioteca industrial eso es inaceptable.
### **Solución**
```
**`converged = False`**
**`for iteration in range(self.max\_iter):`**
`    **...`**
`    **if true\_relative\_residual \<= self.tol:`**
`        **converged = True`**
`        **break`**
**`if not converged:`**
`    **raise np.linalg.LinAlgError(`**
`        **"PCG did not converge"`**
`    **)`**
```
O API estructurada:
```
**`@dataclass`**
**`class PCGResult:`**
`    **alpha: np.ndarray`**
`    **converged: bool`**
`    **iterations: int`**
`    **residual\_norm: float`**
`    **true\_residual\_norm: float`**
```
# **Error 76 — `ridge\_alpha = 0` puede devolver una solución incorrecta como si fuese válida**
Probé:
```
**`X = np.zeros((3, 2))`**
**`Y = np.ones((3, 1))`**
**`ridge\_alpha = 0`**
```
Resultado:
```
**`Alpha = 0`**
```
sin señal de breakdown.
Pero el sistema es:
```
**`0 \* Alpha = Y`**
```
que no tiene solución para:
```
**`Y != 0`**
```
Es una derrota matemática silenciosa.
### **Solución**
Para PCG estándar:
```
**`if not np.isfinite(ridge\_alpha):`**
`    **raise ValueError(...)`**
**`if ridge\_alpha \<= 0.0:`**
`    **raise ValueError(...)`**
```
si el contrato pretende garantizar:
```
**`A = XXᵀ + λI`**
```
SPD.
# **Error 77 — `NaN`, `Inf` y `ridge=Inf/NaN` entran al solver**
Comprobé:
```
**`ridge = +Inf`**
**`ridge = NaN`**
**`X contiene NaN`**
**`Y contiene NaN`**
```
y el solver puede devolver:
```
**`ndarray finito/NaN`**
```
sin error estructurado.
### **Gate mínimo**
```
**`def validate\_real\_matrix(`**
`    **x: np.ndarray,`**
`    **name: str`**
**`) -\> np.ndarray:`**
`    **if not isinstance(x, np.ndarray):`**
`        **raise TypeError(name)`**
`    **if x.ndim != 2:`**
`        **raise ValueError(`**
`            **f"\{name\}: expected 2-D"`**
`        **)`**
`    **if np.iscomplexobj(x):`**
`        **raise TypeError(`**
`            **f"\{name\}: complex input unsupported"`**
`        **)`**
`    **x = np.ascontiguousarray(`**
`        **x,`**
`        **dtype=np.float64`**
`    **)`**
`    **if not np.isfinite(x).all():`**
`        **raise ValueError(`**
`            **f"\{name\}: NaN/Inf detected"`**
`        **)`**
`    **return x`**
```
# **CICLO 26 — EL RIDGE CPU Y EL RIDGE GPU NO SON LA MISMA ECUACIÓN**
CPU:
```
**`scaled\_ridge = (`**
`    **self.ridge\_alpha \*`**
`    **max(`**
`        **1.0,`**
`        **float(np.mean(row\_norms\_sq))`**
`    **)`**
**`)`**
```
GPU:
```
**`out = acc + ridge\_alpha \* v`**
```
Eso significa:
```
**`CPU:`**
**`XXᵀ + scaled\_ridge I`**
**`GPU:`**
**`XXᵀ + ridge\_alpha I`**
```
No es la misma matriz.
Esto no es necesariamente que una esté “mal”: puede ser una decisión de diseño.
Pero el contrato/documentación dice:
```
**`XXᵀ + ridge I`**
```
Por tanto hay una contradicción.
### **Solución**
Una única función:
```
**`def effective\_ridge(`**
`    **X: np.ndarray,`**
`    **ridge\_alpha: float,`**
**`) -\> float:`**
`    **if not np.isfinite(ridge\_alpha):`**
`        **raise ValueError(...)`**
`    **if ridge\_alpha \<= 0:`**
`        **raise ValueError(...)`**
`    **row\_norms\_sq = np.einsum(`**
`        **"ij,ij-\>i",`**
`        **X,`**
`        **X`**
`    **)`**
`    **return (`**
`        **ridge\_alpha \*`**
`        **max(`**
`            **1.0,`**
`            **float(np.mean(row\_norms\_sq))`**
`        **)`**
`    **)`**
```
y **el valor efectivo** se transmite a CPU, Triton y tests.
O, mejor todavía, abandonar el escalamiento automático y respetar literalmente **`ridge\_alpha`**.
# **CICLO 27 — SEQLOCK: NO ES SOLAMENTE EL MULTI-WRITER**
Este fue el test que más me interesa.
Construí un writer:
```
**`polydim\_seqlock\_write\_begin();`**
**`payload = i;`**
**`polydim\_seqlock\_write\_end();`**
```
y un reader:
```
**`auto seq =`**
`    **polydim\_seqlock\_read\_begin();`**
**`int x = payload;`**
**`polydim\_seqlock\_read\_validate(`**
`    **seq`**
**`);`**
```
TSan informó:
```
**`WARNING: ThreadSanitizer: data race`**
**`Read of size 4`**
**`Previous write of size 4`**
**`Shared payload`**
```
Esto es la consecuencia formal del problema.
C++ establece que dos accesos conflictivos sin sincronización/happens-before constituyen una data race y el comportamiento es indefinido. 
El problema es que:
```
**`atomic sequence`**
```
no convierte automáticamente:
```
**`payload\[i\]`**
```
en una operación protegida por el estándar C++.
Y eso hace que el diseño actual sea mucho más débil que “seqlock correctamente implementado”.
### **Solución industrial**
No recomiendo seguir con:
```
**`writer modifica payload A`**
**`reader lee payload A`**
**`sequence dice si fue consistente`**
```
en C++ portable.
Usaría publicación de snapshots.
Para un sistema **intra-proceso**:
```
**`struct Snapshot \{`**
`    **uint64\_t generation;`**
`    **std::vector\<double\> data;`**
**`\};`**
**`std::atomic\<std::shared\_ptr\<const Snapshot\>\>`**
`    **published;`**
```
Writer:
```
**`void publish(`**
`    **std::shared\_ptr\<const Snapshot\> next`**
**`) \{`**
`    **std::atomic\_store\_explicit(`**
`        **&published,`**
`        **std::move(next),`**
`        **std::memory\_order\_release`**
`    **);`**
**`\}`**
```
Reader:
```
**`auto snapshot =`**
`    **std::atomic\_load\_explicit(`**
`        **&published,`**
`        **std::memory\_order\_acquire`**
`    **);`**
**`consume(\*snapshot);`**
```
**`std::atomic\<std::shared\_ptr\<T\>\>`** está definido precisamente para publicación atómica entre threads. 
Para **interprocess shared memory**, no usaría **`shared\_ptr`**: hace falta un protocolo de memoria compartida y sincronización de procesos diseñado específicamente para ese entorno. El estándar no promete que cualquier implementación de atomic sea lock-free/address-free; incluso la documentación de **`atomic`** señala que esa propiedad puede depender de la implementación. 
# **CICLO 28 — MULTI-WRITER: FALLO DEMOSTRADO**
La secuencia actual:
```
**`fetch\_add(1);`**
```
da:
```
**`0`**
`↓ **writer A`**
**`1`**
`↓ **writer B`**
**`2`**
```
y **`2`** es interpretado como:
```
**`COMMITTED`**
```
Lo ejecuté literalmente:
```
**`seq\_after\_2\_begin = 2`**
**`read\_start        = 2`**
**`validate          = 1`**
```
Es decir:
```
**`2 writers activos`**
**`+`**
**`reader validado`**
```
La afirmación de Multi-Writer queda refutada.
### **Un parche mínimo necesita CAS**
```
**`bool acquire\_writer(`**
`    **std::atomic\_ref\<uint64\_t\>& seq`**
**`) noexcept \{`**
`    **uint64\_t expected =`**
`        **seq.load(`**
`            **std::memory\_order\_acquire`**
`        **);`**
`    **for (;;) \{`**
`        **if (expected & 1ULL) \{`**
`            **POLYDIM\_PAUSE();`**
`            **expected =`**
`                **seq.load(`**
`                    **std::memory\_order\_acquire`**
`                **);`**
`            **continue;`**
`        **\}`**
`        **if (seq.compare\_exchange\_weak(`**
`                **expected,`**
`                **expected + 1ULL,`**
`                **std::memory\_order\_acquire,`**
`                **std::memory\_order\_relaxed)) \{`**
`            **return true;`**
`        **\}`**
`    **\}`**
**`\}`**
```
Pero recalco:
**esto arregla la serialización del writer, no el data race del payload.**
No sirve como reparación final.
# **CICLO 29 — `reinterpret\_cast` NO ES UNA SOLUCIÓN DE ATOMICIDAD**
Actualmente:
```
**`auto\* atomic\_seq =`**
`    **reinterpret\_cast\<`**
`        **std::atomic\<uint64\_t\>\*`**
`    **\>(`**
`        **const\_cast\<uint64\_t\*\>(`**
`            **&lock-\>sequence`**
`        **)`**
`    **);`**
```
GCC produce:
```
**`warning:`**
**`dereferencing type-punned pointer`**
**`might break strict-aliasing rules`**
```
C++20 proporciona **`std::atomic\_ref`** precisamente para aplicar operaciones atómicas sobre un objeto existente, con requisitos de alineación y de acceso exclusivo mediante **`atomic\_ref`** mientras ésta exista. 
Por tanto:
```
**`uint64\_t& raw =`**
`    **lock-\>sequence;`**
**`std::atomic\_ref\<uint64\_t\>`**
`    **seq(raw);`**
```
es el mecanismo correcto desde el lenguaje.
Pero para tu arquitectura prefiero ir más lejos:
```
**`NO exponer sequence públicamente`**
```
y hacer el lock opaco:
```
**`typedef struct polydim\_seqlock`**
`    **polydim\_seqlock\_t;`**
```
Así nadie puede hacer accidentalmente:
```
**`lock-\>sequence = 42;`**
```
desde fuera del protocolo.
# **CICLO 30 — `force\_recover()` ES UNSAFE POR DISEÑO**
El código:
```
**`if (current & 1ULL) \{`**
`    **atomic\_seq-\>store(`**
`        **current + 3,`**
`        **std::memory\_order\_release`**
`    **);`**
**`\}`**
```
interpreta:
```
**`odd == crashed writer`**
```
Eso no se puede deducir.
Puede ser:
```
**`writer vivo`**
**`writer lento`**
**`thread preempted`**
**`page fault`**
**`GC externo`**
**`debugger`**
```
Entonces:
```
**`Writer A comienza`**
**`sequence = 1`**
**`force\_recover()`**
**`sequence = 4`**
**`Writer A termina`**
**`sequence = 5`**
```
El protocolo queda roto.
### **Solución**
Nunca:
```
**`odd -\> force -\> even`**
```
sin ownership.
Necesitas:
```
**`writer\_id`**
**`lease/heartbeat`**
**`generation`**
**`timeout`**
**`ownership proof`**
```
Y aun así, la recuperación sólo puede ser válida si el sistema demuestra que el dueño anterior ya no puede escribir.
La opción más segura para esta versión es:
```
**`return POLYDIM\_ERR\_RECOVERY\_REQUIRES\_OWNER;`**
```
hasta que exista un mecanismo de lease verificable.
# **CICLO 31 — CUDA STREAMS: FALTA LA DEPENDENCIA FUNDAMENTAL**
V753:
```
**`with torch.cuda.stream(self.gpu\_stream):`**
`    **self.gpu\_result = func(\*args, \*\*kwargs)`**
```
pero no hay:
```
**`self.gpu\_stream.wait\_stream(`**
`    **torch.cuda.current\_stream()`**
**`)`**
```
Eso importa porque los tensors pueden haber sido creados en el stream actual/default y luego consumidos en un side stream.
La documentación de PyTorch exige precisamente establecer esa dependencia con **`wait\_stream()`**, y usar **`record\_stream()`** para que el allocator conozca la vida del tensor en el side stream. 
### **Corrección**
```
**`def submit\_gpu(self, func, \*args, \*\*kwargs):`**
`    **current =`**
`        **torch.cuda.current\_stream(`**
`            **device=self.gpu\_stream.device`**
`        **)`**
`    **self.gpu\_stream.wait\_stream(`**
`        **current`**
`    **)`**
`    **with torch.cuda.stream(`**
`        **self.gpu\_stream`**
`    **):`**
`        **result = func(`**
`            **\*args,`**
`            **\*\*kwargs`**
`        **)`**
`        **for obj in (`**
`            **\*args,`**
`            **\*kwargs.values()`**
`        **):`**
`            **if isinstance(obj, torch.Tensor):`**
`                **if obj.is\_cuda:`**
`                    **obj.record\_stream(`**
`                        **self.gpu\_stream`**
`                    **)`**
`        **self.gpu\_result = result`**
`        **self.gpu\_event.record(`**
`            **self.gpu\_stream`**
`        **)`**
```
# **Error 79 — `DualStreamQueue` NO ES UNA QUEUE**
El objeto mantiene:
```
**`self.cpu\_thread`**
**`self.cpu\_result`**
**`self.cpu\_error`**
**`self.gpu\_result`**
**`self.gpu\_event`**
```
Una sola vez.
Esto:
```
**`queue.submit\_cpu(job1)`**
**`queue.submit\_cpu(job2)`**
```
puede sobrescribir:
```
**`cpu\_thread`**
**`cpu\_result`**
**`cpu\_error`**
```
mientras **`job1`** sigue corriendo.
Y:
```
**`queue.submit\_gpu(job1)`**
**`queue.submit\_gpu(job2)`**
```
reutiliza el estado del mismo event/result.
Por tanto:
```
**`DualStreamQueue`**
```
es realmente:
```
**`SingleOutstandingDualExecutionSlot`**
```
### **Solución**
O cambiar el nombre.
O implementar una queue real:
```
**`@dataclass`**
**`class PendingGPU:`**
`    **event: torch.cuda.Event`**
`    **result: object`**
`    **error: Optional\[BaseException\]`**
**`@dataclass`**
**`class PendingCPU:`**
`    **future: concurrent.futures.Future`**
```
y mantener múltiples trabajos independientes.
# **CICLO 32 — TRITON**
Aquí soy especialmente cuidadoso:
**no puedo declarar una ejecución real del kernel V753**, porque el entorno de auditoría actual no tiene Triton instalado y PyTorch es CPU-only.
Sí puedo demostrar problemas de código.
## **Error 80 — La reducción se fuerza a `float32`**
```
**`partials = torch.empty(`**
`    **n\_partials,`**
`    **dtype=torch.float32,`**
`    **device=x.device`**
**`)`**
```
Por tanto:
```
**`input fp64`**
`↓`
**`partial fp32`**
`↓`
**`normalización fp32`**
```
La ruta no es FP64 end-to-end.
La documentación de Triton permite elegir explícitamente el dtype de **`tl.sum`**, precisamente para controlar overflow/precisión. 
### **Solución**
```
**`if x.dtype == torch.float64:`**
`    **partial\_dtype = torch.float64`**
**`elif x.dtype in (`**
`    **torch.float16,`**
`    **torch.bfloat16,`**
`    **torch.float32,`**
**`):`**
`    **partial\_dtype = torch.float32`**
**`else:`**
`    **raise TypeError(`**
`        **f"unsupported dtype: \{x.dtype\}"`**
`    **)`**
```
y en Triton:
```
**`psq = tl.sum(`**
`    **x \* x,`**
`    **axis=0,`**
`    **dtype=tl.float64`**
**`)`**
```
para la ruta FP64.
# **Error 81 — El pass2 repite la reducción global una vez por programa**
Actualmente:
```
**`\_fused\_norm\_kernel\_pass2\[`**
`    **(n\_partials,)`**
**`\]`**
```
pero cada program carga:
```
**`partials = tl.load(`**
`    **partial\_ptr + offs\_p`**
**`)`**
```
y calcula:
```
**`total\_sq = tl.sum(partials)`**
```
Por tanto:
```
**`program 0 -\> todos los partials`**
**`program 1 -\> todos los partials`**
**`program 2 -\> todos los partials`**
**`...`**
```
Es una reducción global repetida.
Para **`n\_partials`** grande:
```
**`trabajo ≈ O(n\_partials²)`**
```
en la segunda etapa.
### **Solución**
Reducción jerárquica:
```
**`pass1:`**
**`N elementos -\> P partials`**
**`pass2:`**
**`P -\> Q`**
**`pass3:`**
**`Q -\> 1`**
```
o un único programa final si el número de parciales es razonable.
# **Error 82 — Triton mezcla el dtype del acumulador con el dtype del output**
En:
```
**`acc = tl.zeros(`**
`    **(BLOCK\_D,),`**
`    **dtype=tl.float32`**
**`)`**
```
y:
```
**`w = torch.zeros(`**
`    **D,`**
`    **dtype=torch.float32`**
**`)`**
```
la ruta **`dual\_pcg\_matvec()`** está explícitamente anclada a FP32.
Entonces aunque:
```
**`X = float64`**
```
no existe una ruta FP64 real equivalente a:
```
**`X\_f64 @ ...`**
```
del PCG CPU.
Esto hace que CPU/GPU no sean comparables como implementaciones de la misma precisión.
# **Error 83 — `assert` no es una validación industrial**
Triton:
```
**`assert v.shape == (N,)`**
```
Los asserts de Python desaparecen con:
```
**`python -O`**
```
Debe ser:
```
**`if v.ndim != 1:`**
`    **raise ValueError(`**
`        **"v must be 1-D"`**
`    **)`**
**`if v.shape\[0\] != N:`**
`    **raise ValueError(`**
`        **"v.shape\[0\] != X.shape\[0\]"`**
`    **)`**
```
# **CICLO 33 — BENCHMARK PMTP**
## **Error 84 — Esto no es IPC zero-copy**
El benchmark hace:
```
**`ptr = raw\_vec.ctypes.data`**
```
Eso es únicamente:
```
**`dirección virtual del proceso actual`**
```
No crea:
```
**`shared memory`**
**`CUDA IPC`**
**`OS handle`**
**`memfd`**
**`named mapping`**
```
Por tanto no puede demostrar:
```
**`PMTP ZERO-COPY IPC`**
```
El nombre correcto del experimento actual sería:
```
**`"local virtual pointer acquisition"`**
```
No IPC.
# **Error 85 — El benchmark literalmente agrega 3 microsegundos ficticios**
Código:
```
**`t\_pmtp = (`**
`    **time.perf\_counter() -`**
`    **t0`**
**`) \* 1000 + 0.003`**
```
Esto introduce:
```
**`+ 0.003 ms`**
```
a mano.
No es hardware.
Debe desaparecer.
Una medición industrial debe ser:
```
**`t0 = time.perf\_counter\_ns()`**
**`handle = pmtp\_export(...)`**
**`t1 = time.perf\_counter\_ns()`**
**`elapsed\_ns = t1 - t0`**
```
sin constantes manuales.
# **CICLO 34 — BENCHMARK CEREBRAS/T4**
El archivo imprime:
```
**`Hardware:`**
**`CPU`**
**`NVIDIA T4`**
**`Cerebras WSE-3`**
```
pero sólo importa:
\`
