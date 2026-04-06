"""
Tests: login sin errores + rutas de impersonation sin conflictos.

Cubre:
  A) Login de usuario normal — debe funcionar aunque staff_accounts no tenga datos
  B) Login de staff — devuelve staff_token, NO access_token
  C) Ruta conflict fix: POST /admin/impersonate/staff/{id}  → 200 (no 422/500)
  D) Ruta conflict fix: GET  /admin/impersonate/sessions     → 200 (no 422/500)
  E) Ruta conflict fix: GET  /admin/impersonate/sessions/{id}→ 404 o 200 (no 422/500)
  F) Ruta conflict fix: POST /admin/impersonate/staff/{id}/close → no 422/500
  G) Session analytics: GET /admin/impersonate/sessions devuelve history/summary/active
  H) Session detail: GET /admin/impersonate/sessions/{id} devuelve session+activities
  I) Close session: POST /admin/impersonate/{id}/close con result válido
  J) Login resilience: staff_accounts ausente NO rompe login de usuario normal

Ejecutar:
    JWT_SECRET=test-secret python -m pytest tests/test_login_and_routes.py -v -s
"""
import os
import pytest
import bcrypt
from fastapi.testclient import TestClient


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def setup(tmp_path, monkeypatch):
    """DB aislada + admin user + staff support + cliente."""
    from app.infra.audit import sqlite as audit_sqlite

    db_file = str(tmp_path / "test.sqlite")
    monkeypatch.setattr(audit_sqlite, "DB_PATH", db_file)

    # Reset thread-local connection
    if hasattr(audit_sqlite._local, "conn") and audit_sqlite._local.conn is not None:
        try:
            audit_sqlite._local.conn._conn.close()
        except Exception:
            pass
        audit_sqlite._local.conn = None

    audit_sqlite.init_db()
    monkeypatch.setattr("app.api.main.ENABLE_AI_ADVISORY", False)

    from app.api.main import app
    from app.infra.audit.staff_repository import StaffRepository
    from app.infra.audit.user_repository import UserRepository

    def pw(s): return bcrypt.hashpw(s.encode(), bcrypt.gensalt()).decode()

    ur = UserRepository()
    sr = StaffRepository()

    # Admin user
    admin_id = ur.create_user("admin@t.com", pw("AdminPass1"), role="admin")
    # Regular user / client
    client_id = ur.create_user("cliente@t.com", pw("ClientePass1"), role="user")
    # Staff support
    staff_id = sr.create_staff(0, "soporte@t.com", pw("SoportePass1"), "Soporte Test", "support")

    tc = TestClient(app, raise_server_exceptions=False)

    return {
        "tc": tc,
        "admin_id": admin_id, "admin_email": "admin@t.com", "admin_pw": "AdminPass1",
        "client_id": client_id, "client_email": "cliente@t.com", "client_pw": "ClientePass1",
        "staff_id": staff_id, "staff_email": "soporte@t.com", "staff_pw": "SoportePass1",
    }


def _login_user(tc, email, pw):
    return tc.post("/login", json={"email": email, "password": pw})

def _login_staff(tc, email, pw):
    return tc.post("/staff/login", json={"email": email, "password": pw})

def _admin_cookies(setup):
    r = _login_user(setup["tc"], setup["admin_email"], setup["admin_pw"])
    assert r.status_code == 200, f"admin login failed: {r.text}"
    return dict(r.cookies)

def _staff_cookies(setup):
    r = _login_staff(setup["tc"], setup["staff_email"], setup["staff_pw"])
    assert r.status_code == 200, f"staff login failed: {r.text}"
    return dict(r.cookies)


# ═════════════════════════════════════════════════════════════════════════════
# A) Login usuario normal
# ═════════════════════════════════════════════════════════════════════════════

class TestUserLogin:

    def test_user_login_returns_200(self, setup):
        r = _login_user(setup["tc"], setup["client_email"], setup["client_pw"])
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        assert r.json()["status"] == "ok"
        assert r.json()["account_type"] == "user"

    def test_user_login_sets_access_token_cookie(self, setup):
        r = _login_user(setup["tc"], setup["client_email"], setup["client_pw"])
        assert "access_token" in r.cookies, "access_token cookie must be set after login"

    def test_user_login_wrong_password_returns_401(self, setup):
        r = _login_user(setup["tc"], setup["client_email"], "WRONG")
        assert r.status_code == 401

    def test_user_login_unknown_email_returns_401(self, setup):
        r = _login_user(setup["tc"], "nadie@t.com", "cualquier")
        assert r.status_code == 401

    def test_user_login_never_returns_500(self, setup):
        """Login nunca debe dar 500, ni con credenciales incorrectas."""
        r = _login_user(setup["tc"], "x@x.com", "y")
        assert r.status_code != 500, f"Login returned 500: {r.text}"

    def test_admin_login_works(self, setup):
        r = _login_user(setup["tc"], setup["admin_email"], setup["admin_pw"])
        assert r.status_code == 200
        assert r.json()["account_type"] == "user"  # admin uses same /login

    def test_me_after_login_returns_user(self, setup):
        tc = setup["tc"]
        r = _login_user(tc, setup["client_email"], setup["client_pw"])
        me = tc.get("/me", cookies=dict(r.cookies))
        assert me.status_code == 200
        body = me.json()
        assert body["email"] == setup["client_email"]
        assert body["is_support_session"] is False


# ═════════════════════════════════════════════════════════════════════════════
# B) Login staff
# ═════════════════════════════════════════════════════════════════════════════

class TestStaffLoginRoute:

    def test_staff_login_returns_staff_token(self, setup):
        r = _login_staff(setup["tc"], setup["staff_email"], setup["staff_pw"])
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        assert r.json()["ok"] is True
        assert "staff_token" in r.cookies

    def test_staff_login_wrong_pw_returns_401(self, setup):
        r = _login_staff(setup["tc"], setup["staff_email"], "WRONG")
        assert r.status_code == 401

    def test_staff_login_does_not_set_access_token(self, setup):
        r = _login_staff(setup["tc"], setup["staff_email"], setup["staff_pw"])
        assert "access_token" not in r.cookies, "staff login must NOT set access_token"


# ═════════════════════════════════════════════════════════════════════════════
# C-F) Rutas impersonate — sin conflictos 422/500
# ═════════════════════════════════════════════════════════════════════════════

class TestImpersonateRoutes:

    def test_staff_start_session_no_route_conflict(self, setup):
        """
        POST /admin/impersonate/staff/{id} NO debe dar 422 (route conflict).
        Antes del fix, FastAPI parseaba 'staff' en /{user_id} como int → 422.
        """
        tc = setup["tc"]
        staff_ck = _staff_cookies(setup)
        r = tc.post(
            f"/admin/impersonate/staff/{setup['client_id']}",
            cookies=staff_ck,
        )
        assert r.status_code != 422, f"Route conflict! Got 422: {r.text}"
        assert r.status_code != 500, f"Server error! Got 500: {r.text}"
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_sessions_list_no_route_conflict(self, setup):
        """GET /admin/impersonate/sessions NO debe dar 422."""
        tc = setup["tc"]
        admin_ck = _admin_cookies(setup)
        r = tc.get("/admin/impersonate/sessions", cookies=admin_ck)
        assert r.status_code != 422, f"Route conflict on /sessions: {r.text}"
        assert r.status_code != 500, f"Server error: {r.text}"
        assert r.status_code == 200, f"Expected 200: {r.text}"

    def test_sessions_list_returns_expected_shape(self, setup):
        """GET /admin/impersonate/sessions devuelve history + summary + active."""
        tc = setup["tc"]
        admin_ck = _admin_cookies(setup)
        r = tc.get("/admin/impersonate/sessions", cookies=admin_ck)
        body = r.json()
        assert "history" in body, f"Missing 'history' key: {body}"
        assert "summary" in body, f"Missing 'summary' key: {body}"
        assert "active"  in body, f"Missing 'active' key: {body}"
        assert isinstance(body["history"], list)
        assert isinstance(body["active"],  list)

    def test_session_detail_nonexistent_returns_404_not_422(self, setup):
        """GET /admin/impersonate/sessions/{uuid} para sesión inexistente → 404."""
        tc = setup["tc"]
        admin_ck = _admin_cookies(setup)
        fake_id = "00000000-0000-0000-0000-000000000000"
        r = tc.get(f"/admin/impersonate/sessions/{fake_id}", cookies=admin_ck)
        assert r.status_code != 422, f"Route conflict on sessions/{{id}}: {r.text}"
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_staff_close_session_no_route_conflict(self, setup):
        """
        POST /admin/impersonate/staff/{session_id}/close NO debe confundirse
        con POST /admin/impersonate/{session_id}/close.
        """
        tc = setup["tc"]
        staff_ck = _staff_cookies(setup)
        # Start a real session first
        start = tc.post(
            f"/admin/impersonate/staff/{setup['client_id']}",
            cookies=staff_ck,
            json={"issue_description": "Test issue", "origin": "manual"},
        )
        assert start.status_code == 200
        session_id = start.json()["session_id"]

        # Close it
        close = tc.post(
            f"/admin/impersonate/staff/{session_id}/close",
            cookies=staff_ck,
            json={"result": "resolved", "action_taken": "Fixed it", "resolution_notes": "All good"},
        )
        assert close.status_code != 422, f"Route conflict on staff close: {close.text}"
        assert close.status_code != 500, f"Server error on staff close: {close.text}"
        assert close.status_code == 200, f"Expected 200, got {close.status_code}: {close.text}"
        assert close.json()["result"] == "resolved"


# ═════════════════════════════════════════════════════════════════════════════
# G-H) Session analytics: datos correctos
# ═════════════════════════════════════════════════════════════════════════════

class TestSessionAnalytics:

    def _create_session(self, setup, close=False):
        """Crea una sesión de soporte (y opcionalmente la cierra)."""
        tc = setup["tc"]
        staff_ck = _staff_cookies(setup)
        start = tc.post(
            f"/admin/impersonate/staff/{setup['client_id']}",
            cookies=staff_ck,
            json={"issue_description": "El sitio no carga", "origin": "client_request"},
        )
        assert start.status_code == 200, start.text
        session_id = start.json()["session_id"]

        if close:
            tc.post(
                f"/admin/impersonate/staff/{session_id}/close",
                cookies=staff_ck,
                json={
                    "result": "resolved",
                    "action_taken": "Reinicio de contenedor",
                    "resolution_notes": "El cliente tenía mal el env",
                },
            )
        return session_id, staff_ck

    def test_session_appears_in_history(self, setup):
        session_id, _ = self._create_session(setup)
        tc = setup["tc"]
        admin_ck = _admin_cookies(setup)
        r = tc.get("/admin/impersonate/sessions", cookies=admin_ck)
        assert r.status_code == 200
        ids = [s["session_id"] for s in r.json()["history"]]
        assert session_id in ids, f"Session {session_id} not found in history: {ids}"

    def test_summary_counts_sessions(self, setup):
        self._create_session(setup, close=True)
        tc = setup["tc"]
        admin_ck = _admin_cookies(setup)
        r = tc.get("/admin/impersonate/sessions", cookies=admin_ck)
        summary = r.json()["summary"]
        assert summary["total"] >= 1, f"Expected at least 1 session in summary: {summary}"
        assert summary.get("resolved") is not None

    def test_session_detail_returns_full_data(self, setup):
        session_id, _ = self._create_session(setup, close=True)
        tc = setup["tc"]
        admin_ck = _admin_cookies(setup)
        r = tc.get(f"/admin/impersonate/sessions/{session_id}", cookies=admin_ck)
        assert r.status_code == 200, f"session detail failed: {r.text}"
        body = r.json()
        assert "session" in body
        assert "activities" in body
        assert "duration_seconds" in body
        assert "activity_count" in body
        s = body["session"]
        assert s["session_id"] == session_id
        assert s["issue_description"] == "El sitio no carga"
        assert s["origin"] == "client_request"
        assert s["result"] == "resolved"
        assert s["action_taken"] == "Reinicio de contenedor"
        assert s["resolution_notes"] == "El cliente tenía mal el env"

    def test_session_detail_has_target_email(self, setup):
        session_id, _ = self._create_session(setup)
        tc = setup["tc"]
        admin_ck = _admin_cookies(setup)
        r = tc.get(f"/admin/impersonate/sessions/{session_id}", cookies=admin_ck)
        s = r.json()["session"]
        assert s.get("target_email") == setup["client_email"], \
            f"target_email mismatch: {s.get('target_email')}"

    def test_closed_session_has_ended_at(self, setup):
        session_id, _ = self._create_session(setup, close=True)
        tc = setup["tc"]
        admin_ck = _admin_cookies(setup)
        r = tc.get(f"/admin/impersonate/sessions/{session_id}", cookies=admin_ck)
        s = r.json()["session"]
        assert s.get("ended_at") is not None, "Closed session must have ended_at"
        assert r.json()["duration_seconds"] is not None, "Closed session must have duration_seconds"

    def test_session_with_issue_info(self, setup):
        """issue_description y origin se persisten correctamente."""
        tc = setup["tc"]
        staff_ck = _staff_cookies(setup)
        r = tc.post(
            f"/admin/impersonate/staff/{setup['client_id']}",
            cookies=staff_ck,
            json={"issue_description": "Error 500 en producción", "origin": "ai_advisory"},
        )
        assert r.status_code == 200
        session_id = r.json()["session_id"]

        admin_ck = _admin_cookies(setup)
        detail = tc.get(f"/admin/impersonate/sessions/{session_id}", cookies=admin_ck)
        s = detail.json()["session"]
        assert s["issue_description"] == "Error 500 en producción"
        assert s["origin"] == "ai_advisory"


# ═════════════════════════════════════════════════════════════════════════════
# I) Admin close session
# ═════════════════════════════════════════════════════════════════════════════

class TestAdminCloseSession:

    def test_admin_can_close_session(self, setup):
        tc = setup["tc"]
        staff_ck = _staff_cookies(setup)
        start = tc.post(
            f"/admin/impersonate/staff/{setup['client_id']}",
            cookies=staff_ck,
        )
        session_id = start.json()["session_id"]

        admin_ck = _admin_cookies(setup)
        r = tc.post(
            f"/admin/impersonate/{session_id}/close",
            cookies=admin_ck,
            json={"result": "escalated", "resolution_notes": "Necesita revisión"},
        )
        assert r.status_code == 200, f"admin close failed: {r.text}"
        assert r.json()["result"] == "escalated"

    def test_close_invalid_result_returns_400(self, setup):
        tc = setup["tc"]
        staff_ck = _staff_cookies(setup)
        start = tc.post(
            f"/admin/impersonate/staff/{setup['client_id']}",
            cookies=staff_ck,
        )
        session_id = start.json()["session_id"]
        admin_ck = _admin_cookies(setup)
        r = tc.post(
            f"/admin/impersonate/{session_id}/close",
            cookies=admin_ck,
            json={"result": "INVALID_VALUE"},
        )
        assert r.status_code == 400

    def test_close_nonexistent_session_returns_404(self, setup):
        admin_ck = _admin_cookies(setup)
        r = setup["tc"].post(
            "/admin/impersonate/00000000-fake-uuid-0000-000000000000/close",
            cookies=admin_ck,
            json={"result": "resolved"},
        )
        assert r.status_code == 404


# ═════════════════════════════════════════════════════════════════════════════
# J) Login resilience — staff_accounts ausente no rompe login normal
# ═════════════════════════════════════════════════════════════════════════════

class TestLoginResilience:

    def test_login_works_when_staff_table_would_error(self, setup, monkeypatch):
        """
        Simula que staff_accounts falla (ej: migración pendiente en prod).
        El login de usuario normal debe seguir devolviendo 200.
        """
        from app.infra.audit import staff_repository as sr_module

        original = sr_module.StaffRepository.get_staff_by_email

        def boom(self, email):
            raise Exception("no such table: staff_accounts")

        monkeypatch.setattr(sr_module.StaffRepository, "get_staff_by_email", boom)

        r = _login_user(setup["tc"], setup["client_email"], setup["client_pw"])
        assert r.status_code == 200, \
            f"Login should work even when staff_accounts fails, got {r.status_code}: {r.text}"
        assert r.json()["account_type"] == "user"

    def test_login_never_returns_500_on_any_input(self, setup):
        """Cualquier combinación de credenciales devuelve 400-401, nunca 500."""
        inputs = [
            ("", ""),
            ("notanemail", "pw"),
            ("a@b.com", ""),
            ("admin@t.com", "wrong"),
            ("cliente@t.com", "wrong"),
        ]
        for email, pw in inputs:
            r = setup["tc"].post("/login", json={"email": email, "password": pw})
            assert r.status_code != 500, \
                f"Login returned 500 for ({email!r}, {pw!r}): {r.text}"
