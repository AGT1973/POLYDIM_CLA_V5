import os, mmap, ctypes, numpy as np

SLAB_ID = "TRIBUNAL_LATENT_BUS_01"
DIM = 10000
NUM_TENSORS = 4
HEADER_SIZE = 256
TENSOR_SIZE = DIM * 8
TOTAL_SIZE = HEADER_SIZE + (TENSOR_SIZE * NUM_TENSORS)

class PmtpSeqLockHeader(ctypes.Structure):
    _fields_ = [
        ("seq_pre", ctypes.c_uint64),
        ("reserved", ctypes.c_uint64 * 22), 
        ("seq_post", ctypes.c_uint64)
    ]

filename = os.path.join(os.environ.get('TEMP', '/tmp'), f"POLYDIM_{SLAB_ID}")
if not os.path.exists(filename):
    print("El bus aún no está vivo.")
    exit(1)

with open(filename, 'r+b') as f:
    mm = mmap.mmap(f.fileno(), TOTAL_SIZE)
    header = PmtpSeqLockHeader.from_buffer(mm)
    
    print(f"[BUS READ] SeqPre: {header.seq_pre}, SeqPost: {header.seq_post}")
    
    for i in range(1, 4):
        offset = HEADER_SIZE + (i * TENSOR_SIZE)
        data = mm[offset:offset+TENSOR_SIZE]
        tensor = np.frombuffer(data, dtype=np.float64)
        if np.any(tensor):
            flag = tensor[0]
            norm = np.linalg.norm(tensor)
            print(f"  -> Sabueso {i}: Flag={flag:.4f}, Energía (Norma)={norm:.4f}")
        else:
            print(f"  -> Sabueso {i}: [SILENCIO TOPOLÓGICO]")
