import os
from huggingface_hub import snapshot_download
import datetime

print(f"[{datetime.datetime.now().isoformat()}] INITIATING HISTORICAL GLOBAL AI CONVERGENCE DOWNLOAD")

base_dir = r"E:\POLYDIM_EINSOF\models"
os.makedirs(base_dir, exist_ok=True)

models_to_download = [
    ("microsoft/Phi-3-mini-4k-instruct", "phi_3_mini"),
    ("Qwen/Qwen2.5-1.5B-Instruct", "qwen_2_5_1_5B")
]

for repo_id, folder_name in models_to_download:
    target_dir = os.path.join(base_dir, folder_name)
    print(f"[{datetime.datetime.now().isoformat()}] Downloading {repo_id} to {target_dir}...")
    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=target_dir,
            local_dir_use_symlinks=False,
            ignore_patterns=["*.gguf", "*.safetensors.index.json", "*fp16*"] # Try to minimize if possible, but keep main safetensors
        )
        print(f"[{datetime.datetime.now().isoformat()}] SUCCESS: {repo_id} downloaded.")
    except Exception as e:
        print(f"[{datetime.datetime.now().isoformat()}] ERROR downloading {repo_id}: {str(e)}")

print(f"[{datetime.datetime.now().isoformat()}] DOWNLOAD SEQUENCE COMPLETED.")
