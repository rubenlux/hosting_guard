
import sys
import os

try:
    print("Checking app.repositories import...")
    import app.repositories.health_repo
    print("Import successful!")
except Exception as e:
    print(f"Import failed: {e}")
    import traceback
    traceback.print_exc()
