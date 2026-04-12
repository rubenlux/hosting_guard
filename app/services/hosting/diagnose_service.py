import asyncio
import logging
import subprocess

from fastapi import Depends, HTTPException, Request

from app.api.security import verify_token
from app.core.alert_engine import check_alerts
from app.core.debug_context_builder import build_debug_context
from app.core.health_engine import calculate_health_score
from app.infra.audit.hosting_repository import HostingRepository
from app.infra.audit.health_repository import HealthRepository

logger = logging.getLogger(__name__)

hosting_repo = HostingRepository()
health_repo = HealthRepository()


import hashlib


def _build_fingerprint(
    score: int,
    cpu: float,
    ram: float,
    parsed_errors: list,
) -> str:
    """
    Stable fingerprint for a health snapshot.
    Same fingerprint → same system state → reuse cached diagnosis.

    CPU/RAM are rounded to 1 decimal to absorb micro-jitter between cycles
    without causing false cache misses on trivially different readings.

    Error signature encodes the *identity* of ACTIONABLE errors only
    (source == "application").  dev_noise and external_probe are excluded
    so that a run with only source-map 404s gets the same fingerprint as a
    clean run — both map to "no real errors", not a distinct broken state.
    """
    actionable = [
        e for e in parsed_errors
        if e.get("source") == "application"
    ]
    error_signature = "-".join(
        sorted(
            f"{e.get('type', '')}:{e.get('file', '')}:{e.get('line', 0)}"
            for e in actionable[:5]
        )
    ) or "none"

    actionable_count = len(actionable)
    raw = f"{score}-{round(cpu, 1)}-{round(ram, 1)}-{actionable_count}-{error_signature}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


async def _run_structured_diagnosis(
    hosting_name: str,
    hosting_id: int,
    user_id: int | None,
    cpu: float,
    ram: float,
    score: int,
    debug_context: dict,
    loop,
    alerts: list | None = None,
    score_breakdown: dict | None = None,
) -> dict | None:
    """
    Structured-diagnosis path (Phase 1.5 + Phase 2):

    1. Build fingerprint from health snapshot.
    2. Cache lookup (get_by_fingerprint) — 24 h TTL.
       HIT  → return cached result immediately (zero LLM cost).
       MISS → continue.
    3. Fetch last 3 diagnoses for RAG history.
    4. Build rich context (context_builder) and prompt (prompt_builder).
    5. Call LLM (claude-sonnet-4-6).
    6. Safe-parse JSON response.
    7. Persist with fingerprint for next lookup.

    Only runs when ENABLE_REAL_LLM=true and CLAUDE_API_KEY is set.
    Any failure is logged as a warning — caller degrades gracefully (returns None).
    """
    import os
    if os.getenv("ENABLE_REAL_LLM", "false").lower() != "true":
        return None

    try:
        from app.core.llm.prompt_builder import build_diagnosis_prompt
        from app.core.llm.context_builder import build_context
        from app.core.llm.safe_parser import safe_parse_llm
        from app.services.ai_client import call_llm
        from app.infra.audit.ai_diagnosis_repository import AIDiagnosisRepository

        # Use only actionable errors throughout the AI pipeline.
        # dev_noise (source maps) and external_probe (bots) must never reach Claude.
        actionable_errors = debug_context["logs"].get("actionable_errors", [])
        repo = AIDiagnosisRepository()

        # ── Phase 1.5: Cache check ──────────────────────────────────────────
        fingerprint = _build_fingerprint(score, cpu, ram, actionable_errors)
        cached = await loop.run_in_executor(
            None,
            lambda: repo.get_by_fingerprint(hosting_id, fingerprint),
        )
        if cached:
            logger.info("Diagnosis cache HIT for hosting_id=%s fp=%s", hosting_id, fingerprint)
            return cached

        # ── Phase 2: RAG — fetch diagnosis history for context ──────────────
        history = await loop.run_in_executor(
            None,
            lambda: repo.get_by_hosting(hosting_id, limit=3),
        )

        # ── Build rich context + prompt ─────────────────────────────────────
        context = build_context(
            hosting_name=hosting_name,
            cpu=cpu,
            ram=ram,
            score=score,
            parsed_errors=actionable_errors,
            logs=debug_context["logs"].get("recent_raw_snippet", ""),
            history=history,
            alerts=alerts or [],
            score_breakdown=score_breakdown,
        )
        prompt = build_diagnosis_prompt(context)

        # ── LLM call ────────────────────────────────────────────────────────
        raw    = await loop.run_in_executor(None, lambda: call_llm(prompt))
        parsed = safe_parse_llm(raw)

        # ── Persist with fingerprint ─────────────────────────────────────────
        saved = await loop.run_in_executor(
            None,
            lambda: repo.save(
                hosting_id=hosting_id,
                user_id=user_id,
                parsed=parsed,
                raw_response=raw,
                fingerprint=fingerprint,
            ),
        )
        return saved or parsed

    except Exception as exc:
        logger.warning("Structured diagnosis skipped: %s", exc)
        return None


async def _run_docker(*args, timeout: int = 30) -> subprocess.CompletedProcess:
    """Ejecuta un comando Docker de forma no bloqueante (sin bloquear el event loop)."""
    loop = asyncio.get_running_loop()
    cmd = list(args)
    return await loop.run_in_executor(
        None,
        lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=timeout),
    )


async def diagnose_hosting(hosting_id: str, request: Request, user: dict = Depends(verify_token)):
    try:
        user_id = user.get("user_id")

        # 1. Validar propiedad
        loop = asyncio.get_running_loop()

        # Intentar convertir id a int si parece numérico para evitar fallos en repo
        query_id = hosting_id
        if hosting_id.isdigit():
            query_id = int(hosting_id)

        hosting = await loop.run_in_executor(None, lambda: hosting_repo.get_hosting(query_id, user_id))

        if not hosting or str(hosting["user_id"]) != str(user_id):
            raise HTTPException(status_code=404, detail="Hosting no encontrado o no tienes permisos")

        container_name = hosting["container_name"]

        # 2. Conseguir metricas basales (CPU, RAM, Status) para el contexto
        status = "unknown"
        metrics = {"cpu": "0%", "memory": "0MiB"}

        try:
            res_inspect = await _run_docker("docker", "inspect", "--format", "{{.State.Status}}", container_name, timeout=5)
            status = res_inspect.stdout.strip()

            if status == "running":
                res_stats = await _run_docker(
                    "docker",
                    "stats",
                    "--no-stream",
                    "--format",
                    "{{.CPUPerc}}|{{.MemUsage}}",
                    container_name,
                    timeout=10,
                )
                pts = res_stats.stdout.strip().split("|")
                if len(pts) == 2:
                    metrics = {"cpu": pts[0], "memory": pts[1]}
        except Exception:
            pass

        # 3. Construir Debug Context (Logs + Métricas + Parsed Errors)
        debug_context = await build_debug_context(container_name, metrics=metrics, limit_logs=60)

        # 4. Decisión simulada de base que alimenta el motor
        decision_base = {
            "overall_status": "unknown"
            if status != "running"
            else "requires_human"
            if debug_context["logs"]["has_errors"]
            else "ready_for_execution",
            "container_name": container_name,
            "hosting_id": hosting_id,
            "metrics": metrics,
        }

        # 5. Llamado al AI Orchestrator para enriquecimiento inteligente
        try:
            from app.core.registry import registry
            try:
                ai_orchestrator = registry.orchestrator
            except RuntimeError:
                ai_orchestrator = registry.get_orchestrator_safe()

            if ai_orchestrator:
                diagnosis = await ai_orchestrator.enrich(decision=decision_base, debug_context=debug_context)
            else:
                diagnosis = {"summary": "AI Orchestrator no configurado.", "requires_human_attention": True}
        except Exception as e:
            logger.error(f"AI Orchestrator failed: {e}")
            diagnosis = {"summary": "Error en diagnóstico inteligente.", "requires_human_attention": True}

        # 6. Cálculo de salud y persistencia (Manual Sync)
        try:
            cpu_val = float(str(metrics.get("cpu", "0")).replace("%", ""))
            mem_str = str(metrics.get("memory", "0"))
            ram_val = float(mem_str.split(" / ")[0].replace("MiB", "").replace("GiB", "").strip())
            if "GiB" in mem_str:
                ram_val *= 1024
        except Exception as e:
            logging.warning(f"Error parsing metrics: {e}")
            cpu_val, ram_val = 0.0, 0.0

        # Agrupar solo errores reales para el engine (dev_noise y external_probe
        # ya tienen source asignado en el parser; health_engine los ignora internamente,
        # pero pasamos la fuente para que el engine pueda aplicar su propio filtro).
        grouped_errors = {}
        for err in debug_context["logs"]["parsed_errors"]:
            etype = err.get("type", "unknown")
            entry = grouped_errors.setdefault(etype, {"type": etype, "count": 0, "source": err.get("source", "application")})
            entry["count"] += 1

        engine_errors = list(grouped_errors.values())

        health_result = calculate_health_score(
            {
                "container_status": status,
                "cpu": cpu_val,
                "ram": ram_val,
                "errors": engine_errors,
            }
        )

        # Persistir en histórico (Async)
        try:
            h_id_db = int(hosting_id) if str(hosting_id).isdigit() else 0
            alert = check_alerts(health_result["score"])
            await loop.run_in_executor(
                None,
                lambda: health_repo.save_health_entry(
                    user_id=user_id,
                    site_id=h_id_db,
                    score=health_result["score"],
                    status=health_result["status"],
                    cpu=cpu_val,
                    ram=ram_val,
                    error_count=len(debug_context["logs"]["actionable_errors"]),
                    warning_count=health_result["warning_count"],
                    alert_type=alert["type"] if alert else None,
                    alert_message=alert["message"] if alert else None,
                ),
            )
            if alert:
                await loop.run_in_executor(
                    None,
                    lambda: health_repo.create_alert(
                        user_id=user_id,
                        site_id=h_id_db,
                        level="critical" if alert["type"] == "critical" else "warning",
                        message=alert["message"],
                    ),
                )
        except Exception as e:
            logging.error(f"Persistence failed in diagnosis: {e}")

        # Structured diagnosis — parallel path, non-blocking failure
        structured = await _run_structured_diagnosis(
            hosting_name=hosting.get("name", container_name),
            hosting_id=h_id_db,
            user_id=user_id,
            cpu=cpu_val,
            ram=ram_val,
            score=health_result["score"],
            debug_context=debug_context,
            loop=loop,
            alerts=[alert] if alert else [],
            score_breakdown=health_result.get("score_breakdown"),
        )

        # ── Sanity clamp: output governance layer ───────────────────────────────
        # The LLM is never the final source of truth.
        # When there are no actionable errors, we own the output entirely —
        # partial field fixes (severity only) leave root_cause / impact / fix_action
        # intact from the LLM, creating semantic contradictions like:
        #   "severity: info" + "root_cause: nginx can't find .map files" + "fix: deploy assets"
        # That breaks user trust immediately, so we replace the full structured object.
        if not debug_context["logs"].get("actionable_errors"):
            structured = {
                "severity":     "info",
                "failure_type": "unknown",
                "summary":      "No se detectaron errores reales en la aplicación.",
                "root_cause":   None,
                "impact":       "No hay impacto. El sistema está funcionando correctamente.",
                "fix_action":   None,
                "fix_steps":    [],
                "evidence":     [],
                "confidence":   0.95,
                "location":     {"file": None, "line": None, "service": "system"},
            }

        return {
            "status": status,
            "metrics": metrics,
            "health_score": health_result["score"],
            # structured (Claude) takes precedence; old AI Orchestrator is the fallback
            "diagnosis": structured or diagnosis,
            "structured_diagnosis": structured,
            "has_hard_errors": debug_context["logs"]["has_errors"],
            "debug_info": {
                "parsed_errors": debug_context["logs"]["parsed_errors"],
                "raw_snippet": debug_context["logs"]["recent_raw_snippet"],
            },
        }
    except Exception as main_err:
        import traceback

        logging.error(f"CRITICAL: diagnose_hosting failed: {main_err}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Fallo crítico en AI Engine: {str(main_err)}")
