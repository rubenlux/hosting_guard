# Engineering Rules - Hosting Guard 🛡️

Este documento define las reglas de oro para mantener la integridad, seguridad y calidad del proyecto.

## 1. Calidad de Código y Tests
*   **Ningún PR sin tests**: Cada nueva funcionalidad o corrección debe incluir su test correspondiente (unitario, integración o E2E).
*   **Tests en Verde**: Main siempre debe estar en verde. El CI bloqueará cualquier cambio que rompa los tests actuales.
*   **Coverage Stricto**: Mantenemos un umbral de cobertura del **80% global**. El Core y el Decision Pipeline priorizan el 90%+.

## 2. Seguridad y Gobernanza
*   **El Core es Sagrado**: No se modifica la lógica de decisión sin un documento de especificación (spec) y validación técnica.
*   **IA de Asesoría, no Ejecución**: El LLM/IA solo explica y sugiere. Nunca decide por sí mismo ni ejecuta acciones sin intervención humana.
*   **Humano en el Loop**: Para acciones críticas, la última palabra siempre la tiene el humano (Approve/Reject).

## 3. Disponibilidad del Cliente
*   **Prudencia Ante Todo**: Si un diagnóstico es incierto (`unknown`), el sistema debe escalar a un humano en lugar de arriesgar la web del cliente.
*   **Ecommerce Prioritario**: Los proyectos de tipo `ecommerce` tienen las reglas de seguridad más restrictivas para evitar pérdida de facturación.

## 4. Arquitectura y Multitenancy
*   **Aislamiento Total**: El conocimiento de un cliente (RAG) nunca debe contaminar el de otro.
*   **Inmutabilidad de Auditoría**: Los logs de decisiones, acciones humanas y ejecuciones son *append-only* y nunca se borran.

---

*La confianza se construye con cada decisión segura.*
