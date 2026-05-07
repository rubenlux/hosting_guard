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

    # 3b. Disk usage — best-effort df per container (5 s timeout, no hard failure)
    disk_by_container: dict = {}
    for _, _, cname, _, _, _, _, _ in samples:
        try:
            r = subprocess.run(
                ["docker", "exec", cname, "df", "-k", "/var/www/html"],
                capture_output=True, text=True, timeout=5,
            )
            for df_line in r.stdout.splitlines()[1:]:
                parts = df_line.split()
                if len(parts) >= 3:
                    disk_by_container[cname] = int(parts[2]) / 1024.0  # KB used → MB
                    break
        except Exception:
            pass

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
