from typing import Dict, Any
from app.services.log_collector import get_container_logs
from app.core.log_parser import LogParser

async def build_debug_context(container_name: str, metrics: Dict[str, Any], limit_logs: int = 50) -> Dict[str, Any]:
    """
    Construye un contexto enriquecido para el motor de diagnóstico y AI.
    1. Obtiene métricas (pasadas como argumento).
    2. Descarga logs recientes.
    3. Parsea los logs buscando errores estructurados.
    """
    raw_logs = await get_container_logs(container_name, tail=limit_logs)
    parsed_errors = LogParser.parse_logs(raw_logs)

    # El "debug_context" final que el Orchestrator consumirá
    debug_context = {
        "metrics": metrics,
        "logs": {
            "has_errors": len(parsed_errors) > 0,
            "parsed_errors": parsed_errors,
            # Proveer contexto puro (ultimas 30 lineas) en caso de que los regex fallen y el LLM necesite inferir
            "recent_raw_snippet": "\n".join(raw_logs.splitlines()[-30:]) 
        }
    }
    
    return debug_context
