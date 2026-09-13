import os
from huggingface_hub import snapshot_download

base_dir = r"E:\POLYDIM_EINSOF\models"

models_to_download = [
    ("microsoft/Phi-3-mini-4k-instruct", "phi_3_mini"),
    ("Qwen/Qwen2.5-1.5B-Instruct", "qwen_2_5_1_5B")
]

for repo_id, folder_name in models_to_download:
    target_dir = os.path.join(base_dir, folder_name)
    print(f"Fetching missing index files for {repo_id}...")
    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=target_dir,
            local_dir_use_symlinks=False,
            allow_patterns=["*.safetensors.index.json"]
        )
    except Exception as e:
        print(f"Error fetching for {repo_id}: {e}")

print("Index fetch complete.")
