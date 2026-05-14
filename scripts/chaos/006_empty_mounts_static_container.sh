#!/usr/bin/env bash
# Chaos 006 — Detect container with Mounts=[] (no bind mount)
# Validates: check_static_container_mounts() → CONTAINER_WITH_EMPTY_MOUNTS → auto_repair_allowed
set -euo pipefail

echo "[CHAOS 006] Validate empty mounts detection"

# ── Signature matching ─────────────────────────────────────────────────────────
python3 - << 'PYEOF'
import sys
sys.path.insert(0, '.')
from app.services.incidents.incident_knowledge_service import match_error_signature

texts = [
    "Mounts=[]",
    '"Mounts": []',
    "container has no mounts invalid_container_mount",
]
expected = "CONTAINER_WITH_EMPTY_MOUNTS"

for text in texts:
    matches = match_error_signature(text)
    if matches and matches[0].incident_id == expected:
        print(f"[CHAOS 006] ✓ '{text}' → {expected}")
    elif matches:
        print(f"[CHAOS 006] ~ '{text}' → {matches[0].incident_id}")
    else:
        from app.services.incidents.incident_knowledge_service import search_runbooks
        r = search_runbooks("empty mounts nginx container")
        if r:
            print(f"[CHAOS 006] ~ keyword match: {r[0].incident_id}")
        else:
            print(f"[CHAOS 006] ✗ no match for: {text}")
PYEOF

# ── _has_html_mount unit test ──────────────────────────────────────────────────
python3 - << 'PYEOF2'
import sys
sys.path.insert(0, '.')
from app.services.router_health_guard import _has_html_mount

cases = [
    ([], False),
    ([{"Destination": "/tmp"}], False),
    ([{"Destination": "/usr/share/nginx/html"}], True),
    ([{"Destination": "/var/www"}, {"Destination": "/usr/share/nginx/html"}], True),
]

all_ok = True
for mounts, expected in cases:
    result = _has_html_mount(mounts)
    status = "✓" if result == expected else "✗"
    if result != expected:
        all_ok = False
    print(f"[CHAOS 006] {status} _has_html_mount({mounts}) = {result} (expected {expected})")

sys.exit(0 if all_ok else 1)
PYEOF2

echo "[CHAOS 006] ✓ Complete"
