"""
Periodic resource usage collector.

Runs every 60 s (via scheduler_runner). Executes `docker stats --no-stream`
for every active hosting container and writes one row per container to
hosting_resource_samples so the admin dashboard can display CPU/RAM trends.
"""
import json
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

_STATS_FORMAT = (
    '{"name":"{{.Name}}",'
    '"cpu":"{{.CPUPerc}}",'
    '"mem":"{{.MemUsage}}",'
    '"net":"{{.NetIO}}"}'
)


def _parse_pct(val: str) -> Optional[float]:
    """'12.34%' → 12.34"""
    try:
        return float(val.strip().rstrip("%"))
    except (ValueError, AttributeError):
        return None


def _parse_mb(val: str) -> Optional[float]:
    """'128MiB', '1.2GiB', '512kB' → float MiB"""
    try:
        v = val.strip()
        if "GiB" in v:
            return float(v.replace("GiB", "")) * 1024
        if "MiB" in v:
            return float(v.replace("MiB", ""))
        if "kB" in v:
            return float(v.replace("kB", "")) / 1024
        if "MB" in v:
            return float(v.replace("MB", ""))
        if "GB" in v:
            return float(v.replace("GB", "")) * 1024
        return None
    except (ValueError, AttributeError):
        return None


def _parse_mem_usage(mem_str: str):
    """'128MiB / 512MiB' → (used_mb, limit_mb)"""
    try:
        parts = mem_str.split("/")
        used  = _parse_mb(parts[0])
        limit = _parse_mb(parts[1]) if len(parts) > 1 else None
        return used, limit
    except Exception:
        return None, None


def _parse_net(net_str: str):
    """'1.2MB / 340kB' → (rx_mb, tx_mb)"""
    try:
        parts = net_str.split("/")
        rx = _parse_mb(parts[0])
        tx = _parse_mb(parts[1]) if len(parts) > 1 else None
        return rx, tx
    except Exception:
        return None, None


def _parse_du_output(output: str) -> Optional[float]:
    """Parse first line of 'du -sm' output → MB as float, or None.

    du -sm outputs '<size_mb>\\t<path>' or '<size_mb> <path>'.
    '90\\t/var/www/html' → 90.0
    '6 /usr/share/nginx/html' → 6.0
    empty / error text → None
    """
    if not output:
        return None
    try:
        first_line = output.strip().splitlines()[0]
        return float(first_line.split()[0])
    except (ValueError, IndexError):
        return None


def _collect_disk_mb(container_name: str) -> Optional[float]:
    """Return real site disk usage in MB via du -sm (never df).

    df reports filesystem-level usage, which is the same for every container
    on a shared volume. du -sm measures only the site's own directory tree.

    Tries three paths in order:
    1. WordPress webroot inside container  (/var/www/html)
    2. Host path                           (/opt/clients/<container>)
    3. Static/nginx webroot inside container (/usr/share/nginx/html)
    Returns None and logs a warning with all paths tried + stderr on failure.
    """
    failures: list[str] = []

    def _du_inside(path: str) -> Optional[float]:
        try:
            r = subprocess.run(
                ["docker", "exec", container_name, "du", "-sm", path],
                capture_output=True, text=True, timeout=10,
            )
            mb = _parse_du_output(r.stdout) if r.returncode == 0 else None
            if mb is None:
                failures.append(
                    f"container:{path} rc={r.returncode} stderr={r.stderr.strip()[:120]!r}"
                )
            return mb
        except Exception as exc:
            failures.append(f"container:{path} exc={exc}")
            return None

    def _du_host(path: str) -> Optional[float]:
        try:
            r = subprocess.run(
                ["du", "-sm", path],
                capture_output=True, text=True, timeout=10,
            )
            mb = _parse_du_output(r.stdout) if r.returncode == 0 else None
            if mb is None:
                failures.append(
                    f"host:{path} rc={r.returncode} stderr={r.stderr.strip()[:120]!r}"
                )
            return mb
        except Exception as exc:
            failures.append(f"host:{path} exc={exc}")
            return None

    mb = _du_inside("/var/www/html")
    if mb is not None:
        return mb

    mb = _du_host(f"/opt/clients/{container_name}")
    if mb is not None:
        return mb

    mb = _du_inside("/usr/share/nginx/html")
    if mb is not None:
        return mb

    logger.warning(
        "collect_resource_usage: disk measurement failed for container=%s — %s",
        container_name, " | ".join(failures),
    )
    return None


def collect_resource_usage() -> None:
    """Collect docker stats for all active hosting containers and persist samples."""
    from app.infra.db import get_connection, release_connection

    # 1. Fetch active hostings: hosting_id + user_id + container_name
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT hosting_id, user_id, container_name FROM hostings
               WHERE status NOT IN ('deleted','expired') AND container_name IS NOT NULL"""
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)

    if not rows:
        return

    # 2. Run docker stats (single shot) for all containers at once
    container_names = [r["container_name"] for r in rows]
    name_to_info = {r["container_name"]: r for r in rows}

    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", _STATS_FORMAT] + container_names,
            capture_output=True, text=True, timeout=30,
        )
        output = result.stdout.strip()
    except Exception as exc:
        logger.warning("collect_resource_usage: docker stats failed: %s", exc)
        return

    if not output:
        return

    # 3. Parse each line (one JSON object per container)
    samples = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        cname = data.get("name", "").lstrip("/")
        info  = name_to_info.get(cname)
        if info is None:
            continue

        cpu_pct           = _parse_pct(data.get("cpu", ""))
        mem_used, mem_lim = _parse_mem_usage(data.get("mem", ""))
        net_rx, net_tx    = _parse_net(data.get("net", ""))

        samples.append((
            info["hosting_id"], info["user_id"], cname,
            cpu_pct, mem_used, mem_lim, net_rx, net_tx,
        ))

    if not samples:
        return

    # 3b. Disk usage — use du -sm (real site bytes), NOT df (reports filesystem usage).
    # df measures the whole filesystem, not the site — all containers on the same
    # volume show the same number. du measures only the site directory.
    disk_by_container: dict = {}
    for _, _, cname, _, _, _, _, _ in samples:
        disk_by_container[cname] = _collect_disk_mb(cname)

    # 4. Insert samples one by one (_AdaptedCursor does not support executemany)
    _INSERT = (
        "INSERT INTO hosting_resource_samples"
        " (hosting_id, user_id, container_name, cpu_pct, mem_mb, mem_limit_mb, net_rx_mb, net_tx_mb, disk_mb)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )
    conn = get_connection()
    try:
        cur = conn.cursor()
        for row in samples:
            disk_mb = disk_by_container.get(row[2])  # row[2] = container_name
            cur.execute(_INSERT, (*row, disk_mb))
        conn.commit()
        logger.info("collect_resource_usage: inserted %d samples", len(samples))
    except Exception as exc:
        logger.warning("collect_resource_usage: insert failed: %s", exc)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        release_connection(conn)

    # 5. Prune old samples (keep 24h to prevent unbounded growth)
    conn2 = get_connection()
    try:
        cur2 = conn2.cursor()
        cur2.execute(
            "DELETE FROM hosting_resource_samples WHERE sampled_at < NOW() - INTERVAL '24 hours'"
        )
        conn2.commit()
    except Exception:
        try:
            conn2.rollback()
        except Exception:
            pass
    finally:
        release_connection(conn2)
