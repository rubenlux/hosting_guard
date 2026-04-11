import asyncio
import hashlib
import json
import re
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Request, HTTPException, Depends
from fastapi.responses import Response

_SITE_ID_RE = re.compile(r'^[a-f0-9\-]{8,36}$')
# event_type: solo lowercase letras, números y guión bajo, máx 50 chars
# Permite todos los eventos actuales (page_view, click, page_exit) y los nuevos
_EVENT_TYPE_RE = re.compile(r'^[a-z][a-z0-9_]{0,49}$')

from pydantic import BaseModel, field_validator
from cachetools import TTLCache
import geoip2.database
import os
from app.api.rate_limit import limiter
from app.api.security import verify_token, require_role
from app.infra.audit.pixel_repository import PixelRepository

router = APIRouter()
pixel_repo = PixelRepository()

# ── GeoIP helpers ─────────────────────────────────────────────────────────────

# Local MaxMind GeoLite2 reader — file must exist at data/GeoLite2-City.mmdb.
# Falls back to None gracefully; geo fields will be left as NULL if unavailable.
_geoip_reader = None
try:
    _geoip_reader = geoip2.database.Reader("data/GeoLite2-City.mmdb")
except Exception:
    pass

# In-memory cache: ip → {"country": str, "region": str, "city": str}
# Bounded to 50k entries, TTL 24h — prevents unbounded growth.
_ip_cache: TTLCache = TTLCache(maxsize=50_000, ttl=86400)

_PRIVATE_PREFIXES = ("127.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
                     "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                     "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                     "172.30.", "172.31.", "192.168.", "::1", "fc", "fd")


def _get_real_ip(request: Request) -> Optional[str]:
    """Extract the real client IP, skipping proxy/load-balancer addresses."""
    for header in ("x-real-ip", "cf-connecting-ip", "x-forwarded-for"):
        val = request.headers.get(header)
        if val:
            # x-forwarded-for may contain a comma-separated chain; first is client
            return val.split(",")[0].strip()
    return request.client.host if request.client else None


def _resolve_geo(ip: str) -> dict:
    """
    Resolve country/region/city from local MaxMind GeoLite2 database.
    Results are cached in _ip_cache (TTL 24h, max 50k entries) so each
    unique IP is only looked up once. No HTTP requests, no external dependencies.
    """
    if ip in _ip_cache:
        return _ip_cache[ip]

    if not _geoip_reader:
        return {"country": None, "region": None, "city": None}

    try:
        response = _geoip_reader.city(ip)
        result = {
            "country": response.country.name or None,
            "region":  response.subdivisions.most_specific.name or None,
            "city":    response.city.name or None,
        }
    except Exception:
        result = {"country": None, "region": None, "city": None}

    if result.get("country"):
        _ip_cache[ip] = result
    return result


async def _enrich_geo(event_id: str, ip: Optional[str]) -> None:
    """
    Background task: resolve geo for `ip` and update the DB record.
    """
    if not ip:
        return
    if any(ip.startswith(p) for p in _PRIVATE_PREFIXES):
        return

    geo = _resolve_geo(ip)
    if geo.get("country"):
        pixel_repo.update_event_geo(
            event_id,
            geo["country"],
            geo.get("region"),
            geo.get("city"),
        )


def _parse_user_agent(ua: str) -> dict:
    if not ua:
        return {"device": "unknown", "browser": "unknown", "os": "unknown"}
    ua_lower = ua.lower()

    device = "desktop"
    if any(x in ua_lower for x in ["mobile", "android", "iphone"]):
        device = "mobile"
    elif "tablet" in ua_lower or "ipad" in ua_lower:
        device = "tablet"

    # Edge debe ir antes de Chrome porque Edge UA contiene "chrome"
    browser = "other"
    for b, k in [("edge", "edg"), ("chrome", "chrome"), ("firefox", "firefox"),
                  ("safari", "safari"), ("opera", "opr")]:
        if k in ua_lower:
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
    if not _SITE_ID_RE.match(id):
        raise HTTPException(status_code=400, detail="Invalid site id")

    safe_id = json.dumps(id)
    script = fr"""(function(){{
  // Guard: evita que el script se inicialice más de una vez por sesión de tab.
  // En SPAs con SSR o lazy-loading, el <script> puede ejecutarse múltiples veces.
  if(window.__hg_init)return;
  window.__hg_init=1;

  var S={safe_id},A='https://api.hostingguard.lat',T=Date.now();

  // visitor_id: persiste entre sesiones (localStorage)
  var vid=localStorage.getItem('hg_vid');
  if(!vid){{vid=Date.now().toString(36)+Math.random().toString(36).substr(2)+Math.random().toString(36).substr(2);localStorage.setItem('hg_vid',vid);}}

  // session_id: por tab/sesión (sessionStorage)
  var sid=sessionStorage.getItem('hg_sid');
  if(!sid){{sid=Math.random().toString(36).substr(2);sessionStorage.setItem('hg_sid',sid);}}

  // ── Client hints (screen, language) ──────────────────────────────────────
  var _dv=window.innerWidth<=768?'mobile':window.innerWidth<=1024?'tablet':'desktop';
  var _sw=(window.screen&&window.screen.width)||0;
  var _lang=(navigator.language||'').split('-')[0].substr(0,5);

  // ── Transport ─────────────────────────────────────────────────────────────

  function _beacon(ev,props){{
    try{{
      var d=JSON.stringify({{site_id:S,event_type:ev,url:window.location.href,
        referrer:document.referrer,user_agent:navigator.userAgent,
        session_id:sid,visitor_id:vid,properties:Object.assign({{}},{{device:_dv,sw:_sw,lang:_lang}},props||{{}})}});
      if(navigator.sendBeacon)navigator.sendBeacon(A+'/pixel/event',new Blob([d],{{type:'application/json'}}));
    }}catch(e){{}}
  }}

  function send(ev,props){{
    try{{
      fetch(A+'/pixel/event',{{
        method:'POST',
        headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{site_id:S,event_type:ev,url:window.location.href,
          referrer:document.referrer,user_agent:navigator.userAgent,
          session_id:sid,visitor_id:vid,properties:Object.assign({{}},{{device:_dv,sw:_sw,lang:_lang}},props||{{}})}}),
        keepalive:true
      }}).catch(function(err){{
        if(ev!=='fetch_error')_beacon('fetch_error',{{failed_event:ev,error:(err&&err.name)||'NetworkError'}});
      }});
    }}catch(e){{}}
  }}

  // ── pixel_init: una sola vez por sesión de tab ────────────────────────────
  _beacon('pixel_init',{{sv:3}});

  // ── UTM: captura de URL o recupera de sessionStorage ─────────────────────
  function _utms(){{
    try{{
      var p=new URLSearchParams(window.location.search),u={{}};
      ['utm_source','utm_medium','utm_campaign'].forEach(function(k){{var v=p.get(k);if(v)u[k]=v;}});
      if(Object.keys(u).length){{sessionStorage.setItem('hg_utm',JSON.stringify(u));return u;}}
      var stored=sessionStorage.getItem('hg_utm');
      return stored?JSON.parse(stored):null;
    }}catch(e){{return null;}}
  }}

  // ── page_view helper ──────────────────────────────────────────────────────
  // Registra una vista de página con URL actual, referrer y UTMs.
  // Se llama tanto en carga inicial como en cada cambio de ruta SPA.
  var _lastUrl=window.location.href;

  function _trackPageView(ref){{
    var pvp={{}},utm=_utms();
    if(utm)pvp.utm=utm;
    if(ref)pvp.referrer_override=ref;
    send('page_view',pvp);
  }}

  _trackPageView();

  // ── SPA route tracking ────────────────────────────────────────────────────
  // Estrategia de triple cobertura:
  //   1. Patch de pushState/replaceState (React Router, Vue Router, Nuxt…)
  //   2. popstate (botón atrás/adelante)
  //   3. Polling 500ms como fallback universal (Next.js App Router, Remix,
  //      frameworks que capturan pushState antes de que cargue este script)
  // _onNav centraliza todos los efectos secundarios de un cambio de ruta.

  function _onNav(prevUrl){{
    _resetScrollMarks();
    setTimeout(function(){{_trackPageView(prevUrl);}},0);
  }}

  // Patch idempotente: no envuelve dos veces si el script se ejecuta más de una vez
  ['pushState','replaceState'].forEach(function(method){{
    var orig=history[method];
    if(orig._hg)return;                // ya parcheado, salir
    var patched=function(){{
      var prev=location.href;
      orig.apply(this,arguments);
      var next=location.href;
      if(next!==prev){{_lastUrl=next;_onNav(prev);}}
    }};
    patched._hg=1;                     // marca para idempotencia
    history[method]=patched;
  }});

  // popstate: botón atrás/adelante del browser
  window.addEventListener('popstate',function(){{
    var next=location.href;
    if(next!==_lastUrl){{
      var prev=_lastUrl;
      _lastUrl=next;
      _onNav(prev);
    }}
  }});

  // hashchange: apps legacy que usan hash routing (#/pricing)
  window.addEventListener('hashchange',function(e){{
    _lastUrl=location.href;
    _onNav(e.oldURL||_lastUrl);
  }});

  // Fallback polling: captura cambios de URL que escapan a todos los métodos
  // anteriores (Next.js App Router, Remix, routers custom, etc.)
  // Usa setInterval sin clearInterval intencional — vive toda la sesión.
  setInterval(function(){{
    var cur=location.href;
    if(cur!==_lastUrl){{
      var prev=_lastUrl;
      _lastUrl=cur;
      _onNav(prev);
    }}
  }},500);

  // ── Performance: carga real (solo en navegación inicial) ──────────────────
  window.addEventListener('load',function(){{
    setTimeout(function(){{
      var t=window.performance&&window.performance.timing;
      if(t&&t.loadEventEnd>0){{
        send('performance',{{
          load_time:t.loadEventEnd-t.navigationStart,
          dom_ready:t.domContentLoadedEventEnd-t.navigationStart,
          ttfb:t.responseStart-t.navigationStart
        }});
      }}
    }},0);
  }});

  // ── Click tracking ────────────────────────────────────────────────────────
  // Captura: links, botones, elementos con data-track.
  // href: para saber adónde iba el usuario (útil en funnel analysis).
  document.addEventListener('click',function(e){{
    var el=e.target&&e.target.closest?e.target.closest('a,button,[data-track]'):null;
    if(!el)return;
    var props={{element:el.tagName,text:(el.innerText||'').substr(0,100)}};
    if(el.tagName==='A'&&el.href)props.href=el.href.replace(/^https?:\/\/[^/]+/,'').substr(0,200);
    send('click',props);
  }});

  // ── Scroll depth: 25%, 50%, 75%, 90% ─────────────────────────────────────
  // Se resetea en cada cambio de ruta (vía _onNav) para medir cada página.
  var marks={{}};
  function _resetScrollMarks(){{marks={{}};}}
  document.addEventListener('scroll',function(){{
    var d=document.documentElement,pct=Math.round((d.scrollTop+window.innerHeight)/d.scrollHeight*100);
    [25,50,75,90].forEach(function(m){{if(pct>=m&&!marks[m]){{marks[m]=1;send('scroll_depth',{{depth:m}});}}}});
  }},{{passive:true}});

  // ── JS error capture ──────────────────────────────────────────────────────
  window.addEventListener('error',function(e){{
    send('js_error',{{message:(e.message||'').substr(0,200),source:(e.filename||'').substr(0,200),line:e.lineno||0}});
  }});

  // ── page_exit: visibilitychange + pagehide ────────────────────────────────
  // En SPAs el exit real es cuando el tab se oculta o cierra, no en cada ruta.
  var done=0;
  function exit(){{if(!done){{done=1;send('page_exit',{{time_on_page:Math.round((Date.now()-T)/1000)}});}}}}
  document.addEventListener('visibilitychange',function(){{if(document.visibilityState==='hidden')exit();}});
  window.addEventListener('pagehide',exit);

  // ── Heartbeat: cada 60s si el tab está activo ─────────────────────────────
  setInterval(function(){{if(!document.hidden)send('heartbeat',{{time_on_page:Math.round((Date.now()-T)/1000)}});}},60000);

  // ── API pública para tracking manual ─────────────────────────────────────
  // Uso: hgTrack('purchase', {{ value: 99, plan: 'pro' }})
  window.hgTrack=send;
}})();"""

    return Response(
        content=script,
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
    visitor_id: Optional[str] = None
    properties: Optional[dict] = {}

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if not _EVENT_TYPE_RE.match(v):
            raise ValueError("event_type inválido — solo lowercase, números y guión bajo, máx 50 chars")
        return v

    @field_validator("site_id")
    @classmethod
    def validate_site_id(cls, v: str) -> str:
        if not _SITE_ID_RE.match(v):
            raise ValueError("site_id inválido")
        return v

    @field_validator("properties")
    @classmethod
    def validate_properties(cls, v: dict) -> dict:
        if not v:
            return {}
        # Max 30 keys — silently drop excess
        keys = list(v.keys())[:30]
        result = {}
        for k in keys:
            val = v[k]
            # Truncate string values to 500 chars
            if isinstance(val, str):
                result[k] = val[:500]
            else:
                result[k] = val
        return result


@router.post("/pixel/event")
@limiter.limit("120/minute")
async def receive_event(data: PixelEventRequest, request: Request, background_tasks: BackgroundTasks):
    site = pixel_repo.get_site(data.site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    ip = _get_real_ip(request)
    ua_info = _parse_user_agent(data.user_agent or "")

    # Use client-side device hint (from screen width) as a fallback when UA parsing
    # returns "unknown" — e.g. minimal/custom user agents or bots.
    device = ua_info["device"]
    if device == "unknown" and isinstance(data.properties, dict):
        hint = data.properties.get("device")
        if hint in ("mobile", "desktop", "tablet"):
            device = hint

    # Country resolution:
    #   cache hit  → resolve synchronously (zero latency, IP already known)
    #   cache miss → save with NULL now, enrich via BackgroundTask after response
    country = None
    schedule_geo = False
    if ip and not any(ip.startswith(p) for p in _PRIVATE_PREFIXES):
        if ip in _ip_cache:
            country = _ip_cache[ip].get("country")
        else:
            schedule_geo = True

    event_id = pixel_repo.save_event(
        site_id=data.site_id,
        user_id=site["user_id"],
        event_type=data.event_type,
        url=data.url,
        referrer=data.referrer,
        user_agent=data.user_agent,
        ip=ip,
        country=country,
        device=device,
        browser=ua_info["browser"],
        os=ua_info["os"],
        properties=data.properties,
        session_id=data.session_id,
        visitor_id=data.visitor_id,
    )

    if schedule_geo:
        background_tasks.add_task(_enrich_geo, event_id, ip)

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
async def get_stats(site_id: str, days: int = 30, user: dict = Depends(verify_token)):
    site = pixel_repo.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if site["user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return pixel_repo.get_stats(site_id, days=days)


@router.get("/pixel/sites/{site_id}/realtime")
async def get_realtime(site_id: str, user: dict = Depends(verify_token)):
    site = pixel_repo.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if site["user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return pixel_repo.get_realtime(site_id)


@router.get("/pixel/sites/{site_id}/funnel")
async def get_funnel(site_id: str, days: int = 30, user: dict = Depends(verify_token)):
    site = pixel_repo.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if site["user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return pixel_repo.get_funnel(site_id, days=days)


@router.get("/pixel/sites/{site_id}/timeseries")
async def get_timeseries(site_id: str, days: int = 30, user: dict = Depends(verify_token)):
    site = pixel_repo.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if site["user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return pixel_repo.get_timeseries(site_id, days=days)


@router.get("/pixel/sites/{site_id}/devices")
async def get_devices(site_id: str, days: int = 30, user: dict = Depends(verify_token)):
    site = pixel_repo.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if site["user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return pixel_repo.get_devices(site_id, days=days)


@router.get("/pixel/sites/{site_id}/countries")
async def get_countries(site_id: str, days: int = 30, user: dict = Depends(verify_token)):
    site = pixel_repo.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if site["user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return pixel_repo.get_countries(site_id, days=days)


@router.get("/pixel/sites/{site_id}/pages")
async def get_pages(site_id: str, days: int = 30, user: dict = Depends(verify_token)):
    site = pixel_repo.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if site["user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return pixel_repo.get_pages(site_id, days=days)


@router.get("/pixel/sites/{site_id}/dashboard-summary")
async def get_dashboard_summary(site_id: str, days: int = 7, user: dict = Depends(verify_token)):
    """
    Aggregated endpoint for the Dashboard analytics overview.
    Single DB connection: 7 sequential queries vs the previous 4 pool acquisitions.
    Returns: stats, sparkline (number[]), top_pages (max 3), chips (max 4).
    """
    import re
    site = pixel_repo.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if site["user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    d = pixel_repo.get_dashboard_summary_data(site_id, days=days)

    def _path(url):
        return re.sub(r'^https?://[^/]+', '', url or '') or '/'

    # Normalize top pages
    top_pages = [
        {"path": _path(p.get("url", "/")), "views": p.get("views", 0), "url": p.get("url")}
        for p in d["pages_raw"]
    ]

    # Compute chips from pre-fetched raw data (no extra queries)
    chips = []
    sparkline = d["sparkline"]
    if len(sparkline) >= 6:
        half = len(sparkline) // 2
        a = sum(sparkline[:half])
        b = sum(sparkline[half:])
        if a > 0:
            pct = round(((b - a) / a) * 100)
            if pct > 5:   chips.append(f"+{pct}%")
            elif pct < -5: chips.append(f"{pct}%")

    devices = d["devices_raw"]
    if devices:
        total = sum(int(x["count"]) for x in devices)
        if total > 0:
            chips.append(f"{round(int(devices[0]['count']) / total * 100)}% {devices[0]['device']}")

    countries = d["countries_raw"]
    if countries:
        total = sum(int(x["count"]) for x in countries)
        if total > 0:
            chips.append(f"{round(int(countries[0]['count']) / total * 100)}% {countries[0]['country']}")

    if d["pages_raw"]:
        path = _path(d["pages_raw"][0].get("url", "/"))
        chips.append(path[:14] if len(path) <= 14 else path[:12] + "…")

    return {
        "stats":     d["stats"],
        "sparkline": sparkline,
        "top_pages": top_pages,
        "chips":     chips[:4],
    }


@router.delete("/pixel/sites/{site_id}")
async def delete_site(site_id: str, user: dict = Depends(verify_token)):
    site = pixel_repo.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if site["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    pixel_repo.delete_site(site_id, user["user_id"])
    return {"status": "deleted"}


@router.get("/pixel/sites/{site_id}/health")
async def get_site_health(site_id: str, user: dict = Depends(verify_token)):
    """last_seen_at + total eventos. Para soporte: confirmar si el pixel está activo."""
    site = pixel_repo.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if site["user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    rows = pixel_repo.get_site_health(site["user_id"])
    match = next((r for r in rows if r["site_id"] == site_id), None)
    return match or {"site_id": site_id, "last_seen_at": None, "total_events": 0}


@router.get("/pixel/admin/stats")
async def admin_stats(user: dict = Depends(require_role("admin"))):
    return pixel_repo.get_all_stats_admin()


@router.get("/pixel/admin/health")
async def admin_health(user: dict = Depends(require_role("admin"))):
    """Admin: todos los sites con last_seen_at. Detecta pixels muertos."""
    return pixel_repo.get_all_sites_health()


@router.post("/pixel/admin/cleanup")
async def admin_cleanup(days: int = 90, user: dict = Depends(require_role("admin"))):
    """Elimina eventos más viejos que `days` días. Usar con precaución."""
    if days < 7:
        raise HTTPException(status_code=400, detail="Mínimo 7 días de retención")
    deleted = pixel_repo.cleanup_old_events(days=days)
    return {"deleted": deleted, "retained_days": days}
