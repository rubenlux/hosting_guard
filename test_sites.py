import os
os.environ["JWT_SECRET"] = "test_secret"
os.environ["DATABASE_URL"] = "sqlite:///test.db"

import sqlite3
import asyncio
from fastapi.testclient import TestClient
from app.api.main import app
from app.infra.audit.user_repository import UserRepository
from app.infra.audit.hosting_repository import HostingRepository
from app.infra.audit.sqlite import init_db

# Mock _run_docker directly on the module instead of patching
import app.api.routes.hosting as hosting_routes

class DummyProcess:
    def __init__(self, stdout="user_1_test|running\n"):
        self.stdout = stdout

async def mock_run_docker(*args, **kwargs):
    cmd = " ".join(args)
    if "inspect" in cmd:
        return DummyProcess("user_1_test|running\n")
    if "stats" in cmd:
        return DummyProcess("user_1_test|10.5%|256MiB\n")
    return DummyProcess()

# Replace the internal helper
hosting_routes._run_docker = mock_run_docker

init_db()

client = TestClient(app)

# Register and login to get token
res = client.post("/register", json={"email": "sitetest@test.com", "password": "password123"})
res = client.post("/login", json={"email": "sitetest@test.com", "password": "password123"})
cookies = res.cookies
user_id = res.json().get("user_id", 1)

# Inject a hosting to test listing
repo = HostingRepository()
from datetime import datetime
repo.execute(
    "INSERT INTO hostings (user_id, name, subdomain, type, container_name, status, port) VALUES (?, ?, ?, ?, ?, ?, ?)",
    (user_id, "test_site", "test.hosting.local", "static", "user_1_test", "active", 8080)
)
repo.conn.commit()

# Call the /list-hostings endpoint
response = client.get("/list-hostings", cookies=cookies)
print(f"Status Code: {response.status_code}")
print(f"Data: {response.json()}")
