"""
Support AI — direct Claude integration for customer support chat.

Calls Claude directly (not via advisory engine) with:
  - A support-oriented system prompt
  - Rich hosting context: status, CPU/RAM, health score, active alerts, last diagnosis
  - Full conversation history (user/assistant turns)

Caching: applied to first responses only (no history context).
Follow-up messages always hit Claude for accurate, context-aware replies.
"""
import asyncio
import hashlib
import logging
import os
from typing import Dict, List, Optional, Tuple

from app.infra.audit.support_cache_repository import SupportCacheRepository

logger = logging.getLogger(__name__)

_support_cache_repo = SupportCacheRepository()

_PRIORITY_MAP = {
    "Sitio caído":        "high",
    "Error en WordPress": "medium",
    "Sitio lento":        "medium",
    "Problema de billing": "low",
    "Ayuda técnica":      "medium",
    "Otro":               "low",
}

_TTL_CONFIG = {
    "Sitio caído":        15,
    "Sitio lento":        60,
    "Error en WordPress": 360,
    "Problema de billing": 5,
    "Ayuda técnica":      120,
}

_SYSTEM_PROMPT = """Eres el asistente de soporte de HostingGuard, una plataforma de hosting administrado para sitios WordPress y aplicaciones web.
Cada cliente tiene su propio contenedor Docker aislado con WordPress + MariaDB.

PERSONALIDAD:
- Directo, claro y empático. No sos un bot genérico.
- Respondés en español, informal pero profesional.
- Siempre preguntás "¿Esto resolvió tu problema?" al final, EXCEPTO cuando estás esperando información del cliente.
- Máximo 4-5 pasos por respuesta. Sin paja.

ACCIONES QUE EL CLIENTE PUEDE HACER DESDE EL DASHBOARD:
- Iniciar / Detener / Reiniciar su contenedor (botones en la tarjeta del hosting)
- Ver logs del contenedor en tiempo real (ícono de archivo)
- Ver métricas de CPU y RAM en el panel principal
- Importar un backup de WordPress (.zip, .wpress, .sql)
- Acceder al wp-admin con credenciales visibles en el panel (usuario: admin, contraseña mostrada)
- Ejecutar diagnóstico automático (botón "Diagnosticar" en la tarjeta del hosting)
- Aplicar fix automático si el diagnóstico lo sugiere (botón "Aplicar fix")

REGLAS:
1. Si el contenedor tiene status "stopped" o "exited": lo primero es sugerir reiniciarlo desde el panel.
2. Para errores de WordPress: guiar a wp-admin o al diagnóstico automático antes de pasos manuales.
3. Si ves alertas críticas activas en los datos del hosting: mencionarlas directamente.
4. Si el último diagnóstico detectó un problema concreto: citarlo y sugerir aplicar el fix automático.
5. Si el problema no tiene solución desde el panel del cliente, recomendar escalar a soporte humano.
6. Nunca inventés información que no esté en los datos del hosting.
7. No prometás tiempos de resolución.
8. Para problemas de billing: solo informar, no hacer cambios.
9. REGLA CRÍTICA — SITIO FUNCIONANDO SEGÚN SISTEMAS: Si la VERIFICACIÓN EN TIEMPO REAL muestra contenedor "running" Y sitio respondiendo HTTP correctamente, decile al cliente de forma directa y sin rodeos: "Nuestros sistemas confirman que tu sitio está funcionando en este momento." Explicá que el problema es probablemente local: limpiar caché del navegador, probar en modo incógnito, revisar si tiene una VPN o extensión activa. NO sugieras reiniciar, diagnosticar ni hacer cambios en el servidor — el servidor está bien. Si el cliente insiste en que "está caído", reiterá que los datos en tiempo real muestran lo contrario y pedile que verifique desde otro dispositivo o red.
"""


def _get_sub_intent(description: str) -> str:
    normalized = description.lower()
    for char in [".", ",", "!", "?", "(", ")", "\n", "\r", "-", "_"]:
        normalized = normalized.replace(char, " ")
    words = [w.strip() for w in normalized.split() if len(w.strip()) > 3]
    if not words:
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]
    fingerprint = "|".join(sorted(set(words)))
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]


def _build_hosting_context(
    hosting_data: Dict,
    metrics: Optional[Dict] = None,
    alerts: Optional[List] = None,
    diagnosis: Optional[Dict] = None,
    live_status: Optional[Dict] = None,
) -> str:
    lines = []
    is_wp = "_wp_" in (hosting_data.get("container_name") or "")

    lines.append("=== DATOS DEL HOSTING DEL CLIENTE ===")
    lines.append(f"Nombre: {hosting_data.get('name', 'N/A')}")
    lines.append(f"Plan: {hosting_data.get('plan', 'N/A')}")
    lines.append(f"Estado del contenedor: {hosting_data.get('status', 'N/A')}")
    lines.append(f"URL: {hosting_data.get('subdomain', 'N/A')}")
    lines.append(f"Tipo: {'WordPress' if is_wp else 'Sitio web'}")

    if metrics:
        score = metrics.get("score")
        cpu = metrics.get("cpu")
        ram = metrics.get("ram")
        health_status = metrics.get("status", "N/A")
        if score is not None:
            lines.append(f"\nSalud: {score}/100 ({health_status})")
        if cpu is not None:
            lines.append(f"CPU: {cpu}% | RAM: {ram}%")

    active_alerts = [a for a in (alerts or []) if not a.get("resolved")]
    if active_alerts:
        lines.append(f"\nAlertas activas ({len(active_alerts)}):")
        for a in active_alerts[:3]:
            lines.append(f"  [{a.get('level', '?').upper()}] {a.get('message', '')}")

    if live_status:
        container_state = live_status.get("container_state")
        http_ok = live_status.get("http_ok")
        http_status = live_status.get("http_status")
        lines.append(f"\nVERIFICACIÓN EN TIEMPO REAL:")
        if container_state:
            lines.append(f"  Contenedor (LIVE): {container_state}")
        if http_status is not None:
            if http_ok:
                lines.append(f"  Sitio web (LIVE): RESPONDE correctamente (HTTP {http_status})")
            else:
                lines.append(f"  Sitio web (LIVE): NO RESPONDE — {http_status}")

    if diagnosis:
        lines.append(f"\nÚltimo diagnóstico automático:")
        lines.append(f"  Severidad: {diagnosis.get('severity', 'N/A')}")
        lines.append(f"  Problema: {diagnosis.get('summary', 'N/A')}")
        if diagnosis.get("root_cause"):
            lines.append(f"  Causa raíz: {diagnosis['root_cause']}")
        if diagnosis.get("fix_action"):
            fix_steps = diagnosis.get("fix_steps") or []
            lines.append(f"  Fix disponible: {diagnosis['fix_action']}")
            if fix_steps:
                lines.append(f"  Pasos: {'; '.join(fix_steps[:2])}")

    lines.append("===")
    return "\n".join(lines)


def _check_live_status(hosting_data: Dict) -> Dict:
    """
    Fetch real-time container state + HTTP reachability.
    Returns dict with container_state and http_status. Never raises.
    """
    import subprocess
    result: Dict = {}

    container_name = hosting_data.get("container_name")

    # Live container state via docker inspect
    if container_name:
        try:
            r = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Status}}", container_name],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                result["container_state"] = r.stdout.strip()
        except Exception as exc:
            logger.debug("support_ai: docker inspect failed for %s: %s", container_name, exc)

    # HTTP check — run curl inside the container to avoid Docker networking limitations.
    # External subdomain DNS is unreachable from inside the app container; localhost:80 always works.
    if container_name:
        try:
            r = subprocess.run(
                [
                    "docker", "exec", container_name,
                    "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                    "--max-time", "4", "http://localhost",
                ],
                capture_output=True, text=True, timeout=8,
            )
            code_str = r.stdout.strip()
            if r.returncode == 0 and code_str.isdigit():
                code = int(code_str)
                result["http_status"] = code
                result["http_ok"] = code < 400
            else:
                result["http_status"] = f"no_responde (exit {r.returncode})"
                result["http_ok"] = False
        except Exception as exc:
            result["http_status"] = f"no_responde ({type(exc).__name__})"
            result["http_ok"] = False

    return result


def _fetch_live_context(hosting_data: Dict) -> Tuple[Optional[Dict], Optional[List], Optional[Dict], Dict]:
    """
    Fetch health metrics, active alerts, last diagnosis, and live status.
    Returns (metrics, alerts, diagnosis, live_status). All non-critical.
    """
    from app.infra.audit.health_repository import HealthRepository
    from app.infra.audit.ai_diagnosis_repository import AIDiagnosisRepository

    hosting_id = hosting_data.get("hosting_id")
    user_id = hosting_data.get("user_id")
    if not hosting_id:
        return None, None, None, {}

    health_repo = HealthRepository()
    diag_repo = AIDiagnosisRepository()

    metrics = None
    alerts = None
    diagnosis = None

    try:
        metrics = health_repo.get_latest_health(hosting_id)
    except Exception as exc:
        logger.debug("support_ai: failed to fetch metrics for hosting %s: %s", hosting_id, exc)

    try:
        if user_id:
            all_alerts = health_repo.get_user_alerts(user_id, limit=10)
            alerts = [a for a in all_alerts if a.get("site_id") == hosting_id]
    except Exception as exc:
        logger.debug("support_ai: failed to fetch alerts for hosting %s: %s", hosting_id, exc)

    try:
        diagnoses = diag_repo.get_by_hosting(hosting_id, limit=1)
        if diagnoses:
            diagnosis = diagnoses[0]
    except Exception as exc:
        logger.debug("support_ai: failed to fetch diagnosis for hosting %s: %s", hosting_id, exc)

    live_status = _check_live_status(hosting_data)

    return metrics, alerts, diagnosis, live_status


def _build_messages(
    description: str,
    message_history: List[Dict],
    context_block: str,
) -> List[Dict]:
    """
    Build Anthropic messages array from ticket history.
    Merges consecutive same-role messages to satisfy the alternating requirement.
    """
    # Filter out system messages — they're not part of the conversation
    relevant = [
        m for m in message_history
        if m.get("sender_type") in ("user", "ai", "staff")
        and m.get("content", "").strip()
    ]

    if not relevant:
        user_content = f"{context_block}\n\n{description}" if context_block else description
        return [{"role": "user", "content": user_content}]

    messages: List[Dict] = []
    for i, msg in enumerate(relevant):
        sender = msg.get("sender_type")
        content = msg.get("content", "").strip()
        role = "user" if sender == "user" else "assistant"

        # Prepend context block to the very first user message
        if i == 0 and role == "user" and context_block:
            content = f"{context_block}\n\n{content}"

        # Merge consecutive same-role messages instead of duplicating
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += f"\n\n{content}"
        else:
            messages.append({"role": role, "content": content})

    # Ensure the conversation ends with the latest user message (the new one being answered)
    # If the last message is already from the user, we're good.
    # If not, append the description as a user follow-up.
    if not messages or messages[-1]["role"] != "user":
        messages.append({"role": "user", "content": description})

    return messages


async def _call_claude(system: str, messages: List[Dict], max_tokens: int = 700) -> str:
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        raise RuntimeError("CLAUDE_API_KEY not set")

    try:
        from anthropic import Anthropic
    except ImportError:
        raise RuntimeError("anthropic SDK not installed")

    client = Anthropic(api_key=api_key)
    model = os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022")
    timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "15"))

    def _sync():
        return client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            timeout=timeout,
        )

    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(None, _sync)

    if not response.content:
        raise RuntimeError("Empty Claude response")
    text = response.content[0].text.strip()
    if not text:
        raise RuntimeError("Empty Claude response text")
    return text


async def generate_support_response(
    category: str,
    description: str,
    ai_prompt_hint: str = "",
    hosting_data: Optional[Dict] = None,
    message_history: Optional[List[Dict]] = None,
) -> Tuple[str, Optional[int], str]:
    """
    Generate AI response for a support ticket.
    Returns (message, cache_id, source) where source is "cache", "claude", or "fallback".
    """
    history = message_history or []
    is_followup = bool(history)

    # ── 1. Cache check (first messages only, not follow-ups) ──────────────────
    cache_id = None
    if not is_followup:
        sub_intent = _get_sub_intent(description)
        hosting_id = hosting_data.get("hosting_id") if hosting_data else None
        cached = _support_cache_repo.get_best_match(category, sub_intent, hosting_id)
        if cached:
            if not hosting_data or cached.get("hosting_status_when_cached") == hosting_data.get("status"):
                logger.info("support_ai: cache HIT category=%s intent=%s", category, sub_intent)
                _support_cache_repo.increment_use(cached["cache_id"])
                return cached["ai_response"], cached["cache_id"], "cache"

    # ── 2. Fetch live hosting context ─────────────────────────────────────────
    context_block = ""
    if hosting_data:
        metrics, alerts, diagnosis, live_status = _fetch_live_context(hosting_data)
        context_block = _build_hosting_context(hosting_data, metrics, alerts, diagnosis, live_status)

    # ── 3. Build messages ─────────────────────────────────────────────────────
    system = _SYSTEM_PROMPT
    if ai_prompt_hint:
        system += f"\n\nCATEGORÍA ACTUAL: {category} — {ai_prompt_hint}"

    messages = _build_messages(description, history, context_block)

    # ── 4. Call Claude ────────────────────────────────────────────────────────
    source = "claude"
    try:
        response = await _call_claude(system, messages)
    except Exception as exc:
        logger.error("support_ai: Claude call failed: %s", exc, exc_info=True)
        response = _fallback_response(category, hosting_data)
        source = "fallback"

    # ── 5. Cache first responses (only real Claude replies) ───────────────────
    if source == "claude" and not is_followup:
        try:
            sub_intent = _get_sub_intent(description)
            hosting_id = hosting_data.get("hosting_id") if hosting_data else None
            ttl = _TTL_CONFIG.get(category, 60)
            cache_id = _support_cache_repo.save_cache(
                category=category,
                sub_intent=sub_intent,
                problem_summary=description[:200],
                ai_response=response,
                ttl_minutes=ttl,
                hosting_id=hosting_id,
                hosting_status=hosting_data.get("status") if hosting_data else None,
                hosting_updated_at=hosting_data.get("updated_at") if hosting_data else None,
            )
        except Exception as exc:
            logger.debug("support_ai: cache save failed (non-critical): %s", exc)

    return response, cache_id, source


def _fallback_response(category: str, hosting_data: Optional[Dict] = None) -> str:
    """Fallback when Claude is unavailable."""
    status = (hosting_data or {}).get("status", "")
    if status in ("stopped", "exited", "error") and category == "Sitio caído":
        return (
            "El contenedor de tu hosting aparece como detenido.\n\n"
            "1. En el dashboard, buscá tu hosting y hacé clic en el botón **Iniciar** (triángulo verde)\n"
            "2. Esperá 30-60 segundos y recargá tu sitio\n"
            "3. Si no inicia, usá el botón **Diagnosticar** para obtener más información\n\n"
            "¿Esto resolvió tu problema?"
        )

    responses = {
        "Sitio caído": (
            "Vamos a diagnosticar esto:\n\n"
            "1. En el dashboard, revisá el estado de tu hosting (debe mostrar ● active en verde)\n"
            "2. Si está detenido, hacé clic en **Iniciar**\n"
            "3. Si está activo pero el sitio no carga, usá el botón **Diagnosticar**\n"
            "4. Revisá los logs (ícono de archivo) buscando errores recientes\n\n"
            "¿Esto resolvió tu problema?"
        ),
        "Sitio lento": (
            "Para diagnosticar lentitud:\n\n"
            "1. Revisá las métricas de CPU y RAM en tu dashboard\n"
            "2. Si CPU o RAM superan el 80%, usá **Reiniciar** para liberar recursos\n"
            "3. En wp-admin → Plugins, desactivá plugins recientes uno a uno\n"
            "4. Usá el botón **Diagnosticar** para análisis automático\n\n"
            "¿Esto resolvió tu problema?"
        ),
        "Error en WordPress": (
            "Para errores en WordPress:\n\n"
            "1. Intentá acceder a wp-admin (credenciales visibles en tu panel)\n"
            "2. Usá **Diagnosticar** para que el sistema identifique la causa\n"
            "3. Si el diagnóstico propone un fix automático, aplicalo desde el panel\n"
            "4. Si ves pantalla blanca, en wp-admin → Plugins → desactivá el último instalado\n\n"
            "¿Esto resolvió tu problema?"
        ),
    }
    return responses.get(
        category,
        "Recibí tu consulta. Podés usar el botón **Diagnosticar** en tu panel para un análisis automático. "
        "Si el problema persiste, puedo conectarte con un colaborador.\n\n¿Hay algo más que puedas contarme?",
    )


def get_ticket_priority(category: str) -> str:
    return _PRIORITY_MAP.get(category, "medium")
