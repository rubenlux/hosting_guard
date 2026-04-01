# app/services/expiration_job.py
import logging
import subprocess
from datetime import datetime
from app.infra.audit.hosting_repository import HostingRepository

logger = logging.getLogger(__name__)
hosting_repo = HostingRepository()

FREE_PLAN_DAYS = 14


def check_and_expire_free_hostings():
    """
    Revisa todos los hostings free activos.
    Si superaron 14 días → suspende el contenedor y marca como 'expired'.
    Si faltan 3 días → registra evento de advertencia.
    """
    hostings = hosting_repo.get_expiring_free_hostings()
    now = datetime.utcnow()

    for hosting in hostings:
        try:
            created = datetime.fromisoformat(hosting["created_at"])
            elapsed_days = (now - created).days
            days_remaining = FREE_PLAN_DAYS - elapsed_days

            if days_remaining <= 0:
                # Expirado — suspender contenedor
                container = hosting["container_name"]
                subprocess.run(
                    ["docker", "stop", container],
                    capture_output=True, timeout=10
                )
                hosting_repo.update_hosting_status(hosting["hosting_id"], "expired")
                hosting_repo.log_orchestrator_event(
                    container_name=container,
                    user_id=hosting["user_id"],
                    event_type="PLAN_EXPIRED",
                    message="Tu plan gratuito de 14 días ha expirado. Actualizá tu plan para reactivar el sitio."
                )
                logger.info(f"Hosting {hosting['hosting_id']} expirado y suspendido.")

            elif days_remaining <= 3:
                # Próximo a expirar — avisar
                hosting_repo.log_orchestrator_event(
                    container_name=hosting["container_name"],
                    user_id=hosting["user_id"],
                    event_type="PLAN_EXPIRING_SOON",
                    message=f"Tu plan gratuito vence en {days_remaining} día(s). Actualizá tu plan para no perder tu sitio."
                )
                logger.info(f"Hosting {hosting['hosting_id']} expira en {days_remaining} días — aviso enviado.")

        except Exception as e:
            logger.error(f"Error procesando hosting {hosting.get('hosting_id')}: {e}")
