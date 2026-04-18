# app/services/expiration_job.py
import logging
import subprocess
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.infra.audit.hosting_repository import HostingRepository
from app.observability.metrics import CONTAINERS_DELETED_TOTAL, CLEANUP_RUNS_TOTAL

logger = logging.getLogger(__name__)

FREE_PLAN_DAYS = 14
# Tiempo máximo en minutos que un hosting puede permanecer en 'expiring' antes de considerarse huérfano
_STALE_EXPIRING_MINUTES = 30


def _recover_stale_expiring() -> None:
    """
    Detecta hostings atascados en estado 'expiring' (proceso previo interrumpido)
    y los reintenta o los revierte a 'active' si Docker tampoco los puede detener.
    Se ejecuta al inicio de cada ciclo del job como paso de recuperación.
    """
    repo = HostingRepository()
    stale = repo.get_stale_expiring_hostings(stale_minutes=_STALE_EXPIRING_MINUTES)
    if not stale:
        return

    logger.warning("Encontrados %d hosting(s) huérfanos en estado 'expiring'. Reintentando.", len(stale))

    for hosting in stale:
        container = hosting["container_name"]
        result = subprocess.run(
            ["docker", "stop", container],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            repo.update_hosting_status(hosting["hosting_id"], "expired")
            logger.info("Hosting huérfano %s marcado como 'expired'.", hosting["hosting_id"])
        else:
            # Docker no puede detenerlo (ya no existe el contenedor, etc.) → revertir a active
            repo.update_hosting_status(hosting["hosting_id"], "active")
            logger.error(
                "No se pudo detener hosting huérfano %s. Revertido a 'active'. Error: %s",
                hosting["hosting_id"],
                result.stderr.decode("utf-8", errors="replace").strip(),
            )


def _expire_single(hosting):
    """
    Intenta detener el contenedor del hosting y manejar el status atómicamente.
    Crea su propia conexión a DB para ser thread-safe.
    Devuelve (hosting, success)
    """
    hosting_repo = HostingRepository()
    container = hosting["container_name"]
    # 1. Marcar en DB como en progreso (operación segura y reversible)
    hosting_repo.update_hosting_status(hosting["hosting_id"], "expiring")
    
    # 2. Ejecutar acción real en Docker
    result = subprocess.run(
        ["docker", "stop", container],
        capture_output=True, timeout=10
    )
    
    if result.returncode == 0:
        hosting_repo.update_hosting_status(hosting["hosting_id"], "expired")
        hosting_repo.log_orchestrator_event(
            container_name=container,
            user_id=hosting["user_id"],
            event_type="PLAN_EXPIRED",
            message="Tu plan gratuito de 14 días ha expirado. Actualizá tu plan para reactivar el sitio."
        )
        return hosting, True
    else:
        # Revertir si Docker falló
        hosting_repo.update_hosting_status(hosting["hosting_id"], "active")
        err_msg = result.stderr.decode('utf-8', errors='replace').strip()
        logger.error(f"Rollback: {container} no pudo detenerse. Error: {err_msg}")
        return hosting, False


def _cleanup_expired_hostings() -> int:
    """Phase 2 of lifecycle management.

    For every hosting already in 'expired' state:
      1. docker rm (idempotent — errors ignored if container doesn't exist)
      2. soft-delete in DB (status='deleted', deleted_at=now)
      3. log cleanup event for audit trail

    Returns the number of hostings successfully cleaned up.
    """
    repo = HostingRepository()
    cleaned = 0
    batch_size = 50
    offset = 0

    while True:
        hostings = repo.get_expired_hostings(batch_size=batch_size, offset=offset)
        if not hostings:
            break

        for hosting in hostings:
            hosting_id = hosting["hosting_id"]
            container  = hosting["container_name"]
            try:
                result = subprocess.run(
                    ["docker", "rm", "-f", container],
                    capture_output=True,
                    timeout=10,
                )
                # docker rm -f exits 0 (removed) or 1 (doesn't exist) — both are fine
                if result.returncode not in (0, 1):
                    stderr = result.stderr.decode("utf-8", errors="replace").strip()
                    logger.warning(
                        "cleanup: docker rm exited %d for %s. Proceeding with soft-delete. Error: %s",
                        result.returncode, container, stderr,
                    )

                repo.mark_deleted(hosting_id)
                CONTAINERS_DELETED_TOTAL.inc()
                repo.log_orchestrator_event(
                    container_name=container,
                    user_id=hosting["user_id"],
                    event_type="FREE_PLAN_CLEANUP",
                    message="Recursos del plan gratuito eliminados automáticamente tras expiración.",
                )
                logger.info(
                    '{"event": "free_plan_cleanup", "hosting_id": %d, "user_id": %d, "action": "deleted_resources"}',
                    hosting_id, hosting["user_id"],
                )
                cleaned += 1
            except Exception as exc:
                logger.error(
                    "cleanup: error processing hosting_id=%d container=%s: %s",
                    hosting_id, container, exc, exc_info=True,
                )

        offset += batch_size

    return cleaned


def check_and_expire_free_hostings():
    """
    Revisa todos los hostings free activos.
    Si superaron 14 días → suspende el contenedor y marca como 'expired'.
    Si faltan 3 días → registra evento de advertencia una vez al día.
    """
    start_time = time.time()
    expired_count = 0
    warned_count = 0
    error_count = 0

    # Paso 0: recuperar hostings huérfanos de ciclos anteriores interrumpidos
    try:
        _recover_stale_expiring()
    except Exception as e:
        logger.error("Error en _recover_stale_expiring: %s", e, exc_info=True)

    hosting_repo = HostingRepository()
    now = datetime.now(timezone.utc)
    
    batch_size = 50
    offset = 0

    while True:
        hostings = hosting_repo.get_expiring_free_hostings(batch_size=batch_size, offset=offset)
        if not hostings:
            break
        
        to_expire = []

        for hosting in hostings:
            try:
                # Admin can set an explicit expiry override on the user (plan_expires_at).
                # "2099-..." = free forever — skip expiration entirely.
                user_expires_at_str = hosting.get("user_plan_expires_at")
                if user_expires_at_str and "2099" in user_expires_at_str:
                    continue  # free forever — never expire

                if user_expires_at_str:
                    exp_str = user_expires_at_str.replace("Z", "+00:00")
                    exp_dt = datetime.fromisoformat(exp_str)
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    days_remaining = (exp_dt - now).total_seconds() / 86400
                else:
                    # Default: 14-day rule from hosting created_at
                    created_str = hosting["created_at"].replace("Z", "+00:00")
                    created = datetime.fromisoformat(created_str)
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    elapsed = (now - created).total_seconds() / 86400
                    days_remaining = FREE_PLAN_DAYS - elapsed

                if days_remaining <= 0:
                    # Expirado — encolar para suspender
                    to_expire.append(hosting)
                elif days_remaining <= 3:
                    # Próximo a expirar — avisar, verificando rate limit
                    last_event = hosting_repo.get_last_event_by_type(
                        hosting["container_name"], "PLAN_EXPIRING_SOON"
                    )
                    
                    can_warn = True
                    if last_event:
                        last_created_str = last_event["created_at"].replace("Z", "+00:00")
                        last_time = datetime.fromisoformat(last_created_str)
                        if last_time.tzinfo is None:
                            last_time = last_time.replace(tzinfo=timezone.utc)
                            
                        # Verificar si pasó al menos 1 día
                        if (now - last_time).total_seconds() / 86400 < 1:
                            can_warn = False
                            
                    if can_warn:
                        hosting_repo.log_orchestrator_event(
                            container_name=hosting["container_name"],
                            user_id=hosting["user_id"],
                            event_type="PLAN_EXPIRING_SOON",
                            message=f"Tu plan gratuito vence en {max(1, int(days_remaining))} día(s). Actualizá tu plan para no perder tu sitio."
                        )
                        logger.info(f"Hosting {hosting['hosting_id']} expira en {max(1, int(days_remaining))} días — aviso enviado.")
                        warned_count += 1

            except Exception as e:
                logger.error(f"Error procesando hosting {hosting.get('hosting_id')}: {e}", exc_info=True)
                error_count += 1

        # Procesar los expirados en paralelo
        if to_expire:
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(_expire_single, h): h for h in to_expire}
                for future in as_completed(futures):
                    try:
                        hosting_res, success = future.result()
                        if success:
                            logger.info(f"Hosting {hosting_res['hosting_id']} expirado y suspendido.")
                            expired_count += 1
                        else:
                            error_count += 1
                    except Exception as e:
                        h_dict = futures[future]
                        logger.error(f"Error al detener hosting en hilo {h_dict.get('hosting_id')}: {e}", exc_info=True)
                        error_count += 1
        
        offset += batch_size

    # Phase 2: clean up previously-expired hostings (docker rm + soft-delete)
    CLEANUP_RUNS_TOTAL.inc()
    try:
        cleaned_count = _cleanup_expired_hostings()
    except Exception as e:
        logger.error("Error en _cleanup_expired_hostings: %s", e, exc_info=True)
        cleaned_count = 0

    # Métricas y observabilidad
    logger.info(
        f"Job completado en {time.time() - start_time:.2f}s — "
        f"expirados: {expired_count}, limpiados: {cleaned_count}, "
        f"advertencias: {warned_count}, errores: {error_count}"
    )
