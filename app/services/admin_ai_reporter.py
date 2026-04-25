"""
Admin AI Reporter — daily platform intelligence report.

Collects all platform data (read-only), generates a Claude analysis,
and emails it to the admin. Also available on-demand via /admin/report.

Scheduled daily at ~8 AM UTC via scheduler_runner.py.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List

logger = logging.getLogger(__name__)

_ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "rubenluxor@hostingguard.lat")


# ── Data collection ───────────────────────────────────────────────────────────

def _collect_platform_data() -> Dict:
    """Gather all platform stats from DB. Read-only, no side effects."""
    from app.infra.audit.hosting_repository import HostingRepository
    from app.infra.audit.health_repository import HealthRepository
    from app.infra.audit.user_repository import UserRepository
    from app.infra.db import get_connection, release_connection

    hosting_repo = HostingRepository()
    health_repo  = HealthRepository()
    user_repo    = UserRepository()

    now = datetime.now(timezone.utc)
    since_24h = (now - timedelta(hours=24)).isoformat()

    data: Dict = {"generated_at": now.isoformat()}

    # ── Hostings ──────────────────────────────────────────────────────────────
    try:
        all_hostings = hosting_repo.get_all_hostings()
        data["hostings_total"]   = len(all_hostings)
        data["hostings_active"]  = sum(1 for h in all_hostings if h.get("status") == "active")
        data["hostings_stopped"] = sum(1 for h in all_hostings if h.get("status") == "stopped")
        data["hostings_error"]   = sum(1 for h in all_hostings if h.get("status") in ("error", "zombie"))
        data["hostings_list"]    = all_hostings
    except Exception as exc:
        logger.warning("admin_reporter: hostings collection failed: %s", exc)
        data["hostings_total"] = 0
        data["hostings_list"]  = []

    # ── Health scores for active hostings ─────────────────────────────────────
    health_summary = []
    try:
        active = [h for h in data.get("hostings_list", []) if h.get("status") == "active"]
        for h in active[:50]:  # cap at 50 to avoid slow reports
            health = health_repo.get_latest_health(h["hosting_id"])
            if health:
                health_summary.append({
                    "name":     h["name"],
                    "plan":     h["plan"],
                    "score":    health.get("score", 100),
                    "cpu":      health.get("cpu", 0),
                    "ram":      health.get("ram", 0),
                    "status":   health.get("status", "unknown"),
                })
        health_summary.sort(key=lambda x: x["score"])
    except Exception as exc:
        logger.warning("admin_reporter: health collection failed: %s", exc)
    data["health_summary"] = health_summary

    # ── Alerts last 24h (all users) ───────────────────────────────────────────
    conn = None
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            """
            SELECT level, COUNT(*) AS cnt
            FROM site_alerts
            WHERE created_at >= %s
            GROUP BY level
            ORDER BY cnt DESC
            """,
            (since_24h,),
        )
        data["alerts_24h"] = {r["level"]: r["cnt"] for r in cur.fetchall()}

        cur.execute(
            """
            SELECT sa.message, sa.level, sa.created_at, h.name AS hosting_name
            FROM site_alerts sa
            JOIN hostings h ON h.hosting_id = sa.site_id
            WHERE sa.created_at >= %s AND sa.resolved = 0
            ORDER BY sa.created_at DESC
            LIMIT 10
            """,
            (since_24h,),
        )
        data["alerts_recent"] = [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("admin_reporter: alerts collection failed: %s", exc)
        data["alerts_24h"]    = {}
        data["alerts_recent"] = []
    finally:
        if conn:
            from app.infra.db import release_connection
            release_connection(conn)

    # ── Orchestrator events last 24h ──────────────────────────────────────────
    conn = None
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            """
            SELECT event_type, COUNT(*) AS cnt
            FROM orchestrator_events
            WHERE created_at >= %s
            GROUP BY event_type
            ORDER BY cnt DESC
            """,
            (since_24h,),
        )
        data["events_24h"] = {r["event_type"]: r["cnt"] for r in cur.fetchall()}

        cur.execute(
            """
            SELECT event_type, message, container_name, cpu_pct, mem_pct, created_at
            FROM orchestrator_events
            WHERE created_at >= %s AND risk_level IN ('high', 'critical')
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (since_24h,),
        )
        data["events_critical"] = [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("admin_reporter: events collection failed: %s", exc)
        data["events_24h"]      = {}
        data["events_critical"] = []
    finally:
        if conn:
            from app.infra.db import release_connection
            release_connection(conn)

    # ── New users last 24h ────────────────────────────────────────────────────
    conn = None
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM users WHERE created_at >= %s",
            (since_24h,),
        )
        row = cur.fetchone()
        data["new_users_24h"] = row["cnt"] if row else 0

        cur.execute("SELECT COUNT(*) AS cnt FROM users")
        row = cur.fetchone()
        data["users_total"] = row["cnt"] if row else 0
    except Exception as exc:
        logger.warning("admin_reporter: users collection failed: %s", exc)
        data["new_users_24h"] = 0
        data["users_total"]   = 0
    finally:
        if conn:
            from app.infra.db import release_connection
            release_connection(conn)

    return data


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_report_prompt(data: Dict) -> str:
    now_str = data.get("generated_at", "")

    # Format health summary
    health_lines = []
    for h in data.get("health_summary", []):
        emoji = "🔴" if h["score"] < 60 else "🟡" if h["score"] < 85 else "🟢"
        health_lines.append(
            f"  {emoji} {h['name']} ({h['plan']}) — score {h['score']}/100, CPU {h['cpu']}%, RAM {h['ram']}%"
        )

    # Format recent alerts
    alert_lines = []
    for a in data.get("alerts_recent", []):
        ts = str(a.get("created_at", ""))[:16]
        alert_lines.append(f"  [{a['level'].upper()}] {a['hosting_name']}: {a['message']} ({ts})")

    # Format critical events
    event_lines = []
    for e in data.get("events_critical", []):
        ts = str(e.get("created_at", ""))[:16]
        cpu = f"CPU {e['cpu_pct']}%" if e.get("cpu_pct") else ""
        mem = f"RAM {e['mem_pct']}%" if e.get("mem_pct") else ""
        event_lines.append(f"  [{e['event_type']}] {e['container_name']}: {e['message']} {cpu} {mem} ({ts})")

    return f"""Sos el asistente de IA interno de HostingGuard. Tu rol es dar al dueño de la plataforma un reporte ejecutivo diario claro y accionable.

Respondé SIEMPRE en español. Sé directo, técnico y concreto.

=== DATOS DE LA PLATAFORMA ({now_str}) ===

HOSTINGS:
- Total: {data.get('hostings_total', 0)}
- Activos: {data.get('hostings_active', 0)}
- Detenidos: {data.get('hostings_stopped', 0)}
- Con error/zombie: {data.get('hostings_error', 0)}

USUARIOS:
- Total: {data.get('users_total', 0)}
- Nuevos (últimas 24h): {data.get('new_users_24h', 0)}

SALUD DE HOSTINGS ACTIVOS (ordenados por score, peores primero):
{chr(10).join(health_lines) if health_lines else "  Sin datos de salud disponibles"}

ALERTAS (últimas 24h):
- Por nivel: {data.get('alerts_24h', {})}
- Sin resolver (recientes):
{chr(10).join(alert_lines) if alert_lines else "  Sin alertas activas"}

EVENTOS DE ORQUESTADOR (últimas 24h):
- Por tipo: {data.get('events_24h', {})}
- Eventos críticos/alto riesgo:
{chr(10).join(event_lines) if event_lines else "  Sin eventos críticos"}

===

Generá un reporte estructurado con estas secciones EXACTAS:

## 📊 Resumen ejecutivo
(2-3 oraciones sobre el estado general de la plataforma)

## 🔴 Requiere atención inmediata
(hostings o situaciones que necesitan acción HOY — si no hay nada, decir "Todo en orden")

## ⚠️ Monitorear hoy
(situaciones que hay que vigilar pero no son urgentes — si no hay, omitir)

## 📈 Métricas del día
(números clave: uptime, alertas, eventos, nuevos usuarios)

## 💡 Recomendaciones
(1-3 acciones concretas que el admin debería hacer esta semana)

Sé específico: nombrá los hostings problemáticos, citá métricas concretas. No uses frases genéricas.
"""


# ── Claude call ───────────────────────────────────────────────────────────────

async def _call_claude_report(prompt: str) -> str:
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        raise RuntimeError("CLAUDE_API_KEY not set")

    try:
        from anthropic import Anthropic
    except ImportError:
        raise RuntimeError("anthropic SDK not installed")

    client = Anthropic(api_key=api_key)
    model  = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")

    def _sync():
        return client.messages.create(
            model=model,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
            timeout=30,
        )

    loop = asyncio.get_running_loop()
    resp = await loop.run_in_executor(None, _sync)

    if not resp.content:
        raise RuntimeError("Empty Claude response")
    return resp.content[0].text.strip()


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_platform_report() -> str:
    """Collect data + call Claude. Returns the full report text."""
    data   = _collect_platform_data()
    prompt = _build_report_prompt(data)
    return await _call_claude_report(prompt)


def run_daily_report() -> None:
    """
    Entry point for the scheduler (sync wrapper).
    Generates report and sends it by email.
    """
    async def _async_run():
        try:
            report = await generate_platform_report()
            _send_report_email(report)
            logger.info("admin_reporter: daily report sent to %s", _ADMIN_EMAIL)
        except Exception as exc:
            logger.error("admin_reporter: daily report failed: %s", exc, exc_info=True)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_async_run())
    except RuntimeError:
        asyncio.run(_async_run())


def _send_report_email(report_text: str) -> None:
    from app.services.mailer import _send, _html_wrap, _cfg

    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    subject = f"HostingGuard — Reporte diario {now_str}"

    # Convert markdown-ish to HTML
    html_body = report_text.replace("\n", "<br>")
    for emoji_header in ["📊", "🔴", "⚠️", "📈", "💡"]:
        html_body = html_body.replace(
            f"## {emoji_header}",
            f'<h3 style="margin-top:20px;color:#4f46e5">{emoji_header}',
        )
    # Close any open h3 tags (simple heuristic)
    import re
    html_body = re.sub(
        r'(<h3[^>]*>)(.*?)(<br>)',
        r'\1\2</h3>',
        html_body,
    )

    body_html = f"""
<div style="font-family:monospace;font-size:14px;line-height:1.7;color:#e5e7eb;background:#0d0d0f;padding:24px;border-radius:8px">
<p style="color:#6b7280;font-size:12px">Generado: {now_str}</p>
{html_body}
<hr style="border-color:#1f2937;margin-top:24px">
<p style="color:#6b7280;font-size:11px">HostingGuard Admin AI — solo lectura, sin acciones automáticas</p>
</div>
"""
    app_url = _cfg()["app_url"]
    _send(
        to_email=_ADMIN_EMAIL,
        subject=subject,
        html=_html_wrap(subject, body_html, app_url),
        text=report_text,
    )
