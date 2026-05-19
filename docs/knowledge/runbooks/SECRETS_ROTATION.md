---
type: runbook
severity: high
system: hostingguard
area: secrets-hygiene
status: active
rag_priority: high
keywords:
  - JWT_SECRET rotation
  - SECRET_KEY rotation
  - .env.production
  - secrets hygiene
  - credentials
  - backup
  - fingerprint
  - token invalidation
---

# Runbook — SECRETS_ROTATION

Procedimiento operativo para rotar credenciales en HostingGuard producción.
Cubre rotación segura, backup, validación y rollback.

## Prioridad de rotación

| Prioridad | Variable | Impacto | Estado P4E |
|---|---|---|---|
| 1 | `JWT_SECRET` | Invalida todas las sesiones | **Rotado en P4E** |
| 2 | `SECRET_KEY` | Sin impacto runtime (FastAPI) | **Rotado en P4E** |
| 3 | `REDIS_PASSWORD` / `REDIS_URL` | Requiere reconfigurar Redis | Pendiente |
| 4 | `SMTP_PASS` | Solo afecta emails salientes | Pendiente |
| 5 | `CLAUDE_API_KEY` | Solo AI Advisory | Pendiente |
| 6 | `LEMONSQUEEZY_*` | Solo billing | Pendiente |
| 7 | `POSTGRES_PASSWORD` / `DATABASE_URL` | Requiere coordinación DB | **Plan separado** |

## Diagnóstico rápido — estado actual

```bash
# Ver fingerprints de secretos (sin imprimir valores)
sudo ./scripts/security/rotate_secrets_p4e.sh   # dry-run

# Validar higiene general
sudo ./scripts/security/validate_secrets_hygiene.sh

# Ver permisos de .env.production
stat /opt/deploy/.env.production

# Verificar que JWT_SECRET está presente (fingerprint)
python3 -c "
import hashlib, re
content = open('/opt/deploy/.env.production').read()
for k in ['JWT_SECRET', 'SECRET_KEY']:
    m = re.search(rf'^{k}=(.+)', content, re.MULTILINE)
    if m:
        v = m.group(1).strip()
        sha = hashlib.sha256(v.encode()).hexdigest()[:8]
        print(f'{k}: len={len(v)} sha256={sha}...')
    else:
        print(f'{k}: NOT FOUND')
"
```

## Rotación de JWT_SECRET y SECRET_KEY

```bash
cd /opt/hosting_guard
git pull  # asegura que el script está actualizado

# 1. Dry-run (ver qué haría)
sudo ./scripts/security/rotate_secrets_p4e.sh

# 2. Aplicar rotación
sudo ./scripts/security/rotate_secrets_p4e.sh --apply

# 3. Reiniciar servicios afectados
cd /opt/deploy
docker compose restart app worker scheduler

# 4. Validar
docker compose ps
curl -sf https://api.hostingguard.lat/health | python3 -m json.tool
```

## Solo rotar SECRET_KEY (no JWT_SECRET)

```bash
# No existe flag directo — editar .env.production manualmente con valor de openssl:
NEW_SK=$(openssl rand -hex 64)
# (copiar valor, NO pegar en log)
# Reemplazar en .env.production y reiniciar
```

Alternativa: usar el script con `ROTATE_SK=true` y no reiniciar si solo se rotó `SECRET_KEY`
(no tiene impacto en sesiones).

## Validación post-rotación

```bash
# 1. Contenedores levantados
docker compose ps | grep -E "hosting_guard|hg_worker|hg_scheduler"

# 2. Health check
curl -sf https://api.hostingguard.lat/health | python3 -m json.tool
# Expected: {"status": "ok", ...}

# 3. Verificar invalidación de sesiones
# Un token viejo (de antes del restart) debe devolver 401:
# curl -b "access_token=<OLD_TOKEN>" https://api.hostingguard.lat/me
# → 401 Could not validate credentials

# 4. Higiene post-rotación
sudo ./scripts/security/validate_secrets_hygiene.sh
```

## Rollback

```bash
# 1. Identificar el backup más reciente
ls -la /root/.env.production.backup_p4e_*

# 2. Restaurar
sudo cp /root/.env.production.backup_p4e_<TIMESTAMP> /opt/deploy/.env.production

# 3. Reiniciar
cd /opt/deploy
docker compose restart app worker scheduler

# 4. Verificar
docker compose ps
curl -sf https://api.hostingguard.lat/health
```

## Rotación futura — REDIS_URL con password

Requiere:
1. Actualizar password en el servidor Redis con `CONFIG SET requirepass <new_pass>`.
2. Actualizar `REDIS_URL` en `.env.production`.
3. Reiniciar todos los servicios que usan Redis (hosting_guard, hg_worker, hg_scheduler).
4. Verificar conectividad: `docker exec redis redis-cli -a <new_pass> PING`.

**No ejecutar en P4E** — plan separado requerido.

## Rotación futura — POSTGRES_PASSWORD

Requiere coordinación con PgBouncer:
1. Agregar nuevo usuario en PostgreSQL.
2. Actualizar `DATABASE_URL` en `.env.production` para PgBouncer.
3. Actualizar `pgbouncer.ini` y `userlist.txt` en el servidor de DB.
4. Reiniciar PgBouncer y verificar pool.
5. Revocar usuario anterior.

**No ejecutar sin plan coordinado con DBA.**

## Señales de alarma

| Señal | Diagnóstico |
|---|---|
| `RuntimeError: JWT_SECRET is required` en logs | `JWT_SECRET` vacío o no cargado |
| Todos los usuarios deslogueados súbitamente | JWT_SECRET rotado sin aviso previo |
| `401 Could not validate credentials` masivo | JWT_SECRET cambió pero restart no completó |
| `.env.production` en perms 644 o 664 | Archivo world-readable — emergencia |

## Prohibido

- No imprimir el valor de ningún secreto en la terminal.
- No pasar secretos como argumentos de línea de comandos (`docker run -e JWT_SECRET=...`).
- No dejar valores en `history` del shell (usar scripts que lean de archivo).
- No rotar `POSTGRES_PASSWORD` sin procedimiento coordinado.
- No eliminar el backup antes de confirmar que la rotación fue exitosa.
- No rotar `DATABASE_URL` en P4E.

## Incidentes relacionados

- [SECRET_EXPOSURE_RESPONSE](../incidents/SECRET_EXPOSURE_RESPONSE.md) — Si un secreto fue expuesto
- [P4E_SECRETS_ROTATION](../security/P4E_SECRETS_ROTATION.md) — Detalle técnico de P4E
