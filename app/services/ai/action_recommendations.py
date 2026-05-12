"""
Phase 3A: Rule-based action recommendation generator.

Generates action_recommendations from open system_incidents that have a
completed ai_diagnosis. All recommendations require human approval.
execution_allowed is ALWAYS false in this phase.

Prohibited in this phase:
  - executing commands
  - restarting containers
  - blocking IPs
  - modifying Protection Mode
  - modifying DNS
  - deleting files or containers
  - resolving incidents automatically
  - touching docker-compose
  - any DB write except action_recommendations INSERT/UPDATE
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from app.services.ai.action_safety_classifier import classify_action

logger = logging.getLogger(__name__)

# Bump this string whenever rule copy or action_type mapping changes.
# Including it in the idempotency hash causes existing pending rows to be
# superseded and new rows (with updated copy) to be created automatically.
RULES_VERSION = "actions_v2"

# ── Owner / responsibility map ─────────────────────────────────────────────────
# Communicates who must act. Never implies HostingGuard will act automatically.

_OWNER_MAP: dict[str, str] = {
    "customer_fix":                   "cliente",
    "dependency_fix":                 "cliente",
    "branch_correction":              "cliente",
    "manual_check":                   "admin",
    "admin_review":                   "admin",
    "monitor":                        "admin",
    "site_recovery_monitor":          "admin",
    "security_review":                "seguridad",
    "enable_protection_mode_monitor": "admin",
    "enable_protection_mode_protect": "admin",
    "block_ip_candidate":             "seguridad",
    "redeploy_candidate":             "admin",
    "restart_container_suggestion":   "admin",
    "notify_customer":                "admin",
    "check_credentials":              "cliente",
    "escalate_to_admin":              "admin",
}

_OWNER_LABEL: dict[str, str] = {
    "cliente":   "Cliente",
    "admin":     "Admin",
    "seguridad": "Seguridad / Admin",
}


def _derive_owner(action_type: str) -> str:
    return _OWNER_MAP.get(action_type, "admin")


# ── Rule table ─────────────────────────────────────────────────────────────────
# No text should imply automatic execution by HostingGuard.
# Preferred verbs: "se recomienda", "verificar", "revisar", "considerar".

_RULES: dict[str, list[dict]] = {
    "node_sass_incompatible": [
        {
            "action_type": "dependency_fix",
            "title": "Migrar node-sass a sass",
            "description": (
                "El proyecto usa node-sass, una dependencia antigua incompatible con versiones "
                "modernas de Node. Se recomienda reemplazarla por 'sass' en el package.json del "
                "cliente y volver a intentar el build."
            ),
            "expected_impact": (
                "El build debería avanzar si no existen otros errores de dependencias."
            ),
            "rollback_notes": (
                "Revertir el cambio en package.json y ejecutar npm install en el repositorio."
            ),
            "safety_notes": (
                "Esta acción debe realizarse en el repositorio del cliente. "
                "HostingGuard no modifica el código fuente."
            ),
        },
    ],
    "github_branch_not_found": [
        {
            "action_type": "customer_fix",
            "title": "Corregir rama de GitHub",
            "description": (
                "La rama indicada en la configuración de deploy no existe en el repositorio "
                "remoto. Verificar si la rama correcta es 'main', 'master' u otra, y actualizar "
                "la configuración del sitio."
            ),
            "expected_impact": (
                "El deploy comenzará a funcionar una vez corregido el nombre de la rama."
            ),
            "rollback_notes": "No aplica — cambio de configuración reversible.",
            "safety_notes": (
                "No se modifica ningún contenedor ni dato de producción. "
                "El cliente debe actualizar la rama desde su panel de configuración."
            ),
        },
    ],
    "github_private_repo_unauthorized": [
        {
            "action_type": "customer_fix",
            "title": "Verificar acceso al repositorio GitHub",
            "description": (
                "HostingGuard no pudo acceder al repositorio. Puede que la URL no exista, "
                "que el repositorio sea privado o que falten permisos de lectura. "
                "Se recomienda verificar URL, visibilidad del repositorio y credenciales de acceso."
            ),
            "expected_impact": (
                "Corregir el acceso permitirá volver a intentar el deploy."
            ),
            "rollback_notes": "No aplica — cambio de configuración reversible.",
            "safety_notes": (
                "Esta recomendación no modifica el repositorio ni ejecuta comandos. "
                "El usuario debe verificar URL, visibilidad o permisos del repositorio."
            ),
        },
    ],
    "build_failed": [
        {
            "action_type": "manual_check",
            "title": "Revisar logs de build",
            "description": (
                "El build falló por un error no clasificado automáticamente. "
                "Se recomienda revisar los logs de deploy para identificar la causa raíz "
                "antes de tomar cualquier acción."
            ),
            "expected_impact": (
                "La revisión manual permite determinar si el fix requiere acción del cliente "
                "o del administrador."
            ),
            "rollback_notes": "No aplica — acción de diagnóstico sin efecto directo.",
            "safety_notes": "Acción de solo lectura. No modifica nada.",
        },
    ],
    "site_critical": [
        {
            "action_type": "admin_review",
            "title": "Revisar salud del contenedor",
            "description": (
                "El sitio está en estado crítico. Se recomienda inspeccionar el estado del "
                "contenedor, los logs y las métricas antes de decidir una acción operativa."
            ),
            "expected_impact": (
                "Permite determinar si se requiere redeploy, restauración de backup "
                "o intervención de infraestructura."
            ),
            "rollback_notes": "No aplica — acción de diagnóstico.",
            "safety_notes": "No modifica el estado del sistema.",
        },
        {
            "action_type": "redeploy_candidate",
            "title": "Considerar redeploy desde último commit estable",
            "description": (
                "Si la revisión confirma corrupción del contenedor, se recomienda considerar "
                "un redeploy desde el último commit estable. Esta acción debe ejecutarse "
                "manualmente por un administrador desde el panel de deploy."
            ),
            "expected_impact": (
                "Restaura el sitio al último estado funcional conocido si el problema "
                "está en el contenedor."
            ),
            "rollback_notes": (
                "Guardar backup antes del redeploy. El redeploy puede sobreescribir "
                "cambios locales no commiteados."
            ),
            "safety_notes": (
                "El administrador debe ejecutar manualmente desde el panel de deploy. "
                "HostingGuard no inicia el redeploy automáticamente."
            ),
        },
    ],
    "site_recovery": [
        {
            "action_type": "monitor",
            "title": "Monitorear recuperación del sitio",
            "description": (
                "El sitio se estabilizó. No se recomienda acción inmediata. "
                "Se sugiere monitorear métricas de CPU, RAM y uptime durante las "
                "próximas 24 horas para confirmar estabilidad."
            ),
            "expected_impact": (
                "Detección temprana de regresión si el sitio vuelve a degradarse."
            ),
            "rollback_notes": "No aplica — acción de monitoreo pasivo.",
            "safety_notes": "No modifica el sistema.",
        },
    ],
    "security_attack": [
        {
            "action_type": "security_review",
            "title": "Revisar eventos de seguridad y logs de acceso",
            "description": (
                "Se detectó actividad potencialmente maliciosa. Se recomienda revisar "
                "los eventos de seguridad, IPs involucradas y paths afectados antes "
                "de tomar cualquier acción."
            ),
            "expected_impact": (
                "Identificar el patrón de ataque y evaluar si conviene activar Protection Mode."
            ),
            "rollback_notes": "No aplica.",
            "safety_notes": "Acción de solo lectura. No bloquea ni modifica tráfico.",
        },
        {
            "action_type": "enable_protection_mode_monitor",
            "title": "Considerar activar Protection Mode en modo monitor",
            "description": (
                "Protection Mode en modo 'monitor' registra peticiones sospechosas sin "
                "bloquearlas, permitiendo evaluar el impacto antes de activar bloqueo real. "
                "Requiere aprobación manual desde el panel de hosting."
            ),
            "expected_impact": (
                "Mayor visibilidad sobre el ataque sin riesgo de falsos positivos."
            ),
            "rollback_notes": "Desactivar Protection Mode desde el panel de hosting.",
            "safety_notes": (
                "Modo monitor no bloquea tráfico. "
                "El administrador debe activarlo manualmente."
            ),
        },
    ],
    "wordpress_malware": [
        {
            "action_type": "security_review",
            "title": "Revisar archivos WordPress por indicadores de malware",
            "description": (
                "Se detectaron posibles indicadores de malware en el sitio WordPress. "
                "Se recomienda revisar los logs de seguridad y los archivos del sitio "
                "antes de tomar cualquier acción."
            ),
            "expected_impact": (
                "Identificar el alcance de la infección y los archivos comprometidos."
            ),
            "rollback_notes": "Considerar restaurar desde backup limpio si se confirma infección.",
            "safety_notes": "No modifica archivos. Acción de diagnóstico.",
        },
        {
            "action_type": "enable_protection_mode_monitor",
            "title": "Considerar activar Protection Mode para visibilidad",
            "description": (
                "Activar modo monitor permite detectar intentos de exfiltración de datos "
                "mientras se realiza el análisis forense. Requiere aprobación manual."
            ),
            "expected_impact": (
                "Mayor visibilidad sobre tráfico saliente anómalo."
            ),
            "rollback_notes": "Desactivar Protection Mode desde el panel de hosting.",
            "safety_notes": (
                "No bloquea tráfico en modo monitor. "
                "El administrador debe activarlo manualmente."
            ),
        },
    ],
}

# Fallback for incident_types not in _RULES
_DEFAULT_RULE: list[dict] = [
    {
        "action_type": "manual_check",
        "title": "Revisión manual del incidente",
        "description": (
            "Este tipo de incidente no tiene recomendaciones automáticas. "
            "Se recomienda que un administrador revise los detalles manualmente."
        ),
        "expected_impact": "Diagnóstico directo del problema.",
        "rollback_notes": "No aplica.",
        "safety_notes": "Acción de solo lectura.",
    },
]


def _idempotency_hash(
    incident_id: int,
    diagnosis_id: int,
    action_type: str,
    context_hash: str,
    rules_version: str = RULES_VERSION,
) -> str:
    key = f"{incident_id}:{diagnosis_id}:{action_type}:{context_hash}:{rules_version}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def _supersede_stale_pending(
    conn, incident_id: int, action_type: str, new_hash: str
) -> int:
    """
    Mark pending_approval rows with a different context_hash as superseded.
    Approved and rejected rows are never touched.
    Returns the number of rows updated.
    """
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE action_recommendations
           SET status = 'superseded', updated_at = %s
         WHERE incident_id = %s
           AND action_type = %s
           AND status = 'pending_approval'
           AND context_hash != %s
        """,
        (datetime.now(timezone.utc), incident_id, action_type, new_hash),
    )
    return cur.rowcount


def _has_approved(conn, incident_id: int, action_type: str) -> bool:
    """True if any approved row exists for this incident+action_type."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1 FROM action_recommendations
         WHERE incident_id = %s AND action_type = %s AND status = 'approved'
         LIMIT 1
        """,
        (incident_id, action_type),
    )
    return cur.fetchone() is not None


def _fetch_diagnosable_incidents(conn, limit: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT si.incident_id, si.source_type, si.incident_type, si.severity,
               si.title, si.hosting_id, si.user_id,
               diag.id            AS diagnosis_id,
               diag.context_hash  AS context_hash,
               diag.confidence    AS confidence
          FROM system_incidents si
          JOIN LATERAL (
            SELECT id, context_hash, confidence
              FROM ai_diagnosis
             WHERE incident_id = si.incident_id
               AND status = 'active'
             ORDER BY created_at DESC
             LIMIT 1
          ) diag ON TRUE
         WHERE si.status = 'open'
           AND si.severity != 'info'
         ORDER BY
           CASE si.severity
             WHEN 'critical' THEN 0 WHEN 'high' THEN 1
             WHEN 'medium'   THEN 2 WHEN 'warning' THEN 3
             ELSE 4
           END,
           si.last_seen DESC
         LIMIT %s
        """,
        (limit,),
    )
    return [dict(r) for r in cur.fetchall()]


def _existing_rec_hashes(conn, incident_id: int) -> set[str]:
    cur = conn.cursor()
    cur.execute(
        "SELECT context_hash FROM action_recommendations WHERE incident_id = %s AND context_hash IS NOT NULL",
        (incident_id,),
    )
    return {row["context_hash"] for row in cur.fetchall()}


def _insert_recommendation(conn, *, incident: dict, action: dict, safety: dict, idem_hash: str) -> None:
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    cur.execute(
        """
        INSERT INTO action_recommendations
            (incident_id, diagnosis_id, action_type, title, description,
             source_type, incident_type,
             recommendation_source, confidence, reason,
             expected_impact, rollback_notes, safety_notes,
             risk_level, requires_approval, status,
             payload, context_hash, rules_version, created_at, updated_at)
        VALUES
            (%s, %s, %s, %s, %s,
             %s, %s,
             'rule_based', %s, %s,
             %s, %s, %s,
             %s, %s, 'pending_approval',
             '{}'::jsonb, %s, %s, %s, %s)
        """,
        (
            incident["incident_id"],
            incident["diagnosis_id"],
            action["action_type"],
            action["title"],
            action["description"],
            incident.get("source_type"),
            incident.get("incident_type"),
            incident.get("confidence"),
            safety["reason"],
            action.get("expected_impact"),
            action.get("rollback_notes"),
            action.get("safety_notes"),
            safety["risk_level"],
            True,
            idem_hash,
            RULES_VERSION,
            now, now,
        ),
    )


def _enrich(row: dict) -> dict:
    """Add derived fields to a DB row before returning to the API."""
    status = row.get("status", "")
    action_type = row.get("action_type", "")
    owner = _derive_owner(action_type)
    return {
        **row,
        "owner": owner,
        "owner_label": _OWNER_LABEL.get(owner, owner.capitalize()),
        "can_approve":      status == "pending_approval",
        "can_reject":       status == "pending_approval",
        "can_execute":      False,   # ALWAYS false in Phase 3A
        "execution_allowed": False,
    }


def _run_generation_loop(conn, incidents: list[dict], force: bool) -> dict:
    """
    Shared generation loop used by both generate_action_recommendations and
    generate_for_incident.
    Returns {created, skipped, blocked, failed}.
    """
    stats = {"created": 0, "skipped": 0, "blocked": 0, "failed": 0}

    for incident in incidents:
        incident_type = incident.get("incident_type") or ""
        actions = _RULES.get(incident_type, _DEFAULT_RULE)
        existing_hashes = _existing_rec_hashes(conn, incident["incident_id"])
        context_hash = incident.get("context_hash") or ""

        for action in actions:
            action_type = action["action_type"]
            safety = classify_action(action_type)

            if safety["blocked_by_policy"]:
                stats["blocked"] += 1
                logger.info(
                    "action blocked by policy: incident=%s action=%s",
                    incident["incident_id"], action_type,
                )
                continue

            idem_hash = _idempotency_hash(
                incident["incident_id"],
                incident["diagnosis_id"],
                action_type,
                context_hash,
            )

            # Exact hash already exists → this exact version was already generated.
            # Always deduplicate by hash; force only bypasses the approved-row guard below.
            if idem_hash in existing_hashes:
                stats["skipped"] += 1
                continue

            try:
                # Supersede any stale pending rows (different hash, same incident+action_type).
                # Approved and rejected rows are not touched.
                superseded = _supersede_stale_pending(
                    conn, incident["incident_id"], action_type, idem_hash
                )

                # If an approved row exists (from any version), preserve the admin's
                # decision and skip creating a new row — unless force=True.
                if not force and _has_approved(conn, incident["incident_id"], action_type):
                    conn.commit()  # commit supersede cleanup
                    stats["skipped"] += 1
                    continue

                _insert_recommendation(
                    conn, incident=incident, action=action,
                    safety=safety, idem_hash=idem_hash,
                )
                conn.commit()  # commits supersede + insert atomically
                stats["created"] += 1
                if superseded:
                    logger.info(
                        "superseded %d stale pending → new rec: incident=%s action=%s",
                        superseded, incident["incident_id"], action_type,
                    )
                else:
                    logger.info(
                        "created recommendation: incident=%s action=%s risk=%s",
                        incident["incident_id"], action_type, safety["risk_level"],
                    )
            except Exception as exc:
                conn.rollback()
                stats["failed"] += 1
                logger.warning(
                    "failed to create recommendation: incident=%s action=%s err=%s",
                    incident["incident_id"], action_type, exc,
                )

    return stats


def generate_action_recommendations(conn=None, limit: int = 10, force: bool = False) -> dict:
    """
    Generate rule-based action recommendations for open incidents with an
    active ai_diagnosis. Idempotent: skips incident+action_type combos whose
    idem_hash already exists in action_recommendations.

    When RULES_VERSION changes, existing pending rows are superseded and new
    rows with updated copy are created. Approved rows are never overwritten
    unless force=True.

    Returns {processed, created, skipped, blocked, failed}.
    """
    from app.infra.db import get_connection, release_connection

    _own_conn = conn is None
    if _own_conn:
        conn = get_connection()

    stats = {"processed": 0, "created": 0, "skipped": 0, "blocked": 0, "failed": 0}

    try:
        incidents = _fetch_diagnosable_incidents(conn, limit)
        stats["processed"] = len(incidents)
        loop_stats = _run_generation_loop(conn, incidents, force)
        for k in ("created", "skipped", "blocked", "failed"):
            stats[k] += loop_stats[k]
    except Exception as exc:
        logger.error("generate_action_recommendations error: %s", exc)
        stats["failed"] += 1
    finally:
        if _own_conn:
            release_connection(conn)

    return stats


def generate_for_incident(conn, incident_id: int, force: bool = False) -> dict:
    """
    Generate recommendations for a single incident. The incident must have an
    active ai_diagnosis. Returns {created, skipped, blocked, failed}.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT si.incident_id, si.source_type, si.incident_type, si.severity,
               si.title, si.hosting_id, si.user_id,
               diag.id            AS diagnosis_id,
               diag.context_hash  AS context_hash,
               diag.confidence    AS confidence
          FROM system_incidents si
          JOIN LATERAL (
            SELECT id, context_hash, confidence
              FROM ai_diagnosis
             WHERE incident_id = si.incident_id
               AND status = 'active'
             ORDER BY created_at DESC
             LIMIT 1
          ) diag ON TRUE
         WHERE si.incident_id = %s
        """,
        (incident_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    stats = {"created": 0, "skipped": 0, "blocked": 0, "failed": 0}

    if not rows:
        logger.warning("generate_for_incident: no active diagnosis for incident %s", incident_id)
        return stats

    return _run_generation_loop(conn, rows, force)


def get_actions_for_incident(conn, incident_id: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT action_id, incident_id, diagnosis_id, action_type, title, description,
               source_type, incident_type, recommendation_source, confidence, reason,
               expected_impact, rollback_notes, safety_notes,
               risk_level, requires_approval, status, rules_version,
               approved_by, approved_at, executed_at, payload, context_hash,
               created_at, updated_at
          FROM action_recommendations
         WHERE incident_id = %s
         ORDER BY
           CASE risk_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
           created_at DESC
        """,
        (incident_id,),
    )
    return [_enrich(dict(r)) for r in cur.fetchall()]


def _log_audit_event(action_id: int, incident_id: int, diagnosis_id: Optional[int],
                     actor_user_id: int, previous_status: str, new_status: str) -> None:
    try:
        from app.services.activity_service import log_event
        log_event(
            user_id=actor_user_id,
            actor_type="admin",
            actor_user_id=actor_user_id,
            event_type=f"action_recommendation_{new_status}",
            category="ai_sentinel",
            severity="info",
            title=f"Recomendación #{action_id} {new_status} por admin",
            metadata={
                "action_id":       action_id,
                "incident_id":     incident_id,
                "diagnosis_id":    diagnosis_id,
                "previous_status": previous_status,
                "new_status":      new_status,
            },
        )
    except Exception as exc:
        logger.warning("audit log failed for action %s → %s: %s", action_id, new_status, exc)


def approve_action(conn, action_id: int, admin_user_id: int) -> dict:
    """
    Mark an action as approved. Does NOT execute it — Phase 3A constraint.
    executed_at remains NULL.
    Returns the updated row.
    """
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    cur.execute(
        """
        UPDATE action_recommendations
           SET status = 'approved', approved_by = %s, approved_at = %s, updated_at = %s
         WHERE action_id = %s AND status = 'pending_approval'
         RETURNING action_id, incident_id, diagnosis_id, status, approved_by, approved_at, executed_at
        """,
        (admin_user_id, now, now, action_id),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Action {action_id} not found or not in pending_approval state")
    conn.commit()
    result = dict(row)
    _log_audit_event(
        action_id=action_id,
        incident_id=result["incident_id"],
        diagnosis_id=result.get("diagnosis_id"),
        actor_user_id=admin_user_id,
        previous_status="pending_approval",
        new_status="approved",
    )
    return result


def reject_action(conn, action_id: int, admin_user_id: int, reason: Optional[str] = None) -> dict:
    """Mark an action as rejected."""
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    cur.execute(
        "SELECT status FROM action_recommendations WHERE action_id = %s",
        (action_id,),
    )
    prev_row = cur.fetchone()
    previous_status = dict(prev_row)["status"] if prev_row else "unknown"

    cur.execute(
        """
        UPDATE action_recommendations
           SET status = 'rejected', approved_by = %s, approved_at = %s, updated_at = %s,
               reason = COALESCE(%s, reason)
         WHERE action_id = %s AND status IN ('pending_approval', 'approved')
         RETURNING action_id, incident_id, diagnosis_id, status, approved_by, approved_at, executed_at
        """,
        (admin_user_id, now, now, reason, action_id),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Action {action_id} not found or cannot be rejected from current state")
    conn.commit()
    result = dict(row)
    _log_audit_event(
        action_id=action_id,
        incident_id=result["incident_id"],
        diagnosis_id=result.get("diagnosis_id"),
        actor_user_id=admin_user_id,
        previous_status=previous_status,
        new_status="rejected",
    )
    return result
