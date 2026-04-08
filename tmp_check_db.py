
import os
os.environ["DATABASE_URL"] = "sqlite:///debug.db" # Usar SQLite para no romper prod en el test local
os.environ["JWT_SECRET"] = "dummy"

try:
    print("Attempting to run init_db...")
    from app.infra.audit.sqlite import init_db
    init_db()
    print("init_db successful!")
except Exception as e:
    print(f"CRITICAL: init_db failed: {e}")
    import traceback
    traceback.print_exc()
