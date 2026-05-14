---
incident_id: SECURITY_UPLOAD_REJECTION_NOT_LOGGED
incident_type: security_audit_gap
severity: medium
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - emit_security_event_on_upload_rejection
forbidden_actions:
  - disable_upload_security_checks
  - log_client_file_content
signatures:
  - "upload rejected.*not logged"
  - "security event missing for upload"
---

# SECURITY_UPLOAD_REJECTION_NOT_LOGGED

## Síntoma
El módulo de seguridad rechaza subidas de archivos peligrosas (shells PHP, archivos de doble extensión, uploads sobredimensionados, tipos MIME sospechosos) pero el rechazo **no se registra** en el audit log ni en el Security Center. Los ataques son bloqueados pero no son visibles.

## Impacto
- Los ataques de upload se bloquean correctamente (no hay compromiso de seguridad inmediato).
- Sin embargo:
  1. **Invisibilidad**: el equipo de seguridad no sabe que se están produciendo intentos de ataque.
  2. **Sin detección de patrones**: múltiples intentos desde la misma IP no se correlacionan para activar bloqueo por reincidencia.
  3. **Sin incidentes en Security Center**: la pantalla del cliente y del admin muestra 0 eventos de seguridad de upload.
  4. **Sin métricas de ataque**: no se puede auditar la frecuencia ni el tipo de ataques que se están bloqueando.
- Riesgo: un atacante persiste sin ser detectado hasta que tiene éxito por otro vector.

## Evidencia
```bash
# El módulo rechaza uploads pero no emite eventos:
docker compose logs app | grep "upload.*reject\|reject.*upload\|file.*blocked"
# Sin resultados, aunque los uploads maliciosos están siendo bloqueados (HTTP 403)

# Verificar la tabla de security events en BD
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
result = db.execute(text(\"\"\"
  SELECT event_type, COUNT(*) as count
  FROM security_events
  WHERE event_type LIKE 'upload%'
    AND created_at > NOW() - INTERVAL '24 hours'
  GROUP BY event_type
\"\"\"))
rows = list(result)
print(rows if rows else 'NO upload security events in last 24h')
"
# Si retorna vacío pero hay tráfico de uploads, hay un gap de logging
```

## Causa raíz
El código de validación de uploads en el backend (FastAPI endpoint o middleware) ejecuta las comprobaciones de seguridad y retorna HTTP 403 directamente cuando detecta un archivo peligroso, pero no llama a `emit_security_event()` ni inserta ningún registro en `security_events` antes de retornar la respuesta de rechazo.

```python
# Código problemático:
async def upload_file(file: UploadFile, hosting_id: int, ...):
    if is_dangerous_extension(file.filename):
        raise HTTPException(status_code=403, detail="File type not allowed")  # ← no hay logging

    if file.size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large")  # ← no hay logging

    # ... resto del handler
```

El `raise HTTPException` no pasa por ningún hook que emita eventos de seguridad.

## Diagnósticos equivocados
- **"El módulo de seguridad no está funcionando"**: Sí está bloqueando; el problema es que no registra el bloqueo.
- **"No hay ataques de upload"**: Puede haberlos; simplemente no son visibles en el Security Center.
- **"El audit log está caído"**: Si otros tipos de eventos sí se registran, el problema es específico de los eventos de upload.

## Diagnóstico rápido
```bash
# 1. Verificar que los rechazos están ocurriendo (via logs de acceso)
docker compose logs app --tail=200 | grep "403\|413" | grep -i "upload\|file"

# 2. Verificar que el endpoint de upload existe y está activo
docker compose exec app python -c "
from app.api import app
routes = [r.path for r in app.routes if 'upload' in r.path.lower()]
print(routes)
"

# 3. Comparar: ¿cuántos 403 en el endpoint de upload vs cuántos eventos de seguridad de upload?
docker compose logs app --tail=1000 | grep "POST.*upload" | grep " 403 " | wc -l
# vs:
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
result = db.execute(text(\"SELECT COUNT(*) FROM security_events WHERE event_type LIKE 'upload%'\"))
print(list(result))
"
# Si los 403 > 0 y los security_events = 0, hay un gap de logging

# 4. Revisar el código del handler de upload
grep -rn "upload\|UploadFile" app/api/ | grep -v ".pyc"
```

## Solución manual
No hay acción de remediación de datos; los eventos pasados no se pueden recuperar. La acción es el fix de código.

```bash
# Verificar qué endpoints de upload existen y cuáles no tienen logging
grep -rn "UploadFile\|upload_file\|is_dangerous\|MAX_UPLOAD_SIZE" app/
```

## Fix permanente
Añadir emisión de evento de seguridad en TODOS los paths de rechazo de upload:

```python
from app.services.security_service import emit_security_event
import logging

logger = logging.getLogger(__name__)

async def upload_file(
    file: UploadFile,
    hosting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    client_ip = request.client.host if request else "unknown"

    # Comprobar extensión peligrosa
    if is_dangerous_extension(file.filename):
        logger.warning(
            "Dangerous file upload rejected",
            extra={"filename": file.filename, "hosting_id": hosting_id, "ip": client_ip}
        )
        emit_security_event(
            db=db,
            hosting_id=hosting_id,
            event_type="upload_dangerous_extension",
            severity="high",
            details={
                "filename": file.filename,  # SOLO el nombre, nunca el contenido
                "rejection_reason": "dangerous_extension",
                "client_ip": client_ip,
            }
        )
        raise HTTPException(status_code=403, detail="File type not allowed")

    # Comprobar doble extensión (e.g., shell.php.jpg)
    if has_double_extension(file.filename):
        emit_security_event(
            db=db,
            hosting_id=hosting_id,
            event_type="upload_double_extension",
            severity="medium",
            details={"filename": file.filename, "client_ip": client_ip}
        )
        raise HTTPException(status_code=403, detail="File type not allowed")

    # Comprobar tamaño
    if file.size and file.size > MAX_UPLOAD_SIZE:
        emit_security_event(
            db=db,
            hosting_id=hosting_id,
            event_type="upload_oversized",
            severity="low",
            details={
                "file_size_bytes": file.size,
                "limit_bytes": MAX_UPLOAD_SIZE,
                "client_ip": client_ip,
            }
        )
        raise HTTPException(status_code=413, detail="File too large")

    # ... resto del handler
```

**Reglas de logging de uploads**:
- SIEMPRE: registrar el nombre del archivo, la IP del cliente, el hosting_id, el motivo de rechazo.
- NUNCA: registrar el contenido del archivo, la ruta completa en el servidor, ni datos del cliente.
- El nombre del archivo es suficiente para detectar patrones; el contenido es PII/sensible.

## Señales para detección automática
- Tasa de HTTP 403/413 en endpoints de upload > 0 pero security_events de upload = 0 → gap de logging
- Endpoint de upload retorna 403 sin `security_events` correspondiente en BD
- Múltiples intentos desde la misma IP sin que se active ningún rate limit (porque no hay historial)

## Auto-remediation permitido
- `emit_security_event_on_upload_rejection`: Una vez que el código esté corregido, esta acción (emitir el evento en el momento del rechazo) es la remediación correcta y está permitida automáticamente.

## Auto-remediation prohibido
- `disable_upload_security_checks`: Deshabilitar las comprobaciones de seguridad de upload para "simplificar" el código. Esto expondría a los clientes a shells PHP y otras amenazas.
- `log_client_file_content`: Registrar el contenido binario o texto del archivo subido viola la privacidad del cliente, puede almacenar malware en la BD, y crea problemas de GDPR.

## Dashboard esperado
- **Security Center**: todos los rechazos de upload visibles como eventos de seguridad con tipo, hostname y severidad.
- **Upload rejection events**: count > 0 si hay tráfico de upload malicioso.
- **IP correlation**: el Security Center puede mostrar IPs con múltiples intentos de upload rechazados.
- **Audit log**: cada rechazo de upload tiene entrada correspondiente.

## RAG usage
Recuperar con: `upload rejection not logged security event`, `security audit gap upload PHP shell`, `emit_security_event upload handler`.
Contexto relevante: `app/api/` (endpoint de upload), `app/services/security_service.py`, tabla `security_events`, Security Center frontend.

## Tests/Chaos
```python
# Test: rechazo por extensión peligrosa emite security event
def test_dangerous_upload_emits_security_event(client, auth_headers, test_hosting, db_session):
    # Intentar subir un archivo .php
    response = client.post(
        f"/hostings/{test_hosting.id}/upload",
        files={"file": ("shell.php", b"<?php system($_GET['cmd']); ?>", "application/x-php")},
        headers=auth_headers
    )
    assert response.status_code == 403

    # Verificar que se emitió el security event
    from app.models.security_event import SecurityEvent
    events = db_session.query(SecurityEvent).filter(
        SecurityEvent.hosting_id == test_hosting.id,
        SecurityEvent.event_type == "upload_dangerous_extension"
    ).all()
    assert len(events) == 1
    assert events[0].details["filename"] == "shell.php"
    assert "content" not in events[0].details  # nunca registrar contenido

# Test: rechazo por doble extensión emite security event
def test_double_extension_upload_emits_security_event(client, auth_headers, test_hosting, db_session):
    response = client.post(
        f"/hostings/{test_hosting.id}/upload",
        files={"file": ("image.php.jpg", b"fake image", "image/jpeg")},
        headers=auth_headers
    )
    assert response.status_code == 403
    events = db_session.query(SecurityEvent).filter(
        SecurityEvent.hosting_id == test_hosting.id,
        SecurityEvent.event_type == "upload_double_extension"
    ).all()
    assert len(events) == 1

# Chaos: enviar 50 uploads maliciosos desde la misma IP
# Verificar que se generan 50 security events
# Verificar que se activa rate limiting / bloqueo de IP si está implementado
```
