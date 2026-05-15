---
incident_id: TENANT_CLOUDFLARE_526_ORIGIN_TLS_INVALID
incident_type: cloudflare_526_origin_tls
severity: high
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - regenerate_tenant_file_provider_route
  - migrate_tenant_route_docker_labels_to_file
  - validate_origin_tls_direct_resolve
  - request_letsencrypt_certificate
  - fix_static_file_permissions
forbidden_actions:
  - disable_tls_verification
  - bypass_forwardauth
  - mark_healthy_on_container_running_only
  - turn_off_cloudflare_security_globally
signatures:
  - "HTTP/2 526"
  - "error code: 526"
  - "Invalid SSL certificate"
  - "Cloudflare 526"
  - "traefik_backend_unreachable"
  - "status_code 526"
  - "router_source docker_labels"
  - "cloudflare_526"
  - "526 origin tls"
  - "origin tls invalid"
---

# TENANT_CLOUDFLARE_526_ORIGIN_TLS_INVALID

## Síntoma

El subdominio del tenant devuelve Cloudflare error 526 "Invalid SSL Certificate":

```
HTTP/2 526
cf-ray: ...
server: cloudflare

Error 526 Ray ID: ...
Invalid SSL Certificate
```

Cloudflare no puede validar el certificado SSL del servidor de origen (Traefik). Esto ocurre cuando Cloudflare opera en modo "Full (strict)" o hay un mismatch entre el certificado de origen y el dominio.

## Impacto

- El sitio es completamente inaccesible desde Cloudflare.
- El contenedor puede estar running y Traefik funcionando correctamente — el error es externo.
- El health check del Router Health Guard reporta el host con error, pero la causa raíz está en la configuración de Cloudflare/TLS, no en la ruta Traefik.
- Falsos positivos: el Router Health Guard puede detectar esto como `traefik_backend_unreachable` cuando en realidad es un problema de TLS entre Cloudflare y el origen.

## Diagnóstico rápido

```bash
DOMAIN="tenant.hostingguard.lat"

# Confirmar código 526
curl -sv "https://${DOMAIN}/" 2>&1 | grep "< HTTP\|526\|SSL\|cloudflare"

# Verificar directamente al origen (sin Cloudflare)
# Primero obtener la IP del servidor
SERVER_IP="10.0.0.3"
curl -sk --resolve "${DOMAIN}:443:${SERVER_IP}" "https://${DOMAIN}/" -o /dev/null -w "%{http_code}"
# → Si retorna 200/401/403 aquí pero 526 desde Cloudflare: problema de TLS entre CF y origen

# Verificar certificado de origen
echo | openssl s_client -connect "${SERVER_IP}:443" -servername "${DOMAIN}" 2>/dev/null | openssl x509 -noout -subject -dates

# Ver configuración SSL de Cloudflare para el dominio
# En dashboard Cloudflare: SSL/TLS → Overview → Modo (debe ser "Full" no "Full Strict" si hay cert auto-firmado)

# Revisar route del tenant en Traefik
cat /opt/traefik-dynamic/tenant-${DOMAIN/./-}.yml 2>/dev/null
```

## Causa raíz — Escenarios comunes

### Escenario A — Cloudflare en modo Full (strict) con certificado auto-firmado
Cloudflare Full (strict) exige que el origen tenga un certificado válido emitido por una CA reconocida. Si Traefik usa un certificado auto-firmado o el Let's Encrypt no renovó, Cloudflare rechaza la conexión con 526.

### Escenario B — Route via docker_labels sin certificado en el puerto 443
Si el tenant usa `router_source: docker_labels` en lugar del file provider, el certificado Let's Encrypt puede no haberse generado para ese subdominio. Traefik necesita el resolver `le` configurado en los labels.

### Escenario C — IP del origen cambió / DNS misconfigured
Si el origen de Cloudflare apunta a una IP incorrecta, el certificado de esa IP no matcheará el dominio → 526.

### Escenario D — Certificado expirado en Traefik
Let's Encrypt falló en renovar el certificado. `acme.json` tiene el certificado pero está expirado.

## Diferencia crítica: 526 vs otros errores

| Error | Causa | Saludable en origen |
|---|---|---|
| 526 | TLS inválido entre CF y origen | Posiblemente sí |
| 525 | SSL Handshake Failed | Posiblemente sí |
| 522 | Connection timed out | Origen caído |
| 523 | Origin unreachable | Origen caído |
| 524 | Timeout | Origen lento |

Un 526 **no** significa que el contenedor está caído — puede estar 200 cuando se accede directamente al origen.

## Diagnósticos equivocados

### ❌ "El contenedor está caído"
**Por qué parece posible:** El sitio devuelve error.
**Por qué es incorrecto:** 526 es un error de Cloudflare, no del contenedor. Verificar el origen directamente antes de tocar el contenedor.

### ❌ "Hay que desactivar TLS verification globalmente"
**Por qué es incorrecto y peligroso:** Desactivar TLS verification en Cloudflare expone todo el tráfico entre CF y el origen. Prohibido explícitamente.

### ❌ "Hay que tocar la configuración de Cloudflare del dashboard general"
**Por qué es incorrecto:** Los tenants tienen sus propias reglas. Cambios globales afectan a todos los clientes. Prohibido.

### ❌ "Hay que marcar el hosting como healthy porque el contenedor está running"
**Por qué es incorrecto:** `container running + 526 público` = **unhealthy**. El usuario no puede acceder al sitio.

## Solución manual

### Opción A — Cambiar Cloudflare SSL mode a "Full" (no strict)
Si el certificado de origen es auto-firmado o de Let's Encrypt en modo staging:
1. Dashboard Cloudflare → `hostingguard.lat` → SSL/TLS → Overview
2. Cambiar de "Full (strict)" a "Full"
3. Esperar 2-5 minutos para que propagule

### Opción B — Regenerar certificado Let's Encrypt
Si el certificado expiró:
```bash
# En servidor de producción
# 1. Verificar que el puerto 80 está accesible desde internet (Traefik ACME)
curl -s http://${DOMAIN}/.well-known/acme-challenge/test -o /dev/null -w "%{http_code}"

# 2. Borrar certificado expirado de acme.json y reiniciar Traefik para regenerar
docker compose restart traefik
```

### Opción C — Migrar de docker_labels a file provider route
Si el tenant usa labels de Docker y no tiene certificado generado:
```bash
# El safe action regenerate_tenant_file_provider_route genera el YAML del file provider
# con el resolver le configurado. Traefik genera el cert automáticamente.
```

## Señales para detección automática

- Código HTTP 526 desde el dominio público
- `cf-ray` header presente en la respuesta (confirma que pasó por Cloudflare)
- Certificado directo al origen válido pero CF rechaza → modo Full (strict) con cert staging
- `router_source: docker_labels` + ausencia de certificado en acme.json para el dominio

## Auto-remediation prohibido

- No desactivar TLS verification a nivel de Cloudflare (`disable_tls_verification`).
- No tocar la configuración global de seguridad de Cloudflare.
- No marcar como healthy si el código público sigue siendo 526.
- No hacer bypass de ForwardAuth (no relacionado con este error).

## Dashboard esperado

- Badge **HIGH** en el tenant: "Error 526 — TLS inválido entre Cloudflare y origen".
- Incidente activo: `cloudflare_526_origin_tls`.
- Acción recomendada: "Regenerar certificado o cambiar modo SSL de Cloudflare".
- `public_reachable: false` — el scoring del tenant baja a 0.

## RAG usage

Cuando el operador reporte "error 526", "Invalid SSL certificate", "Cloudflare error", "el sitio no carga" en un dominio con Cloudflare activo → matchear este runbook. Verificar primero si el origen responde directamente (sin CF). Si responde, el problema es la configuración TLS de CF, no el contenedor. Si no responde, puede ser `container_not_running` o `traefik_router_missing_or_unmatched`.

## Tests/Chaos

```bash
# Simular la detección:
curl -s -o /dev/null -w "%{http_code}" "https://chaos-test.hostingguard.lat/"
# → 526

# Verificar que el Router Health Guard clasifica correctamente
# y no muestra 'container_not_running' cuando el contenedor está running
docker inspect chaos-test --format "{{.State.Status}}"
# → running (confirma que el 526 es de TLS, no del contenedor)
```
