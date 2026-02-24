# Guía de Onboarding del Primer Cliente - Hosting Guard 🛡️🚀

Esta guía detalla el proceso paso a paso para dar de alta a un cliente real de forma segura y profesional.

---

## 🧱 FASE 0: Pre-onboarding (Verificación de Salud)
*Antes de contactar al cliente, asegura que el sistema está blindado.*

- [ ] **CI/CD en Verde**: Todos los tests automáticos (47/47) pasan en la rama `main`.
- [ ] **Feature Flags verificadas**: 
    - `ENABLE_ACTION_EXECUTION=false` (Ejecución desactivada por defecto).
    - `ENABLE_AI_ADVISORY=true` (Asesoría activada).
- [ ] **Audit DB inicializada**: Las tablas de auditoría están listas para recibir eventos.
- [ ] **Métricas activas**: El endpoint `/metrics` reporta actividad.

---

## 🧩 FASE 1: Alta Técnica (El Tenant)
*Configuración inicial en el sistema de gobernanza.*

1. **Crear Tenant**: Ejecutar script o endpoint `/tenant/config` para el cliente (ej. `tienda-deportes-pro`).
2. **Asignar Reglas Base**:
    ```json
    {
      "tenant_id": "tienda-deportes-pro",
      "kind": "rules",
      "content": {
        "force_human_on_ecommerce": true,
        "allow_execution": false,
        "max_risk_level": "medium"
      }
    }
    ```
3. **Configurar Tono de IA**:
    ```json
    {
      "tenant_id": "tienda-deportes-pro",
      "kind": "prompt",
      "content": {
        "tone": "conservador",
        "detail_level": "alto",
        "language": "es-ES"
      }
    }
    ```
4. **API Key**: Generar y entregar de forma privada al equipo técnico del cliente.

---

## 🧪 FASE 2: Modo Observación (Días 1 a 3)
*El sistema escucha pero no interviene.*

- **Objetivo**: Validar que los síntomas detectados coincidan con la realidad del cliente.
- **Actividad**: Revisar diariamente el log de auditoría (`decision_events`).
- **Check**: ¿Se están generando falsos positivos? ¿El Advisory es útil?

---

## 🧾 FASE 3: Simulación de Confianza
*Demostración controlada del valor del sistema.*

1. Realizar una acción de bajo riesgo (ej. limpiar caché o actualizar un plugin menor en staging).
2. Mostrar al cliente el **Advisory enriquecido**:
   - "Detectamos una actualización de plugin. El riesgo es bajo pero monitorizamos la carga del servidor."
3. **Hito**: El cliente ve que el sistema entiende el contexto de su negocio.

---

## 🔒 FASE 4: Activación de Runbooks
*Definir la hoja de ruta operativa.*

- Presentar al cliente los runbooks aplicables a su sitio:
    - [ ] `RB-ECOM-001` si es ecommerce.
    - [ ] `RB-WP-001` si es WordPress.
- **Acuerdo**: Confirmar quién es el contacto humano de emergencia para las aprobaciones.

---

## 📒 FASE 5: Cierre de Onboarding
*Transición a servicio activo.*

- **Entregable**: Documento `OPERATIONS_RULES.md` firmado/aceptado.
- **Estado Técnico**: Cliente en modo "Protegido".
- **Mensaje Final**: "Ya conocemos tu sistema. Si pasa algo, sabremos como actuar con prudencia."

---

*Hosting Guard: Tranquilidad técnica a escala.*
