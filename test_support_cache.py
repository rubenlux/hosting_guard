import asyncio
import os
from datetime import datetime
import json
from app.infra.audit.sqlite import init_db, get_connection
from app.infra.audit.support_cache_repository import SupportCacheRepository
from app.core.support_ai import _get_sub_intent, generate_support_response

# Seteamos sqlite como db para el test
os.environ["AUDIT_DB_PATH"] = "test_audit.sqlite"

def run_tests():
    print("Iniciando tests de Support Cache...")
    
    # 1. Inicializar BD
    init_db()
    repo = SupportCacheRepository()
    print("✓ Base de datos iniciada")

    # 2. Test intent fingerprint
    desc1 = "Mi sitio de WordPress está muy lento, da error 502 a veces."
    desc2 = "Ayuda! el sitio de wordpress esta re lento, tira error 502 constante."
    desc3 = "Quiero cambiar mi tarjeta de crédito."
    
    intent1 = _get_sub_intent(desc1)
    intent2 = _get_sub_intent(desc2)
    intent3 = _get_sub_intent(desc3)
    
    # Intent 1 y 2 deberían ser muy similares o idénticos si se usaran mismas palabras 
    # (aquí varian por stop words pero probemos cómo saca la huella)
    print(f"Huella 1: {intent1}")
    print(f"Huella 2: {intent2}")
    print(f"Huella 3: {intent3}")
    print("✓ Huellas generadas")

    # 3. Test insert y recuperar cache
    ai_resp_mock = "Parece que el servidor tiene alta carga. Prueba reiniciar."
    
    cid = repo.save_cache(
        category="Sitio lento",
        sub_intent=intent1,
        problem_summary=desc1,
        ai_response=ai_resp_mock,
        ttl_minutes=15,
        hosting_id=None
    )
    print(f"✓ Guardado en cache con ID: {cid}")

    # 4. Recuperar cache
    cached = repo.get_best_match("Sitio lento", intent1)
    assert cached is not None, "Debería haber un hit en cache"
    assert cached["ai_response"] == ai_resp_mock
    print("✓ Cache recuperado correctamente")

    # 5. Incrementar uso y puntaje
    score_antes = cached["score"]
    repo.increment_use(cid)
    cached2 = repo.get_best_match("Sitio lento", intent1)
    assert cached2["uses"] == 1
    assert cached2["score"] == score_antes + 1
    print(f"✓ Uso incrementado (Score: {cached2['score']}, Usos: {cached2['uses']})")

    # 6. Test Feedback positivo
    repo.record_feedback(cid, resolved=True)
    cached3 = repo.get_best_match("Sitio lento", intent1)
    assert cached3["resolutions"] == 1
    assert cached3["score"] == cached2["score"] + 10
    print(f"✓ Feedback positivo aplicado (Nuevo Score: {cached3['score']})")

    # 7. Test Feedback negativo
    repo.record_feedback(cid, resolved=False)
    cached4 = repo.get_best_match("Sitio lento", intent1)
    assert cached4["score"] == cached3["score"] - 20
    print(f"✓ Feedback negativo aplicado (Nuevo Score: {cached4['score']})")

    # 8. Test Invalidación por Hosting (mock hosting_id)
    cid2 = repo.save_cache("Sitio caído", intent1, desc1, "...", 15, hosting_id=123)
    cached_h = repo.get_best_match("Sitio caído", intent1, hosting_id=123)
    assert cached_h is not None

    repo.invalidate_by_hosting(123)
    cached_h_post = repo.get_best_match("Sitio caído", intent1, hosting_id=123)
    assert cached_h_post is None
    print("✓ Invalidación por hosting exitosa")

    print("\n✅ ¡Todos los tests locales pasaron exitosamente!")

if __name__ == "__main__":
    run_tests()
    # Limpiamos archivo temp de test
    try:
        os.remove("test_audit.sqlite")
        os.remove("test_audit.sqlite-wal")
        os.remove("test_audit.sqlite-shm")
    except:
        pass
