"""
rule_based_diagnostics — deterministic fallback when LLM is unavailable.

Returns the same schema as the LLM response so callers don't need to branch.
Only covers common deploy/site/security patterns; everything else gets a generic response.
"""
from typing import Optional


_RULES: list[tuple[frozenset, dict]] = [
    (
        frozenset({"node_sass_incompatible"}),
        {
            "summary": "Dependencia node-sass incompatible con Node 20.",
            "root_cause": "node-sass no compila con versiones modernas de Node. La dependencia está obsoleta.",
            "recommended_next_steps": [
                "Reemplazar node-sass por sass en package.json",
                "Ejecutar: npm uninstall node-sass && npm install sass",
                "Actualizar imports de @import a las nuevas sintaxis si aplica",
            ],
            "customer_message": (
                "Tu proyecto usa node-sass, una librería que no es compatible con el entorno de build actual (Node 20). "
                "Migrá a sass ejecutando: npm uninstall node-sass && npm install sass"
            ),
            "admin_notes": "Problema conocido. Migración directa a sass. Sin impacto en prod.",
            "confidence": 0.95,
        },
    ),
    (
        frozenset({"github_branch_not_found"}),
        {
            "summary": "La rama especificada no existe en el repositorio.",
            "root_cause": "El nombre de rama no coincide con ninguna rama en el repo remoto.",
            "recommended_next_steps": [
                "Verificar que la rama exista en GitHub",
                "Revisar mayúsculas/minúsculas en el nombre de la rama",
                "Actualizar la configuración del deploy con la rama correcta",
            ],
            "customer_message": (
                "La rama que configuraste para el deploy no existe en el repositorio. "
                "Verificá el nombre exacto de la rama en GitHub y actualizá la configuración."
            ),
            "admin_notes": "Error de configuración del usuario. No requiere intervención de infra.",
            "confidence": 0.9,
        },
    ),
    (
        frozenset({"github_private_repo_unauthorized"}),
        {
            "summary": "Repositorio privado sin acceso autorizado.",
            "root_cause": "El repo es privado y no se proporcionó token de acceso válido.",
            "recommended_next_steps": [
                "Hacer el repositorio público en GitHub",
                "O configurar un deploy token con acceso de lectura al repo",
            ],
            "customer_message": (
                "Tu repositorio es privado y el sistema no tiene acceso para clonarlo. "
                "Podés hacerlo público o generar un token de acceso con permisos de lectura."
            ),
            "admin_notes": "Repositorio privado. El usuario debe autorizar acceso o cambiar a público.",
            "confidence": 0.9,
        },
    ),
    (
        frozenset({"invalid_repo_url"}),
        {
            "summary": "URL del repositorio inválida o malformada.",
            "root_cause": "La URL no sigue el formato esperado de GitHub o contiene caracteres inválidos.",
            "recommended_next_steps": [
                "Verificar el formato: https://github.com/usuario/repositorio.git",
                "Eliminar espacios o caracteres especiales de la URL",
            ],
            "customer_message": (
                "La URL del repositorio no es válida. "
                "Asegurate de usar el formato correcto: https://github.com/usuario/repo.git"
            ),
            "admin_notes": "URL malformada ingresada por el usuario. Revisar validación de frontend.",
            "confidence": 0.9,
        },
    ),
    (
        frozenset({"build_failed"}),
        {
            "summary": "El comando de build falló durante la compilación.",
            "root_cause": "Error en el proceso de build. Puede ser por dependencias faltantes, errores de sintaxis o configuración incorrecta.",
            "recommended_next_steps": [
                "Revisar los logs técnicos del deploy para el error exacto",
                "Verificar que el build funcione localmente",
                "Revisar la versión de Node requerida vs disponible (Node 20)",
            ],
            "customer_message": (
                "El proceso de compilación falló. Revisá los logs del deploy para ver el error específico, "
                "y verificá que tu proyecto compile correctamente en tu entorno local."
            ),
            "admin_notes": "Error de build genérico. Revisar logs técnicos para causa raíz.",
            "confidence": 0.5,
        },
    ),
    (
        frozenset({"ssl_provisioning_timeout"}),
        {
            "summary": "Timeout en el aprovisionamiento del certificado SSL.",
            "root_cause": "El proveedor ACME no pudo verificar el dominio dentro del tiempo límite. Puede ser por DNS aún propagando o firewall bloqueando el challenge.",
            "recommended_next_steps": [
                "Verificar que el DNS del dominio apunte correctamente al servidor",
                "Esperar 10-15 minutos para propagación DNS y reintentar",
                "Verificar que el puerto 80 esté accesible públicamente",
            ],
            "customer_message": (
                "El certificado SSL no se pudo generar a tiempo. "
                "Esto suele ocurrir cuando el DNS aún está propagando. "
                "Esperá 15 minutos y volvé a intentar."
            ),
            "admin_notes": "Posible problema de propagación DNS o challenge ACME bloqueado. Verificar Traefik logs.",
            "confidence": 0.75,
        },
    ),
    (
        frozenset({"site_returns_502", "site_returns_503"}),
        {
            "summary": "El sitio retorna error 5xx — posible caída del contenedor.",
            "root_cause": "El contenedor Docker no está respondiendo. Puede estar crasheado, reiniciándose o saturado.",
            "recommended_next_steps": [
                "Verificar estado del contenedor: docker ps -a",
                "Revisar logs del contenedor: docker logs <container_name>",
                "Reiniciar el contenedor si está en estado exited",
            ],
            "customer_message": (
                "Tu sitio no está respondiendo. El servidor está experimentando problemas. "
                "Nuestro equipo fue notificado. Si el problema persiste en 10 minutos, contactá soporte."
            ),
            "admin_notes": "Contenedor posiblemente caído. Verificar docker ps y logs.",
            "confidence": 0.7,
        },
    ),
    (
        frozenset({"site_critical"}),
        {
            "summary": "Sitio en estado crítico — múltiples fallas detectadas.",
            "root_cause": "El health check detectó fallas repetidas. El contenedor puede estar caído o en bucle de reinicio.",
            "recommended_next_steps": [
                "Revisar logs del contenedor inmediatamente",
                "Verificar uso de memoria y CPU",
                "Considerar escalado o reinicio del servicio",
            ],
            "customer_message": (
                "Tu sitio está experimentando problemas críticos de disponibilidad. "
                "Estamos investigando. Te contactaremos si se requiere acción de tu parte."
            ),
            "admin_notes": "Falla crítica de sitio. Requiere intervención de ops.",
            "confidence": 0.6,
        },
    ),
]


def diagnose_without_llm(incident_type: str, context: dict) -> dict:
    """
    Return a rule-based diagnosis dict matching the LLM response schema.
    Always succeeds — falls back to a generic response if no rule matches.
    """
    for codes, template in _RULES:
        if incident_type in codes:
            return {
                "severity": context.get("severity", "warning"),
                "summary": template["summary"],
                "root_cause": template["root_cause"],
                "recommended_next_steps": template["recommended_next_steps"],
                "customer_message": template["customer_message"],
                "admin_notes": template["admin_notes"],
                "confidence": template["confidence"],
                "diagnosis_source": "rule_based",
            }

    return {
        "severity": context.get("severity", "warning"),
        "summary": f"Incidente detectado: {incident_type}",
        "root_cause": "Causa raíz no determinada automáticamente. Revisión manual recomendada.",
        "recommended_next_steps": [
            "Revisar los logs del sistema para más contexto",
            "Verificar el estado del contenedor afectado",
        ],
        "customer_message": (
            "Se detectó un problema en tu servicio. "
            "Nuestro equipo está revisando. Si el problema persiste, contactá soporte."
        ),
        "admin_notes": f"Incidente tipo '{incident_type}' sin regla específica. Revisión manual.",
        "confidence": 0.3,
        "diagnosis_source": "rule_based",
    }
