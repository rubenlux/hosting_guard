"""
npm/node build error classifier for GitHub Deploy.

Inspects captured stdout + stderr from npm install / npm run build and returns
structured failure info: (code, detail, suggested_fix).  Also helpers to
extract npm debug log paths and suspected failing packages.
"""
import os
import re
from typing import Optional, Tuple

# ── Pattern rules (checked top-to-bottom; first match wins) ──────────────────

_RULES: list[tuple[list[str], str]] = [
    # node-sass before generic gyp — more specific fix
    (["node-sass", "Node Sass does not yet support"], "node_sass_incompatible"),
    # Missing native build tools in the container
    (["python: not found", "python3: not found", "make: not found",
      "g++: not found", "gcc: not found", "/usr/bin/env: 'python'"], "native_build_tool_missing"),
    # Any other gyp / native compilation failure
    (["gyp ERR!", "node-gyp", "Build failed with error code: 1"], "native_dependency_build_failed"),
    # OpenSSL ABI mismatch
    (["ERR_OSSL_EVP_UNSUPPORTED", "ERR_OSSL"], "openssl_build_failed"),
    # Missing import / missing package
    (["Module not found", "Cannot find module", "Cannot resolve module",
      "Failed to compile"], "module_not_found_build"),
    # Peer-dependency conflicts (ERESOLVE already triggers a retry upstream,
    # so this only fires when the retry also fails)
    (["ERESOLVE", "peer dep"], "npm_peer_dependency_failed"),
    # Package/version not found in registry
    (["No matching version found for", "code E404", "404  Not Found"], "dependency_version_not_found"),
]

_DETAILS: dict[str, str] = {
    "node_sass_incompatible":         "El proyecto usa node-sass, una dependencia antigua incompatible con Node 20.",
    "native_build_tool_missing":      "Faltan herramientas de compilación nativas en el entorno de build.",
    "native_dependency_build_failed": "No pudimos compilar una dependencia nativa de Node.",
    "openssl_build_failed":           "El build falló por incompatibilidad OpenSSL/Node.",
    "module_not_found_build":         "Falta un módulo o dependencia requerida por el proyecto.",
    "npm_peer_dependency_failed":     "Las dependencias tienen conflictos de peer dependencies.",
    "dependency_version_not_found":   "Una dependencia solicitada no existe o no está disponible en el registro.",
    "build_failed":                   "El comando de build falló.",
    "npm_install_failed":             "El comando de instalación de dependencias falló.",
}

_FIXES: dict[str, str] = {
    "node_sass_incompatible": (
        "Migrá de node-sass a sass (npm install sass). "
        "node-sass no es compatible con versiones modernas de Node."
    ),
    "native_build_tool_missing": (
        "El administrador debe agregar herramientas de compilación a la imagen de build "
        "(python3, make, g++). Esto no es un problema de tu código."
    ),
    "native_dependency_build_failed": (
        "Este proyecto usa una dependencia que requiere compilación nativa. "
        "Actualizá las dependencias a versiones modernas (ej: node-sass → sass) "
        "o contactá soporte para habilitar herramientas de compilación."
    ),
    "openssl_build_failed": (
        "Usá NODE_OPTIONS=--openssl-legacy-provider o actualizá las dependencias "
        "a versiones compatibles con Node 20."
    ),
    "module_not_found_build": (
        "Falta una dependencia o hay un import incorrecto. "
        "Verificá que todas las dependencias estén en package.json y que los imports sean correctos."
    ),
    "npm_peer_dependency_failed": (
        "Hay conflictos de peer dependencies. "
        "Actualizá las dependencias o ejecutá npm install --legacy-peer-deps."
    ),
    "dependency_version_not_found": (
        "Revisá las versiones en package.json. La versión solicitada puede no existir "
        "o el paquete puede haber sido eliminado del registro npm."
    ),
}


def classify_npm_failure(output: str, stage: str = "build") -> Tuple[str, str, str]:
    """
    Returns (code, detail, suggested_fix) for the given combined npm output.
    stage is "dependency_install" or "build".
    """
    for patterns, code in _RULES:
        if any(p in output for p in patterns):
            return (
                code,
                _DETAILS.get(code, "El proceso de build falló."),
                _FIXES.get(code, "Ejecutá el mismo comando localmente y corregí los errores."),
            )
    default = "npm_install_failed" if stage == "dependency_install" else "build_failed"
    return (
        default,
        _DETAILS.get(default, "El proceso de build falló."),
        "Ejecutá el mismo comando localmente y corregí los errores antes de deployar.",
    )


def extract_npm_log_path(output: str) -> Optional[str]:
    """Extract the npm debug log file path mentioned in npm error output."""
    m = re.search(r"A complete log of this run can be found in:\s*(\S+\.log)", output)
    return m.group(1) if m else None


def extract_suspected_package(output: str) -> Optional[str]:
    """Guess the package that caused the failure from npm / gyp error output."""
    # "> package@version install" line before gyp error
    m = re.search(r"> ([\w@][^\s@]+@[^\s]+) (install|postinstall|build)\b", output)
    if m:
        return m.group(1)
    if "node-sass" in output:
        return "node-sass"
    # gyp ERR inside a build script
    m = re.search(r"gyp ERR! stack Error:.*?in '?([\w@/.-]+)'?", output)
    if m:
        return m.group(1)
    return None


def read_npm_log(log_path: Optional[str], npm_log_host_dir: str) -> dict:
    """
    Try to read the npm debug log from the host-mounted log directory.
    Returns dict with npm_debug_log_path and either npm_debug_log_tail or
    npm_debug_log_read_error.
    """
    if not log_path:
        return {}
    filename  = os.path.basename(log_path)
    host_path = os.path.join(npm_log_host_dir, filename)
    try:
        with open(host_path) as f:
            return {
                "npm_debug_log_path": log_path,
                "npm_debug_log_tail": f.read()[-4000:],
            }
    except FileNotFoundError:
        return {"npm_debug_log_path": log_path, "npm_debug_log_read_error": "not_found"}
    except PermissionError:
        return {"npm_debug_log_path": log_path, "npm_debug_log_read_error": "permission_denied"}
    except Exception as exc:
        return {"npm_debug_log_path": log_path, "npm_debug_log_read_error": str(exc)}
