"""
Node version requirement detection.

Reads .nvmrc or package.json engines.node to determine the requested Node version.
"""
import os
from typing import Optional


def _read_version_file(work_dir: str) -> Optional[str]:
    """Return the requested Node version from .nvmrc or package.json engines.node."""
    import json
    nvmrc = os.path.join(work_dir, ".nvmrc")
    if os.path.exists(nvmrc):
        with open(nvmrc) as f:
            return f.read().strip()
    pkg = os.path.join(work_dir, "package.json")
    if os.path.exists(pkg):
        with open(pkg) as f:
            return json.load(f).get("engines", {}).get("node")
    return None
