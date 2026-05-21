# Free Trial Limits & AI Usage Quotas

## Free trial limits

| Constant | Value | Location |
|---|---|---|
| `MAX_FREE_USERS` | 10 | `app/api/routes/hosting.py` |
| `FREE_PLAN_DAYS` | 14 | `app/services/expiration_job.py` |
| `PLANS["free"]["days"]` | 14 | `app/api/routes/hosting.py` |

`MAX_FREE_USERS` is a soft cap enforced at provisioning time: once 10 free-plan hostings are active, new free registrations are rejected. The expiration job (`check_and_expire_free_hostings`) transitions hostings through `active → expiring → expired → deleted` over the 14-day window.

IP and prior-use checks (`has_free_plan_from_ip`, `had_free_hosting_recently`) prevent circumvention by re-registration.

## AI quota system

### Constants

| Constant | Value | File |
|---|---|---|
| `_FREE_TRIAL_TOTAL` | 10 queries (all-time) | `app/services/ai_quota_service.py` |
| `_FREE_DAILY_LIMIT` | 3 queries/day | `app/services/ai_quota_service.py` |
| Per-plan monthly limits | see `plan_economics` table | DB |

### Per-plan monthly limits (from `plan_economics.included_ai_queries_month`)

| Plan | Monthly limit |
|---|---|
| free | 0 (governed by trial limits above) |
| personal | 20 |
| negocio | 100 |
| agencia | 300 |
| agencia_pro | 700 |
| enterprise_annual / enterprise_monthly | 1500 |

### Database table: `ai_usage_events`

```sql
CREATE TABLE ai_usage_events (
    id         BIGSERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    plan       TEXT NOT NULL,
    feature    TEXT NOT NULL,
    units      INTEGER NOT NULL DEFAULT 1,
    metadata   JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Indexes: `(user_id, feature, created_at DESC)`, `(user_id, created_at DESC)`, `(plan, feature, created_at DESC)`.

### Service: `app/services/ai_quota_service.py`

| Function | Purpose |
|---|---|
| `check_ai_quota(user_id, feature, plan)` | Raises HTTP 429 with `code: ai_quota_exceeded` if exceeded |
| `record_ai_usage(user_id, feature, plan, units, metadata)` | Inserts one row; call ONLY after a successful AI response |
| `get_ai_usage_summary(...)` | Admin aggregation query with filters |
| `get_user_ai_quota_status(user_id, feature, plan)` | Per-user status for dashboard display |

### Integration points

**`app/api/routes/support_chat.py`**

- `create_ticket()`: `check_ai_quota` called before `generate_support_response`; `record_ai_usage` called after.
- `_ai_followup_reply()`: same pattern; quota failure is caught silently (no AI reply, human agent can respond).

### HTTP 429 response shape

```json
{
  "detail": {
    "detail": "Has alcanzado el límite diario de consultas IA.",
    "code": "ai_quota_exceeded",
    "limit": 3,
    "used": 3,
    "reset_at": "2026-05-22T00:00:00+00:00"
  }
}
```

`reset_at` is `null` for the all-time free trial cap.

### Admin visibility

`GET /admin/ai-usage` — requires admin role.

Query params: `user_id`, `feature`, `plan`, `days` (default 30), `limit`, `offset`.

Returns: aggregated rows grouped by `(user_id, plan, feature)` + `total_users` count.

## Validation

```bash
bash scripts/security/validate_free_trial_limits.sh
```

All 16 checks must pass.
