import re
from typing import List, Dict, Any

# Expresiones regulares comunes para errores de backend
PHP_ERROR_REGEX    = re.compile(r"(Fatal error|Parse error|Warning|Notice):(.+?) in (.+?)(?: on line |:)(\d+)", re.IGNORECASE)
PYTHON_ERROR_REGEX = re.compile(r"Traceback \(most recent call last\):([\s\S]+?)([A-Za-z]+Error: .+)")
NODE_ERROR_REGEX   = re.compile(r"(TypeError|ReferenceError|SyntaxError):(.+?)\n\s+at (.+?):(\d+)(:\d+)?")

# Docker log timestamp prefix: 2024-01-15T10:30:45.123456789Z (added by --timestamps flag)
DOCKER_TS_REGEX = re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s+')

# Prefijos de rutas generadas por bots/scanners — no son errores de la aplicación
_PROBE_PREFIXES = (
    "/.env", "/.git", "/wp-", "/wordpress", "/xmlrpc",
    "/config", "/admin.php", "/phpmyadmin", "/mysqladmin",
    "/backup", "/shell", "/.aws", "/.ssh", "/cgi-bin",
    "/setup.php", "/install.php", "/manager/", "/actuator",
    "/console", "/.DS_Store", "/web.config",
)

# API path patterns that would never be static files on a nginx container.
# A 404 on these paths means the request was misrouted (sent to the hosting
# container instead of the API backend).
_API_PATH_PATTERNS = re.compile(
    r'^/(?:hosting|api|fix|diagnose|health|login|auth|user|admin|v\d+)(?:/|$)',
    re.IGNORECASE,
)

# User-agents that indicate synthetic/test requests — not real end-user traffic.
# These produce noise in logs but carry zero production signal.
_SYNTHETIC_UA_PATTERNS = re.compile(
    r'\b(?:curl|wget|httpie|python-requests|go-http|okhttp|grpc|postman|insomnia)\b',
    re.IGNORECASE,
)

def _is_probe(path: str) -> bool:
    p = path.lower()
    return any(p.startswith(prefix) for prefix in _PROBE_PREFIXES)

def _is_misrouted_api(path: str) -> bool:
    """True when a 404 path looks like an API call on a static nginx container."""
    return bool(_API_PATH_PATTERNS.match(path))

def _is_synthetic(log_line: str) -> bool:
    """True when the request was made by a CLI tool (curl, wget, etc.) — not a real user."""
    return bool(_SYNTHETIC_UA_PATTERNS.search(log_line))


# ── Error quality weights ─────────────────────────────────────────────────────
# Base signal strength per error type.
# http_404 base weight is intentionally low (1) — path context multiplier
# below elevates critical paths (/, /index.html) to realistic signal weight.
_ERROR_QUALITY_WEIGHTS: dict[str, int] = {
    "python_exception":    10,
    "ModuleNotFoundError": 10,
    "SyntaxError":         10,
    "ImportError":         10,
    "AttributeError":       9,
    "TypeError":            9,
    "http_5xx":             8,
    "php_error":            7,
    "http_404":             1,
}

# Hard-trigger types — always activate LLM regardless of health_score or quality.
# These error classes always mean code is broken; no threshold needed.
_HARD_TRIGGER_TYPES: frozenset[str] = frozenset({
    "python_exception", "http_5xx", "php_error",
    "ModuleNotFoundError", "SyntaxError", "ImportError",
    "AttributeError", "TypeError",
})

_QUALITY_THRESHOLD = 5


def _path_context_multiplier(path: str) -> float:
    """
    Context multiplier for http_404 errors based on path criticality.

    Why path-aware:
      404 /favicon.ico       → 0.1  (cosmetic, no functional impact)
      404 /old-page.html     → 1.0  (normal, broken link)
      404 /main.css          → 2.0  (site renders broken)
      404 /index.html        → 5.0  (site completely unreachable)

    This is what 'weighting by path' means in practice:
    5 favicon 404s  = quality 0.5  → no LLM (noise)
    1 index.html 404 = quality 5.0 → LLM (real problem)
    """
    if not path:
        return 1.0
    p = path.lower().split("?")[0]   # strip query string

    # Entry point — if index is missing, site is completely down for users
    if p in ("/", "/index.html", "/index.php"):
        return 5.0

    # Critical bundles — site renders broken without CSS/JS
    if re.search(r'\.(css|js)$', p):
        return 2.0

    # Pure cosmetic / font / icon files — no functional impact
    if re.search(r'\.(ico|svg|woff|woff2|ttf|eot|png|jpg|jpeg|gif|webp|map)$', p):
        return 0.1

    return 1.0


def error_quality_score(errors: list) -> float:
    """
    Returns the total quality score for a list of parsed errors.
    Only considers actionable (source='application') errors.
    http_404 errors are weighted by path criticality via _path_context_multiplier.

    Examples:
      1 curl 404 /hosting/1/diagnose → dev_noise (excluded) → 0
      1 http_404 /index.html         → 1 × 5.0 = 5.0 → LLM activates
      1 SyntaxError                  → 10 (hard trigger, always LLM)
      5 http_404 /old-page.html      → 5 × 1.0 = 5.0 → LLM activates
    """
    total = 0.0
    for e in errors:
        if e.get("source") != "application":
            continue
        base = _ERROR_QUALITY_WEIGHTS.get(e.get("type", "unknown"), 2)
        if e.get("type") == "http_404":
            total += base * _path_context_multiplier(e.get("file", ""))
        else:
            total += float(base)
    return total


def is_signal_worth_diagnosing(actionable_errors: list, health_score: int) -> bool:
    """
    Returns True only when the error signal is strong enough to warrant an LLM call.

    Hard triggers (python_exception, http_5xx, etc.) always return True — these
    error classes always mean code is broken, no threshold applies.

    For everything else: quality_score >= QUALITY_THRESHOLD OR health_score < 85.
    """
    # Hard trigger check — one exception = always diagnose
    for e in actionable_errors:
        if e.get("type") in _HARD_TRIGGER_TYPES and e.get("source") == "application":
            return True

    # Health engine already flagged a real problem
    if health_score < 85:
        return True

    # Quality threshold gate
    return error_quality_score(actionable_errors) >= _QUALITY_THRESHOLD

def _extract_ts(line: str) -> str | None:
    """Extract ISO timestamp from a docker --timestamps log line, or None."""
    m = DOCKER_TS_REGEX.match(line)
    return m.group(1) if m else None


class LogParser:
    @staticmethod
    def parse_logs(raw_logs: str) -> List[Dict[str, Any]]:
        """
        Escanea logs de texto crudo y extrae errores estructurados.
        Diferencia entre CRITICAL (errores de código) y WARNING (señales HTTP como 404).
        Los 404 de bots/scanners se clasifican como source="external_probe" y se excluyen
        del conteo de errores para evitar falsos positivos en el health score.

        Cada error incluye:
          ts     — ISO timestamp extraído de la línea (docker --timestamps), si está presente
          source — "application" | "external_probe" (diferencia errores propios de ruido externo)
        """
        parsed_errors = []
        lines = raw_logs.splitlines()

        for i, line in enumerate(lines):
            ts = _extract_ts(line)

            # 1. PHP Errors
            php_match = PHP_ERROR_REGEX.search(line)
            if php_match:
                severity = "critical" if "error" in php_match.group(1).lower() else "warning"
                parsed_errors.append({
                    "type":        "php_error",
                    "severity":    severity,
                    "source":      "application",
                    "message":     php_match.group(2).strip(),
                    "file":        php_match.group(3).strip(),
                    "line":        int(php_match.group(4)),
                    "ts":          ts,
                    "raw_context": line,
                })
                continue

            # 2. HTTP Signals (404, 5xx, timeouts)
            if '" 404 ' in line:
                path_match = re.search(r'(?:GET|POST|HEAD)\s+(.+?)\s+HTTP', line)
                path = path_match.group(1) if path_match else "unknown"

                # Source maps (.map) are browser dev-tool requests — no production impact.
                # Treat as dev_noise so they never pollute the health score or LLM context.
                if path.endswith(".map"):
                    parsed_errors.append({
                        "type":        "http_404",
                        "severity":    "info",
                        "source":      "dev_noise",
                        "message":     f"Source map faltante (sin impacto en producción): {path}",
                        "file":        path,
                        "line":        0,
                        "ts":          ts,
                        "raw_context": line,
                    })
                    continue

                if _is_probe(path):
                    parsed_errors.append({
                        "type":        "http_404",
                        "severity":    "info",
                        "source":      "external_probe",
                        "message":     f"Probe externo ignorado (404): {path}",
                        "file":        path,
                        "line":        0,
                        "ts":          ts,
                        "raw_context": line,
                    })
                    continue

                # Misrouted API call — request sent to static container instead of
                # the API backend (e.g. /hosting/1/diagnose on nginx).
                if _is_misrouted_api(path):
                    parsed_errors.append({
                        "type":        "http_404",
                        "severity":    "info",
                        "source":      "dev_noise",
                        "message":     f"Petición API mal enrutada (sin impacto): {path}",
                        "file":        path,
                        "line":        0,
                        "ts":          ts,
                        "raw_context": line,
                    })
                    continue

                # Synthetic request (curl, wget, etc.) — CLI tools, not real users.
                # Quality weight = 1 but classify as dev_noise so it never inflates
                # actionable_errors or triggers the LLM.
                if _is_synthetic(line):
                    parsed_errors.append({
                        "type":        "http_404",
                        "severity":    "info",
                        "source":      "dev_noise",
                        "message":     f"Petición sintética (herramienta CLI, sin impacto): {path}",
                        "file":        path,
                        "line":        0,
                        "ts":          ts,
                        "raw_context": line,
                    })
                    continue

                parsed_errors.append({
                    "type":        "http_404",
                    "severity":    "warning",
                    "source":      "application",
                    "message":     f"Archivo faltante (404): {path}",
                    "file":        path,
                    "line":        0,
                    "ts":          ts,
                    "raw_context": line,
                })

            elif '" 500 ' in line or '" 503 ' in line:
                parsed_errors.append({
                    "type":        "http_5xx",
                    "severity":    "critical",
                    "source":      "application",
                    "message":     "Error interno del servidor (500/503) detectado",
                    "file":        "servidor",
                    "line":        0,
                    "ts":          ts,
                    "raw_context": line,
                })

        # Python Regex over the whole blob (no per-line TS for multi-line tracebacks)
        for py_match in PYTHON_ERROR_REGEX.finditer(raw_logs):
            error_msg = py_match.group(2).strip()
            # Extract specific exception class (e.g. "ModuleNotFoundError: ..." → "ModuleNotFoundError")
            # This feeds _detect_system_hint with the exact type for targeted pre-classification.
            raw_class  = error_msg.split(":")[0].strip()
            error_type = (
                raw_class
                if re.match(r'^[A-Z][A-Za-z]+(?:Error|Exception|Warning)$', raw_class)
                else "python_exception"
            )
            parsed_errors.append({
                "type":        error_type,
                "severity":    "critical",
                "source":      "application",
                "message":     error_msg,
                "file":        "unknown.py",
                "line":        0,
                "ts":          None,  # multi-line blob — no reliable single timestamp
                "raw_context": py_match.group(0).strip(),
            })

        # Deduplicar
        unique_errors = []
        seen = set()
        for err in parsed_errors:
            key = f"{err['type']}_{err['message']}_{err['file']}"
            if key not in seen:
                seen.add(key)
                unique_errors.append(err)

        return unique_errors[:10]
