import json
with open(r'E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V507\KAGGLE_NODE_B\kernel-metadata.json', 'r', encoding='utf-8-sig') as f:
    d = json.load(f)
with open(r'E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V507\KAGGLE_NODE_B\kernel-metadata.json', 'w', encoding='utf-8') as f:
    json.dump(d, f, indent=2)
