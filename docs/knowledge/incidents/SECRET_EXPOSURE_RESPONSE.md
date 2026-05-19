---
type: incident
severity: critical
system: hostingguard
area: secrets-hygiene
status: active
rag_priority: high
keywords:
  - secret exposure
  - credentials leak
  - JWT_SECRET exposed
  - API key leaked
  - git history secret
  - hardcoded credentials
  - token leak
  - incident response
---

# SECRET_EXPOSURE_RESPONSE

Respuesta a incidente de exposición de credenciales en HostingGuard.

## Síntoma

Cualquiera de los siguientes:
- Un secreto (`JWT_SECRET`, `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, API keys) fue
  impreso en logs, en un informe, en un commit de git, o en una respuesta HTTP.
- Un archivo `.env.production` o backup fue accedido sin autorización.
- Un token `sk-ant-`, `ghp_`, o `ey...` aparece en docs, git history, o Slack.
- `validate_secrets_hygiene.sh` reporta credential patterns en docs.

## Impacto potencial

- **JWT_SECRET expuesto**: un atacante puede forjar tokens JWT para cualquier usuario o
  rol (admin, staff, support). Impersonación completa de la plataforma.
- **DATABASE_URL expuesto**: acceso directo a PostgreSQL con todas las credenciales de
  tenants, usuarios, y datos de facturación.
- **REDIS_URL expuesto**: acceso al store de sesiones, blacklist de tokens, caché de
  políticas de seguridad.
- **CLAUDE_API_KEY expuesto**: cargos a la cuenta de Anthropic, posible exfiltración de
  prompts que contengan datos de tenants.
- **LEMONSQUEEZY keys expuestos**: manipulación de suscripciones y pagos.

## Respuesta inmediata (primeros 15 minutos)

### 1. Revocar JWT_SECRET — máxima prioridad si fue expuesto

```bash
cd /opt/hosting_guard && git pull
sudo ./scripts/security/rotate_secrets_p4e.sh --apply
cd /opt/deploy
docker compose restart hosting_guard hg_worker hg_scheduler
```

### 2. Verificar que el app levantó correctamente

```bash
docker compose ps
curl -sf https://api.hostingguard.lat/health | python3 -m json.tool
```

### 3. Limpiar el vector de exposición

```bash
# Si fue en git history — reescribir y force-push (requiere coordinación del equipo):
git filter-repo --path-glob '*.env*' --invert-paths
# O usar BFG Repo Cleaner para secretos específicos

# Si fue en logs del servidor — rotar inmediatamente (ya hecho arriba)

# Si fue en documentación — redactar y commitear corrección
```

### 4. Auditar accesos recientes

```bash
# Revisar accesos al archivo .env
ls -la /root/.env.production.backup*
stat /opt/deploy/.env.production

# Revisar logs de acceso al API con el JWT antiguo (si hay logs de nginx/traefik)
# No hay forma de saber si el token fue usado sin analizar los access logs

# Revisar logs de la app por actividad sospechosa
cd /opt/deploy
docker compose logs --since="24h" hosting_guard | grep -E "event=|user_id=|401|403" | tail -100
```

### 5. Notificar si aplica

- Si `DATABASE_URL` fue expuesto: notificar al equipo y evaluar si hay acceso no autorizado a la DB.
- Si keys de billing fueron expuestas: contactar a LemonSqueezy y revocar las keys desde el dashboard.
- Si `CLAUDE_API_KEY` fue expuesto: revocar en Anthropic Console y crear nueva key.

## Clasificación por secreto

| Secreto expuesto | Acción inmediata | Urgencia |
|---|---|---|
| `JWT_SECRET` | Rotar con script + restart | Crítica — minutos |
| `SECRET_KEY` | Rotar con script (sin impacto en sesiones) | Alta — horas |
| `DATABASE_URL` | Cambiar password en PgBouncer + PostgreSQL | Crítica — minutos |
| `REDIS_URL` con password | Cambiar en Redis config + env | Alta — horas |
| `CLAUDE_API_KEY` | Revocar en Anthropic Console | Alta — horas |
| `LEMONSQUEEZY_*` | Revocar en LemonSqueezy dashboard | Alta — horas |
| `SMTP_PASS` | Revocar en proveedor de email | Media — día |
| `POSTGRES_PASSWORD` directa | Plan coordinado DBA | Crítica — plan separado |

## Diagnóstico — ¿dónde fue expuesto?

```bash
# Buscar en git history (sin mostrar valores)
git log --all --oneline | head -20
git grep -i "JWT_SECRET=" HEAD~20..HEAD -- '*.md' '*.env*' '*.yml'

# Buscar en docs actuales
grep -rn "sk-ant-\|ghp_\|JWT_SECRET=\|SECRET_KEY=" docs/ scripts/ --include="*.md"

# Validar higiene
sudo ./scripts/security/validate_secrets_hygiene.sh

# Buscar en logs de la app (sin imprimir valores)
cd /opt/deploy
docker compose logs hosting_guard | grep -i "secret\|jwt\|token" | grep -v "revoked\|validated\|bearer" | tail -50
```

## Post-incidente

Después de contener el incidente:

1. **Root cause analysis** — ¿cómo llegó el secreto al vector de exposición?
2. **Prevención** — agregar check en `validate_secrets_hygiene.sh` para el patrón.
3. **Documentar** en este archivo el incidente (sin valores reales).
4. **Revisión de acceso logs** — 24-48h después del evento.

## Comandos de revalidación

```bash
# Confirmar rotación exitosa (fingerprint)
sudo ./scripts/security/rotate_secrets_p4e.sh   # dry-run muestra fingerprints

# Validación general de higiene
sudo ./scripts/security/validate_secrets_hygiene.sh --strict

# Health final
curl -sf https://api.hostingguard.lat/health | python3 -m json.tool
```

## RAG usage

Si el operador reporta que un secreto fue impreso en logs, aparece en docs, o fue
commitado al repo → este es el runbook. Acción inmediata: rotar el secreto afectado
con `rotate_secrets_p4e.sh --apply` y reiniciar los servicios que lo usan. Si fue
`POSTGRES_PASSWORD` o `DATABASE_URL`, escalar — requiere plan coordinado.
