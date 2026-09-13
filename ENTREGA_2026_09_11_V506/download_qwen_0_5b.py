# download_qwen_0_5b.py
import os
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_DIR = r"E:\POLYDIM_EINSOF\models\qwen_0_5b"
os.makedirs(MODEL_DIR, exist_ok=True)

model_id = "Qwen/Qwen2-0.5B"

print(f"Descargando Tokenizer de {model_id}...")
tokenizer = AutoTokenizer.from_pretrained(model_id)
tokenizer.save_pretrained(MODEL_DIR)

print(f"Descargando Modelo {model_id} (esto puede demorar unos minutos)...")
# Usamos torch_dtype="auto" para que descargue y guarde los pesos de forma optimizada
model = AutoModelForCausalLM.from_pretrained(model_id)
model.save_pretrained(MODEL_DIR)

print(f"Descarga finalizada. Modelo guardado localmente en: {MODEL_DIR}")
