import asyncio
import logging
import subprocess

from fastapi import Depends, HTTPException

from app.api.security import verify_token
from app.core.alert_engine import check_alerts
from app.core.debug_context_builder import build_debug_context
from app.core.health_engine import calculate_health_score
from app.infra.audit.hosting_repository import HostingRepository
from app.repositories import health_repo

logger = logging.getLogger(__name__)

hosting_repo = HostingRepository()


async def _run_docker(*args, timeout: int = 30) -> subprocess.CompletedProcess:
    """Ejecuta un comando Docker de forma no bloqueante (sin bloquear el event loop)."""
    loop = asyncio.get_running_loop()
    cmd = list(args)
    return await loop.run_in_executor(
        None,
        lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=timeout),
    )


async def diagnose_hosting(hosting_id: str, user: dict = Depends(verify_token)):
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
            from app.api.main import ai_orchestrator

            diagnosis = await ai_orchestrator.enrich(decision=decision_base, debug_context=debug_context)
        except Exception as e:
            logging.error(f"AI Orchestrator failed: {e}")
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

        # Agrupar errores para el engine
        grouped_errors = {}
        for err in debug_context["logs"]["parsed_errors"]:
            etype = err.get("type", "unknown")
            grouped_errors[etype] = grouped_errors.get(etype, 0) + 1

        engine_errors = [{"type": k, "count": v} for k, v in grouped_errors.items()]

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
                    error_count=len(debug_context["logs"]["parsed_errors"]),
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

        return {
            "status": status,
            "metrics": metrics,
            "health_score": health_result["score"],
            "diagnosis": diagnosis,
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
