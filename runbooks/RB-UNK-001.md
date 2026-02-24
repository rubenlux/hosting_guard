# RB-UNK-001: Diagnóstico Incierto (UNKNOWN) 🔍🧐

## 🧾 Identificador y Nivel
*   **ID**: RB-UNK-001
*   **Severidad**: variable (depende del síntoma)
*   **Principio**: "UNKNOWN no es error, es prudencia."

## 1. Disparador
*   `overall_status` = `unknown`
*   El sistema no encuentra patrones de fallo de alta confianza.

## 2. Evaluación Automática (IA)
*   El Advisory debe admitir incertidumbre.
*   No sugerir acciones automáticas.
*   Recomendar explícitamente "Revisión Humana Requerida".

## 3. Procedimiento Operativo (Humano)
1.  **Investigación manual**: Acceder vía SSH/SFTP y revisar logs del sistema (`/var/log/...`).
2.  **Triaje**: Determinar si el impacto es mayor de lo reportado.
3.  **Documentación**: Anotar por qué el sistema no pudo identificar la causa.

## 4. Acciones Permitidas
*   ⚠️ Solo acciones manuales de diagnóstico (lectura de logs, `top`, `df -h`).
*   ✅ Cualquier acción que el técnico senior determine tras la investigación.

## 5. Acciones Prohibidas
*   ❌ **PROHIBIDO** ejecutar acciones sugeridas por la IA si el estado es UNKNOWN.
*   ❌ **PROHIBIDO** automatizar la resolución de este caso sin feedback previo.

## 6. Feedback para el Sistema
*   Si se descubre una nueva causa, documentar para:
    *   [ ] Crear una nueva regla en el `DecisionPipeline`.
    *   [ ] Añadir un documento al RAG del tenant.

## 7. Criterio de Cierre
*   [ ] Causa raíz identificada manualmente.
*   [ ] Incidencia resuelta.
*   [ ] Lección aprendida registrada en el sistema de gobernanza.
