"""SSL certificate expiry checker — runs as a scheduled job."""
import logging
import socket
import ssl
from datetime import datetime, timezone

from app.infra.audit.hosting_repository import HostingRepository
from app.services.notification_service import notify

logger = logging.getLogger(__name__)

_WARN_DAYS = 14    # notify when < 14 days remaining
_CRIT_DAYS = 3     # critical when < 3 days

_hosting_repo = HostingRepository()


def _check_ssl(hostname: str) -> dict:
    """Returns dict with keys: valid, days_remaining, expires_dt. None on connection error."""
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                expire_str = cert.get("notAfter", "")
                if not expire_str:
                    return {"valid": False, "days_remaining": -1, "expires_dt": None}
                expire_dt = datetime.strptime(expire_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                days = (expire_dt - datetime.now(timezone.utc)).days
                return {"valid": True, "days_remaining": days, "expires_dt": expire_dt}
    except ssl.SSLCertVerificationError as e:
        return {"valid": False, "days_remaining": -1, "expires_dt": None, "error": str(e)}
    except Exception:
        return None  # can't reach host, skip silently


def check_ssl_for_all_hostings() -> None:
    """Scheduled job — checks SSL certs for all active WP hostings."""
    from app.infra.db import reset_pg_connection
    reset_pg_connection()

    hostings = _hosting_repo.get_all_hostings()
    active = [h for h in hostings if h.get("status") == "active" and "_wp_" in h.get("container_name", "")]
    logger.info("ssl_checker: checking %d WP sites", len(active))

    for hosting in active:
        subdomain = hosting.get("subdomain", "")
        if not subdomain:
            continue
        try:
            result = _check_ssl(subdomain)
            if result is None:
                continue  # unreachable, skip

            user_id = hosting["user_id"]
            site_name = hosting.get("name") or subdomain
            days = result["days_remaining"]

            if not result["valid"]:
                notify(user_id, f"SSL inválido: {site_name}",
                       f"El certificado SSL de '{site_name}' no es válido o está vencido. "
                       "El sitio puede mostrar advertencias de seguridad a los visitantes.",
                       category="ssl", severity="critical", channel="both",
                       action_url="/dashboard")
            elif days < _CRIT_DAYS:
                notify(user_id, f"SSL vence en {days} día{'s' if days != 1 else ''}: {site_name}",
                       f"El certificado SSL de '{site_name}' vence en {days} día{'s' if days != 1 else ''}. "
                       "Si no se renueva automáticamente, el sitio mostrará errores de seguridad.",
                       category="ssl", severity="critical", channel="both",
                       action_url="/dashboard")
            elif days < _WARN_DAYS:
                notify(user_id, f"SSL próximo a vencer: {site_name}",
                       f"El certificado SSL de '{site_name}' vence en {days} días "
                       f"({result['expires_dt'].strftime('%d/%m/%Y') if result['expires_dt'] else ''}). "
                       "Verificá que la renovación automática esté funcionando.",
                       category="ssl", severity="warning", channel="both",
                       action_url="/dashboard")
        except Exception as exc:
            logger.error("ssl_checker: error for %s — %s", subdomain, exc)

    logger.info("ssl_checker: done")
