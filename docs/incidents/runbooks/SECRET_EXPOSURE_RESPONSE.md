---
incident_id: SECRET_EXPOSURE_RESPONSE
incident_type: secrets_hygiene
severity: critical
status: confirmed
validated: true
auto_repair_allowed: false
area: secrets-hygiene
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
safe_actions:
  - run_secrets_hygiene_validation
  - rotate_jwt_secret
  - rotate_secret_key
forbidden_actions:
  - log_secret_value
  - print_env_file_content
  - rotate_postgres_password_without_plan
  - commit_env_file_to_git
---

# SECRET_EXPOSURE_RESPONSE

Incidente de exposición de credenciales en HostingGuard.

## Runbook completo

Ver [docs/knowledge/incidents/SECRET_EXPOSURE_RESPONSE.md](../../knowledge/incidents/SECRET_EXPOSURE_RESPONSE.md).

## Acción inmediata

Si `JWT_SECRET` fue expuesto:

```bash
cd /opt/hosting_guard && git pull
sudo ./scripts/security/rotate_secrets_p4e.sh --apply
cd /opt/deploy
docker compose restart app worker scheduler
sudo ./scripts/security/validate_secrets_hygiene.sh
```

## Clasificación

| Secreto expuesto | Urgencia |
|---|---|
| `JWT_SECRET` | Crítica — minutos |
| `DATABASE_URL` | Crítica — minutos |
| `SECRET_KEY` | Alta — horas |
| `REDIS_URL` con password | Alta — horas |
| `CLAUDE_API_KEY` | Alta — horas |
| `LEMONSQUEEZY_*` | Alta — horas |
| `SMTP_PASS` | Media — día |
