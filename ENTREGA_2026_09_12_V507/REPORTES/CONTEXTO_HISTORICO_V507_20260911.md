# CONTEXTO HISTORICO - SESION V507 - 2026-09-11

## TRABAJO COMPLETADO

Los 5 archivos V507 estan commiteados en master local (E:\POLYDIM_EINSOF):
- polydim_v507_monolito.py: ASLR fix (offsets relativos u64) + CAS Rust FFI
- kernel_rust_v507.rs.txt: Riemannian CBF (P_x = I - x x^T) + NaN guard
- kernel_cpp_v507.cpp.txt: XCR0 + _xgetbv(0) OS check + BF16 align relax
- polydim_triton_kernel_v507.py: ThreadPoolExecutor persistente (fix #45)
- readme_first_v507.md: Bitacora tecnica V507

## PROBLEMA PENDIENTE: GITHUB HTTP 500

CAUSA: Repo local tiene 3.49 GB en pack objects (datasets .dat/.pt/.npy en _HISTORICO/).
SOLUCION PREPARADA: Branch orphan limpio llamado master_clean_v2 ya creado y commiteado.
ACCION INMEDIATA AL INICIAR NUEVA SESION:
  git -C E:\POLYDIM_EINSOF push origin master_clean_v2:master --force

## CREDENCIALES ACTIVAS

Kimi: [REDACTED_API_KEY]
  -> Inyectada en C:\Users\eluithi\.gemini\config\mcp_config.json (KIMI_API_KEY_1)
  -> Antigravity necesita REINICIARSE para que el proceso mcp_kimi.exe la tome.

OpenRouter: [REDACTED_OPENROUTER_KEY]
  -> Ya activa en mcp_config.json (OPENROUTER_API_KEY_1)

DeepSeek: [REDACTED_API_KEY]
  -> En mcp_config.json (DEEPSEEK_API_KEY_1)
  -> DeepSeek V4.1 Flash activo desde Sept 10 a precio reducido.

GitHub PAT: [REDACTED_GITHUB_PAT] (user AGY_09)
  -> Remote configurado en el repo.

## PROXIMA SESION: PASOS EN ORDEN

1. Reiniciar Antigravity para que Kimi MCP tome la key nueva.
2. Ejecutar: git -C E:\POLYDIM_EINSOF push origin master_clean_v2:master --force
3. Lanzar auditoría Kimi del CBF Riemanniano y offsets relativos SHM.
4. Modo Nocturno completo con Kimi+DeepSeek+OpenRouter sobre V507.

## GIT STATUS LOCAL

Branch activa: master_clean_v2 (orphan, sin binarios pesados)
Remote origin: https://AGT1973@github.com/AGT1973/POLYDIM_CLA_V5.git

