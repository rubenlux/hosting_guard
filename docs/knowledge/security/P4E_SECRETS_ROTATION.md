---
type: security-hardening
severity: high
system: hostingguard
area: secrets-hygiene
status: resolved
rag_priority: high
keywords:
  - JWT_SECRET
  - SECRET_KEY
  - secrets rotation
  - credentials hygiene
  - token invalidation
  - .env.production
  - fingerprint
  - backup
---

# P4E — Secrets Rotation & Credentials Hygiene

**Fecha**: 2026-05 (auditoría P4E)
**Estado**: Procedimiento documentado. Scripts creados y validados.

## Contexto

Después de P4B (network isolation) y P4C (runtime hardening), P4E cierra el ciclo de
higiene de secretos. Objetivo: rotar `JWT_SECRET` y `SECRET_KEY` sin downtime de
contenedores, con backup, fingerprint de verificación, y sesiones antiguas invalidadas.

## Variables en scope

| Variable | Uso en runtime | Impacto de rotación |
|---|---|---|
| `JWT_SECRET` | Firma/verifica TODOS los JWT (access, refresh, staff) | Invalida todas las sesiones activas inmediatamente al restart |
| `SECRET_KEY` | Bloqueada en build containers — no usada en runtime FastAPI | Sin impacto en sesiones, no requiere flush de Redis |
| `DATABASE_URL` | Conexión PostgreSQL vía PgBouncer | Requiere coordinación con DB — **no rotar en P4E** |
| `REDIS_URL` | Caché, rate-limit, revocación de tokens | Si lleva password en URL, requiere reconfigurar Redis — **no rotar en P4E** |
| `SMTP_PASS` | Envío de emails | Solo afecta emails salientes — **posterior a JWT** |
| `CLAUDE_API_KEY` | AI Advisory | Solo afecta AI Advisory — **posterior a JWT** |
| `LEMONSQUEEZY_*` | Billing | Solo afecta billing — **posterior a JWT** |
| `POSTGRES_PASSWORD` | Login DB directo | Requiere plan separado con PgBouncer y pg_hba — **NO en P4E** |

## Cómo funciona `JWT_SECRET` en el código

`app/api/security.py` lee `JWT_SECRET` al importar el módulo:

```python
SECRET = os.getenv("JWT_SECRET")
if not SECRET:
    raise RuntimeError("JWT_SECRET is required.")
```

`SECRET` se usa en `create_token()`, `create_refresh_token()`, `create_staff_token()`,
y en todos los `jwt.decode(token, SECRET, ...)`. Al rotar `JWT_SECRET` y reiniciar el
app, todos los tokens firmados con el valor anterior fallan la verificación → sesiones
invalidadas automáticamente.

No hay cache de `SECRET` en Redis — el efecto es inmediato tras el restart.

## Procedimiento de rotación (JWT_SECRET + SECRET_KEY)

### Paso 1 — Dry-run (sin cambios)

```bash
cd /opt/hosting_guard
git pull
sudo ./scripts/security/rotate_secrets_p4e.sh
# → muestra fingerprints actuales, no modifica nada
```

### Paso 2 — Ejecutar rotación

```bash
sudo ./scripts/security/rotate_secrets_p4e.sh --apply
```

El script:
1. Verifica permisos del `.env.production` (no world-readable)
2. Muestra fingerprints actuales (longitud + SHA256 parcial)
3. Crea backup: `/root/.env.production.backup_p4e_YYYYMMDD_HHMMSS` (perms 600, owner root)
4. Genera nuevos secretos con `openssl rand -hex 64` DENTRO de Python (nunca en variables shell)
5. Reemplaza en `.env.production` usando `re.sub` con renombramiento atómico
6. Verifica fingerprints post-rotación
7. Muestra instrucciones de restart

### Paso 3 — Reiniciar servicios

```bash
cd /opt/deploy
docker compose restart hosting_guard hg_worker hg_scheduler
```

### Paso 4 — Validar

```bash
# Estado de contenedores
docker compose ps

# Health check
curl -sf https://api.hostingguard.lat/health | python3 -m json.tool

# Verificar que sesiones antiguas están invalidadas:
# Intentar un endpoint protegido con un token viejo → debe devolver 401
```

### Paso 5 — Higiene general

```bash
cd /opt/hosting_guard
sudo ./scripts/security/validate_secrets_hygiene.sh
```

## Seguridad del script de rotación

- **Sin shell variables con secretos**: los nuevos valores se generan y escriben completamente dentro de un proceso Python. Nunca asignados a variables bash que pudieran aparecer en `/proc/PID/environ` o `ps aux`.
- **Fingerprint-only output**: solo se imprime `len=128 sha256=a3f1b2c4...` — nunca el valor.
- **Atomic write**: el archivo se escribe a un `.tmp_rotate` y se renombra — no queda en estado corrupto si el proceso se interrumpe.
- **Rollback automático**: si falla la escritura o la verificación post-rotación, el script restaura desde el backup.
- **Backup perms 600**: solo root puede leer el backup.

## Validación de fingerprint

Para verificar que la rotación fue exitosa sin imprimir el secreto:

```bash
python3 -c "
import hashlib, re, os
env = open('/opt/deploy/.env.production').read()
m = re.search(r'^JWT_SECRET=(.+)$', env, re.MULTILINE)
val = m.group(1).strip()
sha = hashlib.sha256(val.encode()).hexdigest()[:12]
print(f'JWT_SECRET: len={len(val)} sha256={sha}...')
"
```

## Impacto operacional

| Afectado | Efecto | Mitigación |
|---|---|---|
| Usuarios con sesión activa | Serán deslogueados al siguiente request | Avisar por email si es horario laboral |
| Staff con staff_token | Serán deslogueados | Re-login en panel de staff |
| Tokens de soporte activos | Expirarán con el restart | Notificar al equipo de soporte |
| Webhooks (HMAC) | No afectados (usan `webhook_token` por hosting, no JWT_SECRET) | — |
| Rate limiter Redis | No afectado | — |
| Caché Redis (policy, subdomain) | No afectado | — |

## Rollback

Si después del restart el app no levanta:

```bash
# 1. Restaurar backup
sudo cp /root/.env.production.backup_p4e_<TIMESTAMP> /opt/deploy/.env.production

# 2. Reiniciar
cd /opt/deploy
docker compose restart hosting_guard hg_worker hg_scheduler

# 3. Verificar
docker compose ps
curl -sf https://api.hostingguard.lat/health
```

## Comandos de diagnóstico rápido

```bash
# Ver si JWT_SECRET está seteado (sin imprimir valor)
python3 -c "import re,hashlib; v=re.search(r'JWT_SECRET=(.+)',open('/opt/deploy/.env.production').read()); val=v.group(1).strip(); print('len=',len(val),'sha256=',hashlib.sha256(val.encode()).hexdigest()[:8],'...')"

# Ver logs del app al arrancar (busca RuntimeError si JWT_SECRET falta)
cd /opt/deploy && docker compose logs --tail=50 hosting_guard

# Verificar que el app firma tokens correctamente (requiere login válido)
curl -sf https://api.hostingguard.lat/health | python3 -m json.tool
```

## Prevención

1. `validate_secrets_hygiene.sh` debe ejecutarse mensualmente o después de cualquier cambio en `.env.production`.
2. Nunca imprimir `os.getenv("JWT_SECRET")` en logs de la app.
3. `build_runner.py` ya bloquea `JWT_SECRET` y `SECRET_KEY` de pasar a containers de build.
4. El backup debe rotarse periódicamente — mantener máximo 3 backups históricos.

## Runbooks relacionados

- [SECRETS_ROTATION](../runbooks/SECRETS_ROTATION.md) — Procedimiento operativo completo
- [SECRET_EXPOSURE_RESPONSE](../incidents/SECRET_EXPOSURE_RESPONSE.md) — Si se expone un secreto
