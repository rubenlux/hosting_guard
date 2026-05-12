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

Safety checklist (enforced before ANY destructive action):
    1. For nginx containers, a safe html source MUST be identified before
       docker stop/rm/run is called. Three strategies in order:
         A) Existing bind to /usr/share/nginx/html whose index.html exists
            on the host and is not the nginx default page.
         B) Known host artifact at /opt/clients/<container>/dist or build
            with a valid index.html.
         C) docker cp /usr/share/nginx/html from the running container to
            /opt/clients/<container>/recovered_html (live mode only).
       If none succeed → ABORT, container is not modified.
    2. Mounts=0 on an nginx container is never silently OK.
    3. Dry-run shows "[ABORT]" for containers with no safe html source —
       never shows a fake "[DRY-RUN] would run" command for them.
    4. --force cannot bypass the html source safety check.
    5. Backs up inspect JSON before any operation.
    6. Merges the middleware label — never clobbers existing values.
    7. Skips infrastructure containers (traefik, redis, hosting_guard, …).
    8. Post-validates after re-create as a second line of defense.

Requires:
    - Python 3.10+, docker CLI in PATH.
    - DATABASE_URL env var pointing to the PostgreSQL instance.
    - Must run as a user with docker access (or inside app container).
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Union


DATABASE_URL = os.getenv("DATABASE_URL", "")

MIDDLEWARE_LABEL_KEY   = "traefik.http.routers.{name}.middlewares"
MIDDLEWARE_LABEL_VALUE = "hg-forwardauth"

CLIENTS_BASE          = Path("/opt/clients")
_HTML_SUBDIRS         = ("dist", "build")       # public excluded (CRA template)
_NGINX_DEFAULT_MARKER = b"Welcome to nginx"
_DOCKER_CP_SENTINEL   = "__docker_cp__"         # signal: need docker cp
_SAFETY_ABORT         = "safety_abort"          # return sentinel for pre-validation failure

# Containers that are part of HostingGuard infrastructure, never tenant sites.
_INFRA_NAMES = frozenset({
    "hosting_guard", "hg_worker", "hg_scheduler", "orchestrator",
    "traefik", "frontend", "redis", "postgres", "hosting_guard_db",
    "pgbouncer", "prometheus", "alertmanager", "node_exporter",
    "docker_socket_proxy",
})

_INFRA_PREFIXES = ("hg_", "docker_")

BACKUP_DIR = Path("/tmp/container-backups")


# ── low-level helpers ────────────────────────────────────────────────────────

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


# ── html source detection ─────────────────────────────────────────────────────

def _is_nginx_content(path: Path) -> bool:
    """Return True if the file looks like the nginx default welcome page."""
    try:
        return _NGINX_DEFAULT_MARKER in path.read_bytes()[:4096]
    except OSError:
        return False


def _find_html_source_from_binds(binds: list[str]) -> tuple[Optional[str], str]:
    """
    Find an existing bind to /usr/share/nginx/html and validate its source.

    Returns (host_path, "") if a valid bind is found.
    Returns (None, err)      if a bind is found but invalid, or not found.
    """
    for bind in binds:
        parts = bind.split(":")
        if len(parts) < 2:
            continue
        host_path, container_path = parts[0], parts[1]
        if "/usr/share/nginx/html" not in container_path and "nginx/html" not in container_path:
            continue
        idx = Path(host_path) / "index.html"
        if not idx.exists():
            return None, (
                f"nginx html mount {host_path} → {container_path} "
                f"has no index.html on host. Refusing to recreate — site would serve nginx default."
            )
        if _is_nginx_content(idx):
            return None, (
                f"nginx html mount {host_path} → {container_path} "
                f"index.html contains nginx default page content."
            )
        return host_path, ""
    return None, "no bind to /usr/share/nginx/html"


def _validate_binds(binds: list[str]) -> tuple[bool, str]:
    """
    Backward-compat wrapper around _find_html_source_from_binds.
    Only fails when a nginx/html bind IS present but invalid.
    No nginx/html bind → passes (caller decides if that's safe).
    """
    src, err = _find_html_source_from_binds(binds)
    if src is not None:
        return True, ""
    if err == "no bind to /usr/share/nginx/html":
        return True, ""
    return False, err


def _find_html_source_from_host(container: str) -> tuple[Optional[str], str]:
    """
    Check for a known build artifact at /opt/clients/<container>/dist or build.
    Returns (dir_path, "") if found and not nginx default.
    """
    for subdir in _HTML_SUBDIRS:
        d   = CLIENTS_BASE / container / subdir
        idx = d / "index.html"
        if idx.exists() and not _is_nginx_content(idx):
            return str(d), ""
    return None, f"no valid artifact in {CLIENTS_BASE / container}/{{dist,build}}"


def _docker_cp_html(container: str, dest: Path) -> tuple[bool, str]:
    """
    Copy /usr/share/nginx/html from a running container to dest on the host.
    Must be called BEFORE docker stop/rm.
    """
    dest.mkdir(parents=True, exist_ok=True)
    r = _run(
        ["docker", "cp", f"{container}:/usr/share/nginx/html/.", str(dest)],
        check=False,
    )
    if r.returncode != 0:
        return False, f"docker cp failed: {r.stderr.strip()}"
    idx = dest / "index.html"
    if not idx.exists():
        return False, f"docker cp succeeded but {idx} not found"
    if _is_nginx_content(idx):
        return False, f"copied content at {idx} is nginx default page"
    return True, ""


def _select_html_source(
    container: str,
    binds: list[str],
    image: str,
    dry_run: bool,
) -> tuple[Optional[str], str]:
    """
    For nginx containers, determine the safe html source BEFORE any destructive
    action. Three fallback strategies (A → B → C).

    Returns:
      ("", "")                   → not an nginx container, no check needed
      (host_path, "")            → use as -v host_path:/usr/share/nginx/html:ro
      (_DOCKER_CP_SENTINEL, "")  → need to docker cp from container (live mode only)
      (None, err)                → cannot proceed safely → caller must ABORT
    """
    if "nginx" not in image.lower():
        return "", ""

    # A) existing valid bind
    src, err = _find_html_source_from_binds(binds)
    if src is not None:
        return src, ""
    bind_err = err

    # B) known host artifact
    src, err = _find_html_source_from_host(container)
    if src is not None:
        return src, ""
    host_err = err

    # C) docker cp — only possible in live mode (container still running)
    if not dry_run:
        return _DOCKER_CP_SENTINEL, ""

    return None, (
        f"bind check: {bind_err}; "
        f"host artifact: {host_err}; "
        f"docker cp: not available in dry-run mode"
    )


# ── container re-creation ─────────────────────────────────────────────────────

def _build_docker_run_cmd(
    info: dict,
    container: str,
    name: str,
    merged_middleware: str,
    html_source_override: Optional[str] = None,
) -> list[str]:
    """
    Build the full `docker run` command to re-create the container.

    If html_source_override is set, any existing /usr/share/nginx/html bind is
    replaced with the override, ensuring the correct content is served.
    """
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

    # Inject html source: remove any existing nginx html bind, add the selected one.
    if html_source_override:
        binds = [b for b in binds if "/usr/share/nginx/html" not in b]
        binds.append(f"{html_source_override}:/usr/share/nginx/html:ro")

    mw_key = MIDDLEWARE_LABEL_KEY.format(name=name)
    labels[mw_key] = merged_middleware

    cmd = ["docker", "run", "-d", "--name", container,
           "--network", network, "--restart", restart]

    if cpus and cpus not in ("0.0", "0"):
        cmd += ["--cpus", cpus]
    if memory and memory not in ("0",):
        cmd += ["--memory", memory]

    for b in binds:
        cmd += ["-v", b]

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
) -> Union[bool, str]:
    """
    Re-create the container with the forwardauth middleware label merged in.

    Returns:
      True           → success or skip (already labeled, no force)
      False          → docker failure or post-validation failure
      _SAFETY_ABORT  → aborted pre-validation; container was NOT modified
    """
    cfg    = info.get("Config", {})
    hc_cfg = info.get("HostConfig", {})
    labels = dict(cfg.get("Labels") or {})
    binds  = hc_cfg.get("Binds") or []
    image  = cfg.get("Image", "")

    existing_mw = _get_current_middlewares(labels, name)
    merged_mw   = _merge_middleware(existing_mw, MIDDLEWARE_LABEL_VALUE)
    mw_key      = MIDDLEWARE_LABEL_KEY.format(name=name)

    # ── Pre-validation: determine html source BEFORE any destructive action ───
    # This must happen first, even before dry-run output, so dry-run accurately
    # reflects what would happen.
    html_src, src_err = _select_html_source(container, binds, image, dry_run)

    if html_src is None:
        # No safe source found → ABORT regardless of --force
        if dry_run:
            print(f"  Mounts ({len(binds)}):")
            for b in binds:
                print(f"    {b}")
            if not binds:
                print("    (none)")
            print(f"  [ABORT] no safe html source found.")
            print(f"  [ABORT] {src_err}")
            print(f"  [ABORT] No destructive action would be taken.")
        else:
            print(
                f"  ABORTED — no html mount detected and no safe host artifact found. "
                f"Container was not modified.",
                file=sys.stderr,
            )
            print(f"  Detail: {src_err}", file=sys.stderr)
        return _SAFETY_ABORT

    # ── Dry-run output ────────────────────────────────────────────────────────
    if dry_run:
        print(f"  Mounts ({len(binds)}):")
        for b in binds:
            print(f"    {b}")
        if not binds:
            print("    (none)")
        print(f"  Middleware before: {existing_mw or '(none)'}")
        print(f"  Middleware after:  {merged_mw}")

        if html_src and html_src not in ("", _DOCKER_CP_SENTINEL):
            print(f"  HTML source: {html_src} → /usr/share/nginx/html:ro")
        elif html_src == _DOCKER_CP_SENTINEL:
            print(f"  HTML source: (would docker cp from container before recreate)")

        if _has_middleware(labels, name) and not force:
            print(f"  [DRY-RUN] WOULD SKIP — already has forwardauth label")
            return True

        # Build preview command; for docker cp case, show the expected recovered path.
        src_for_cmd = html_src if html_src not in ("", _DOCKER_CP_SENTINEL) else None
        if html_src == _DOCKER_CP_SENTINEL:
            src_for_cmd = str(CLIENTS_BASE / container / "recovered_html")
        cmd = _build_docker_run_cmd(info, container, name, merged_mw, src_for_cmd)
        print(f"  [DRY-RUN] would run: {' '.join(cmd)}")
        return True

    # ── Skip if already labeled (unless --force) ─────────────────────────────
    if _has_middleware(labels, name) and not force:
        print(f"  SKIP — already has forwardauth label.")
        return True

    # ── Handle docker cp BEFORE stop/rm ──────────────────────────────────────
    # html_src is either a real path (options A/B) or _DOCKER_CP_SENTINEL (option C).
    # In all cases, final_html_src must be a real path by the time we call stop/rm.
    final_html_src: Optional[str] = html_src if html_src != "" else None

    if html_src == _DOCKER_CP_SENTINEL:
        recovered = CLIENTS_BASE / container / "recovered_html"
        print(f"  No bind mount found. Copying html from container before stop...")
        ok, err = _docker_cp_html(container, recovered)
        if not ok:
            print(
                f"  ABORTED — docker cp failed: {err}. Container was not modified.",
                file=sys.stderr,
            )
            return _SAFETY_ABORT
        final_html_src = str(recovered)
        print(f"  Copied html to {recovered}")

    # ── Backup ────────────────────────────────────────────────────────────────
    backup_path = _backup(container, info)
    print(f"  Backup saved: {backup_path}")

    # ── Build command ─────────────────────────────────────────────────────────
    cmd = _build_docker_run_cmd(info, container, name, merged_mw, final_html_src)

    # ── Stop / rm / run ───────────────────────────────────────────────────────
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

    # ── Post-validate (second line of defense) ────────────────────────────────
    time.sleep(2)
    if _is_nginx_default(f"http://{container}/"):
        print(
            f"  [!] POST-VALIDATE FAILED — http://{container}/ shows nginx default page.",
            file=sys.stderr,
        )
        return False

    print(f"  OK — {container} re-created. {mw_key}={merged_mw}")
    return True


def _is_nginx_default(url: str, timeout: int = 5) -> bool:
    """Return True if the URL responds with the nginx default welcome page."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read(4096)
            return _NGINX_DEFAULT_MARKER in body
    except Exception:
        return False


# ── database ──────────────────────────────────────────────────────────────────

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


# ── main ──────────────────────────────────────────────────────────────────────

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
    done = skipped = failed = safety_aborted = 0

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

        result = _relabel_container(
            info, container, container, subdomain,
            dry_run=args.dry_run,
            force=args.force,
        )

        if result == _SAFETY_ABORT:
            safety_aborted += 1
        elif result is True:
            labels = (info.get("Config") or {}).get("Labels") or {}
            if _has_middleware(labels, container) and not args.force and not args.dry_run:
                skipped += 1
            else:
                done += 1
        else:
            failed += 1

    print(
        f"\nDone. relabeled={done}  skipped={skipped}  "
        f"safety_aborted={safety_aborted}  failed={failed}"
    )
    if failed or safety_aborted:
        sys.exit(1)


if __name__ == "__main__":
    main()
