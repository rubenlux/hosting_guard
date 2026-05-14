#!/usr/bin/env bash
# Chaos 005 — Welcome to nginx body detection
# Validates: HTTP 200 + nginx default body → WELCOME_TO_NGINX_EMPTY_SITE → NOT healthy
set -euo pipefail

echo "[CHAOS 005] Validate Welcome-to-nginx detection"

# ── Unit test: signature matching ─────────────────────────────────────────────
python3 - << 'PYEOF'
import sys
sys.path.insert(0, '.')
from app.services.incidents.incident_knowledge_service import match_error_signature

texts = [
    "Welcome to nginx!",
    "nginx default page",
    "Welcome to nginx! If you see this page, the nginx web server",
]
expected = "WELCOME_TO_NGINX_EMPTY_SITE"

for text in texts:
    matches = match_error_signature(text)
    if matches and matches[0].incident_id == expected:
        print(f"[CHAOS 005] ✓ '{text[:40]}' → {expected}")
    elif matches:
        print(f"[CHAOS 005] ~ '{text[:40]}' → {matches[0].incident_id} (expected {expected})")
    else:
        print(f"[CHAOS 005] ✗ '{text[:40]}' → no match")

# Validate auto_repair_allowed=True (if client content exists)
if matches:
    best = matches[0]
    print(f"[CHAOS 005] auto_repair_allowed: {best.auto_repair_allowed}")
    if "recreate_static_nginx_container_with_mount" in best.safe_actions:
        print("[CHAOS 005] ✓ safe action 'recreate_static_nginx_container_with_mount' present")
    if "delete_client_files" in best.forbidden_actions or "delete_client_data_without_snapshot" in best.forbidden_actions:
        print("[CHAOS 005] ✓ client file deletion correctly forbidden")
PYEOF

# ── Body check unit test ───────────────────────────────────────────────────────
python3 - << 'PYEOF2'
import sys
sys.path.insert(0, '.')
from app.services.router_health_guard import _is_nginx_default_page

cases = [
    (b"Welcome to nginx!", True),
    (b"<html><body>Welcome to nginx! If you see this page</body></html>", True),
    (b"nginx default page lorem ipsum", True),
    (b"Welcome to My Awesome Blog", False),
    (b"<html><body>Hello World</body></html>", False),
]

all_ok = True
for body, expected in cases:
    result = _is_nginx_default_page(body)
    status = "✓" if result == expected else "✗"
    if result != expected:
        all_ok = False
    print(f"[CHAOS 005] {status} _is_nginx_default_page({body[:40]!r}) = {result} (expected {expected})")

if all_ok:
    print("[CHAOS 005] ✓ All body detection tests pass")
else:
    print("[CHAOS 005] ✗ Some body detection tests FAILED")
    sys.exit(1)
PYEOF2

echo "[CHAOS 005] ✓ Complete"
