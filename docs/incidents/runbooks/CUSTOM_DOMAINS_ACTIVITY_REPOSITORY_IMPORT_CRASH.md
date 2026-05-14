---
incident_id: CUSTOM_DOMAINS_ACTIVITY_REPOSITORY_IMPORT_CRASH
incident_type: application_crash
severity: medium
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - skip_activity_fetch_on_import_error
forbidden_actions:
  - delete_activity_records
  - disable_activity_logging
signatures:
  - "ImportError: cannot import name"
  - "AttributeError: 'NoneType' object has no attribute 'custom_domain'"
---

# CUSTOM_DOMAINS_ACTIVITY_REPOSITORY_IMPORT_CRASH

## Síntoma
El módulo de repositorio de actividad (`activity_service.py`) lanza una excepción `ImportError` o `AttributeError` cuando se intenta cargar actividad para un hosting que tiene un dominio personalizado (`custom_domain`) configurado. El admin activity feed para esos hostings deja de funcionar parcialmente o por completo.

## Impacto
- El feed de actividad de administración falla para todos los hostings que tienen `custom_domain` asignado.
- Los registros de actividad existentes no se borran, pero no se pueden listar desde el panel.
- No afecta al funcionamiento del hosting en sí ni a la experiencia del cliente final.
- Alcance: solo el panel de administración, sección de actividad.

## Evidencia
```
ImportError: cannot import name 'ActivityRepository' from 'app.repositories.activity_repository'
# o bien:
AttributeError: 'NoneType' object has no attribute 'custom_domain'
Traceback (most recent call last):
  File "app/services/activity_service.py", line XX, in get_activity_for_hosting
    ...
```

Revisar logs de la aplicación:
```bash
docker compose logs app | grep -E "ImportError|AttributeError.*custom_domain"
```

## Causa raíz
Una de las siguientes:

1. **ImportError**: El módulo `activity_repository` fue refactorizado o renombrado y `activity_service.py` sigue importando el nombre antiguo.
2. **AttributeError**: El objeto `Hosting` recuperado de la BD no tiene el campo `custom_domain` cargado (lazy load no inicializado, o columna no mapeada en el ORM), y el código intenta acceder a él directamente sin comprobar `None`.

El campo `custom_domain` fue añadido al modelo `Hosting` sin actualizar todos los puntos de acceso del ORM o los imports relacionados.

## Diagnósticos equivocados
- **"El hosting no existe"**: El hosting existe; el error es en el layer de actividad, no en el objeto de hosting.
- **"Problema de permisos de BD"**: No es un problema de permisos; es un error de import o de ORM en Python.
- **"Bug en custom_domain en sí"**: El campo custom_domain puede estar bien en la BD; el problema es cómo lo accede `activity_service.py`.

## Diagnóstico rápido
```bash
# 1. Confirmar el error en logs
docker compose logs app --tail=100 | grep -E "ImportError|custom_domain"

# 2. Verificar que la columna existe en la BD
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
result = db.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name='hostings' AND column_name='custom_domain'\"))
print(list(result))
"

# 3. Verificar el import en activity_service.py
grep -n "import" app/services/activity_service.py | head -30

# 4. Verificar que el modelo ORM incluye custom_domain
grep -n "custom_domain" app/models/hosting.py
```

## Solución manual
### Para ImportError:
```bash
# 1. Identificar el nombre correcto del módulo/clase
grep -rn "class.*Repository\|def.*activity" app/repositories/

# 2. Corregir el import en activity_service.py
# Cambiar el import incorrecto por el nombre actual del módulo/clase

# 3. Rebuild y restart
docker compose up -d --build app
docker compose logs -f app | head -50
```

### Para AttributeError en custom_domain:
```python
# En activity_service.py, cambiar acceso directo:
#   hosting.custom_domain  →  getattr(hosting, 'custom_domain', None)
# O bien asegurarse de hacer eager load en la query:
#   query.options(load_only(Hosting.id, Hosting.custom_domain, ...))
```

```bash
# Tras el fix de código:
docker compose up -d --build app
```

## Fix permanente
1. Añadir test unitario en `tests/` que instancie un `Hosting` con `custom_domain` y llame a `activity_service.get_activity_for_hosting()`.
2. Si se usa lazy loading en el ORM, documentar qué campos requieren eager load en `activity_service.py`.
3. Al añadir columnas nuevas al modelo `Hosting`, ejecutar búsqueda en el codebase de todos los lugares que itereran sobre campos del modelo para actualizar.
4. Añadir migration check en CI: `alembic check` debe pasar antes del merge.

## Señales para detección automática
- Log pattern: `ImportError: cannot import name` en el contexto de `activity`
- Log pattern: `AttributeError.*custom_domain`
- HTTP 500 en endpoints `/admin/hostings/{id}/activity`
- Tasa de error > 0 en rutas de actividad para hostings con `custom_domain IS NOT NULL`

## Auto-remediation permitido
- `skip_activity_fetch_on_import_error`: Si el módulo falla al importar, el endpoint puede retornar lista vacía con un warning en logs en lugar de lanzar 500. Esto es un fallback seguro que no modifica datos.

## Auto-remediation prohibido
- `delete_activity_records`: Nunca borrar registros de actividad como solución al error de import. Los registros son append-only.
- `disable_activity_logging`: Deshabilitar el logging de actividad oculta el problema y crea deuda operativa.

## Dashboard esperado
- **Activity Feed**: debe mostrar entradas para todos los hostings, incluidos los que tienen `custom_domain`.
- **Error rate en /admin/hostings/{id}/activity**: debe ser 0%.
- **Logs de app**: sin `ImportError` ni `AttributeError` relacionados con `custom_domain` o `activity_repository`.

## RAG usage
Recuperar con: `custom_domain activity crash`, `ImportError activity_service`, `AttributeError custom_domain hosting`.
Contexto relevante: modelo `Hosting`, `activity_service.py`, `activity_repository.py`, migrations de `custom_domain`.

## Tests/Chaos
```python
# Test: hosting con custom_domain no rompe activity feed
def test_activity_fetch_with_custom_domain(db_session, test_hosting):
    test_hosting.custom_domain = "example.com"
    db_session.commit()
    result = activity_service.get_activity_for_hosting(db_session, test_hosting.id)
    assert result is not None  # No debe lanzar excepción

# Chaos: forzar custom_domain=None en un hosting activo y llamar al servicio
def test_activity_fetch_with_null_custom_domain(db_session, test_hosting):
    test_hosting.custom_domain = None
    db_session.commit()
    result = activity_service.get_activity_for_hosting(db_session, test_hosting.id)
    assert result is not None
```
