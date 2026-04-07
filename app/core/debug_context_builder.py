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
    print(f"[DEBUG] PARSED ERRORS: {parsed_errors}")

    # El "debug_context" final que el Orchestrator consumirá
    debug_context = {
        "metrics": metrics,
        "logs": {
            "has_errors": len(parsed_errors) > 0,
            "parsed_errors": parsed_errors,
            "recent_raw_snippet": "\n".join(raw_logs.splitlines()[-30:]) 
        }
    }
    
    print(f"[DEBUG] DEBUG CONTEXT BUILT - Errores encontrados: {len(parsed_errors)}")
    return debug_context
