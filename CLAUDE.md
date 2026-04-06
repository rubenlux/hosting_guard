# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Hosting Guard

A SaaS platform for managed web hosting. Each client gets an isolated Docker container. The backend runs persistently to handle billing, autoscaling, resource throttling, and container lifecycle management. The AI layer advises but never executes autonomously — a human must always approve critical actions.

## Commands

### Backend (Python/FastAPI)
```bash
# Run tests
pytest

# Run a single test file
pytest tests/test_decision_pipeline.py

# Run a single test
pytest tests/test_decision_pipeline.py::test_name

# Lint
ruff check .

# Type check
mypy .
```

### Frontend (React/Vite)
```bash
cd frontend

# Dev server
npm run dev

# Build for production
npm run build
```

### Docker (Production)
```bash
# Start all services
docker compose up -d

# Rebuild and restart the app
docker compose up -d --build app

# View app logs
docker compose logs -f app
```

## Architecture

### Service topology (`docker-compose.yml`)
- **Traefik** — reverse proxy + TLS. Routes `api.hostingguard.lat` → backend, `hostingguard.lat` → frontend.
- **docker-socket-proxy** — the only service that touches `/var/run/docker.sock`. Neither Traefik nor the app mount the socket directly; they go through `tcp://docker-socket-proxy:2375`.
- **app** — FastAPI backend on port 8000.
- **frontend** — React (Vite) built to static files, served by Nginx.
- **postgres** — Primary relational database (PostgreSQL 15). Configured via `DATABASE_URL` env var.
- **redis** — Token revocation store + AI cache.
- **prometheus** — Internal metrics, only exposed on `127.0.0.1:9090`.

### Backend (`app/`)
```
app/
  api/           # FastAPI application — routes, auth, middleware, config
    main.py      # App entry point; registers routers & background schedulers
    routes/      # hosting.py (user-facing), admin.py, pixel.py
    config.py    # Feature flags: ENABLE_AI_ADVISORY, ENABLE_ACTION_EXECUTION, APP_ENV
    security.py  # JWT creation/verification, token revocation via Redis
  core/          # Business logic — THE SACRED CORE (do not change without a spec)
    decision_pipeline.py      # Orchestrates: diagnose → classify actions → return decision
    diagnostic_engine.py      # Rule-based symptom → diagnosis mapping
    action_safety_classifier.py
    ai_orchestrator.py        # Enriches decisions with AI advisory (optional, feature-flagged)
    execution/                # BaseExecutor interface + concrete executors (restart, cache clear, git)
    llm/                      # LLM factory + RuleBasedFakeLLM for testing
    rag/                      # Per-tenant in-memory knowledge provider
  services/      # Background schedulers (run as asyncio tasks from lifespan)
    orchestrator.py       # Infinite loop: reads docker stats, applies throttle/autoscale
    expiration_job.py     # Every 12h: suspends free-tier containers older than 14 days
    health_checker.py     # Every 5min: health checks all hosting containers
    traffic_collector.py  # Every 5min: collects nginx traffic metrics
  infra/
    db.py                 # DB abstraction layer: SQLite (default) or PostgreSQL (via DATABASE_URL)
    audit/                # Append-only repositories: decisions, human actions, executions, hosting, users
```

### Database
- Backend selects SQLite or PostgreSQL based on `DATABASE_URL`. If `DATABASE_URL` starts with `postgresql://`, it uses PostgreSQL with a thread-local connection pool. Otherwise falls back to SQLite.
- `infra/db.py` provides a unified cursor adapter (`_AdaptedCursor`) that translates `?` → `%s` for PostgreSQL and handles `lastrowid` differences.
- All audit tables are **append-only** — never delete records.

### Auth flow
- Cookie-based JWT: `access_token` (15min, `path=/`) + `refresh_token` (7 days, `path=/refresh`).
- Revocation tracked in Redis by `jti` claim.
- Refresh tokens are rotated on use — old `jti` is revoked before a new token is issued.
- Role is always read from the DB at `/me` time, not from the JWT, so role changes take effect immediately.

### Frontend (`frontend/src/`)
- React 18 + React Router v7 + Tailwind CSS + Framer Motion.
- `services/` — Axios API client wrappers.
- `hooks/` — Custom React hooks.
- `pages/` — Route-level components (Dashboard, etc.).

## Feature Flags

| Env var | Default | Effect |
|---|---|---|
| `ENABLE_AI_ADVISORY` | `false` | Enriches decisions with LLM advisory |
| `ENABLE_ACTION_EXECUTION` | `false` | Allows `/decision/execute` to actually run executors |
| `APP_ENV` | `development` | Controls cookie security flags and logging |

## Key Engineering Constraints

- **The Core is Sacred**: `app/core/` decision logic requires a written spec and technical validation before modification.
- **AI is advisory only**: The LLM never executes actions autonomously. `/decision/execute` requires `requires_human_approval: true` on the action.
- **Ecommerce projects** have the most restrictive safety rules — rollback is the default action if a diagnosis takes more than 5 minutes.
- **Audit logs are immutable**: All repositories in `infra/audit/` are append-only.
- **Test coverage**: 80% global minimum; `core/` and `decision_pipeline` target 90%+.

## Test Layout

Tests live in `tests/`. Key test files map directly to modules:
- `test_decision_pipeline.py`, `test_diagnostic_engine.py` — core logic
- `test_api_decision.py`, `test_api_security.py` — API layer
- `test_e2e_ecommerce.py`, `test_decision_flow_integration.py` — integration/E2E
- `test_rag_tenant_isolation.py` — verifies RAG knowledge never leaks between tenants
- `conftest.py` — shared fixtures

`pytest.ini` config is in `pyproject.toml`. `pythonpath = ["."]` means imports are relative to the repo root.
