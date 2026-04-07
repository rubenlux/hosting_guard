import re
from typing import List, Dict, Any

# Expresiones regulares comunes para errores de backend
PHP_ERROR_REGEX = re.compile(r"(Fatal error|Parse error|Warning|Notice):(.+?) in (.+?)(?: on line |:)(\d+)", re.IGNORECASE)
PYTHON_ERROR_REGEX = re.compile(r"Traceback \(most recent call last\):([\s\S]+?)([A-Za-z]+Error: .+)")
NODE_ERROR_REGEX = re.compile(r"(TypeError|ReferenceError|SyntaxError):(.+?)\n\s+at (.+?):(\d+)(:\d+)?")

class LogParser:
    @staticmethod
    def parse_logs(raw_logs: str) -> List[Dict[str, Any]]:
        """
        Escanea logs de texto crudo y extrae errores estructurados.
        """
        parsed_errors = []
        lines = raw_logs.splitlines()

        # Usar un buffer simple para python stacktraces
        python_traceback_buffer = []
        in_python_traceback = False

        for i, line in enumerate(lines):
            # 1. PHP PHP Errors
            php_match = PHP_ERROR_REGEX.search(line)
            if php_match:
                severity = "high" if "error" in php_match.group(1).lower() else "medium"
                parsed_errors.append({
                    "type": "php_error",
                    "severity": severity,
                    "message": php_match.group(2).strip(),
                    "file": php_match.group(3).strip(),
                    "line": int(php_match.group(4)),
                    "raw_context": line
                })
                continue
            
            # 2. Node.js Errors (simple one-line start usually)
            node_match = NODE_ERROR_REGEX.search(line)
            if node_match and len(lines) > i + 1:
               # Often node errors have "    at ..." on subsequent lines, 
               # but we are looking for a simple generic match right now
               pass # Improved JS parsing can be added later

            # Nginx / Generic 500s or timeouts
            if "HTTP/1.1\" 500" in line:
               parsed_errors.append({
                   "type": "http_500",
                   "severity": "high",
                   "message": "Internal Server Error detected in access logs",
                   "file": "nginx/access.log",
                   "line": 0,
                   "raw_context": line
               })

        # Python Regex over the whole blob
        for py_match in PYTHON_ERROR_REGEX.finditer(raw_logs):
             parsed_errors.append({
                 "type": "python_exception",
                 "severity": "high",
                 "message": py_match.group(2).strip(),
                 "file": "unknown.py", # Can be extracted from stack trace if needed
                 "line": 0,
                 "raw_context": py_match.group(0).strip()
             })

        # Deduplicate generic errors avoiding noise
        unique_errors = []
        seen = set()
        for err in parsed_errors:
            # Hash basico para dedup
            key = f"{err['type']}_{err['message']}_{err['file']}"
            if key not in seen:
                seen.add(key)
                unique_errors.append(err)

        return unique_errors[:5] # Limitar a los 5 errores más relevantes
