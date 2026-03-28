import asyncio
from app.api.routes.hosting import list_hostings
from app.infra.audit.hosting_repository import HostingRepository
import sqlite3

def setup_test_data():
    conn = sqlite3.connect('audit_events.sqlite')
    cursor = conn.cursor()
    # Create a dummy user if not exists
    cursor.execute("INSERT OR IGNORE INTO users (user_id, email, hashed_password, created_at) VALUES (1, 'test@example.com', 'hash', 'today')")
    # Create a dummy hosting
    cursor.execute("""
        INSERT OR IGNORE INTO hostings (hosting_id, user_id, name, subdomain, container_name, plan, status, created_at) 
        VALUES (100, 1, 'Test Projekt', 'test.hostingguard.lat', 'test_container_abc', 'starter', 'active', 'today')
    """)
    conn.commit()
    conn.close()

async def test_list():
    setup_test_data()
    # Mock user dict
    user = {"user_id": 1, "email": "test@example.com"}
    
    print("Iniciando prueba de list_hostings...")
    try:
        results = await list_hostings(user)
        print("\n--- RESULTADOS API ---")
        for r in results:
            print(f"Proyecto: {r['name']}, Contenedor: {r['container_name']}, Status: {r['status']}")
            
        if results and results[0]['status'] == 'not_found' or results[0]['status'] == 'error':
             print("\n✅ PRUEBA EXITOSA: El sistema manejó correctamente la desconexión de Docker.")
        else:
             print("\n❌ PRUEBA FALLIDA: El sistema no detectó el estado de error de Docker.")
             
    except Exception as e:
        print(f"\n💥 ERROR CRÍTICO: El endpoint falló: {e}")

if __name__ == "__main__":
    asyncio.run(test_list())
