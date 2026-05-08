"""
DNS verification and Traefik dynamic config management for custom domains.

DNS verification strategy:
  1. Resolve the custom domain IP via socket.gethostbyname().
  2. Resolve the hosting's subdomain (.hostingguard.lat) to the same IP.
  3. If both IPs match → CNAME or A record is pointing correctly.
  4. If SERVER_IP env var is set, also accept a direct A record match.

Traefik dynamic config:
  Writes YAML files to TRAEFIK_DYNAMIC_DIR (default: /opt/traefik-dynamic/).
  Traefik must be configured with --providers.file.directory pointing there.
  One file per verified domain: domain-{domain_id}.yml
"""
import ipaddress
import os
import logging
import socket
import yaml

logger = logging.getLogger(__name__)

TRAEFIK_DYNAMIC_DIR = os.getenv("TRAEFIK_DYNAMIC_DIR", "/opt/traefik-dynamic")
SERVER_IP = os.getenv("SERVER_IP", "")
DOMAIN = "hostingguard.lat"

_PRIVATE_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _PRIVATE_NETS)
    except ValueError:
        return False


# ── DNS check ────────────────────────────────────────────────────────────────

def _resolve(host: str) -> str:
    try:
        return socket.gethostbyname(host)
    except socket.gaierror:
        return ""


def verify_dns(domain: str, subdomain: str) -> dict:
    """
    Returns:
      {"ok": True/False, "resolved_ip": str, "method": str, "error": str|None}
    """
    domain_ip = _resolve(domain)
    if not domain_ip:
        return {"ok": False, "resolved_ip": None, "method": None,
                "error": f"No se pudo resolver {domain}. Verificá que el DNS esté configurado."}

    if _is_private(domain_ip):
        return {"ok": False, "resolved_ip": domain_ip, "method": None,
                "error": f"El dominio resuelve a una IP privada o reservada ({domain_ip}). No se puede activar."}

    # Method 1: direct A record matches SERVER_IP
    if SERVER_IP and domain_ip == SERVER_IP:
        return {"ok": True, "resolved_ip": domain_ip, "method": "a_record", "error": None}

    # Method 2: resolves to the same IP as the hosting subdomain (CNAME chain)
    subdomain_ip = _resolve(subdomain)
    if subdomain_ip and domain_ip == subdomain_ip:
        return {"ok": True, "resolved_ip": domain_ip, "method": "cname", "error": None}

    expected = SERVER_IP or subdomain_ip or f"IP de {subdomain}"
    return {
        "ok": False,
        "resolved_ip": domain_ip,
        "method": None,
        "error": (
            f"El dominio resuelve a {domain_ip} pero se esperaba {expected}. "
            "Revisá el registro CNAME o A en tu proveedor de DNS."
        ),
    }


# ── DNS instructions ──────────────────────────────────────────────────────────

def dns_instructions(domain: str, subdomain: str) -> dict:
    """Return human-readable DNS configuration instructions."""
    is_apex = domain.count(".") == 1 or domain.startswith("@")
    www = domain.startswith("www.")
    bare = domain.removeprefix("www.") if www else domain

    if www or not is_apex:
        return {
            "type": "CNAME",
            "name": domain,
            "value": f"{subdomain}.",
            "note": f"Apuntá el CNAME de {domain} → {subdomain}",
        }
    # apex domain
    instructions = {
        "type": "A",
        "name": bare,
        "value": SERVER_IP or "IP del servidor",
        "note": (
            f"Para apex ({bare}), creá un registro A hacia {SERVER_IP or 'la IP del servidor'}. "
            "Si usás Cloudflare, podés usar un registro CNAME con proxy activado."
        ),
    }
    return instructions


# ── Traefik dynamic config ────────────────────────────────────────────────────

def _config_path(domain_id: int) -> str:
    return os.path.join(TRAEFIK_DYNAMIC_DIR, f"domain-{domain_id}.yml")


def write_traefik_config(domain_id: int, domain: str, container_name: str,
                         port: int = 80, redirect_www: bool = True) -> None:
    """
    Write a Traefik file-provider YAML that routes `domain` (and optionally
    `www.domain`) to the container.

    Requires Traefik to be configured with:
      --providers.file.directory=/opt/traefik-dynamic
      --providers.file.watch=true
    """
    os.makedirs(TRAEFIK_DYNAMIC_DIR, exist_ok=True)

    router_name  = f"custom-{domain_id}"
    service_name = f"svc-{container_name}"
    bare_domain  = domain.removeprefix("www.")
    hosts        = [bare_domain]
    if redirect_www and not domain.startswith("www."):
        hosts.append(f"www.{bare_domain}")

    host_rule = " || ".join(f"Host(`{h}`)" for h in hosts)

    config = {
        "http": {
            "routers": {
                router_name: {
                    "rule": host_rule,
                    "service": service_name,
                    "entryPoints": ["websecure"],
                    "tls": {"certResolver": "le"},
                },
                f"{router_name}-http": {
                    "rule": host_rule,
                    "service": service_name,
                    "entryPoints": ["web"],
                    "middlewares": ["redirect-to-https"],
                },
            },
            "services": {
                service_name: {
                    "loadBalancer": {
                        "servers": [{"url": f"http://{container_name}:{port}"}]
                    }
                }
            },
        }
    }

    path = _config_path(domain_id)
    try:
        with open(path, "w") as f:
            yaml.safe_dump(config, f, default_flow_style=False)
        logger.info("domain_checker: wrote Traefik config %s for %s → %s", path, domain, container_name)
    except Exception as exc:
        logger.error("domain_checker: failed to write Traefik config %s: %s", path, exc)
        raise


def remove_traefik_config(domain_id: int) -> None:
    path = _config_path(domain_id)
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info("domain_checker: removed Traefik config %s", path)
    except Exception as exc:
        logger.warning("domain_checker: failed to remove Traefik config %s: %s", path, exc)


# ── Periodic check job ────────────────────────────────────────────────────────

def check_pending_domains() -> None:
    """Scheduled job: attempt DNS verification for all pending/failed domains."""
    from app.infra.audit.domain_repository import DomainRepository
    from app.services.activity_service import log_event as _log_activity

    domain_repo = DomainRepository()
    rows = domain_repo.get_pending_domains()

    for row in rows:
        domain     = row["domain"]
        subdomain  = row["subdomain"]
        domain_id  = row["domain_id"]
        hosting_id = row["hosting_id"]
        user_id    = row["user_id"]

        result = verify_dns(domain, subdomain)
        if result["ok"]:
            domain_repo.update_status(
                domain_id,
                dns_status="active",
                ssl_status="pending",
                error_message=None,
                verified=True,
            )
            try:
                write_traefik_config(
                    domain_id, domain, row["container_name"],
                    port=int((row.get("git_config") or {}).get("port", 80) if row.get("git_config") else 80),
                )
                domain_repo.update_status(domain_id, ssl_status="active")
            except Exception as exc:
                logger.warning("domain_checker: Traefik write failed for %s: %s", domain, exc)
                domain_repo.update_status(domain_id, ssl_status="failed",
                                           error_message=f"Traefik error: {exc}")

            try:
                _log_activity(
                    user_id=user_id, hosting_id=hosting_id,
                    event_type="custom_domain_verified",
                    category="domain", severity="info",
                    title=f"Dominio {domain} verificado",
                    message=f"DNS verificado via {result['method']}. SSL en proceso.",
                )
            except Exception:
                pass
        else:
            domain_repo.update_status(domain_id, dns_status="pending",
                                        error_message=result["error"])
            logger.debug("domain_checker: %s still pending — %s", domain, result["error"])
