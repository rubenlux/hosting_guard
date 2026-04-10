import re
from typing import List, Dict, Any

# Expresiones regulares comunes para errores de backend
PHP_ERROR_REGEX = re.compile(r"(Fatal error|Parse error|Warning|Notice):(.+?) in (.+?)(?: on line |:)(\d+)", re.IGNORECASE)
PYTHON_ERROR_REGEX = re.compile(r"Traceback \(most recent call last\):([\s\S]+?)([A-Za-z]+Error: .+)")
NODE_ERROR_REGEX = re.compile(r"(TypeError|ReferenceError|SyntaxError):(.+?)\n\s+at (.+?):(\d+)(:\d+)?")

# Prefijos de rutas generadas por bots/scanners — no son errores de la aplicación
_PROBE_PREFIXES = (
    "/.env", "/.git", "/wp-", "/wordpress", "/xmlrpc",
    "/config", "/admin.php", "/phpmyadmin", "/mysqladmin",
    "/backup", "/shell", "/.aws", "/.ssh", "/cgi-bin",
    "/setup.php", "/install.php", "/manager/", "/actuator",
    "/console", "/.DS_Store", "/web.config",
)

def _is_probe(path: str) -> bool:
    p = path.lower()
    return any(p.startswith(prefix) for prefix in _PROBE_PREFIXES)


class LogParser:
    @staticmethod
    def parse_logs(raw_logs: str) -> List[Dict[str, Any]]:
        """
        Escanea logs de texto crudo y extrae errores estructurados.
        Diferencia entre CRITICAL (errores de código) y WARNING (señales HTTP como 404).
        Los 404 de bots/scanners se clasifican como source="external_probe" y se excluyen
        del conteo de errores para evitar falsos positivos en el health score.
        """
        parsed_errors = []
        lines = raw_logs.splitlines()

        for i, line in enumerate(lines):
            # 1. PHP PHP Errors
            php_match = PHP_ERROR_REGEX.search(line)
            if php_match:
                severity = "critical" if "error" in php_match.group(1).lower() else "warning"
                parsed_errors.append({
                    "type": "php_error",
                    "severity": severity,
                    "message": php_match.group(2).strip(),
                    "file": php_match.group(3).strip(),
                    "line": int(php_match.group(4)),
                    "raw_context": line
                })
                continue

            # 2. HTTP Signals (404, 5xx, timeouts)
            if '" 404 ' in line:
                path_match = re.search(r'(?:GET|POST|HEAD)\s+(.+?)\s+HTTP', line)
                path = path_match.group(1) if path_match else "unknown"

                if _is_probe(path):
                    # Clasificar como probe externo — no afecta health score
                    parsed_errors.append({
                        "type": "http_404",
                        "severity": "info",
                        "source": "external_probe",
                        "message": f"Probe externo ignorado (404): {path}",
                        "file": path,
                        "line": 0,
                        "raw_context": line,
                    })
                    continue

                parsed_errors.append({
                    "type": "http_404",
                    "severity": "warning",
                    "source": "application",
                    "message": f"Archivo faltante (404): {path}",
                    "file": path,
                    "line": 0,
                    "raw_context": line
                })
            
            elif '" 500 ' in line or '" 503 ' in line:
                parsed_errors.append({
                    "type": "http_5xx",
                    "severity": "critical",
                    "message": "Error interno del servidor (500/503) detectado",
                    "file": "servidor",
                    "line": 0,
                    "raw_context": line
                })

        # Python Regex over the whole blob
        for py_match in PYTHON_ERROR_REGEX.finditer(raw_logs):
             parsed_errors.append({
                 "type": "python_exception",
                 "severity": "critical",
                 "message": py_match.group(2).strip(),
                 "file": "unknown.py",
                 "line": 0,
                 "raw_context": py_match.group(0).strip()
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
