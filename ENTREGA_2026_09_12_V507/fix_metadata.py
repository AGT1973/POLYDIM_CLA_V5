import json

meta = {
  "id": "tradingnewtech/polydim-blind-consensus-live",
  "title": "POLYDIM Blind Consensus Live",
  "code_file": "live_consensus.py",
  "language": "python",
  "kernel_type": "script",
  "is_private": "true",
  "enable_gpu": "true",
  "enable_internet": "true",
  "dataset_sources": [],
  "competition_sources": [],
  "kernel_sources": []
}

with open(r'E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V507\KAGGLE_CONSENSUS\kernel-metadata.json', 'w', encoding='utf-8') as f:
    json.dump(meta, f, indent=2)

print("Metadata fixed without BOM.")
