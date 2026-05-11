"""
Dependency preflight — scans package manifests and config files for known-incompatible
packages and unsupported configurations. Called before npm install to fail fast
without running node-gyp or the full install process.

Priority order: node-sass → pnpm → yarn → node version → next SSR
"""
import json
import os
import re
from typing import Optional

_INCOMPATIBLE_PACKAGES = frozenset({"node-sass"})

# Node major version used in the build container
_CONTAINER_NODE_MAJOR = 20


# ── node-sass detection ───────────────────────────────────────────────────────

def _check_package_json(work_dir: str) -> Optional[str]:
    path = os.path.join(work_dir, "package.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            pkg = json.load(f)
        for section in ("dependencies", "devDependencies", "optionalDependencies"):
            if _INCOMPATIBLE_PACKAGES & set(pkg.get(section, {})):
                return "package.json"
    except Exception:
        pass
    return None


def _check_lockfile(work_dir: str, filename: str) -> Optional[str]:
    path = os.path.join(work_dir, filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, errors="replace") as f:
            content = f.read()
        if any(pkg in content for pkg in _INCOMPATIBLE_PACKAGES):
            return filename
    except Exception:
        pass
    return None


def check_node_sass_preflight(work_dir: str) -> Optional[dict]:
    """Scan manifest files for node-sass. Returns {"package": ..., "detection_source": ...} or None."""
    source = (
        _check_package_json(work_dir)
        or _check_lockfile(work_dir, "package-lock.json")
        or _check_lockfile(work_dir, "yarn.lock")
        or _check_lockfile(work_dir, "pnpm-lock.yaml")
    )
    if source:
        return {"package": "node-sass", "detection_source": source}
    return None


# ── Extended preflight checks ─────────────────────────────────────────────────

def _node_sass_check(work_dir: str) -> Optional[dict]:
    found = check_node_sass_preflight(work_dir)
    if not found:
        return None
    return {
        "code": "node_sass_incompatible",
        "stage": "dependency_preflight",
        "detail": "El proyecto usa node-sass, una dependencia antigua incompatible con Node 20.",
        "suggested_fix": (
            "Migrá de node-sass a sass (npm install sass). "
            "node-sass no es compatible con versiones modernas de Node."
        ),
        "evidence": {
            "suspected_package": "node-sass",
            "detection_source": found["detection_source"],
            "install_skipped": True,
            "reason": "known_incompatible_dependency",
        },
    }


def _package_manager_check(work_dir: str) -> Optional[dict]:
    """Detect pnpm or pure-yarn projects that can't be built with npm."""
    has_pkg_lock = os.path.exists(os.path.join(work_dir, "package-lock.json"))

    if os.path.exists(os.path.join(work_dir, "pnpm-lock.yaml")):
        return {
            "code": "package_manager_pnpm_detected",
            "stage": "dependency_preflight",
            "detail": "El proyecto usa pnpm, que no está disponible en el entorno de build actual.",
            "suggested_fix": (
                "Este deploy usa npm. Configurá el Install Command manualmente "
                "(ej: 'npm install') o migrá a npm borrando pnpm-lock.yaml."
            ),
            "evidence": {
                "lockfile": "pnpm-lock.yaml",
                "install_skipped": True,
                "reason": "unsupported_package_manager",
            },
        }

    if os.path.exists(os.path.join(work_dir, "yarn.lock")) and not has_pkg_lock:
        return {
            "code": "package_manager_yarn_detected",
            "stage": "dependency_preflight",
            "detail": "El proyecto usa Yarn, que no está disponible en el entorno de build actual.",
            "suggested_fix": (
                "Este deploy usa npm. Generá un package-lock.json ejecutando npm install "
                "localmente, o configurá el Install Command a 'npm install'."
            ),
            "evidence": {
                "lockfile": "yarn.lock",
                "install_skipped": True,
                "reason": "unsupported_package_manager",
            },
        }

    return None


def _node_version_check(work_dir: str, pkg: dict) -> Optional[dict]:
    """Check .nvmrc, .node-version, and engines.node for Node < 16 requirements."""

    def _parse_major(s: str) -> Optional[int]:
        m = re.match(r"v?(\d+)", s.strip())
        return int(m.group(1)) if m else None

    for fname in (".nvmrc", ".node-version"):
        path = os.path.join(work_dir, fname)
        if not os.path.exists(path):
            continue
        try:
            declared = open(path).read().strip().split()[0]
            major = _parse_major(declared)
            if major is not None and major < 16:
                return {
                    "code": "node_version_mismatch",
                    "stage": "dependency_preflight",
                    "detail": (
                        f"El proyecto declara Node {declared} en {fname}, "
                        f"pero el entorno de build usa Node {_CONTAINER_NODE_MAJOR}."
                    ),
                    "suggested_fix": (
                        "Actualizá las dependencias para ser compatibles con Node 20, "
                        f"o modificá {fname} para usar una versión compatible (≥16)."
                    ),
                    "evidence": {
                        "declared_version": declared,
                        "container_node_major": _CONTAINER_NODE_MAJOR,
                        "source": fname,
                        "install_skipped": True,
                        "reason": "node_version_incompatible",
                    },
                }
        except Exception:
            pass

    engines_node = pkg.get("engines", {}).get("node", "")
    if engines_node:
        upper = re.search(r"<=?\s*(\d+)", engines_node)
        if upper:
            max_major = int(upper.group(1))
            if max_major < _CONTAINER_NODE_MAJOR:
                return {
                    "code": "node_version_mismatch",
                    "stage": "dependency_preflight",
                    "detail": (
                        f"El proyecto requiere Node {engines_node} (engines.node), "
                        f"pero el entorno de build usa Node {_CONTAINER_NODE_MAJOR}."
                    ),
                    "suggested_fix": (
                        "Actualizá las dependencias para ser compatibles con Node 20, "
                        "o eliminá la restricción engines.node."
                    ),
                    "evidence": {
                        "declared_version": engines_node,
                        "container_node_major": _CONTAINER_NODE_MAJOR,
                        "source": "package.json engines.node",
                        "install_skipped": True,
                        "reason": "node_version_incompatible",
                    },
                }

    return None


def _next_ssr_check(work_dir: str, pkg: dict) -> Optional[dict]:
    """Flag Next.js projects without output:'export' — SSR won't work on static hosting."""
    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    if "next" not in all_deps:
        return None

    for config_file in ("next.config.js", "next.config.ts", "next.config.mjs", "next.config.cjs"):
        path = os.path.join(work_dir, config_file)
        if not os.path.exists(path):
            continue
        try:
            content = open(path, errors="replace").read()
            if re.search(r"""output\s*:\s*['"]export['"]""", content):
                return None  # Static export configured — OK
        except Exception:
            pass

    return {
        "code": "next_ssr_not_supported",
        "stage": "dependency_preflight",
        "detail": (
            "El proyecto usa Next.js en modo SSR. "
            "Este hosting solo sirve sitios estáticos."
        ),
        "suggested_fix": (
            "Para hosting estático, agregá output: 'export' en next.config.js. "
            "Si necesitás SSR/API routes, usá el Start Command con un runtime Node."
        ),
        "evidence": {
            "framework": "next.js",
            "install_skipped": True,
            "reason": "ssr_framework_not_supported",
        },
    }


def run_dependency_preflight(work_dir: str, pkg: dict) -> Optional[dict]:
    """
    Run all preflight checks in priority order.
    Returns the first issue found as a dict with keys:
      code, stage, detail, suggested_fix, evidence
    Returns None if no issues detected.
    """
    for check in (
        lambda: _node_sass_check(work_dir),
        lambda: _package_manager_check(work_dir),
        lambda: _node_version_check(work_dir, pkg),
        lambda: _next_ssr_check(work_dir, pkg),
    ):
        result = check()
        if result:
            return result
    return None
