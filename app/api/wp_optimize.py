"""
Shared WordPress post-provision optimization.
Called after both: new WordPress creation AND backup import.
"""
import logging
import subprocess
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _docker_exec(container: str, *cmd, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "exec", container, *cmd],
        capture_output=True, text=True, timeout=timeout,
    )


def _wait_for_wp(container: str, max_wait: int = 240) -> bool:
    """
    Wait until the WordPress container is fully initialized and WP-CLI works.

    Two-phase approach:
    1. Wait for Apache/PHP to start (check process or HTTP on localhost).
    2. Wait for wp-config.php to exist (entrypoint generates it after DB is ready).
    Then confirm WP-CLI responds.
    """
    # Phase 1: wait for Apache to be running (up to max_wait/2 seconds)
    deadline_apache = max_wait // 2
    for i in range(deadline_apache // 5):
        r = _docker_exec(container, "pgrep", "-x", "apache2", timeout=5)
        if r.returncode == 0:
            logger.debug("[wp_optimize:%s] Apache up after ~%ds", container, i * 5)
            break
        time.sleep(5)
    else:
        logger.warning("[wp_optimize:%s] Apache never started — aborting wait", container)
        return False

    # Phase 2: wait for wp-config.php to exist (DB connection + entrypoint done)
    for i in range(30):  # up to 150 more seconds
        r = _docker_exec(container, "test", "-f", "/var/www/html/wp-config.php", timeout=5)
        if r.returncode == 0:
            logger.debug("[wp_optimize:%s] wp-config.php found after ~%ds", container, i * 5)
            break
        time.sleep(5)
    else:
        logger.warning("[wp_optimize:%s] wp-config.php never appeared", container)
        # Don't abort — still try WP-CLI below

    # Phase 3: confirm WP-CLI works (needed for wp config set)
    for i in range(12):  # up to 60 more seconds
        r = _docker_exec(container, "wp", "--allow-root", "--info", timeout=15)
        if r.returncode == 0:
            logger.debug("[wp_optimize:%s] WP-CLI ready", container)
            return True
        logger.debug(
            "[wp_optimize:%s] wp --info returned %d: %s",
            container, r.returncode,
            (r.stderr or r.stdout or "").strip()[:120],
        )
        time.sleep(5)

    logger.warning("[wp_optimize:%s] WP-CLI never responded — optimización omitida", container)
    return False


# Constants to write to wp-config.php.
# (name, value, --raw) — raw=True means PHP sees the native type (bool/int), not a string.
_WP_CONSTANTS = [
    ("FS_METHOD",       "direct", False),
    ("WP_CACHE",        "true",   True),
    ("WP_MEMORY_LIMIT", "256M",   False),
    ("WP_REDIS_HOST",   "redis",  False),
    ("WP_REDIS_PORT",   "6379",   True),
]


def optimize_wordpress(container: str, log: Optional[Callable[[str], None]] = None) -> dict:
    """
    Idempotent optimization for any WordPress container.
    - Sets wp-config constants individually (safe to re-run, no grep guard)
    - Installs Redis Object Cache + WP Super Cache
    - Flushes rewrite rules, cleans transients, fixes permissions

    Returns a result dict with keys:
      config_ok, redis_ok, supercache_ok, errors[]
    """
    def _log(msg: str):
        logger.info("[wp_optimize:%s] %s", container, msg)
        if log:
            log(msg)

    result = {"config_ok": False, "redis_ok": False, "supercache_ok": False, "errors": []}

    # ── 1. Wait for WordPress to be ready ────────────────────────────────────
    _log("Esperando que WordPress esté listo...")
    if not _wait_for_wp(container):
        msg = "WordPress no respondió en 120s — optimización omitida"
        _log(f"  WARN: {msg}")
        result["errors"].append(msg)
        return result
    _log("  ✓ WordPress listo")

    # ── 2. wp-config constants — one wp config set per constant (idempotent) ─
    _log("Configurando wp-config.php...")
    config_ok = True
    for key, value, raw in _WP_CONSTANTS:
        cmd = ["wp", "--allow-root", "config", "set", key, value, "--type=constant"]
        if raw:
            cmd.append("--raw")
        r = _docker_exec(container, *cmd, timeout=20)
        if r.returncode == 0:
            _log(f"  ✓ {key}")
        else:
            err = r.stderr.strip()[:120]
            _log(f"  WARN {key}: {err}")
            result["errors"].append(f"wp-config {key}: {err}")
            config_ok = False

    # Verify critical keys
    for key in ("FS_METHOD", "WP_REDIS_HOST", "WP_REDIS_PORT"):
        r = _docker_exec(container, "wp", "--allow-root", "config", "get", key, timeout=10)
        val = r.stdout.strip() if r.returncode == 0 else "ERROR"
        _log(f"  verify {key}={val}")

    result["config_ok"] = config_ok

    # ── 3. Redis Object Cache ─────────────────────────────────────────────────
    _log("Instalando Redis Object Cache...")
    r = _docker_exec(container, "wp", "--allow-root",
                     "plugin", "install", "redis-cache", "--activate", timeout=120)
    if r.returncode == 0:
        _docker_exec(container, "wp", "--allow-root", "redis", "enable", timeout=30)
        _log("  ✓ Redis Object Cache activado")
        result["redis_ok"] = True
    else:
        err = r.stderr.strip()[:80]
        _log(f"  WARN redis-cache: {err}")
        result["errors"].append(f"redis-cache: {err}")

    # ── 4. WP Super Cache ─────────────────────────────────────────────────────
    _log("Instalando WP Super Cache...")
    r = _docker_exec(container, "wp", "--allow-root",
                     "plugin", "install", "wp-super-cache", "--activate", timeout=120)
    if r.returncode == 0:
        _docker_exec(container, "wp", "--allow-root", "super-cache", "enable", timeout=30)
        # PHP simple mode (no mod_rewrite needed), gzip on, 1h cache expiry
        for opt, val in (
            ("wp_cache_mod_rewrite", "0"),
            ("wp_cache_compression", "1"),
            ("cache_max_time",       "3600"),
        ):
            _docker_exec(container, "wp", "--allow-root", "option", "update", opt, val, timeout=10)
        _log("  ✓ WP Super Cache activado y configurado")
        result["supercache_ok"] = True
    else:
        err = r.stderr.strip()[:80]
        _log(f"  WARN wp-super-cache: {err}")
        result["errors"].append(f"wp-super-cache: {err}")

    # ── 5. Flush rewrite rules ────────────────────────────────────────────────
    r = _docker_exec(container, "wp", "--allow-root", "rewrite", "flush", "--hard", timeout=20)
    if r.returncode == 0:
        _log("  ✓ Rewrite rules actualizadas")
    else:
        _log(f"  WARN rewrite flush: {r.stderr.strip()[:80]}")

    # ── 6. Clean transients from old data ────────────────────────────────────
    _docker_exec(container, "wp", "--allow-root", "transient", "delete", "--all", timeout=30)
    _log("  ✓ Transients limpiados")

    # ── 7. Fix ownership ──────────────────────────────────────────────────────
    _docker_exec(container, "chown", "-R", "www-data:www-data", "/var/www/html", timeout=30)
    _log("  ✓ Permisos ok")

    # ── 8. DB optimize ────────────────────────────────────────────────────────
    _log("Optimizando base de datos...")
    r = _docker_exec(container, "wp", "--allow-root", "db", "optimize", timeout=120)
    if r.returncode == 0:
        _log("  ✓ DB optimizada")
    else:
        _log(f"  WARN db optimize: {r.stderr.strip()[:80]}")

    _log("Optimización completada")
    return result
