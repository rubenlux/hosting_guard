# RB-WP-001: Error 500 en WordPress tras Cambios (MEDIUM) 📝⚠️

## 🧾 Identificador y Nivel
*   **ID**: RB-WP-001
*   **Severidad**: MEDIUM
*   **Tipo de Proyecto**: WordPress (Shared / VPS)

## 1. Disparador
*   `symptoms` incluye `error_500`
*   `recent_changes` incluye `plugin_update` o `theme_change`

## 2. Evaluación Automática (IA)
*   Diagnóstico: `plugin_incompatibility` o `theme_conflict`.
*   Propuesta: `disable_plugin` o `rollback_plugin`.
*   IA Advisory: Explicar por qué la actualización causó el fallo.

## 3. Punto de Control Humano
*   [ ] Verificar carpeta `wp-content/plugins` para identificar el plugin ofensivo.
*   [ ] Revisar `error_log` de Apache/Nginx para errores de PHP Fatal Error.
*   [ ] Si el sitio es crítico, habilitar `WP_DEBUG` temporalmente.

## 4. Acciones Permitidas
*   ✅ `disable_plugin` (renombrar carpeta o vía WP-CLI)
*   ✅ `clear_cache` (W3 Total Cache, Rocket, etc.)
*   ✅ `restart_service` (PHP-FPM)

## 5. Acciones Prohibidas
*   ❌ **NO** desactivar todos los plugins a la vez (pérdida de configuración).
*   ❌ **NO** actualizar la versión de PHP sin probar antes.
*   ❌ **NO** modificar `wp-config.php` sin backup.

## 6. Comunicación al Cliente
"Su sitio muestra un error interno que parece haber sido causado por la reciente actualización de un plugin. Estamos procediendo a desactivar el componente en conflicto para restaurar el acceso. Le informaremos cuál es el plugin afectado en breve."

## 7. Criterio de Cierre
*   [ ] Homepage carga correctamente.
*   [ ] Escritorio de WordPress (/wp-admin) accesible.
*   [ ] Plugin conflictivo identificado y comunicado.
