---
incident_id: ADMIN_TERMINATE_PIXEL_EVENTS_TYPE_MISMATCH
incident_type: database_query_error
severity: medium
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions: []
forbidden_actions:
  - alter_column_type_without_migration
  - disable_pixel_events
signatures:
  - "operator does not exist: text = integer"
  - "ProgrammingError: operator does not exist"
---

# ADMIN_TERMINATE_PIXEL_EVENTS_TYPE_MISMATCH

## Síntoma
El endpoint de administración para terminar un hosting o para consultar pixel events retorna HTTP 500. Los logs muestran `ProgrammingError: operator does not exist: text = integer`. La operación falla completamente; no se termina ningún hosting ni se retornan pixel events.

## Impacto
- Los administradores no pueden terminar hostings desde el panel mientras persista el error.
- Las consultas de pixel events para un hosting específico fallan con 500.
- No hay pérdida de datos; el hosting sigue activo (lo cual puede ser el comportamiento no deseado si la intención era terminarlo).
- Alcance: solo las operaciones admin que filtran por `hosting_id` en tablas donde ese campo es de tipo `TEXT`.

## Evidencia
```
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedFunction)
operator does not exist: text = integer
LINE 1: ...WHERE pixel_events.hosting_id = $1
HINT: No operator matches the given name and argument types.
You might need to add explicit type casts.
```

```bash
docker compose logs app | grep "operator does not exist"
```

## Causa raíz
La columna `hosting_id` en la tabla `pixel_events` (y posiblemente en otras tablas relacionadas) está almacenada como `TEXT` (o `VARCHAR`), pero el parámetro que se pasa en la query es un `integer` (el ID numérico del hosting). PostgreSQL no hace cast implícito entre `TEXT` e `INTEGER`, por lo que rechaza el operador `=`.

Esto ocurre cuando:
1. El modelo ORM define `hosting_id` como `Integer` pero la columna real en BD es `TEXT`.
2. Una query raw usa `hosting_id = :hosting_id` y el binding es un int Python.
3. El ID del hosting se almacenó históricamente como string (e.g., `"42"`) y ahora se consulta con `42` (int).

## Diagnósticos equivocados
- **"La tabla pixel_events no existe"**: La tabla existe; el problema es el tipo de la columna.
- **"El hosting_id no existe en la tabla"**: Existe; el tipo no coincide con el parámetro.
- **"Error de permisos en BD"**: No es permisos; es un mismatch de tipos en el operador `=`.

## Diagnóstico rápido
```bash
# 1. Confirmar el error en logs
docker compose logs app --tail=100 | grep "operator does not exist"

# 2. Verificar el tipo real de hosting_id en pixel_events
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
result = db.execute(text(\"\"\"
  SELECT column_name, data_type
  FROM information_schema.columns
  WHERE table_name='pixel_events' AND column_name='hosting_id'
\"\"\"))
for row in result: print(row)
"

# 3. Buscar el punto de la query que causa el error
grep -rn "pixel_events\|terminate" app/api/admin/ | grep -i "hosting_id"

# 4. Verificar el tipo en el modelo ORM
grep -n "hosting_id" app/models/pixel_event.py 2>/dev/null || \
grep -rn "hosting_id" app/models/
```

## Solución manual
### Opción A: Cast en la query (fix inmediato, sin migration)
```python
# En la query raw o en el filtro ORM, añadir cast explícito:

# SQLAlchemy ORM:
from sqlalchemy import cast, Text
db.query(PixelEvent).filter(cast(PixelEvent.hosting_id, Text) == str(hosting_id))

# Query raw:
db.execute(text("SELECT * FROM pixel_events WHERE hosting_id = CAST(:hid AS TEXT)"),
           {"hid": str(hosting_id)})
# o alternativamente:
db.execute(text("SELECT * FROM pixel_events WHERE hosting_id = :hid"),
           {"hid": str(hosting_id)})  # pasar como string
```

### Opción B (para terminate endpoint):
```python
# Si hosting_id en pixel_events es TEXT, asegurarse de pasar string:
hosting_id_str = str(hosting_id)
# usar hosting_id_str en todas las queries sobre pixel_events
```

```bash
# Rebuild y restart tras el fix
docker compose up -d --build app
```

## Fix permanente
1. Decidir el tipo canónico de `hosting_id` en todas las tablas y estandarizarlo:
   - Si el ID de hosting es siempre numérico, migrar `pixel_events.hosting_id` a `INTEGER` con foreign key.
   - Si debe ser `TEXT` por compatibilidad, asegurarse de que todos los bindings usen `str()`.
2. Añadir migration Alembic si se cambia el tipo de columna.
3. Añadir tests de integración para terminate y pixel_events que usen IDs reales de hosting.
4. Añadir validación de tipos en el schema Pydantic del request para detectar el mismatch antes de llegar a BD.

## Señales para detección automática
- Log pattern: `operator does not exist: text = integer`
- Log pattern: `ProgrammingError: operator does not exist`
- HTTP 500 en `POST /admin/hostings/{id}/terminate`
- HTTP 500 en `GET /admin/hostings/{id}/pixel-events`

## Auto-remediation permitido
Ninguna. El fix requiere corrección de código (cast o cambio de tipo) y redeploy.

## Auto-remediation prohibido
- `alter_column_type_without_migration`: Cambiar el tipo de la columna `hosting_id` en producción sin migration versionada y sin backup puede causar pérdida de datos o corrupción de FK.
- `disable_pixel_events`: Deshabilitar el tracking de pixel events como workaround oculta el problema y elimina funcionalidad de analítica.

## Dashboard esperado
- **Terminate hosting**: `POST /admin/hostings/{id}/terminate` retorna 200/204.
- **Pixel events**: `GET /admin/hostings/{id}/pixel-events` retorna 200 con lista.
- **Error rate**: 0% en rutas de terminate y pixel-events.

## RAG usage
Recuperar con: `operator does not exist text integer hosting_id`, `pixel events 500 type mismatch`, `terminate hosting ProgrammingError`.
Contexto relevante: `app/models/pixel_event.py`, `app/api/admin/hostings.py`, migrations de `pixel_events`.

## Tests/Chaos
```python
# Test: terminate con hosting_id entero no lanza ProgrammingError
def test_terminate_hosting_type_safe(client, admin_auth_headers, test_hosting):
    response = client.post(
        f"/admin/hostings/{test_hosting.id}/terminate",
        headers=admin_auth_headers
    )
    assert response.status_code in (200, 204)

# Test: pixel events con ID numérico
def test_pixel_events_type_safe(client, admin_auth_headers, test_hosting):
    response = client.get(
        f"/admin/hostings/{test_hosting.id}/pixel-events",
        headers=admin_auth_headers
    )
    assert response.status_code == 200
```
