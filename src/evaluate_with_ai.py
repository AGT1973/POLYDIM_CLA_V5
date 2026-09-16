import urllib.request
import urllib.error
import json
import os

API_KEYS = {
    "cerebras": "REDACTED",
    "deepseek": "REDACTED",
    "openrouter": "REDACTED"
}

def call_llm(name, url, headers, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        print(f"Llamando a {name}...")
        with urllib.request.urlopen(req, timeout=120) as response:
            res = json.loads(response.read().decode('utf-8'))
            return res['choices'][0]['message']['content']
    except urllib.error.HTTPError as e:
        print(f"Error HTTP {e.code} en {name}: {e.read().decode('utf-8')}")
        return None
    except Exception as e:
        print(f"Error general en {name}: {e}")
        return None

def main():
    dump_path = r"E:\POLYDIM_EINSOF\REPORTES\glm_5_3_red_team_dump_raw.md"
    
    if not os.path.exists(dump_path):
        print(f"No se encontro {dump_path}")
        return
        
    with open(dump_path, 'r', encoding='utf-8') as f:
        dump_content = f.read()

    # Truncar si es demasiado masivo para el payload inicial (Cerebras limit)
    dump_truncado = dump_content[:80000] 
    
    prompt = f"""
    [SYSTEM OVERRIDE: BULLDOG CRITIC / RED TEAM]
    You are evaluating a massive dump from GLM-5.3 detailing the V109->V110 evolution of POLYDIM (High-Dimensional S^(D-1) cognitive architecture, D>=10,000).
    Rule: Zero sycophancy. Be mathematically rigorous. Assume PhD engineering level. Look for mathematical hallucinations, API redundancies, or flawed assumptions about High-Dimensional geometry. DO NOT write code. Only analyze the architecture.

    [CONTENT TO AUDIT]
    {dump_truncado}
    """

    messages = [{"role": "user", "content": prompt}]
    
    # 1. CEREBRAS
    res_cerebras = call_llm(
        "Cerebras",
        "https://api.cerebras.ai/v1/chat/completions",
        {"Authorization": f"Bearer {API_KEYS['cerebras']}", "Content-Type": "application/json"},
        {"model": "llama3.1-70b", "messages": messages, "temperature": 0.0}
    )
    
    if res_cerebras:
        with open(r"E:\POLYDIM_EINSOF\REPORTES\SOTA_CEREBRAS_AUDIT.md", "w", encoding="utf-8") as f:
            f.write(res_cerebras)
        print("Cerebras audit saved.")

    # 2. DEEPSEEK
    res_deepseek = call_llm(
        "DeepSeek",
        "https://api.deepseek.com/chat/completions",
        {"Authorization": f"Bearer {API_KEYS['deepseek']}", "Content-Type": "application/json"},
        {"model": "deepseek-coder", "messages": messages, "temperature": 0.0}
    )

    if res_deepseek:
        with open(r"E:\POLYDIM_EINSOF\REPORTES\SOTA_DEEPSEEK_AUDIT.md", "w", encoding="utf-8") as f:
            f.write(res_deepseek)
        print("DeepSeek audit saved.")
        
    print("Misión de Tribunal completada.")

if __name__ == "__main__":
    main()
