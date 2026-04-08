import traceback

try:
    from app.api.main import app
    print("IMPORT OK", app.title)
except Exception as e:
    print("IMPORT FAIL", type(e).__name__, e)
    traceback.print_exc()
