"""
Web project auto-detection helpers.

Finds and classifies buildable Node/npm projects within a cloned repository.
"""
import os

_PKG_SEARCH_DIRS = [
    ".", "client", "frontend", "app", "web", "site",
    "apps/web", "apps/frontend", "packages/web", "packages/frontend",
]

_WEB_BUILDABLE_DEPS = frozenset([
    "react", "vue", "svelte", "solid-js", "preact",
    "react-scripts",
    "vite", "next", "nuxt", "@sveltejs/kit", "astro",
    "@angular/core",
])


def _read_pkg(directory: str) -> dict:
    try:
        import json
        with open(os.path.join(directory, "package.json")) as f:
            return json.load(f)
    except Exception:
        return {}


def _is_web_buildable(pkg: dict) -> bool:
    if not pkg or "build" not in pkg.get("scripts", {}):
        return False
    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    return bool(_WEB_BUILDABLE_DEPS & set(all_deps))


def _detect_out_dir(pkg: dict) -> str | None:
    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    build_script = pkg.get("scripts", {}).get("build", "")
    if "react-scripts" in all_deps or "react-scripts" in build_script:
        return "build"
    if "vite" in all_deps or "vite" in build_script or "astro" in all_deps:
        return "dist"
    if "next" in all_deps:
        return "out"
    if "nuxt" in all_deps:
        return "dist"
    return None


def _find_buildable_roots(site_dir: str) -> list:
    """Return [(rel_path, pkg_dict)] for each subdir containing a web-buildable package.json."""
    results = []
    seen: set = set()
    for rel in _PKG_SEARCH_DIRS:
        candidate = os.path.join(site_dir, rel) if rel != "." else site_dir
        if not os.path.isdir(candidate):
            continue
        real_c = os.path.realpath(candidate)
        if real_c in seen:
            continue
        seen.add(real_c)
        pkg = _read_pkg(candidate)
        if _is_web_buildable(pkg):
            results.append((rel, pkg))
    return results


def _detect_framework(pkg: dict) -> str:
    """Return a human-readable framework name from package.json dependencies."""
    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    for dep, fw in [
        ("react-scripts", "create-react-app"),
        ("vite",          "vite"),
        ("next",          "next.js"),
        ("nuxt",          "nuxt"),
        ("astro",         "astro"),
        ("svelte",        "@sveltejs/kit"),
    ]:
        if dep in all_deps:
            return fw
    return "unknown"


def _find_serve_dir(site_dir: str) -> str:
    # "public" is intentionally excluded — it's a CRA source template, not a build output
    for subdir in ["dist", "build", "www", "_site", "frontend/dist", "out"]:
        candidate = os.path.join(site_dir, subdir)
        if os.path.exists(os.path.join(candidate, "index.html")):
            return candidate
    return site_dir
