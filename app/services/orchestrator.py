import subprocess
import time
import os
from datetime import datetime
import sys
import threading

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
    "starter": {
        "cpu_limit": 0.25,
        "mem_limit": 256,
        "cpu_soft": 60,   # % de su limite
        "cpu_hard": 80,   # % de su limite
        "mem_hard": 85,   # % de su limite
    },
    "growth": {
        "cpu_limit": 0.50,
        "mem_limit": 512,
        "cpu_soft": 75,
        "cpu_hard": 90,
        "mem_hard": 90,
    },
    "pro": {
        "cpu_limit": 1.00,
        "mem_limit": 1024,
        "cpu_soft": 85,
        "cpu_hard": 95,
        "mem_hard": 95,
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
    except:
        return 0

def get_container_stats():
    """Lee estadísticas reales de Docker sin streaming."""
    result = subprocess.run(
        [
            "docker", "stats", "--no-stream",
            "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemPerc}}"
        ],
        capture_output=True,
        text=True
    )

    containers = []
    lines = result.stdout.strip().split("\n")
    for line in lines:
        if not line or "|" not in line:
            continue

        try:
            name, cpu, mem = line.split("|")
            cpu_val = float(cpu.replace("%", "").strip())
            mem_val = float(mem.replace("%", "").strip())

            containers.append({
                "name": name,
                "cpu": cpu_val,
                "mem": mem_val
            })
        except Exception as e:
            continue

    return containers

def throttle_container(name, user_id, cpu_limit, reason_type):
    """Aplica límites de CPU dinámicamente y registra el evento."""
    print(f"[{datetime.now()}] ⚡ LIMITANDO {name} → {cpu_limit} CPU")
    subprocess.run([
        "docker", "update",
        f"--cpus={cpu_limit}",
        name
    ], capture_output=True)
    
    msg = f"Uso elevado de recursos. Se aplicó limitación temporal a {cpu_limit} vCPU."
    if reason_type == "panic":
        msg = "Alta carga del servidor. Recursos reducidos temporalmente para proteger la estabilidad."
        
    hosting_repo.log_orchestrator_event(name, user_id, reason_type, msg)

def restart_container(name, user_id):
    """Reinicia un contenedor por exceso crítico de memoria y registra el evento."""
    print(f"[{datetime.now()}] 🔄 REINICIANDO {name} (Exceso crítico de RAM)")
    subprocess.run([
        "docker", "restart",
        name
    ], capture_output=True)
    
    hosting_repo.log_orchestrator_event(name, user_id, "restart", "Uso crítico de memoria. El contenedor se reinició automáticamente para evitar fallos.")

def revert_scaling(name, user_id, original_cpu, original_mem):
    """Devuelve el contenedor a su estado original según plan."""
    print(f"[{datetime.now()}] 🔙 REVIRTIENDO {name} a límites de plan ({original_cpu} CPU)")
    try:
        subprocess.run([
            "docker", "update",
            f"--cpus={original_cpu}",
            f"--memory={original_mem}m",
            name
        ], capture_output=True)
        hosting_repo.log_orchestrator_event(name, user_id, "autoscale_revert", "Pico de tráfico superado. Recursos restaurados a los límites de tu plan.")
    except Exception as e:
        print(f"Error en revert_scaling: {e}")

def apply_autoscale(name, user_id, rules):
    """Aplica escalamiento temporal cobrando al usuario."""
    print(f"[{datetime.now()}] 🚀 AUTOSCALING {name} (+Potencia temporal)")
    
    # 1. Cobrar
    user_repo.update_balance(user_id, AUTOSCALE_COST)
    
    # 2. Aplicar recursos
    try:
        subprocess.run([
            "docker", "update",
            f"--cpus={AUTOSCALE_CPU}",
            f"--memory={AUTOSCALE_RAM}",
            name
        ], capture_output=True)
        
        hosting_repo.log_orchestrator_event(
            name, user_id, "autoscale", 
            f"Escalamiento automático activado por alta demanda. (+{AUTOSCALE_CPU} vCPU). Costo: ${abs(AUTOSCALE_COST)}"
        )
        
        # 3. Programar reversión
        threading.Timer(
            AUTOSCALE_TIME, 
            revert_scaling, 
            args=[name, user_id, rules["cpu_limit"], rules["mem_limit"]]
        ).start()
        
    except Exception as e:
        print(f"Error aplicando autoscale: {e}")

def handle_container(container):
    """Toma decisiones basadas en métricas y plan del usuario."""
    name = container["name"]
    cpu = container["cpu"]
    mem = container["mem"]

    # Obtenemos el plan real de la DB
    hosting = hosting_repo.get_hosting_by_container(name)
    if not hosting:
        # No es un contenedor gestionado por nosotros
        return

    user_id = hosting["user_id"]
    plan_name = hosting.get("plan", "starter").lower()
    rules = PLANS.get(plan_name, PLANS["starter"])

    user_data = user_repo.get_user_by_id(user_id)
    sys_load = get_system_load()

    # --- 💰 LÓGICA DE MONETIZACIÓN (AUTOSCALE) ---
    # Si hay pico de uso y el server NO está saturado
    if (cpu > 85 or mem > 85) and sys_load < 4.0:
        if user_data.get("autoscale_enabled") and user_data.get("has_payment_method") and user_data.get("balance", 0) > 0:
            apply_autoscale(name, user_id, rules)
            return

    # --- 🛡️ LÓGICA DE PROTECCIÓN (THROTTLE/RESTART) ---
    # 🚨 PROTECCIÓN DE SISTEMA: Si el server está saturado (> Load 4), bajamos Starter al 50%
    if sys_load > 4.0 and plan_name == "starter":
        print(f"⚠️ Servidor Saturado (L:{sys_load}). Penalizando Starter: {name}")
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
    print("-----------------------------------------")
    print(f"🚀 HostingGuard Intelligent Orchestrator")
    print(f"[{datetime.now()}] Iniciando monitoreo...")
    print("-----------------------------------------")
    
    while True:
        try:
            containers = get_container_stats()
            for c in containers:
                handle_container(c)
        except Exception as e:
            print(f"❌ Error en el loop del orchestrator: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_orchestrator()
