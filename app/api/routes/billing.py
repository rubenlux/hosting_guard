"""Billing routes — MercadoPago.

Flujo de pago:
  1.  POST /billing/checkout      → genera preferencia en MP y retorna payment_url
  2.  Usuario completa el pago en MercadoPago
  3.  MP envía webhook a POST /billing/webhooks/mercadopago
  4.  El sistema valida firma, consulta el pago y activa el plan del usuario

El proveedor de pagos se inyecta mediante la factory — el resto de la lógica
de negocio nunca importa MercadoPago directamente.
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.security import verify_token
from app.infra.audit.user_repository import UserRepository
from app.services.billing import get_payment_provider

router = APIRouter(prefix="/billing", tags=["billing"])
_user_repo = UserRepository()
logger = logging.getLogger(__name__)


# ── Helpers de auditoría ──────────────────────────────────────────────────────

def _log_billing(
    user_id: int,
    event_type: str,
    title: str,
    plan: str | None = None,
    severity: str = "info",
) -> None:
    try:
        from app.services.activity_service import log_event
        log_event(
            user_id=user_id,
            event_type=event_type,
            category="billing",
            severity=severity,
            title=title,
            source="webhook",
            metadata={"plan": plan} if plan else {},
        )
    except Exception:
        pass


# ── Checkout ──────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str  # personal | negocio | agencia | agencia_pro | enterprise_annual | enterprise_monthly


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    current_user: dict = Depends(verify_token),
):
    """Genera un link de pago en MercadoPago para el plan seleccionado.

    Retorna: ``{ "url": "https://www.mercadopago.com/..." }``
    """
    provider = get_payment_provider()

    if not provider.is_configured():
        raise HTTPException(status_code=503, detail="Billing no configurado en el servidor")

    try:
        result = await provider.create_payment_link(plan=body.plan, user=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        logger.error("MP checkout error: %s", exc)
        raise HTTPException(status_code=502, detail="Error al crear el checkout en MercadoPago")

    try:
        from app.services.activity_service import log_event
        log_event(
            user_id=current_user["user_id"],
            event_type="checkout_started",
            category="billing",
            severity="info",
            title=f"Checkout iniciado: plan {body.plan}",
            source="dashboard",
            metadata={"plan": body.plan, "preference_id": result.preference_id},
        )
    except Exception:
        pass

    return {"url": result.payment_url}


# ── Webhook background processor ──────────────────────────────────────────────

async def _process_webhook(payload: dict) -> None:
    """Resuelve el pago vía el proveedor activo y actualiza el estado del usuario."""
    provider = get_payment_provider()

    try:
        event = await provider.process_webhook_payload(payload)
    except Exception as exc:
        logger.error("Webhook: error procesando pago: %s", exc)
        return

    if not event.valid:
        return

    event_type = event.event_type
    uid = event.user_id
    plan = event.plan

    # Si no tenemos user_id en external_reference, intentar por email/customer_id
    if not uid and event.provider_customer_id:
        user = _user_repo.get_user_by_payment_customer_id(event.provider_customer_id)
        if user:
            uid = user["user_id"]

    if not uid:
        logger.error("Webhook %s: user_id no resuelto — payload=%s", event_type, str(payload)[:200])
        return

    base: dict = {
        "mp_customer_id":      event.provider_customer_id or "",
        "mp_payment_id":       event.provider_payment_id or "",
        "mp_preference_id":    event.provider_preference_id or "",
        "mp_subscription_id":  event.provider_subscription_id or "",
        "current_period_end":  event.period_end,
    }

    if event_type == "payment_approved":
        if not plan:
            logger.error("Webhook payment_approved: plan no resuelto para user=%s", uid)
            return

        # Calcular interval de facturación
        billing_interval = "monthly" if plan == "enterprise_monthly" else "yearly"

        _user_repo.update_billing_subscription(
            uid,
            plan=plan,
            plan_started_at=datetime.now(timezone.utc).isoformat(),
            current_period_start=datetime.now(timezone.utc).isoformat(),
            billing_interval=billing_interval,
            subscription_status="active",
            **base,
        )
        logger.info("User %s → plan=%s payment=%s", uid, plan, event.provider_payment_id)
        _log_billing(uid, "subscription_created", f"Plan activado: {plan}", plan)

        # Notificar al usuario
        try:
            from app.services.notification_service import notify as _notify
            _notify(
                user_id=uid,
                title="¡Tu plan está activo!",
                message=f"Tu pago fue confirmado y el plan {plan} ya está activado en tu cuenta.",
                category="billing",
                severity="info",
                action_url="https://hostingguard.lat/dashboard",
            )
        except Exception:
            pass

    elif event_type == "payment_failed":
        _user_repo.update_billing_subscription(
            uid,
            subscription_status="past_due",
            mp_payment_id=event.provider_payment_id or "",
            mp_customer_id=event.provider_customer_id or "",
        )
        logger.warning("User %s payment failed — past_due", uid)
        _log_billing(uid, "payment_failed", "Pago fallido — estado: past_due", severity="critical")

        try:
            from app.services.notification_service import notify as _notify
            _notify(
                user_id=uid,
                title="Problema con tu pago",
                message="No pudimos procesar el pago. Revisá tu método de pago para evitar la suspensión del servicio.",
                category="billing",
                severity="critical",
                action_url="https://hostingguard.lat/dashboard?tab=billing",
            )
        except Exception:
            pass

    elif event_type == "payment_pending":
        _user_repo.update_billing_subscription(
            uid,
            subscription_status="pending",
            mp_payment_id=event.provider_payment_id or "",
        )
        logger.info("User %s payment pending", uid)
        _log_billing(uid, "payment_pending", "Pago pendiente de confirmación")

    else:
        logger.debug("Webhook event_type=%s ignorado", event_type)


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@router.post("/webhooks/mercadopago")
async def handle_mercadopago_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Endpoint de notificaciones de MercadoPago.

    - Valida firma HMAC-SHA256 (x-signature header).
    - Aplica idempotencia por payment_id.
    - Delega el procesamiento a un background task.
    """
    body = await request.body()

    # Parsear JSON antes de validar para poder extraer el payment_id del manifest
    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    provider = get_payment_provider()
    headers_lower = {k.lower(): v for k, v in request.headers.items()}
    validation = provider.validate_webhook(body, headers_lower, payload)

    if not validation.valid:
        logger.warning(
            "Webhook MP: firma inválida desde %s",
            request.client.host if request.client else "unknown",
        )
        try:
            from app.services.security_event_service import log_security_event
            log_security_event(
                severity="warning",
                category="webhook",
                event_type="invalid_webhook_signature",
                title="Webhook MercadoPago con firma inválida rechazado",
                ip=request.client.host if request.client else None,
                source="billing",
                metadata={"path": "/billing/webhooks/mercadopago"},
            )
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Idempotencia: payment_id es único por evento en MP
    payment_id = validation.provider_payment_id or ""
    action = payload.get("action", "")
    event_key = f"{action}:{payment_id}" if payment_id else str(payload)[:100]

    if _user_repo.is_webhook_processed(event_key):
        logger.info("Webhook MP ya procesado: %s", event_key[:60])
        return {"ok": True}

    _user_repo.mark_webhook_processed(event_key, action or "payment.notification")
    background_tasks.add_task(_process_webhook, payload)
    return {"ok": True}
