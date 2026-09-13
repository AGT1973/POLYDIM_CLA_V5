import torch
import numpy as np
import time
from transformers import AutoModelForCausalLM
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')
logger = logging.getLogger('NODE_A_PHI3')

logger.info('='*60)
logger.info('POLYDIM FULL-DUPLEX CLOUD - NODE A (MICROSOFT PHI-3)')
logger.info('='*60)

logger.info('Loading Phi-3-mini-4k-instruct on GPU...')
model = AutoModelForCausalLM.from_pretrained('microsoft/Phi-3-mini-4k-instruct', torch_dtype=torch.float16, device_map='cuda:0')
logger.info(f'Model loaded. Hidden size: {model.config.hidden_size}')

D = model.config.hidden_size  # 3072
SEQ = 16

logger.info(f'Generating latent thought tensor (1, {SEQ}, {D})...')
estado_latente = torch.randn(1, SEQ, D, dtype=torch.float16)
norm_original = torch.norm(estado_latente).item()
logger.info(f'Norm L2 of injected tensor: {norm_original:.6f}')

# Pass through MLP layer 0 (pure geometric, no RoPE needed)
logger.info('Passing tensor through Phi-3 MLP Layer 0 (Geometric Mutation)...')
with torch.no_grad():
    mlp = model.model.layers[0].mlp
    estado_mutado = mlp(estado_latente.to('cuda:0'))

norm_mutada = torch.norm(estado_mutado).item()
logger.info(f'Norm L2 after MLP mutation: {norm_mutada:.6f}')

# Save raw binary tensor to disk (the "letter" for Node B)
tensor_bytes = estado_mutado.cpu().numpy().tobytes()
output_path = '/kaggle/working/tensor_node_a.bin'
with open(output_path, 'wb') as f:
    f.write(tensor_bytes)

# Save metadata
import json
meta = {
    'shape': [1, SEQ, D],
    'dtype': 'float16',
    'norm_original': norm_original,
    'norm_mutada': norm_mutada,
    'model': 'microsoft/Phi-3-mini-4k-instruct',
    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S%z')
}
with open('/kaggle/working/tensor_meta.json', 'w') as f:
    json.dump(meta, f, indent=2)

logger.info(f'Tensor saved to {output_path} ({len(tensor_bytes)} bytes)')
logger.info('NODE A MISSION COMPLETE. Tensor is waiting for Node B.')
