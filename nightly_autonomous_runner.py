import os, time, subprocess, sys
from datetime import datetime

TELEMETRY_FILE = "NOCTURNO_TELEMETRIA_CONTINUA.md"
POLL_INTERVAL = 10  # seconds

def log_telemetry(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    # Print encoding safely
    sys.stdout.buffer.write(line.encode("utf-8"))
    sys.stdout.flush()
    with open(TELEMETRY_FILE, "a", encoding="utf-8") as f:
        f.write(line)

def run_tests():
    # Try to run the Python monolith (which imports the DLLs)
    monolith = "polydim_v507_monolito.py"
    if not os.path.exists(monolith):
        return False, "Monolith missing."
    
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        res = subprocess.run([sys.executable, monolith], capture_output=True, text=True, encoding='utf-8', timeout=600, env=env)
        if res.returncode == 0:
            return True, "Execution OK."
        else:
            return False, f"Crash/Error (Code {res.returncode}): {res.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return False, "Timeout (Deadlock detected)."
    except Exception as e:
        return False, f"Exception: {str(e)}"

def main():
    log_telemetry("=== INICIANDO RUNNER NOCTURNO AUTÓNOMO (SOTA 2026) ===")
    log_telemetry("Objetivo: Testeo Asintótico y de Estrés de la Arquitectura V506/V507.")
    while True:
        success, info = run_tests()
        if success:
            log_telemetry(f"✅ CICLO EXITOSO: {info}")
        else:
            log_telemetry(f"❌ FALLA DETECTADA: {info}")
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()

