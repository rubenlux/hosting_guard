# 🚀 Registro de Migración: De Arquitectura Híbrida a PostgreSQL Nativo

Este documento registra el proceso de refactorización integral realizado en el sistema **Hosting Guard** para eliminar la dependencia de SQLite y consolidar una infraestructura de persistencia pura en **PostgreSQL**.

## 1. Diagnóstico Inicial: La Deuda Técnica
Antes de la migración, el sistema operaba en un estado "híbrido" que era insostenible para un entorno de producción escalable:

*   **Doble Adaptador**: Existía un archivo `app/infra/audit/sqlite.py` que actuaba como proxy, intentando traducir consultas entre SQLite y Postgres en tiempo real.
*   **Inconsistencia de Sintaxis**: Los repositorios usaban placeholders mixtos (`?` de SQLite y `%s` de Postgres), lo que causaba errores en tiempo de ejecución según el backend.
*   **Dependencia en Analytics**: El módulo de `PixelRepository` estaba 100% hardcodeado a archivos `.sqlite`, ignorando la base de datos central.
*   **Lógica de Fechas Incompatible**: Se utilizaban funciones como `DATE()` o `strftime()` que tienen comportamientos distintos en ambos motores.
*   **Código Muerto**: Existía una carpeta `app/repositories/` con una implementación antigua y duplicada que generaba confusión en las importaciones.

---

## 2. Estrategia de Refactorización (Safe-Mode)
La migración se ejecutó en dos fases quirúrgicas para evitar downtime y roturas en la lógica de negocio:

### Fase 1: Estandarización de Sintaxis
1.  **Placeholders**: Se reemplazaron todos los `?` por `%s` en los más de 12 repositorios del sistema.
2.  **Atomicidad**: Se eliminó la dependencia de `cursor.lastrowid` (SQLite) y se implementó la cláusula `RETURNING id` nativa de PostgreSQL para obtener IDs de forma segura y atómica.
3.  **JSONB**: Las consultas de Analytics pasaron de `json_extract(properties, '$.time_on_page')` a la sintaxis nativa de Postgres: `(properties->>'time_on_page')::float`.

### Fase 2: Consolidación de Infraestructura
1.  **Capa de Datos Única**: Se eliminó el "backend switch" de `app/infra/db.py`, dejando a PostgreSQL como el único motor soportado.
2.  **Migraciones Centralizadas**: Se creó `app/infra/migrations.py` como el punto único de verdad. Todas las tablas (incluyendo Pixel Analytics y configuraciones de Tenant) se declaran e inicializan aquí de forma idempotente.
3.  **Lifespan Injection**: Se integró la llamada `init_db()` en el evento `lifespan` de FastAPI (`app/api/main.py`), garantizando que la base de datos esté lista antes de aceptar la primera petición.

---

## 3. Resumen de Cambios por Módulo

| Módulo | Antes | Después |
| :--- | :--- | :--- |
| **Repositorios Audit** | Lógica híbrida, imports de `sqlite.py` | PostgreSQL Puro, imports directos de `db.py` |
| **Pixel Analytics** | Archivo `.sqlite` local | Tablas `pixel_sites` y `pixel_events` en Postgres |
| **Conexiones** | Proxy `sqlite.py` (detección dinámica) | Adaptador directo con Pool en `db.py` |
| **Esquema** | Disperso en archivos `init()` manuales | Centralizado en `app/infra/migrations.py` |
| **Tipos de Datos** | `TEXT` para fechas | `TIMESTAMPTZ` para precisión temporal |

---

## 4. Limpieza y Desmantelamiento (Technical Debt Removal)
Para dejar el sistema en un estado profesional, se eliminaron los siguientes componentes obsoletos:
*   🗑️ `app/infra/audit/sqlite.py` (ELIMINADO)
*   🗑️ `app/infra/config/sqlite.py` (ELIMINADO)
*   🗑️ Carpeta `app/repositories/` (ELIMINADA completamente)
*   🗑️ Lógica de `if BACKEND == "sqlite"` en servicios background.

---

## 5. Estado Final de la Arquitectura
El sistema ahora sigue un patrón **Repository-Adapter-Migration** limpio:
1.  **Migrations**: Definen el qué (esquema).
2.  **DB Adapter**: Define el cómo (conexión/pool).
3.  **Repositories**: Ejecutan el para qué (lógica de datos).

**Próximos Pasos Recomendados:**
*   Asegurar que la variable `DATABASE_URL` sea la única fuente de configuración en producción.
*   Monitorizar el uso del pool si el tráfico aumenta drásticamente (configurado actualmente para 5-20 conexiones).
*   Utilizar exclusivamente `migrations.py` para cualquier cambio de esquema futuro.

---
**Fecha de finalización:** 8 de Abril, 2026
**Responsable:** Antigravity AI
**Estado:** 🟢 PRODUCCIÓN READY
