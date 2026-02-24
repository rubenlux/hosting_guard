import json
import time

from fastapi.testclient import TestClient

from app.api.main import app
from app.api.tenancy import Tenant
from app.api.tenant_resolver import API_KEY_TO_TENANT
from app.core.rag.documents import KnowledgeDocument
from app.infra.config.repository import TenantConfigRepository

client = TestClient(app)

# 1. PREPARACIÓN DEL ESCENARIO
print("--- INICIANDO SIMULACION E2E FINAL: Hosting Guard v1 ---")

# Registramos una API Key válida para el simulacro
SIM_TENANT_ID = "shoes-store-plus"
SIM_API_KEY = "sk-sim-final-123"
API_KEY_TO_TENANT[SIM_API_KEY] = Tenant(tenant_id=SIM_TENANT_ID, name="Shoes Store Sim")

# Configuramos el conocimiento del Tenant (RAG)
from app.api.main import ai_orchestrator
from app.core.rag.tenant_in_memory_provider import TenantInMemoryKnowledgeProvider

docs = {
    SIM_TENANT_ID: [
        KnowledgeDocument(
            doc_id="doc_rollback",
            tags=["ecommerce", "rollback_deploy"],
            content="Para fallos de checkout en este tenant, la reversion a la version estable de las 22:00 es obligatoria.",
            metadata={"priority": "high"},
        )
    ]
}
ai_orchestrator.knowledge_provider = TenantInMemoryKnowledgeProvider(docs)

# Configuramos Reglas Versionadas para el Tenant
config_repo = TenantConfigRepository()
config_repo.create_new_version(
    tenant_id=SIM_TENANT_ID,
    kind="rules",
    content={"force_human_on_ecommerce": True, "strict_mode": True},
)

print(f"Escenario preparado para tenant: {SIM_TENANT_ID}")


# 2. DISPARO DEL INCIDENTE (Llamada a la API)
print("\n--- PASO 1: Deteccion y Diagnostico ---")
payload = {
    "hosting_type": "vps_managed",
    "project_type": "ecommerce",
    "symptoms": ["checkout_error", "payment_gateway_timeout"],
    "recent_changes": ["deploy", "database_migration"],
    "estimated_impact": "high",
}

import app.api.main as api_main
api_main.ENABLE_AI_ADVISORY = True

headers = {"X-API-Key": SIM_API_KEY}
response = client.post("/decision", json=payload, headers=headers)
decision = response.json()

print(f"STATUS: {decision['overall_status']}")
print(f"ADVISORY: {decision['advisory']['summary']}")
print(f"CONTEXTO RAG USADO: {decision['advisory']['context_used']}")
print(f"REQUIERE HUMANO: {decision['advisory']['requires_human_attention']}")

decision_id = decision["decision_id"]


# 3. ACCIÓN HUMANA (Aprobación)
print("\n--- PASO 2: Intervencion Humana (Approve) ---")
time.sleep(1)  # Simular tiempo de lectura del humano
action_payload = {
    "decision_id": decision_id,
    "action_type": "approve",
    "reason": "Confirmado fallo en pasarela tras deploy. Rollback necesario.",
}

response = client.post("/decision/action", json=action_payload, headers=headers)
print(f"ACCION REGISTRADA: {response.json()['status']}")


# 4. EJECUCIÓN SEGURA
print("\n--- PASO 3: Ejecucion de la Accion ---")

# Activamos el flag de ejecución solo para esta simulación
import app.api.main as api_main

api_main.ENABLE_ACTION_EXECUTION = True

# La acción sugerida fue rollback_deploy
action_to_execute = decision["actions_evaluation"][0]  # Tomamos la recomendada

execute_payload = action_to_execute

response = client.post("/decision/execute", json=execute_payload, headers=headers, params={"decision_id": decision_id})
print(f"RESULTADO DE EJECUCION: {response.json()['status']}")


# 5. VERIFICACIÓN DE AUDITORÍA
print("\n--- PASO 4: Verificacion de Auditoria (Append-only) ---")
from app.infra.audit.sqlite import get_connection

conn = get_connection()
cur = conn.cursor()

print(f"\nBuscando decision_id: {decision_id}")

print("\nEventos en base de datos:")
# Decisión
cur.execute("SELECT tenant_id, overall_status FROM decision_events WHERE decision_id = ?", (decision_id,))
row = cur.fetchone()
if row:
    print(f"- [Decision] Tenant: {row['tenant_id']} | Status: {row['overall_status']}")
else:
    print("- [Decision] ERROR: No se encontro el evento de decision.")

# Acción Humana
cur.execute("SELECT action_type, actor, reason FROM human_action_events WHERE decision_id = ?", (decision_id,))
row = cur.fetchone()
if row:
    print(f"- [Human] Accion: {row['action_type']} | Actor: {row['actor']} | Motivo: {row['reason']}")
else:
    print("- [Human] ERROR: No se encontro el evento humano.")

# Ejecución
cur.execute("SELECT status FROM execution_events WHERE decision_id = ?", (decision_id,))
row = cur.fetchone()
if row:
    print(f"- [Execution] Resultado Final: {row['status']}")
else:
    print("- [Execution] ERROR: No se encontro el evento de ejecucion.")

conn.close()

# 6. MÉTRICAS
print("\n--- PASO 5: Telemetria ---")
metrics_resp = client.get("/metrics")
# Buscamos nuestra métrica en el chorro de texto de Prometheus
if "decisions_total" in metrics_resp.text:
    print("Métricas generadas correctamente en el endpoint /metrics")

print("\n--- SIMULACION COMPLETADA CON EXITO ---")
print("Hosting Guard v1: Detectado -> Explicado -> Aprobado -> Ejecutado -> Auditado.")
