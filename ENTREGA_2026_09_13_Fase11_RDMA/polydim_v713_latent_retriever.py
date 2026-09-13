import os
import json
import numpy as np
from sentence_transformers import SentenceTransformer

class LatentMemoryRetriever:
    def __init__(self, manifold_dir="matrix_state"):
        self.manifold_dir = manifold_dir
        self.model = None
        self.manifold = None
        self.metadata = None

    def load_memory(self):
        print("[LatentRetriever] Conectando al Manifold de Memoria S^(D-1)...")
        self.manifold = np.load(f"{self.manifold_dir}/agents_manifold.npy")
        with open(f"{self.manifold_dir}/rules_metadata.json", 'r', encoding='utf-8') as f:
            self.metadata = json.load(f)
        
        print("[LatentRetriever] Cargando motor embebido local...")
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        print(f"[LatentRetriever] Enlace completado. D = {self.manifold.shape[1]}")

    def query(self, text_query, top_k=2):
        # 1. Colapsar texto a tensor S^(D-1)
        query_vector = self.model.encode([text_query], normalize_embeddings=True)[0]
        
        # 2. Producto escalar en alta dimensión (Similitud Coseno pura, Zero-Drift)
        similarities = np.dot(self.manifold, query_vector)
        
        # 3. Top-K
        best_indices = np.argsort(similarities)[::-1][:top_k]
        
        print(f"\n[QUERY] '{text_query}'")
        for rank, idx in enumerate(best_indices):
            score = similarities[idx]
            chunk = self.metadata[idx]
            print(f"  -> Rank {rank+1} | Similitud: {score:.4f} | Origen: {chunk['source']}")
            print(f"     Extracto: {chunk['content'][:100]}...\n")
            
        return [self.metadata[i] for i in best_indices]

if __name__ == "__main__":
    retriever = LatentMemoryRetriever()
    retriever.load_memory()
    
    # Test 1: Alineamiento FFI (Debe traer la regla de Rust 64-bytes)
    retriever.query("Como aislo la memoria FFI en Rust para no tener False Sharing?")
    
    # Test 2: Protocolo Zero-Copy
    retriever.query("Que es el ghost protocol y como pasamos tensores sin json?")
