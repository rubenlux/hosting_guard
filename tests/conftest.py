"""
conftest.py — fixtures compartidos para todo el test suite.

Sin PostgreSQL local: los repositorios se mockean con unittest.mock.
Los tests de lógica pura (decision_pipeline, etc.) no necesitan DB.
Los tests de API (login, staff) usan el fixture `db_mocks` que provee
usuarios/staff en memoria y parchea todos los repositorios.
"""
import os
import bcrypt
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

# ── DEBE estar antes de importar la app ──────────────────────────────────────
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-prod")

from app.api.main import app  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def make_user(user_id: int, email: str, plain_pw: str, role: str = "user",
              plan: str = "free", email_verified: int = 1) -> dict:
    return {
        "user_id": user_id,
        "email": email,
        "password_hash": _pw(plain_pw),
        "role": role,
        "plan": plan,
        "plan_expires_at": None,
        "first_name": email.split("@")[0].capitalize(),
        "last_name": "Test",
        "phone": "+5491112345678",
        "email_verified": email_verified,
        "balance": 0.0,
        "has_payment_method": 0,
        "autoscale_enabled": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def make_staff(staff_id: int, email: str, plain_pw: str, role: str = "support",
               active: int = 1) -> dict:
    return {
        "staff_id": staff_id,
        "email": email,
        "password_hash": _pw(plain_pw),
        "full_name": email.split("@")[0].capitalize(),
        "role": role,
        "is_active": active,  # campo usado por el login handler
        "created_at": "2026-01-01T00:00:00+00:00",
        "last_login": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# In-memory support session store
# ─────────────────────────────────────────────────────────────────────────────

class InMemorySupportStore:
    def __init__(self):
        self._sessions: dict = {}

    def create_session(self, admin_id, target_user_id, expires_at, ip_address,
                       issue_description=None, origin=None, **kwargs) -> str:
        import uuid
        from datetime import datetime, timezone
        sid = str(uuid.uuid4())
        self._sessions[sid] = {
            "session_id": sid,
            "admin_id": admin_id,
            "target_user_id": target_user_id,
            "expires_at": expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at),
            "ip_address": ip_address,
            "issue_description": issue_description,
            "origin": origin,
            "result": None,
            "resolution_notes": None,
            "action_taken": None,
            "ended_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return sid

    def close_session(self, session_id, result, resolution_notes=None,
                      action_taken=None, closed_by=None) -> bool:
        from datetime import datetime, timezone
        if session_id not in self._sessions:
            return False
        s = self._sessions[session_id]
        s["result"] = result
        s["resolution_notes"] = resolution_notes
        s["action_taken"] = action_taken
        s["ended_at"] = datetime.now(timezone.utc).isoformat()
        return True

    def revoke_session(self, session_id, admin_id) -> bool:
        return self.close_session(session_id, result="revoked")

    def get_active_sessions(self) -> list:
        return [s for s in self._sessions.values() if s["ended_at"] is None]

    def get_recent_sessions(self, limit=50) -> list:
        return list(self._sessions.values())[:limit]

    def get_session_detail(self, session_id) -> dict | None:
        return self._sessions.get(session_id)

    def get_session_activities(self, session_id) -> list:
        return []

    def get_sessions_for_staff(self, staff_id, days=30, limit=50) -> list:
        return [s for s in self._sessions.values() if s["admin_id"] == staff_id][:limit]

    def get_sessions_for_user(self, user_id, limit=20) -> list:
        return [s for s in self._sessions.values() if s["target_user_id"] == user_id][:limit]

    def get_sessions_summary(self, days=30) -> dict:
        sessions = list(self._sessions.values())
        return {
            "total": len(sessions),
            "resolved": sum(1 for s in sessions if s.get("result") == "resolved"),
            "escalated": sum(1 for s in sessions if s.get("result") == "escalated"),
            "revoked": sum(1 for s in sessions if s.get("result") == "revoked"),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Fixture principal: mocks de DB
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_mocks(monkeypatch):
    """
    Parchea todos los repositorios PostgreSQL con mocks en memoria.
    Retorna un dict con los datos precargados y los mocks para que
    los tests puedan hacer asserts o agregar datos.
    """
    # ── Datos en memoria ──────────────────────────────────────────────────────
    admin  = make_user(1, "admin@t.com",   "AdminPass1",   role="admin")
    client = make_user(2, "cliente@t.com", "ClientePass1", role="user")
    users_by_email = {u["email"]: u for u in [admin, client]}
    users_by_id    = {u["user_id"]: u for u in [admin, client]}
    next_uid = [3]

    support  = make_staff(1, "soporte@t.com",  "SoportePass1", role="support")
    readonly = make_staff(2, "readonly@t.com", "ReadOnly123x", role="readonly")
    staff_by_email = {s["email"]: s for s in [support, readonly]}
    staff_by_id    = {s["staff_id"]: s for s in [support, readonly]}

    session_store = InMemorySupportStore()

    # ── Mock UserRepository ───────────────────────────────────────────────────
    mu = MagicMock()
    mu.get_user_by_email.side_effect  = lambda email: users_by_email.get(email)
    mu.get_user_by_id.side_effect     = lambda uid: users_by_id.get(int(uid))
    mu.log_login_attempt.return_value = None
    mu.set_email_verified.return_value = None
    mu.update_password.return_value   = None
    mu.get_all_users.return_value     = list(users_by_id.values())
    mu.update_plan.return_value       = True

    def _create_user(email, password_hash, role="user", first_name=None,
                     last_name=None, phone=None):
        uid = next_uid[0]; next_uid[0] += 1
        u = {
            "user_id": uid, "email": email, "password_hash": password_hash,
            "role": role, "plan": "free", "plan_expires_at": None,
            "first_name": first_name, "last_name": last_name, "phone": phone,
            "email_verified": 0, "balance": 0.0,
            "has_payment_method": 0, "autoscale_enabled": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        users_by_email[email] = u
        users_by_id[uid] = u
        return uid
    mu.create_user.side_effect = _create_user

    # ── Mock StaffRepository ──────────────────────────────────────────────────
    ms = MagicMock()
    ms.get_staff_by_email.side_effect  = lambda email: staff_by_email.get(email)
    ms.get_staff_by_id.side_effect     = lambda sid: staff_by_id.get(int(sid))
    ms.update_last_login.return_value  = None
    ms.log_activity.return_value       = None
    ms.get_available_staff.return_value = list(staff_by_id.values())
    ms.get_activity_for_staff.return_value = []
    ms.get_all_activity.return_value   = []
    ms.get_analytics.return_value      = []
    ms.get_hourly_activity.return_value = []

    def _create_staff(admin_id, email, password_hash, full_name, role):
        sid = max(staff_by_id.keys(), default=0) + 1
        s = {
            "staff_id": sid, "email": email, "password_hash": password_hash,
            "full_name": full_name, "role": role, "is_active": 1,
            "created_at": "2026-01-01T00:00:00+00:00", "last_login": None,
        }
        staff_by_email[email] = s
        staff_by_id[sid] = s
        return sid
    ms.create_staff.side_effect = _create_staff

    # ── Mock SupportSessionRepository ────────────────────────────────────────
    mss = MagicMock()
    mss.create_session.side_effect       = session_store.create_session
    mss.close_session.side_effect        = session_store.close_session
    mss.revoke_session.side_effect       = session_store.revoke_session
    mss.get_active_sessions.side_effect  = session_store.get_active_sessions
    mss.get_recent_sessions.side_effect  = session_store.get_recent_sessions
    mss.get_session_detail.side_effect   = session_store.get_session_detail
    mss.get_session_activities.side_effect = session_store.get_session_activities
    mss.get_sessions_for_staff.side_effect = session_store.get_sessions_for_staff
    mss.get_sessions_for_user.side_effect  = session_store.get_sessions_for_user
    mss.get_sessions_summary.side_effect   = session_store.get_sessions_summary

    # ── Mock AuthTokenRepository ──────────────────────────────────────────────
    mat = MagicMock()
    mat.create_token.return_value   = "test-token-uuid"
    mat.get_valid_token.return_value = None
    mat.mark_used.return_value      = None

    # ── Patch clases en módulos fuente (cubre instancias inline y singleton) ──
    import app.infra.audit.user_repository    as _ur
    import app.infra.audit.staff_repository   as _sr
    import app.infra.audit.support_repository as _ssr
    import app.infra.auth_token_repository    as _atr

    monkeypatch.setattr(_ur,  "UserRepository",            lambda: mu,  raising=False)
    monkeypatch.setattr(_sr,  "StaffRepository",           lambda: ms,  raising=False)
    monkeypatch.setattr(_ssr, "SupportSessionRepository",  lambda: mss, raising=False)
    monkeypatch.setattr(_atr, "AuthTokenRepository",       lambda: mat, raising=False)

    # Patch singletons ya instanciados en main.py y rutas (módulos cargados)
    import app.api.main            as _main
    import app.api.routes.impersonate as _imp
    import app.api.routes.staff       as _staff_route
    import app.api.routes.admin       as _admin_route

    monkeypatch.setattr(_main, "user_repo", mu, raising=False)
    monkeypatch.setattr(_imp,  "_user_repo",    mu,  raising=False)
    monkeypatch.setattr(_imp,  "_staff_repo",   ms,  raising=False)
    monkeypatch.setattr(_imp,  "_support_repo", mss, raising=False)
    monkeypatch.setattr(_staff_route, "_staff_repo", ms, raising=False)
    monkeypatch.setattr(_admin_route, "_user_repo",  mu, raising=False)

    # Patch también security.py que instancia StaffRepository() inline
    import app.api.security as _sec
    monkeypatch.setattr(_sec, "StaffRepository", lambda: ms, raising=False)

    # Silenciar mailer en tests
    monkeypatch.setattr("app.services.mailer.send_verification_email",  lambda *a, **k: None)
    monkeypatch.setattr("app.services.mailer.send_password_reset_email", lambda *a, **k: None)

    monkeypatch.setattr("app.api.main.ENABLE_AI_ADVISORY", False)

    return {
        "users_by_email": users_by_email,
        "users_by_id":    users_by_id,
        "staff_by_email": staff_by_email,
        "staff_by_id":    staff_by_id,
        "session_store":  session_store,
        "mock_user_repo":    mu,
        "mock_staff_repo":   ms,
        "mock_support_repo": mss,
        # IDs pre-cargados
        "admin_id":    1, "admin_email":    "admin@t.com",   "admin_pw":    "AdminPass1",
        "client_id":   2, "client_email":   "cliente@t.com", "client_pw":   "ClientePass1",
        "support_id":  1, "support_email":  "soporte@t.com", "support_pw":  "SoportePass1",
        "readonly_id": 2, "readonly_email": "readonly@t.com","readonly_pw": "ReadOnly123x",
    }


@pytest.fixture()
def tc(db_mocks):
    """TestClient con mocks de DB aplicados."""
    return TestClient(app, raise_server_exceptions=False)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures de sesión / globales
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True, scope="session")
def disable_rate_limiter():
    from app.api.rate_limit import limiter
    limiter.enabled = False
    yield
    limiter.enabled = True


@pytest.fixture()
def client(monkeypatch):
    """TestClient básico para tests de lógica pura (no necesitan DB)."""
    monkeypatch.setattr("app.api.main.ENABLE_AI_ADVISORY", True)
    return TestClient(app)
