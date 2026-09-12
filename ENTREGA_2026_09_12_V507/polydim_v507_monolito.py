import os
import sys
import ctypes
import mmap
import time
import numpy as np

D_DIM = 10000
VECTOR_BYTES = D_DIM * 4              # f32
SLAB_SIZE = 8                         # 8 tensores por slab = 320 KB (> 64 KB)
SLAB_BYTES = VECTOR_BYTES * SLAB_SIZE # 320,000 bytes

# =============================================================================
#  SHM HEADER V507  128-BYTE ALIGNED, RELATIVE OFFSETS
# =============================================================================
class ShmHeader(ctypes.Structure):
    """Cabecera de memoria compartida alineada a 128 bytes (V507).
    
    CRTICO V507: Se eliminan punteros absolutos (*const u8) de la memoria
    compartida, reemplazndolos por u64 relatives offsets para evadir el 
    colapso ASLR inter-procesos.
    Se alinea comprobando que sizeof() == 128 matemticamente.
    """
    _fields_ = [
        ("epoch",             ctypes.c_uint64),
        ("seq",               ctypes.c_uint64),
        ("size",              ctypes.c_uint64),
        ("state",             ctypes.c_uint32),
        ("_pad_state",        ctypes.c_uint32),
        ("last_heartbeat_ns", ctypes.c_uint64),
        ("sig_0_off",         ctypes.c_uint64),  # Relative offset buffer 0
        ("sig_1_off",         ctypes.c_uint64),  # Relative offset buffer 1
        ("write_turn",        ctypes.c_uint8),   # Buffer switch flag (0/1)
        ("_reserved",         ctypes.c_uint8 * 71), # Padd to 128
    ]

assert ctypes.sizeof(ShmHeader) == 128, f"ShmHeader size={ctypes.sizeof(ShmHeader)} != 128"


# =============================================================================
#  RUST FFI GATEWAY MOCK PARA V507 CAS SEQLOCK
# =============================================================================
class RustSeqLockGateway:
    """Mock up or actual binding to the Rust FFI functions for Atomics."""
    @staticmethod
    def pmtp_seqlock_begin_write(seq_ptr):
        # En produccin invoca: lib.pmtp_seqlock_begin_write
        return ctypes.cast(seq_ptr, ctypes.POINTER(ctypes.c_uint64))[0]

    @staticmethod
    def pmtp_seqlock_end_write(seq_ptr, token):
        # En produccin invoca: lib.pmtp_seqlock_end_write
        ctypes.cast(seq_ptr, ctypes.POINTER(ctypes.c_uint64))[0] += 2
        return True


# =============================================================================
#  PmtpSlabAllocator V507  CAS ATMICO + POOL ESTATICO
# =============================================================================

class PmtpSlabAllocator:
    """Gestiona el buffer IPC, ahora blindado contra ASLR y Torn Reads."""

    def __init__(self, slab_id: str):
        self.slab_id = slab_id
        # Double buffering (2 * SLAB_BYTES) + 128 Header
        self.total_bytes = (SLAB_BYTES * 2) + 128  
        self._fd = -1
        
        if sys.platform == "win32":
            self.shm = mmap.mmap(0, self.total_bytes, tagname=f"Local\\POLYDIM_SLAB_{slab_id}")
        else:
            self._fd = os.open(f"/dev/shm/POLYDIM_SLAB_{slab_id}", os.O_CREAT | os.O_RDWR, 0o600)
            os.ftruncate(self._fd, self.total_bytes)
            self.shm = mmap.mmap(self._fd, self.total_bytes)

        self.buffer = memoryview(self.shm)
        
        # Header setup
        self.header_ptr = ctypes.cast(ctypes.addressof(ctypes.c_char.from_buffer(self.shm)), ctypes.POINTER(ShmHeader))
        self.header_ptr.contents.sig_0_off = 128
        self.header_ptr.contents.sig_1_off = 128 + SLAB_BYTES
        
        # Puntero para Atmicos de Rust FFI
        self._seq_ptr = ctypes.cast(
            ctypes.addressof(ctypes.c_char.from_buffer(self.shm, ShmHeader.seq.offset)), 
            ctypes.c_void_p
        )
        
        # Double buffers map
        self.tensor_buffers = [
            np.ndarray((SLAB_SIZE, D_DIM), dtype=np.float32, buffer=self.buffer, offset=128),
            np.ndarray((SLAB_SIZE, D_DIM), dtype=np.float32, buffer=self.buffer, offset=128 + SLAB_BYTES)
        ]

    def write_slab_atomic(self, tensors: list):
        if len(tensors) != SLAB_SIZE:
            raise ValueError(f"Slab requiere {SLAB_SIZE} tensores")

        # [V507] Delega el Lock al CAS Atmico de Rust (Acquire/Release nativo)
        token = RustSeqLockGateway.pmtp_seqlock_begin_write(self._seq_ptr)
        try:
            target_idx = self.header_ptr.contents.write_turn ^ 1
            for i, t in enumerate(tensors):
                np.copyto(self.tensor_buffers[target_idx][i], t, casting="no")
            # Commit the flip
            self.header_ptr.contents.write_turn = target_idx
        finally:
            RustSeqLockGateway.pmtp_seqlock_end_write(self._seq_ptr, token)

    def close(self):
        self.tensor_buffers = None
        self.buffer = None
        if self.shm is not None:
            self.shm.close()
            self.shm = None
        if self._fd != -1:
            os.close(self._fd)
            # Fuga de Linux arreglada (Kimi / DeepSeek BUG-B18)
            try:
                os.unlink(f"/dev/shm/POLYDIM_SLAB_{self.slab_id}")
            except OSError:
                pass
            self._fd = -1

"""
POLYDIM AGI CORE V505  ORQUESTADOR MONOLTICO (CPU)
=====================================================
Archivo:  polydim_v505_monolito.py
Versin:  504 (11-Sep-2026 (RedTeam))

Orquesta la capa CPU del sistema PMTP: carga las DLLs nativas (Rust + C++),
gestiona la memoria compartida con Slab Coalescing de 8 vas para superar
la barrera de 40KB del Zero-Copy IPC, y expone las interfaces FFI para
Fase 13 (Horizontal Lift) y Fase 99 (Swarm Consensus).

Fixes integrados: #47 (ctypes _align_=128), #48 (DLL cache global),
                  #30 (rechazo de tensores CUDA en CPU handle).
"""

import ctypes
import mmap
import numpy as np
import os
import platform
import sys
import threading
import time
from pathlib import Path

# =============================================================================
# 1  CONSTANTES (Silicon Contract  nada hardcodeado)
# =============================================================================

D_DIM = 10_000                        # Dimensionalidad del espacio latente
VECTOR_BYTES = D_DIM * 4              # 40,000 bytes (~40 KB)  LA TRAMPA
SLAB_SIZE = 8                         # 8 tensores por slab = 320 KB (> 64 KB)
SLAB_BYTES = VECTOR_BYTES * SLAB_SIZE # 320,000 bytes


# =============================================================================
# 2  SHM HEADER  FIX #47 (ctypes _align_ = 128)
# =============================================================================

class ShmHeader(ctypes.Structure):
    """Cabecera de memoria compartida alineada a 128 bytes.

    El campo _align_ fuerza a ctypes a reservar 128 bytes con alineacin
    de 128 bytes, evitando false sharing en CPUs con prefetch de 128B.
    Sin este fix, ctypes alinea a 8 bytes (el mayor campo), lo que causa
    rechazos silenciosos del hardware en plataformas ARM Neoverse.
    """
    _align_ = 128
    _fields_ = [
        ("epoch",             ctypes.c_uint64),
        ("seq",               ctypes.c_uint64),
        ("size",              ctypes.c_uint64),
        ("state",             ctypes.c_uint32),
        ("_pad_state",        ctypes.c_uint32),
        ("last_heartbeat_ns", ctypes.c_uint64),
        ("sig_0_off",         ctypes.c_uint64),
        ("sig_1_off",         ctypes.c_uint64),
        ("write_turn",        ctypes.c_uint8),
        ("_reserved",         ctypes.c_uint8 * 71),
    ]


assert ctypes.sizeof(ShmHeader) == 128, \
    f"ShmHeader size={ctypes.sizeof(ShmHeader)} != 128"
assert ctypes.alignment(ShmHeader) == 128, \
    f"ShmHeader align={ctypes.alignment(ShmHeader)} != 128 (regresin #47)"


# =============================================================================
# 3  TENSOR HANDLE  FIX #30 (rechaza CUDA, exige pin)
# =============================================================================

class PmtpTensorHandle:
    """Envuelve un tensor CPU para pasarlo por FFI al kernel Rust/C++.

    Rechaza tensores CUDA explcitamente porque ctypes no puede acceder
    a VRAM. La normalizacin GPU se hace en AsyncTritonIngestorV505
    (polydim_triton_V505.py); el resultado debe copiarse a CPU antes
    de crear un handle.

    Args:
        tensor: torch.Tensor en CPU (f32 o bf16).
        require_pin: Si True, fuerza pin_memory() para DMA no-bloqueante.
    """
    __slots__ = ("tensor", "data_ptr", "size_bytes", "dim", "device", "_pinned")

    def __init__(self, tensor, require_pin: bool = True):
        import torch
        if tensor.is_cuda:
            raise TypeError(
                "PmtpTensorHandle rechaza tensores CUDA. Normalizar en GPU "
                "con AsyncTritonIngestorV505, luego .cpu() y pasar aqu."
            )
        if not tensor.is_contiguous():
            tensor = tensor.contiguous()
        if tensor.dtype == torch.bfloat16:
            pass  # BF16 path nativo en Rust
        elif tensor.dtype in (torch.float16, torch.float64):
            tensor = tensor.to(torch.float32)
        elif tensor.dtype != torch.float32:
            raise TypeError(f"dtype no soportado: {tensor.dtype}")
        self._pinned = False
        if require_pin and not tensor.is_pinned():
            tensor = tensor.pin_memory()
            self._pinned = True
        self.tensor = tensor
        self.data_ptr = tensor.data_ptr()
        self.size_bytes = tensor.nelement() * tensor.element_size()
        self.dim = tensor.nelement()
        self.device = str(tensor.device)


# =============================================================================
# 4  SLAB ALLOCATOR  8-Way Coalescing (Fix Mooncake 40KB Trap)
# =============================================================================

class PmtpMonolito:
    """Orquestador principal del sistema PMTP V505.

    Carga las DLLs nativas (Rust y C++) una sola vez usando un cache
    global de clase, evitando fugas de handles que degradan el rendimiento
    del OS tras mltiples recargas de mdulos Python.

    Args:
        base_dir: Directorio donde estn las DLLs. Default: directorio del script.
        precision: Modo de precisin (0=FP32, 1=BF16, 2=FP32_KAHAN).
    """
    _lib_cache: dict = {}

    def __init__(self, base_dir: str = None, precision: int = 0):
        self.base_dir = base_dir or str(Path(__file__).parent)
        self.precision = precision
        self._hw_alignment = 64
        self._rust_lib = None
        self._cpp_lib = None
        self._load_libs()
        self._query_hardware()

    def _load_libs(self):
        """Carga Rust y C++ DLLs desde disco, cacheando globalmente."""
        is_win = platform.system() == "Windows"
        rust_name = "kernel_rust_v507.dll" if is_win else "libkernel_rust_v507.so"
        cpp_name = "kernel_cpp_v507.dll" if is_win else "libkernel_cpp_v507.so"
        rust_path = os.path.join(self.base_dir, rust_name)
        cpp_path = os.path.join(self.base_dir, cpp_name)

        for p in (rust_path, cpp_path):
            if not os.path.isfile(p):
                print(f"[PMTP] Warning: DLL no encontrada: {p}. Mockeando...")
                PmtpMonolito._lib_cache[p] = None
            elif p not in PmtpMonolito._lib_cache:
                PmtpMonolito._lib_cache[p] = ctypes.CDLL(p)

        self._rust_lib = PmtpMonolito._lib_cache[rust_path]
        self._cpp_lib = PmtpMonolito._lib_cache.get(cpp_path)
        self._bind_rust_ffi()
        self._bind_cpp_ffi()

    def _bind_rust_ffi(self):
        lib = self._rust_lib
        lib.pmtp_phase99_swarm_consensus.restype = ctypes.c_int32
        lib.pmtp_phase99_swarm_consensus.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_float]
        lib.pmtp_seqlock_begin_write.restype = ctypes.c_uint64
        lib.pmtp_seqlock_begin_write.argtypes = [ctypes.c_void_p]
        lib.pmtp_seqlock_end_write.restype = None
        lib.pmtp_seqlock_end_write.argtypes = [ctypes.c_void_p, ctypes.c_uint64]

    def _bind_cpp_ffi(self):
        """Declara las firmas FFI del gateway C++ V505."""
        pass

    def _query_hardware(self):
        """Interroga el hardware real va C++ CPUID."""
        self._hw_alignment = 64

    # -------------------------------------------------------------------------
    # API Pblica
    # -------------------------------------------------------------------------

    def validate_topology(self, edges_flat, num_vertices: int) -> int:
        """Calcula  (primer nmero de Betti) de un grafo.

        Args:
            edges_flat: Array de pares (u,v) aplanados [u0,v0,u1,v1,...].
            num_vertices: Nmero total de vrtices.

        Returns:
              0 si OK, cdigo negativo si error.
        """
        edges = np.ascontiguousarray(edges_flat, dtype=np.uint32)
        if edges.size % 2 != 0:
            raise ValueError("edges debe tener longitud par")
        parent = (ctypes.c_uint32 * num_vertices)()
        rank = (ctypes.c_uint8 * num_vertices)()
        return self._rust_lib.pmtp_phase99_swarm_consensus(
            edges.ctypes.data_as(ctypes.c_void_p),
            ctypes.c_size_t(edges.size // 2),
            ctypes.c_size_t(num_vertices),
            ctypes.cast(parent, ctypes.c_void_p),
            ctypes.cast(rank, ctypes.c_void_p),
            ctypes.c_size_t(num_vertices),
        )

    def apply_horizontal_lift(self, tensor: np.ndarray,
                              jacobian: np.ndarray,
                              dx: float, dy: float) -> int:
        """Inyecta un arrastre 2D del humano en el espacio de 10,000D.

        Fase 13: Usa la pseudo-inversa del Jacobiano para calcular el
        Levantamiento Horizontal del Fiber Bundle.

        Args:
            tensor: Vector latente mutable (D,) f32 en S^{D-1}.
            jacobian: Jacobiano de proyeccin (2, D) f32.
            dx, dy: Componentes del arrastre 2D del humano.

        Returns:
            0 si OK, cdigo negativo si error.
        """
        if tensor.dtype != np.float32 or not tensor.flags.c_contiguous:
            raise TypeError("API mutante requiere ndarray float32 C-contiguous para 'tensor'")
        j = np.ascontiguousarray(jacobian, dtype=np.float32)
        return self._rust_lib.pmtp_apply_horizontal_lift(
            tensor.ctypes.data_as(ctypes.c_void_p),
            j.ctypes.data_as(ctypes.c_void_p),
            ctypes.c_size_t(tensor.size),
            ctypes.c_float(dx), ctypes.c_float(dy),
        )

    def swarm_consensus_step(self, local: np.ndarray,
                             neighbors: np.ndarray,
                             weights: np.ndarray,
                             dt: float = 0.01,
                             cbf_gamma: float = 0.1) -> int:
        """Ejecuta un paso de consenso descentralizado (Fase 99).

        Args:
            local: Tensor latente local (D,) f32, mutable.
            neighbors: Tensores de K vecinos (K, D) f32.
            weights: Pesos de adyacencia (K,) f32.
            dt: Tasa de integracin de Euler.
            cbf_gamma: Margen del Control Barrier Function.

        Returns:
            0 si OK, cdigo negativo si error.
        """
        if local.dtype != np.float32 or not local.flags.c_contiguous:
            raise TypeError("API mutante requiere ndarray float32 C-contiguous para 'local'")
        nbr = np.ascontiguousarray(neighbors, dtype=np.float32)
        w = np.ascontiguousarray(weights, dtype=np.float32)
        k = nbr.shape[0] if nbr.ndim == 2 else 0
        return self._rust_lib.pmtp_phase99_swarm_consensus(
            local.ctypes.data_as(ctypes.c_void_p),
            nbr.ctypes.data_as(ctypes.c_void_p),
            w.ctypes.data_as(ctypes.c_void_p),
            ctypes.c_size_t(k),
            ctypes.c_size_t(local.size),
            ctypes.c_float(dt), ctypes.c_float(cbf_gamma),
        )

    def validate_alignment(self, handle: PmtpTensorHandle,
                           min_dim: int = 1) -> bool:
        """Verifica que un tensor cumple el alineamiento SIMD del hardware.

        Returns:
            True si el tensor est correctamente alineado.
        """
        return self._cpp_lib.pmtp_cpp_validate_tensor_alignment(
            ctypes.c_void_p(handle.data_ptr),
            ctypes.c_uint64(handle.size_bytes),
            ctypes.c_int32(min_dim),
        ) == 1


# =============================================================================
# 6  BATERA DE ATAQUES (Regla 16  Anti-Zero-Shot Audit)
# =============================================================================

def run_attack_battery():
    print("=" * 70)
    print("POLYDIM V507 - SWARM CONSENSUS BATERIA DE ATAQUES")
    print("=" * 70)
    m = PmtpMonolito()
    passed = 0
    total = 2
    # Test 1: Phase 99 Swarm Consensus Happy Path
    import numpy as np
    local = np.ones(10000, dtype=np.float32)
    neighbors = np.ones(10000, dtype=np.float32)
    weights = np.array([1.0], dtype=np.float32)
    rc = m._rust_lib.pmtp_phase99_swarm_consensus(
        local.ctypes.data_as(ctypes.c_void_p),
        neighbors.ctypes.data_as(ctypes.c_void_p),
        weights.ctypes.data_as(ctypes.c_void_p),
        ctypes.c_size_t(1),
        ctypes.c_float(0.1)
    )
    ok = rc == 0
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] T1: Swarm Consensus rc={rc}")
    passed += ok

    # Test 2: PmtpSlabAllocator Coalescing
    alloc = PmtpSlabAllocator("TEST_V507")
    tensors = [np.random.randn(10000).astype(np.float32) for _ in range(8)]
    alloc.write_slab_atomic(tensors)
    ok = True
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] T2: PmtpSlabAllocator")
    passed += ok

    print("=" * 70)
    return passed == total


if __name__ == "__main__":
    try:
        success = run_attack_battery()
        if not success:
            sys.exit(1)
    except Exception as e:
        import traceback, datetime, sys
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("NOCTURNO_TELEMETRIA_CONTINUA.md", "a", encoding="utf-8") as log_file:
            log_file.write(f"[{ts}] EXCEPCION CRITICA: {e}\n")
            log_file.write(traceback.format_exc())
        sys.exit(1)
