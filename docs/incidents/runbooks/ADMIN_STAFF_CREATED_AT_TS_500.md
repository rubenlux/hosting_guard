---
incident_id: ADMIN_STAFF_CREATED_AT_TS_500
incident_type: database_query_error
severity: medium
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions: []
forbidden_actions:
  - alter_table_add_column_without_migration
  - drop_column_without_backup
signatures:
  - "column created_at_ts does not exist"
  - "ProgrammingError: column"
---

# ADMIN_STAFF_CREATED_AT_TS_500

## Síntoma
El endpoint `GET /admin/staff` retorna HTTP 500. En los logs de la aplicación se ve `ProgrammingError: column "created_at_ts" does not exist`. La sección de gestión de personal del panel de administración está completamente caída.

## Impacto
- Todos los administradores pierden acceso a la lista de staff desde el panel.
- No se pueden crear, listar ni gestionar usuarios de staff hasta que se corrija.
- No afecta a clientes finales ni a sus hostings.
- No hay pérdida de datos; el error es exclusivamente en la consulta.

## Evidencia
```
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn)
column "created_at_ts" does not exist
LINE 1: SELECT staff.id, staff.email, staff.created_at_ts FROM staff
                                               ^
HINT: Perhaps you meant to reference the column "staff.created_at".
```

```bash
docker compose logs app | grep "created_at_ts"
```

## Causa raíz
El modelo ORM de `Staff` o una query raw SQL referencia `created_at_ts` pero la columna real en la tabla `staff` de PostgreSQL se llama `created_at` (tipo `timestamp`). El nombre incorrecto fue introducido por:

1. Un typo en el modelo SQLAlchemy (`Column(DateTime, name="created_at_ts")` en lugar de `"created_at"`), o
2. Una query raw que usa el nombre incorrecto directamente, o
3. Un schema Pydantic que serializa con alias `created_at_ts` y lo propaga a la query.

La columna nunca existió con ese nombre en ninguna migración.

## Diagnósticos equivocados
- **"Falta una migration"**: No falta ninguna migration. La columna correcta (`created_at`) ya existe. No hay que añadir `created_at_ts`.
- **"Error de permisos en PostgreSQL"**: Es un error de nombre de columna, no de permisos.
- **"La tabla staff no existe"**: La tabla existe; solo el nombre de columna en la query es incorrecto.

## Diagnóstico rápido
```bash
# 1. Confirmar el error en logs
docker compose logs app --tail=100 | grep "created_at_ts\|ProgrammingError"

# 2. Verificar columnas reales de la tabla staff en PostgreSQL
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
result = db.execute(text(\"SELECT column_name, data_type FROM information_schema.columns WHERE table_name='staff' ORDER BY ordinal_position\"))
for row in result: print(row)
"

# 3. Buscar todas las referencias a created_at_ts en el código
grep -rn "created_at_ts" app/

# 4. Verificar el modelo ORM de Staff
grep -n "created_at" app/models/staff.py
```

## Solución manual
```bash
# 1. Localizar todas las referencias al nombre incorrecto
grep -rn "created_at_ts" app/

# 2. Para cada archivo encontrado, cambiar created_at_ts → created_at
# Ejemplo en app/models/staff.py:
#   created_at_ts = Column(DateTime)  →  created_at = Column(DateTime)
# Ejemplo en query raw:
#   "SELECT created_at_ts FROM staff"  →  "SELECT created_at FROM staff"

# 3. Si hay schema Pydantic con alias:
#   created_at_ts: datetime = Field(alias="created_at")
#   →  created_at: datetime

# 4. Rebuild y restart
docker compose up -d --build app

# 5. Verificar
curl -s -o /dev/null -w "%{http_code}" https://admin.hostingguard.example/admin/staff \
  -H "Cookie: access_token=<admin_token>"
# Debe retornar 200
```

## Fix permanente
1. Añadir test de integración que llame a `GET /admin/staff` y verifique respuesta 200.
2. Ejecutar `mypy .` y `ruff check .` en CI para detectar inconsistencias de nombres de campo.
3. Documentar en `app/models/staff.py` el nombre exacto de cada columna con un comentario si difiere del atributo Python.
4. Considerar añadir `__table_args__` con check constraints para validar que el schema ORM coincide con la DB en startup.

## Señales para detección automática
- Log pattern: `column "created_at_ts" does not exist`
- Log pattern: `ProgrammingError.*column.*does not exist`
- HTTP 500 en `GET /admin/staff` con cuerpo que contiene `created_at_ts`
- Alerta de tasa de error 100% en ruta `/admin/staff`

## Auto-remediation permitido
Ninguna. El fix requiere corrección de código y redeploy.

## Auto-remediation prohibido
- `alter_table_add_column_without_migration`: Añadir la columna `created_at_ts` a la tabla como workaround está estrictamente prohibido. Crea deuda de schema, duplica datos y requiere una migration real igualmente.
- `drop_column_without_backup`: Nunca modificar el schema de `staff` sin migration versionada y backup previo.

## Dashboard esperado
- **Admin staff endpoint**: `GET /admin/staff` retorna 200 con lista de staff.
- **Error rate**: 0% en rutas `/admin/staff`.
- **PostgreSQL logs**: sin errores de `UndefinedColumn` para la tabla `staff`.

## RAG usage
Recuperar con: `created_at_ts staff 500`, `ProgrammingError column does not exist staff`, `admin staff endpoint crash`.
Contexto relevante: `app/models/staff.py`, `app/api/admin/staff.py` o equivalente, schema Pydantic de Staff.

## Tests/Chaos
```python
# Test: GET /admin/staff devuelve 200
def test_admin_staff_list(client, admin_auth_headers):
    response = client.get("/admin/staff", headers=admin_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Verificar que los campos esperados están presentes
    if data:
        assert "created_at" in data[0]
        assert "created_at_ts" not in data[0]  # el alias incorrecto no debe aparecer
```
