"""
Phase 3B: Execution Planner.

Generates auditable execution plans for approved action recommendations.
Plans describe a safe procedure for human review — they NEVER execute anything.

Prohibited in this phase:
  - executing any command
  - calling Docker
  - restarting containers
  - modifying Traefik / DNS
  - blocking IPs
  - changing Protection Mode
  - resolving incidents automatically
  - execution_allowed is ALWAYS false
  - no /execute endpoint, no "Ejecutar" button
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from app.services.ai.execution_plan_safety import classify_execution_plan

logger = logging.getLogger(__name__)

PLANNER_VERSION = "planner_v1"

# ── Plan templates ─────────────────────────────────────────────────────────────
# Keys are action_type values from action_recommendations.
# Each entry defines the static plan structure. Prechecks / steps / rollback are
# informational only — HostingGuard never executes them automatically.

_TEMPLATES: dict[str, dict] = {
    "customer_fix": {
        "title": "Plan de corrección para el cliente",
        "summary": (
            "El cliente debe realizar cambios en su repositorio o configuración. "
            "Este plan describe los pasos recomendados para su revisión."
        ),
        "prechecks": [
            {"order": 1, "description": "Verificar acceso al repositorio del cliente"},
            {"order": 2, "description": "Confirmar que el incidente sigue activo"},
        ],
        "steps": [
            {"order": 1, "description": "Notificar al cliente con los detalles del incidente y la acción recomendada"},
            {"order": 2, "description": "Solicitar al cliente que aplique el cambio en su entorno"},
            {"order": 3, "description": "Confirmar con el cliente que la corrección fue aplicada"},
            {"order": 4, "description": "Verificar que el incidente se resolvió tras la corrección del cliente"},
        ],
        "rollback_steps": [
            {"order": 1, "description": "Si el cambio del cliente genera nuevos problemas, revertir al estado anterior"},
        ],
        "expected_impact": "El incidente se resolverá una vez que el cliente aplique la corrección indicada.",
        "safety_notes": "HostingGuard no modifica nada. El cliente realiza todos los cambios.",
    },
    "dependency_fix": {
        "title": "Plan de actualización de dependencias",
        "summary": (
            "El cliente debe actualizar dependencias en su repositorio. "
            "Este plan describe el procedimiento recomendado."
        ),
        "prechecks": [
            {"order": 1, "description": "Verificar la versión de Node / runtime en uso"},
            {"order": 2, "description": "Identificar la dependencia incompatible y la alternativa recomendada"},
        ],
        "steps": [
            {"order": 1, "description": "Comunicar al cliente la dependencia que debe actualizar y la versión recomendada"},
            {"order": 2, "description": "El cliente actualiza package.json y ejecuta npm install en su repositorio"},
            {"order": 3, "description": "El cliente hace commit y push del cambio"},
            {"order": 4, "description": "Verificar que el deploy se completa correctamente"},
        ],
        "rollback_steps": [
            {"order": 1, "description": "Revertir el cambio en package.json al estado anterior"},
            {"order": 2, "description": "Ejecutar npm install con la versión revertida"},
        ],
        "expected_impact": "El build debería completarse correctamente tras actualizar la dependencia.",
        "safety_notes": "HostingGuard no modifica el código del cliente ni ejecuta comandos en el contenedor.",
    },
    "branch_correction": {
        "title": "Plan de corrección de rama de GitHub",
        "summary": "La configuración de deploy apunta a una rama inexistente. Este plan guía la corrección.",
        "prechecks": [
            {"order": 1, "description": "Verificar las ramas disponibles en el repositorio del cliente"},
            {"order": 2, "description": "Confirmar la rama correcta (main, master u otra)"},
        ],
        "steps": [
            {"order": 1, "description": "Informar al cliente la rama correcta a configurar"},
            {"order": 2, "description": "El cliente actualiza la configuración de deploy en su panel"},
            {"order": 3, "description": "Disparar un nuevo deploy para verificar que la rama es accesible"},
        ],
        "rollback_steps": [
            {"order": 1, "description": "Restaurar la configuración de rama anterior si el nuevo deploy falla"},
        ],
        "expected_impact": "El deploy comenzará a funcionar una vez corregido el nombre de la rama.",
        "safety_notes": "Solo se modifica la configuración de deploy. No se toca el repositorio ni el contenedor.",
    },
    "manual_check": {
        "title": "Plan de revisión manual",
        "summary": "Un administrador debe revisar manualmente este incidente y determinar la acción apropiada.",
        "prechecks": [
            {"order": 1, "description": "Revisar los detalles del incidente y el diagnóstico de IA"},
            {"order": 2, "description": "Verificar que no hay otro admin ya trabajando en el mismo incidente"},
        ],
        "steps": [
            {"order": 1, "description": "Abrir los logs del componente afectado"},
            {"order": 2, "description": "Identificar la causa raíz basándose en la evidencia disponible"},
            {"order": 3, "description": "Documentar hallazgos en las notas del incidente"},
            {"order": 4, "description": "Determinar y ejecutar manualmente la acción correctiva adecuada"},
        ],
        "rollback_steps": [],
        "expected_impact": "Identificación de la causa raíz y determinación del próximo paso correctivo.",
        "safety_notes": "Acción de diagnóstico de solo lectura. No modifica ningún sistema.",
    },
    "admin_review": {
        "title": "Plan de revisión de administrador",
        "summary": "Un administrador debe inspeccionar el estado del sistema afectado.",
        "prechecks": [
            {"order": 1, "description": "Verificar el estado actual del contenedor y servicios relacionados"},
            {"order": 2, "description": "Revisar métricas de CPU, RAM y red en las últimas horas"},
        ],
        "steps": [
            {"order": 1, "description": "Revisar logs del contenedor afectado"},
            {"order": 2, "description": "Analizar métricas de salud del sitio"},
            {"order": 3, "description": "Comparar con el baseline histórico para detectar anomalías"},
            {"order": 4, "description": "Determinar si se requiere intervención operativa y documentarla"},
        ],
        "rollback_steps": [],
        "expected_impact": "Claridad sobre el estado del sistema y decisión informada sobre próximos pasos.",
        "safety_notes": "Acción de observación. No modifica el sistema.",
    },
    "monitor": {
        "title": "Plan de monitoreo continuo",
        "summary": "Seguimiento pasivo del sistema para detectar regresión.",
        "prechecks": [
            {"order": 1, "description": "Confirmar que las alertas automáticas están activas para el hosting afectado"},
        ],
        "steps": [
            {"order": 1, "description": "Revisar métricas de uptime y latencia cada 4-6 horas durante 24 horas"},
            {"order": 2, "description": "Verificar que no se repiten los patrones del incidente"},
            {"order": 3, "description": "Cerrar el incidente si el sistema permanece estable por 24 horas"},
        ],
        "rollback_steps": [],
        "expected_impact": "Detección temprana de regresión si el problema se repite.",
        "safety_notes": "Solo lectura. No modifica el sistema.",
    },
    "site_recovery_monitor": {
        "title": "Plan de monitoreo post-recuperación",
        "summary": "Monitoreo activo tras recuperación de sitio crítico.",
        "prechecks": [
            {"order": 1, "description": "Confirmar que el sitio responde con HTTP 200 en el health check"},
            {"order": 2, "description": "Verificar que los métricas de CPU y RAM volvieron al rango normal"},
        ],
        "steps": [
            {"order": 1, "description": "Mantener monitoreo cada 15 min durante las primeras 2 horas"},
            {"order": 2, "description": "Revisar logs de errores cada hora"},
            {"order": 3, "description": "Verificar ausencia de spike de CPU/RAM en las próximas 6 horas"},
            {"order": 4, "description": "Marcar incidente como resuelto si la estabilidad se mantiene 24h"},
        ],
        "rollback_steps": [
            {"order": 1, "description": "Si el sitio vuelve a caer, escalar a plan de redeploy o restauración de backup"},
        ],
        "expected_impact": "Confirmación de estabilidad post-recuperación.",
        "safety_notes": "Solo monitoreo pasivo. No ejecuta acciones correctivas automáticamente.",
    },
    "security_review": {
        "title": "Plan de revisión de seguridad",
        "summary": "Revisión de eventos de seguridad, IPs y logs de acceso ante actividad sospechosa.",
        "prechecks": [
            {"order": 1, "description": "Verificar que los eventos de seguridad están disponibles en el panel"},
            {"order": 2, "description": "Confirmar el rango horario del ataque"},
        ],
        "steps": [
            {"order": 1, "description": "Revisar eventos de seguridad filtrados por IP y rango de tiempo"},
            {"order": 2, "description": "Identificar patrones: fuerza bruta, escaneo de paths, inyección"},
            {"order": 3, "description": "Revisar logs de acceso del contenedor afectado"},
            {"order": 4, "description": "Documentar las IPs y patrones identificados"},
            {"order": 5, "description": "Evaluar si el nivel de riesgo justifica activar Protection Mode"},
        ],
        "rollback_steps": [],
        "expected_impact": "Identificación del vector de ataque y base para decisión sobre bloqueo.",
        "safety_notes": "Revisión de solo lectura. No bloquea tráfico ni modifica configuración.",
    },
    "enable_protection_mode_monitor": {
        "title": "Plan para activar Protection Mode (modo monitor)",
        "summary": (
            "Procedimiento para que un administrador active Protection Mode en modo monitor "
            "desde el panel de hosting. Requiere aprobación manual."
        ),
        "prechecks": [
            {"order": 1, "description": "Verificar que Protection Mode no está ya activo en modo monitor o protect"},
            {"order": 2, "description": "Confirmar que el hosting está activo y accesible"},
        ],
        "steps": [
            {"order": 1, "description": "Navegar al panel de hosting → Configuración → Protection Mode"},
            {"order": 2, "description": "Seleccionar modo 'monitor' (registra sin bloquear)"},
            {"order": 3, "description": "Confirmar la activación y documentar la hora de inicio"},
            {"order": 4, "description": "Revisar los eventos registrados en las siguientes 2 horas"},
        ],
        "rollback_steps": [
            {"order": 1, "description": "Desactivar Protection Mode desde el panel de hosting si genera falsos positivos"},
        ],
        "expected_impact": "Mayor visibilidad sobre tráfico sospechoso sin interrumpir el servicio.",
        "safety_notes": "Modo monitor no bloquea tráfico. El administrador activa manualmente desde el panel.",
    },
    "enable_protection_mode_protect": {
        "title": "Plan para activar Protection Mode (modo protect)",
        "summary": (
            "Procedimiento para activar Protection Mode en modo bloqueo activo. "
            "Alto impacto — puede causar falsos positivos. Requiere aprobación explícita."
        ),
        "prechecks": [
            {"order": 1, "description": "Confirmar que la revisión de seguridad identificó amenaza real"},
            {"order": 2, "description": "Verificar que Protection Mode monitor estuvo activo al menos 30 min"},
            {"order": 3, "description": "Estimar el riesgo de falsos positivos basándose en el tráfico legítimo"},
        ],
        "steps": [
            {"order": 1, "description": "Navegar al panel de hosting → Configuración → Protection Mode"},
            {"order": 2, "description": "Cambiar de modo 'monitor' a modo 'protect'"},
            {"order": 3, "description": "Confirmar la activación y documentar la decisión"},
            {"order": 4, "description": "Monitorear el tráfico bloqueado durante la primera hora"},
            {"order": 5, "description": "Ajustar reglas si se detectan falsos positivos"},
        ],
        "rollback_steps": [
            {"order": 1, "description": "Reducir a modo 'monitor' o desactivar Protection Mode si hay impacto en tráfico legítimo"},
        ],
        "expected_impact": "Bloqueo activo de tráfico malicioso identificado.",
        "safety_notes": "Puede afectar tráfico legítimo. El administrador activa y monitorea manualmente.",
    },
    "redeploy_candidate": {
        "title": "Plan de redeploy desde último commit estable",
        "summary": (
            "Procedimiento para que un administrador ejecute un redeploy manual "
            "desde el panel de deploy. No se ejecuta automáticamente."
        ),
        "prechecks": [
            {"order": 1, "description": "Identificar el último commit estable conocido"},
            {"order": 2, "description": "Verificar que hay un backup reciente disponible"},
            {"order": 3, "description": "Confirmar que el problema está en el contenedor y no en el código"},
        ],
        "steps": [
            {"order": 1, "description": "Crear backup del estado actual del sitio si es posible"},
            {"order": 2, "description": "Navegar al panel de deploy del hosting afectado"},
            {"order": 3, "description": "Seleccionar el commit estable objetivo y confirmar el redeploy"},
            {"order": 4, "description": "Monitorear el proceso de deploy en tiempo real"},
            {"order": 5, "description": "Verificar que el sitio responde correctamente tras el deploy"},
        ],
        "rollback_steps": [
            {"order": 1, "description": "Restaurar el backup previo al redeploy si el nuevo deploy falla"},
            {"order": 2, "description": "Escalar a soporte si la restauración no resuelve el problema"},
        ],
        "expected_impact": "Restauración del sitio al último estado funcional conocido.",
        "safety_notes": "El administrador ejecuta el redeploy manualmente. HostingGuard no lo inicia automáticamente.",
    },
    "restart_container_suggestion": {
        "title": "Plan de reinicio de contenedor (sugerencia)",
        "summary": (
            "Sugerencia de reinicio manual del contenedor. Solo un administrador puede ejecutar "
            "esta acción desde el panel de infraestructura."
        ),
        "prechecks": [
            {"order": 1, "description": "Verificar si el reinicio resolverá el problema (p.ej. memory leak, proceso colgado)"},
            {"order": 2, "description": "Confirmar que hay backup reciente disponible"},
            {"order": 3, "description": "Notificar al cliente sobre la ventana de downtime esperada (< 60 seg)"},
        ],
        "steps": [
            {"order": 1, "description": "Navegar al panel de infraestructura del hosting"},
            {"order": 2, "description": "Seleccionar 'Reiniciar contenedor' y confirmar la acción"},
            {"order": 3, "description": "Esperar que el contenedor levante (status: running)"},
            {"order": 4, "description": "Verificar que el sitio responde correctamente"},
            {"order": 5, "description": "Monitorear métricas durante 30 minutos post-reinicio"},
        ],
        "rollback_steps": [
            {"order": 1, "description": "Si el contenedor no levanta, iniciar diagnóstico de logs y escalar"},
        ],
        "expected_impact": "Resolución de problemas transitorios del contenedor (memory leak, proceso colgado).",
        "safety_notes": "El administrador ejecuta el reinicio manualmente. Downtime esperado < 60 segundos.",
    },
    "block_ip_candidate": {
        "title": "Plan de bloqueo de IP (candidato)",
        "summary": (
            "Procedimiento de evaluación para bloqueo manual de IP maliciosa. "
            "Alto impacto — requiere verificación de falsos positivos antes de bloquear."
        ),
        "prechecks": [
            {"order": 1, "description": "Verificar que la IP es efectivamente maliciosa y no un proxy/CDN legítimo"},
            {"order": 2, "description": "Revisar si la IP tiene tráfico legítimo en los últimos 7 días"},
            {"order": 3, "description": "Confirmar que el bloqueo no afecta a usuarios válidos en la misma IP (NAT)"},
        ],
        "steps": [
            {"order": 1, "description": "Documentar la IP, patrones de ataque y logs de evidencia"},
            {"order": 2, "description": "Evaluar si bloquear en Protection Mode es suficiente o se requiere regla de firewall"},
            {"order": 3, "description": "Implementar el bloqueo por el canal apropiado (Protection Mode / firewall)"},
            {"order": 4, "description": "Verificar que el tráfico malicioso cesó"},
            {"order": 5, "description": "Monitorear durante 1 hora para detectar cambio de IP del atacante"},
        ],
        "rollback_steps": [
            {"order": 1, "description": "Eliminar la regla de bloqueo si se detectan falsos positivos"},
        ],
        "expected_impact": "Eliminación del tráfico malicioso de la IP identificada.",
        "safety_notes": "Requiere verificación manual antes de bloquear. No se bloquea automáticamente.",
    },
    "escalate_to_admin": {
        "title": "Plan de escalada a administrador senior",
        "summary": "El incidente supera el alcance del diagnóstico automático y requiere atención de un administrador.",
        "prechecks": [
            {"order": 1, "description": "Verificar que no hay admin senior ya asignado al incidente"},
        ],
        "steps": [
            {"order": 1, "description": "Crear ticket de escalada con toda la evidencia disponible"},
            {"order": 2, "description": "Asignar el incidente al admin senior disponible"},
            {"order": 3, "description": "Notificar al cliente que el caso está siendo revisado por el equipo"},
        ],
        "rollback_steps": [],
        "expected_impact": "Atención especializada del incidente por un administrador con mayor contexto.",
        "safety_notes": "Solo comunicación y asignación. No modifica ningún sistema.",
    },
    "notify_customer": {
        "title": "Plan de notificación al cliente",
        "summary": "El cliente debe ser informado del estado del incidente y los pasos recomendados.",
        "prechecks": [
            {"order": 1, "description": "Verificar los datos de contacto del cliente"},
            {"order": 2, "description": "Preparar el mensaje con detalles claros del incidente y la acción esperada"},
        ],
        "steps": [
            {"order": 1, "description": "Redactar mensaje de notificación con detalles del incidente"},
            {"order": 2, "description": "Enviar notificación al cliente vía panel o email"},
            {"order": 3, "description": "Registrar la notificación en el log del incidente"},
            {"order": 4, "description": "Aguardar respuesta del cliente (SLA: 24-48 horas)"},
        ],
        "rollback_steps": [],
        "expected_impact": "El cliente toma conocimiento del problema y puede aplicar la corrección.",
        "safety_notes": "Solo comunicación. No modifica ningún sistema.",
    },
    "check_credentials": {
        "title": "Plan de verificación de credenciales",
        "summary": "El cliente debe verificar y corregir las credenciales de acceso al repositorio.",
        "prechecks": [
            {"order": 1, "description": "Confirmar el tipo de credencial que falla (token, deploy key, webhook)"},
        ],
        "steps": [
            {"order": 1, "description": "Notificar al cliente el tipo de credencial que requiere actualización"},
            {"order": 2, "description": "El cliente genera nuevas credenciales en GitHub / GitLab"},
            {"order": 3, "description": "El cliente actualiza las credenciales en la configuración del hosting"},
            {"order": 4, "description": "Verificar que el deploy se completa correctamente con las nuevas credenciales"},
        ],
        "rollback_steps": [
            {"order": 1, "description": "Restaurar credenciales anteriores si las nuevas no funcionan"},
        ],
        "expected_impact": "Acceso al repositorio restaurado; deploy puede completarse.",
        "safety_notes": "HostingGuard no accede ni almacena credenciales. El cliente las gestiona directamente.",
    },
}

_DEFAULT_TEMPLATE: dict = {
    "title": "Plan de revisión manual",
    "summary": "No hay un template predefinido para este tipo de acción. Requiere revisión manual.",
    "prechecks": [
        {"order": 1, "description": "Revisar los detalles del incidente y el diagnóstico disponible"},
    ],
    "steps": [
        {"order": 1, "description": "Revisar manualmente el incidente y determinar el curso de acción apropiado"},
        {"order": 2, "description": "Documentar la decisión y ejecutar el paso correctivo si corresponde"},
    ],
    "rollback_steps": [],
    "expected_impact": "Resolución manual del incidente.",
    "safety_notes": "Acción manual. Verificar el impacto antes de proceder.",
}

# ── Specific templates keyed by (action_type, incident_type) ──────────────────
# These override the generic _TEMPLATES entry and set status='ready_for_review'
# because the content is complete and actionable without further review.
# Generic fallbacks (_TEMPLATES) use status='draft'.

_SPECIFIC_TEMPLATES: dict[tuple[str, str], dict] = {
    ("customer_fix", "github_private_repo_unauthorized"): {
        "plan_type": "github_access_review",
        "title": "Plan para verificar acceso al repositorio GitHub",
        "summary": (
            "El deploy no pudo clonar el repositorio. El plan guía al admin/cliente para "
            "verificar URL, existencia, visibilidad y permisos de lectura."
        ),
        "prechecks": [
            {"order": 1, "description": "Confirmar que la URL del repositorio esté bien escrita"},
            {"order": 2, "description": "Confirmar que el repositorio existe en GitHub"},
            {"order": 3, "description": "Confirmar si el repositorio es público o privado"},
            {"order": 4, "description": "Confirmar si el usuario conectó credenciales o token con permisos de lectura"},
            {"order": 5, "description": "Confirmar que el incidente sigue abierto antes de reintentar el deploy"},
        ],
        "steps": [
            {"order": 1, "description": "Solicitar al cliente verificar la URL del repositorio"},
            {"order": 2, "description": "Si el repositorio no existe, pedir la URL correcta"},
            {"order": 3, "description": "Si el repositorio es privado, solicitar permisos de lectura o conexión GitHub válida"},
            {"order": 4, "description": "Confirmar que HostingGuard puede acceder al repositorio"},
            {"order": 5, "description": "Reintentar el deploy después de corregir el acceso"},
        ],
        "rollback_steps": [
            {"order": 1, "description": "No aplica rollback porque HostingGuard no modifica infraestructura ni repositorios en esta fase"},
            {"order": 2, "description": "Si el cliente cambia permisos incorrectamente, revertir la visibilidad o token desde GitHub"},
        ],
        "expected_impact": "Una vez corregido el acceso, HostingGuard podrá intentar clonar el repositorio nuevamente.",
        "safety_notes": (
            "Este plan no ejecuta comandos, no modifica infraestructura y no cambia permisos automáticamente. "
            "Es una guía para revisión humana."
        ),
    },
    ("dependency_fix", "node_sass_incompatible"): {
        "plan_type": "node_sass_migration",
        "title": "Plan para migrar node-sass a sass",
        "summary": (
            "El proyecto usa node-sass, incompatible con versiones modernas de Node. "
            "El plan guía al cliente para reemplazarlo por el paquete 'sass' en su repositorio."
        ),
        "prechecks": [
            {"order": 1, "description": "Confirmar que el error de build menciona node-sass explícitamente"},
            {"order": 2, "description": "Verificar la versión de Node en uso (node-sass no es compatible con Node 17+)"},
            {"order": 3, "description": "Confirmar que el cliente tiene acceso al repositorio para hacer el cambio"},
            {"order": 4, "description": "Revisar si el proyecto usa yarn o npm para saber qué comando usar"},
        ],
        "steps": [
            {"order": 1, "description": "Notificar al cliente que debe reemplazar node-sass por sass en package.json"},
            {"order": 2, "description": "El cliente abre package.json y reemplaza 'node-sass' por 'sass' en dependencies/devDependencies"},
            {"order": 3, "description": "El cliente ejecuta npm install (o yarn install) en el repositorio"},
            {"order": 4, "description": "El cliente verifica que el build local compile sin errores"},
            {"order": 5, "description": "El cliente hace commit y push del package.json y lockfile actualizados"},
            {"order": 6, "description": "Reintentar el deploy para confirmar que el build se completa correctamente"},
        ],
        "rollback_steps": [
            {"order": 1, "description": "Si el build falla con sass, revisar si hay importaciones que usan sintaxis node-sass específica y actualizarlas"},
            {"order": 2, "description": "Revertir a la rama anterior del repositorio si el cambio genera más errores"},
        ],
        "expected_impact": "El build debería completarse sin errores de dependencias una vez reemplazado node-sass por sass.",
        "safety_notes": (
            "HostingGuard no modifica el repositorio ni ejecuta npm install. "
            "El cliente realiza todos los cambios en su entorno."
        ),
    },
}


# ── Idempotency ────────────────────────────────────────────────────────────────

def _plan_idempotency_hash(
    action_id: int,
    incident_id: int,
    diagnosis_id: Optional[int],
    action_type: str,
    action_context_hash: str,
    planner_version: str = PLANNER_VERSION,
) -> str:
    key = f"{action_id}:{incident_id}:{diagnosis_id}:{action_type}:{action_context_hash}:{planner_version}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


# ── DB helpers ────────────────────────────────────────────────────────────────

def _fetch_action(conn, action_id: int) -> Optional[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT action_id, incident_id, diagnosis_id, action_type, status,
               context_hash, risk_level, incident_type, title AS action_title
          FROM action_recommendations
         WHERE action_id = %s
        """,
        (action_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _existing_plan_hash(conn, action_id: int) -> Optional[str]:
    cur = conn.cursor()
    cur.execute(
        "SELECT context_hash FROM execution_plans WHERE action_id = %s AND status != 'cancelled' LIMIT 1",
        (action_id,),
    )
    row = cur.fetchone()
    return dict(row)["context_hash"] if row else None


def _insert_plan(
    conn, *, action: dict, template: dict, safety: dict,
    plan_hash: str, actor: str,
    plan_type: str, status: str,
) -> dict:
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    import json

    cur.execute(
        """
        INSERT INTO execution_plans
            (action_id, incident_id, diagnosis_id, plan_type, status,
             risk_level, execution_allowed, requires_final_approval,
             title, summary,
             prechecks, steps, rollback_steps,
             expected_impact, safety_notes,
             blocked_reason, planner_version, context_hash,
             created_by, created_at, updated_at)
        VALUES
            (%s, %s, %s, %s, %s,
             %s, FALSE, TRUE,
             %s, %s,
             %s::jsonb, %s::jsonb, %s::jsonb,
             %s, %s,
             %s, %s, %s,
             %s, %s, %s)
        RETURNING plan_id, action_id, incident_id, diagnosis_id, plan_type, status,
                  risk_level, execution_allowed, requires_final_approval,
                  title, summary, prechecks, steps, rollback_steps,
                  expected_impact, safety_notes, blocked_reason,
                  planner_version, context_hash, created_by, created_at, updated_at
        """,
        (
            action["action_id"],
            action["incident_id"],
            action.get("diagnosis_id"),
            plan_type,
            status,
            safety["risk_level"],
            template["title"],
            template["summary"],
            json.dumps(template["prechecks"]),
            json.dumps(template["steps"]),
            json.dumps(template.get("rollback_steps", [])),
            template.get("expected_impact", ""),
            template.get("safety_notes", ""),
            safety.get("blocked_reason", ""),
            PLANNER_VERSION,
            plan_hash,
            actor,
            now, now,
        ),
    )
    row = cur.fetchone()
    return dict(row)


def _log_plan_audit(action_id: int, plan_id: int, incident_id: int,
                    diagnosis_id: Optional[int], actor: str, event: str) -> None:
    try:
        from app.services.activity_service import log_event
        log_event(
            user_id=None,
            actor_type="admin",
            actor_user_id=None,
            event_type=f"execution_plan_{event}",
            category="ai_sentinel",
            severity="info",
            title=f"Plan #{plan_id} {event}",
            metadata={
                "plan_id":      plan_id,
                "action_id":    action_id,
                "incident_id":  incident_id,
                "diagnosis_id": diagnosis_id,
                "actor":        actor,
            },
        )
    except Exception as exc:
        logger.warning("audit log failed for plan %s event %s: %s", plan_id, event, exc)


# ── Public API ────────────────────────────────────────────────────────────────

def create_execution_plan(
    conn,
    action_id: int,
    force: bool = False,
    actor: str = "admin",
) -> dict:
    """
    Create an execution plan for an approved action_recommendation.

    Rules:
    - Only approved actions can generate a plan.
    - Idempotent: returns existing plan if hash matches (force=False).
    - force=True cancels the existing plan and creates a new one.
    - execution_allowed is ALWAYS false.
    - No commands are executed.
    """
    action = _fetch_action(conn, action_id)
    if not action:
        raise ValueError(f"Action {action_id} not found")

    if action["status"] != "approved":
        raise ValueError(
            f"Action {action_id} is '{action['status']}' — only approved actions can generate a plan"
        )

    safety = classify_execution_plan(action["action_type"])
    if safety["blocked"]:
        raise ValueError(safety["blocked_reason"])

    # Prefer specific (action_type, incident_type) template; fall back to generic.
    specific_key = (action["action_type"], action.get("incident_type") or "")
    specific = _SPECIFIC_TEMPLATES.get(specific_key)
    if specific:
        template    = specific
        plan_type   = specific["plan_type"]
        plan_status = "ready_for_review"
    else:
        template    = _TEMPLATES.get(action["action_type"], _DEFAULT_TEMPLATE)
        plan_type   = action["action_type"]
        plan_status = "draft"

    plan_hash = _plan_idempotency_hash(
        action_id=action["action_id"],
        incident_id=action["incident_id"],
        diagnosis_id=action.get("diagnosis_id"),
        action_type=action["action_type"],
        action_context_hash=action.get("context_hash") or "",
    )

    existing_hash = _existing_plan_hash(conn, action_id)

    if existing_hash == plan_hash and not force:
        # Exact match — return the existing plan
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM execution_plans WHERE action_id = %s AND context_hash = %s AND status != 'cancelled' LIMIT 1",
            (action_id, plan_hash),
        )
        row = cur.fetchone()
        if row:
            return {"created": False, "plan": dict(row)}

    if existing_hash and force:
        # Cancel stale plan before creating a new one
        cur = conn.cursor()
        now = datetime.now(timezone.utc)
        cur.execute(
            """
            UPDATE execution_plans
               SET status = 'cancelled', updated_at = %s
             WHERE action_id = %s AND status NOT IN ('cancelled')
            """,
            (now, action_id),
        )

    plan = _insert_plan(conn, action=action, template=template, safety=safety,
                        plan_hash=plan_hash, actor=actor,
                        plan_type=plan_type, status=plan_status)
    conn.commit()

    _log_plan_audit(
        action_id=action_id,
        plan_id=plan["plan_id"],
        incident_id=action["incident_id"],
        diagnosis_id=action.get("diagnosis_id"),
        actor=actor,
        event="created",
    )
    logger.info("execution plan created: plan=%s action=%s risk=%s", plan["plan_id"], action_id, safety["risk_level"])
    return {"created": True, "plan": plan}


def get_execution_plans_for_action(conn, action_id: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT plan_id, action_id, incident_id, diagnosis_id, plan_type, status,
               risk_level, execution_allowed, requires_final_approval,
               title, summary, prechecks, steps, rollback_steps,
               expected_impact, safety_notes, blocked_reason,
               planner_version, context_hash, created_by, created_at, updated_at
          FROM execution_plans
         WHERE action_id = %s
         ORDER BY created_at DESC
        """,
        (action_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def get_execution_plans_for_incident(conn, incident_id: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT plan_id, action_id, incident_id, diagnosis_id, plan_type, status,
               risk_level, execution_allowed, requires_final_approval,
               title, summary, prechecks, steps, rollback_steps,
               expected_impact, safety_notes, blocked_reason,
               planner_version, context_hash, created_by, created_at, updated_at
          FROM execution_plans
         WHERE incident_id = %s
         ORDER BY created_at DESC
        """,
        (incident_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def cancel_execution_plan(conn, plan_id: int, actor_user_id: Optional[int] = None) -> dict:
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    cur.execute(
        """
        UPDATE execution_plans
           SET status = 'cancelled', updated_at = %s
         WHERE plan_id = %s AND status != 'cancelled'
         RETURNING plan_id, action_id, incident_id, diagnosis_id, status, updated_at
        """,
        (now, plan_id),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Plan {plan_id} not found or already cancelled")
    conn.commit()
    result = dict(row)
    _log_plan_audit(
        action_id=result["action_id"],
        plan_id=plan_id,
        incident_id=result["incident_id"],
        diagnosis_id=result.get("diagnosis_id"),
        actor=str(actor_user_id or "admin"),
        event="cancelled",
    )
    return result
