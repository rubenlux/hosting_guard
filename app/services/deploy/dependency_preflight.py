"""
Dependency preflight — scans package manifests for known-incompatible packages.
Called before npm install so we short-circuit deploy without running node-gyp.
"""
import json
import os
from typing import Optional

_INCOMPATIBLE_PACKAGES = frozenset({"node-sass"})


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
    """
    Scan manifest files for node-sass before npm install.
    Returns {"package": ..., "detection_source": ...} if found, else None.
    """
    source = (
        _check_package_json(work_dir)
        or _check_lockfile(work_dir, "package-lock.json")
        or _check_lockfile(work_dir, "yarn.lock")
        or _check_lockfile(work_dir, "pnpm-lock.yaml")
    )
    if source:
        return {"package": "node-sass", "detection_source": source}
    return None
