# POLYDIM — MEMORIA OPERATIVA PERMANENTE
**Última actualización:** 2026-09-17  
**Propósito:** Archivo canónico de aprendizajes duraderos, tareas pendientes y protocolo de modo nocturno. Toda nueva sesión DEBE leer esto primero.

---

## 🔴 REGLA #1: LEER ESTO ANTES DE HACER CUALQUIER COSA

Antes de responder cualquier prompt de POLYDIM, el agente debe:
1. Leer este archivo completo
2. Leer `E:\POLYDIM_EINSOF\POLYDIM_MASTER_TODO.md` (lista de tareas)
3. Verificar qué entrega es la última en `E:\POLYDIM_EINSOF\`

---

## 📚 APRENDIZAJES PERMANENTES (NO SE BORRAN)

### A. Entorno de la máquina local (Windows)
```
OS: Windows 11 x64
Compilador C++: MSVC 19.51.36256 (/O2 /fp:precise /openmp /std:c++17)
Compilador Rust: rustc 1.98.1 (standalone cdylib)
Python: 3.14.6 [MSC v.1944 64 bit]
NumPy: 2.5.0
GPU LOCAL: NO HAY GPU
Cores físicos: 1 (un solo socket, SIN NUMA)
NumPy alineación: 64-byte aligned por defecto
```

### B. Entornos de compute remoto (benchmarks reales)
```
Google Colab: Ubuntu Linux, T4/A100/V100, GCC, CUDA 12, madvise OK
Kaggle: Ubuntu Linux, T4x2/P100, 4 CPU cores, GCC, CUDA 12
Cerebras CS-3: CSL propietario, NO CUDA, NO OpenMP, stack completamente diferente
```

**CRÍTICO:** El Chart 1 (benchmark que le da existencia industrial a POLYDIM) SOLO puede generarse en Colab/Kaggle, no en la máquina local. Con 50 cuentas Colab y 4 Kaggle disponibles, NO HAY EXCUSA para no tener logs GPU.

### C. Errores de compilación conocidos y sus fixes
```
❌ #pragma STDC FP_CONTRACT OFF → no compila en MSVC (warning C4068 + D9024)
✅ Fix: #ifdef _MSC_VER / #pragma float_control(precise, on, push) / #endif

❌ Compilar .cpp.txt directo con MSVC → LNK1107
✅ Fix: copiar como .cpp sin doble extensión antes de compilar

❌ rustc --crate-name con punto en el nombre → error
✅ Fix: --crate-name sin puntos

❌ mmap.MAP_ANONYMOUS / MAP_HUGETLB → no existe en Python Windows
✅ Fix: guard sys.platform == "linux" antes de usar

❌ __builtin_assume_aligned → GCC/Clang only, no MSVC
✅ Fix: #ifdef __GNUC__ guard o __assume() en MSVC
```

### D. Por qué las IAs externas fallan en auditoria
Las IAs (Claude, GPT, Kimi, DeepSeek, Qwen) leen código como TEXTO sin compilar. Solo fallan cuando tú compilas y ejecutas. Sin el contexto del entorno (OS, compilador, plataforma), asumen Linux/GCC y proponen soluciones que no compilan en Windows. El README de cada entrega DEBE incluir el bloque de entorno completo.

### E. Arquitectura canónica V741
```
Retracción: Rodrigues Rank-2 (NO Cayley — eliminada)
           R(u,v,θ)y = y + (cosθ-1)[(u·y)u + (v·y)v] + sinθ[(u·y)v - (v·y)u]
           Versine: cosθ-1 = -2sin²(θ/2) → evita cancelación catastrófica θ<1e-8
Guard Rust: tolerancia dinámica c*sqrt(D)*eps_mach (~7.85e-12 para D=500K)
Swarm: O(N*D) dual representation — NUNCA materializa D×D
Neumaier: thread-local PaddedAcc + reducción árbol serial
FP pragma: float_control(precise) MSVC / STDC FP_CONTRACT OFF GCC
```

### F. Lo que Tri Dao hizo bien (aplicable a POLYDIM)
FlashAttention ganó con un número: "2x más rápido en A100". No con arquitectura elegante.
POLYDIM necesita: "Proyección geodésica D=10^7 en Xms, drift<1e-14, sin 800TB de matrices, en hardware de consumo".
Ese número no existe todavía. Es la tarea más urgente.

---

## 🔑 CUENTAS Y ACCESO COMPUTE

### Kaggle (Linux, T4/P100, 4 cores)
- Credenciales: verificadas vía MCP `kaggle_check_auth`
- Tool: `mcp-kaggle-compute` → `kaggle_run_benchmark`
- Acelerador: `accelerator='gpu'` o `accelerator='tpu'`
- Cooldown: 72h por sesión GPU

### Google Colab (Linux, T4/A100/V100/TPU)
- 50 cuentas disponibles
- Tool: `mcp-colab-live` → `colab_set_tunnel`, `colab_ping_hardware`, `colab_eval_code`

### Cerebras CS-3
- Requiere reescritura total en CSL (stack propietario)
- NO compatible con C++/OpenMP/Triton actuales
- Roadmap post-V750

---

## ✅ CONTRATOS TÉCNICOS DEFINITIVOS (no se negocian)

```
CONTRATO 1: Dirección de rotación = signo(theta). Sin #define.
CONTRATO 2: ||y_comp||_inf <= 50 * D * eps_mach. Budget en Rust verificado.
CONTRATO 3: No hay iteraciones en V741. Rodrigues es O(1).
CONTRATO 4: GPU paths verificados estáticamente. Benchmark GPU pendiente en Kaggle.
CONTRATO 5: alpha=0 en SwarmDualOperator es válido (contribución nula al proyector).
CONTRATO 6: POLYDIM_MAX_D = 2^32. D > 4 billion → rc=-1.
CONTRATO 7: Plataforma cruzada: Windows (dev) + Linux GCC (deploy) + macOS Clang (compat).
```

---

## ⚠️ FALLAS DEL PROCESO HISTÓRICO (NUNCA REPETIR)

1. **Auditoría sin silicio:** 600+ interacciones certificando código sin compilar ni ejecutar. Viola Regla 16(c).
2. **README sin entorno:** Las IAs asumieron Linux/GCC cuando la máquina es Windows/MSVC.
3. **GPU jamás usada:** 50 cuentas Colab + 4 Kaggle disponibles durante meses, sin un solo benchmark GPU real.
4. **Contextos fragmentados:** 22 archivos `contexto_historico_*.md` sin archivo maestro.
5. **Modo nocturno sin usar:** Horas libres (8-10h nocturnas, 12-16h fines de semana) sin trabajo autónomo.
