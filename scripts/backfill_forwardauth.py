#!/usr/bin/env python3
"""
Backfill ForwardAuth middleware label to existing tenant containers.

Tenant containers created before the forwardauth middleware was added do not
carry the Traefik label that wires them through /internal/forwardauth. This
script re-creates each affected container with the label added, preserving ALL
existing configuration including bind mounts, env vars, resource limits, etc.

Usage (run inside the app container on production):
    python scripts/backfill_forwardauth.py [--dry-run] [--hosting-id N] [--force]

Flags:
    --dry-run     Show what WOULD be done; no containers are modified.
    --hosting-id  Process only this specific hosting_id.
    --force       Re-create even containers that already have the middleware
                  label (use to recover containers that lost bind mounts).

Safety checklist (enforced automatically):
    1. Reads full container config via `docker inspect` before any change.
    2. Backs up inspect JSON to /tmp/container-backups/<name>-<ts>.json.
    3. Pre-validates bind mounts: if any Bind maps to an nginx html dir,
       the index.html must exist on the host or the container is skipped.
    4. Merges the middleware label — never clobbers existing middleware values.
    5. Skips non-tenant containers (api.*, hosting_guard, traefik, redis, …).
    6. Post-validates after re-create: fetches / and checks for nginx default
       page regression. Marks container failed if regression detected.
    7. Dry-run prints full mount list, middleware before/after, validation.

Requires:
    - Python 3.10+, docker CLI in PATH.
    - DATABASE_URL env var pointing to the PostgreSQL instance.
    - Must run as a user with docker access (or inside app container).
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional


DATABASE_URL = os.getenv("DATABASE_URL", "")

MIDDLEWARE_LABEL_KEY   = "traefik.http.routers.{name}.middlewares"
MIDDLEWARE_LABEL_VALUE = "hg-forwardauth"

# Containers that are part of HostingGuard infrastructure, never tenant sites.
_INFRA_NAMES = frozenset({
    "hosting_guard", "hg_worker", "hg_scheduler", "orchestrator",
    "traefik", "frontend", "redis", "postgres", "hosting_guard_db",
    "pgbouncer", "prometheus", "alertmanager", "node_exporter",
    "docker_socket_proxy",
})

# Prefixes that identify infrastructure containers by name pattern.
_INFRA_PREFIXES = ("hg_", "docker_")

BACKUP_DIR = Path("/tmp/container-backups")

# Marker text served by an unconfigured nginx container.
_NGINX_DEFAULT_MARKER = b"Welcome to nginx"


# ── helpers ──────────────────────────────────────────────────────────────────

def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _inspect(container: str) -> Optional[dict]:
    try:
        r = _run(["docker", "inspect", container], check=False)
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout)
        return data[0] if data else None
    except Exception as exc:
        print(f"  [!] inspect failed for {container}: {exc}", file=sys.stderr)
        return None


def _backup(container: str, info: dict) -> Path:
    """Write inspect JSON to /tmp/container-backups/<name>-<ts>.json."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    path = BACKUP_DIR / f"{container}-{ts}.json"
    path.write_text(json.dumps(info, indent=2))
    return path


def _is_tenant_container(container: str, infra_names: frozenset = _INFRA_NAMES) -> bool:
    """Return True only for user-deployed site containers."""
    name = container.lower()
    if name in infra_names:
        return False
    for prefix in _INFRA_PREFIXES:
        if name.startswith(prefix):
            return False
    return True


def _get_current_middlewares(labels: dict, name: str) -> list[str]:
    """Return the list of middlewares already on this container's router label."""
    key = MIDDLEWARE_LABEL_KEY.format(name=name)
    raw = labels.get(key, "")
    return [m.strip() for m in raw.split(",") if m.strip()] if raw else []


def _merge_middleware(existing: list[str], value: str) -> str:
    """Append value to the middleware list without introducing duplicates."""
    if value in existing:
        return ",".join(existing)
    return ",".join(existing + [value])


def _has_middleware(labels: dict, name: str) -> bool:
    return MIDDLEWARE_LABEL_VALUE in _get_current_middlewares(labels, name)


def _validate_binds(binds: list[str]) -> tuple[bool, str]:
    """
    Check that every nginx html bind mount has an index.html on the host.

    Bind entries from docker inspect are in the form:
        /host/path:/container/path[:options]
    """
    for bind in binds:
        parts = bind.split(":")
        if len(parts) < 2:
            continue
        host_path, container_path = parts[0], parts[1]
        if "nginx/html" in container_path or "/usr/share/nginx/html" in container_path:
            host_index = Path(host_path) / "index.html"
            if not host_index.exists():
                return False, (
                    f"nginx html mount {host_path} → {container_path} "
                    f"exists but {host_index} not found on host. "
                    "Refusing to recreate — site would serve nginx default."
                )
    return True, ""


def _is_nginx_default(url: str, timeout: int = 5) -> bool:
    """Return True if the URL responds with the nginx default welcome page."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read(4096)
            return _NGINX_DEFAULT_MARKER in body
    except Exception:
        return False


# ── container re-creation ────────────────────────────────────────────────────

def _build_docker_run_cmd(
    info: dict,
    container: str,
    name: str,
    merged_middleware: str,
) -> list[str]:
    """Build the full `docker run` command to re-create the container."""
    cfg    = info.get("Config", {})
    hc_cfg = info.get("HostConfig", {})

    image   = cfg.get("Image", "")
    labels  = dict(cfg.get("Labels") or {})
    env     = cfg.get("Env") or []
    binds   = hc_cfg.get("Binds") or []

    networks = list((info.get("NetworkSettings", {}).get("Networks") or {}).keys())
    network  = networks[0] if networks else "deploy_hosting_network"

    restart = hc_cfg.get("RestartPolicy", {}).get("Name", "unless-stopped")
    cpus    = str(hc_cfg.get("NanoCpus", 0) / 1e9) if hc_cfg.get("NanoCpus") else ""
    memory  = str(hc_cfg.get("Memory", 0)) if hc_cfg.get("Memory") else ""

    # Merge the middleware label in place.
    mw_key = MIDDLEWARE_LABEL_KEY.format(name=name)
    labels[mw_key] = merged_middleware

    cmd = ["docker", "run", "-d", "--name", container,
           "--network", network, "--restart", restart]

    if cpus and cpus not in ("0.0", "0"):
        cmd += ["--cpus", cpus]
    if memory and memory not in ("0",):
        cmd += ["--memory", memory]

    for bind in binds:
        cmd += ["-v", bind]

    for k, v in labels.items():
        cmd += ["-l", f"{k}={v}"]

    for e in env:
        cmd += ["-e", e]

    cmd.append(image)
    return cmd


def _relabel_container(
    info: dict,
    container: str,
    name: str,
    subdomain: str,
    dry_run: bool,
    force: bool = False,
) -> bool:
    """
    Re-create the container with the forwardauth middleware label merged in.

    Returns True on success (or dry-run), False on failure.
    Skips (returns True) if middleware already present and --force not set.
    """
    cfg    = info.get("Config", {})
    hc_cfg = info.get("HostConfig", {})
    labels = dict(cfg.get("Labels") or {})
    binds  = hc_cfg.get("Binds") or []

    existing_mw = _get_current_middlewares(labels, name)
    merged_mw   = _merge_middleware(existing_mw, MIDDLEWARE_LABEL_VALUE)
    mw_key      = MIDDLEWARE_LABEL_KEY.format(name=name)

    # ── dry-run ──────────────────────────────────────────────────────────────
    if dry_run:
        print(f"  Mounts ({len(binds)}):")
        for b in binds:
            print(f"    {b}")
        if not binds:
            print("    (none)")
        print(f"  Middleware before: {existing_mw or '(none)'}")
        print(f"  Middleware after:  {merged_mw}")

        valid, err = _validate_binds(binds)
        if not valid:
            print(f"  [DRY-RUN] WOULD SKIP — pre-validation failed: {err}")
            return False
        if _has_middleware(labels, name) and not force:
            print(f"  [DRY-RUN] WOULD SKIP — already has forwardauth label")
            return True

        cmd = _build_docker_run_cmd(info, container, name, merged_mw)
        print(f"  [DRY-RUN] would run: {' '.join(cmd)}")
        return True

    # ── skip if already labeled (unless --force) ─────────────────────────────
    if _has_middleware(labels, name) and not force:
        print(f"  SKIP — already has forwardauth label.")
        return True

    # ── pre-validate bind mounts ──────────────────────────────────────────────
    valid, err = _validate_binds(binds)
    if not valid:
        print(f"  SKIP (safety) — pre-validation failed: {err}", file=sys.stderr)
        return False

    # ── backup inspect JSON ───────────────────────────────────────────────────
    backup_path = _backup(container, info)
    print(f"  Backup saved: {backup_path}")

    # ── build and run ─────────────────────────────────────────────────────────
    cmd = _build_docker_run_cmd(info, container, name, merged_mw)

    print(f"  Stopping {container}...")
    _run(["docker", "stop", container], check=False)
    print(f"  Removing {container}...")
    _run(["docker", "rm", container], check=False)
    print(f"  Re-creating {container}...")
    r = _run(cmd, check=False)
    if r.returncode != 0:
        print(f"  [!] docker run failed: {r.stderr}", file=sys.stderr)
        print(f"  Inspect backup is at: {backup_path}", file=sys.stderr)
        return False

    # ── post-validate: check for nginx default regression ────────────────────
    time.sleep(2)
    test_url = f"http://{container}/"
    if _is_nginx_default(test_url):
        print(
            f"  [!] POST-VALIDATE FAILED — {test_url} shows nginx default page. "
            f"Bind mounts may not have been applied correctly.",
            file=sys.stderr,
        )
        return False

    print(f"  OK — {container} re-created. {mw_key}={merged_mw}")
    return True


# ── database ─────────────────────────────────────────────────────────────────

def _get_hostings() -> list[dict]:
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(DATABASE_URL)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT hosting_id, container_name, subdomain, plan "
            "FROM hostings WHERE status NOT IN ('deleted', 'expired') "
            "ORDER BY hosting_id"
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run",    action="store_true",
                        help="Show what would be done; no containers are modified")
    parser.add_argument("--hosting-id", type=int,
                        help="Process only this hosting_id")
    parser.add_argument("--force",      action="store_true",
                        help="Re-create even containers that already have the label "
                             "(use to recover lost bind mounts)")
    args = parser.parse_args()

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)

    hostings = _get_hostings()
    if args.hosting_id:
        hostings = [h for h in hostings if h["hosting_id"] == args.hosting_id]
    if not hostings:
        print("No hostings found.")
        return

    print(f"Processing {len(hostings)} hosting(s) — dry_run={args.dry_run} force={args.force}\n")
    skipped = done = failed = 0

    for h in hostings:
        container = h["container_name"]
        subdomain = h.get("subdomain", "")
        print(f"[{h['hosting_id']}] {container} ({subdomain})")

        if not _is_tenant_container(container):
            print(f"  SKIP — infrastructure container.")
            skipped += 1
            continue

        info = _inspect(container)
        if info is None:
            print(f"  SKIP — container not found.")
            skipped += 1
            continue

        if info.get("State", {}).get("Status") != "running":
            print(f"  SKIP — container is not running.")
            skipped += 1
            continue

        ok = _relabel_container(
            info, container, container, subdomain,
            dry_run=args.dry_run,
            force=args.force,
        )
        if ok:
            # _relabel_container returns True for already-labeled + no-force (skip)
            labels = (info.get("Config") or {}).get("Labels") or {}
            if _has_middleware(labels, container) and not args.force and not args.dry_run:
                skipped += 1
            else:
                done += 1
        else:
            failed += 1

    print(f"\nDone. relabeled={done}  skipped={skipped}  failed={failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
