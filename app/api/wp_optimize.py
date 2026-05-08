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


_HG_MARKER = "HostingGuard: WordPress hardening"

# ── Nginx hardening config ────────────────────────────────────────────────────
_NGINX_HARDENING = """\
# HostingGuard: WordPress hardening — do not remove
# Block XML-RPC (brute-force amplification vector)
location = /xmlrpc.php {
    deny all;
    return 403;
}
# Rate-limit wp-login.php: 10 requests/minute per IP
limit_req_zone $binary_remote_addr zone=wplogin:10m rate=10r/m;
location = /wp-login.php {
    limit_req zone=wplogin burst=5 nodelay;
    limit_req_status 429;
    try_files $uri =404;
    fastcgi_pass 127.0.0.1:9000;
    include fastcgi_params;
    fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
}
"""
_NGINX_CONF_PATH = "/etc/nginx/conf.d/wp-hardening.conf"

# ── Apache hardening config ───────────────────────────────────────────────────
# Rate limiting for wp-login is handled by Traefik; here we only block xmlrpc.
_APACHE_HARDENING = """\
# HostingGuard: WordPress hardening — do not remove
# Block XML-RPC (brute-force amplification vector)
<LocationMatch "^/xmlrpc\\.php$">
    Require all denied
</LocationMatch>
"""
_APACHE_CONF_AVAILABLE = "/etc/apache2/conf-available/hostingguard-wp-hardening.conf"
_APACHE_CONF_NAME      = "hostingguard-wp-hardening"


def _harden_webserver(container: str, log=None) -> None:
    """Detect runtime webserver and apply idempotent WordPress hardening.

    - Apache2: writes conf-available + a2enconf + apache2ctl graceful
    - Nginx:   writes conf.d file + nginx -t + nginx -s reload
    - Unknown: logs a warning, does nothing (never crashes the caller)
    """
    def _log(msg: str) -> None:
        if log:
            log(msg)
        else:
            logger.info("[wp_harden:%s] %s", container, msg)

    try:
        # ── Detect webserver ─────────────────────────────────────────────────
        r_apache = _docker_exec(container, "pgrep", "-x", "apache2", timeout=5)
        r_nginx  = _docker_exec(container, "pgrep", "-x", "nginx",   timeout=5)
        is_apache = r_apache.returncode == 0
        is_nginx  = r_nginx.returncode == 0

        if not is_apache and not is_nginx:
            _log("  WARN harden_webserver: no apache2 or nginx process found — skipping")
            return

        if is_apache:
            _harden_apache(container, _log)
        else:
            _harden_nginx(container, _log)

    except Exception as exc:
        _log(f"  WARN harden_webserver exception: {exc}")


def _harden_apache(container: str, _log) -> None:
    """Apply hardening to an Apache2 container. Idempotent."""
    try:
        # Check if already hardened
        r = _docker_exec(container, "sh", "-c",
                         f"grep -q '{_HG_MARKER}' {_APACHE_CONF_AVAILABLE} 2>/dev/null && echo EXISTS",
                         timeout=5)
        if r.returncode == 0 and "EXISTS" in r.stdout:
            _log("  apache hardening already applied — skipping")
            return

        # Write the config file
        escaped = _APACHE_HARDENING.replace("'", "'\\''")
        r = _docker_exec(container, "sh", "-c",
                         f"printf '%s' '{escaped}' > {_APACHE_CONF_AVAILABLE}",
                         timeout=10)
        if r.returncode != 0:
            _log(f"  WARN apache hardening write failed: {r.stderr.strip()[:80]}")
            return

        # Enable the config
        r = _docker_exec(container, "a2enconf", _APACHE_CONF_NAME, timeout=10)
        if r.returncode != 0:
            _log(f"  WARN a2enconf failed: {r.stderr.strip()[:80]}")
            return

        # Test config syntax
        r = _docker_exec(container, "apache2ctl", "configtest", timeout=10)
        if r.returncode != 0:
            _log(f"  WARN apache2ctl configtest failed: {r.stderr.strip()[:80]}")
            _docker_exec(container, "a2disconf", _APACHE_CONF_NAME, timeout=5)
            return

        # Graceful reload (no dropped connections)
        r = _docker_exec(container, "apache2ctl", "graceful", timeout=15)
        if r.returncode == 0:
            _log("  ✓ Apache hardening applied (xmlrpc blocked via LocationMatch)")
        else:
            _log(f"  WARN apache2ctl graceful failed: {r.stderr.strip()[:80]}")
    except Exception as exc:
        _log(f"  WARN harden_apache exception: {exc}")


def _harden_nginx(container: str, _log) -> None:
    """Apply hardening to a Nginx container. Idempotent."""
    try:
        # Check if already hardened
        r = _docker_exec(container, "sh", "-c",
                         f"grep -q '{_HG_MARKER}' {_NGINX_CONF_PATH} 2>/dev/null && echo EXISTS",
                         timeout=5)
        if r.returncode == 0 and "EXISTS" in r.stdout:
            _log("  nginx hardening already applied — skipping")
            return

        # Write the config file
        escaped = _NGINX_HARDENING.replace("'", "'\\''")
        r = _docker_exec(container, "sh", "-c",
                         f"printf '%s' '{escaped}' > {_NGINX_CONF_PATH}",
                         timeout=10)
        if r.returncode != 0:
            _log(f"  WARN nginx hardening write failed: {r.stderr.strip()[:80]}")
            return

        # Test config before reload
        r = _docker_exec(container, "nginx", "-t", timeout=10)
        if r.returncode != 0:
            _log(f"  WARN nginx -t failed, removing hardening config: {r.stderr.strip()[:80]}")
            _docker_exec(container, "rm", "-f", _NGINX_CONF_PATH, timeout=5)
            return

        # Reload Nginx
        r = _docker_exec(container, "nginx", "-s", "reload", timeout=10)
        if r.returncode == 0:
            _log("  ✓ Nginx hardening applied (xmlrpc blocked, wp-login rate-limited)")
        else:
            _log(f"  WARN nginx reload failed: {r.stderr.strip()[:80]}")
    except Exception as exc:
        _log(f"  WARN harden_nginx exception: {exc}")


def optimize_wordpress(
    container: str,
    log: Optional[Callable[[str], None]] = None,
    auto_install: bool = False,
    install_url: str = "",
    install_title: str = "Mi Sitio",
    install_email: str = "",
    admin_password: str = "",
    user_id: int = 0,
    site_name: str = "",
) -> dict:
    """
    Idempotent optimization for any WordPress container.
    - Sets wp-config constants individually (safe to re-run, no grep guard)
    - Optionally runs wp core install if auto_install=True and WP is not yet set up
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
        if user_id:
            try:
                from app.services.notification_service import notify as _notify
                _notify(
                    user_id,
                    f"Optimización no completada: {site_name or container}",
                    "WordPress no respondió a tiempo durante la configuración inicial. "
                    "El sitio puede tardar unos minutos más en estar listo.",
                    category="wordpress", severity="warning", channel="dashboard",
                )
            except Exception:
                pass
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

    # ── 3. Ensure WordPress is fully installed ───────────────────────────────
    r = _docker_exec(container, "wp", "--allow-root", "core", "is-installed", timeout=20)
    if r.returncode != 0:
        if auto_install and install_url and install_email and admin_password:
            _log("  WordPress no instalado — ejecutando wp core install automáticamente...")
            install_cmd = [
                "wp", "--allow-root", "core", "install",
                f"--url={install_url}",
                f"--title={install_title}",
                "--admin_user=admin",
                f"--admin_password={admin_password}",
                f"--admin_email={install_email}",
                "--skip-email",
            ]
            r2 = _docker_exec(container, *install_cmd, timeout=60)
            if r2.returncode == 0:
                _log("  ✓ WordPress instalado automáticamente (usuario: admin)")
            else:
                err = r2.stderr.strip()[:120]
                _log(f"  WARN wp core install: {err}")
                result["errors"].append(f"wp core install: {err}")
                return result
        else:
            _log("  WordPress no instalado aún — wp-config listo, plugins diferidos")
            return result

    # ── 4. Redis Object Cache ─────────────────────────────────────────────────
    _log("Instalando Redis Object Cache...")
    r = _docker_exec(container, "wp", "--allow-root",
                     "plugin", "install", "redis-cache", "--activate", timeout=120)
    if r.returncode == 0:
        _docker_exec(container, "wp", "--allow-root", "redis", "enable", timeout=30)
        _log("  ✓ Redis Object Cache activado")
        result["redis_ok"] = True
        if user_id:
            try:
                from app.services.notification_service import notify as _notify
                _notify(
                    user_id,
                    f"Redis activado: {site_name or container}",
                    f"El caché de objetos Redis fue activado en '{site_name or container}'. "
                    "Esto mejora significativamente el rendimiento de tu sitio.",
                    category="wordpress", severity="success", channel="dashboard",
                )
            except Exception:
                pass
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
        if user_id:
            try:
                from app.services.notification_service import notify as _notify
                _notify(
                    user_id,
                    f"WP Super Cache activado: {site_name or container}",
                    f"El caché de páginas WP Super Cache fue activado en '{site_name or container}'. "
                    "Las páginas se sirven ahora como archivos estáticos.",
                    category="wordpress", severity="success", channel="dashboard",
                )
            except Exception:
                pass
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
    if user_id:
        try:
            from app.services.notification_service import notify as _notify
            _notify(user_id, f"Permisos corregidos: {site_name or container}",
                    f"Los permisos de archivos de '{site_name or container}' fueron corregidos (www-data).",
                    category="wordpress", severity="success", channel="dashboard")
        except Exception:
            pass

    # ── 8. DB optimize — skip-ssl because MariaDB containers run without SSL ─
    _log("Optimizando base de datos...")
    r = _docker_exec(
        container,
        "wp", "--allow-root", "db", "query",
        "OPTIMIZE TABLE wp_options, wp_posts, wp_postmeta, wp_comments, wp_commentmeta, wp_terms, wp_termmeta, wp_term_relationships, wp_term_taxonomy, wp_usermeta, wp_users;",
        timeout=120,
    )
    if r.returncode == 0:
        _log("  ✓ DB optimizada")
    else:
        _log(f"  WARN db optimize: {r.stderr.strip()[:80]}")

    # ── 9. Webserver hardening: block xmlrpc.php (Apache or Nginx) ──────────
    _harden_webserver(container, _log)

    _log("Optimización completada")
    if user_id:
        try:
            from app.services.notification_service import notify as _notify
            activated = []
            if result["redis_ok"]:      activated.append("Redis")
            if result["supercache_ok"]: activated.append("WP Super Cache")
            extras = f" ({', '.join(activated)} activo)" if activated else ""
            _notify(
                user_id,
                f"WordPress listo: {site_name or container}",
                f"La configuración de '{site_name or container}' fue completada.{extras} "
                "Tu sitio está optimizado y disponible.",
                category="wordpress", severity="success", channel="dashboard",
                action_url="/dashboard",
            )
        except Exception:
            pass
    return result
