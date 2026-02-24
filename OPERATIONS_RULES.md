# Operations Rules - Hosting Guard 🛠️🛡️

Estas reglas definen el comportamiento esperado del equipo operativo ante cualquier incidente gestionado por el sistema.

## 1. Fidelidad al Runbook
*   **Ninguna acción sin Runbook**: Si no existe un runbook para la situación actual, se debe tratar como un caso `UNKNOWN` y escalar a un técnico senior.
*   **Checklist Obligatorio**: Los puntos de control humano de los runbooks no son opcionales. Deben verificarse antes de cualquier clic en "Aprobar".

## 2. Gobernanza de la IA
*   **La IA es un asesor**: La IA propone, pero el humano es el responsable legal y técnico de la ejecución.
*   **Validación de Advisory**: Si la explicación de la IA parece incoherente o contradictoria con los hechos técnicos, se debe ignorar y usar el diagnóstico base del core.

## 3. Prioridad de Negocio
*   **Ecommerce es sagrado**: En picos de tráfico o errores de checkout, la prioridad absoluta es restaurar la facturación. El rollback es la acción por defecto si el diagnóstico tarda más de 5 minutos.
*   **Sitios en Producción**: Nunca se realizan pruebas directamente en producción. Usa entornos de staging si el runbook lo indica.

## 4. Trazabilidad
*   **Todo queda auditado**: No se realizan cambios "por fuera" del sistema sin registrar el motivo en la auditoría humana.
*   **Cierre de Ciclo**: Cada incidencia debe cerrarse con un resultado claro (Success/Fail) y un comentario que ayude a mejorar el sistema.

---
*Operamos con la calma de quien tiene el control total.*
