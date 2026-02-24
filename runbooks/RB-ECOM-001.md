# RB-ECOM-001: Ecommerce Checkout Caído (CRÍTICO) 🛒🚨

## 🧾 Identificador y Nivel
*   **ID**: RB-ECOM-001
*   **Severidad**: CRITICAL
*   **Tipo de Proyecto**: Ecommerce (PrestaShop, WooCommerce, Magento)

## 1. Disparador
*   `symptoms` incluye `checkout_error`
*   `recent_changes` incluye `deploy`
*   `estimated_impact` = `high`

## 2. Evaluación Automática (IA)
El sistema debe:
*   Clasificar el estado como `requires_human` o `blocked`.
*   **NUNCA** permitir `ready_for_execution` automático.
*   Generar Advisory con contexto RAG sobre despliegues fallidos.
*   Sugerir `rollback_deploy` como prioridad #1.

## 3. Punto de Control Humano (OBLIGATORIO)
Antes de actuar, el técnico debe confirmar:
*   [ ] ¿Existe un snapshot o punto de restauración válido?
*   [ ] ¿La base de datos ha sufrido cambios de esquema que impidan el rollback?
*   [ ] ¿Se ha verificado la pasarela de pagos externa (Stripe/PayPal)?
*   [ ] **Acción**: Registrar `approve` o `reject` en el endpoint de auditoría humana.

## 4. Acciones Permitidas
*   ✅ `rollback_deploy`
*   ✅ `restart_service` (Nginx/PHP-FPM/MySQL)
*   ✅ `clear_cache`

## 5. Acciones Prohibidas
*   ❌ **NO** ejecutar migraciones de DB manuales en caliente.
*   ❌ **NO** borrar carpetas `/vendor` o archivos de configuración.
*   ❌ **NO** editar código directamente en producción sin clonar.
*   ❌ **NO** ejecutar múltiples acciones concurrentes.

## 6. Comunicación al Cliente (Plantilla)
"Detectamos un problema en el proceso de pago tras un cambio reciente. Estamos priorizando la continuidad de ventas y aplicando una reversión segura. Te mantenemos informado en todo momento."
*   *Nota*: No culpar al cliente ni usar tecnicismos complejos.

## 7. Criterio de Cierre
*   [ ] El proceso de checkout funciona (test manual).
*   [ ] Se confirma una nueva orden en el dashboard.
*   [ ] Logs de error (5XX) han desaparecido por >15 min.
*   [ ] Evento de auditoría de cierre registrado.

## 8. Auditoría Obligatoria
*   Verificar que existan: `decision_event`, `human_action_event`, y `execution_event`.
