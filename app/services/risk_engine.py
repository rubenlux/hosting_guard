"""
risk_engine — classifies a fix action by operational risk level.

Risk levels:
  low    → zero or near-zero downtime, fully reversible (nginx reload, docker start)
  medium → brief downtime (5–10s), automatically reversible (docker restart)
  high   → potential extended downtime or data impact — display only, no apply button
  none   → no executable action (manual fix required)

Only actions registered here are ever executed by execution_engine.
Adding a new action requires updating BOTH this module and execution_engine.py.
"""

# ── Action → risk metadata ────────────────────────────────────────────────────

_RISK_TABLE: dict[str, dict] = {
    "nginx_reload": {
        "risk_level":         "low",
        "estimated_downtime": "0s",
        "description":        "Recarga la configuración de Nginx sin detener el contenedor.",
    },
    "docker_start": {
        "risk_level":         "low",
        "estimated_downtime": "0s",
        "description":        "Inicia un contenedor detenido.",
    },
    "docker_restart": {
        "risk_level":         "medium",
        "estimated_downtime": "5–10s",
        "description":        "Reinicia el contenedor — limpia estado en memoria y procesos colgados.",
    },
    "wp_cache_flush": {
        "risk_level":         "low",
        "estimated_downtime": "0s",
        "description":        "Limpia el object cache de WordPress (wp cache flush). Sin downtime.",
    },
    "wp_rewrite_flush": {
        "risk_level":         "low",
        "estimated_downtime": "0s",
        "description":        "Regenera las reglas de rewrite de WordPress. Resuelve errores 404 en permalinks.",
    },
    "wp_transient_flush": {
        "risk_level":         "low",
        "estimated_downtime": "0s",
        "description":        "Elimina todos los transients expirados de la base de datos de WordPress.",
    },
    "manual": {
        "risk_level":         "none",
        "estimated_downtime": "n/a",
        "description":        "Requiere intervención manual del desarrollador.",
    },
}


def classify_risk(action: str) -> dict:
    """
    Return risk metadata for a given action id.
    Returns the 'manual' entry (risk_level='none') for unknown actions —
    unknown actions are never auto-executed, only described.
    """
    return _RISK_TABLE.get(action, _RISK_TABLE["manual"])


def get_risk_level(action: str) -> str:
    return classify_risk(action)["risk_level"]


def get_downtime(action: str) -> str:
    return classify_risk(action)["estimated_downtime"]


def is_auto_executable(action: str) -> bool:
    """True when execution_engine has a whitelisted handler for this action."""
    return action in _RISK_TABLE and action != "manual"
