"""MercadoPagoProvider — Checkout Pro + Suscripciones.

Flujos según tipo de plan:
  - Planes ANUALES:   Checkout Pro (POST /checkout/preferences) → pago único
  - Planes MENSUALES: Suscripciones (POST /preapproval) → cobro recurrente automático

Refs oficiales:
  Preferences API:  https://www.mercadopago.com.ar/developers/es/reference/preferences/_checkout_preferences/post
  Preapproval API:  https://www.mercadopago.com.ar/developers/es/reference/subscriptions/_preapproval/post
  Webhooks:         https://www.mercadopago.com.ar/developers/es/docs/your-integrations/notifications/webhooks
  Pagos GET:        https://www.mercadopago.com.ar/developers/es/reference/payments/_payments_id/get

Firma HMAC-SHA256 (doc oficial):
  Header:   x-signature: ts=<timestamp>,v1=<hash>
  Manifest: id:<data.id>;request-id:<x-request-id>;ts:<ts>;   ← trailing semicolon obligatorio
  Clave:    MERCADOPAGO_WEBHOOK_SECRET
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
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
#
# Planes anuales  → Checkout Pro (pago único, unit_price = monto anual total)
# Planes mensuales → Preapproval API (cobro recurrente, unit_price = monto mensual)

_PLAN_CATALOG: dict[str, dict] = {
    # Anuales
    "personal":             {"title": "Plan Personal",             "unit_price": 108.00,  "billing_interval": "yearly"},
    "negocio":              {"title": "Plan Negocio",              "unit_price": 228.00,  "billing_interval": "yearly"},
    "agencia":              {"title": "Plan Agencia",              "unit_price": 468.00,  "billing_interval": "yearly"},
    "agencia_pro":          {"title": "Plan Agencia Pro",          "unit_price": 708.00,  "billing_interval": "yearly"},
    "enterprise_annual":    {"title": "Plan Enterprise Anual",     "unit_price": 1188.00, "billing_interval": "yearly"},
    # Mensuales — precios ligeramente más altos que la tarifa anual equivalente
    "personal_monthly":     {"title": "Plan Personal Mensual",     "unit_price": 15.00,   "billing_interval": "monthly"},
    "negocio_monthly":      {"title": "Plan Negocio Mensual",      "unit_price": 25.00,   "billing_interval": "monthly"},
    "agencia_monthly":      {"title": "Plan Agencia Mensual",      "unit_price": 50.00,   "billing_interval": "monthly"},
    "agencia_pro_monthly":  {"title": "Plan Agencia Pro Mensual",  "unit_price": 75.00,   "billing_interval": "monthly"},
    "enterprise_monthly":   {"title": "Plan Enterprise Mensual",   "unit_price": 129.00,  "billing_interval": "monthly"},
}

_VALID_PLANS   = frozenset(_PLAN_CATALOG)
_MONTHLY_PLANS = frozenset(k for k, v in _PLAN_CATALOG.items() if v["billing_interval"] == "monthly")


def _unknown_result(event_id: str, payload: dict) -> WebhookValidationResult:
    return WebhookValidationResult(
        valid=True,
        event_type="unknown",
        user_id=None,
        plan=None,
        provider_payment_id=event_id,
        provider_customer_id=None,
        provider_preference_id=None,
        provider_subscription_id=None,
        period_end=None,
        raw_payload=payload,
    )


class MercadoPagoProvider(PaymentProvider):
    """Proveedor de pagos MercadoPago — Checkout Pro + Suscripciones."""

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _auth_headers(self, idempotency_key: str = "") -> dict:
        h = {
            "Authorization": f"Bearer {_MP.ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            h["X-Idempotency-Key"] = idempotency_key
        return h

    def is_configured(self) -> bool:
        return bool(_MP.ACCESS_TOKEN)

    def _pick_url(self, data: dict) -> str:
        """Selecciona init_point o sandbox_init_point según el modo configurado."""
        if _MP.SANDBOX_MODE:
            return data.get("sandbox_init_point") or data.get("init_point", "")
        return data.get("init_point", "")

    # ── Checkout Pro — pago único (planes anuales) ────────────────────────────

    async def _create_preference(self, plan: str, user: dict) -> CheckoutResult:
        """POST /checkout/preferences — genera una preferencia de pago único.

        Ref: https://www.mercadopago.com.ar/developers/es/reference/preferences/_checkout_preferences/post
        """
        catalog      = _PLAN_CATALOG[plan]
        user_id      = str(user["user_id"])
        email        = user.get("email", "")
        external_ref = f"user:{user_id}:plan:{plan}"
        period_end   = (datetime.now(timezone.utc) + timedelta(days=366)).isoformat()

        payload = {
            "items": [{
                "id":          f"hostingguard-{plan}",
                "title":       catalog["title"],
                "description": f"HostingGuard · {catalog['title']} · facturación anual",
                "quantity":    1,
                "unit_price":  catalog["unit_price"],
                "currency_id": "USD",
            }],
            "payer": {"email": email},
            "back_urls": {
                "success": f"{_MP.FRONTEND_URL}/dashboard?billing=success",
                "failure": f"{_MP.FRONTEND_URL}/dashboard?billing=failure",
                "pending": f"{_MP.FRONTEND_URL}/dashboard?billing=pending",
            },
            "auto_return":        "approved",
            "notification_url":   f"{_MP.WEBHOOK_BASE_URL}/billing/webhooks/mercadopago",
            "external_reference": external_ref,
            "metadata": {
                "user_id":          user_id,
                "plan":             plan,
                "billing_interval": "yearly",
                "period_end":       period_end,
            },
            "statement_descriptor": "HOSTINGGUARD",
        }

        idempotency_key = f"{user_id}-{plan}-{uuid.uuid4()}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{_MP_API_BASE}/checkout/preferences",
                json=payload,
                headers=self._auth_headers(idempotency_key),
            )

        if resp.status_code not in (200, 201):
            logger.error("MP create_preference HTTP %s — user=%s plan=%s body=%s",
                         resp.status_code, user_id, plan, resp.text[:300])
            raise RuntimeError(f"Error al crear preferencia en MercadoPago (HTTP {resp.status_code})")

        data          = resp.json()
        preference_id = data.get("id", "")
        payment_url   = self._pick_url(data)

        logger.info("MP preference created — id=%s plan=%s user=%s url=%s",
                    preference_id, plan, user_id, payment_url[:60])
        return CheckoutResult(payment_url=payment_url, preference_id=preference_id)

    # ── Preapproval — suscripción recurrente (planes mensuales) ───────────────

    async def _create_subscription(self, plan: str, user: dict) -> CheckoutResult:
        """POST /preapproval — crea una suscripción con cobro mensual automático.

        MP guarda el método de pago del usuario y lo debita cada mes hasta que
        la suscripción sea cancelada o pausada.

        Ref: https://www.mercadopago.com.ar/developers/es/reference/subscriptions/_preapproval/post

        Campos clave:
          reason           — descripción visible al usuario en el resumen de MP
          external_reference — viaja en todos los webhooks; formato user:{id}:plan:{slug}
          payer_email      — pre-carga el email del comprador
          auto_recurring   — configura frecuencia y monto del cobro recurrente
          back_url         — redirección después de autorizar la suscripción
          notification_url — endpoint que recibe los webhooks de cada cobro
          status: "pending"— el usuario debe autorizar el débito automático
        """
        catalog      = _PLAN_CATALOG[plan]
        user_id      = str(user["user_id"])
        email        = user.get("email", "")
        external_ref = f"user:{user_id}:plan:{plan}"

        payload = {
            "reason":             f"HostingGuard · {catalog['title']}",
            "external_reference": external_ref,
            "payer_email":        email,
            "auto_recurring": {
                "frequency":          1,
                "frequency_type":     "months",
                "transaction_amount": catalog["unit_price"],
                "currency_id":        "USD",
            },
            "back_url":         f"{_MP.FRONTEND_URL}/dashboard?billing=success",
            "notification_url": f"{_MP.WEBHOOK_BASE_URL}/billing/webhooks/mercadopago",
            "status":           "pending",
        }

        idempotency_key = f"sub-{user_id}-{plan}-{uuid.uuid4()}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{_MP_API_BASE}/preapproval",
                json=payload,
                headers=self._auth_headers(idempotency_key),
            )

        if resp.status_code not in (200, 201):
            logger.error("MP create_subscription HTTP %s — user=%s plan=%s body=%s",
                         resp.status_code, user_id, plan, resp.text[:300])
            raise RuntimeError(f"Error al crear suscripción en MercadoPago (HTTP {resp.status_code})")

        data            = resp.json()
        subscription_id = data.get("id", "")
        payment_url     = self._pick_url(data)

        logger.info("MP subscription created — id=%s plan=%s user=%s url=%s",
                    subscription_id, plan, user_id, payment_url[:60])
        return CheckoutResult(payment_url=payment_url, preference_id=subscription_id)

    # ── Router público ────────────────────────────────────────────────────────

    async def create_payment_link(self, plan: str, user: dict) -> CheckoutResult:
        """Genera el link de pago adecuado según el tipo de plan.

        - plan en _MONTHLY_PLANS → suscripción recurrente (preapproval)
        - plan anual             → pago único (preference)
        """
        if plan not in _VALID_PLANS:
            valid = ", ".join(sorted(_VALID_PLANS))
            raise ValueError(f"Plan no válido: '{plan}'. Opciones: {valid}")
        if not self.is_configured():
            raise RuntimeError("MercadoPago no configurado — falta MERCADOPAGO_ACCESS_TOKEN")

        if plan in _MONTHLY_PLANS:
            return await self._create_subscription(plan, user)
        return await self._create_preference(plan, user)

    # ── Webhook — validación de firma (síncrono, sin I/O) ────────────────────

    def _verify_signature(self, headers: dict[str, str], payload: dict) -> bool:
        """Verifica HMAC-SHA256 según doc oficial de MP.

        Manifest: id:<data.id>;request-id:<x-request-id>;ts:<ts>;
        El trailing semicolon es obligatorio (doc oficial).
        """
        secret = _MP.WEBHOOK_SECRET
        if not secret:
            logger.warning(
                "MP webhook: MERCADOPAGO_WEBHOOK_SECRET no configurado — "
                "omitiendo verificación de firma (solo aceptable en dev local)"
            )
            return True

        x_signature  = headers.get("x-signature", "")
        x_request_id = headers.get("x-request-id", "")

        if not x_signature:
            logger.warning("MP webhook: header x-signature ausente")
            return False

        parts = {}
        for segment in x_signature.split(","):
            if "=" in segment:
                k, v = segment.split("=", 1)
                parts[k.strip()] = v.strip()

        ts = parts.get("ts", "")
        v1 = parts.get("v1", "")

        if not ts or not v1:
            logger.warning("MP webhook: x-signature mal formado: %s", x_signature[:100])
            return False

        data_id  = str(payload.get("data", {}).get("id", ""))
        manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"

        expected = hmac.new(
            secret.encode("utf-8"),
            manifest.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        ok = hmac.compare_digest(expected, v1)
        if not ok:
            logger.warning(
                "MP webhook: firma inválida — data_id=%s ts=%s manifest=%s",
                data_id, ts, manifest[:80],
            )
        return ok

    def validate_webhook(
        self, body: bytes, headers: dict[str, str], payload: dict,
    ) -> WebhookValidationResult:
        valid      = self._verify_signature(headers, payload)
        payment_id = str(payload.get("data", {}).get("id", ""))
        return WebhookValidationResult(
            valid=valid,
            event_type="unknown",
            user_id=None,
            plan=None,
            provider_payment_id=payment_id,
            provider_customer_id=None,
            provider_preference_id=None,
            provider_subscription_id=None,
            period_end=None,
            raw_payload=payload,
        )

    # ── Webhook — resolución completa (con I/O) ───────────────────────────────

    async def _fetch_payment(self, payment_id: str) -> dict:
        """GET /v1/payments/{id}"""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_MP_API_BASE}/v1/payments/{payment_id}",
                headers=self._auth_headers(),
            )
        if resp.status_code != 200:
            logger.error("MP fetch_payment HTTP %s — id=%s", resp.status_code, payment_id)
            return {}
        return resp.json()

    async def _fetch_subscription(self, subscription_id: str) -> dict:
        """GET /preapproval/{id} — estado de la suscripción."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_MP_API_BASE}/preapproval/{subscription_id}",
                headers=self._auth_headers(),
            )
        if resp.status_code != 200:
            logger.error("MP fetch_subscription HTTP %s — id=%s", resp.status_code, subscription_id)
            return {}
        return resp.json()

    def _parse_external_reference(self, ext_ref: str) -> tuple[int | None, str | None]:
        """Extrae (user_id, plan) del external_reference.

        Formato: ``user:<user_id>:plan:<plan_slug>``
        """
        try:
            parts   = ext_ref.split(":")
            user_id = int(parts[1])
            plan    = parts[3]
            if plan not in _VALID_PLANS:
                logger.warning("MP external_reference: plan desconocido '%s'", plan)
                return user_id, None
            return user_id, plan
        except (IndexError, ValueError, TypeError) as exc:
            logger.warning("MP external_reference imparseable '%s': %s", ext_ref, exc)
            return None, None

    async def _resolve_subscription_event(
        self, subscription_id: str, payload: dict,
    ) -> WebhookValidationResult:
        """Resuelve evento de suscripción via GET /preapproval/{id}.

        Mapeo de status:
          authorized → payment_approved  (suscripción activa, cobro exitoso)
          cancelled  → payment_failed    (suscripción cancelada)
          paused     → payment_pending   (suscripción pausada)
        """
        sub = await self._fetch_subscription(subscription_id)
        if not sub:
            return WebhookValidationResult(
                valid=True, event_type="payment_error",
                user_id=None, plan=None,
                provider_payment_id=None,
                provider_customer_id=None,
                provider_preference_id=None,
                provider_subscription_id=subscription_id,
                period_end=None, raw_payload=payload,
            )

        status   = sub.get("status", "")
        ext_ref  = sub.get("external_reference", "")
        payer    = sub.get("payer") or {}
        payer_id = str(payer.get("id", ""))

        user_id, plan = self._parse_external_reference(ext_ref)
        period_end = (datetime.now(timezone.utc) + timedelta(days=32)).isoformat()

        if status == "authorized":
            event_type = "payment_approved"
        elif status == "cancelled":
            event_type = "payment_failed"
        elif status == "paused":
            event_type = "payment_pending"
        else:
            event_type = "unknown"

        logger.info(
            "MP subscription resolved — id=%s status=%s event=%s user=%s plan=%s",
            subscription_id, status, event_type, user_id, plan,
        )
        return WebhookValidationResult(
            valid=True,
            event_type=event_type,
            user_id=user_id,
            plan=plan,
            provider_payment_id=None,
            provider_customer_id=payer_id,
            provider_preference_id=None,
            provider_subscription_id=subscription_id,
            period_end=period_end,
            raw_payload=payload,
        )

    async def process_webhook_payload(self, payload: dict) -> WebhookValidationResult:
        """Resuelve el evento completo consultando la API de MP.

        Maneja dos tipos de eventos:
          - subscription_preapproval → suscripción mensual (preapproval)
          - payment                  → pago único anual o cobro de suscripción
        """
        topic   = payload.get("type", "")
        action  = payload.get("action", "")
        data_id = str(payload.get("data", {}).get("id", ""))

        # ── Evento de suscripción mensual ──────────────────────────────────
        if topic == "subscription_preapproval":
            if not data_id:
                logger.warning("MP webhook subscription: data.id vacío — payload=%s", str(payload)[:200])
                return _unknown_result("", payload)
            return await self._resolve_subscription_event(data_id, payload)

        # ── Evento de pago (anual o cobro mensual de suscripción) ─────────
        is_payment = action in ("payment.created", "payment.updated") or topic == "payment"
        if not is_payment:
            logger.debug("MP webhook: tipo ignorado — type=%s action=%s", topic, action)
            return _unknown_result(data_id, payload)

        if not data_id:
            logger.warning("MP webhook: data.id vacío — payload=%s", str(payload)[:200])
            return _unknown_result("", payload)

        payment = await self._fetch_payment(data_id)
        if not payment:
            return WebhookValidationResult(
                valid=True, event_type="payment_error",
                user_id=None, plan=None,
                provider_payment_id=data_id,
                provider_customer_id=None,
                provider_preference_id=None,
                provider_subscription_id=None,
                period_end=None, raw_payload=payload,
            )

        status        = payment.get("status", "")
        ext_ref       = payment.get("external_reference", "")
        preference_id = payment.get("preference_id", "")
        payer         = payment.get("payer") or {}
        payer_id      = str(payer.get("id", ""))

        user_id, plan = self._parse_external_reference(ext_ref)

        metadata   = payment.get("metadata") or {}
        period_end = metadata.get("period_end")
        if not period_end and plan:
            catalog  = _PLAN_CATALOG.get(plan, {})
            interval = catalog.get("billing_interval", "yearly")
            delta    = timedelta(days=32) if interval == "monthly" else timedelta(days=366)
            period_end = (datetime.now(timezone.utc) + delta).isoformat()

        if status == "approved":
            event_type = "payment_approved"
        elif status in ("rejected", "cancelled", "refunded", "charged_back"):
            event_type = "payment_failed"
        elif status in ("pending", "in_process", "authorized"):
            event_type = "payment_pending"
        else:
            logger.info("MP payment status desconocido: '%s' para id=%s", status, data_id)
            event_type = "unknown"

        logger.info(
            "MP payment resolved — id=%s status=%s event=%s user=%s plan=%s",
            data_id, status, event_type, user_id, plan,
        )
        return WebhookValidationResult(
            valid=True,
            event_type=event_type,
            user_id=user_id,
            plan=plan,
            provider_payment_id=data_id,
            provider_customer_id=payer_id,
            provider_preference_id=preference_id,
            provider_subscription_id=None,
            period_end=period_end,
            raw_payload=payload,
        )
