import asyncio
from app.api.routes.hosting import get_hosting_logs
import sqlite3

async def test_logs():
    # El usuario y el hosting ya fueron creados por el script anterior (id=1, hosting_id=100)
    user = {"user_id": 1, "email": "test@example.com"}
    
    print("Iniciando prueba de get_hosting_logs...")
    try:
        result = await get_hosting_logs(100, user)
        print("\n--- RESULTADO API LOGS ---")
        print(f"Logs: {result['logs']}")
        
        if "Error" in result['logs'] or "not found" in result['logs'].lower() or "No logs available" in result['logs']:
             print("\n✅ PRUEBA EXITOSA: El sistema manejó correctamente la ausencia de logs (o error de Docker).")
        else:
             print("\n❌ PRUEBA FALLIDA: El sistema devolvió algo inesperado.")
             
    except Exception as e:
        print(f"\n💥 ERROR CRÍTICO: El endpoint falló: {e}")

if __name__ == "__main__":
    asyncio.run(test_logs())
