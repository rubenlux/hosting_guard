from prometheus_client import Counter, Histogram

# ---------------------------------------------------------------------------
# Business / domain metrics
# ---------------------------------------------------------------------------

DECISIONS_TOTAL = Counter(
    "decisions_total",
    "Total de decisiones procesadas",
    ["tenant_id", "project_type"],
)

DECISIONS_BY_STATUS = Counter(
    "decisions_by_status",
    "Decisiones por estado final",
    ["tenant_id", "overall_status"],
)

HUMAN_ACTIONS_TOTAL = Counter(
    "human_actions_total",
    "Acciones humanas registradas",
    ["tenant_id", "action_type"],
)

# Kept for backward compat — use HTTP_REQUEST_LATENCY for p95/p99
DECISION_LATENCY = Histogram(
    "decision_latency_seconds",
    "Latencia end-to-end del endpoint /decision",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# ---------------------------------------------------------------------------
# HTTP infrastructure metrics — p95 / p99 per endpoint
# ---------------------------------------------------------------------------
# Buckets tuned for a hosting SaaS: most reads < 200ms, Docker ops < 10s
_HTTP_BUCKETS = (0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf"))

HTTP_REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds",
    "HTTP request latency broken down by method, path template, and status code",
    ["method", "path", "status_code"],
    buckets=_HTTP_BUCKETS,
)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

HTTP_REQUESTS_IN_FLIGHT = Counter(
    "http_errors_total",
    "HTTP 4xx/5xx responses total",
    ["method", "path", "status_code"],
)
