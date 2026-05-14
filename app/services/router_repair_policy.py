"""
Router repair policy — controls auto-remediation scope.

Set via env var ROUTER_HEALTH_REPAIR_MODE (default: "protect").

Modes:
  "off"     — no incidents, no repair; useful in test/CI
  "monitor" — detect + create incidents; no automatic repair (decision='would_repair' logged)
  "protect" — detect + create incidents + auto-repair platform dynamic files
              (tenant auto-repair is NEVER automatic in any mode)
"""
import os

REPAIR_MODE: str = os.getenv("ROUTER_HEALTH_REPAIR_MODE", "protect")
