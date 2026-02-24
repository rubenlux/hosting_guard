from prometheus_client import Counter, Histogram

# Volumen y Negocio
DECISIONS_TOTAL = Counter(
    "decisions_total",
    "Total de decisiones procesadas",
    ["tenant_id", "project_type"],
)

# Estados y Resultados
DECISIONS_BY_STATUS = Counter(
    "decisions_by_status",
    "Decisiones por estado final",
    ["tenant_id", "overall_status"],
)

# Interacción Humana
HUMAN_ACTIONS_TOTAL = Counter(
    "human_actions_total",
    "Acciones humanas registradas",
    ["tenant_id", "action_type"],
)

# Perfomance / UX
DECISION_LATENCY = Histogram(
    "decision_latency_seconds",
    "Latencia end-to-end del endpoint /decision",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, float("inf")],
)
