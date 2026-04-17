"""
Tests: flujo completo staff login → soporte → permisos de escritura.
Usa db_mocks + tc del conftest (sin PostgreSQL real).
"""


def _staff_login(tc, email, pw):
    return tc.post("/staff/login", json={"email": email, "password": pw})

def _user_login(tc, email, pw):
    return tc.post("/login", json={"email": email, "password": pw})

def _staff_ck(tc, db):
    r = _staff_login(tc, db["support_email"], db["support_pw"])
    assert r.status_code == 200, r.text
    return dict(r.cookies)


# ─── 1-2) Staff login ──────────────────────────────────────────────────────────

def test_staff_login_valid(tc, db_mocks):
    r = _staff_login(tc, db_mocks["support_email"], db_mocks["support_pw"])
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "staff_token" in r.cookies

def test_staff_login_wrong_password(tc, db_mocks):
    r = _staff_login(tc, db_mocks["support_email"], "WRONG")
    assert r.status_code == 401

def test_staff_login_unknown_email(tc, db_mocks):
    r = _staff_login(tc, "nadie@noemail.com", "cualquier")
    assert r.status_code == 401

# ─── 3) Staff inactivo ────────────────────────────────────────────────────────

def test_inactive_staff_cannot_login(tc, db_mocks):
    db_mocks["staff_by_email"][db_mocks["support_email"]]["is_active"] = 0
    r = _staff_login(tc, db_mocks["support_email"], db_mocks["support_pw"])
    db_mocks["staff_by_email"][db_mocks["support_email"]]["is_active"] = 1  # restaurar
    assert r.status_code == 403

# ─── 4-5) GET /staff/me ───────────────────────────────────────────────────────

def test_staff_me_without_cookie_returns_401(tc, db_mocks):
    assert tc.get("/staff/me").status_code == 401

def test_staff_me_with_valid_cookie(tc, db_mocks):
    ck = _staff_ck(tc, db_mocks)
    r = tc.get("/staff/me", cookies=ck)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == db_mocks["support_email"]
    assert "password_hash" not in body

# ─── 6) Iniciar sesión de soporte ─────────────────────────────────────────────

def test_staff_starts_support_session(tc, db_mocks):
    ck = _staff_ck(tc, db_mocks)
    r = tc.post(
        f"/admin/impersonate/staff/{db_mocks['client_id']}",
        cookies=ck,
        json={"issue_description": "El sitio no carga", "origin": "client_request"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "session_id" in body
    assert "token" in body  # token crudo, se activa vía /support/activate

# ─── 7) support_token activo → /me ve datos del cliente ──────────────────────

def _activate_support(tc, token: str) -> dict:
    """Activa el support_token via /support/activate y retorna las cookies."""
    r = tc.post("/support/activate", json={"token": token})
    assert r.status_code == 200, f"activate failed: {r.text}"
    return dict(r.cookies)

def test_support_token_gives_client_context(tc, db_mocks):
    ck = _staff_ck(tc, db_mocks)
    start = tc.post(f"/admin/impersonate/staff/{db_mocks['client_id']}", cookies=ck)
    assert start.status_code == 200
    token = start.json()["token"]
    support_ck = _activate_support(tc, token)

    me = tc.get("/me", cookies=support_ck)
    assert me.status_code == 200
    assert me.json()["email"] == db_mocks["client_email"]
    assert me.json()["is_support_session"] is True

# ─── 8) Topup bloqueado en soporte ────────────────────────────────────────────

def test_topup_blocked_in_support_session(tc, db_mocks):
    ck = _staff_ck(tc, db_mocks)
    start = tc.post(f"/admin/impersonate/staff/{db_mocks['client_id']}", cookies=ck)
    token = start.json()["token"]
    support_ck = _activate_support(tc, token)
    r = tc.post("/user/topup", json={"amount": 10}, cookies=support_ck)
    assert r.status_code == 403

# ─── 9) Rol readonly no puede iniciar sesiones ────────────────────────────────

def test_readonly_cannot_start_session(tc, db_mocks):
    r = _staff_login(tc, db_mocks["readonly_email"], db_mocks["readonly_pw"])
    assert r.status_code == 200
    ck = dict(r.cookies)
    r2 = tc.post(f"/admin/impersonate/staff/{db_mocks['client_id']}", cookies=ck)
    assert r2.status_code == 403
