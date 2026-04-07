import os
os.environ["JWT_SECRET"] = "test_secret"
os.environ["DATABASE_URL"] = "sqlite:///test.db"

import sqlite3
from fastapi.testclient import TestClient
from app.api.main import app
from app.infra.audit.user_repository import UserRepository

client = TestClient(app)

# Setup initial clean test DB
if os.path.exists("test.db"):
    os.remove("test.db")

# Run migrations (assuming they run on init or we can instantiate repo)
from app.infra.audit.sqlite import init_db
init_db()

# 1. Register a test user
res = client.post("/register", json={"email": "freeuser@test.com", "password": "password123"})
assert res.status_code == 200, f"Register failed: {res.text}"

# 2. Login to get token
res = client.post("/login", json={"email": "freeuser@test.com", "password": "password123"})
assert res.status_code == 200, f"Login failed: {res.text}"
cookies = res.cookies

# By default, a new user is 'free' plan. Let's verify.
repo = UserRepository()
user = repo.get_user_by_email("freeuser@test.com")
print(f"Test User Plan: {user['plan']}")

# 3. Try to enable autoscale
res = client.post("/user/config", json={"autoscale_enabled": True}, cookies=cookies)
print(f"Status: {res.status_code}")
print(f"Response: {res.json()}")

if res.status_code == 403 and "Autoscaling solo disponible en planes pagos" in res.json().get("detail", ""):
    print("SUCCESS: The rule blocked the action correctly for FREE plan.")
else:
    print("FAILED: The rule didn't block as expected.")
