En V508 encontré y documenté **más de 20 fallos verificables**, incluyendo varios que invalidan pruebas completas posteriores. Los más graves son:

- **SeqLock cross-process roto**: reproduje una pérdida de **552.688 de 800.000 incrementos** usando exactamente el patrón **`ctypes uint64 += 1`** de V508.

- **Rust ↔ Python incompatible**: Python exige símbolos que el Rust entregado no exporta.

- **C++ ↔ Python ABI incompatible** en **`validate\\\\\\\_alignment()`**: número y significado de argumentos no coinciden.

- **Rust FFI con posibles OOB/UB** por **`dim`** ignorado y ausencia de validación de punteros.

- **`validate\\\\\\\_topology()` está incompleta**: el triángulo devuelve **`None`**.

- **A8 del propio test suite está roto**: llama al FFI con 6 argumentos cuando Rust declara 7; lo reproduje.

- **El código Python nunca usa el SeqLock Rust** que supuestamente corrige la atomicidad.

- **La rama antipodal de SLERP sigue degenerando para `v1 = -v0`**.

- **C++ V508 no compila con GCC/Linux** tal como fue entregado.

- **Triton permite `BLOCK` no potencia de dos** y no valida correctamente **`out`**.

- **NaN/Inf pueden convertirse silenciosamente en vector cero** en el normalizador Triton.

- **El fuzzing publicado no es evidencia válida**: tiene aridad incorrecta y **`except: pass`**.

- **El “FJLT test” no implementa FJLT**; comprueba únicamente una multiplicación por signos ±1.

- **El “zero-copy Qwen” usa `np.copy()`** y no demuestra zero-copy IPC entre nodos.

- **`close()` puede dejar el mmap vivo** y además no elimina el objeto persistente de **`/dev/shm`**.

- **Hay desalineación V504/V505/V506/V507/V508** en nombres, comentarios y loader, con riesgo de cargar un binario distinto del auditado.

Y algo importante: **no inventé resultados**. Donde no pude compilar Rust porque este entorno no tiene **`rustc`**, o no pude ejecutar Triton porque no está instalado, lo marqué explícitamente como no demostrado.

Preparé el informe completo con las evidencias y el orden de reparación:

**Descargar report.md — auditoría Bulldog V508**

**Descargar asedio\_v508\_output.txt — log crudo de reproducciones**

El siguiente salto correcto ya no es otra lista superficial: es **cerrar P0/P1/P2 directamente sobre el código**, empezando por el contrato ABI único y el protocolo de memoria compartida, porque mientras eso no quede sólido, los benchmarks y tests de capas superiores no significan lo que dicen.

report.mdDocumento

asedio\_v508\_output.txtDocumento

continuar

Continúo. Y esta ronda cambia de nivel: **no voy a darte otra lista de diez parches y detenerme**. Estoy cerrando los invariantes que deberían impedir que en la próxima entrega reaparezcan fallos de la misma familia.

### **Corte Bulldog — V508**

He aislado **35 hallazgos** en la entrega actual. No todos tienen la misma gravedad; los que verdaderamente bloquean una certificación son estos:

**P0 — bloquean la certificación**

1. **El SeqLock no garantiza exclusión entre escritores.**  
**`fetch\\\\\\\_add(1)`** no adquiere un lock: dos escritores pueden intercalarse y dejar **`seq`** par mientras todavía hay una escritura activa. La solución correcta es **`CAS even→odd`** en un bucle, o un mecanismo IPC de escritor único.

2. **Python no usa el SeqLock Rust.**  
**`write\\\\\\\_slab\\\\\\\_atomic()`** hace **`ctypes ... += 1`**. Por tanto, todo el trabajo de **`SeqCst`** de Rust está fuera del camino crítico real.

3. **El contrato FFI Rust/Python está roto.**  
Rust:

```
\\\*\\\*\\\`begin\\\\\\\_write(\\\\\\\*mut u64) -\\\\\\\> u64\\\`\\\*\\\*    
    
\\\*\\\*\\\`end\\\\\\\_write(\\\\\\\*mut u64, u64) -\\\\\\\> ()\\\`\\\*\\\*
```

Python declara otras firmas y omite el token.

1. **`phase99` ignora `dim` para la memoria real.**  
El caller entrega **`dim`**, pero Rust trabaja siempre con **`D\\\\\\\_DIM=10000`**. Eso convierte una API aparentemente genérica en una frontera de memoria insegura.

2. **`phase99` no valida punteros ni longitudes.**  
**`num\\\\\\\_neighbors \\\\\\\> 0`** + puntero inválido puede entrar directamente en **`from\\\\\\\_raw\\\\\\\_parts\\\\\\\*`**.

3. **SLERP antipodal sigue roto en el caso exacto más importante.**  
Lo compilé y ejecuté sobre el cuerpo entregado: con **`v0=e1`**, **`v1=-e1`**, **`t=0.5`**, produce **10.000 NaN**. El “fix antipodal” no está cerrado.

4. **SLERP tiene un buffer fijo `float ortho\\\\\\\[10000\\\\\\\]` con `dim` dinámico.**  
**`dim \\\\\\\> 10000`** implica escritura fuera de límites.

5. **Python/C++ tienen ABI incompatible en `validate\\\\\\\_alignment()`.**  
C++ recibe 2 argumentos; Python manda 3.

6. **`validate\\\\\\\_topology()` está incompleta.**  
Construye estructuras y no devuelve β₁.

7. **A8 del propio sistema de pruebas usa la aridad equivocada.**  
No está verificando el contrato actual de Rust.

8. **Los nombres de biblioteca Rust y C++ colisionan.**  
En Linux ambos apuntan a:  
**`libpmtp\\\\\\\_kernel\\\\\\\_v506.so`**.  
El supuesto “Rust + C++ separado” no queda materializado como dos binarios.

9. **El monolito puede cargar `None` y luego desreferenciarlo.**  
Probado:  
**`PmtpMonolito(base\\\\\\\_dir=nonexistent)`** → **`AttributeError`** dentro de **`\\\\\\\_bind\\\\\\\_rust\\\\\\\_ffi`**.

### **P1 — fallos de diseño que producen resultados engañosos**

1. **`dt`** entra a **`phase99`** pero **no se usa**.

2. **`cbf\\\\\\\_gamma`** se utiliza como ganancia de actualización, pero **no hay realmente un Control Barrier Function** implementado.

3. **`drift = vec!\\\\\\\[0.0; D\\\\\\\_DIM\\\\\\\]`** reserva memoria por llamada Rust. En 50.000 llamadas son aproximadamente **2 GB de tráfico temporal de buffers**, aunque el RSS no necesariamente lo revele.

4. Pesos, vecinos, **`dt`**, **`gamma`**, **`local`** y datos de vecinos no tienen política completa para **`NaN/Inf`**.

5. **`num\\\\\\\_neighbors`** y el tamaño efectivo de **`weights`** no se validan conjuntamente.

6. La rama estándar de SLERP no hace **`clamp(dot, -1, 1)`** antes de **`acos`**.

7. SLERP tampoco define el comportamiento para vectores cero.

8. **`close()`** del slab no hace **`unlink()`** de **`/dev/shm/...`**, por lo que aparecen objetos persistentes.

9. **`threading.Lock()`** solo protege el proceso local; no resuelve múltiples escritores de procesos distintos.

### **P2 — pruebas que actualmente sobreafirman lo que demostraron**

1. El fuzzing hace:

```
\\\*\\\*\\\`except Exception:\\\`\\\*\\\*    
    
\\\`    \\\*\\\*pass\\\`\\\*\\\*
```

Por lo tanto, **50.000 fallos pueden terminar reportados como éxito**.

1. La variación de RSS de **`0.52 MB`** **no demuestra 0 leaks**.

2. El supuesto **FJLT test no es un FJLT**.  
Prueba esencialmente que multiplicar componentes por ±1 conserva la norma.

3. El supuesto **Qwen zero-copy no es una prueba zero-copy**.  
El fallback hace:

```
\\\*\\\*\\\`self.memory = np.copy(tensor)\\\`\\\*\\\*    
    
\\\*\\\*\\\`...\\\`\\\*\\\*    
    
\\\*\\\*\\\`return np.copy(self.memory)\\\`\\\*\\\*
```

Eso prueba igualdad de bytes después de copiar, no IPC zero-copy.

1. Tampoco se demuestra transferencia entre dos procesos independientes.

2. **`model\\\\\\\_b`** se carga, pero el latent reconstruido **no entra realmente en una continuación de Model B**.

3. **`PmtpTensorHandle(require\\\\\\\_pin=True)`** rompe en este entorno CPU-only: **`pin\\\\\\\_memory()`** produce **`RuntimeError`**.

4. El output Triton no exige **`contiguous()`**.

5. No se define claramente qué sucede con aliasing **`x is out`**.

6. El tratamiento NaN de Triton puede transformar un total NaN en **`inv=0`** y terminar produciendo un vector aparentemente válido pero semánticamente destruido.

7. La cola de polling async no tiene una política completa de cancelación/cierre.

8. La documentación y los binarios no tienen una única versión: V508 contiene referencias V504/V505/V506/V507.

9. El C++ entregado no compila directamente en GCC/Linux tal como está escrito (**`\\\\\\\_\\\\\\\_declspec`**, **`\\\\\\\_\\\\\\\_cpuid`**/headers y funciones matemáticas).

10. La afirmación del README sobre Mooncake y una supuesta ley universal de “\<64 KB ⇒ colapso por TLB shootdown” **no queda respaldada por la fuente citada**. Mooncake sí documenta arquitectura de KVCache disaggregated, uso de CPU/DRAM/SSD/NIC y RDMA a gran escala; eso no equivale a demostrar esa ley de 64 KB. 

### **Lo más importante**

He encontrado además algo que explica por qué el ciclo se eterniza:

**la batería de pruebas V508 está certificando propiedades distintas de las que afirma certificar.**

Ese es el enemigo raíz.

Hay tres capas distintas que deben pasar:

Algoritmo correcto​=Implementacioˊn correcta​=Prueba que realmente lo demuestra​

V508 tiene problemas en las **tres**.

Por ejemplo:

```
\\\*\\\*\\\`FJLT\\\`\\\*\\\*    
    
\\\`   ↓\\\`    
    
\\\*\\\*\\\`prueba implementada:  ||x|| ≈ ||Dx||\\\`\\\*\\\*    
    
\\\`   ↓\\\`    
    
\\\*\\\*\\\`propiedad realmente demostrada: D es una matriz diagonal ±1 isométrica\\\`\\\*\\\*    
    
\\\`   ↓\\\`    
    
\\\*\\\*\\\`propiedad afirmada: "FJLT funciona"\\\`\\\*\\\*    
    
\\\`   ↓\\\`    
    
\\\*\\\*\\\`NO EQUIVALENTE\\\`\\\*\\\*
```

Y el mismo patrón aparece en zero-copy, fuzzing, SeqLock, CBF, SLERP y ABI.

### **Solución arquitectónica que recomiendo**

No seguir agregando fixes aislados.

La V509 debería imponer **un único contrato canónico**:

```
\\\*\\\*\\\`ABI\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*tipos\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*tamaños\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*alignment\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*ownership\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*lifetime\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*error codes\\\`\\\*\\\*    
    
\\\` └── \\\*\\\*versión ABI\\\`\\\*\\\*    
    
    
\\\*\\\*\\\`SHM\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*header\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*writer ownership\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*sequence protocol\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*publication\\\`\\\*\\\*    
    
\\\` └── \\\*\\\*reclamation/unlink\\\`\\\*\\\*    
    
    
\\\*\\\*\\\`MATH\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*finite-input contract\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*zero-vector contract\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*antipodal contract\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*normalization contract\\\`\\\*\\\*    
    
\\\` └── \\\*\\\*dimensional contract\\\`\\\*\\\*    
    
    
\\\*\\\*\\\`TEST\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*unit\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*property\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*adversarial\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*cross-process\\\`\\\*\\\*    
    
\\\` ├── \\\*\\\*sanitizer\\\`\\\*\\\*    
    
\\\` └── \\\*\\\*benchmark\\\`\\\*\\\*
```

Y **ningún test puede usar un mock cuando está certificando una propiedad del backend real**.

La documentación SOTA de Rust confirma que **`AtomicU64`** proporciona operaciones atómicas para compartir entre **threads**, pero eso no convierte por sí mismo el protocolo completo de escritores de POLYDIM en un mecanismo IPC correcto; el algoritmo sigue necesitando adquisición exclusiva y un contrato bien definido para la memoria compartida. 

Triton, por su parte, sí documenta explícitamente las máscaras de **`load/store`** y las reducciones **`sum`**; por tanto el problema de tu kernel no está en que Triton no permita este patrón, sino en que **el contrato de entrada/salida y la política numérica de POLYDIM están incompletos**. 

Y el problema de **`pin\\\\\\\_memory()`** tampoco es hipotético: en el entorno que utilicé, PyTorch 2.10 CPU-only lanza exactamente el error al intentar fijar memoria; la documentación actual de PyTorch también advierte que el API de pinned memory es específico del acelerador. 

He dejado la evidencia de esta ronda en:

**asedio\_v508\_round3.txt — evidencias de la ronda**

**Todavía no doy “APTA”.** La razón es concreta: quedan P0 sin cerrar. El siguiente blanco prioritario es **diseñar el ABI único + SeqLock multi-proceso correctamente**, porque mientras eso no esté cerrado, cualquier benchmark superior puede ser una medición de un sistema distinto del que creemos estar probando.

asedio\_v508\_round3.txtDocumento

Continúo. Esta ronda encontró varios problemas nuevos que no conviene esconder detrás de los ya conocidos.

### Nuevos golpes fuertes de V508

**1. El “double buffer” no existe en Python.**

Rust define:

```
\`sig\\\_0\\\_off\`  
  
\`sig\\\_1\\\_off\`  
  
\`write\\\_turn\`
```

pero `PmtpSlabAllocator` solo tiene:

```
\`self.tensor\\\_array\`
```

No hay dos buffers de payload ni selector de buffer publicado. Es decir:

documentacioˊn: Double Buffer≠implementacioˊn: Single Buffer\\text\{documentación: Double Buffer\} \\neq \\text\{implementación: Single Buffer\}

Esto es más grave que una optimización faltante: afecta el protocolo de publicación.

**2. El header pasa un test engañoso.**

Verifiqué:

```
\`Python sizeof = 128\`  
  
\`Python alignment = 128\`
```

Eso está bien. **Retiro explícitamente el supuesto defecto de `\\\_align\\\_=128`.**

Pero el layout semántico es distinto:

```
\`Python:\`  
  
\`40..127 = \\\_reserved\`  
  
  
\`Rust:\`  
  
\`40..47 = sig\\\_0\\\_off\`  
  
\`48..55 = sig\\\_1\\\_off\`  
  
\`56    = write\\\_turn\`  
  
\`57..127 = reserved\`
```

Por eso:

```
\`sizeof == 128\`  
  
\`alignment == 128\`
```

puede pasar mientras Rust y Python interpretan **bytes diferentes como metadatos**.

Ese tipo de bug es exactamente el que quiero eliminar antes de dar cierre.

**3. El chequeo C++ de alineación está conectado al parámetro equivocado.**

Python hace:

```
\`pmtp\\\_cpp\\\_validate\\\_tensor\\\_alignment(\`  
  
\`    handle.data\\\_ptr,\`  
  
\`    handle.size\\\_bytes,\`  
  
\`    min\\\_dim\`  
  
\`)\`
```

C++ espera:

```
\`(const void\\\* ptr, int element\\\_size)\`
```

Por tanto, para un tensor FP32 de 40.000 bytes C++ recibe:

```
\`element\\\_size = 40000\`
```

y no:

```
\`element\\\_size = 4\`
```

El tercer argumento ni siquiera existe en C++.

Además:

```
\`ptr == nullptr\`
```

puede devolver PASS, porque:

```
\`0 % 64 == 0\`
```

Eso es un bug concreto de validación.

**4. El slab permite broadcasting no deseado.**

Lo ejecuté realmente.

Se esperaba:

```
\`8 arrays de shape (10000,)\`
```

pero esto:

```
\`np.array(3.0, dtype=np.float32)\`
```

también es aceptado por:

```
\`np.copyto(self.tensor\\\_array\\\[i\\\], t, casting='no')\`
```

y rellena los 10.000 elementos con `3`.

Así que la función **no está imponiendo el contrato que declara**.

**5. Dos procesos pueden abrir el mismo slab sin coordinación de ownership.**

Lo reproduje:

```
\`Proceso/allocator A escribe 1\`  
  
\`Proceso/allocator B lee -\\\> 1\`  
  
  
\`B escribe 2\`  
  
\`A lee -\\\> 2\`
```

No hay propietario exclusivo, generation token, lease, epoch de adquisición ni protocolo de creación exclusiva.

Esto significa que el `slab\\\_id` no identifica un recurso privado: identifica un espacio que varios procesos pueden modificar.

**6. `close()` deja el objeto POSIX persistente.**

Reproducción:

```
\`close()\`  
  
\`/dev/shm/POLYDIM\\\_SLAB\\\_\\\<id\\\> todavía existe\`
```

Por tanto hay dos recursos distintos que deben gestionarse:

mmap lifetime≠namespace lifetime\\text\{mmap lifetime\} \\neq \\text\{namespace lifetime\}

Cerrar el descriptor no equivale a destruir el objeto IPC.

**7. El Rust puede corromper el tensor y luego informar “error”.**

Este orden es peligroso:

```
\`for i in 0..D\\\_DIM \\\{\`  
  
\`    let updated = ...;\`  
  
\`    local\\\[i\\\] = updated as f32;\`  
  
\`\\\}\`  
  
  
\`if !new\\\_norm\\\_sq.is\\\_finite() \\\{\`  
  
\`    return -7;\`  
  
\`\\\}\`
```

Con `NaN`/`Inf`:

1. modifica `local`;

2. termina con datos corruptos;

3. recién después detecta el problema;

4. devuelve `-7`.

La semántica correcta debe ser transaccional:

```
\`READ\`  
  
\`  ↓\`  
  
\`COMPUTE\`  
  
\`  ↓\`  
  
\`VALIDATE\`  
  
\`  ↓\`  
  
\`COMMIT\`
```

no:

```
\`WRITE\`  
  
\`  ↓\`  
  
\`VALIDATE\`
```

**8. `dt` no existe matemáticamente en la dinámica implementada.**

La API declara:

```
\`dt=0.01\`
```

y Rust recibe `dt`.

Pero el update usa:

```
\`let updated = local\\\[i\\\] + gamma \\\* px\\\_drift;\`
```

`dt` nunca participa.

Así que:

```
\`dt = 0.001\`  
  
\`dt = 1.0\`  
  
\`dt = 1000.0\`
```

producen exactamente la misma actualización.

Eso invalida la descripción de integración Euler.

**9. `cbf\\\_gamma` tampoco implementa una CBF visible.**

El parámetro llamado:

```
\`cbf\\\_gamma\`
```

termina siendo simplemente un multiplicador escalar.

No aparece una función barrera, restricción, condición de seguridad, proyección factible ni corrección asociada a CBF.

No voy a llamar a esto “CBF implementado” hasta que exista realmente el objeto matemático que se afirma.

**10. `dim` es una mentira peligrosa en la frontera Rust.**

Se recibe:

```
\`dim: usize\`
```

pero se ignora en todos los slices.

El código usa siempre:

```
\`D\\\_DIM = 10000\`
```

Eso crea una API aparentemente dinámica con backend fijo.

**11. También falta protección contra overflow en `num\\\_neighbors \\\* D\\\_DIM`.**

La expresión:

```
\`num\\\_neighbors \\\* D\\\_DIM\`
```

se usa antes de crear el slice.

No hay validación previa de overflow ni de que el tamaño solicitado sea representable/validable frente al buffer real.

En una frontera FFI esto no puede quedar implícito.

### Y encontré otra grieta importante en Triton

La documentación actual de Triton especifica que `tl.arange` exige límites apropiados con potencia de dos; el propio tutorial de vectorización también señala que los bloques deben ser potencia de dos.

Pero V508 hace:

```
\`self.block = min(block, triton.next\\\_power\\\_of\\\_2(dim))\`
```

Ejemplo:

```
\`dim   = 10000\`  
  
\`block = 1000\`  
  
  
\`self.block = 1000\`
```

Eso no es potencia de dos.

La corrección es:

```
\`self.block = min(\`  
  
\`    triton.next\\\_power\\\_of\\\_2(block),\`  
  
\`    triton.next\\\_power\\\_of\\\_2(dim)\`  
  
\`)\`
```

o validar/rechazar explícitamente un `block` inválido.

### Otra grieta de Triton: `out` no está validado

Se comprueba:

```
\`x.is\\\_cuda\`  
  
\`x.dtype == float32\`  
  
\`x.is\\\_contiguous()\`
```

pero para `out` solo:

```
\`out.numel() == self.dim\`
```

Faltan como mínimo:

```
\`out.is\\\_cuda\`  
  
\`out.dtype == float32\`  
  
\`out.is\\\_contiguous()\`  
  
\`out.device == x.device\`  
  
\`out.numel() == x.numel()\`
```

Porque el kernel escribe:

```
\`tl.store(out\\\_ptr + offs, ...)\`
```

con direccionamiento lineal.

Un `out` no contiguo no tiene la misma semántica.

### Y hay un bug de concurrencia que no estaba en la lista anterior

En `AsyncTritonIngestorv508`:

```
\`finally:\`  
  
\`    await self.\\\_release(idx)\`
```

no significa que el slot esté libre del punto de vista del GPU.

Si una coroutine es cancelada después de haber hecho:

```
\`staging.copy\\\_(...)\`  
  
\`self.normalizer.run(...)\`  
  
\`event.record()\`
```

pero antes de esperar el `event`, `idx` vuelve a:

```
\`self.\\\_free\`
```

aunque el GPU todavía pueda estar leyendo/escribiendo:

```
\`staging\\\[idx\\\]\`  
  
\`output\\\[idx\\\]\`
```

Resultado potencial:

```
\`operación A GPU todavía activa\`  
  
\`        ↓\`  
  
\`slot liberado\`  
  
\`        ↓\`  
  
\`operación B reutiliza slot\`  
  
\`        ↓\`  
  
\`A y B comparten buffers\`  
  
\`        ↓\`  
  
\`corrupción\`
```

Ese sí es un problema real de lifecycle, no una cuestión de estilo.

### Y el “zero-copy” sigue sin pasar la prueba conceptual

El camino del README hace:

```
\`latent\\\_tensor\\\_a.detach().cpu().float().numpy()\`
```

después:

```
\`np.copy(tensor)\`
```

y al leer:

```
\`np.copy(self.memory)\`
```

Eso demuestra:

igualdad de datos\\text\{igualdad de datos\}

pero no:

zero-copy\\text\{zero-copy\}

Son propiedades distintas.

El test tampoco vuelve a insertar ese buffer directamente como estado interno de Model B; solamente reconstruye un `numpy.ndarray` y compara bytes.

### Resultado de esta ronda

Ahora mismo tengo estas categorías bloqueadas:

```
\`ABI / FFI              ❌\`  
  
\`SHM protocol           ❌\`  
  
\`Seqlock                ❌\`  
  
\`Double buffer          ❌\`  
  
\`Rust safety            ❌\`  
  
\`SLERP                  ❌\`  
  
\`Topology               ❌\`  
  
\`Triton contract        ❌\`  
  
\`Async lifecycle        ❌\`  
  
\`Zero-copy evidence     ❌\`  
  
\`Test validity          ❌\`  
  
\`Documentation claims   ❌\`
```

Y una corrección positiva verificable:

```
\`ctypes ShmHeader size/alignment = CORRECTO\`
```

No lo mantengo como problema solo porque haya sido señalado antes.

Dejé esta ronda aquí:

**asedio\_v508\_round4.txt — evidencia y nuevos hallazgos**

La próxima fase que corresponde ya es todavía más profunda: **buscar bugs de segundo orden**, es decir, qué ocurre cuando los parches de P0 se aplican simultáneamente y sus invariantes interactúan entre sí. Ese es el nivel donde suelen sobrevivir los últimos errores de sistemas pequeños pero complejos.

Lo muerdo. Y ahora aparecen fallos de **especificación científica** que son independientes del código.

## RONDA 6 — el hueso debajo del hueso

### P0.21 — La batería no puede certificar V508 porque `PmtpMonolito()` ni siquiera representa V508

El propio archivo dice:

```
`Archivo:  polydim\_v505\_monolito.py`

`Versión:  504`
```

y la batería imprime:

```
`POLYDIM V505`
```

mientras el paquete es:

```
`V508`
```

Eso no es cosmético.

En investigación reproducible:

artefacto probado=?artefacto entregado\\text\{artefacto probado\} \\stackrel\{?\}\{=\} \\text\{artefacto entregado\} 

V508 no lo demuestra.

### Consecuencia

Aunque A1–A8 fueran perfectos, todavía faltaría probar:

```
`hash del código probado`

`=`

`hash del código entregado`
```

Ese debería ser un requisito de cierre.


# P0.22 — A6 es literalmente una prueba constante

El código:

```
`ping = 1`

`ok = ping == 1`
```

Prueba esto:

1=11=1 

No prueba:

```
`Rust cargado`

`ABI válido`

`FFI válido`

`memoria compartida`

`tensor transferido`
```

Es un **test tautológico**.

Por tanto:

```
`A6 PASS`
```

no contiene ninguna evidencia sobre el sistema.


# P0.23 — A5 tampoco interroga hardware

```
`cl = 64`

`ok = cl \>= 32 and ...`
```

No lee:

```
`/sys/devices`

`CPUID`

`cache descriptors`

`NUMA`

`lstopo`
```

ni ninguna fuente de hardware.

La batería dice:

```
`cache\_line = 64`
```

porque el programa escribió:

```
`64`
```

Eso es una constante, no una medición.

Esto contradice directamente la propia regla:

> “Software does not assume; software interrogates.”


# P0.24 — A3 tampoco consulta el hardware

```
`a = m.\_hw\_alignment`
```

pero:

```
`self.\_hw\_alignment = 64`
```

se inicializa así:

```
`self.\_hw\_alignment = 64`
```

y luego:

```
`\_query\_hardware():`

`    self.\_hw\_alignment = 64`
```

Por tanto A3 equivale a:

```
`ok = 64 in (16,32,64)`
```

Otra tautología.

No existe interrogación.


# P0.25 — A4 demuestra únicamente un comportamiento de `ctypes`

Esto sí está correctamente medido:

```
`ctypes.alignment(ShmHeader)`
```

pero no demuestra:

alignmentPython=alignmentRustalignment\_\{Python\} = alignment\_\{Rust\} 

ni:

offsetiPython=offsetiRust.offset\_i^\{Python\} = offset\_i^\{Rust\}. 

Por tanto A4 es necesario pero muy insuficiente.


# P0.26 — El test A7 mide una copia local, no IPC

Hace:

```
`alloc.write\_slab\_atomic(tensors)`

`readback = alloc.read\_slab()`
```

Todo sucede dentro del mismo objeto Python.

No hay:

```
`process A`

`   ↓`

`POSIX SHM`

`   ↓`

`process B`
```

No hay:

```
`fork`

`exec`

`attach`

`detach`
```

No se mide IPC.

El nombre:

```
`Zero-Copy IPC`
```

no está demostrado por A7.


# P0.27 — El “zero-copy Qwen” tiene una contradicción experimental adicional

El experimento hace:

```
`latent\_tensor\_a =`

`    last\_hidden\_state\_a.detach().cpu().float().numpy()`
```

Esto ya implica una transición:

```
`GPU tensor`

`   ↓`

`CPU`

`   ↓`

`NumPy`
```

y después:

```
`pmtp\_ipc.write(flattened\_tensor\_a)`
```

el fallback hace:

```
`self.memory = np.copy(tensor)`
```

y la lectura:

```
`return np.copy(self.memory)`
```

Así que el experimento ha probado:

A→copy1→copy2→BA \\rightarrow copy\_1 \\rightarrow copy\_2 \\rightarrow B 

No:

A→shared memory→BA \\rightarrow shared\\ memory \\rightarrow B 


# P0.28 — Ni siquiera existe “Node B”

El propio código dice:

```
`\# Simulating the second node for memory/telemetry profiling`

`model\_b = ...`
```

Pero ambos están en:

```
`mismo process`

`mismo host`

`misma dirección lógica de ejecución`
```

y `model\_b` nunca consume realmente:

```
`latent\_tensor\_b`
```

como entrada de un forward posterior.

Por tanto el claim:

```
`latent transfer Model A → Model B`
```

no está demostrado.

Solo existe:

```
`Model A`

`   ↓`

`numpy`

`   ↓`

`buffer`

`   ↓`

`numpy`
```


# P0.29 — “Zero Drift” está mal definido

Este cálculo:

```
`drift = np.max(np.abs(latent\_tensor\_a - latent\_tensor\_b))`
```

con:

```
`latent\_tensor\_b = np.copy(latent\_tensor\_a)`
```

va a producir:

00 

por construcción.

Eso no demuestra una propiedad de la arquitectura geométrica.

Para demostrar una transformación isométrica necesitaríamos algo como:

∣∥Tx−Ty∥2−∥x−y∥2∣≤ϵ\\left| \\|Tx-Ty\\|\_2-\\|x-y\\|\_2 \\right| \\le\\epsilon 

para múltiples pares x,yx,y.

La igualdad elemento-a-elemento después de una copia es trivial.


# P0.30 — La afirmación DPI del README no se sigue de los datos

El README afirma:

I(Z;Z^)≤I(Z;T)≤H(T)≪H(Z)I(Z;\\hat Z)\\le I(Z;T)\\le H(T)\\ll H(Z) 

y posteriormente:

> “projection onto a 512-token JSON bus annihilates \>97.3% of the geometric information.”

El problema es que:

H(T)H(T) 

no puede compararse automáticamente con:

32D32D 

bits de almacenamiento FP32 como si ambos fueran capacidades informacionales directamente equivalentes.

Además:

```
`512 tokens`
```

no especifica:

```
`vocabulary`

`token entropy`

`encoding`

`context constraints`

`decoder`

`noise`
```

Por tanto el:

97.3%97.3\\% 

no está demostrado por la ecuación mostrada.


# P0.31 — “320,000 bits físicos” no es “capacidad entrópica”

El README dice:

> physical entropic capacity is 320,000 bits

Pero:

```
`10000 × 32 = 320000`
```

es **capacidad de representación bruta del formato**, no necesariamente entropía de Shannon.

Para hablar de entropía necesitamos una distribución:

H(X)=−∑p(x)log⁡p(x).H(X)=-\\sum p(x)\\log p(x). 

Un tensor FP32 no tiene automáticamente 320.000 bits de Shannon.

Este es un error conceptual, no de implementación.


# P0.32 — El supuesto “FJLT” no contiene FWHT

El README dice:

```
`Rademacher preconditioning for FWHT`
```

pero el código:

```
`latente\_precondicionado = latente \* rademacher\_signs`
```

y termina.

No aparece:

HDxH\_Dx 

ni:

```
`FWHT`
```

ni transformación equivalente.

Por tanto el benchmark no es:

```
`FJLT`
```

sino:

```
`random sign diagonal transform`
```

La propiedad:

∥Dx∥2=∥x∥2\\|Dx\\|\_2=\\|x\\|\_2 

es cierta exactamente, pero no certifica el embedding JL.


# P0.33 — `O(N log N)` y `O(1)` espacio están simultáneamente mal atribuidos al código

El README dice:

O(Nlog⁡N)O(N\\log N) 

y:

O(1) space.O(1)\\text\{ space\}. 

Pero un FWHT in-place normalmente requiere almacenar el vector:

Θ(N)\\Theta(N) 

aunque el espacio auxiliar adicional pueda ser:

O(1)O(1) 

o muy pequeño.

Eso es distinto de:

O(1) total.O(1)\\text\{ total\}. 

Más importante aún:

**V508 no contiene ninguna implementación FWHT.**

Por tanto el claim no está conectado al artefacto.


# P0.34 — La afirmación `S^\{D-1\}` tampoco queda garantizada

El Rust intenta normalizar al final:

```
`local\[i\] \*= inv\_norm;`
```

pero durante el cálculo utiliza:

```
`local`

`drift`

`updated`
```

sin validar inicialmente:

∥local∥2=1.\\|local\\|\_2=1. 

La proyección:

Px=I−xx⊤P\_x = I-xx^\\top 

solo es idempotente/proyector ortogonal cuando:

x⊤x=1.x^\\top x=1. 

En general:

(I−xx⊤)2≠I−xx⊤.(I-xx^\\top)^2 \\ne I-xx^\\top. 

La fórmula correcta para un xx arbitrario sería:

Px=I−xx⊤x⊤x.P\_x = I-\\frac\{xx^\\top\}\{x^\\top x\}. 

Por tanto la etiqueta:

```
`Riemannian Projection on S^(D-1)`
```

requiere una precondición que el código no impone.


# P0.35 — La normalización de `new\_norm\_sq` no salva la proyección incorrecta

Puede parecer:

```
`proyecto`

`→ actualizo`

`→ normalizo`
```

y por tanto:

```
`“termina en la esfera”`
```

Sí, pero eso **no convierte en correcto el vector tangente utilizado para llegar allí**.

Es posible obtener:

∥x′∥=1\\|x'\\|=1 

y aun así haber aplicado una dirección que no era tangente a:

TxSD−1.T\_xS^\{D-1\}. 

Hay que separar:

```
`manifold membership`
```

de:

```
`correct tangent dynamics`
```


# P0.36 — `dt` rompe además la reproducibilidad científica

Con:

```
`updated =`

`local\[i\] + gamma \* px\_drift`
```

la ecuación implementada no depende de:

```
`dt`
```

pero el README y Python la presentan como integración temporal.

Entonces el experimento:

```
`dt = 0.001`
```

y:

```
`dt = 0.1`
```

no representa dos simulaciones distintas.

Esto hace imposible validar estabilidad temporal del integrador.


# P0.37 — El supuesto “CBF” no tiene barrera

Esto ya no es una sospecha.

En todo Rust V508:

```
`h(x)         → inexistente`

`∇h(x)        → inexistente`

`α(h)         → inexistente`

`constraint   → inexistente`

`QP/project   → inexistente`
```

Por tanto:

CBF≢γ\\boxed\{\\text\{CBF\} \\not\\equiv \\gamma\} 

Lo que existe es:

x˙←γPxd.\\dot x \\gets \\gamma P\_x d. 

Renombrarlo como:

```
`gain\_gamma`
```

sería correcto.

Llamarlo:

```
`cbf\_gamma`
```

es científicamente engañoso.


# P0.38 — El “Frechet Mean” del README tampoco está implementado

README:

> Multi-agent aggregation employs the Fréchet Mean.

Código Rust:

```
`drift\[i\] += w \* n\_ptr\[i\];`
```

Eso es una suma ponderada en coordenadas ambiente.

Después:

```
`P\_x(drift)`
```

y normalización.

No hay minimización de:

F(μ)=∑iwid2(μ,xi)F(\\mu)=\\sum\_i w\_i d^2(\\mu,x\_i) 

ni algoritmo iterativo de Karcher/Fréchet mean.

Por tanto:

```
`documentación = Fréchet Mean`

`implementación = projected weighted Euclidean drift`
```

No son equivalentes.


# P0.39 — `num\_neighbors == 0` no significa necesariamente éxito

Rust:

```
`if num\_neighbors == 0 \{`

`    return 0;`

`\}`
```

pero la API dice:

```
`0 = OK`
```

Entonces:

```
`sin vecinos`
```

es indistinguible de:

```
`consenso ejecutado correctamente`
```

Hay que decidir formalmente:

K=0⇒NOOPK=0 \\Rightarrow \\text\{NOOP\} 

y devolver un estado distinguible, por ejemplo:

```
`NO\_NEIGHBORS`
```

si el protocolo lo necesita.


# P0.40 — Los pesos no están normalizados ni validados

Se hace:

```
`drift\[i\] += w \* n\_ptr\[i\];`
```

No hay:

∑kwk=1\\sum\_k w\_k = 1 

ni:

```
`finite(weight)`

`nonnegative(weight)`

`bounded(weight)`
```

Entonces un único peso:

```
`1e30`
```

puede destruir la dinámica.

Y:

```
`NaN`
```

puede infectarla.

Esto afecta tanto la matemática como la seguridad numérica.


# P0.41 — El acumulador `drift` es FP32 aunque el estado se evalúa en FP64

Rust:

```
`let mut drift = vec!\[0.0f32; D\_DIM\];`
```

pero:

```
`dot\_x\_drift`
```

es `f64`.

Entonces:

```
`neighbor accumulation = FP32`

`dot projection        = FP64`

`state update          = FP64`

`state storage         = FP32`
```

Hay cuatro dominios numéricos distintos.

No es necesariamente incorrecto, pero **es un contrato numérico no especificado**.

Con muchos vecinos:

∑kwknk\\sum\_k w\_k n\_k 

puede acumular error de cancelación considerable en FP32 antes de entrar en FP64.


# P0.42 — La métrica de memoria del FFI no puede certificar ausencia de leaks

La prueba usa:

```
`RSS inicial`

`RSS final`
```

y:

```
`delta \< 10 MB`
```

Eso no demuestra:

leaks=0.\\text\{leaks\}=0. 

RSS puede permanecer estable con:

```
`allocator caching`

`arenas`

`mmap reuse`

`fragmentation`

`page retention`
```

y puede incluso aumentar sin leak.

Un verdadero ataque necesita:

```
`ASan`

`LSan`

`Valgrind/Memcheck`

`heaptrack`

`massif`

`allocator stats`
```

según plataforma.


# P0.43 — El fuzzing publicado no es fuzzing

Los inputs son constantes:

```
`local = ones(...)`

`neighbors = ones(...)`

`weights = \[1\]`
```

y se repiten 50.000 veces.

Eso es:

stress repetition\\text\{stress repetition\} 

no:

fuzzing\\text\{fuzzing\} 

Fuzzing debería variar:

```
`ptr validity`

`dim`

`K`

`weights`

`NaN`

`Inf`

`zero`

`misalignment`

`aliasing`

`boundary lengths`
```

y registrar cada input que rompe un invariant.


# P0.44 — El fuzzing puede ocultar 50.000 fallos y declarar PASS

Esto sigue siendo uno de los defectos más graves del test:

```
`except Exception:`

`    pass`
```

Si las 50.000 llamadas hacen:

```
`Exception`

`Exception`

`Exception`

`...`
```

la prueba termina:

```
`SUCCESS`
```

sin haber validado ninguna llamada correcta.


# P0.45 — El script de fuzzing llama al FFI con una firma incorrecta

V508 Rust:

7 argumentos7\\ \\text\{argumentos\} 

El fuzzing manda:

```
`ptr`

`ptr`

`ptr`

`1`

`0.1`
```

cinco.

Por tanto el benchmark que supuestamente demuestra:

> “Frontera FFI estable”

**ni siquiera invoca correctamente la función que pretende probar**.


# Este es el verdadero cierre parcial que emerge

Después de seis meses, entiendo tu frustración. El problema no es que “queden infinitos bugs porque hay 1.000 líneas”.

El problema es que estábamos recorriendo:

```
`bug 1`

`bug 2`

`...`

`bug 10`
```

cuando había que atacar:

```
`              ESPECIFICACIÓN`

`                    │`

`        ┌───────────┼───────────┐`

`        ▼           ▼           ▼`

`      Python      Rust        C++`

`        │           │           │`

`        └───────────┼───────────┘`

`                    ▼`

`                ABI / SHM`

`                    │`

`                    ▼`

`                MATEMÁTICA`

`                    │`

`                    ▼`

`                 TESTS`

`                    │`

`                    ▼`

`                EVIDENCIA`
```

Y ahora el ataque muestra que **las cinco capas tienen desacoples**.

La buena noticia es importante:

**ya podemos parar de “buscar bugs al azar”.**

El conjunto de fallos se está concentrando en un número reducido de contratos raíz:

C1:ABIC2:SHM protocolC3:numerical contractC4:manifold contractC5:test validityC6:empirical evidence\\boxed\{ \\begin\{aligned\} C\_1 &: ABI \\\\ C\_2 &: SHM\\ protocol \\\\ C\_3 &: numerical\\ contract\\\\ C\_4 &: manifold\\ contract\\\\ C\_5 &: test\\ validity\\\\ C\_6 &: empirical\\ evidence \\end\{aligned\}\} 

Cerrar esos seis contratos elimina de golpe decenas de fallos derivados.

Y todavía **no doy cierre**, porque queda morder una capa más: **qué invariantes exactos deben cumplirse en cada byte, cada llamada FFI, cada transición de estado y cada operación matemática para que V509 pueda ser certificable de verdad**. Ahí es donde voy a intentar conseguir que, después de la próxima reconstrucción, no vuelvamos a empezar desde cero.

