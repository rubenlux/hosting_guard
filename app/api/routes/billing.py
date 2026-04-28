import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.security import verify_token
from app.core.config import LemonSqueezySettings as _LS
from app.infra.audit.user_repository import UserRepository
from app.services.notification_service import notify as _notify

router = APIRouter(prefix="/billing", tags=["billing"])
_user_repo = UserRepository()
logger = logging.getLogger(__name__)

_LS_API_BASE = "https://api.lemonsqueezy.com/v1"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _verify_signature(body: bytes, signature: str) -> bool:
    secret = _LS.WEBHOOK_SECRET
    if not secret:
        return True  # Skip in unconfigured local dev
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _ls_headers() -> dict:
    return {
        "Authorization": f"Bearer {_LS.API_KEY}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }


# ── Checkout ──────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str  # personal | negocio | agencia


@router.post("/checkout")
async def create_checkout(body: CheckoutRequest, current_user: dict = Depends(verify_token)):
    variant_map = _LS.variant_map()
    variant_id = variant_map.get(body.plan)

    if not variant_id:
        raise HTTPException(status_code=400, detail=f"Plan no válido: {body.plan}. Opciones: personal, negocio, agencia")
    if not _LS.API_KEY or not _LS.STORE_ID:
        raise HTTPException(status_code=503, detail="Billing no configurado en el servidor")

    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_options": {
                    "embed": False,
                    "media": True,
                    "logo": True,
                    "skip_trial": True,
                },
                "checkout_data": {
                    "email": current_user["email"],
                    "custom": {"user_id": str(current_user["user_id"])},
                },
                "product_options": {
                    "redirect_url": "https://hostingguard.lat/dashboard?billing=success",
                    "receipt_button_text": "Ir al dashboard",
                    "receipt_link_url": "https://hostingguard.lat/dashboard",
                    "receipt_thank_you_note": "Gracias por confiar en HostingGuard. Tu plan ya está activo.",
                },
            },
            "relationships": {
                "store":   {"data": {"type": "stores",   "id": str(_LS.STORE_ID)}},
                "variant": {"data": {"type": "variants", "id": str(variant_id)}},
            },
        }
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{_LS_API_BASE}/checkouts",
            json=payload,
            headers=_ls_headers(),
        )

    if resp.status_code not in (200, 201):
        logger.error("LS checkout error %s: %s", resp.status_code, resp.text[:500])
        raise HTTPException(status_code=502, detail="Error al crear el checkout en Lemon Squeezy")

    url: str = resp.json()["data"]["attributes"]["url"]
    return {"url": url}


# ── Webhook: background processor ─────────────────────────────────────────────

async def _process_webhook(event_name: str, meta: dict, data: dict) -> None:
    attrs = data.get("attributes", {})
    subscription_id = str(data.get("id", ""))

    # Resolve user: custom_data.user_id → ls_customer_id → email
    custom = meta.get("custom_data") or {}
    user: dict | None = None

    raw_uid = custom.get("user_id")
    if raw_uid:
        try:
            user = _user_repo.get_user_by_id(int(raw_uid))
        except (ValueError, TypeError):
            pass

    if not user:
        ls_cid = str(attrs.get("customer_id", ""))
        if ls_cid:
            user = _user_repo.get_user_by_ls_customer_id(ls_cid)

    if not user:
        email = attrs.get("user_email", "")
        if email:
            user = _user_repo.get_user_by_email(email)

    if not user:
        logger.error("Webhook %s: user not found — custom=%s", event_name, custom)
        return

    uid: int = user["user_id"]
    variant_id = str(attrs.get("variant_id", ""))
    ls_cid = str(attrs.get("customer_id", ""))
    status = attrs.get("status", "")
    period_end = attrs.get("renews_at") or attrs.get("ends_at")
    period_start = attrs.get("created_at")
    portal_url = (attrs.get("urls") or {}).get("customer_portal")

    base: dict = {
        "ls_customer_id": ls_cid,
        "ls_subscription_id": subscription_id,
        "ls_variant_id": variant_id,
        "subscription_status": status,
        "current_period_end": period_end,
        "ls_customer_portal_url": portal_url,
    }

    # For events that involve plan assignment, variant_id must map to a known plan.
    # This prevents a misconfigured LS product from silently elevating any plan.
    plan_from_variant: str | None = _LS.plan_from_variant(variant_id) if variant_id else None
    _plan_events = {"subscription_created", "subscription_updated", "subscription_resumed", "order_created"}
    if event_name in _plan_events and not plan_from_variant:
        logger.error(
            "Webhook %s: variant_id=%s is not mapped to any allowed plan — aborting. user=%s",
            event_name, variant_id, uid,
        )
        return

    if event_name in ("subscription_created", "order_created"):
        _user_repo.update_billing_subscription(uid,
            plan=plan_from_variant,
            plan_started_at=datetime.now(timezone.utc).isoformat(),
            current_period_start=period_start,
            billing_interval="yearly",
            subscription_status="active",
            **base)
        logger.info("User %s → plan=%s sub=%s", uid, plan_from_variant, subscription_id)

    elif event_name in ("subscription_updated", "subscription_resumed"):
        _user_repo.update_billing_subscription(uid, plan=plan_from_variant, **base)

    elif event_name == "subscription_cancelled":
        # Service remains active until current_period_end — do NOT downgrade plan yet
        _user_repo.update_billing_subscription(uid,
            subscription_status="cancelled",
            ls_customer_id=ls_cid,
            ls_subscription_id=subscription_id,
            current_period_end=period_end,
            ls_customer_portal_url=portal_url)
        logger.info("User %s cancelled; active until %s", uid, period_end)

    elif event_name == "subscription_expired":
        # Period truly ended — downgrade to free
        _user_repo.update_billing_subscription(uid, plan="free",
            subscription_status="expired", **base)
        logger.info("User %s subscription expired → free", uid)

    elif event_name == "subscription_payment_failed":
        _user_repo.update_billing_subscription(uid, subscription_status="past_due", **base)
        _notify(
            user_id=uid,
            title="Problema con tu pago",
            message="No pudimos procesar el pago de tu suscripción. Actualiza tu método de pago para evitar la suspensión del servicio.",
            category="billing",
            severity="critical",
            action_url=portal_url or "https://hostingguard.lat/dashboard",
            _user_email=user.get("email"),
        )
        logger.warning("User %s payment failed — past_due", uid)

    elif event_name == "subscription_payment_success":
        _user_repo.update_billing_subscription(uid, subscription_status="active", **base)
        logger.info("User %s payment success, renewed until %s", uid, period_end)

    else:
        logger.debug("Webhook %s ignored (unhandled)", event_name)


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@router.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    signature = request.headers.get("X-Signature", "")

    if not _verify_signature(body, signature):
        logger.warning("Webhook: invalid signature from %s", request.client)
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    meta = payload.get("meta", {})
    event_name = meta.get("event_name", "")
    data = payload.get("data", {})

    # Idempotency: prefer LS webhook_id (unique UUID per delivery), then signature,
    # then a composite fallback. This handles LS retry storms correctly.
    event_key = (
        meta.get("webhook_id")
        or signature
        or f"{event_name}:{data.get('id', '')}"
    )

    if _user_repo.is_webhook_processed(event_key):
        logger.info("Webhook already processed: %s", event_key[:40])
        return {"ok": True}

    _user_repo.mark_webhook_processed(event_key, event_name)
    background_tasks.add_task(_process_webhook, event_name, meta, data)
    return {"ok": True}
