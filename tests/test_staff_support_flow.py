"""
Tests: flujo completo staff login → soporte → permisos de escritura.

Ejecutar:
    JWT_SECRET=test-secret python -m pytest tests/test_staff_support_flow.py -v -s

Escenarios cubiertos:
1.  Staff login válido → staff_token cookie ✓
2.  Staff login contraseña incorrecta → 401 ✓
3.  Staff inactivo → 403 ✓
4.  GET /staff/me sin cookie → 401 ✓
5.  GET /staff/me con cookie → perfil sin password_hash ✓
6.  Staff inicia sesión de soporte (POST /admin/impersonate/staff/{user_id}) ✓
7.  Activar support_token → GET /me devuelve datos del cliente, is_support_session=True ✓
8.  Topup bloqueado en modo soporte → 403 ✓
9.  POST /files/save en soporte con rol support → 404 (llega al handler, no 403) ✓
10. DELETE /files en soporte con rol support → 404 (llega al handler, no 403) ✓
11. Rol readonly → NO puede iniciar sesión de soporte → 403 ✓
12. Tabla de permisos impresa para revisión visual ✓
"""
import os
import pytest
import bcrypt
from fastapi.testclient import TestClient

# ─────────────────────────────────────────────────────────────────────────────
# Fixture base: DB aislada + app + staff preconfigurado
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def setup(tmp_path, monkeypatch):
    """
    Provee un TestClient con:
    - DB SQLite aislada en tmp_path
    - Un staff 'support' activo  (email: soporte@t.com  / pw: SoportePass1)
    - Un staff 'readonly' activo (email: readonly@t.com / pw: ReadOnly123x)
    - Un usuario cliente          (email: cliente@t.com  / pw: ClientePass1)
    """
    # 1. Apuntar la DB a un archivo temporal antes de importar nada
    from app.infra.audit import sqlite as audit_sqlite
    db_file = str(tmp_path / "test_audit.sqlite")
    monkeypatch.setattr(audit_sqlite, "DB_PATH", db_file)

    # Forzar cierre del hilo-local de SQLite: la conexión thread-local cacheada apunta
    # al archivo del test anterior. Si no se resetea, las queries del nuevo test
    # van contra la DB vieja → "no such table: staff_accounts" en el segundo test.
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

    def pw_hash(pw: str) -> str:
        return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

    staff_repo = StaffRepository()
    user_repo  = UserRepository()

    support_id = staff_repo.create_staff(
        admin_id=0,
        email="soporte@t.com",
        password_hash=pw_hash("SoportePass1"),
        full_name="Soporte Staff",
        role="support",
    )
    readonly_id = staff_repo.create_staff(
        admin_id=0,
        email="readonly@t.com",
        password_hash=pw_hash("ReadOnly123x"),
        full_name="Readonly Staff",
        role="readonly",
    )

    # Crear usuario cliente directamente en la DB
    client_pw_hash = pw_hash("ClientePass1")
    user_repo.create_user("cliente@t.com", client_pw_hash)
    client_db = user_repo.get_user_by_email("cliente@t.com")
    client_id  = client_db["user_id"]

    tc = TestClient(app, raise_server_exceptions=False)

    return {
        "tc": tc,
        "support_email": "soporte@t.com",
        "support_pw":    "SoportePass1",
        "support_id":    support_id,
        "readonly_email":"readonly@t.com",
        "readonly_pw":   "ReadOnly123x",
        "client_email":  "cliente@t.com",
        "client_pw":     "ClientePass1",
        "client_id":     client_id,
    }


# Helpers
def staff_login(tc, email, pw):
    return tc.post("/staff/login", json={"email": email, "password": pw})

def start_support(tc, staff_cookies, user_id):
    return tc.post(f"/admin/impersonate/staff/{user_id}", cookies=staff_cookies)

def activate_support(tc, token):
    return tc.post("/support/activate", json={"token": token})


# ═══════════════════════════════════════════════════════════════════════════════
# 1 — STAFF LOGIN
# ═══════════════════════════════════════════════════════════════════════════════

class TestStaffLogin:

    def test_valid_login_returns_staff_token(self, setup):
        tc = setup["tc"]
        resp = staff_login(tc, setup["support_email"], setup["support_pw"])
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json()["ok"] is True
        assert resp.json()["role"] == "support"
        assert "staff_token" in resp.cookies, "staff_token cookie must be set"

    def test_wrong_password_returns_401(self, setup):
        resp = staff_login(setup["tc"], setup["support_email"], "WRONG")
        assert resp.status_code == 401

    def test_unknown_email_returns_401(self, setup):
        resp = staff_login(setup["tc"], "nadie@t.com", "cualquier")
        assert resp.status_code == 401

    def test_inactive_staff_returns_403(self, setup, monkeypatch):
        from app.infra.audit.staff_repository import StaffRepository
        StaffRepository().deactivate_staff(setup["support_id"])
        resp = staff_login(setup["tc"], setup["support_email"], setup["support_pw"])
        assert resp.status_code == 403, f"Expected 403 for inactive staff, got {resp.status_code}"


# ═══════════════════════════════════════════════════════════════════════════════
# 2 — STAFF /me
# ═══════════════════════════════════════════════════════════════════════════════

class TestStaffMe:

    def test_me_without_cookie_returns_401(self, setup):
        resp = setup["tc"].get("/staff/me")
        assert resp.status_code == 401

    def test_me_with_cookie_returns_profile_no_hash(self, setup):
        tc = setup["tc"]
        login = staff_login(tc, setup["support_email"], setup["support_pw"])
        me = tc.get("/staff/me", cookies=login.cookies)
        assert me.status_code == 200, me.text
        body = me.json()
        assert body["email"] == setup["support_email"]
        assert body["role"] == "support"
        assert "password_hash" not in body, "password_hash must NOT be exposed"


# ═══════════════════════════════════════════════════════════════════════════════
# 3 — SOPORTE: inicio + activación + /me como cliente
# ═══════════════════════════════════════════════════════════════════════════════

class TestSupportSessionFlow:

    def test_support_staff_can_start_session(self, setup):
        tc = setup["tc"]
        login = staff_login(tc, setup["support_email"], setup["support_pw"])
        resp = start_support(tc, login.cookies, setup["client_id"])
        assert resp.status_code == 200, f"start_support failed: {resp.text}"
        body = resp.json()
        assert "token" in body
        assert body["target_email"] == setup["client_email"]

    def test_after_activate_me_returns_client_data(self, setup):
        """
        Flujo crítico: después de activar el support_token,
        GET /me debe devolver datos del CLIENTE (no del staff).
        Esto es lo que permite que PrivateRoute vea user != null.
        """
        tc = setup["tc"]
        login = staff_login(tc, setup["support_email"], setup["support_pw"])
        imp = start_support(tc, login.cookies, setup["client_id"])
        token = imp.json()["token"]

        activate = activate_support(tc, token)
        assert activate.status_code == 200, f"activate failed: {activate.text}"
        support_cookies = dict(activate.cookies)

        me = tc.get("/me", cookies=support_cookies)
        assert me.status_code == 200, f"/me in support mode failed: {me.text}"
        body = me.json()
        assert body["email"] == setup["client_email"], \
            f"/me should return CLIENT email, got: {body.get('email')}"
        assert body.get("is_support_session") is True, \
            "is_support_session must be True in support mode"

    def test_readonly_cannot_start_support_session(self, setup):
        """Rol readonly no puede iniciar sesión de soporte."""
        tc = setup["tc"]
        login = staff_login(tc, setup["readonly_email"], setup["readonly_pw"])
        assert login.status_code == 200
        resp = start_support(tc, login.cookies, setup["client_id"])
        assert resp.status_code == 403, \
            f"readonly should get 403 when starting support, got {resp.status_code}"

    def test_nonexistent_user_returns_404(self, setup):
        tc = setup["tc"]
        login = staff_login(tc, setup["support_email"], setup["support_pw"])
        resp = start_support(tc, login.cookies, 99999)
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 4 — PERMISOS DE ESCRITURA EN MODO SOPORTE
# ═══════════════════════════════════════════════════════════════════════════════

class TestWritePermissionsInSupportMode:

    def _support_cookies(self, setup) -> dict:
        """Devuelve cookies con support_token activo para rol support."""
        tc = setup["tc"]
        login = staff_login(tc, setup["support_email"], setup["support_pw"])
        imp = start_support(tc, login.cookies, setup["client_id"])
        activate = activate_support(tc, imp.json()["token"])
        return dict(activate.cookies)

    def test_topup_is_blocked(self, setup):
        """POST /user/topup debe retornar 403 en modo soporte."""
        tc = setup["tc"]
        cookies = self._support_cookies(setup)
        resp = tc.post("/user/topup", json={"amount": 10}, cookies=cookies)
        assert resp.status_code == 403, \
            f"topup should be BLOCKED in support mode, got {resp.status_code}: {resp.text}"

    def test_file_save_not_blocked_for_support_role(self, setup):
        """
        POST /files/{id}/save con rol support en modo soporte:
        - Debe llegar al handler (no ser bloqueado por require_support_write)
        - El 404 confirma que llegó al handler y solo falló porque el hosting no existe
        - Si fuera 403 significaría que la dependency bloqueó incorrectamente
        """
        tc = setup["tc"]
        cookies = self._support_cookies(setup)
        resp = tc.post(
            "/files/99999/save",
            json={"path": "index.html", "content": "<h1>ok</h1>"},
            cookies=cookies,
        )
        assert resp.status_code != 403, \
            f"file save should NOT return 403 for support role: {resp.text}"
        # 404 = llegó al handler, hosting no existe (correcto en tests sin Docker)
        assert resp.status_code == 404, \
            f"Expected 404 (no hosting), got {resp.status_code}: {resp.text}"

    def test_file_delete_not_blocked_for_support_role(self, setup):
        """DELETE /files/{id} con rol support en modo soporte → 404, no 403."""
        tc = setup["tc"]
        cookies = self._support_cookies(setup)
        resp = tc.delete("/files/99999?path=index.html", cookies=cookies)
        assert resp.status_code != 403, \
            f"file delete should NOT return 403 for support role: {resp.text}"
        assert resp.status_code == 404

    def test_hosting_delete_not_blocked_for_support_role(self, setup):
        """DELETE /delete-hosting/{id} con rol support → 404, no 403."""
        tc = setup["tc"]
        cookies = self._support_cookies(setup)
        resp = tc.delete("/delete-hosting/99999", cookies=cookies)
        assert resp.status_code != 403, \
            f"hosting delete should NOT return 403 for support role: {resp.text}"
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 5 — TABLA DE PERMISOS (visual, siempre pasa)
# ═══════════════════════════════════════════════════════════════════════════════

def test_permission_table_visual():
    """Imprime la tabla de permisos final para revisión. Siempre pasa."""
    rows = [
        #  Operación              Endpoint                            Client Admin  Suprt  Billg  Rdoly
        ("Leer archivos",        "GET /files/{id}",                   True, True,  True,  False, True),
        ("Editar archivo",       "POST /files/{id}/save",             True, True,  True,  False, False),
        ("Eliminar archivo",     "DELETE /files/{id}",                True, True,  True,  False, False),
        ("Subir ZIP",            "POST /hostings/{id}/upload-zip",    True, True,  True,  False, False),
        ("Ver logs",             "GET /hostings/{id}/logs",           True, True,  True,  False, True),
        ("Reiniciar hosting",    "POST /hostings/{id}/restart",       True, True,  True,  False, False),
        ("Detener hosting",      "POST /hostings/{id}/stop",          True, True,  True,  False, False),
        ("Iniciar hosting",      "POST /hostings/{id}/start",         True, True,  True,  False, False),
        ("Eliminar hosting",     "DELETE /delete-hosting/{id}",       True, True,  True,  False, False),
        ("Terminar (abuso)",     "DELETE /admin/hostings/{id}/term",  False,True,  False, False, False),
        ("Deploy GitHub",        "POST /deploy-from-github",          True, True,  True,  False, False),
        ("Ver metricas",         "GET /hostings/{id}/metrics",        True, True,  True,  False, True),
        ("Topup / saldo",        "POST /user/topup",                  True, False, False, True,  False),
        ("Config cuenta",        "POST /user/config",                 True, False, False, False, False),
        ("Crear colaborador",    "POST /admin/staff",                 False,True,  False, False, False),
        ("Listar clientes",      "GET /staff/clients",                False,False, True,  True,  True),
        ("Iniciar soporte",      "POST /admin/impersonate/staff/{id}",False,True,  True,  False, False),
    ]
    ok = " OK "
    no = " -- "
    hdr = f"{'Operacion':<22} {'Endpoint':<45} {'Client':>6} {'Admin':>5} {'Spprt':>5} {'Billg':>5} {'Rdoly':>5}"
    sep = "-" * len(hdr)
    print(f"\n{sep}")
    print(hdr)
    print(sep)
    for op, ep, cl, adm, sup, bil, ro in rows:
        f = lambda v: ok if v else no
        print(f"{op:<22} {ep:<45} {f(cl):>6} {f(adm):>5} {f(sup):>5} {f(bil):>5} {f(ro):>5}")
    print(sep)
    print("Dependency map:")
    print("  verify_token          -> authenticated, any role")
    print("  require_support_write -> if support session: caller_role must be admin or support")
    print("  require_not_support   -> blocks if any support session active (topup, billing)")
    print("  require_role('admin') -> only access_token with role=admin")
    print("  require_staff_role(X) -> only staff_token with role X")
    print(sep)
    assert True
