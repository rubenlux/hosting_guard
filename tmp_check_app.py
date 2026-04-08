
try:
    print("Attempting to import app.api.main...")
    from app.api.main import app
    print("App import successful!")
except Exception as e:
    print(f"CRITICAL: App failed to import: {e}")
    import traceback
    traceback.print_exc()
