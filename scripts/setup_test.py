from app.infra.audit.sqlite import init_db
from app.infra.audit.user_repository import UserRepository
from app.infra.audit.hosting_repository import HostingRepository
from passlib.context import CryptContext
from datetime import datetime
import os

# Contexto para hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def setup_test():
    # 1. Asegurar que la DB existe y tiene tablas nuevas
    init_db()
    
    user_repo = UserRepository()
    hosting_repo = HostingRepository()
    
    # 2. Crear usuario de prueba
    email = "test@hostingguard.lat"
    password = "password123"
    hashed = pwd_context.hash(password)
    
    print(f"--- SETUP TEST ---")
    try:
        user_id = user_repo.create_user(email, hashed)
        print(f"✅ Usuario creado: {email} (ID: {user_id})")
    except ValueError:
        user = user_repo.get_user_by_email(email)
        user_id = user["user_id"]
        print(f"ℹ️ Usuario ya existía (ID: {user_id})")
        
    # 3. Fondear cuenta y activar pagos
    user_repo.update_balance(user_id, 10.0) # $10 de saldo
    user_repo.update_payment_method(user_id, True)
    user_repo.update_autoscale(user_id, True)
    print(f"✅ Saldo fondeado: $10.00")
    print(f"✅ Pagos activados: Sí")
    print(f"✅ Auto-scaling habilitado: Sí")
    
    # 4. Crear Hosting para match con container 'test-app'
    # Limpiar hostings viejos si existen para 'test-app'
    hostings = hosting_repo.get_user_hostings(user_id)
    for h in hostings:
        if h["container_name"] == "test-app":
            hosting_repo.delete_hosting(h["hosting_id"], user_id)

    hosting_id = hosting_repo.create_hosting(
        user_id=user_id,
        name="Test Project",
        subdomain="test-app.hostingguard.lat",
        container_name="test-app",
        plan="starter"
    )
    print(f"✅ Tracking de hosting creado para 'test-app' (ID: {hosting_id})")
    print(f"------------------")
    print(f"🔥 LISTO PARA PRUEBA")
    print(f"1. Inicia el orquestador: python app/services/orchestrator.py")
    print(f"2. Inicia el container: docker run -d --name test-app nginx")
    print(f"3. Simula carga: docker exec test-app sh -c 'yes > /dev/null'")

if __name__ == "__main__":
    setup_test()
