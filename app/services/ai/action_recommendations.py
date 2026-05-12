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
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.services.ai.action_safety_classifier import classify_action

logger = logging.getLogger(__name__)

# Rule table: incident_type → list of (action_type, title, description, expected_impact, rollback_notes, safety_notes)
_RULES: dict[str, list[dict]] = {
    "node_sass_incompatible": [
        {
            "action_type": "dependency_fix",
            "title": "Actualizar dependencia node-sass a sass",
            "description": "node-sass está obsoleto y es incompatible con la versión de Node instalada. Migrar a 'sass' resuelve el error de compilación.",
            "expected_impact": "El build debería completarse correctamente tras actualizar package.json.",
            "rollback_notes": "Revertir el cambio en package.json y ejecutar npm install.",
            "safety_notes": "Solo afecta dependencias de desarrollo. No modifica datos ni contenedores.",
        },
    ],
    "github_branch_not_found": [
        {
            "action_type": "customer_fix",
            "title": "Verificar nombre de rama en configuración GitHub",
            "description": "La rama configurada no existe en el repositorio. El cliente debe corregir el nombre de rama en la configuración de deploy.",
            "expected_impact": "El deploy comenzará a funcionar una vez corregida la rama.",
            "rollback_notes": "No aplica — es un cambio de configuración reversible.",
            "safety_notes": "No se modifica ningún contenedor ni dato de producción.",
        },
    ],
    "github_private_repo_unauthorized": [
        {
            "action_type": "customer_fix",
            "title": "Revisar permisos del token GitHub",
            "description": "El token de acceso no tiene permisos sobre el repositorio privado. El cliente debe actualizar el token con acceso 'repo' completo.",
            "expected_impact": "El deploy podrá clonar el repositorio una vez actualizado el token.",
            "rollback_notes": "No aplica — cambio de configuración reversible.",
            "safety_notes": "El token se almacena cifrado. No afecta contenedores en ejecución.",
        },
    ],
    "build_failed": [
        {
            "action_type": "manual_check",
            "title": "Revisar logs de build para identificar error",
            "description": "El build falló por un error no clasificado. Revisar los logs de deploy para identificar la causa raíz.",
            "expected_impact": "Diagnóstico manual permite determinar si el fix requiere intervención del cliente o del administrador.",
            "rollback_notes": "No aplica — acción de diagnóstico sin efecto directo.",
            "safety_notes": "Acción de solo lectura.",
        },
    ],
    "site_critical": [
        {
            "action_type": "admin_review",
            "title": "Revisión urgente por administrador",
            "description": "El sitio está en estado crítico. Un administrador debe revisar el estado del contenedor y los logs antes de tomar cualquier acción.",
            "expected_impact": "Permite determinar si se requiere redeploy, restauración de backup, o intervención de infraestructura.",
            "rollback_notes": "No aplica — acción de diagnóstico.",
            "safety_notes": "No modifica el estado del sistema.",
        },
        {
            "action_type": "redeploy_candidate",
            "title": "Considerar redeploy desde última versión estable",
            "description": "Si el diagnóstico confirma corrupción del contenedor, un redeploy desde el último commit estable puede restaurar el servicio.",
            "expected_impact": "Restaura el sitio al último estado funcional conocido si el problema es del contenedor.",
            "rollback_notes": "Guardar backup antes del redeploy. El redeploy puede sobreescribir cambios locales.",
            "safety_notes": "Requiere aprobación explícita. El administrador debe ejecutar manualmente desde el panel de deploy.",
        },
    ],
    "site_recovery": [
        {
            "action_type": "monitor",
            "title": "Monitorear estabilidad tras recuperación",
            "description": "El sitio se ha recuperado de un estado crítico. Monitorear métricas de CPU, RAM y uptime durante las próximas 24h para confirmar estabilidad.",
            "expected_impact": "Detección temprana de regresión si el sitio vuelve a degradarse.",
            "rollback_notes": "No aplica — acción de monitoreo pasivo.",
            "safety_notes": "No modifica el sistema.",
        },
    ],
    "security_attack": [
        {
            "action_type": "security_review",
            "title": "Revisar eventos de seguridad y logs de acceso",
            "description": "Se detectó actividad maliciosa. Revisar los eventos de seguridad, IPs involucradas y paths afectados.",
            "expected_impact": "Identificar patrón de ataque y decidir si activar Protection Mode.",
            "rollback_notes": "No aplica.",
            "safety_notes": "Acción de solo lectura.",
        },
        {
            "action_type": "enable_protection_mode_monitor",
            "title": "Activar Protection Mode en modo monitor",
            "description": "Activar Protection Mode en modo 'monitor' registrará todas las peticiones sospechosas sin bloquearlas, permitiendo evaluar el impacto antes de bloquear.",
            "expected_impact": "Mayor visibilidad sobre el ataque sin riesgo de falsos positivos.",
            "rollback_notes": "Desactivar Protection Mode desde el panel de hosting.",
            "safety_notes": "Modo monitor no bloquea tráfico. Requiere aprobación del administrador.",
        },
    ],
    "wordpress_malware": [
        {
            "action_type": "security_review",
            "title": "Revisión de archivos WordPress por malware",
            "description": "Se detectaron indicadores de malware en el sitio WordPress. Revisar los logs de seguridad y los archivos del sitio antes de tomar acción.",
            "expected_impact": "Identificar alcance de la infección y archivos comprometidos.",
            "rollback_notes": "Restaurar desde backup limpio si se confirma infección.",
            "safety_notes": "No modifica archivos. Acción de diagnóstico.",
        },
        {
            "action_type": "enable_protection_mode_monitor",
            "title": "Activar Protection Mode para detectar exfiltración",
            "description": "Activar modo monitor permite detectar intentos de exfiltración de datos mientras se realiza el análisis.",
            "expected_impact": "Visibilidad sobre tráfico saliente anómalo.",
            "rollback_notes": "Desactivar Protection Mode desde el panel de hosting.",
            "safety_notes": "No bloquea tráfico en modo monitor. Requiere aprobación.",
        },
    ],
}

# Fallback for incident_types not in _RULES
_DEFAULT_RULE: list[dict] = [
    {
        "action_type": "manual_check",
        "title": "Revisión manual del incidente",
        "description": "Este tipo de incidente no tiene recomendaciones automáticas. Un administrador debe revisar los detalles manualmente.",
        "expected_impact": "Diagnóstico directo del problema.",
        "rollback_notes": "No aplica.",
        "safety_notes": "Acción de solo lectura.",
    },
]


def _idempotency_hash(incident_id: int, diagnosis_id: int, action_type: str, context_hash: str) -> str:
    key = f"{incident_id}:{diagnosis_id}:{action_type}:{context_hash}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


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
             payload, context_hash, created_at, updated_at)
        VALUES
            (%s, %s, %s, %s, %s,
             %s, %s,
             'rule_based', %s, %s,
             %s, %s, %s,
             %s, %s, 'pending_approval',
             '{}'::jsonb, %s, %s, %s)
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
            now, now,
        ),
    )


def generate_action_recommendations(conn=None, limit: int = 10, force: bool = False) -> dict:
    """
    Generate rule-based action recommendations for open incidents with an
    active ai_diagnosis. Idempotent: skips incident+action_type combos whose
    idem_hash already exists in action_recommendations.

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

                if not force and idem_hash in existing_hashes:
                    stats["skipped"] += 1
                    continue

                try:
                    _insert_recommendation(conn, incident=incident, action=action, safety=safety, idem_hash=idem_hash)
                    conn.commit()
                    stats["created"] += 1
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

    incident = rows[0]
    incident_type = incident.get("incident_type") or ""
    actions = _RULES.get(incident_type, _DEFAULT_RULE)
    existing_hashes = _existing_rec_hashes(conn, incident_id)
    context_hash = incident.get("context_hash") or ""

    for action in actions:
        action_type = action["action_type"]
        safety = classify_action(action_type)

        if safety["blocked_by_policy"]:
            stats["blocked"] += 1
            continue

        idem_hash = _idempotency_hash(
            incident["incident_id"],
            incident["diagnosis_id"],
            action_type,
            context_hash,
        )

        if not force and idem_hash in existing_hashes:
            stats["skipped"] += 1
            continue

        try:
            _insert_recommendation(conn, incident=incident, action=action, safety=safety, idem_hash=idem_hash)
            conn.commit()
            stats["created"] += 1
        except Exception as exc:
            conn.rollback()
            stats["failed"] += 1
            logger.warning("generate_for_incident insert failed: incident=%s action=%s err=%s", incident_id, action_type, exc)

    return stats


def get_actions_for_incident(conn, incident_id: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT action_id, incident_id, diagnosis_id, action_type, title, description,
               source_type, incident_type, recommendation_source, confidence, reason,
               expected_impact, rollback_notes, safety_notes,
               risk_level, requires_approval, status,
               approved_by, approved_at, payload, context_hash,
               created_at, updated_at
          FROM action_recommendations
         WHERE incident_id = %s
         ORDER BY
           CASE risk_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
           created_at DESC
        """,
        (incident_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def approve_action(conn, action_id: int, admin_user_id: int) -> dict:
    """
    Mark an action as approved. Does NOT execute it — Phase 3A constraint.
    Returns the updated row.
    """
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    cur.execute(
        """
        UPDATE action_recommendations
           SET status = 'approved', approved_by = %s, approved_at = %s, updated_at = %s
         WHERE action_id = %s AND status = 'pending_approval'
         RETURNING action_id, status, approved_by, approved_at
        """,
        (admin_user_id, now, now, action_id),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Action {action_id} not found or not in pending_approval state")
    conn.commit()
    return dict(row)


def reject_action(conn, action_id: int, admin_user_id: int, reason: Optional[str] = None) -> dict:
    """Mark an action as rejected."""
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    cur.execute(
        """
        UPDATE action_recommendations
           SET status = 'rejected', approved_by = %s, approved_at = %s, updated_at = %s,
               reason = COALESCE(%s, reason)
         WHERE action_id = %s AND status IN ('pending_approval', 'approved')
         RETURNING action_id, status, approved_by, approved_at
        """,
        (admin_user_id, now, now, reason, action_id),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Action {action_id} not found or cannot be rejected from current state")
    conn.commit()
    return dict(row)
