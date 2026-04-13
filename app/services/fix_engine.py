"""
fix_engine — heuristic FixProposal builder.

Maps (failure_type, container_status, metrics) → FixProposal using a
deterministic decision table.  No LLM calls, no randomness.

Decision table (in priority order):
  1. container not running           → docker_start (low risk)
  2. failure_type == "runtime"       → docker_restart (medium risk)
  3. failure_type == "infra"         → docker_restart (container may be OOM/stuck)
  4. failure_type == "unknown"       → nginx_reload first (softest option)
  5. failure_type in (syntax/import) → manual (can_auto_fix=False)
  6. no actionable errors            → None (nothing to fix)

Why docker_restart for "infra":
  OOM-killed or CPU-pinned processes persist across nginx reloads.
  A restart flushes the process table and lets the container allocate
  fresh memory — the safest recoverable action short of a full redeploy.

Why nginx_reload for "unknown":
  When the diagnosis can't classify the root cause, reloading nginx is
  the lowest-risk operation that resolves a broad class of transient issues
  (stuck worker, config drift) without service disruption.
"""
import logging

from app.models.fix import FixProposal
from app.services.risk_engine import get_risk_level, get_downtime, is_auto_executable

logger = logging.getLogger(__name__)

# ── Command builders (mirrored in execution_engine whitelist) ─────────────────

def _nginx_reload_cmd(container: str) -> list[str]:
    return ["docker", "exec", container, "nginx", "-s", "reload"]

def _docker_restart_cmd(container: str) -> list[str]:
    return ["docker", "restart", container]

def _docker_start_cmd(container: str) -> list[str]:
    return ["docker", "start", container]


# ── Public API ─────────────────────────────────────────────────────────────────

def build_fix_proposal(
    *,
    hosting_id: int,
    container_name: str,
    fingerprint: str,
    failure_type: str,
    container_status: str,       # "running" | "exited" | "paused" | "unknown"
    cpu: float = 0.0,
    ram: float = 0.0,
    score: int = 100,
    quality_score: float = 0.0,  # from error_quality_score() — gates weak-signal fixes
) -> FixProposal | None:
    """
    Build a FixProposal from diagnosis context.
    Returns None when no fix is applicable (clean system).

    Never raises — all exceptions are caught and logged.
    Caller should treat None as "no fix available".
    """
    try:
        return _select_fix(
            hosting_id=hosting_id,
            container_name=container_name,
            fingerprint=fingerprint,
            failure_type=failure_type,
            container_status=container_status,
            cpu=cpu,
            ram=ram,
            score=score,
            quality_score=quality_score,
        )
    except Exception as exc:
        logger.warning("fix_engine: proposal build failed: %s", exc)
        return None


def _select_fix(
    *,
    hosting_id: int,
    container_name: str,
    fingerprint: str,
    failure_type: str,
    container_status: str,
    cpu: float,
    ram: float,
    score: int,
    quality_score: float,
) -> FixProposal | None:

    # ── Fix Engine Gate ───────────────────────────────────────────────────────
    # Gate 1 — healthy system: score >= 95 + running → nothing to fix.
    if score >= 95 and container_status == "running":
        return None

    # Gate 2 — weak signal: quality < 8 means there's not enough evidence
    # of a real failure to justify any automated action (even nginx_reload).
    # Exceptions: container is stopped (clear infra failure regardless of quality),
    # or failure_type is a hard-typed exception (syntax/import — those are manual anyway).
    if quality_score < 8 and container_status == "running" and failure_type not in ("syntax", "import"):
        return None

    # ── 1. Container is not running → start it ────────────────────────────────
    if container_status not in ("running",):
        action = "docker_start"
        return FixProposal(
            fingerprint=fingerprint,
            hosting_id=hosting_id,
            container_name=container_name,
            failure_type=failure_type or "infra",
            risk_level=get_risk_level(action),
            can_auto_fix=is_auto_executable(action),
            title="Iniciar contenedor",
            description="El contenedor está detenido. Iniciarlo restaura el servicio sin pérdida de datos.",
            action=action,
            commands=_docker_start_cmd(container_name),
            rollback_commands=[],     # rollback: nothing — don't re-stop it
            estimated_downtime=get_downtime(action),
        )

    # ── Score guard ───────────────────────────────────────────────────────────
    # If the health engine says the system is healthy (score >= 90) there's no
    # actionable infrastructure problem worth restarting over.  This prevents
    # the AI from proposing docker_restart when a single irrelevant 404 inflated
    # the error list but the system is objectively functioning correctly.
    if score >= 90 and failure_type in ("infra", "runtime", "unknown"):
        return None

    # ── 2. Runtime errors → restart clears stuck processes / bad state ────────
    if failure_type == "runtime":
        action = "docker_restart"
        return FixProposal(
            fingerprint=fingerprint,
            hosting_id=hosting_id,
            container_name=container_name,
            failure_type=failure_type,
            risk_level=get_risk_level(action),
            can_auto_fix=is_auto_executable(action),
            title="Reiniciar contenedor",
            description=(
                "Un error de runtime indica un proceso fallido o estado corrupto en memoria. "
                "Reiniciar el contenedor restaura el estado inicial."
            ),
            action=action,
            commands=_docker_restart_cmd(container_name),
            rollback_commands=_docker_start_cmd(container_name),
            estimated_downtime=get_downtime(action),
        )

    # ── 3. Infra failure → restart (OOM, CPU runaway, container crash) ────────
    if failure_type == "infra":
        action = "docker_restart"
        return FixProposal(
            fingerprint=fingerprint,
            hosting_id=hosting_id,
            container_name=container_name,
            failure_type=failure_type,
            risk_level=get_risk_level(action),
            can_auto_fix=is_auto_executable(action),
            title="Reiniciar contenedor (fallo de infraestructura)",
            description=(
                "El contenedor está experimentando presión de recursos o un fallo de infraestructura. "
                "Reiniciarlo libera memoria y detiene procesos descontrolados."
            ),
            action=action,
            commands=_docker_restart_cmd(container_name),
            rollback_commands=_docker_start_cmd(container_name),
            estimated_downtime=get_downtime(action),
        )

    # ── 4. Unknown failure type → nginx reload (softest option, 0s downtime) ──
    if failure_type == "unknown" and score < 80:
        action = "nginx_reload"
        return FixProposal(
            fingerprint=fingerprint,
            hosting_id=hosting_id,
            container_name=container_name,
            failure_type=failure_type,
            risk_level=get_risk_level(action),
            can_auto_fix=is_auto_executable(action),
            title="Recargar Nginx",
            description=(
                "No se pudo clasificar la causa raíz. Recargar Nginx resuelve "
                "la mayoría de fallos transitorios sin tiempo de inactividad."
            ),
            action=action,
            commands=_nginx_reload_cmd(container_name),
            rollback_commands=_nginx_reload_cmd(container_name),  # idempotent
            estimated_downtime=get_downtime(action),
        )

    # ── 5. Syntax / import errors → manual only (developer must fix code) ─────
    if failure_type in ("syntax", "import"):
        return FixProposal(
            fingerprint=fingerprint,
            hosting_id=hosting_id,
            container_name=container_name,
            failure_type=failure_type,
            risk_level="none",
            can_auto_fix=False,
            title="Corrección manual requerida",
            description=(
                "Este error requiere que un desarrollador corrija el código fuente. "
                "No es posible aplicar un fix automático sin modificar archivos."
            ),
            action="manual",
            commands=[],
            rollback_commands=[],
            estimated_downtime="n/a",
        )

    # ── 6. No actionable condition → no fix needed ────────────────────────────
    return None
