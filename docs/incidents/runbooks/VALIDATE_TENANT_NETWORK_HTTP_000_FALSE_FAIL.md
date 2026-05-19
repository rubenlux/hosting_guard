---
incident_id: VALIDATE_TENANT_NETWORK_HTTP_000_FALSE_FAIL
incident_type: validation_script
severity: medium
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - validate_tenant_network_isolation
forbidden_actions: []
signatures:
  - "returned 000000"
  - "HTTP reachable returned 000000"
  - "false positive HTTP reachable"
---

# VALIDATE_TENANT_NETWORK_HTTP_000_FALSE_FAIL

`validate_tenant_network_isolation.sh` emits a false FAIL with code `000000`
for HTTP probes of correctly blocked services.

**Full runbook**: `docs/knowledge/incidents/VALIDATE_TENANT_NETWORK_HTTP_000_FALSE_FAIL.md`

## Síntoma

```
[FAIL] HTTP reachable: hosting_guard:8000 returned 000000
```

The code `000000` (six zeros) is impossible as an HTTP status code. DNS and TCP probes
for the same service correctly show PASS. This is a script bug, not a real isolation breach.

## Causa raíz

`|| echo 000` inside the `sh -c` string appended an extra `000` after curl already
printed `000` via `-w '%{http_code}'` when the connection failed. The old check
`[[ "$code" != "000" ]]` treated `000000` as a real HTTP response.

## How to distinguish from a real breach

| DNS probe | TCP probe | HTTP code | Verdict |
|---|---|---|---|
| PASS (no resolve) | PASS (closed) | `000000` | Script bug — not a breach |
| FAIL (resolved) | FAIL (open) | `200`/`403` | Real breach — escalate |

## Fix applied

Commit `6749177` — capture curl exit code via `; printf ':%d' $?`. FAIL only if
`http_code != "000"` AND `curl_exit == "0"`.

## Revalidar

```bash
# Confirm fix is present
grep "printf ':%d'" scripts/security/validate_tenant_network_isolation.sh

# Run corrected validation
sudo ./scripts/security/validate_tenant_network_isolation.sh <CONTAINER_NAME>
# Blocked services should show:
# [PASS] HTTP blocked: hosting_guard:8000 returned 000 (curl exit=6)
```

## Si el servidor todavía muestra el bug

```bash
# Pull the fix
git pull
# Then re-run validation
sudo ./scripts/security/validate_tenant_network_isolation.sh <CONTAINER_NAME>
```
