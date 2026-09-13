import json
meta = {
  'id': 'tradingnewtech/polydim-node-a-phi3',
  'title': 'POLYDIM Node A Phi3',
  'code_file': 'node_a.py',
  'language': 'python',
  'kernel_type': 'script',
  'is_private': 'true',
  'enable_gpu': 'true',
  'enable_internet': 'false',
  'dataset_sources': [],
  'competition_sources': [],
  'kernel_sources': []
}
with open(r'E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V507\KAGGLE_NODE_A_V2\kernel-metadata.json', 'w', encoding='utf-8') as f:
    json.dump(meta, f, indent=2)
