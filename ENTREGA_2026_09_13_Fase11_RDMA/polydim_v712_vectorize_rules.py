import os
import numpy as np
import re
import json
from sentence_transformers import SentenceTransformer

class RealRuleVectorizationEngine:
    def __init__(self):
        self.rules_data = []
        print("[LatentOS] Cargando motor local de embeddings (all-MiniLM-L6-v2)...")
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        
    def parse_markdown_file(self, filepath, source_name):
        if not os.path.exists(filepath):
            return
            
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        chunks = re.split(r'\n(?=\d+\.\s+\*\*|\#\#\s+|\#\#\#\s+)', content)
        
        for i, chunk in enumerate(chunks):
            chunk = chunk.strip()
            if len(chunk) > 20:
                self.rules_data.append({
                    'source': source_name,
                    'chunk_id': i,
                    'content': chunk
                })
                
    def vectorize_and_save(self, output_dir="matrix_state"):
        print(f"[LatentOS] Parseados {len(self.rules_data)} bloques semánticos reales.")
        os.makedirs(output_dir, exist_ok=True)
        
        with open(f"{output_dir}/rules_metadata.json", 'w', encoding='utf-8') as f:
            json.dump(self.rules_data, f, ensure_ascii=False, indent=2)
            
        print("[LatentOS] Calculando tensores S^(D-1) (Zero-Cost local)...")
        texts = [item['content'] for item in self.rules_data]
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        
        np.save(f"{output_dir}/agents_manifold.npy", embeddings)
        D = embeddings.shape[1]
        print(f"[LatentOS] Manifold S^({D-1}) cristalizado en {output_dir}/agents_manifold.npy con {len(self.rules_data)} vectores EXACTOS.")

if __name__ == "__main__":
    engine = RealRuleVectorizationEngine()
    engine.parse_markdown_file(r"E:\.agents\AGENTS.md", "AGENTS.md")
    engine.parse_markdown_file(r"C:\Users\eluithi\.gemini\config\PERMANENT_MEMORY.md", "PERMANENT_MEMORY.md")
    engine.vectorize_and_save()
