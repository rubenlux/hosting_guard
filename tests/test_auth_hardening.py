"""
test_auth_hardening.py

Tests for two security hardening features:
  A) Revoke-sessions enforcement — revoked_all:{user_id} Redis check in verify_token
  B) 2FA login enforcement — single-use challenge, backup codes, structured logging
"""

import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.api.main import app
from app.api.security import SECRET, ALGO

client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

class FakeRedis:
    """Minimal in-memory Redis substitute for tests."""
    def __init__(self, data=None):
        self._data = dict(data or {})

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value, ex=None):
        self._data[key] = str(value)

    def setex(self, key, ttl, value):
        self._data[key] = str(value)

    def exists(self, key):
        return 1 if key in self._data else 0

    def delete(self, key):
        self._data.pop(key, None)


def _access_token(user_id=2, email="user@t.com", role="user", iat=None, jti=None):
    """Create a signed access JWT with controllable iat."""
    now = iat if iat is not None else int(time.time())
    tok_jti = jti or str(uuid.uuid4())
    payload = {
        "user_id": user_id, "email": email, "role": role,
        "jti": tok_jti, "iat": now, "type": "access", "exp": now + 900,
    }
    return jwt.encode(payload, SECRET, algorithm=ALGO), tok_jti


def _pending_2fa_token(user_id=2, email="user@t.com", role="user", iat=None, exp_offset=180):
    """Create a signed pending_2fa JWT."""
    now = iat if iat is not None else int(time.time())
    tok_jti = str(uuid.uuid4())
    payload = {
        "user_id": user_id, "email": email, "role": role,
        "jti": tok_jti, "iat": now, "type": "2fa_pending", "exp": now + exp_offset,
    }
    return jwt.encode(payload, SECRET, algorithm=ALGO), tok_jti


def _make_2fa_conn_mock(user_id=2, totp_secret="TOTP_SECRET_BASE32",
                        totp_enabled=1, backup_codes=None):
    """Return a mock DB connection that emits a 2FA user row."""
    if backup_codes is None:
        backup_codes = json.dumps(["AAAA1111", "BBBB2222", "CCCC3333"])
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {
        "totp_secret": totp_secret,
        "totp_enabled": totp_enabled,
        "totp_backup_codes": backup_codes,
    }
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


# ── A. Revoke-sessions enforcement ────────────────────────────────────────────

class TestRevokeAllSessions:
    """
    Verify that _decode_and_validate rejects tokens whose iat ≤ revoked_all timestamp.
    Tests mock app.api.security._get_redis to control Redis state per test.
    """

    def test_token_before_revoke_at_rejected(self, db_mocks, monkeypatch):
        """iat < revoked_at → 401 Sesión revocada."""
        revoked_at = int(time.time())
        iat = revoked_at - 60
        fr = FakeRedis({f"revoked_all:{db_mocks['client_id']}": str(revoked_at)})
        monkeypatch.setattr("app.api.security._get_redis", lambda: fr)
        token, _ = _access_token(user_id=db_mocks["client_id"], iat=iat)

        r = client.get("/me", cookies={"access_token": token})
        assert r.status_code == 401

    def test_token_equal_revoke_at_rejected(self, db_mocks, monkeypatch):
        """iat == revoked_at → 401 (the <= boundary fix)."""
        ts = int(time.time())
        fr = FakeRedis({f"revoked_all:{db_mocks['client_id']}": str(ts)})
        monkeypatch.setattr("app.api.security._get_redis", lambda: fr)
        token, _ = _access_token(user_id=db_mocks["client_id"], iat=ts)

        r = client.get("/me", cookies={"access_token": token})
        assert r.status_code == 401

    def test_token_after_revoke_at_passes(self, db_mocks, monkeypatch):
        """iat > revoked_at → request succeeds."""
        revoked_at = int(time.time()) - 60
        iat = revoked_at + 30
        fr = FakeRedis({f"revoked_all:{db_mocks['client_id']}": str(revoked_at)})
        monkeypatch.setattr("app.api.security._get_redis", lambda: fr)
        token, _ = _access_token(user_id=db_mocks["client_id"], iat=iat)

        r = client.get("/me", cookies={"access_token": token})
        assert r.status_code == 200

    def test_no_revoke_key_token_passes(self, db_mocks, monkeypatch):
        """No revoked_all key set → token passes normally."""
        fr = FakeRedis()
        monkeypatch.setattr("app.api.security._get_redis", lambda: fr)
        token, _ = _access_token(user_id=db_mocks["client_id"])

        r = client.get("/me", cookies={"access_token": token})
        assert r.status_code == 200

    def test_redis_unavailable_warns_and_passes(self, db_mocks, monkeypatch, caplog):
        """Redis unavailable → warning logged, token not blocked (fail-open)."""
        import logging
        monkeypatch.setattr("app.api.security._get_redis", lambda: None)
        monkeypatch.setattr("app.api.security._revoked_tokens", {})
        token, _ = _access_token(user_id=db_mocks["client_id"])

        with caplog.at_level(logging.WARNING, logger="app.api.security"):
            r = client.get("/me", cookies={"access_token": token})

        assert r.status_code == 200
        assert "revoke_all" in caplog.text

    def test_revoke_sessions_endpoint_sets_redis_key(self, db_mocks, monkeypatch):
        """POST /auth/revoke-sessions writes revoked_all:{user_id} to Redis."""
        fr = FakeRedis()
        monkeypatch.setattr("app.api.security._get_redis", lambda: fr)
        monkeypatch.setattr("app.infra.redis_client.get_redis", lambda: fr)
        token, _ = _access_token(user_id=db_mocks["client_id"],
                                  email=db_mocks["client_email"])

        r = client.post("/auth/revoke-sessions", cookies={"access_token": token})

        assert r.status_code == 200
        assert f"revoked_all:{db_mocks['client_id']}" in fr._data


# ── B. 2FA login enforcement ──────────────────────────────────────────────────

class TestTwoFactorLogin:

    def test_login_without_2fa_returns_token(self, db_mocks):
        """Normal login (totp_enabled absent/0) → access_token cookie issued."""
        r = client.post("/login", json={
            "email": db_mocks["client_email"],
            "password": db_mocks["client_pw"],
        })
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert "access_token" in r.cookies

    def test_login_with_2fa_returns_2fa_required(self, db_mocks):
        """Login with totp_enabled=1 → 2fa_required, no access_token cookie."""
        db_mocks["users_by_email"][db_mocks["client_email"]]["totp_enabled"] = 1
        try:
            r = client.post("/login", json={
                "email": db_mocks["client_email"],
                "password": db_mocks["client_pw"],
            })
            assert r.status_code == 200
            assert r.json()["status"] == "2fa_required"
            assert "access_token" not in r.cookies
        finally:
            db_mocks["users_by_email"][db_mocks["client_email"]]["totp_enabled"] = 0

    def test_login_with_2fa_body_has_no_token(self, db_mocks):
        """2fa_required response body must not contain access_token or refresh_token."""
        db_mocks["users_by_email"][db_mocks["client_email"]]["totp_enabled"] = 1
        try:
            r = client.post("/login", json={
                "email": db_mocks["client_email"],
                "password": db_mocks["client_pw"],
            })
            body = r.json()
            assert "access_token" not in body
            assert "refresh_token" not in body
        finally:
            db_mocks["users_by_email"][db_mocks["client_email"]]["totp_enabled"] = 0

    def test_verify_2fa_valid_otp_issues_session(self, db_mocks, monkeypatch):
        """Valid OTP → status ok + access_token cookie."""
        conn_mock, _ = _make_2fa_conn_mock(user_id=db_mocks["client_id"])
        pending, _ = _pending_2fa_token(user_id=db_mocks["client_id"],
                                         email=db_mocks["client_email"])
        mock_totp = MagicMock()
        mock_totp.verify.return_value = True

        with patch("app.infra.db.get_connection", return_value=conn_mock), \
             patch("app.infra.db.release_connection"), \
             patch("pyotp.TOTP", return_value=mock_totp):
            r = client.post(
                "/auth/2fa/verify-login",
                json={"token": "123456"},
                cookies={"pending_2fa": pending},
            )

        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert "access_token" in r.cookies

    def test_verify_2fa_invalid_otp_401(self, db_mocks):
        """Invalid OTP → 401, no access_token issued."""
        conn_mock, _ = _make_2fa_conn_mock(user_id=db_mocks["client_id"])
        pending, _ = _pending_2fa_token(user_id=db_mocks["client_id"],
                                         email=db_mocks["client_email"])
        mock_totp = MagicMock()
        mock_totp.verify.return_value = False

        with patch("app.infra.db.get_connection", return_value=conn_mock), \
             patch("app.infra.db.release_connection"), \
             patch("pyotp.TOTP", return_value=mock_totp):
            r = client.post(
                "/auth/2fa/verify-login",
                json={"token": "000000"},
                cookies={"pending_2fa": pending},
            )

        assert r.status_code == 401
        assert "access_token" not in r.cookies

    def test_verify_2fa_expired_challenge_401(self, db_mocks):
        """Expired pending_2fa cookie → 401 (JWT expiry enforced)."""
        # iat 400s ago, exp = iat+180 → expired 220s ago
        pending, _ = _pending_2fa_token(
            user_id=db_mocks["client_id"],
            iat=int(time.time()) - 400,
            exp_offset=180,
        )
        r = client.post(
            "/auth/2fa/verify-login",
            json={"token": "123456"},
            cookies={"pending_2fa": pending},
        )
        assert r.status_code == 401

    def test_verify_2fa_single_use(self, db_mocks, monkeypatch):
        """After one successful OTP verify, the same pending token is rejected."""
        fr = FakeRedis()
        monkeypatch.setattr("app.api.security._get_redis", lambda: fr)

        conn_mock, _ = _make_2fa_conn_mock(user_id=db_mocks["client_id"])
        pending, _ = _pending_2fa_token(user_id=db_mocks["client_id"],
                                         email=db_mocks["client_email"])
        mock_totp = MagicMock()
        mock_totp.verify.return_value = True

        with patch("app.infra.db.get_connection", return_value=conn_mock), \
             patch("app.infra.db.release_connection"), \
             patch("pyotp.TOTP", return_value=mock_totp):
            r1 = client.post(
                "/auth/2fa/verify-login",
                json={"token": "123456"},
                cookies={"pending_2fa": pending},
            )
        assert r1.status_code == 200

        # Reuse same pending cookie → must be rejected
        with patch("app.infra.db.get_connection", return_value=conn_mock), \
             patch("app.infra.db.release_connection"), \
             patch("pyotp.TOTP", return_value=mock_totp):
            r2 = client.post(
                "/auth/2fa/verify-login",
                json={"token": "123456"},
                cookies={"pending_2fa": pending},
            )
        assert r2.status_code == 401

    def test_verify_2fa_backup_code_accepted(self, db_mocks):
        """Valid backup code accepted when TOTP fails."""
        backup = "AAAA1111"
        conn_mock, mock_cursor = _make_2fa_conn_mock(
            user_id=db_mocks["client_id"],
            backup_codes=json.dumps([backup, "BBBB2222"]),
        )
        pending, _ = _pending_2fa_token(user_id=db_mocks["client_id"],
                                         email=db_mocks["client_email"])
        mock_totp = MagicMock()
        mock_totp.verify.return_value = False  # TOTP fails → falls through to backup

        with patch("app.infra.db.get_connection", return_value=conn_mock), \
             patch("app.infra.db.release_connection"), \
             patch("pyotp.TOTP", return_value=mock_totp):
            r = client.post(
                "/auth/2fa/verify-login",
                json={"token": backup},
                cookies={"pending_2fa": pending},
            )

        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_verify_2fa_no_otp_in_logs(self, db_mocks, caplog):
        """OTP value must never appear in log output (even on failure)."""
        import logging
        SECRET_OTP = "MYSECRETOTP"
        conn_mock, _ = _make_2fa_conn_mock(user_id=db_mocks["client_id"])
        pending, _ = _pending_2fa_token(user_id=db_mocks["client_id"],
                                         email=db_mocks["client_email"])
        mock_totp = MagicMock()
        mock_totp.verify.return_value = False

        with caplog.at_level(logging.DEBUG):
            with patch("app.infra.db.get_connection", return_value=conn_mock), \
                 patch("app.infra.db.release_connection"), \
                 patch("pyotp.TOTP", return_value=mock_totp):
                client.post(
                    "/auth/2fa/verify-login",
                    json={"token": SECRET_OTP},
                    cookies={"pending_2fa": pending},
                )

        assert SECRET_OTP not in caplog.text
