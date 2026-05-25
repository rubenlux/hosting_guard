"""MercadoPagoProvider — implementación concreta del PaymentProvider.

Documentación de la API:
  - Checkout Preferences: https://www.mercadopago.com.ar/developers/es/reference/preferences/
  - Webhooks:             https://www.mercadopago.com.ar/developers/es/docs/notifications/webhooks
  - Pagos:                https://www.mercadopago.com.ar/developers/es/reference/payments/
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import MercadoPagoSettings as _MP
from app.services.billing.interface import (
    CheckoutResult,
    PaymentProvider,
    WebhookValidationResult,
)

logger = logging.getLogger(__name__)

_MP_API_BASE = "https://api.mercadopago.com"

# ── Catálogo de planes ────────────────────────────────────────────────────────
# Precios en USD · facturación anual (o mensual para enterprise_monthly).
# No modifiques aquí los precios — vienen de plan_economics en la DB.
# Estos son fallbacks si la DB no está disponible.

_PLAN_CATALOG: dict[str, dict] = {
    "personal":           {"title": "Plan Personal",           "unit_price": 108.00,  "billing_interval": "yearly"},
    "negocio":            {"title": "Plan Negocio",            "unit_price": 228.00,  "billing_interval": "yearly"},
    "agencia":            {"title": "Plan Agencia",            "unit_price": 468.00,  "billing_interval": "yearly"},
    "agencia_pro":        {"title": "Plan Agencia Pro",        "unit_price": 708.00,  "billing_interval": "yearly"},
    "enterprise_annual":  {"title": "Plan Enterprise Anual",   "unit_price": 1188.00, "billing_interval": "yearly"},
    "enterprise_monthly": {"title": "Plan Enterprise Mensual", "unit_price": 129.00,  "billing_interval": "monthly"},
}

_VALID_PLANS = frozenset(_PLAN_CATALOG)


class MercadoPagoProvider(PaymentProvider):
    """Proveedor de pagos usando la API de MercadoPago."""

    # ── Utilidades internas ───────────────────────────────────────────────────

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {_MP.ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "X-Idempotency-Key": "",  # se sobreescribe por request
        }

    def is_configured(self) -> bool:
        return bool(_MP.ACCESS_TOKEN)

    # ── Checkout ──────────────────────────────────────────────────────────────

    async def create_payment_link(self, plan: str, user: dict) -> CheckoutResult:
        """Crea una preferencia de pago en MP y retorna el init_point."""
        if plan not in _VALID_PLANS:
            valid = ", ".join(sorted(_VALID_PLANS))
            raise ValueError(f"Plan no válido: '{plan}'. Opciones: {valid}")

        if not self.is_configured():
            raise RuntimeError("MercadoPago no está configurado (ACCESS_TOKEN faltante)")

        catalog = _PLAN_CATALOG[plan]
        user_id = str(user["user_id"])
        email = user.get("email", "")

        # external_reference viaja en todas las notificaciones — permite resolver
        # el usuario sin necesidad de custom metadata adicional.
        external_ref = f"user:{user_id}:plan:{plan}"

        # notification_url: MP envía POST aquí tras cada evento de pago.
        notification_url = f"{_MP.WEBHOOK_BASE_URL}/billing/webhooks/mercadopago"

        # Duración de acceso: 1 año para planes anuales, 1 mes para mensual.
        interval = catalog["billing_interval"]
        if interval == "monthly":
            expires_delta = timedelta(days=32)
        else:
            expires_delta = timedelta(days=366)

        period_end = (datetime.now(timezone.utc) + expires_delta).isoformat()

        preference_payload = {
            "items": [
                {
                    "id": f"plan-{plan}",
                    "title": catalog["title"],
                    "quantity": 1,
                    "unit_price": catalog["unit_price"],
                    "currency_id": "USD",
                    "description": f"HostingGuard · {catalog['title']} · facturación {'anual' if interval == 'yearly' else 'mensual'}",
                }
            ],
            "payer": {
                "email": email,
            },
            "back_urls": {
                "success": f"{_MP.FRONTEND_URL}/dashboard?billing=success",
                "failure": f"{_MP.FRONTEND_URL}/dashboard?billing=failure",
                "pending": f"{_MP.FRONTEND_URL}/dashboard?billing=pending",
            },
            "auto_return": "approved",
            "notification_url": notification_url,
            "external_reference": external_ref,
            "metadata": {
                "user_id": user_id,
                "plan": plan,
                "billing_interval": interval,
                "period_end": period_end,
            },
            "statement_descriptor": "HostingGuard",
            "expires": False,
        }

        import uuid
        headers = self._headers()
        headers["X-Idempotency-Key"] = f"{user_id}-{plan}-{uuid.uuid4()}"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{_MP_API_BASE}/checkout/preferences",
                json=preference_payload,
                headers=headers,
            )

        if resp.status_code not in (200, 201):
            logger.error(
                "MP create_preference error %s: %s",
                resp.status_code,
                resp.text[:500],
            )
            raise RuntimeError(
                f"Error al crear preferencia en MercadoPago (HTTP {resp.status_code})"
            )

        data = resp.json()
        preference_id = data.get("id", "")

        # En sandbox usar sandbox_init_point; en producción, init_point.
        if _MP.SANDBOX_MODE:
            payment_url = data.get("sandbox_init_point") or data.get("init_point", "")
        else:
            payment_url = data.get("init_point", "")

        logger.info(
            "MP preference created: id=%s plan=%s user=%s",
            preference_id,
            plan,
            user_id,
        )
        return CheckoutResult(payment_url=payment_url, preference_id=preference_id)

    # ── Webhook ───────────────────────────────────────────────────────────────

    def _verify_signature(
        self,
        body: bytes,
        headers: dict[str, str],
        payload: dict,
    ) -> bool:
        """Verifica la firma HMAC-SHA256 enviada por MercadoPago.

        Formato del header x-signature: ``ts=<timestamp>,v1=<hmac>``
        Manifest: ``id:<payment_id>;request-id:<x-request-id>;ts:<ts>``

        Si WEBHOOK_SECRET no está configurado, se permite en dev (log warning).
        """
        secret = _MP.WEBHOOK_SECRET
        if not secret:
            logger.warning("MP webhook: MERCADOPAGO_WEBHOOK_SECRET no configurado — omitiendo verificación")
            return True

        x_signature = headers.get("x-signature", "")
        x_request_id = headers.get("x-request-id", "")

        if not x_signature:
            logger.warning("MP webhook: header x-signature ausente")
            return False

        # Parsear ts y v1 del header
        parts = dict(p.split("=", 1) for p in x_signature.split(",") if "=" in p)
        ts = parts.get("ts", "")
        v1 = parts.get("v1", "")

        if not ts or not v1:
            logger.warning("MP webhook: x-signature malformado: %s", x_signature[:80])
            return False

        # El data.id del payload es el payment_id en el manifest
        data_id = str(payload.get("data", {}).get("id", ""))
        manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts}"

        expected = hmac.new(
            secret.encode("utf-8"),
            manifest.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, v1)

    async def _fetch_payment(self, payment_id: str) -> dict:
        """Consulta el detalle de un pago a la API de MP."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_MP_API_BASE}/v1/payments/{payment_id}",
                headers=self._headers(),
            )
        if resp.status_code != 200:
            logger.error("MP fetch_payment %s error %s: %s", payment_id, resp.status_code, resp.text[:300])
            return {}
        return resp.json()

    def _parse_external_reference(self, ext_ref: str) -> tuple[int | None, str | None]:
        """Extrae (user_id, plan) de external_reference = 'user:123:plan:negocio'."""
        try:
            parts = ext_ref.split(":")
            user_id = int(parts[1])
            plan = parts[3]
            return user_id, plan
        except (IndexError, ValueError, TypeError):
            return None, None

    def validate_webhook(
        self,
        body: bytes,
        headers: dict[str, str],
        payload: dict,
    ) -> WebhookValidationResult:
        """Valida firma y parsea el evento sin hacer llamadas a la API.

        La resolución completa del pago (fetch_payment) se hace de forma async
        en el background task del endpoint de webhook.
        """
        valid = self._verify_signature(body, headers, payload)
        return WebhookValidationResult(
            valid=valid,
            event_type="unknown",
            user_id=None,
            plan=None,
            provider_payment_id=str(payload.get("data", {}).get("id", "")),
            provider_customer_id=None,
            provider_preference_id=None,
            period_end=None,
            raw_payload=payload,
        )

    async def process_webhook_payload(self, payload: dict) -> WebhookValidationResult:
        """Implementa PaymentProvider.process_webhook_payload.

        Consulta GET /v1/payments/{id} en la API de MP y resuelve el evento.
        """
        action = payload.get("action", "")
        topic = payload.get("type", "")

        payment_id = str(payload.get("data", {}).get("id", ""))

        # Solo procesamos eventos de tipo "payment"
        if topic not in ("payment",) and action not in ("payment.created", "payment.updated"):
            return WebhookValidationResult(
                valid=True,
                event_type="unknown",
                user_id=None,
                plan=None,
                provider_payment_id=payment_id,
                provider_customer_id=None,
                provider_preference_id=None,
                period_end=None,
                raw_payload=payload,
            )

        # Obtener detalle del pago desde la API de MP
        payment = await self._fetch_payment(payment_id)
        if not payment:
            return WebhookValidationResult(
                valid=True,
                event_type="payment_error",
                user_id=None,
                plan=None,
                provider_payment_id=payment_id,
                provider_customer_id=None,
                provider_preference_id=None,
                period_end=None,
                raw_payload=payload,
            )

        status = payment.get("status", "")
        ext_ref = payment.get("external_reference", "")
        preference_id = payment.get("preference_id", "")
        payer_email = payment.get("payer", {}).get("email", "")
        payer_id = str(payment.get("payer", {}).get("id", ""))

        # Resolver user_id y plan desde external_reference
        user_id, plan = self._parse_external_reference(ext_ref)

        # Metadatos del pago para calcular period_end
        metadata = payment.get("metadata") or {}
        period_end = metadata.get("period_end")

        # Si no viene en metadata, calcularlo según plan
        if not period_end and plan:
            catalog = _PLAN_CATALOG.get(plan, {})
            interval = catalog.get("billing_interval", "yearly")
            delta = timedelta(days=32) if interval == "monthly" else timedelta(days=366)
            period_end = (datetime.now(timezone.utc) + delta).isoformat()

        # Mapear status de MP a event_type interno
        if status == "approved":
            event_type = "payment_approved"
        elif status in ("rejected", "cancelled", "refunded", "charged_back"):
            event_type = "payment_failed"
        elif status in ("pending", "in_process", "authorized"):
            event_type = "payment_pending"
        else:
            event_type = "unknown"

        return WebhookValidationResult(
            valid=True,
            event_type=event_type,
            user_id=user_id,
            plan=plan,
            provider_payment_id=payment_id,
            provider_customer_id=payer_id or payer_email,
            provider_preference_id=preference_id,
            period_end=period_end,
            raw_payload=payload,
        )
