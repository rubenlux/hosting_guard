import json
import logging
import os
import time
from datetime import datetime, timezone

from typing import Optional
from fastapi import Depends, FastAPI, Request, HTTPException, Response, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import generate_latest
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

import time as _time_module
from app.api.config import APP_ENV, ENABLE_ACTION_EXECUTION, ENABLE_AI_ADVISORY
from app.api.rate_limit import limiter
from app.api.schemas import DecisionRequest, DecisionResponse, HumanActionRequest
from app.api.security import create_token, create_refresh_token, verify_token, revoke_token, require_role, require_not_support, SECRET, ALGO, _is_revoked
from app.api.security_headers import SecurityHeadersMiddleware
from app.api.correlation import CorrelationMiddleware
from app.api.tenancy import Tenant
from app.api.tenant_resolver import resolve_tenant
from app.infra.audit.user_repository import UserRepository
from app.lifespan import lifespan
import bcrypt
from pydantic import BaseModel, EmailStr
from app.core.ai_advisory_engine import generate_advisory
from app.core.ai_orchestrator import AIOrchestrator
from app.core.decision_pipeline import run_decision_pipeline
from app.core.execution.engine import ExecutionEngine
from app.core.llm.fake_llm import RuleBasedFakeLLM
from app.core.rag.tenant_in_memory_provider import TenantInMemoryKnowledgeProvider
from app.infra.audit.execution_repository import ExecutionRepository
from app.infra.audit.human_repository import HumanActionRepository
from app.infra.audit.repository import AuditRepository
from app.infra.config.repository import TenantConfigRepository
from app.observability.metrics import (
    DECISION_LATENCY,
    DECISIONS_BY_STATUS,
    DECISIONS_TOTAL,
    HUMAN_ACTIONS_TOTAL,
)

from app.infra.logging_config import setup_logging
setup_logging()
logger = logging.getLogger("hosting_guard_audit")


from app.infra.db import init_db_pool
# maxconn=20 per worker: 2 Uvicorn workers × 20 = 40 app conns + 10 scheduler = 50 total.
# PostgreSQL default max_connections=100 — stay well under it.
init_db_pool(minconn=2, maxconn=20)

app = FastAPI(
    title="Hosting Guard API",
    description="Decision API for hosting diagnostics and safety evaluation",
    version="1.16.0",
    lifespan=lifespan,
)

# Servidores de repositorio de usuarios
user_repo = UserRepository()

# Importar y registrar sub-routers
from app.api.routes.pixel import router as pixel_router
from app.api.routes.files import router as files_router
from app.api.routes.impersonate import router as impersonate_router
from app.api.routes.staff import router as staff_router
from app.api.routes.staff_activity import router as staff_activity_router
from app.api.routes.health import router as health_router
from app.api.routes.alerts import router as alerts_router
from app.api.routes.import_hosting import router as import_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.backup import router as backup_router
from app.api.routes.billing import router as billing_router
from app.api.routes.presence import router as presence_router
from app.api.routes.wp_audit import router as wp_audit_router
app.include_router(pixel_router)
app.include_router(files_router)
app.include_router(impersonate_router)
app.include_router(staff_router)
app.include_router(staff_activity_router)
app.include_router(health_router)
app.include_router(alerts_router)
app.include_router(import_router)
app.include_router(notifications_router)
app.include_router(backup_router)
app.include_router(billing_router)
app.include_router(presence_router)
app.include_router(wp_audit_router)


_IS_PRODUCTION = APP_ENV == "production"

# Flags de seguridad para cookies de sesión.
#
# PRODUCCIÓN (APP_ENV=production):
#   Secure=True   → solo se envían sobre HTTPS (obligatorio con SameSite=None o en general)
#   SameSite=Lax  → permite peticiones cross-origin same-site (hostingguard.lat → api.hostingguard.lat)
#   Domain=hostingguard.lat → cubre todos los subdominios; evita ambigüedad con cookies host-only
#
# DESARROLLO (APP_ENV=development):
#   Secure=False  → permite HTTP en localhost
#   SameSite=Lax  → mismo comportamiento
#   Sin domain    → host-only a localhost
#
# NOTA: SameSite=Strict fue cambiado a Lax en producción porque aunque ambos dominios son
# same-site (mismo eTLD+1), ciertos navegadores tratan peticiones XHR cross-origin como
# "cross-site" en contextos edge. Lax es el balance correcto: seguro + funcional.
_COOKIE_SECURE   = _IS_PRODUCTION
_COOKIE_SAMESITE = "lax"
_COOKIE_DOMAIN   = "hostingguard.lat" if _IS_PRODUCTION else None
_ACCESS_TOKEN_TTL  = 15 * 60
_REFRESH_TOKEN_TTL = 7 * 24 * 60 * 60


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Establece las dos cookies de sesión con los flags de seguridad correctos."""
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        domain=_COOKIE_DOMAIN,
        max_age=_ACCESS_TOKEN_TTL,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        domain=_COOKIE_DOMAIN,
        max_age=_REFRESH_TOKEN_TTL,
        path="/refresh",
    )


def _clear_auth_cookies(response: Response) -> None:
    """Elimina las cookies de sesión. Domain y path deben coincidir exactamente con el set."""
    response.delete_cookie("access_token",  path="/",        domain=_COOKIE_DOMAIN)
    response.delete_cookie("refresh_token", path="/refresh", domain=_COOKIE_DOMAIN)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    phone: str


@app.get("/")
def root():
    return {
        "service": "HostingGuard API",
        "status": "ok"
    }

@app.post("/register")
@limiter.limit("5/minute")
def register(request: Request, body: RegisterRequest):
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres")
    hashed_password = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    try:
        user_id = user_repo.create_user(
            body.email,
            hashed_password,
            first_name=body.first_name.strip(),
            last_name=body.last_name.strip(),
            phone=body.phone.strip(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Create verification token and send email (best-effort — never block registration)
    try:
        from app.infra.auth_token_repository import AuthTokenRepository
        from app.services.mailer import send_verification_email
        token = AuthTokenRepository().create_token(user_id, "email_verification", expires_minutes=1440)
        send_verification_email(body.email, body.first_name.strip(), token)
    except Exception as exc:
        logger.error("Failed to send verification email to %s: %s", body.email, exc)

    return {"email": body.email, "status": "registered"}


@app.get("/auth/verify-email")
@limiter.limit("10/minute")
def verify_email(request: Request, token: str):
    from app.infra.auth_token_repository import AuthTokenRepository
    repo = AuthTokenRepository()
    record = repo.get_valid_token(token, "email_verification")
    if not record:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")
    repo.mark_used(token)
    user_repo.set_email_verified(record["user_id"])
    try:
        from app.services.notification_service import notify
        notify(
            record["user_id"],
            "Email verificado",
            "Tu dirección de correo fue verificada correctamente. "
            "Ya podés acceder a todas las funciones de tu cuenta.",
            category="account", severity="success", channel="both",
        )
    except Exception:
        pass
    return {"status": "verified"}


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

@app.post("/auth/forgot-password")
@limiter.limit("3/minute")
def forgot_password(request: Request, body: ForgotPasswordRequest):
    # Always return success to avoid email enumeration
    user = user_repo.get_user_by_email(body.email)
    if user:
        try:
            from app.infra.auth_token_repository import AuthTokenRepository
            from app.services.mailer import send_password_reset_email
            token = AuthTokenRepository().create_token(user["user_id"], "password_reset", expires_minutes=60)
            first = user.get("first_name") or user["email"].split("@")[0]
            send_password_reset_email(body.email, first, token)
        except Exception as exc:
            logger.error("Failed to send password reset email to %s: %s", body.email, exc)
    return {"status": "ok", "detail": "Si el email existe, recibirás un enlace en tu casilla."}


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

@app.post("/auth/reset-password")
@limiter.limit("5/minute")
def reset_password(request: Request, body: ResetPasswordRequest):
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres")
    from app.infra.auth_token_repository import AuthTokenRepository
    repo = AuthTokenRepository()
    record = repo.get_valid_token(body.token, "password_reset")
    if not record:
        raise HTTPException(status_code=400, detail="El enlace es inválido o ya expiró")
    repo.mark_used(body.token)
    new_hash = bcrypt.hashpw(body.new_password.encode(), bcrypt.gensalt()).decode()
    user_repo.update_password(record["user_id"], new_hash)
    try:
        from app.services.notification_service import notify
        notify(
            record["user_id"],
            "Contraseña restablecida",
            "Tu contraseña fue cambiada exitosamente. Si no realizaste este cambio, "
            "contactá soporte de inmediato.",
            category="security", severity="warning", channel="both",
        )
    except Exception:
        pass
    return {"status": "ok", "detail": "Contraseña actualizada. Ya podés iniciar sesión."}


class ChangeEmailRequest(BaseModel):
    new_email: EmailStr
    password: str

@app.post("/auth/change-email")
@limiter.limit("3/minute")
def change_email(request: Request, body: ChangeEmailRequest, user: dict = Depends(verify_token)):
    user_db = user_repo.get_user_by_id(user["user_id"])
    if not user_db or not bcrypt.checkpw(body.password.encode(), user_db["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    existing = user_repo.get_user_by_email(body.new_email)
    if existing and existing["user_id"] != user["user_id"]:
        raise HTTPException(status_code=400, detail="El email ya está en uso")
    old_email = user["email"]
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET email=%s, email_verified=0 WHERE user_id=%s",
                    (body.new_email, user["user_id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Error al actualizar email")
    finally:
        release_connection(conn)
    # Send verification to new email
    try:
        from app.infra.auth_token_repository import AuthTokenRepository
        from app.services.mailer import send_verification_email
        token = AuthTokenRepository().create_token(user["user_id"], "email_verification", expires_minutes=1440)
        first = user_db.get("first_name") or body.new_email.split("@")[0]
        send_verification_email(body.new_email, first, token)
    except Exception as exc:
        logger.error("Email change verification send failed: %s", exc)
    # Notify about the change
    try:
        from app.services.notification_service import notify
        notify(user["user_id"], "Email de cuenta cambiado",
               f"El email de tu cuenta cambió de '{old_email}' a '{body.new_email}'. "
               "Si no realizaste este cambio, contactá soporte de inmediato.",
               category="security", severity="warning", channel="both")
    except Exception:
        pass
    return {"status": "ok", "detail": "Email actualizado. Revisá tu nueva casilla para verificar."}


class ResendVerificationRequest(BaseModel):
    email: EmailStr

@app.post("/auth/resend-verification")
@limiter.limit("3/minute")
def resend_verification(request: Request, body: ResendVerificationRequest):
    user = user_repo.get_user_by_email(body.email)
    if user and not user.get("email_verified"):
        try:
            from app.infra.auth_token_repository import AuthTokenRepository
            from app.services.mailer import send_verification_email
            token = AuthTokenRepository().create_token(user["user_id"], "email_verification", expires_minutes=1440)
            first = user.get("first_name") or user["email"].split("@")[0]
            send_verification_email(body.email, first, token)
        except Exception as exc:
            logger.error("Failed to resend verification to %s: %s", body.email, exc)
    return {"status": "ok", "detail": "Si el email existe y no está verificado, recibirás el enlace."}


@app.post("/auth/revoke-sessions")
def revoke_sessions(user: dict = Depends(verify_token)):
    """Invalidates all sessions for this user (except current request)."""
    from app.infra.redis_client import get_redis
    r = get_redis()
    user_id = user["user_id"]
    if r:
        import time as _time_mod
        r.set(f"revoked_all:{user_id}", str(_time_mod.time()), ex=86400 * 30)
    try:
        from app.services.notification_service import notify
        notify(user_id, "Todas las sesiones cerradas",
               "Todas las sesiones activas de tu cuenta fueron cerradas. "
               "Si no realizaste esta acción, cambiá tu contraseña de inmediato.",
               category="security", severity="warning", channel="both")
    except Exception:
        pass
    return {"status": "ok", "detail": "Todas las sesiones han sido cerradas."}


import secrets as _secrets_mod
import base64


class TotpSetupResponse(BaseModel):
    secret: str
    qr_url: str
    backup_codes: list


class TotpVerifyRequest(BaseModel):
    token: str


class TotpDisableRequest(BaseModel):
    token: str


@app.post("/auth/2fa/setup")
@limiter.limit("5/minute")
def setup_2fa(request: Request, user: dict = Depends(verify_token)):
    """Generate a TOTP secret and return setup info. Does NOT enable 2FA yet."""
    try:
        import pyotp
    except ImportError:
        raise HTTPException(status_code=501, detail="2FA no disponible en este servidor")
    secret = pyotp.random_base32()
    email = user["email"]
    totp = pyotp.TOTP(secret)
    qr_url = totp.provisioning_uri(name=email, issuer_name="HostingGuard")
    backup_codes = [_secrets_mod.token_hex(4).upper() for _ in range(8)]
    # Store secret temporarily in user record (not enabled yet)
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        import json
        cur.execute(
            "UPDATE users SET totp_secret=%s, totp_backup_codes=%s WHERE user_id=%s",
            (secret, json.dumps(backup_codes), user["user_id"])
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Error guardando configuración 2FA")
    finally:
        release_connection(conn)
    return {"secret": secret, "qr_url": qr_url, "backup_codes": backup_codes}


@app.post("/auth/2fa/enable")
@limiter.limit("10/minute")
def enable_2fa(request: Request, body: TotpVerifyRequest, user: dict = Depends(verify_token)):
    """Verify OTP token and enable 2FA for this account."""
    try:
        import pyotp
    except ImportError:
        raise HTTPException(status_code=501, detail="2FA no disponible en este servidor")
    user_db = user_repo.get_user_by_id(user["user_id"])
    if not user_db:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    secret = user_db.get("totp_secret")
    if not secret:
        raise HTTPException(status_code=400, detail="Primero configurá el 2FA (/auth/2fa/setup)")
    totp = pyotp.TOTP(secret)
    if not totp.verify(body.token, valid_window=1):
        raise HTTPException(status_code=400, detail="Código inválido")
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET totp_enabled=1 WHERE user_id=%s", (user["user_id"],))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)
    try:
        from app.services.notification_service import notify
        notify(user["user_id"], "Autenticación de dos factores activada",
               "El 2FA fue activado en tu cuenta. Ahora necesitarás tu app autenticadora para iniciar sesión.",
               category="security", severity="success", channel="both")
    except Exception:
        pass
    return {"status": "ok", "detail": "2FA activado correctamente"}


@app.post("/auth/2fa/disable")
@limiter.limit("5/minute")
def disable_2fa(request: Request, body: TotpDisableRequest, user: dict = Depends(verify_token)):
    """Disable 2FA after verifying current OTP."""
    try:
        import pyotp
    except ImportError:
        raise HTTPException(status_code=501, detail="2FA no disponible en este servidor")
    user_db = user_repo.get_user_by_id(user["user_id"])
    if not user_db:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    secret = user_db.get("totp_secret")
    if not secret or not user_db.get("totp_enabled"):
        raise HTTPException(status_code=400, detail="2FA no está activado")
    # Check OTP or backup code
    totp = pyotp.TOTP(secret)
    valid = totp.verify(body.token, valid_window=1)
    if not valid:
        import json
        backup_codes = user_db.get("totp_backup_codes")
        if backup_codes:
            codes = json.loads(backup_codes) if isinstance(backup_codes, str) else backup_codes
            valid = body.token.upper() in codes
    if not valid:
        raise HTTPException(status_code=400, detail="Código inválido")
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET totp_enabled=0, totp_secret=NULL, totp_backup_codes=NULL WHERE user_id=%s",
                    (user["user_id"],))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)
    try:
        from app.services.notification_service import notify
        notify(user["user_id"], "Autenticación de dos factores desactivada",
               "El 2FA fue desactivado en tu cuenta. Te recomendamos reactivarlo para mayor seguridad.",
               category="security", severity="warning", channel="both")
    except Exception:
        pass
    return {"status": "ok", "detail": "2FA desactivado"}


@app.post("/auth/2fa/verify-login")
@limiter.limit("5/minute")
def verify_2fa_login(request: Request, response: Response, body: TotpVerifyRequest):
    """Second step of login when 2FA is enabled. Exchanges pending_2fa cookie for real session."""
    pending = request.cookies.get("pending_2fa")
    if not pending:
        raise HTTPException(status_code=400, detail="No hay verificación 2FA pendiente")
    try:
        payload = jwt.decode(pending, SECRET, algorithms=[ALGO])
    except JWTError:
        raise HTTPException(status_code=401, detail="Sesión 2FA expirada, iniciá sesión de nuevo")
    if payload.get("type") != "2fa_pending":
        raise HTTPException(status_code=401, detail="Token inválido")

    user_id = payload["user_id"]
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT totp_secret, totp_backup_codes, totp_enabled FROM users WHERE user_id=%s", (user_id,))
        row = cur.fetchone()
    finally:
        release_connection(conn)

    if not row or not row.get("totp_enabled") or not row.get("totp_secret"):
        raise HTTPException(status_code=400, detail="2FA no activo en esta cuenta")

    try:
        import pyotp
    except ImportError:
        raise HTTPException(status_code=501, detail="2FA no disponible en este servidor")

    totp = pyotp.TOTP(row["totp_secret"])
    valid = totp.verify(body.token, valid_window=1)
    if not valid:
        # Try backup codes
        backup_codes = (row.get("totp_backup_codes") or "").split(",")
        if body.token in backup_codes:
            remaining = [c for c in backup_codes if c != body.token]
            conn2 = get_connection()
            try:
                conn2.cursor().execute(
                    "UPDATE users SET totp_backup_codes=%s WHERE user_id=%s",
                    (",".join(remaining), user_id)
                )
                conn2.commit()
            finally:
                release_connection(conn2)
            valid = True
    if not valid:
        raise HTTPException(status_code=401, detail="Código incorrecto")

    # Clear pending cookie, issue real session
    response.delete_cookie("pending_2fa", path="/")
    claims = {"user_id": payload["user_id"], "email": payload["email"], "role": payload.get("role", "user")}
    _set_auth_cookies(response, create_token(claims), create_refresh_token(claims))
    return {"status": "ok", "account_type": "user"}


@app.post("/login")
@limiter.limit("5/minute")
def login(request: Request, response: Response, body: LoginRequest):
    ip = request.client.host if request.client else "unknown"
    try:
        user = user_repo.get_user_by_email(body.email)

        if user and bcrypt.checkpw(body.password.encode(), user["password_hash"].encode()):
            # Login de cliente / admin normal
            try:
                user_repo.log_login_attempt(body.email, ip, success=True)
            except Exception as _log_err:
                logger.warning("log_login_attempt failed (non-fatal): %s", _log_err)
            # Detect suspicious login: N failed attempts before this success
            try:
                from app.infra.db import get_connection, release_connection as _rc
                from datetime import datetime as _dt_cls, timezone as _tz_cls, timedelta as _td_cls
                _conn = get_connection()
                _cur = _conn.cursor()
                _cutoff = (_dt_cls.now(_tz_cls.utc) - _td_cls(minutes=15)).isoformat()
                _cur.execute(
                    "SELECT COUNT(*) AS cnt FROM login_audit WHERE email=%s AND success=0 AND created_at>%s",
                    (body.email, _cutoff)
                )
                _row = _cur.fetchone()
                _rc(_conn)
                _failed = _row["cnt"] if _row else 0
                if _failed >= 3:
                    from app.services.notification_service import notify as _notify
                    _notify(user["user_id"], "Inicio de sesión sospechoso",
                            f"Se detectaron {_failed} intentos fallidos en los últimos 15 minutos "
                            f"antes de este inicio de sesión desde IP {ip}. "
                            "Si no fuiste vos, cambiá tu contraseña.",
                            category="security", severity="warning", channel="both")
            except Exception:
                pass
            try:
                from app.services.notification_service import notify
                notify(
                    user["user_id"],
                    "Nuevo inicio de sesión",
                    f"Se inició sesión en tu cuenta desde la IP {ip}. "
                    "Si no fuiste vos, cambiá tu contraseña de inmediato.",
                    category="security", severity="info", channel="both",
                )
            except Exception:
                pass
            # 2FA gate: if enabled, issue a short-lived pending token instead of full session
            if user.get("totp_enabled"):
                _pending_payload = {
                    "user_id": user["user_id"],
                    "email":   user["email"],
                    "role":    user.get("role", "user"),
                    "jti":     str(uuid.uuid4()),
                    "exp":     datetime.now(timezone.utc) + timedelta(minutes=3),
                    "type":    "2fa_pending",
                }
                _pending_token = jwt.encode(_pending_payload, SECRET, algorithm=ALGO)
                _secure = APP_ENV == "production"
                response.set_cookie(
                    key="pending_2fa", value=_pending_token,
                    httponly=True, secure=_secure, samesite="lax",
                    max_age=180, path="/",
                )
                return {"status": "2fa_required"}

            claims = {"user_id": user["user_id"], "email": user["email"], "role": user.get("role", "user")}
            _set_auth_cookies(response, create_token(claims), create_refresh_token(claims))
            try:
                from app.services.activity_service import log_event as _log
                _log(user_id=user["user_id"], event_type="login_success", category="auth",
                     title="Inicio de sesión", message=f"IP: {ip}",
                     ip=ip, user_agent=request.headers.get("user-agent"), source="login")
            except Exception:
                pass
            return {"status": "ok", "account_type": "user"}

        # Fallback: verificar si es un colaborador (staff_accounts).
        # Wrapped in try/except: if the table doesn't exist yet (pending migration in prod),
        # login degrades gracefully for regular users instead of returning 500.
        try:
            from app.infra.audit.staff_repository import StaffRepository
            _staff = StaffRepository().get_staff_by_email(body.email)
            if _staff and _staff.get("is_active"):
                _stored = (_staff.get("password_hash") or "").strip()
                try:
                    _ok = bcrypt.checkpw(body.password.encode("utf-8"), _stored.encode("utf-8"))
                except Exception:
                    _ok = False
                if _ok:
                    from app.api.security import create_staff_token
                    _token = create_staff_token({
                        "staff_id":  _staff["staff_id"],
                        "email":     _staff["email"],
                        "full_name": _staff["full_name"],
                        "role":      _staff["role"],
                    })
                    _secure = APP_ENV == "production"
                    response.set_cookie(
                        key="staff_token", value=_token, httponly=True,
                        secure=_secure, samesite="lax", max_age=8 * 3600, path="/",
                    )
                    try:
                        StaffRepository().update_last_login(_staff["staff_id"])
                    except Exception:
                        pass
                    return {"status": "ok", "account_type": "staff"}
        except Exception as _staff_err:
            logger.warning("Staff lookup failed during login (non-fatal): %s", _staff_err)

        try:
            user_repo.log_login_attempt(body.email, ip, success=False, detail="Invalid credentials")
        except Exception as _log_err:
            logger.warning("log_login_attempt (fail) error (non-fatal): %s", _log_err)

        raise HTTPException(status_code=401, detail="Invalid credentials")

    except HTTPException:
        raise
    except Exception as _login_err:
        # Captura cualquier excepción inesperada — log real para diagnóstico, nunca 500 al client
        logger.error("CRITICAL: Unexpected error in /login — %s: %s", type(_login_err).__name__, _login_err, exc_info=True)
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/logout")
def logout(response: Response, user=Depends(verify_token)):
    # Revocar access token
    jti = user.get("jti")
    exp = user.get("exp")
    if jti and exp:
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
        revoke_token(jti, expires_at=expires_at)
    _clear_auth_cookies(response)
    return {"status": "ok", "detail": "Sesión cerrada correctamente"}


@app.post("/refresh/revoke")
@limiter.limit("10/minute")
def revoke_refresh(request: Request, response: Response):
    """
    Revoca el refresh_token activo.
    El browser envía la cookie refresh_token aquí (path=/refresh) pero NO en /logout,
    por eso este endpoint existe separado. Llamar desde el frontend justo antes de /logout.
    """
    from jose import jwt, JWTError
    refresh_token_value = request.cookies.get("refresh_token")
    if not refresh_token_value:
        return {"status": "ok"}  # Nada que revocar
    try:
        payload = jwt.decode(refresh_token_value, SECRET, algorithms=[ALGO])
        r_jti = payload.get("jti")
        r_exp = payload.get("exp")
        if r_jti and r_exp:
            revoke_token(r_jti, datetime.fromtimestamp(r_exp, tz=timezone.utc))
    except JWTError:
        pass  # Token ya inválido — nada que hacer
    return {"status": "ok"}

@app.post("/refresh")
@limiter.limit("10/minute")
def refresh(request: Request, response: Response):
    from jose import jwt, JWTError
    refresh_token_value = request.cookies.get("refresh_token")
    if not refresh_token_value:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(refresh_token_value, SECRET, algorithms=[ALGO])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        user_id = payload.get("user_id")
        email   = payload.get("email")
        role    = payload.get("role", "user")

        # Comprobar que este refresh token no haya sido ya rotado o revocado.
        # Sin esta comprobación, un token robado sigue funcionando aunque el usuario
        # legítimo ya haya rotado su sesión (replay attack).
        old_jti = payload.get("jti")
        old_exp = payload.get("exp")
        if old_jti and _is_revoked(old_jti):
            _clear_auth_cookies(response)
            raise HTTPException(status_code=401, detail="Refresh token revocado")

        # Rotación: revocar el refresh token usado antes de emitir uno nuevo
        if old_jti and old_exp:
            revoke_token(old_jti, datetime.fromtimestamp(old_exp, tz=timezone.utc))

        claims = {"user_id": user_id, "email": email, "role": role}
        _set_auth_cookies(response, create_token(claims), create_refresh_token(claims))
        return {"status": "ok"}
    except JWTError:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    except Exception:
        raise HTTPException(status_code=500, detail="Error interno al procesar el token")

@app.get("/me")
def get_me(user: dict = Depends(verify_token)):
    user_db = user_repo.get_user_by_id(user["user_id"])
    if not user_db:
        # Si el token es válido pero el usuario no existe (ej: DB borrada),
        # lanzamos 401 para que el frontend limpie la sesión.
        raise HTTPException(status_code=401, detail="User session expired or not found")
        
    response_data = {
        "user_id": user["user_id"],
        "email": user["email"],
        # Role is read from the DB (not the JWT) so a role change in the DB takes effect
        # on the next /me call without waiting for token expiry.
        "role": user_db.get("role", "user"),
        "plan": user_db.get("plan", "free"),
        "balance": user_db.get("balance", 0.0),
        "has_payment_method": bool(user_db.get("has_payment_method", 0)),
        "autoscale_enabled": bool(user_db.get("autoscale_enabled", 1)),
        "email_verified": bool(user_db.get("email_verified", 1)),
        "status": "authenticated",
        "is_support_session": user.get("is_support_session", False),
        # Profile fields
        "first_name": user_db.get("first_name"),
        "last_name": user_db.get("last_name"),
        "phone": user_db.get("phone"),
        "timezone": user_db.get("timezone"),
        "company": user_db.get("company"),
        "avatar_url": user_db.get("avatar_url"),
        "notification_prefs": user_db.get("notification_prefs"),
        # Billing fields (Lemon Squeezy)
        "subscription_status": user_db.get("subscription_status", "none"),
        "current_period_end": user_db.get("current_period_end"),
        "plan_started_at": user_db.get("plan_started_at"),
        "billing_interval": user_db.get("billing_interval", "yearly"),
        "ls_customer_portal_url": user_db.get("ls_customer_portal_url"),
    }
    # Expose support metadata so the frontend can render the SupportBanner
    if user.get("is_support_session"):
        from datetime import datetime as _dt, timezone as _tz
        exp = user.get("exp")
        response_data["admin_email"]       = user.get("admin_email")
        response_data["support_expires_at"] = (
            _dt.fromtimestamp(exp, tz=_tz.utc).isoformat() if exp else None
        )
    return response_data

@app.get("/me/support-history")
def get_support_history(user: dict = Depends(verify_token)):
    """Client can see when support accessed their account — full transparency."""
    from app.infra.audit.support_repository import SupportSessionRepository
    repo = SupportSessionRepository()
    return repo.get_sessions_for_user(user["user_id"])


# --- NUEVAS RUTAS DE PRODUCTO ---

class UserConfigRequest(BaseModel):
    autoscale_enabled: Optional[bool] = None
    has_payment_method: Optional[bool] = None

@app.post("/user/config")
def update_user_config(config: UserConfigRequest, user=Depends(verify_token)):
    user_db = user_repo.get_user_by_id(user["user_id"])
    if not user_db:
        raise HTTPException(status_code=404, detail="User not found")
        
    try:
        if config.autoscale_enabled is not None:
            # 🛑 RESTRICCIÓN: Solo planes de pago pueden activar autoscale
            if config.autoscale_enabled and user_db.get("plan", "free") == "free":
                raise HTTPException(
                    status_code=403, 
                    detail="Autoscaling solo disponible en planes pagos. Por favor, actualiza tu plan para activar esta función."
                )
            user_repo.update_autoscale(user["user_id"], config.autoscale_enabled)
            
        if config.has_payment_method is not None:
            user_repo.update_payment_method(user["user_id"], config.has_payment_method)
            
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ProfileRequest(BaseModel):
    first_name: Optional[str] = None
    last_name:  Optional[str] = None
    phone:      Optional[str] = None
    timezone:   Optional[str] = None
    company:    Optional[str] = None

@app.patch("/user/profile")
def update_profile(body: ProfileRequest, user=Depends(verify_token)):
    user_repo.update_profile(
        user["user_id"],
        first_name=(body.first_name or "").strip(),
        last_name=(body.last_name or "").strip(),
        phone=(body.phone or "").strip(),
        timezone=body.timezone,
        company=(body.company or "").strip() or None,
    )
    return {"status": "ok"}


class NotificationPrefsRequest(BaseModel):
    prefs: dict

@app.post("/user/notifications")
def update_notifications(body: NotificationPrefsRequest, user=Depends(verify_token)):
    user_repo.update_notification_prefs(user["user_id"], body.prefs)
    return {"status": "ok"}


_AVATARS_DIR = os.getenv("AVATARS_DIR", "/app/data/avatars")
_ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2 MB

@app.post("/user/avatar")
async def upload_avatar(file: UploadFile, user=Depends(verify_token)):
    import os, pathlib

    if file.content_type not in _ALLOWED_AVATAR_TYPES:
        raise HTTPException(status_code=400, detail="Formato no permitido. Usa JPG, PNG o WebP.")

    data = await file.read((_MAX_AVATAR_BYTES + 1))
    if len(data) > _MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="Imagen demasiado grande. Máximo 2 MB.")

    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[file.content_type]
    pathlib.Path(_AVATARS_DIR).mkdir(parents=True, exist_ok=True)
    dest = f"{_AVATARS_DIR}/{user['user_id']}.{ext}"
    # Remove any old avatar files for this user (different extension)
    for old_ext in ("jpg", "png", "webp"):
        old = f"{_AVATARS_DIR}/{user['user_id']}.{old_ext}"
        if old != dest and os.path.exists(old):
            os.unlink(old)
    with open(dest, "wb") as f:
        f.write(data)

    url = f"/user/avatar-image/{user['user_id']}.{ext}"
    user_repo.update_avatar_url(user["user_id"], url)
    return {"url": url}


@app.get("/user/avatar-image/{filename}")
def get_avatar(filename: str):
    from fastapi.responses import FileResponse
    import os, re
    if not re.fullmatch(r'\d+\.(jpg|png|webp)', filename):
        raise HTTPException(status_code=404)
    path = f"{_AVATARS_DIR}/{filename}"
    if not os.path.exists(path):
        raise HTTPException(status_code=404)
    return FileResponse(path)


from pydantic import field_validator

class TopupRequest(BaseModel):
    amount: float
    idempotency_key: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v):
        if v <= 0 or v > 1000:
            raise ValueError("Monto inválido")
        return v

@app.post("/user/topup")
def topup(data: TopupRequest, user=Depends(require_not_support)):
    from app.infra.db import get_connection, release_connection
    from datetime import datetime, timezone

    try:
        # Idempotency check — same key = same operation already processed
        if data.idempotency_key:
            conn = get_connection()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT amount FROM topup_idempotency WHERE idempotency_key = %s AND user_id = %s",
                    (data.idempotency_key, user["user_id"]),
                )
                existing = cur.fetchone()
            finally:
                release_connection(conn)

            if existing:
                user_db = user_repo.get_user_by_id(user["user_id"])
                return {"balance": user_db["balance"], "idempotent": True}

        user_repo.update_balance(user["user_id"], data.amount)

        # Record idempotency key after a successful credit
        if data.idempotency_key:
            conn = get_connection()
            try:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO topup_idempotency (idempotency_key, user_id, amount, created_at) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (idempotency_key) DO NOTHING",
                    (data.idempotency_key, user["user_id"], data.amount,
                     datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
            finally:
                release_connection(conn)

        user_db = user_repo.get_user_by_id(user["user_id"])
        if not user_db:
            raise HTTPException(status_code=404, detail="User not found")
        return {"balance": user_db["balance"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/advisory")
def get_advisory_mock(user=Depends(verify_token)):
    # Mock de eventos para el dashboard
    return [
        {"message": "Aumento de CPU detectado en 'miapp'", "level": "warning", "time": "Justo ahora"},
        {"message": "Certificado SSL renovado automáticamente", "level": "success", "time": "Hace 2h"},
        {"message": "Intento de intrusión bloqueado por IA Guard", "level": "security", "time": "Hace 5h"}
    ]

# ---------------------------------------------------------------------------
# Body size guard — rejects oversized JSON bodies before they reach handlers.
# Multipart uploads (file imports) are exempt; they enforce their own limits.
# ---------------------------------------------------------------------------
from starlette.middleware.base import BaseHTTPMiddleware as _BaseHTTPMiddleware
from fastapi.responses import JSONResponse as _JSONResponse

_MAX_JSON_BODY = 1 * 1024 * 1024  # 1 MB for JSON endpoints

class _BodySizeMiddleware(_BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        ct = request.headers.get("content-type", "")
        # skip multipart (file uploads enforce their own MAX_UPLOAD_BYTES limit)
        if "multipart/form-data" not in ct:
            cl = request.headers.get("content-length")
            if cl and int(cl) > _MAX_JSON_BODY:
                return _JSONResponse(
                    status_code=413,
                    content={"detail": f"Request body exceeds limit ({_MAX_JSON_BODY // 1024} KB)"},
                )
        return await call_next(request)

# ---------------------------------------------------------------------------
# HTTP metrics middleware — records latency + status for every request
# ---------------------------------------------------------------------------
from app.observability.metrics import HTTP_REQUEST_LATENCY, HTTP_REQUESTS_TOTAL, HTTP_REQUESTS_IN_FLIGHT

class _MetricsMiddleware(_BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = _time_module.perf_counter()
        response = await call_next(request)
        elapsed = _time_module.perf_counter() - start

        # Normalize path: replace path params with placeholders to avoid cardinality explosion
        # e.g. /hostings/42/restart → /hostings/{id}/restart
        path = request.url.path
        for seg in path.split("/"):
            if seg.isdigit():
                path = path.replace(seg, "{id}", 1)

        method = request.method
        status_code = str(response.status_code)

        HTTP_REQUEST_LATENCY.labels(method=method, path=path, status_code=status_code).observe(elapsed)
        HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status_code=status_code).inc()
        if response.status_code >= 400:
            HTTP_REQUESTS_IN_FLIGHT.labels(method=method, path=path, status_code=status_code).inc()

        return response

# Middleware de seguridad y trazabilidad
app.add_middleware(_MetricsMiddleware)
app.add_middleware(_BodySizeMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CorrelationMiddleware)

# CORS — solo orígenes reales de producción.
# allow_origin_regex=r".*" fue eliminado: con allow_credentials=True permitía
# que cualquier origen (incluidos dominios comprometidos) enviara cookies de sesión.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://hostingguard.lat",
        "https://www.hostingguard.lat",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-Correlation-ID"],
)

# Rate Limiting
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Pixel CORS — outermost layer, handles /pixel/event and /pixel.js from any origin.
#
# Rule: origins already covered by the credentialed CORSMiddleware (hostingguard.lat,
# www.hostingguard.lat) are passed through untouched — the inner CORSMiddleware returns
# the specific origin, which is required when credentials mode is 'include'.
# All other origins (*.hostingguard.lat subdomains, external sites) get Access-Control-
# Allow-Origin: * because the pixel is a public, unauthenticated endpoint.
_PIXEL_CORS_PATHS = {"/pixel/event", "/pixel.js"}
_CREDENTIALED_ORIGINS = {b"https://hostingguard.lat", b"https://www.hostingguard.lat"}

class _PixelCORSMiddleware:
    def __init__(self, app_):
        self.app = app_

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path", "") not in _PIXEL_CORS_PATHS:
            await self.app(scope, receive, send)
            return

        # Extract Origin header
        origin = b""
        for k, v in scope.get("headers", []):
            if k.lower() == b"origin":
                origin = v
                break

        # Dashboard origins already handled by inner CORSMiddleware with credentials
        if origin in _CREDENTIALED_ORIGINS:
            await self.app(scope, receive, send)
            return

        # External / subdomain origin → wildcard CORS, no credentials
        if scope.get("method") == "OPTIONS":
            await send({
                "type": "http.response.start",
                "status": 204,
                "headers": [
                    (b"access-control-allow-origin",  b"*"),
                    (b"access-control-allow-methods", b"POST, GET, OPTIONS"),
                    (b"access-control-allow-headers", b"Content-Type"),
                    (b"access-control-max-age",       b"86400"),
                    (b"content-length",               b"0"),
                ],
            })
            await send({"type": "http.response.body", "body": b""})
            return

        async def _send_with_acao(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", [])
                           if k.lower() != b"access-control-allow-origin"]
                headers.append((b"access-control-allow-origin", b"*"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, _send_with_acao)

app.add_middleware(_PixelCORSMiddleware)


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches unhandled exceptions inside FastAPI's ExceptionMiddleware layer,
    which sits *inside* CORSMiddleware — so CORS headers are always present,
    even on 500 responses. Without this, ServerErrorMiddleware (outer layer)
    would return 500 before CORS headers are added.
    """
    logger.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Infraestructura
audit_repo = AuditRepository()
human_repo = HumanActionRepository()
execution_repo = ExecutionRepository()
tenant_config_repo = TenantConfigRepository()

from app.core.rag.documents import load_tenant_documents
from app.api.routes.hosting import router as hosting_router
from app.api.routes.admin import router as admin_router

# Orquestador con RAG por Tenant y LLM dinámico (env var)
ai_orchestrator = AIOrchestrator(
    knowledge_provider=TenantInMemoryKnowledgeProvider(load_tenant_documents())
)
from app.core.registry import registry
registry.orchestrator = ai_orchestrator

# Motor de ejecución
execution_engine = ExecutionEngine()
app.state.execution_engine = execution_engine

# Routers
app.include_router(hosting_router)
app.include_router(admin_router)

# ── Support Chat (aditivo) ────────────────────────────────────────────────
from app.api.routes.support_chat import router as support_chat_router
from app.api.websocket.support_ws import support_ws_handler

app.include_router(support_chat_router)
app.add_api_websocket_route("/ws/support/{ticket_id}", support_ws_handler)


# ── Support session cookie management ────────────────────────────────────────

class SupportTokenRequest(BaseModel):
    token: str

@app.post("/support/activate")
def activate_support_session(body: SupportTokenRequest, response: Response):
    """
    Sets the support_token cookie so verify_token picks it up automatically.
    Called by the frontend after the admin receives the token from /admin/impersonate/{id}.
    """
    from jose import jwt as _jwt, JWTError
    try:
        payload = _jwt.decode(body.token, SECRET, algorithms=[ALGO])
    except JWTError:
        raise HTTPException(status_code=400, detail="Token de soporte inválido.")
    if payload.get("mode") != "support":
        raise HTTPException(status_code=400, detail="No es un token de soporte.")

    from app.api.config import APP_ENV
    secure = APP_ENV == "production"
    response.set_cookie(
        key="support_token",
        value=body.token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=15 * 60,   # 15 minutos
        path="/",
    )
    return {
        "ok": True,
        "target_email": payload.get("email"),
        "admin_email":  payload.get("admin_email"),
        "expires_at":   payload.get("exp"),
    }


@app.post("/support/deactivate")
def deactivate_support_session(response: Response):
    """Clears the support_token cookie (admin exits support mode)."""
    response.delete_cookie("support_token", path="/")
    return {"ok": True}


@app.post("/decision", response_model=DecisionResponse)
@limiter.limit("30/minute")
async def make_decision(
    request: Request,
    payload: DecisionRequest,
    tenant: Tenant = Depends(resolve_tenant),
):
    start_time = time.time()

    decision = run_decision_pipeline(
        hosting_type=payload.hosting_type,
        project_type=payload.project_type,
        symptoms=payload.symptoms,
        recent_changes=payload.recent_changes,
        estimated_impact=payload.estimated_impact,
    )

    # Advisory base
    advisory = generate_advisory(decision)

    # Enriquecimiento opcional (Feature Flag)
    if ENABLE_AI_ADVISORY:
        advisory = await ai_orchestrator.enrich(decision=decision, tenant=tenant)

    # 📊 MÉTRICAS DE NEGOCIO
    DECISIONS_TOTAL.labels(
        tenant_id=tenant.tenant_id,
        project_type=payload.project_type,
    ).inc()

    DECISIONS_BY_STATUS.labels(
        tenant_id=tenant.tenant_id,
        overall_status=decision["overall_status"],
    ).inc()

    DECISION_LATENCY.observe(time.time() - start_time)

    # 🔒 AUDITORÍA (append-only)
    try:
        audit_repo.save_decision_event(
            tenant_id=tenant.tenant_id,
            decision=decision,
            advisory=advisory,
        )
    except Exception as e:
        logger.error(f"Error persisting audit event: {e}")

    # Auditoría de seguridad por tenant (log estructurado)
    from app.api.correlation import request_id_var
    logger.info(
        json.dumps(
            {
                "event": "api_decision_processed",
                "request_id": request_id_var.get(),
                "tenant_id": tenant.tenant_id,
                "ip": request.client.host if request.client else "unknown",
                "decision_id": decision["decision_id"],
                "status": decision["overall_status"],
                "human_required": advisory["requires_human_attention"],
                "latency_ms": round((time.time() - start_time) * 1000),
            }
        )
    )

    return {
        **decision,
        "tenant_id": tenant.tenant_id,
        "advisory": advisory,
    }


@app.post("/decision/action")
def human_decision_action(
    action: HumanActionRequest,
    tenant: Tenant = Depends(resolve_tenant),
):
    event = human_repo.save_action(
        tenant_id=tenant.tenant_id,
        decision_id=action.decision_id,
        action_type=action.action_type,
        actor="human",  # luego usuario real
        reason=action.reason,
    )

    # 📊 MÉTRICAS DE INTERACCIÓN HUMANA
    HUMAN_ACTIONS_TOTAL.labels(
        tenant_id=tenant.tenant_id,
        action_type=action.action_type,
    ).inc()

    return {
        "status": "recorded",
        "action_event_id": event.action_event_id,
    }


@app.post("/decision/execute")
def execute_action(
    decision_id: str,
    action: dict,
    tenant: Tenant = Depends(resolve_tenant),
):
    """
    Ejecuta una acción técnica aprobada.
    Protegido por feature flag y validación de aprobación humana.
    """
    if not ENABLE_ACTION_EXECUTION:
        return JSONResponse(
            status_code=403,
            content={
                "status": "DISABLED",
                "detail": "Action execution is not enabled for this environment.",
            },
        )

    # 🔒 POLÍTICA DE SEGURIDAD v1:
    # Solo ejecutamos si la acción está marcada como que requiere aprobación
    # (lo cual implica que el humano ya la vio y dio el OK en /decision/action)
    # En v2 verificaremos el estado de la auditoría humana antes de ejecutar.
    if not action.get("requires_human_approval"):
        return JSONResponse(
            status_code=400,
            content={
                "status": "REJECTED",
                "detail": "Only previously approved human actions can be executed.",
            },
        )

    result = execution_engine.run(action)

    # 📒 Auditar resultado de ejecución
    try:
        execution_repo.save_execution_event(
            tenant_id=tenant.tenant_id,
            decision_id=decision_id,
            action_type=action.get("action_type", "unknown"),
            status=result,
        )
    except Exception as e:
        logger.error(f"Error persisting execution audit event: {e}")

    return {"status": result}


@app.post("/tenant/config")
def update_tenant_config(
    tenant_id: str,
    kind: str,
    content: dict,
    user=Depends(require_role("admin")),
):
    """
    Crea una nueva versión de reglas o prompts para un tenant.
    Solo accesible para usuarios con rol 'admin'.
    """
    cfg = tenant_config_repo.create_new_version(
        tenant_id=tenant_id,
        kind=kind,
        content=content,
    )

    return {
        "status": "ok",
        "config_id": cfg.config_id,
        "version": cfg.version,
    }


@app.get("/metrics")
def metrics():
    """
    Expone métricas para Prometheus. Accesible internamente sin token.
    """
    return PlainTextResponse(generate_latest())


@app.get("/health")
def health():
    return {"status": "ok"}
