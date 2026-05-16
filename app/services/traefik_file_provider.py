"""
Traefik File Provider management for HostingGuard tenants.

Each static tenant gets a YAML file in TRAEFIK_DYNAMIC_DIR that Traefik
hot-reloads. This is the canonical routing model — Docker labels are kept
as fallback but the File Provider is authoritative.
"""
import os
import logging

logger = logging.getLogger(__name__)

TRAEFIK_DYNAMIC_DIR = "/opt/traefik-dynamic"


def _validate_traefik_yaml(content: str, path: str = "<content>") -> None:
    """Raise ValueError if the YAML structure is invalid for Traefik file provider.

    Specifically detects the 'middlewares nested under tls' mistake that
    causes Traefik to log 'field not found, node: middlewares' and reject
    the entire file.
    """
    try:
        import yaml
        parsed = yaml.safe_load(content)
    except Exception as exc:
        raise ValueError(f"{path}: YAML parse error: {exc}") from exc

    if not isinstance(parsed, dict) or "http" not in parsed:
        raise ValueError(f"{path}: missing top-level 'http' key")

    routers = (parsed.get("http") or {}).get("routers") or {}
    for name, router in routers.items():
        if not isinstance(router, dict):
            continue
        tls = router.get("tls")
        if isinstance(tls, dict) and "middlewares" in tls:
            raise ValueError(
                f"{path}: router '{name}': 'middlewares' is nested under 'tls'. "
                "Middlewares must be at the router level, not inside tls."
            )


def create_tenant_file_provider(
    hosting_id: int,
    container_name: str,
    subdomain: str,
    *,
    use_forwardauth: bool = True,
) -> str:
    """Write (or overwrite) the Traefik File Provider YAML for a tenant.

    Uses an atomic rename so Traefik never reads a half-written file.
    Returns the absolute path to the created file.
    """
    route_file = os.path.join(TRAEFIK_DYNAMIC_DIR, f"tenant-{hosting_id}.yml")
    # middlewares at 6-space indent = router level, NOT inside tls
    mw_block = (
        "      middlewares:\n"
        "        - hg-forwardauth@file\n"
        if use_forwardauth else ""
    )
    content = (
        f"# HostingGuard — auto-generated. hosting_id={hosting_id}\n"
        f"http:\n"
        f"  routers:\n"
        f"    {container_name}:\n"
        f'      rule: "Host(`{subdomain}`)"\n'
        f"      entryPoints:\n"
        f"        - websecure\n"
        f"      service: {container_name}\n"
        f"{mw_block}"
        f"      tls:\n"
        f"        certResolver: le\n"
        f"      priority: 100\n"
        f"  services:\n"
        f"    {container_name}:\n"
        f"      loadBalancer:\n"
        f"        servers:\n"
        f'          - url: "http://{container_name}:80"\n'
    )

    _validate_traefik_yaml(content, route_file)

    os.makedirs(TRAEFIK_DYNAMIC_DIR, exist_ok=True)
    tmp = route_file + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, route_file)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise

    logger.info(
        "traefik_file_provider: route created hosting_id=%d -> %s",
        hosting_id, route_file,
    )
    return route_file


def delete_tenant_file_provider(hosting_id: int) -> bool:
    """Remove the Traefik File Provider YAML for a tenant.

    Returns True if the file was deleted, False if it did not exist.
    """
    route_file = os.path.join(TRAEFIK_DYNAMIC_DIR, f"tenant-{hosting_id}.yml")
    try:
        os.remove(route_file)
        logger.info("traefik_file_provider: removed route for hosting_id=%d", hosting_id)
        return True
    except FileNotFoundError:
        return False
    except Exception as exc:
        logger.warning(
            "traefik_file_provider: failed to remove %s: %s", route_file, exc
        )
        return False
