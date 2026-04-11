import subprocess
import time
import os
from datetime import datetime
import sys
import threading
import logging

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger("hosting_guard_orchestrator")
logging.basicConfig(level=logging.INFO)

# Asegurar que el path incluye la raíz para los imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.infra.audit.hosting_repository import HostingRepository
from app.infra.audit.user_repository import UserRepository

hosting_repo = HostingRepository()
user_repo = UserRepository()

# 🔧 CONFIG GLOBAL
CHECK_INTERVAL = 10  # segundos
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"  # DRY_RUN=false para ejecución real

# 🛡️ CONTENEDORES DEL SISTEMA — JAMÁS SE TOCAN
# Lista de contenedores core que el orquestador NUNCA debe modificar ni reiniciar.
# Si el nombre de un contenedor está aquí, se ignora incondicionalmente.
PROTECTED_CONTAINERS = frozenset({
    "hosting_guard",    # API FastAPI principal
    "postgres",
    "hosting_guard_db", # alias del contenedor postgres
    "traefik",
    "redis",
    "prometheus",
    "docker_socket_proxy",
    "orchestrator",     # el propio proceso
    "frontend",
})

# 🔥 PLANES DEFINIDOS (Sincronizados con el resto de la app)
PLANS = {
    "free": {
        "cpu_limit": 0.25,
        "mem_limit": 256,
        "cpu_soft": 60,   # % de su limite
        "cpu_hard": 80,   # % de su limite
        "mem_hard": 85,   # % de su limite
    },
    "personal": {
        "cpu_limit": 0.50,
        "mem_limit": 512,
        "cpu_soft": 75,
        "cpu_hard": 90,
        "mem_hard": 90,
    },
    "negocio": {
        "cpu_limit": 1.00,
        "mem_limit": 1024,
        "cpu_soft": 85,
        "cpu_hard": 95,
        "mem_hard": 95,
    },
    "agencia": {
        "cpu_limit": 2.00,
        "mem_limit": 2048,
        "cpu_soft": 90,
        "cpu_hard": 98,
        "mem_hard": 98,
    }
}

# 💰 COSTOS Y LÍMITES DE AUTOSCALE
AUTOSCALE_CPU = 1.0
AUTOSCALE_RAM = "1024m"
AUTOSCALE_TIME = 600  # 10 minutos
AUTOSCALE_COST = -0.05 # 5 centavos por evento

def get_system_load():
    """Retorna el load average del sistema. En Windows retorna 0."""
    try:
        if hasattr(os, 'getloadavg'):
            return os.getloadavg()[0]
        return 0
    except OSError as e:
        logger.warning(f"No se pudo leer load average: {e}")
        return 0

# Prefijo que identifica contenedores gestionados por HostingGuard.
# El orquestador SOLO actúa sobre estos — nunca sobre contenedores del sistema.
_CONTAINER_PREFIX = "user_"


def _is_protected(name: str) -> bool:
    """Retorna True si el contenedor está en la lista de protegidos."""
    return name in PROTECTED_CONTAINERS or not name.startswith(_CONTAINER_PREFIX)


def _is_paid_plan(user_id: int) -> bool:
    """
    Centralized plan check. Returns True ONLY for users on paid plans.
    Uses the shared _get_user_cached() (TTL=60s) to avoid hitting the DB
    on every action call. Free plan → fail-safe False.
    """
    try:
        # NOTE: _get_user_cached is defined below — forward reference OK at runtime
        user = _get_user_cached(user_id)
        if not user:
            return False
        return user.get("plan", "free").lower() != "free"
    except Exception as e:
        logger.error(f"_is_paid_plan: error consultando plan de user_id={user_id}: {e}")
        return False  # Falla segura: sin datos → no ejecutar


def get_container_stats():
    """
    Lee estadísticas de Docker filtradas por prefijo 'user_'.
    Solo procesa contenedores creados por HostingGuard, evitando actuar sobre
    contenedores del sistema (traefik, postgres, etc.).
    DOBLE CHECK: filtra por prefijo AND por lista de protegidos.
    """
    result = subprocess.run(
        [
            "docker", "stats", "--no-stream",
            "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemPerc}}"
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    containers = []
    lines = result.stdout.strip().split("\n")
    for line in lines:
        if not line or "|" not in line:
            continue

        try:
            name, cpu, mem = line.split("|")
            name = name.strip()

            # ARCH-01: ignorar contenedores del sistema (doble capa)
            if _is_protected(name):
                continue

            cpu_val = float(cpu.replace("%", "").strip())
            mem_val = float(mem.replace("%", "").strip())

            containers.append({"name": name, "cpu": cpu_val, "mem": mem_val})
        except Exception:
            continue

    return containers

def throttle_container(name, user_id, cpu_limit, reason_type, cpu_pct=None, mem_pct=None):
    """Aplica límites de CPU dinámicamente y registra el evento."""
    # 🔒 BLOQUEO DE PLAN: throttle solo aplica a usuarios de pago
    if not _is_paid_plan(user_id):
        logger.info(f"⛔ BLOCKED (FREE PLAN) action=throttle container={name} user_id={user_id}")
        return

    risk = "critical" if reason_type == "panic" else "warning"
    if DRY_RUN:
        msg = f"[SIMULADO] Throttle → {cpu_limit} vCPU (Razón: {reason_type}, CPU: {cpu_pct}%, MEM: {mem_pct}%)"
        logger.info(f"[{datetime.now()}] [DRY_RUN] {msg}")
        hosting_repo.log_orchestrator_event(
            name, user_id, reason_type, msg,
            cpu_pct=cpu_pct, mem_pct=mem_pct, risk_level=risk, simulated=True
        )
        return

    logger.info(f"[{datetime.now()}] ⚡ LIMITANDO {name} → {cpu_limit} CPU")
    result = subprocess.run([
        "docker", "update",
        f"--cpus={cpu_limit}",
        name
    ], capture_output=True, text=True, timeout=15)

    if result.returncode != 0:
        logger.error(f"throttle_container falló para {name}: {result.stderr.strip()}")
        return

    msg = f"Uso elevado de recursos. Se aplicó limitación temporal a {cpu_limit} vCPU."
    if reason_type == "panic":
        msg = "Alta carga del servidor. Recursos reducidos temporalmente para proteger la estabilidad."

    risk = "critical" if reason_type == "panic" else "warning"
    hosting_repo.log_orchestrator_event(
        name, user_id, reason_type, msg,
        cpu_pct=None, mem_pct=None, risk_level=risk, simulated=False
    )

def restart_container(name, user_id, cpu_pct=None, mem_pct=None):
    """Reinicia un contenedor por exceso crítico de memoria y registra el evento."""
    # 🔒 BLOQUEO DE PLAN: restart solo aplica a usuarios de pago
    if not _is_paid_plan(user_id):
        logger.info(f"⛔ BLOCKED (FREE PLAN) action=restart container={name} user_id={user_id}")
        return

    if DRY_RUN:
        msg = f"[SIMULADO] Restart por RAM crítica (CPU: {cpu_pct}%, MEM: {mem_pct}%)"
        logger.info(f"[{datetime.now()}] [DRY_RUN] {msg}")
        hosting_repo.log_orchestrator_event(
            name, user_id, "restart", msg,
            cpu_pct=cpu_pct, mem_pct=mem_pct, risk_level="critical", simulated=True
        )
        return

    logger.info(f"[{datetime.now()}] 🔄 REINICIANDO {name} (Exceso crítico de RAM)")
    result = subprocess.run([
        "docker", "restart",
        name
    ], capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        logger.error(f"restart_container falló para {name}: {result.stderr.strip()}")
        return

    hosting_repo.log_orchestrator_event(
        name, user_id, "restart",
        "Uso crítico de memoria. El contenedor se reinició automáticamente para evitar fallos.",
        risk_level="critical", simulated=False
    )

def revert_scaling(name, user_id, original_cpu, original_mem):
    """Devuelve el contenedor a su estado original según plan."""
    if DRY_RUN:
        logger.info(f"[{datetime.now()}] [DRY_RUN] Would revert scaling for {name} to {original_cpu} CPU")
        return

    logger.info(f"[{datetime.now()}] 🔙 REVIRTIENDO {name} a límites de plan ({original_cpu} CPU)")
    try:
        result = subprocess.run([
            "docker", "update",
            f"--cpus={original_cpu}",
            f"--memory={original_mem}m",
            name
        ], capture_output=True, text=True, timeout=15)

        if result.returncode != 0:
            logger.error(f"revert_scaling falló para {name}: {result.stderr.strip()}")
        else:
            hosting_repo.log_orchestrator_event(name, user_id, "autoscale_revert", "Pico de tráfico superado. Recursos restaurados a los límites de tu plan.")
    except Exception as e:
        logger.error(f"Error en revert_scaling: {e}", exc_info=True)
    finally:
        # Limpiar el timer del registro para evitar acumulación de objetos muertos
        _active_timers.pop(name, None)

_active_timers: dict = {}

def apply_autoscale(name, user_id, rules, cpu_pct=None, mem_pct=None):
    """Aplica escalamiento temporal cobrando al usuario atómicamente."""
    # 🔒 BLOQUEO DE PLAN (CRÍTICO MÁXIMO): autoscale solo para planes de pago
    if not _is_paid_plan(user_id):
        logger.info(f"⛔ BLOCKED (FREE PLAN) action=autoscale container={name} user_id={user_id}")
        return

    if name in _active_timers and _active_timers[name].is_alive():
        return

    if DRY_RUN:
        msg = f"[SIMULADO] Autoscale por alta demanda (CPU: {cpu_pct}%, MEM: {mem_pct}%)"
        logger.info(f"[{datetime.now()}] [DRY_RUN] {msg}")
        hosting_repo.log_orchestrator_event(
            name, user_id, "autoscale", msg,
            cpu_pct=cpu_pct, mem_pct=mem_pct, risk_level="warning", simulated=True
        )
        return

    cost_abs = abs(AUTOSCALE_COST)
    if not user_repo.deduct_balance_if_sufficient(user_id, cost_abs):
        logger.warning(f"[{datetime.now()}] Saldo insuficiente para {name}.")
        return

    logger.info(f"[{datetime.now()}] 🚀 AUTOSCALING {name} (+Potencia temporal)")
    
    # 2. Aplicar recursos
    try:
        result = subprocess.run([
            "docker", "update",
            f"--cpus={AUTOSCALE_CPU}",
            f"--memory={AUTOSCALE_RAM}",
            name
        ], capture_output=True, text=True, timeout=15)
        
        if result.returncode != 0:
            logger.error(f"Autoscale falló para {name}: {result.stderr.strip()}")
            user_repo.update_balance(user_id, cost_abs) # Rollback
            return
            
        hosting_repo.log_orchestrator_event(
            name, user_id, "autoscale",
            f"Escalamiento automático activado por alta demanda. (+{AUTOSCALE_CPU} vCPU). Costo: ${cost_abs}",
            cpu_pct=cpu_pct, mem_pct=mem_pct, risk_level="warning", simulated=False
        )
        
        # 3. Programar reversión
        t = threading.Timer(
            AUTOSCALE_TIME, 
            revert_scaling, 
            args=[name, user_id, rules["cpu_limit"], rules["mem_limit"]]
        )
        t.start()
        _active_timers[name] = t
        
    except Exception as e:
        logger.error(f"Error aplicando autoscale: {e}")
        user_repo.update_balance(user_id, cost_abs)

_hosting_cache: dict = {}
_user_cache: dict = {}
CACHE_TTL = 60  # segundos

def _get_hosting_cached(name: str):
    entry = _hosting_cache.get(name)
    if entry and time.time() - entry["ts"] < CACHE_TTL:
        return entry["data"]
    data = hosting_repo.get_hosting_by_container(name)
    _hosting_cache[name] = {"data": data, "ts": time.time()}
    return data

def _get_user_cached(user_id: int):
    entry = _user_cache.get(user_id)
    if entry and time.time() - entry["ts"] < CACHE_TTL:
        return entry["data"]
    data = user_repo.get_user_by_id(user_id)
    _user_cache[user_id] = {"data": data, "ts": time.time()}
    return data

def handle_container(container):
    """Toma decisiones basadas en métricas y plan del usuario."""
    name = container["name"]
    cpu = container["cpu"]
    mem = container["mem"]

    # 🛡️ GUARDIA FINAL: si por cualquier razón un contenedor protegido llegó aquí,
    # se rechaza incondicionalmente. Esta línea NO debería ejecutarse nunca.
    if _is_protected(name):
        logger.critical("⛔ SECURITY BLOCK: intento de actuar sobre contenedor protegido '%s'. Ignorado.", name)
        return

    hosting = _get_hosting_cached(name)
    if not hosting:
        return

    user_id = hosting["user_id"]
    plan_name = hosting.get("plan", "free").lower()
    rules = PLANS.get(plan_name, PLANS["free"])

    user_data = _get_user_cached(user_id)
    sys_load = get_system_load()

    # --- 💰 LÓGICA DE MONETIZACIÓN (AUTOSCALE) ---
    # Si hay pico de uso y el server NO está saturado
    if (cpu > 85 or mem > 85) and sys_load < 4.0:
        if user_data.get("autoscale_enabled") and user_data.get("has_payment_method") and user_data.get("balance", 0) > 0:
            apply_autoscale(name, user_id, rules, cpu_pct=cpu, mem_pct=mem)
            return

    # --- 🛡️ LÓGICA DE PROTECCIÓN (THROTTLE/RESTART) ---
    # 🚨 PROTECCIÓN DE SISTEMA: Si el server está saturado (> Load 4), bajamos Free al 50%
    if sys_load > 4.0 and plan_name == "free":
        logger.warning(f"⚠️ Servidor Saturado (L:{sys_load}). Penalizando Free: {name}")
        throttle_container(name, user_id, rules["cpu_limit"] * 0.5, "panic", cpu_pct=cpu, mem_pct=mem)
        return

    # 🚨 RAM CRÍTICA
    if mem > rules["mem_hard"]:
        restart_container(name, user_id, cpu_pct=cpu, mem_pct=mem)
        return

    # 🔥 CPU ABUSO DE SU PROPIO PLAN
    if cpu > rules["cpu_hard"]:
        throttle_container(name, user_id, rules["cpu_limit"] * 0.5, "throttle", cpu_pct=cpu, mem_pct=mem)
        return

    # ⚠️ CPU ELEVADA (Dentro de su plan)
    if cpu > rules["cpu_soft"]:
        throttle_container(name, user_id, rules["cpu_limit"], "soft_limit", cpu_pct=cpu, mem_pct=mem)
        return

def run_orchestrator():
    """Loop principal del orquestador."""
    logger.info("-----------------------------------------")
    logger.info(f"🚀 HostingGuard Intelligent Orchestrator")
    logger.info(f"[{datetime.now()}] Iniciando monitoreo...")
    logger.info(f"Orchestrator mode: {'DRY_RUN' if DRY_RUN else 'EXECUTION'}")
    logger.info("-----------------------------------------")
    
    consecutive_errors = 0
    while True:
        try:
            containers = get_container_stats()
            consecutive_errors = 0
            for c in containers:
                handle_container(c)
        except Exception as e:
            consecutive_errors += 1
            wait = min(CHECK_INTERVAL * (2 ** consecutive_errors), 300)
            logger.error(f"❌ Error en el loop del orchestrator (intento {consecutive_errors}): {e}. Esperando {wait}s")
            time.sleep(wait)
            continue

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    LOCK_FILE = "/tmp/orchestrator.lock"

    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            if psutil and psutil.pid_exists(pid):
                logger.critical("Orchestrator already running (pid=%d). Exiting.", pid)
                sys.exit(1)
            else:
                logger.warning("Stale lock file detected (pid=%d no longer exists). Removing.", pid)
                os.remove(LOCK_FILE)
        except Exception:
            # Lock corrupto o ilegible — remover y continuar
            os.remove(LOCK_FILE)

    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
            f.flush()
            os.fsync(f.fileno())  # garantiza persistencia ante crash inmediato
        run_orchestrator()
    finally:
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass
