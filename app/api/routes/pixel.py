import hashlib
import json
import re
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import Response

_SITE_ID_RE = re.compile(r'^[a-f0-9\-]{8,36}$')
from pydantic import BaseModel
from app.api.security import verify_token, require_role
from app.infra.audit.pixel_repository import PixelRepository

router = APIRouter()
pixel_repo = PixelRepository()


def _parse_user_agent(ua: str) -> dict:
    if not ua:
        return {"device": "unknown", "browser": "unknown", "os": "unknown"}
    ua_lower = ua.lower()
    device = "desktop"
    if any(x in ua_lower for x in ["mobile", "android", "iphone"]):
        device = "mobile"
    elif "tablet" in ua_lower or "ipad" in ua_lower:
        device = "tablet"
    browser = "other"
    for b in ["chrome", "firefox", "safari", "edge", "opera"]:
        if b in ua_lower:
            browser = b
            break
    os_name = "other"
    for o, k in [("windows", "windows"), ("macos", "mac os"), ("linux", "linux"),
                  ("android", "android"), ("ios", "iphone")]:
        if k in ua_lower:
            os_name = o
            break
    return {"device": device, "browser": browser, "os": os_name}


# ── Pixel JS ──────────────────────────────────────────────────────────────
@router.get("/pixel.js")
async def pixel_script(id: str, request: Request):
    """Sirve el script de tracking."""
    # Validar id antes de interpolarlo en JS: solo UUIDs / hex con guiones
    if not _SITE_ID_RE.match(id):
        raise HTTPException(status_code=400, detail="Invalid site id")
    # json.dumps produce un string JS literal correctamente escapado (sin riesgo de injection)
    safe_id = json.dumps(id)
    script = f"""
(function() {{
  var HG_SITE_ID = {safe_id};
  var HG_API = 'https://api.hostingguard.lat';
  var session = sessionStorage.getItem('hg_sid') || Math.random().toString(36).substr(2);
  sessionStorage.setItem('hg_sid', session);

  function track(event, props) {{
    var data = {{
      site_id: HG_SITE_ID,
      event_type: event,
      url: window.location.href,
      referrer: document.referrer,
      user_agent: navigator.userAgent,
      session_id: session,
      properties: props || {{}}
    }};
    fetch(HG_API + '/pixel/event', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(data),
      keepalive: true
    }}).catch(function() {{}});
  }}

  track('page_view');

  document.addEventListener('click', function(e) {{
    var el = e.target.closest('a, button, [data-track]');
    if (el) track('click', {{ element: el.tagName, text: el.innerText?.substr(0,150) }});
  }});

  window.addEventListener('beforeunload', function() {{
    track('page_exit', {{ time_on_page: Math.round(performance.now() / 1000) }});
  }});

  window.hgTrack = track;
}})();
"""

    return Response(
        content=script.strip(),
        media_type="application/javascript",
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"}
    )


# ── Recibir eventos ────────────────────────────────────────────────────────
class PixelEventRequest(BaseModel):
    site_id: str
    event_type: str
    url: Optional[str] = None
    referrer: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    properties: Optional[dict] = {}


@router.post("/pixel/event")
async def receive_event(data: PixelEventRequest, request: Request):
    site = pixel_repo.get_site(data.site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    ip = request.client.host if request.client else None
    ua_info = _parse_user_agent(data.user_agent or "")

    pixel_repo.save_event(
        site_id=data.site_id,
        user_id=site["user_id"],
        event_type=data.event_type,
        url=data.url,
        referrer=data.referrer,
        user_agent=data.user_agent,
        ip=ip,
        device=ua_info["device"],
        browser=ua_info["browser"],
        os=ua_info["os"],
        properties=data.properties,
        session_id=data.session_id,
    )
    return Response(status_code=204)


# ── Gestión de sitios (requiere auth) ─────────────────────────────────────
class CreateSiteRequest(BaseModel):
    name: str
    domain: Optional[str] = None


@router.post("/pixel/sites")
async def create_site(data: CreateSiteRequest, user: dict = Depends(verify_token)):
    site_id = pixel_repo.create_site(
        user_id=user["user_id"],
        name=data.name,
        domain=data.domain
    )
    return {
        "site_id": site_id,
        "name": data.name,
        "snippet": f'<script src="https://api.hostingguard.lat/pixel.js?id={site_id}"></script>'
    }


@router.get("/pixel/sites")
async def list_sites(user: dict = Depends(verify_token)):
    return pixel_repo.get_user_sites(user["user_id"])


@router.get("/pixel/sites/{site_id}/stats")
async def get_stats(site_id: str, user: dict = Depends(verify_token)):
    site = pixel_repo.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if site["user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return pixel_repo.get_stats(site_id)


@router.delete("/pixel/sites/{site_id}")
async def delete_site(site_id: str, user: dict = Depends(verify_token)):
    site = pixel_repo.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if site["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    pixel_repo.delete_site(site_id, user["user_id"])
    return {"status": "deleted"}


@router.get("/pixel/admin/stats")
async def admin_stats(user: dict = Depends(require_role("admin"))):
    return pixel_repo.get_all_stats_admin()
