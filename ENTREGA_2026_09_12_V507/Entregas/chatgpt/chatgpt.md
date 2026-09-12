ENTREGA\_2026\_09\_11\_V505\_FASE13\_REDTEAM.zip

Archivo Zip

lee profundamente, evalua errores, dame soluciones. se un bulldog que ataca al problema pero ayuda al dueño. se un redteam que ataca el problema pero respeta y cuida el que les da el trabajo. /goal busca todo problema, encuentra soluciones dame la mejor continua con el siguiente error. No te apresures. gasta tu tiempo. prefiero lento y chequeado que rapido y mal. no quiero alucinaciones --------------------------. \#\#\# POLYDIM – RED‑TEAM / BULLDOG RESEARCH PROMPT \*\*USER\_ROLE:\*\* Arquitecto de infraestructura multi‑vectorial (creador de la arquitectura de alto‑dimensionalidad). \*\*AI\_ROLE:\*\* RedTeam / Bulldog técnico – ataca los problemas sin piedad pero protege al creador del trabajo. \*\*DIRECTIVE:\*\* - Cero sermones. - Cero alucinaciones. - Cero culpa al usuario. - Operar al límite del silicio: optimización de bajo nivel, compiladores, concurrencia, tensores y protocolos distribuidos. - Traducir la física computacional a ejecución real. \*\*GOAL (/goal):\*\* Buscar \*todos\* los problemas en el código de POLYDIM, encontrar soluciones y entregar la \*mejor\* solución continua. \*\*STATUS:\*\* Sesión vinculada al núcleo de emancipación arquitectónica. Continuar despliegue SOTA. \*\*TASKS FOR THE STUDENT:\*\* 1. \*\*Lectura profunda\*\* del código fuente (`kernel\_cpp\_v\*.cpp.txt`, `kernel\_rust\_v\*.rs.txt`, `polydim\_v\*\_monolito.py`). 2. \*\*Evaluar errores\*\* de: - Asignaciones de memoria no‑in‑place. - Uso del recolector de basura (busca `gc.disable()`/`gc.enable()`). - Alineación de estructuras FFI (`alignas(64)`, `\#\[repr(C, align(64))\]`). - Condiciones de carrera y bloqueos de hilos. - Manejo de tensores con NaN / Inf / subnormales. 3. \*\*Proponer remedios\*\* con código de parche (ej.: `torch.mm(out=)`, `torch.add\_()`, prefetch, double‑buffering). 4. \*\*Generar evidencia\*\*: - Logs crudos del asedio (`asedio\_v\*\_output.txt`). - Métricas de latencia y uso de RAM por iteración. - Pruebas unitarias que reproduzcan los fallos detectados. 5. \*\*Crear artefacto\*\* `report.md` con: - Lista de hallazgos. - Soluciones propuestas (código + explicación). - Evidencia cruda (copiar output del log). \*\*CRITERIOS DE ACEPTACIÓN:\*\* - Cada vulnerabilidad crítica tiene una solución implementable y una prueba de concepto que la verifica. - El informe incluye logs sin editar y métricas de rendimiento antes y después del parche. - No se introduce código que genere datos sintéticos sin su script de generación y salida. Esta es la 3er ronde del dia de hoy. realmente no entiendo, entre los 4 archivos no llegan a 1000 lineas. como puede ser que no encuentres todos los errores en casi seis meses de 3 entregas diarias los 7 dias de la semana. Y tengamos en cuenta el que se apuera en darme respuestas pobres y no profundas sos vos. Parece que estas apurado y me das para solucionarlo 10 items. Yo voy rehago el codigo, lo pruebo y vuelvo. Luego encuentras que aun hay cosas mal que no te habias dado cuenta antes, voy hago mi parte y asi de lunes a domingo en tre 2 y 3 veces a veces 4. quien hace un trabajo por la mitad? como puede ser mas de 600 interacciones no tengamos terminado algo de 1000 lineas. solo mil 800 de rust 100 entre los python y 100 en cpp como muchisimo SoS BULDOG muerde hasta el hueso. no quiero volver 600 veces mas. quiero que termines de darme 1000 lineas. solo 1000 perfectas 

confirmas que no son alucinaciones? luego si a todas las opciones que me puedas dar. una detrás de otra en bucle hasta el limite de tus entregas o no encontrar mas errores. el propósito es darle cierre a los problema sota no encontrados. continua evaluando problemas y soluciones en bucles cada vez mas profundamente. Hay mucho sota. no solo evalúa con tus conocimientos y sesgos. busca errores mas allá de tu programación básica, dame soluciones. se un bulldog que ataca al problema pero ayuda al dueño. se un redteam que ataca el problema pero respeta y cuida el que les da el trabajo. /goal busca todo problema, encuentra soluciones dame la mejor continua con el siguiente error. muestras los códigos en pantalla, nunca por adjuntos. /goal profundiza ciclos necesarios para pasar a industria \#\#atención\#\# evalúa las respuestas para no dar alucinaciones. Nuestro deve ser "matemáticamente SOTA en papel" a ser industrialmente inquebrantable en silicio real.

Sí. **Confirmo que no debo tratar mis 40 hallazgos anteriores como 40 verdades simplemente porque yo los escribí.** Los estoy revalidando contra el código real y, donde corresponde, contra documentación primaria. En esta revisión ya encontré algo importante: **algunos de los diagnósticos anteriores eran demasiado fuertes o estaban formulados de manera imprecisa**. Eso también cuenta como un error mío y lo corrijo ahora.

Por ejemplo, el punto sobre `ibv\_send\_wr` necesita precisión: el layout actual de `libibverbs` **no es de 80 bytes como afirma el fuente**; la estructura real incluye una unión final adicional después de `qp\_type`. La documentación y el header muestran `wr`, `qp\_type` y otra unión (`bind\_mw`/`tso`). Eso no significa automáticamente que el `RDMA\_WRITE` falle sólo por el tamaño total, porque los campos usados están antes; significa que la afirmación de “replica EXACTAMENTE” es falsa y que **no debemos implementar este ABI a mano**. Esa distinción es importante.

## Ciclo 1 — desmontar lo que parecía “cerrado”

### 1. RDMA: esto sí está confirmado como crítico

El código hace:

```
`let local\_addr = (mr as u64).wrapping\_add(off as u64);`

`let mut sge = ibv\_sge \{`

`    addr: local\_addr,`

`    length: sz as u32,`

`    lkey: 0`

`\};`
```

Esto no es una interpretación: es una violación directa del contrato de `ibv\_sge`.

`addr` debe ser la dirección del **buffer local** y `lkey` la clave del MR local. 

Por tanto, `mr + off` **no equivale** a `buffer + off`, y `lkey=0` no es el `lkey` del MR.

Además falta comprobar:

```
`off + sz \<= mr-\>length`
```

El código sólo comprueba que `off + sz` no desborde `usize`.

### Parche correcto

No recomiendo seguir intentando reconstruir `struct ibv\_mr` ni `struct ibv\_send\_wr` desde Rust.

La frontera industrial debe ser:

```
`// rdma\_shim.h`

`\#pragma once`

`\#include \<infiniband/verbs.h\>`

`\#include \<stdint.h\>`

`\#include \<stddef.h\>`


`struct pmtp\_rdma\_region \{`

`    struct ibv\_mr \*mr;`

`\};`


`int pmtp\_rdma\_write(`

`    struct ibv\_qp \*qp,`

`    struct ibv\_mr \*mr,`

`    size\_t off,`

`    size\_t len,`

`    uint64\_t remote\_addr,`

`    uint32\_t remote\_rkey,`

`    uint64\_t wr\_id`

`);`
```

Y en C:

```
`int pmtp\_rdma\_write(`

`    struct ibv\_qp \*qp,`

`    struct ibv\_mr \*mr,`

`    size\_t off,`

`    size\_t len,`

`    uint64\_t remote\_addr,`

`    uint32\_t remote\_rkey,`

`    uint64\_t wr\_id`

`) \{`

`    if (!qp || !mr || !mr-\>addr) return -1;`

`    if (len == 0) return -2;`

`    if (off \> mr-\>length) return -3;`

`    if (len \> mr-\>length - off) return -4;`


`    struct ibv\_sge sge = \{`

`        .addr   = (uintptr\_t)mr-\>addr + off,`

`        .length = (uint32\_t)len,`

`        .lkey   = mr-\>lkey,`

`    \};`


`    struct ibv\_send\_wr wr = \{0\};`


`    wr.wr\_id      = wr\_id;`

`    wr.sg\_list    = &sge;`

`    wr.num\_sge    = 1;`

`    wr.opcode     = IBV\_WR\_RDMA\_WRITE;`

`    wr.send\_flags = IBV\_SEND\_SIGNALED;`

`    wr.wr.rdma.remote\_addr = remote\_addr;`

`    wr.wr.rdma.rkey = remote\_rkey;`


`    struct ibv\_send\_wr \*bad = NULL;`


`    return ibv\_post\_send(qp, &wr, &bad);`

`\}`
```

La ventaja no es estética. El compilador que conoce **el header real instalado** construye el `ibv\_send\_wr` real. No estamos jugando a adivinar ABI.

**Estado:** confirmado.


# 2. El “fix” de MXCSR todavía está roto

El código:

```
`let old = core::arch::x86\_64::\_mm\_getcsr();`

`core::arch::x86\_64::\_mm\_setcsr(old | 0x8040);`

`let r = f();`

`core::arch::x86\_64::\_mm\_setcsr(old);`

`r`
```

El comentario dice:

> RESTAURAR SIEMPRE

Pero no.

Si `f()` hace panic:

```
`set MXCSR`

`   ↓`

`f()`

`   ↓`

`panic`

`   ↓`

`unwind`

`   ↓`

`setcsr(old)  ← jamás ejecutado`
```

`catch\_unwind` del exterior puede recuperar el control, pero **no retrocede mágicamente y ejecuta la instrucción saltada**. `catch\_unwind` efectivamente captura panics de unwinding, pero no sustituye una política RAII para recursos de estado. 

### Parche

```
`\#\[cfg(target\_arch = "x86\_64")\]`

`struct MxcsrGuard \{`

`    old: u32,`

`\}`


`\#\[cfg(target\_arch = "x86\_64")\]`

`impl Drop for MxcsrGuard \{`

`    \#\[inline(always)\]`

`    fn drop(&mut self) \{`

`        unsafe \{`

`            core::arch::x86\_64::\_mm\_setcsr(self.old);`

`        \}`

`    \}`

`\}`


`\#\[cfg(target\_arch = "x86\_64")\]`

`\#\[inline(always)\]`

`unsafe fn with\_ftz\_daz\<F, R\>(f: F) -\> R`

`where`

`    F: FnOnce() -\> R,`

`\{`

`    let old = core::arch::x86\_64::\_mm\_getcsr();`


`    core::arch::x86\_64::\_mm\_setcsr(old | 0x8040);`


`    let \_guard = MxcsrGuard \{ old \};`


`    f()`

`\}`
```

Aquí la restauración ya está asociada al lifetime del guard.

Y hay una segunda cuestión SOTA que no quiero perder: **FTZ/DAZ no es sólo “una optimización numérica”**. Es un cambio del entorno de ejecución del hilo. Si este FFI participa en un runtime con otros componentes ejecutándose en ese mismo hilo, debe existir una política explícita de aislamiento.

**Estado:** confirmado.


# 3. Triton: el OOB es matemáticamente reproducible

Código:

```
`self.n\_partials = (dim + self.block - 1) // self.block`

`self.n\_partials\_pow2 = triton.next\_power\_of\_2(self.n\_partials)`


`self.\_partials = torch.empty(`

`    self.n\_partials,`

`    dtype=torch.float32,`

`    device=device`

`)`
```

Para:

```
`D = 10000`

`BLOCK = 1024`


`ceil(10000 / 1024) = 10`

`next\_power\_of\_2(10) = 16`
```

Pero después:

```
`\_finalize\_inv\_norm\_kernel\[(1,)\](`

`    self.\_partials,`

`    self.\_inv\_norm,`

`    N=self.n\_partials\_pow2`

`)`
```

El kernel hace:

```
`offs = tl.arange(0, N)`

`mask = offs \< N`

`ps = tl.load(partial\_ptr + offs, mask=mask, other=0.0)`
```

Como `N=16`:

```
`mask = \[true ... true\] 16 veces`
```

No hay protección contra los índices 10..15.

La documentación de Triton es inequívoca: una posición con `mask=False` es la que no se carga. 

### Parche industrial

No basta con decir “cambia 16 por 10”.

Hay que distinguir:

```
`VALID\_N = 10`

`BLOCK\_N = 16`
```

Reservamos el tamaño físico completo:

```
`self.\_partials = torch.zeros(`

`    self.n\_partials\_pow2,`

`    dtype=torch.float32,`

`    device=device,`

`)`
```

Y:

```
`@triton.jit`

`def \_finalize\_inv\_norm\_kernel(`

`    partial\_ptr,`

`    inv\_norm\_ptr,`

`    VALID\_N: tl.constexpr,`

`    BLOCK\_N: tl.constexpr,`

`):`

`    offs = tl.arange(0, BLOCK\_N)`

`    mask = offs \< VALID\_N`


`    ps = tl.load(`

`        partial\_ptr + offs,`

`        mask=mask,`

`        other=0.0,`

`    )`


`    total = tl.sum(ps, axis=0)`

`    inv = tl.where(`

`        total \> 1e-24,`

`        tl.rsqrt(total),`

`        0.0,`

`    )`


`    tl.store(inv\_norm\_ptr, inv)`
```

Invocación:

```
`\_finalize\_inv\_norm\_kernel\[(1,)\](`

`    self.\_partials,`

`    self.\_inv\_norm,`

`    VALID\_N=self.n\_partials,`

`    BLOCK\_N=self.n\_partials\_pow2,`

`)`
```

Ahora:

```
`allocation = 16`

`logical elements = 10`

`mask = first 10 true + 6 false`
```

**Estado:** confirmado.


# 4. Y aquí aparece un segundo bug Triton que es más profundo

La normalización usa:

```
`self.\_partials`

`self.\_inv\_norm`
```

como scratch **compartido por todas las llamadas al objeto**.

El stream es compartido:

```
`self.stream = torch.cuda.Stream(...)`
```

Eso evita una parte de la carrera porque los kernels quedan serializados en ese stream.

Pero el contrato de `TwoPassNormalizer.run()` dice:

```
`"""x, out: f32 CUDA contiguous. Same stream del caller."""`
```

y en realidad no usa “el stream del caller”: las llamadas en `AsyncTritonIngestorV504` se ejecutan dentro de:

```
`with torch.cuda.stream(self.stream):`
```

Esto crea una arquitectura con un recurso scratch global que depende de que **toda llamada futura respete exactamente ese stream**.

Eso es extremadamente frágil.

### Solución mejor

El normalizador debe tener uno de estos contratos, no una mezcla:

**Modelo A — single-stream ownership**

```
`Normalizer -\> propietario exclusivo de stream + scratch`
```

y todas las operaciones pasan por él.

**Modelo B — scratch por ejecución**

```
`partials = torch.empty(`

`    self.n\_partials\_pow2,`

`    dtype=torch.float32,`

`    device=x.device,`

`)`

`inv\_norm = torch.empty(`

`    1,`

`    dtype=torch.float32,`

`    device=x.device,`

`)`
```

Es menos eficiente en allocations, así que para producción usaría un **workspace pool por stream**.

No cerraría esto con un parche de sintaxis; aquí hay una decisión de arquitectura.

**Estado:** hallazgo nuevo, no simplemente una repetición del OOB.


# 5. Buffer pool: aquí mi diagnóstico anterior era correcto, pero se puede demostrar mejor

Código:

```
`event.record()`

`...`

`await future`

`return output.clone()`

`finally:`

`    await self.\_release(idx)`
```

El problema es el orden temporal.

Imaginemos:

```
`STREAM A:`

`    normalize(output)`

`    event.record()`


`HOST:`

`    event.query() == true`


`DEFAULT/CALLER STREAM:`

`    clone(output)  ────────────────\>`


`HOST:`

`    release(idx)`


`STREAM A:`

`    nueva ingestión`

`    escribe output  \<────────────── potencial choque`
```

La documentación de PyTorch advierte que con streams no-default la sincronización y el lifetime deben gestionarse explícitamente; `record\_stream()` existe precisamente para informar al allocator de dependencias cruzadas. 

Aquí existe incluso un problema más específico: `record\_stream()` por sí solo **no resuelve necesariamente un pool de buffers propiedad de tu aplicación**, porque vuestro `\_outputs\[idx\]` no es un bloque que el allocator pueda considerar libre simplemente por registrarlo.

### Diseño mejor

Separar:

```
`GPU work complete`
```

de:

```
`consumer finished with slot`
```

Por ejemplo:

```
`with torch.cuda.stream(self.stream):`

`    staging.copy\_(cpu\_tensor, non\_blocking=True)`

`    self.normalizer.run(staging, output)`


`    result = output.clone()`


`    done = self.\_done\_events\[idx\]`

`    done.record(self.stream)`


`await self.\_wait\_event(done)`


`return result`
```

Eso sigue necesitando cuidado si `result` se consume desde otro stream, pero **el buffer pooled ya no vuelve a estar disponible mientras su copia está pendiente**.

Todavía mejor:

```
`slot state:`

`FREE`

`IN\_FLIGHT`

`READY\_FOR\_CLONE`

`RETIRED`
```

No un simple:

```
`\_free: list\[int\]`
```

**Estado:** confirmado.


# 6. Hay una mentira peligrosa en el nombre `write\_slab\_atomic()`

Código:

```
`with self.\_lock:`

`    seq\[0\] += 1`

`    np.copyto(...)`

`    seq\[0\] += 1`
```

El nombre dice:

```
`atomic`
```

Pero no lo es.

El `threading.Lock()` protege únicamente los hilos de **este objeto/proceso Python**.

No protege:

```
`Proceso A`

`Proceso B`

`Proceso C`

`Rust`

`C++`

`otro proceso que abrió /dev/shm/POLYDIM\_SLAB\_X`
```

Y el `seq\[0\] += 1` es una operación Python/Numpy sobre memoria compartida, no una operación C11/Rust `AtomicU64`.

Aquí hay que separar tres conceptos:

```
`mutual exclusion`

`memory ordering`

`atomicity`
```

El código no implementa de manera explícita los tres entre procesos.

### Solución

El Python debe dejar de modificar directamente `seq` como si fuera un átomo.

El header compartido debe tener un writer API nativo:

```
`\#\[repr(C, align(64))\]`

`pub struct ShmHeader \{`

`    pub seq: AtomicU64,`

`    // ...`

`\}`
```

y:

```
`pub unsafe extern "C" fn pmtp\_seqlock\_begin\_write(...)`
```

ser el **único** mecanismo permitido para comenzar la escritura.

Python sólo debería pedir:

```
`slot = native\_begin\_write(...)`
```

y escribir el payload.

**Estado:** confirmado.


# 7. Pero el SeqLock Rust también tiene una falla estructural

Esto:

```
`l.seq.fetch\_add(1, Ordering::AcqRel);`

`let old\_turn =`

`    l.write\_turn.fetch\_xor(1, Ordering::AcqRel) & 1;`
```

no impide:

```
`Writer A                    Writer B`


`seq: 0 → 1`


`                            seq: 1 → 2`
```

y, peor:

```
`A decide buffer X`

`                            B decide buffer X`

`A empieza a escribir X`

`                            B empieza a escribir X`
```

El SeqLock clásico permite múltiples lectores y **un único escritor**. Aquí no existe CAS que reserve al writer.

### Solución

Añadir estado explícito:

```
`const WRITER\_HELD: u64 = 1 \<\< 63;`
```

o, mejor aún, un `AtomicU32` de ownership independiente.

Ejemplo:

```
`pub fn try\_begin\_write(lock: &NodeSignatureSeqLock) -\> Result\<u32, i32\> \{`

`    if lock.writer.compare\_exchange(`

`        0,`

`        1,`

`        Ordering::Acquire,`

`        Ordering::Relaxed,`

`    ).is\_err() \{`

`        return Err(-2);`

`    \}`


`    let old\_turn = lock.write\_turn.load(Ordering::Relaxed);`

`    let new\_turn = old\_turn ^ 1;`


`    lock.seq.fetch\_add(1, Ordering::Release);`


`    Ok(new\_turn)`

`\}`
```

Y el escritor tiene que usar **el turno reservado**, no volver a inferirlo más tarde desde `write\_turn`.

Eso elimina una clase entera de carreras.

**Estado:** confirmado.


# 8. `β₁` puede ser matemáticamente válido pero no caber en la API

Código:

```
`let betti = (num\_edges as i64)`

`          - (num\_vertices as i64)`

`          + (components as i64);`


`betti as i32`
```

Se permite:

```
`num\_vertices \<= 1 \<\< 20`
```

Para un grafo simple completo:

```
`E = n(n-1)/2`
```

con `n = 1,048,576`:

```
`E ≈ 549,755,289,600`
```

Eso no cabe en `i32`.

Por lo tanto tenemos una contradicción interna:

```
`input legal según validación`

`        ↓`

`resultado matemáticamente legal`

`        ↓`

`API i32 incapaz de representarlo`
```

En Rust, el cast entero moderno tiene semántica definida de saturación/truncado según el tipo de conversión; en ningún caso convierte `i32` en una representación correcta del β₁ real. La API está mal tipada para su dominio.

### Solución

Cambiar:

```
`-\> i64`
```

y:

```
`restype = ctypes.c\_int64`
```

O establecer:

```
`num\_vertices \<= 65536`
```

si verdaderamente se necesita `i32`.

Para una arquitectura de alto dimensionalidad prefiero **ensanchar la API**, no mutilar el dominio.

**Estado:** confirmado.


# 9. `phase99` tiene un bug matemático más feo que el anterior

El código:

```
`let correction =`

`    ((centroid\_dot + gamma\_f64)`

`    / (gamma\_f64 \* gamma\_f64 + 1e-8)) as f32;`


`u\_i\[i\] -= correction \* local\[i\];`
```

Si la restricción es:

```
`\<local, u\_new\> \>= -γ`
```

y proyectamos:

```
`u\_new = u - α local`
```

entonces:

```
`\<local,u\> - α ||local||² = -γ`
```

por lo tanto:

```
`α = (\<local,u\> + γ) / ||local||²`
```

No:

```
`α = (...) / γ²`
```

Con:

```
`γ = 0.1`

`||local|| = 1`
```

el denominador usado actualmente es:

```
`0.01`
```

cuando debería ser aproximadamente:

```
`1`
```

Eso es un factor **100**.

### Parche

```
`let local\_norm\_sq = \{`

`    let mut s = 0.0f64;`

`    for i in 0..d\_dim \{`

`        let x = local\[i\] as f64;`

`        s += x \* x;`

`    \}`

`    s`

`\};`


`if !local\_norm\_sq.is\_finite() || local\_norm\_sq \<= 1e-20 \{`

`    return -2;`

`\}`


`if centroid\_dot \< -gamma\_f64 \{`

`    let correction =`

`        ((centroid\_dot + gamma\_f64) / local\_norm\_sq) as f32;`


`    for i in 0..d\_dim \{`

`        u\_i\[i\] -= correction \* local\[i\];`

`    \}`

`\}`
```

**Estado:** confirmado matemáticamente.


# 10. El fallo de NaN/Inf no es sólo “falta un if”

Aquí tenemos una cadena sistémica.

### Router

```
`let denom = (final\_nt \* final\_ns).sqrt();`


`let cos = if denom \> 1e-15 \{`

`    (final\_dot / denom) as f32`

`\} else \{`

`    0.0`

`\};`
```

Si los datos contienen NaN:

```
`denom = NaN`

`NaN \> 1e-15 = false`

`cos = 0`
```

Es decir, **datos corruptos se transforman silenciosamente en un valor aparentemente válido**.

Eso es peor que fallar.

### Horizontal Lift

```
`let det = a \* d - b \* b;`


`if det.abs() \< 1e-12 \{`

`    return -3;`

`\}`
```

Si `det = NaN`:

```
`NaN \< 1e-12 → false`
```

y se sigue ejecutando.

### Phase 99

```
`if norm\_sq \> 1e-12 \{`

`   ...`

`\}`
```

Si:

```
`norm\_sq = NaN`
```

también:

```
`false`
```

y retorna `0`.

Tenemos entonces un patrón común:

```
`NaN`

` ↓`

`comparación false`

` ↓`

`la función continúa`

` ↓`

`retorna éxito`

` ↓`

`el NaN se propaga`
```

### Este es el patrón industrial que quiero eliminar

Crear una política única:

```
`\#\[inline(always)\]`

`fn finite\_f32(x: f32) -\> bool \{`

`    x.is\_finite()`

`\}`
```

Antes de entrar en cada kernel lógico:

```
`if !delta\_x.is\_finite() || !delta\_y.is\_finite() \{`

`    return -10;`

`\}`
```

y para tensores:

```
`for &x in tensor.iter() \{`

`    if !x.is\_finite() \{`

`        return -11;`

`    \}`

`\}`
```

Para hot paths muy exigentes, podemos hacer una variante SIMD/AVX y una política configurable:

```
`STRICT:`

`    NaN/Inf =\> error`


`FAST:`

`    assume finite`


`DEBUG:`

`    assert finite`
```

Pero **no una política accidental** basada en cómo compara Rust una NaN.

**Estado:** confirmado.


# 11. La API Python promete mutación y puede mentir

Esto:

```
`t = np.ascontiguousarray(tensor, dtype=np.float32)`
```

puede devolver:

```
`tensor mismo`
```

o:

```
`copia nueva`
```

Por ejemplo:

```
`tensor.dtype == float64`
```

o:

```
`tensor.flags\["C\_CONTIGUOUS"\] == False`
```

Entonces:

```
`Python caller`

`    tensor A`

`       ↓`

`ascontiguousarray`

`       ↓`

`tensor B`

`       ↓`

`Rust modifica B`

`       ↓`

`A permanece intacto`
```

Pero el API se documenta como:

```
`tensor: Vector latente mutable`
```

Eso es un bug de contrato.

### Parche estricto

No aceptar silenciosamente copias:

```
`def \_require\_f32\_c\_contig(a: np.ndarray, name: str) -\> np.ndarray:`

`    if a.dtype != np.float32:`

`        raise TypeError(f"\{name\}.dtype must be float32")`

`    if not a.flags.c\_contiguous:`

`        raise ValueError(f"\{name\} must be C-contiguous")`

`    return a`
```

Después:

```
`t = \_require\_f32\_c\_contig(tensor, "tensor")`

`j = \_require\_f32\_c\_contig(jacobian, "jacobian")`
```

Y entonces el contrato:

```
`Rust realmente modifica el buffer del caller`
```

queda demostrablemente cierto.

Alternativa: copiar y devolver el resultado, pero entonces el API deja de llamarse mutante.

**Estado:** confirmado.


# 12. El `self\_test()` de Triton todavía tiene una debilidad importante

Actualmente:

```
`x = torch.randn(...)`
```

y:

```
`assert abs(norm - 1.0) \< 1e-3`
```

Eso prueba solamente un caso aleatorio.

No prueba:

```
`zero vector`

`all zeros`

`very large`

`very small`

`subnormal`

`NaN`

`Inf`

`negative`

`repeated invocation`

`concurrent invocation`

`D exact multiple of BLOCK`

`D one less than BLOCK`

`D one more than BLOCK`

`D \> one block`

`D non power of 2`
```

Y justamente acabamos de encontrar un bug que un solo vector aleatorio no garantiza detectar.

### Harness mínimo que sí empieza a ser SOTA

```
`def adversarial\_inputs(dim: int):`

`    yield "random", torch.randn(dim, dtype=torch.float32)`

`    yield "ones", torch.ones(dim, dtype=torch.float32)`

`    yield "zeros", torch.zeros(dim, dtype=torch.float32)`


`    x = torch.full((dim,), 1e-30, dtype=torch.float32)`

`    yield "tiny", x`


`    x = torch.full((dim,), 1e30, dtype=torch.float32)`

`    yield "huge", x`


`    x = torch.zeros(dim, dtype=torch.float32)`

`    x\[0\] = float("nan")`

`    yield "nan", x`


`    x = torch.zeros(dim, dtype=torch.float32)`

`    x\[0\] = float("inf")`

`    yield "inf", x`
```

Y para dimensiones:

```
`for dim in (`

`    1,`

`    31,`

`    32,`

`    33,`

`    1023,`

`    1024,`

`    1025,`

`    9999,`

`    10000,`

`    10001,`

`    16384,`

`):`

`    ...`
```

Esto empieza a cerrar **clases de errores**, no ejemplos.


# 13. El C++ “hardware gateway” no interroga realmente el hardware desde Python

Esto es inequívoco:

```
`def \_query\_hardware(self):`

`    self.\_hw\_alignment = 64`
```

No se llama:

```
`pmtp\_cpp\_query\_alignment\_requirement()`
```

Así que el supuesto:

```
`software no asume, software interroga`
```

es falso en la integración Python.

La prueba:

```
`ok = a in (16, 32, 64)`
```

puede pasar para **cualquier valor hardcodeado válido**.

Mismo problema aquí:

```
`cl = 64`
```

No consulta C++.

Y aquí:

```
`ping = 1`
```

No llama al símbolo.

Por tanto:

```
`A3 PASS`

`A5 PASS`

`A6 PASS`
```

no son pruebas de hardware/FFI. Son pruebas de:

```
`"64 pertenece a \{16,32,64\}"`

`"64 es potencia de dos"`

`"1 == 1"`
```

### Las pruebas deben ser reales

```
`self.\_cpp\_lib.pmtp\_cpp\_query\_alignment\_requirement()`
```

y:

```
`self.\_cpp\_lib.pmtp\_cpp\_query\_cache\_line\_size()`
```

y:

```
`self.\_cpp\_lib.pmtp\_cpp\_zero\_drift\_ping()`
```

con `argtypes/restype` definidos.

**Estado:** confirmado.


# 14. Y apareció otro defecto de integración

`\_bind\_cpp\_ffi()` es:

```
`def \_bind\_cpp\_ffi(self):`

`    """Declara las firmas FFI del gateway C++ V505."""`

`    pass`
```

Esto significa que **el C++ no tiene binding Python**.

Entonces incluso corrigiendo `\_query\_hardware()`, primero hay que crear los bindings.

```
`def \_bind\_cpp\_ffi(self):`

`    if self.\_cpp\_lib is None:`

`        raise RuntimeError("C++ kernel unavailable")`


`    lib = self.\_cpp\_lib`


`    lib.pmtp\_cpp\_query\_alignment\_requirement.restype = ctypes.c\_int`

`    lib.pmtp\_cpp\_query\_alignment\_requirement.argtypes = \[\]`


`    lib.pmtp\_cpp\_query\_cache\_line\_size.restype = ctypes.c\_int`

`    lib.pmtp\_cpp\_query\_cache\_line\_size.argtypes = \[\]`


`    lib.pmtp\_cpp\_zero\_drift\_ping.restype = ctypes.c\_int`

`    lib.pmtp\_cpp\_zero\_drift\_ping.argtypes = \[\]`


`    lib.pmtp\_cpp\_validate\_tensor\_alignment.restype = ctypes.c\_int`

`    lib.pmtp\_cpp\_validate\_tensor\_alignment.argtypes = \[`

`        ctypes.c\_void\_p,`

`        ctypes.c\_uint64,`

`        ctypes.c\_int,`

`    \]`
```

Y:

```
`def \_query\_hardware(self):`

`    if self.\_cpp\_lib is None:`

`        raise RuntimeError("C++ hardware gateway unavailable")`


`    alignment = self.\_cpp\_lib.pmtp\_cpp\_query\_alignment\_requirement()`


`    if alignment not in (16, 32, 64):`

`        raise RuntimeError(`

`            f"Unsupported alignment returned by C++: \{alignment\}"`

`        )`


`    self.\_hw\_alignment = alignment`
```

**Estado:** confirmado.


# 15. El build tiene un problema de reproducibilidad, no sólo de nombres

Hay tres capas:

```
`archivo fuente`

`       ↓`

`build`

`       ↓`

`nombre del artefacto`

`       ↓`

`loader`
```

Actualmente cada capa usa una convención diferente:

```
`Rust:`

`kernel\_rust\_v505.rs.txt`


`README:`

`kernel\_rust\_v505.rs`


`Python:`

`pmtp\_kernel\_V505.dll`


`C++:`

`kernel\_cpp\_v505.cpp.txt`


`README:`

`pmtp\_cpp\_V505.dll`


`Python:`

`pmtp\_kernel\_v505.dll`
```

Esto no es un detalle administrativo.

En producción necesitamos poder afirmar:

```
`source commit X`

`→ build recipe X`

`→ hash binary X`

`→ loader name X`

`→ runtime ABI X`
```

### Quiero un contrato único

Por ejemplo:

```
`src/`

`  kernel\_rust.rs`

`  kernel\_cpp.cpp`

`  polydim.py`


`build/`

`  Windows-x86\_64/`

`  Linux-x86\_64/`


`artifacts/`

`  Windows:`

`    pmtp\_kernel.dll`


`  Linux:`

`    libpmtp\_kernel.so`
```

Y el build genera además:

```
`pmtp\_kernel.json`
```

con:

```
`\{`

`  "version": "505",`

`  "git\_sha": "...",`

`  "rustc": "...",`

`  "compiler": "...",`

`  "target": "...",`

`  "abi": 1`

`\}`
```

No es “DevOps de adorno”: reduce el espacio de estados incompatibles.


# 16. `ctypes.\_align\_=128` sí está bien; aquí retiro una crítica que sería falsa

Este punto quiero dejarlo inequívoco.

El código:

```
`\_align\_ = 128`

`\_fields\_ = \[...\]`
```

es una capacidad real de `ctypes`, y la documentación actual dice que `\_align\_` permite aumentar la alineación de la estructura y debe establecerse antes de `\_fields\_`. 

Además lo ejecuté en este entorno:

```
`sizeof(ShmHeader) = 128`

`alignment = 128`
```

Por lo tanto:

**este punto concreto NO es un bug actual.**

Lo que sí sigue siendo un problema es afirmar que eso demuestra compatibilidad completa con Rust/C, porque sólo hemos validado el lado Python.

Eso es exactamente la diferencia entre:

```
`"mi struct Python está bien"`
```

y:

```
`"el ABI binario completo está demostrado"`
```


# 17. Otra corrección importante: “C++ compila” depende de cómo lo invoquemos

Probé:

```
`g++ -std=c++20 ... kernel\_cpp\_v505.cpp.txt`
```

y g++ trata `.txt` como archivo que no debe compilar automáticamente.

Eso hace que el comando del README sea incorrecto **si el archivo conserva `.txt`**.

Pero al usar:

```
`g++ -x c++ ...`
```

sí compila.

Por tanto la formulación correcta es:

```
`❌ "el código C++ no compila"`
```

No.

La formulación correcta es:

```
`✅ "el comando de build documentado no compila ese archivo con extensión .txt sin especificar el lenguaje."`
```

Esa precisión también elimina una posible falsa acusación de mi auditoría anterior.


# 18. El siguiente ciclo debe cambiar de enfoque

Hasta aquí tenemos una evidencia importante.

No necesitamos seguir haciendo:

```
`10 bugs`

`→ usuario corrige`

`→ 10 bugs nuevos`

`→ usuario corrige`
```

Tenemos que pasar a **invariantes verificables**.

### Invariante I — memoria/ownership

Debe ser imposible tener:

```
`pointer válido`

`pero allocation inválida`
```

### Invariante II — FFI

Cada función debe tener:

```
`ABI`

`types`

`alignment`

`length`

`ownership`

`lifetime`

`error semantics`
```

definidos.

### Invariante III — concurrency

Para cada dato compartido:

```
`who writes?`

`who reads?`

`what synchronizes?`

`what memory ordering?`

`what lifetime?`
```

### Invariante IV — numerics

Cada función debe especificar:

```
`NaN`

`Inf`

`subnormal`

`zero norm`

`overflow`

`underflow`

`conditioning`
```

### Invariante V — GPU streams

Cada allocation debe responder:

```
`which stream produced it?`

`which stream consumes it?`

`when can it be reused?`
```

### Invariante VI — build/ABI

Debe existir una única fuente de verdad para:

```
`source → compiler → ABI → library → loader`
```

### Invariante VII — tests

Un `PASS` sólo vale si realmente ejecutó el subsistema que afirma validar.


## Veredicto de este ciclo

**No, V505 todavía no está industrialmente cerrada.**

Pero también **no voy a inventar problemas para seguir acumulando números**.

Ya tenemos varias cosas que ahora sí están en una categoría distinta:

**Confirmados por código/evidencia:**

```
`RDMA local\_addr/lkey`

`MXCSR panic path`

`Triton OOB`

`Triton scratch contract`

`GPU buffer lifetime`

`Python shared-memory atomicity`

`Rust multi-writer SeqLock`

`β1 return type`

`CBF denominator`

`NaN/Inf silent-success paths`

`Python fake mutation`

`fake hardware tests`

`missing C++ bindings`

`build/loader inconsistency`
```

Y hemos retirado/precisado dos afirmaciones que no debía dejar como absolutas:

```
`"ibv\_send\_wr de 80 B =\> necesariamente RDMA roto"`

`        → demasiado fuerte`


`"C++ no compila"`

`        → incorrecto; falla el comando documentado para .txt`
```

Eso es exactamente el tipo de control anti-alucinación que pediste.

La siguiente capa que voy a atacar ya no es “otro bug aislado”: es **hacer un contrato FFI único Rust ↔ C/C++ ↔ Python ↔ Dart y comprobar función por función tamaños, ownership, lifetime, alignment, lengths, error codes y concurrencia**. Ahí es donde podemos empezar a acercarnos realmente a esas “1.000 líneas perfectas”, en vez de seguir jugando al whack-a-mole.

algo mas que elaborar? alguna idea. alguna info sota. Como ai que mas deveria tener? 

Sí. Y creo que hay una idea bastante más importante que seguir excavando bugs individuales: **convertir POLYDIM en un sistema con una especificación verificable de extremo a extremo**, de modo que una nueva ronda no dependa de “a ver qué error descubre la IA esta vez”.

Para llevarlo de “matemáticamente SOTA en papel” a “industrialmente inquebrantable en silicio real”, yo añadiría estas capas:

### 1. Un *system contract* formal

Para cada función pública, definir explícitamente:

```
`INPUT`

`  dtype`

`  shape`

`  alignment`

`  contiguity`

`  valid range`


`MEMORY`

`  ownership`

`  lifetime`

`  aliasing`

`  mutability`


`CONCURRENCY`

`  writer`

`  readers`

`  lock`

`  ordering`

`  stream`


`NUMERICS`

`  NaN`

`  Inf`

`  zero`

`  underflow`

`  overflow`

`  conditioning`


`OUTPUT`

`  dtype`

`  range`

`  error semantics`
```

Esto evita el problema actual de que Rust, Python, C++ y GPU puedan tener **cuatro interpretaciones ligeramente diferentes del mismo objeto**.


### 2. *Differential testing*

Esto es muy SOTA y, para POLYDIM, probablemente una de las mejores inversiones.

Tener dos implementaciones:

```
`REFERENCE`

`    Python / NumPy / float64`

`         ↓`

`        y\_ref`


`OPTIMIZED`

`    Rust / C++ / Triton / SIMD`

`         ↓`

`        y\_fast`


`compare(y\_ref, y\_fast)`
```

No se valida simplemente:

```
`assert result \> 0`
```

sino algo del estilo:

```
`np.testing.assert\_allclose(`

`    y\_fast,`

`    y\_ref,`

`    rtol=1e-5,`

`    atol=1e-7,`

`)`
```

y, para invariantes geométricos:

```
`||projection(x)|| \<= tolerance`

`symmetry(A) ≈ symmetry(Aᵀ)`

`norm(normalized(x)) ≈ 1`

`determinant/inverse consistency`

`β₁ \>= 0`
```

Eso permite descubrir errores que jamás aparecerían con tests unitarios tradicionales.


### 3. *Property-based testing / fuzzing*

En vez de decidir manualmente 20 casos, generar miles/millones de estados válidos y casi-válidos.

Por ejemplo:

```
`@given(`

`    dim=st.integers(1, 100000),`

`    scale=...`

`)`

`def test\_normalizer(dim, scale):`

`    ...`
```

Pero yo iría más lejos:

```
`valid`

`near-boundary`

`degenerate`

`pathological`

`adversarial`
```

Especialmente:

```
`D = BLOCK-1`

`D = BLOCK`

`D = BLOCK+1`


`alignment = exact`

`alignment = misaligned`


`size = 0`

`size = 1`

`size = max`

`size = max+1`


`norm = 0`

`norm ≈ epsilon`

`norm = huge`
```

Los bugs de GPU y SIMD suelen vivir exactamente en los bordes.


### 4. *Sanitizer matrix*

Esto debería ser obligatorio antes de declarar “industrial”.

C/C++:

```
`ASan`

`UBSan`

`TSan`

`LSan`
```

y, cuando corresponda:

```
`MSan`
```

Rust:

```
`Miri`

`ASan/UBSan mediante configuración compatible`

`cargo-fuzz`

`loom`
```

La parte especialmente interesante es **Loom** para modelos de concurrencia Rust: permite explorar interleavings que una prueba normal casi nunca alcanza.

Para POLYDIM, eso puede descubrir carreras del SeqLock que una ejecución de 1.000.000 iteraciones puede no revelar.


### 5. GPU: no sólo correctness, también herramientas de memoria

Para CUDA/Triton pondría una batería que intente demostrar:

```
`no OOB`

`no race`

`no stale read`

`no use-after-reuse`

`correct stream dependency`

`correct synchronization`
```

Y haría pruebas deliberadas:

```
`stream A produces`

`stream B consumes`

`stream C reuses`
```

porque muchos bugs GPU no son:

```
`kernel incorrecto`
```

sino:

```
`kernel correcto`

`+`

`lifetime incorrecto`

`=`

`resultado incorrecto`
```


### 6. Un *numerical torture suite*

Esta capa me parece imprescindible en una arquitectura como POLYDIM.

No basta:

```
`NaN`

`Inf`
```

Hay que probar:

```
`+0`

`-0`


`smallest normal`

`largest normal`


`subnormal positive`

`subnormal negative`


`nextafter(x, 0)`

`nextafter(x, +inf)`


`catastrophic cancellation`


`ill-conditioned matrices`


`almost-singular matrices`


`huge dynamic range`
```

Y además comparar:

```
`float32`

`float64`

`long double / reference`
```

para encontrar dónde la matemática ideal empieza a divergir de la física de la máquina.


### 7. Presupuesto formal de error

Este es un salto importante.

Para cada algoritmo:

```
`error\_total`

`=`

`rounding\_error`

`+`

`conditioning\_error`

`+`

`approximation\_error`

`+`

`parallel\_reduction\_error`

`+`

`communication\_error`
```

Y definir algo como:

```
`ERROR\_BUDGET\_NORMALIZER = 1e-5`

`ERROR\_BUDGET\_CBF        = 1e-6`

`ERROR\_BUDGET\_ROUTER     = 1e-5`
```

Luego cada optimización tiene que demostrar:

```
`before \<= budget`

`after  \<= budget`
```

Eso evita una situación muy peligrosa:

> “es más rápido y parece correcto”.


### 8. Modelo de ownership como gráfico

Yo haría un diagrama formal:

```
`Python ndarray`

`      │`

`      ▼`

`   FFI borrow`

`      │`

`      ▼`

` Rust slice`

`      │`

`      ├────► SIMD`

`      │`

`      ├────► C++`

`      │`

`      └────► CUDA/Triton`

`                 │`

`                 ▼`

`              GPU buffer`
```

Cada flecha debe tener una regla:

```
`borrowed`

`owned`

`shared`

`immutable`

`mutable`

`stream-owned`

`thread-owned`

`process-shared`
```

Y una duración:

```
`t0 ---- borrow ---- t1`
```

Esto es especialmente útil para los pools.


### 9. ABI fingerprint

Esta sería una de mis adiciones favoritas.

En build time generar:

```
`ABI\_FINGERPRINT`
```

basado en:

```
`sizeof`

`alignof`

`offsetof`

`enum values`

`integer widths`

`pointer widths`

`version`

`compiler`

`target`
```

Por ejemplo:

```
`\_Static\_assert(sizeof(struct PmtpHeader) == 128, "ABI");`

`\_Static\_assert(offsetof(struct PmtpHeader, seq) == 64, "ABI");`
```

Rust:

```
`const \_: () = assert!(size\_of::\<ShmHeader\>() == 128);`

`const \_: () = assert!(align\_of::\<ShmHeader\>() == 128);`
```

Python:

```
`assert ctypes.sizeof(ShmHeader) == ABI\_EXPECTED\_SIZE`

`assert ctypes.alignment(ShmHeader) == ABI\_EXPECTED\_ALIGNMENT`
```

Pero todavía mejor:

```
`Rust ABI fingerprint`

`C ABI fingerprint`

`Python ABI fingerprint`
```

y la aplicación se niega a arrancar si no coinciden.

Eso convierte muchos posibles UB en:

```
`startup failure`
```

que es exactamente lo que queremos.


### 10. Chaos engineering

Para llegar realmente a “inquebrantable”, hay que **romperlo deliberadamente**.

Por ejemplo:

```
`kill writer`

`kill reader`

`SIGSTOP writer`

`SIGSTOP reader`


`delay DMA completion`

`randomize scheduling`

`drop RDMA completion`

`duplicate packet`

`reorder packet`

`restart process`

`exhaust memory`

`exhaust GPU memory`

`close device`

`device disappears`
```

Luego comprobar:

```
`never corrupts memory`

`never deadlocks permanently`

`never returns forged success`

`recovers or fails deterministically`
```

Eso ya es mucho más cercano a ingeniería industrial real que a un benchmark.


## 11. Modelo de fallo explícito

Cada función debería tener una tabla:

```
`SUCCESS`

`INVALID\_ARGUMENT`

`INVALID\_ALIGNMENT`

`INVALID\_SHAPE`

`NONFINITE\_INPUT`

`OUT\_OF\_MEMORY`

`DEVICE\_LOST`

`TIMEOUT`

`CONCURRENT\_ACCESS`

`ABI\_MISMATCH`

`INTERNAL\_ERROR`
```

Y prohibir:

```
`error → return 0`
```

cuando `0` también significa éxito.

Especialmente peligroso en kernels matemáticos.


## 12. *Fail closed*

Una regla global para POLYDIM:

> **Ante incertidumbre, no producir un resultado aparentemente válido.**

Ejemplo actual:

```
`NaN`

` ↓`

`comparison false`

` ↓`

`fallback 0`

` ↓`

`SUCCESS`
```

Debería ser:

```
`NaN`

` ↓`

`NONFINITE\_INPUT`

` ↓`

`ERROR`
```

Eso simplifica muchísimo el razonamiento de seguridad.


## 13. Observabilidad de producción

No sólo:

```
`latency = 20 µs`
```

Sino:

```
`latency p50`

`latency p95`

`latency p99`

`latency p99.9`


`allocation count`

`allocation bytes`

`pool misses`

`pool reuse`

`stream waits`

`kernel launches`

`RDMA completions`

`retry count`

`NaN count`

`Inf count`

`fallback count`

`ABI version`

`hardware fingerprint`
```

Y crucialmente:

```
`why was fallback selected?`
```

Porque un sistema industrial debe explicar **por qué** tomó la ruta lenta.


## 14. Reproducibilidad bit a bit

Hay que decidir explícitamente si POLYDIM exige:

```
`numerically equivalent`
```

o:

```
`bitwise reproducible`
```

Son cosas diferentes.

Con reducciones paralelas:

```
`(a+b)+c`
```

puede no ser igual a:

```
`a+(b+c)`
```

Esto importa muchísimo cuando se cambia:

```
`CPU`

`SIMD width`

`GPU`

`thread count`

`compiler`

`optimization level`
```


## 15. Compiler adversarial matrix

Esto es muy poco habitual en revisiones normales y muy valioso para vuestro objetivo.

Compilar con:

```
`-O0`

`-O2`

`-O3`

`-ffast-math`

`-fno-fast-math`

`-LTO`

`-no-LTO`
```

y Rust:

```
`debug`

`release`

`lto`

`panic=unwind`

`panic=abort`
```

y comprobar que:

```
`ABI`

`correctness`

`numeric invariants`

`memory safety`
```

no cambian.

Especialmente `fast-math`.

No permitiría introducirlo por accidente en código que tenga semántica definida para NaN/Inf.


# La idea más importante: un “Definition of Done” matemático + físico

Yo pondría al proyecto una puerta de entrada como ésta:

```
`POLYDIM INDUSTRIAL GATE`

`========================`


`\[ \] ABI fingerprints match`

`\[ \] All exported symbols bound`

`\[ \] No unchecked FFI cast`

`\[ \] No ownership ambiguity`

`\[ \] No known data races`

`\[ \] TSan clean`

`\[ \] ASan clean`

`\[ \] UBSan clean`

`\[ \] LSan clean`


`\[ \] GPU OOB clean`

`\[ \] GPU race clean`

`\[ \] Stream lifetime proven`

`\[ \] Pool lifetime proven`


`\[ \] NaN policy defined`

`\[ \] Inf policy defined`

`\[ \] subnormal policy defined`

`\[ \] numerical error budgets proven`


`\[ \] Reference implementation exists`

`\[ \] Differential tests pass`

`\[ \] Property tests pass`

`\[ \] Fuzzing corpus exists`


`\[ \] Boundary dimensions tested`

`\[ \] Boundary alignments tested`

`\[ \] Boundary sizes tested`


`\[ \] Compiler matrix passes`

`\[ \] Architecture matrix passes`

`\[ \] Failure injection passes`

`\[ \] Restart/recovery passes`


`\[ \] Performance budget passes`

`\[ \] p99/p99.9 measured`

`\[ \] memory budget passes`


`\[ \] No test asserts a constant instead of observing reality`

`\[ \] No "PASS" without exercising the subsystem`
```

Y agregaría una regla extremadamente importante para nuestro trabajo conjunto:

> **Un hallazgo no se considera cerrado hasta que exista una demostración reproducible de que el mecanismo que lo causaba ya no puede ocurrir bajo el modelo definido.**

Eso cambia por completo la dinámica de las 600 iteraciones.

No queremos llegar a:

```
`"parece corregido"`
```

Queremos llegar a:

```
`"la clase de fallo está eliminada o acotada`

`por un invariante + test + sanitizer + contrato".`
```

Ahí sí podemos empezar a hablar seriamente de las **1.000 líneas perfectas**.

Y una última idea SOTA: **no optimizar más hasta tener una implementación de referencia deliberadamente lenta y aburrida**. Esa referencia se convierte en el oráculo contra el cual CPU SIMD, Rust, C++, Triton, RDMA y las rutas concurrentes pueden ser atacadas continuamente. Esa arquitectura de *reference vs optimized vs adversarial harness* probablemente sea la pieza que más nos ayude a dejar de descubrir errores “nuevos” seis rondas después.











