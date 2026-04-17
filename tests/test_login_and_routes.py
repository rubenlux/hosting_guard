"""
Tests: login + rutas de impersonation.

Usa el fixture `db_mocks` + `tc` del conftest para operar sin PostgreSQL real.

Escenarios:
  A) Login usuario normal → 200, access_token cookie
  B) Login staff → staff_token cookie, NO access_token
  C-F) Rutas impersonate sin conflictos 422/500
  G-H) Session analytics: datos correctos
  I) Admin cierra sesión
  J) Login resiliente: staff falla → usuario normal sigue funcionando
"""
import pytest
from fastapi.testclient import TestClient
from app.api.main import app


# ─── Helpers ──────────────────────────────────────────────────────────────────

def login_user(tc, email, pw):
    return tc.post("/login", json={"email": email, "password": pw})

def login_staff(tc, email, pw):
    return tc.post("/staff/login", json={"email": email, "password": pw})

def admin_cookies(tc, db):
    r = login_user(tc, db["admin_email"], db["admin_pw"])
    assert r.status_code == 200, f"admin login failed: {r.text}"
    return dict(r.cookies)

def staff_cookies(tc, db):
    r = login_staff(tc, db["support_email"], db["support_pw"])
    assert r.status_code == 200, f"staff login failed: {r.text}"
    return dict(r.cookies)


# ═══════════════════════════════════════════════════════════════════════════════
# A) Login usuario normal
# ═══════════════════════════════════════════════════════════════════════════════

class TestUserLogin:

    def test_login_returns_200(self, tc, db_mocks):
        r = login_user(tc, db_mocks["client_email"], db_mocks["client_pw"])
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["account_type"] == "user"

    def test_login_sets_access_token_cookie(self, tc, db_mocks):
        r = login_user(tc, db_mocks["client_email"], db_mocks["client_pw"])
        assert "access_token" in r.cookies

    def test_login_wrong_password_returns_401(self, tc, db_mocks):
        r = login_user(tc, db_mocks["client_email"], "WRONG_PASSWORD")
        assert r.status_code == 401

    def test_login_unknown_email_returns_401(self, tc, db_mocks):
        r = login_user(tc, "nadie@nowhere.com", "cualquiercosa")
        assert r.status_code == 401

    def test_login_never_returns_500(self, tc, db_mocks):
        r = login_user(tc, "x@x.com", "y")
        assert r.status_code != 500

    def test_admin_login_works(self, tc, db_mocks):
        r = login_user(tc, db_mocks["admin_email"], db_mocks["admin_pw"])
        assert r.status_code == 200

    def test_me_after_login_returns_user(self, tc, db_mocks):
        r = login_user(tc, db_mocks["client_email"], db_mocks["client_pw"])
        me = tc.get("/me", cookies=dict(r.cookies))
        assert me.status_code == 200
        assert me.json()["email"] == db_mocks["client_email"]
        assert me.json()["is_support_session"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# B) Login staff
# ═══════════════════════════════════════════════════════════════════════════════

class TestStaffLogin:

    def test_staff_login_returns_staff_token(self, tc, db_mocks):
        r = login_staff(tc, db_mocks["support_email"], db_mocks["support_pw"])
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert "staff_token" in r.cookies

    def test_staff_login_wrong_pw_returns_401(self, tc, db_mocks):
        r = login_staff(tc, db_mocks["support_email"], "WRONG")
        assert r.status_code == 401

    def test_staff_login_does_not_set_access_token(self, tc, db_mocks):
        r = login_staff(tc, db_mocks["support_email"], db_mocks["support_pw"])
        assert "access_token" not in r.cookies


# ═══════════════════════════════════════════════════════════════════════════════
# C-F) Rutas impersonate sin conflictos 422/500
# ═══════════════════════════════════════════════════════════════════════════════

class TestImpersonateRoutes:

    def test_staff_start_session_no_route_conflict(self, tc, db_mocks):
        ck = staff_cookies(tc, db_mocks)
        r = tc.post(f"/admin/impersonate/staff/{db_mocks['client_id']}", cookies=ck)
        assert r.status_code not in {422, 500}, f"Got {r.status_code}: {r.text}"
        assert r.status_code == 200

    def test_sessions_list_no_route_conflict(self, tc, db_mocks):
        ck = admin_cookies(tc, db_mocks)
        r = tc.get("/admin/impersonate/sessions", cookies=ck)
        assert r.status_code not in {422, 500}
        assert r.status_code == 200

    def test_sessions_list_returns_expected_shape(self, tc, db_mocks):
        ck = admin_cookies(tc, db_mocks)
        r = tc.get("/admin/impersonate/sessions", cookies=ck)
        body = r.json()
        assert "history" in body
        assert "summary" in body
        assert "active" in body

    def test_session_detail_nonexistent_returns_404(self, tc, db_mocks):
        ck = admin_cookies(tc, db_mocks)
        r = tc.get("/admin/impersonate/sessions/00000000-0000-0000-0000-000000000000", cookies=ck)
        assert r.status_code not in {422}
        assert r.status_code == 404

    def test_staff_close_session_no_route_conflict(self, tc, db_mocks):
        ck = staff_cookies(tc, db_mocks)
        start = tc.post(
            f"/admin/impersonate/staff/{db_mocks['client_id']}",
            cookies=ck,
            json={"issue_description": "Test issue", "origin": "manual"},
        )
        assert start.status_code == 200
        session_id = start.json()["session_id"]

        close = tc.post(
            f"/admin/impersonate/staff/{session_id}/close",
            cookies=ck,
            json={"result": "resolved", "action_taken": "Fixed", "resolution_notes": "OK"},
        )
        assert close.status_code not in {422, 500}
        assert close.status_code == 200
        assert close.json()["result"] == "resolved"


# ═══════════════════════════════════════════════════════════════════════════════
# G-H) Session analytics
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionAnalytics:

    def _start_session(self, tc, db_mocks, close=False):
        ck = staff_cookies(tc, db_mocks)
        r = tc.post(
            f"/admin/impersonate/staff/{db_mocks['client_id']}",
            cookies=ck,
            json={"issue_description": "El sitio no carga", "origin": "client_request"},
        )
        assert r.status_code == 200
        sid = r.json()["session_id"]
        if close:
            tc.post(
                f"/admin/impersonate/staff/{sid}/close",
                cookies=ck,
                json={"result": "resolved", "action_taken": "Reinicio", "resolution_notes": "OK"},
            )
        return sid, ck

    def test_session_appears_in_history(self, tc, db_mocks):
        sid, _ = self._start_session(tc, db_mocks)
        ck = admin_cookies(tc, db_mocks)
        r = tc.get("/admin/impersonate/sessions", cookies=ck)
        ids = [s["session_id"] for s in r.json()["history"]]
        assert sid in ids

    def test_summary_counts_sessions(self, tc, db_mocks):
        self._start_session(tc, db_mocks, close=True)
        ck = admin_cookies(tc, db_mocks)
        r = tc.get("/admin/impersonate/sessions", cookies=ck)
        summary = r.json()["summary"]
        assert summary["total"] >= 1

    def test_session_detail_returns_full_data(self, tc, db_mocks):
        sid, _ = self._start_session(tc, db_mocks, close=True)
        ck = admin_cookies(tc, db_mocks)
        r = tc.get(f"/admin/impersonate/sessions/{sid}", cookies=ck)
        assert r.status_code == 200
        body = r.json()
        assert "session" in body
        assert "activities" in body
        assert body["session"]["session_id"] == sid


# ═══════════════════════════════════════════════════════════════════════════════
# I) Admin cierra sesión
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdminCloseSession:

    def test_admin_can_close_session(self, tc, db_mocks):
        ck_staff = staff_cookies(tc, db_mocks)
        start = tc.post(
            f"/admin/impersonate/staff/{db_mocks['client_id']}",
            cookies=ck_staff,
        )
        sid = start.json()["session_id"]

        ck_admin = admin_cookies(tc, db_mocks)
        r = tc.post(
            f"/admin/impersonate/{sid}/close",
            cookies=ck_admin,
            json={"result": "escalated", "resolution_notes": "Necesita revisión"},
        )
        assert r.status_code == 200
        assert r.json()["result"] == "escalated"

    def test_close_invalid_result_returns_400(self, tc, db_mocks):
        ck_staff = staff_cookies(tc, db_mocks)
        start = tc.post(
            f"/admin/impersonate/staff/{db_mocks['client_id']}",
            cookies=ck_staff,
        )
        sid = start.json()["session_id"]
        ck_admin = admin_cookies(tc, db_mocks)
        r = tc.post(
            f"/admin/impersonate/{sid}/close",
            cookies=ck_admin,
            json={"result": "INVALID_VALUE"},
        )
        assert r.status_code == 400

    def test_close_nonexistent_session_returns_404(self, tc, db_mocks):
        ck = admin_cookies(tc, db_mocks)
        r = tc.post(
            "/admin/impersonate/00000000-fake-uuid-0000-000000000000/close",
            cookies=ck,
            json={"result": "resolved"},
        )
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# J) Login resiliente
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoginResilience:

    def test_login_works_when_staff_lookup_fails(self, tc, db_mocks, monkeypatch):
        db_mocks["mock_staff_repo"].get_staff_by_email.side_effect = Exception("staff table missing")
        r = login_user(tc, db_mocks["client_email"], db_mocks["client_pw"])
        assert r.status_code == 200
        assert r.json()["account_type"] == "user"

    def test_login_never_returns_500_on_any_input(self, tc, db_mocks):
        for email, pw in [("", ""), ("notanemail", "pw"), ("a@b.com", ""),
                          ("admin@t.com", "wrong"), ("cliente@t.com", "wrong")]:
            r = tc.post("/login", json={"email": email, "password": pw})
            assert r.status_code != 500, f"Login returned 500 for ({email!r}, {pw!r}): {r.text}"
