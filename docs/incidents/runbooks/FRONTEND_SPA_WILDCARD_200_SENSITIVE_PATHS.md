---
incident_id: FRONTEND_SPA_WILDCARD_200_SENSITIVE_PATHS
incident_type: security_misconfiguration
severity: medium
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - add_nginx_sensitive_path_block
  - add_nginx_spa_route_allowlist
forbidden_actions:
  - disable_spa_fallback_entirely
  - return_200_on_sensitive_paths
  - expose_api_docs_publicly
  - add_unknown_routes_to_spa_allowlist
signatures:
  - "random path 200 length=index.html"
  - "GET /server-status HTTP/1.1\" 200"
  - "GET /metrics HTTP/1.1\" 200"
  - "GET /openapi.json HTTP/1.1\" 200"
  - "GET /docs HTTP/1.1\" 200"
  - "GET /redoc HTTP/1.1\" 200"
  - "Gobuster aborts wildcard 200"
  - "sensitive frontend path returns index.html"
  - "__hg_audit_random"
  - "random route 200"
  - "unknown path returns index.html"
---

# FRONTEND_SPA_WILDCARD_200_SENSITIVE_PATHS

## Síntoma

Rutas sensibles en `hostingguard.lat` devuelven HTTP 200 con el body de `index.html` (el frontend SPA):

```
/server-status → 200 text/html length 919
/metrics       → 200 text/html length 919
/docs          → 200 text/html length 919
/redoc         → 200 text/html length 919
/openapi.json  → 200 text/html length 919
```

Gobuster y otros scanners abortan porque cualquier ruta aleatoria devuelve 200 con el mismo `Content-Length`.

## Impacto

- **Falsos positivos masivos** en herramientas de seguridad (gobuster, nikto, nuclei)
- **Oculta rutas inexistentes** — no se puede distinguir entre ruta válida y ruta inventada
- **Rompe health checks externos** que esperan 404 en rutas no existentes
- **Confunde a WAFs** que esperan respuestas semánticas correctas
- Los nombres de rutas sensibles (`/metrics`, `/docs`, `/admin`) no deben "existir" en la superficie de ataque aunque no expongan datos reales

## Evidencia

```bash
# Rutas sensibles devuelven 200 con el SPA
curl -s -o /dev/null -w "%{http_code} %{size_download}" https://hostingguard.lat/server-status
# → 200 919

curl -s -o /dev/null -w "%{http_code} %{size_download}" https://hostingguard.lat/metrics
# → 200 919

# Ruta aleatoria también devuelve 200 (SPA wildcard)
curl -s -o /dev/null -w "%{http_code} %{size_download}" https://hostingguard.lat/xyz-random-abc
# → 200 919

# Gobuster aborts
gobuster dir -u https://hostingguard.lat -w /usr/share/wordlists/dirb/common.txt
# → "Wildcard response found: 200 (Length: 919) — aborting"
```

## Causa raíz

El bloque SPA fallback en `nginx.conf` captura toda ruta que no corresponde a un archivo estático real:

```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

Para una SPA esto es correcto (React Router necesita que `/login`, `/dashboard` etc. devuelvan `index.html`). El problema es que rutas **semánticamente sensibles** como `/metrics`, `/server-status`, `/docs` también caen en este fallback en lugar de devolver 404.

## Diagnósticos equivocados

### ❌ "Expone datos — hay que parcharlo urgente"
**Por qué parece posible:** Los nombres suenan críticos (`/server-status`, `/metrics`).
**Por qué es incorrecto:** El body es siempre `index.html` — no hay datos reales expuestos. El impacto real es operativo (falsos positivos, confusión en scanners), no una fuga de datos.
**Severidad real:** medium, no critical.

### ❌ "Hay que desactivar el SPA fallback"
**Por qué parece posible:** El fallback es la causa del problema.
**Por qué es incorrecto:** Sin SPA fallback, React Router no funciona — `/login`, `/dashboard` devuelven 404. La solución es añadir un bloque específico ANTES del fallback para las rutas sensibles.

### ❌ "Traefik debería manejar esto"
**Por qué parece posible:** Traefik está delante de nginx.
**Por qué es incorrecto:** Traefik enruta al contenedor nginx del frontend. El comportamiento de 200 es interno a nginx, no a Traefik.

## Diagnóstico rápido

```bash
# Verificar si una ruta sensible devuelve 200 o 404
curl -s -o /dev/null -w "%{http_code}" https://hostingguard.lat/server-status
# → Antes del fix: 200 (problema)
# → Después del fix: 404 (correcto)

# Verificar que las rutas de app siguen funcionando
curl -s -o /dev/null -w "%{http_code}" https://hostingguard.lat/login
# → Siempre: 200 (SPA fallback, correcto)

# Detectar SPA wildcard: misma Content-Length en cualquier ruta
SIZE_REAL=$(curl -s -o /dev/null -w "%{size_download}" https://hostingguard.lat/login)
SIZE_FAKE=$(curl -s -o /dev/null -w "%{size_download}" https://hostingguard.lat/server-status)
[ "$SIZE_REAL" = "$SIZE_FAKE" ] && echo "WILDCARD ACTIVO" || echo "OK"
```

## Solución manual

Agregar bloque en `frontend/nginx.conf` ANTES del bloque SPA fallback:

```nginx
# Sensitive server/infra paths — return 404 before SPA fallback
location ~* ^/(server-status|server-info|metrics|prometheus|healthz|health|status|docs|redoc|swagger|openapi\.json|api-docs|backup\.sql|db\.sql|dump\.sql|phpinfo\.php|info\.php|test\.php|wp-login\.php|wp-admin|xmlrpc\.php|admin|administrator|phpmyadmin|adminer|\.env|\.git|\.svn|\.htaccess|\.htpasswd) {
    return 404;
}
```

Orden correcto de bloques en nginx.conf:
1. Archivos ocultos (`.env`, `.git`) → 404
2. Extensiones sensibles (`.sql`, `.php`) → 404
3. Archivos de config de build (`package.json`, etc.) → 404
4. **Rutas sensibles de servidor** → 404  ← este bloque nuevo
5. `/assets/` → archivos estáticos exactos
6. `/` → SPA fallback

## Fix permanente

El bloque ya está en `frontend/nginx.conf`. Se aplica con el próximo rebuild del contenedor frontend:

```bash
# En servidor de producción
cd /opt/deploy
docker compose up -d --build frontend
```

## Señales para detección automática

- Petición GET a `/server-status` devuelve 200 y `Content-Type: text/html`
- `Content-Length` de `/metrics` == `Content-Length` de `/login` (SPA wildcard)
- Gobuster reporta "Wildcard response" con longitud constante
- Nikto reporta `/server-status` como "potentially interesting"

## Auto-remediation permitido

Ninguna. Requiere rebuild del contenedor frontend.

## Auto-remediation prohibido

- No desactivar el SPA fallback completo
- No devolver 200 en rutas sensibles "para no romper nada"
- No exponer `/docs` o `/openapi.json` públicamente (el backend tiene auth)

## Dashboard esperado

Incidente de severidad `medium` en Security Center. No degrada el score de salud general del tenant (no hay contenido real expuesto). Badge informativo, no crítico.

## RAG usage

Cuando el operador reporte "gobuster no funciona", "rutas sensibles devuelven 200", "wildcard 200 en scanner" → matchear a este runbook.
Respuesta AI: "El SPA de React sirve `index.html` para cualquier ruta no mapeada. Agregar el bloque nginx de rutas sensibles ANTES del fallback. No desactivar el fallback completo."

## Tests/Chaos

```bash
# Después del fix, verificar:
curl -s -o /dev/null -w "%{http_code}" https://hostingguard.lat/metrics      # → 404
curl -s -o /dev/null -w "%{http_code}" https://hostingguard.lat/server-status # → 404
curl -s -o /dev/null -w "%{http_code}" https://hostingguard.lat/docs          # → 404
curl -s -o /dev/null -w "%{http_code}" https://hostingguard.lat/openapi.json  # → 404
curl -s -o /dev/null -w "%{http_code}" https://hostingguard.lat/login         # → 200
curl -s -o /dev/null -w "%{http_code}" https://hostingguard.lat/dashboard     # → 200
```
