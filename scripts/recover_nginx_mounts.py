#!/usr/bin/env python3
"""
Recover nginx containers that lost their bind mounts (and now serve the
nginx default page instead of the user's deployed artifact).

Root cause: backfill_forwardauth.py (pre-fix) never preserved HostConfig.Binds
when re-creating containers. Affected containers have the correct labels but
no -v mount, so nginx serves its built-in default page.

Usage (run inside app container on production):
    python scripts/recover_nginx_mounts.py [--dry-run] [--container NAME]

What it does for each affected container:
    1. docker inspect to get current config.
    2. Detect expected bind: /opt/clients/<container>/dist:/usr/share/nginx/html:ro
    3. Verify /opt/clients/<container>/dist/index.html exists on host.
    4. Back up inspect JSON to /tmp/container-backups/<name>-<ts>-recover.json
    5. Stop / rm / docker run with the bind mount re-added.
    6. Post-validate: curl internal URL must NOT return nginx default.

Only targets nginx static-site containers (image contains "nginx").
Containers serving WordPress (image contains "wordpress"/"mariadb") are skipped.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional


CLIENTS_BASE   = Path("/opt/clients")
NGINX_HTML_DST = "/usr/share/nginx/html"
NGINX_BIND_TPL = "{host_dir}:" + NGINX_HTML_DST + ":ro"
BACKUP_DIR     = Path("/tmp/container-backups")

_NGINX_DEFAULT_MARKER = b"Welcome to nginx"

# Containers known to be broken (update / leave empty to rely on auto-detect).
KNOWN_BROKEN: list[str] = [
    "user_1_git_matrix-vite-ok_547dd4",
    "user_1_git_mi-test_0d3874",
]


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


def _backup(container: str, info: dict, suffix: str = "recover") -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    path = BACKUP_DIR / f"{container}-{ts}-{suffix}.json"
    path.write_text(json.dumps(info, indent=2))
    return path


def _is_nginx_default(url: str, timeout: int = 5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read(4096)
            return _NGINX_DEFAULT_MARKER in body
    except Exception:
        return False


def _needs_recovery(info: dict) -> bool:
    """True if the container is nginx but has no html bind mount."""
    image = (info.get("Config") or {}).get("Image", "").lower()
    if "nginx" not in image:
        return False
    binds = (info.get("HostConfig") or {}).get("Binds") or []
    return not any(NGINX_HTML_DST in b for b in binds)


def _recover(container: str, info: dict, dry_run: bool) -> bool:
    cfg    = info.get("Config", {})
    hc_cfg = info.get("HostConfig", {})

    image   = cfg.get("Image", "")
    labels  = dict(cfg.get("Labels") or {})
    env     = cfg.get("Env") or []
    binds   = list(hc_cfg.get("Binds") or [])

    networks = list((info.get("NetworkSettings", {}).get("Networks") or {}).keys())
    network  = networks[0] if networks else "deploy_hosting_network"
    restart  = hc_cfg.get("RestartPolicy", {}).get("Name", "unless-stopped")
    cpus     = str(hc_cfg.get("NanoCpus", 0) / 1e9) if hc_cfg.get("NanoCpus") else ""
    memory   = str(hc_cfg.get("Memory", 0)) if hc_cfg.get("Memory") else ""

    # Determine expected host dir for this container's artifact.
    host_dir = CLIENTS_BASE / container / "dist"
    bind_str = NGINX_BIND_TPL.format(host_dir=host_dir)

    print(f"  Expected host dir: {host_dir}")
    if not (host_dir / "index.html").exists():
        print(
            f"  ABORT — {host_dir}/index.html not found. "
            "Cannot recover without the build artifact.",
            file=sys.stderr,
        )
        return False

    if any(NGINX_HTML_DST in b for b in binds):
        print(f"  SKIP — container already has an html bind mount.")
        return True

    # Add the missing bind.
    all_binds = binds + [bind_str]

    cmd = ["docker", "run", "-d", "--name", container,
           "--network", network, "--restart", restart]
    if cpus and cpus not in ("0.0", "0"):
        cmd += ["--cpus", cpus]
    if memory and memory not in ("0",):
        cmd += ["--memory", memory]
    for b in all_binds:
        cmd += ["-v", b]
    for k, v in labels.items():
        cmd += ["-l", f"{k}={v}"]
    for e in env:
        cmd += ["-e", e]
    cmd.append(image)

    if dry_run:
        print(f"  [DRY-RUN] would add bind: {bind_str}")
        print(f"  [DRY-RUN] full command: {' '.join(cmd)}")
        return True

    backup_path = _backup(container, info)
    print(f"  Backup: {backup_path}")
    print(f"  Stopping {container}...")
    _run(["docker", "stop", container], check=False)
    print(f"  Removing {container}...")
    _run(["docker", "rm", container], check=False)
    print(f"  Re-creating with bind {bind_str}...")
    r = _run(cmd, check=False)
    if r.returncode != 0:
        print(f"  [!] docker run failed: {r.stderr}", file=sys.stderr)
        return False

    time.sleep(2)
    if _is_nginx_default(f"http://{container}/"):
        print(
            f"  [!] POST-VALIDATE FAILED — still serving nginx default.",
            file=sys.stderr,
        )
        return False

    print(f"  OK — {container} is serving artifact content.")
    return True


def _list_nginx_containers() -> list[str]:
    """List all running containers whose image contains 'nginx'."""
    r = _run(
        ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"],
        check=False,
    )
    names = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and "nginx" in parts[1].lower():
            names.append(parts[0])
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run",   action="store_true",
                        help="Show what would be done; no containers modified")
    parser.add_argument("--container", help="Process only this container name")
    args = parser.parse_args()

    if args.container:
        targets = [args.container]
    elif KNOWN_BROKEN:
        targets = list(KNOWN_BROKEN)
    else:
        targets = _list_nginx_containers()

    if not targets:
        print("No containers to process.")
        return

    print(f"Processing {len(targets)} container(s) — dry_run={args.dry_run}\n")
    done = failed = skipped = 0

    for container in targets:
        print(f"[container] {container}")
        info = _inspect(container)
        if info is None:
            print(f"  SKIP — not found.")
            skipped += 1
            continue
        if info.get("State", {}).get("Status") != "running":
            print(f"  SKIP — not running.")
            skipped += 1
            continue
        if not _needs_recovery(info):
            print(f"  SKIP — not an nginx container or already has html mount.")
            skipped += 1
            continue

        ok = _recover(container, info, dry_run=args.dry_run)
        if ok:
            done += 1
        else:
            failed += 1

    print(f"\nDone. recovered={done}  skipped={skipped}  failed={failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
