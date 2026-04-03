import subprocess
import time
import os
from datetime import datetime
import sys
import threading
import logging

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


def get_container_stats():
    """
    Lee estadísticas de Docker filtradas por prefijo 'user_'.
    Solo procesa contenedores creados por HostingGuard, evitando actuar sobre
    contenedores del sistema (traefik, prometheus, etc.).
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

            # ARCH-01: ignorar contenedores que no sean de usuarios
            if not name.startswith(_CONTAINER_PREFIX):
                continue

            cpu_val = float(cpu.replace("%", "").strip())
            mem_val = float(mem.replace("%", "").strip())

            containers.append({"name": name, "cpu": cpu_val, "mem": mem_val})
        except Exception:
            continue

    return containers

def throttle_container(name, user_id, cpu_limit, reason_type):
    """Aplica límites de CPU dinámicamente y registra el evento."""
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

    hosting_repo.log_orchestrator_event(name, user_id, reason_type, msg)

def restart_container(name, user_id):
    """Reinicia un contenedor por exceso crítico de memoria y registra el evento."""
    logger.info(f"[{datetime.now()}] 🔄 REINICIANDO {name} (Exceso crítico de RAM)")
    result = subprocess.run([
        "docker", "restart",
        name
    ], capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        logger.error(f"restart_container falló para {name}: {result.stderr.strip()}")
        return

    hosting_repo.log_orchestrator_event(name, user_id, "restart", "Uso crítico de memoria. El contenedor se reinició automáticamente para evitar fallos.")

def revert_scaling(name, user_id, original_cpu, original_mem):
    """Devuelve el contenedor a su estado original según plan."""
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

def apply_autoscale(name, user_id, rules):
    """Aplica escalamiento temporal cobrando al usuario atómicamente."""
    if name in _active_timers and _active_timers[name].is_alive():
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
            f"Escalamiento automático activado por alta demanda. (+{AUTOSCALE_CPU} vCPU). Costo: ${cost_abs}"
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
            apply_autoscale(name, user_id, rules)
            return

    # --- 🛡️ LÓGICA DE PROTECCIÓN (THROTTLE/RESTART) ---
    # 🚨 PROTECCIÓN DE SISTEMA: Si el server está saturado (> Load 4), bajamos Free al 50%
    if sys_load > 4.0 and plan_name == "free":
        logger.warning(f"⚠️ Servidor Saturado (L:{sys_load}). Penalizando Free: {name}")
        throttle_container(name, user_id, rules["cpu_limit"] * 0.5, "panic")
        return

    # 🚨 RAM CRÍTICA
    if mem > rules["mem_hard"]:
        restart_container(name, user_id)
        return

    # 🔥 CPU ABUSO DE SU PROPIO PLAN
    if cpu > rules["cpu_hard"]:
        throttle_container(name, user_id, rules["cpu_limit"] * 0.5, "throttle")
        return

    # ⚠️ CPU ELEVADA (Dentro de su plan)
    if cpu > rules["cpu_soft"]:
        throttle_container(name, user_id, rules["cpu_limit"], "soft_limit")
        return

def run_orchestrator():
    """Loop principal del orquestador."""
    logger.info("-----------------------------------------")
    logger.info(f"🚀 HostingGuard Intelligent Orchestrator")
    logger.info(f"[{datetime.now()}] Iniciando monitoreo...")
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
    run_orchestrator()
