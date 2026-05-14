"""
Dependency preflight — scans package manifests and config files for known-incompatible
packages and unsupported configurations. Called before npm install to fail fast
without running node-gyp or the full install process.

Priority order: node-sass → supply-chain → pnpm → yarn → node version → next SSR
"""
import json
import os
import re
from typing import Optional

_INCOMPATIBLE_PACKAGES = frozenset({"node-sass"})

# TanStack npm supply-chain compromise — advisory 2026-05-11
# Maps package name → set of pinned versions known to be malicious.
_TANSTACK_AFFECTED: dict[str, frozenset] = {
    "@tanstack/react-query":                frozenset({"5.75.0", "5.75.1", "5.75.2"}),
    "@tanstack/query-core":                 frozenset({"5.75.0", "5.75.1", "5.75.2"}),
    "@tanstack/vue-query":                  frozenset({"5.75.0", "5.75.1", "5.75.2"}),
    "@tanstack/svelte-query":               frozenset({"5.75.0", "5.75.1", "5.75.2"}),
    "@tanstack/solid-query":                frozenset({"5.75.0", "5.75.1", "5.75.2"}),
    "@tanstack/angular-query-experimental": frozenset({"5.75.0", "5.75.1", "5.75.2"}),
    "@tanstack/react-table":                frozenset({"8.21.0"}),
    "@tanstack/table-core":                 frozenset({"8.21.0"}),
    "@tanstack/react-router":               frozenset({"1.120.0", "1.120.1"}),
    "@tanstack/router":                     frozenset({"1.120.0", "1.120.1"}),
}

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


# ── TanStack supply-chain guard ───────────────────────────────────────────────

def _scan_package_lock(work_dir: str) -> dict[str, str]:
    """Return {pkg: version} for @tanstack/* packages pinned in package-lock.json."""
    path = os.path.join(work_dir, "package-lock.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            lock = json.load(f)
    except Exception:
        return {}
    found: dict[str, str] = {}
    # v2/v3: packages dict keyed like "node_modules/@tanstack/react-query"
    for key, info in lock.get("packages", {}).items():
        if "@tanstack/" not in key or not isinstance(info, dict):
            continue
        parts = key.split("node_modules/")
        last = parts[-1] if parts else key
        if last.startswith("@tanstack/"):
            pkg_name = "/".join(last.split("/")[:2])
            version = info.get("version", "")
            if version:
                found[pkg_name] = version
    # v1: dependencies dict
    for pkg_name, info in lock.get("dependencies", {}).items():
        if pkg_name.startswith("@tanstack/") and isinstance(info, dict):
            version = info.get("version", "")
            if version and pkg_name not in found:
                found[pkg_name] = version
    return found


def _scan_pnpm_lock(work_dir: str) -> dict[str, str]:
    """Return {pkg: version} for @tanstack/* packages pinned in pnpm-lock.yaml."""
    path = os.path.join(work_dir, "pnpm-lock.yaml")
    if not os.path.exists(path):
        return {}
    found: dict[str, str] = {}
    try:
        content = open(path, errors="replace").read()
        for m in re.finditer(
            r"""['"/ ](@tanstack/[\w-]+)@([\d]+\.[\d]+\.[\d]+[\w.-]*)['"/ ]?\s*:""",
            content,
        ):
            found[m.group(1)] = m.group(2)
    except Exception:
        pass
    return found


def _scan_yarn_lock(work_dir: str) -> dict[str, str]:
    """Return {pkg: version} for @tanstack/* packages pinned in yarn.lock (v1 and berry)."""
    path = os.path.join(work_dir, "yarn.lock")
    if not os.path.exists(path):
        return {}
    found: dict[str, str] = {}
    try:
        current_pkg: Optional[str] = None
        for line in open(path, errors="replace"):
            m_hdr = re.match(r'^["\s]*(@tanstack/[\w-]+)@', line)
            if m_hdr:
                current_pkg = m_hdr.group(1)
            if current_pkg:
                m_ver = re.match(r'\s+version[:\s]+"?([\d]+\.[\d]+\.[\d]+[\w.-]*)"?', line)
                if m_ver:
                    found[current_pkg] = m_ver.group(1)
                    current_pkg = None
    except Exception:
        pass
    return found


def _has_tanstack_in_manifest(pkg: dict) -> bool:
    for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        for name in pkg.get(section, {}):
            if name.startswith("@tanstack/"):
                return True
    return False


def _tanstack_supply_chain_check(work_dir: str, pkg: dict) -> Optional[dict]:
    # Aggregate all pinned @tanstack versions across all lockfile formats
    all_pinned: dict[str, str] = {}
    for scanner in (_scan_package_lock, _scan_pnpm_lock, _scan_yarn_lock):
        all_pinned.update(scanner(work_dir))

    affected = {
        name: ver
        for name, ver in all_pinned.items()
        if name in _TANSTACK_AFFECTED and ver in _TANSTACK_AFFECTED[name]
    }
    if affected:
        return {
            "code": "npm_supply_chain_tanstack_compromise",
            "stage": "dependency_preflight",
            "detail": (
                "Este deploy fue bloqueado porque el proyecto referencia paquetes involucrados "
                "en el compromiso de la cadena de suministro de TanStack (anunciado 2026-05-11). "
                "Fijá una versión segura y commiteá un lockfile."
            ),
            "suggested_fix": (
                "Actualizá los paquetes @tanstack afectados a la última versión parcheada "
                "y regenerá el lockfile con 'npm install'. "
                "Consultá https://github.com/TanStack para las versiones seguras."
            ),
            "evidence": {
                "install_skipped": True,
                "reason": "supply_chain_compromised_version",
                "affected_packages": affected,
                "advisory_date": "2026-05-11",
            },
        }

    has_lock = any(
        os.path.exists(os.path.join(work_dir, f))
        for f in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock")
    )
    if not has_lock and _has_tanstack_in_manifest(pkg):
        return {
            "code": "npm_lockfile_required_for_supply_chain_safety",
            "stage": "dependency_preflight",
            "detail": (
                "El proyecto incluye paquetes @tanstack/* pero no tiene lockfile. "
                "Sin un lockfile no es posible verificar que las versiones instaladas "
                "no estén comprometidas por el ataque de cadena de suministro de TanStack (2026-05-11)."
            ),
            "suggested_fix": (
                "Ejecutá 'npm install' localmente para generar un package-lock.json, "
                "verificá que las versiones de @tanstack/* sean seguras y commiteá el lockfile."
            ),
            "evidence": {
                "install_skipped": True,
                "reason": "lockfile_required_for_supply_chain_safety",
                "advisory_date": "2026-05-11",
            },
        }

    return None


def run_dependency_preflight(work_dir: str, pkg: dict) -> Optional[dict]:
    """
    Run all preflight checks in priority order.
    Returns the first issue found as a dict with keys:
      code, stage, detail, suggested_fix, evidence
    Returns None if no issues detected.
    """
    for check in (
        lambda: _node_sass_check(work_dir),
        lambda: _tanstack_supply_chain_check(work_dir, pkg),
        lambda: _package_manager_check(work_dir),
        lambda: _node_version_check(work_dir, pkg),
        lambda: _next_ssr_check(work_dir, pkg),
    ):
        result = check()
        if result:
            return result
    return None
