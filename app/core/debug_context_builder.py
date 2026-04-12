from typing import Dict, Any
from app.services.log_collector import get_container_logs
from app.core.log_parser import LogParser

async def build_debug_context(container_name: str, metrics: Dict[str, Any], limit_logs: int = 50) -> Dict[str, Any]:
    """
    Construye un contexto enriquecido para el motor de diagnóstico y AI.
    """
    print(f"[DEBUG] Iniciando build_debug_context para: {container_name}")
    
    raw_logs = await get_container_logs(container_name, tail=limit_logs)
    print(f"[DEBUG] RAW LOGS (últimas 2 líneas): {raw_logs.splitlines()[-2:] if raw_logs else 'VACÍO'}")
    
    parsed_errors = LogParser.parse_logs(raw_logs)

    # Only application-sourced errors count as real errors.
    # dev_noise (source maps) and external_probe (bots) are logged but never
    # affect has_errors — otherwise the entire pipeline treats noise as failures.
    actionable_errors = [
        e for e in parsed_errors
        if e.get("source") == "application"
    ]

    print(f"[DEBUG] PARSED ERRORS: total={len(parsed_errors)} actionable={len(actionable_errors)}")

    # El "debug_context" final que el Orchestrator consumirá
    debug_context = {
        "metrics": metrics,
        "logs": {
            "has_errors": len(actionable_errors) > 0,
            "parsed_errors": parsed_errors,          # full list — for display/debug
            "actionable_errors": actionable_errors,  # filtered list — for AI pipeline
            "recent_raw_snippet": "\n".join(raw_logs.splitlines()[-30:])
        }
    }

    print(f"[DEBUG] DEBUG CONTEXT BUILT - Errores reales: {len(actionable_errors)}")
    return debug_context
