from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.api.security import verify_token
from app.api.rate_limit import limiter
from app.infra.audit.domain_repository import DomainRepository
from app.infra.audit.hosting_repository import HostingRepository
from app.services.domain_checker import verify_dns, dns_instructions, write_traefik_config, remove_traefik_config
from app.services.activity_service import log_event as _log_activity
from fastapi import Request

router = APIRouter()

_domain_repo  = DomainRepository()
_hosting_repo = HostingRepository()

DOMAIN = "hostingguard.lat"


class AddDomainRequest(BaseModel):
    domain: str
    domain_type: Optional[str] = "cname"


def _get_hosting_or_404(hosting_id: int, user_id: int) -> dict:
    hosting = _hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")
    return hosting


@router.get("/hostings/{hosting_id}/domains")
def list_domains(hosting_id: int, user: dict = Depends(verify_token)):
    user_id = user["user_id"]
    _get_hosting_or_404(hosting_id, user_id)
    domains = _domain_repo.get_domains(hosting_id, user_id)
    return {"domains": domains}


@router.post("/hostings/{hosting_id}/domains")
@limiter.limit("10/hour")
def add_domain(
    hosting_id: int,
    body: AddDomainRequest,
    request: Request,
    user: dict = Depends(verify_token),
):
    user_id = user["user_id"]
    hosting = _get_hosting_or_404(hosting_id, user_id)

    raw = body.domain.lower().strip()
    if not raw or "." not in raw:
        raise HTTPException(status_code=400, detail="Dominio inválido")
    if raw.endswith(f".{DOMAIN}"):
        raise HTTPException(status_code=400, detail="No podés usar subdominios de hostingguard.lat")

    existing = _domain_repo.get_by_domain_name(raw)
    if existing:
        raise HTTPException(status_code=409, detail="Este dominio ya está registrado en otra cuenta")

    domain_id = _domain_repo.add_domain(user_id, hosting_id, raw, body.domain_type or "cname")
    subdomain  = hosting.get("subdomain", "")

    try:
        _log_activity(
            user_id=user_id, hosting_id=hosting_id,
            event_type="custom_domain_added",
            category="domain", severity="info",
            title=f"Dominio {raw} añadido",
            message=f"Pendiente verificación DNS. Apuntar hacia {subdomain}.",
        )
    except Exception:
        pass

    instructions = dns_instructions(raw, subdomain)
    return {
        "domain_id":    domain_id,
        "domain":       raw,
        "dns_status":   "pending",
        "instructions": instructions,
    }


@router.delete("/hostings/{hosting_id}/domains/{domain_id}")
def delete_domain(hosting_id: int, domain_id: int, user: dict = Depends(verify_token)):
    user_id = user["user_id"]
    _get_hosting_or_404(hosting_id, user_id)

    domain_row = _domain_repo.get_domain(domain_id, user_id)
    if not domain_row or domain_row["hosting_id"] != hosting_id:
        raise HTTPException(status_code=404, detail="Dominio no encontrado")

    domain_name = domain_row["domain"]
    deleted = _domain_repo.delete_domain(domain_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Dominio no encontrado")

    try:
        remove_traefik_config(domain_id)
    except Exception:
        pass

    try:
        _log_activity(
            user_id=user_id, hosting_id=hosting_id,
            event_type="custom_domain_deleted",
            category="domain", severity="info",
            title=f"Dominio {domain_name} eliminado",
            message="Configuración de Traefik removida.",
        )
    except Exception:
        pass

    return {"status": "deleted"}


@router.post("/hostings/{hosting_id}/domains/{domain_id}/verify")
@limiter.limit("20/hour")
def verify_domain(
    hosting_id: int,
    domain_id: int,
    request: Request,
    user: dict = Depends(verify_token),
):
    user_id = user["user_id"]
    hosting = _get_hosting_or_404(hosting_id, user_id)

    domain_row = _domain_repo.get_domain(domain_id, user_id)
    if not domain_row or domain_row["hosting_id"] != hosting_id:
        raise HTTPException(status_code=404, detail="Dominio no encontrado")

    domain    = domain_row["domain"]
    subdomain = hosting.get("subdomain", "")
    result    = verify_dns(domain, subdomain)

    if result["ok"]:
        _domain_repo.update_status(
            domain_id,
            dns_status="active",
            ssl_status="pending",
            error_message=None,
            verified=True,
        )
        git_config     = hosting.get("git_config") or {}
        container_name = hosting["container_name"]
        port           = int(git_config.get("port", 80) if isinstance(git_config, dict) else 80)

        try:
            write_traefik_config(domain_id, domain, container_name, port=port)
            _domain_repo.update_status(domain_id, ssl_status="active")
        except Exception as exc:
            _domain_repo.update_status(domain_id, ssl_status="failed",
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

        return {"ok": True, "dns_status": "active", "method": result["method"]}
    else:
        _domain_repo.update_status(domain_id, dns_status="pending",
                                    error_message=result["error"])
        subdomain_fqdn = subdomain if "." in subdomain else f"{subdomain}.{DOMAIN}"
        instructions   = dns_instructions(domain, subdomain_fqdn)
        return {
            "ok":           False,
            "dns_status":   "pending",
            "error":        result["error"],
            "resolved_ip":  result.get("resolved_ip"),
            "instructions": instructions,
        }


@router.post("/hostings/{hosting_id}/domains/{domain_id}/set-primary")
def set_primary_domain(hosting_id: int, domain_id: int, user: dict = Depends(verify_token)):
    user_id = user["user_id"]
    _get_hosting_or_404(hosting_id, user_id)

    domain_row = _domain_repo.get_domain(domain_id, user_id)
    if not domain_row or domain_row["hosting_id"] != hosting_id:
        raise HTTPException(status_code=404, detail="Dominio no encontrado")

    if domain_row.get("dns_status") != "active":
        raise HTTPException(status_code=400, detail="Solo se puede marcar como primario un dominio verificado")

    _domain_repo.set_primary(domain_id, hosting_id)
    return {"status": "ok", "primary_domain": domain_row["domain"]}
