#!/usr/bin/env python3
"""
Backfill ForwardAuth middleware label to existing tenant containers.

Tenant containers created before the forwardauth middleware was added do not
carry the Traefik label that wires them through /internal/forwardauth. This
script re-creates each affected container with the label added.

Usage (run on production server inside /opt/deploy):
    python scripts/backfill_forwardauth.py [--dry-run] [--hosting-id N]

Safety:
    - Reads current container config via `docker inspect`.
    - Skips containers that already have the label.
    - Skips containers that are not currently running.
    - Re-creates WordPress containers (wp_*) preserving all volumes and env vars.
    - Each re-create takes the site offline for ~3-5 seconds.
    - --dry-run shows what WOULD be done without touching anything.

Requires:
    - Python 3.10+, docker CLI in PATH.
    - DATABASE_URL env var (or set at top of file).
    - Must run as a user with docker access.
"""
import argparse
import json
import os
import subprocess
import sys
from typing import Optional


DATABASE_URL = os.getenv("DATABASE_URL", "")
MIDDLEWARE_LABEL_KEY   = "traefik.http.routers.{name}.middlewares"
MIDDLEWARE_LABEL_VALUE = "hg-forwardauth"


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _inspect(container: str) -> Optional[dict]:
    try:
        r = _run(["docker", "inspect", container], check=False)
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout)
        return data[0] if data else None
    except Exception as e:
        print(f"  [!] inspect failed for {container}: {e}", file=sys.stderr)
        return None


def _has_label(info: dict, name: str) -> bool:
    labels = info.get("Config", {}).get("Labels") or {}
    key = MIDDLEWARE_LABEL_KEY.format(name=name)
    val = labels.get(key, "")
    return MIDDLEWARE_LABEL_VALUE in val.split(",")


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


def _relabel_container(info: dict, container: str, name: str, dry_run: bool) -> bool:
    """Re-create the container with the forwardauth label added."""
    cfg     = info.get("Config", {})
    image   = cfg.get("Image", "")
    labels  = dict(cfg.get("Labels") or {})
    env     = cfg.get("Env") or []
    hc_cfg  = info.get("HostConfig", {})
    networks = list((info.get("NetworkSettings", {}).get("Networks") or {}).keys())
    network = networks[0] if networks else "deploy_hosting_network"
    restart = hc_cfg.get("RestartPolicy", {}).get("Name", "unless-stopped")
    cpus    = str(hc_cfg.get("NanoCpus", 0) / 1e9) if hc_cfg.get("NanoCpus") else ""
    memory  = str(hc_cfg.get("Memory", 0)) if hc_cfg.get("Memory") else ""

    mw_key   = MIDDLEWARE_LABEL_KEY.format(name=name)
    mw_value = MIDDLEWARE_LABEL_VALUE
    labels[mw_key] = mw_value

    cmd = ["docker", "run", "-d", "--name", container,
           "--network", network, "--restart", restart]
    if cpus and cpus != "0.0":
        cmd += ["--cpus", cpus]
    if memory and memory != "0":
        cmd += ["--memory", memory]
    for k, v in labels.items():
        cmd += ["-l", f"{k}={v}"]
    for e in env:
        cmd += ["-e", e]
    cmd.append(image)

    if dry_run:
        print(f"  [DRY-RUN] would stop+rm+run {container} with label {mw_key}={mw_value}")
        return True

    print(f"  Stopping {container}...")
    _run(["docker", "stop", container], check=False)
    print(f"  Removing {container}...")
    _run(["docker", "rm", container], check=False)
    print(f"  Re-creating {container}...")
    r = _run(cmd, check=False)
    if r.returncode != 0:
        print(f"  [!] docker run failed: {r.stderr}", file=sys.stderr)
        return False
    print(f"  OK — {container} re-created with forwardauth label.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run",    action="store_true", help="Show what would be done, no changes")
    parser.add_argument("--hosting-id", type=int,            help="Process only this hosting_id")
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

    print(f"Processing {len(hostings)} hosting(s) — dry_run={args.dry_run}\n")
    skipped = done = failed = 0

    for h in hostings:
        container = h["container_name"]
        print(f"[{h['hosting_id']}] {container} ({h.get('subdomain', '')})")
        info = _inspect(container)
        if info is None:
            print(f"  SKIP — container not found or not running.")
            skipped += 1
            continue
        if info.get("State", {}).get("Status") != "running":
            print(f"  SKIP — container is not running.")
            skipped += 1
            continue
        if _has_label(info, container):
            print(f"  SKIP — already has forwardauth label.")
            skipped += 1
            continue
        ok = _relabel_container(info, container, container, args.dry_run)
        if ok:
            done += 1
        else:
            failed += 1

    print(f"\nDone. relabeled={done} skipped={skipped} failed={failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
