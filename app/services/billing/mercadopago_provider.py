"""MercadoPagoProvider — Checkout Pro (Preferences API).

Refs oficiales:
  Crear aplicación:  https://www.mercadopago.com.ar/developers/es/docs/checkout-pro/create-application
  Preferences API:   https://www.mercadopago.com.ar/developers/es/reference/preferences/_checkout_preferences/post
  Webhooks:          https://www.mercadopago.com.ar/developers/es/docs/your-integrations/notifications/webhooks
  Pagos GET:         https://www.mercadopago.com.ar/developers/es/reference/payments/_payments_id/get

Verificación de firma HMAC-SHA256 (según doc oficial):
  Header recibido:   x-signature: ts=<timestamp>,v1=<hash>
  Manifest:          id:<data.id>;request-id:<x-request-id>;ts:<ts>;   ← trailing semicolon requerido
  Clave:             MERCADOPAGO_WEBHOOK_SECRET
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
# Precios en USD · facturación anual (o mensual para enterprise_monthly).
# Estos valores son el fallback estático; en producción se obtienen de la
# tabla plan_economics en la DB cuando el caller lo permite.

_PLAN_CATALOG: dict[str, dict] = {
    "personal":           {"title": "Plan Personal",           "unit_price": 108.00,  "billing_interval": "yearly"},
    "negocio":            {"title": "Plan Negocio",            "unit_price": 228.00,  "billing_interval": "yearly"},
    "agencia":            {"title": "Plan Agencia",            "unit_price": 468.00,  "billing_interval": "yearly"},
    "agencia_pro":        {"title": "Plan Agencia Pro",        "unit_price": 708.00,  "billing_interval": "yearly"},
    "enterprise_annual":  {"title": "Plan Enterprise Anual",   "unit_price": 1188.00, "billing_interval": "yearly"},
    "enterprise_monthly": {"title": "Plan Enterprise Mensual", "unit_price": 129.00,  "billing_interval": "monthly"},
}

_VALID_PLANS = frozenset(_PLAN_CATALOG)


def _unknown_result(payment_id: str, payload: dict) -> WebhookValidationResult:
    """Helper para retornar un evento desconocido sin repetir el dict."""
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


class MercadoPagoProvider(PaymentProvider):
    """Proveedor de pagos usando MercadoPago Checkout Pro."""

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _auth_headers(self, idempotency_key: str = "") -> dict:
        """Cabeceras base para la API de MP."""
        h = {
            "Authorization": f"Bearer {_MP.ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            h["X-Idempotency-Key"] = idempotency_key
        return h

    def is_configured(self) -> bool:
        return bool(_MP.ACCESS_TOKEN)

    # ── Checkout Pro — crear preferencia ─────────────────────────────────────

    async def create_payment_link(self, plan: str, user: dict) -> CheckoutResult:
        """Crea una preference en MercadoPago y retorna el init_point.

        Endpoint: POST https://api.mercadopago.com/checkout/preferences
        Docs:     https://www.mercadopago.com.ar/developers/es/docs/checkout-pro/create-application

        Campos clave de la preference:
          items[]         — artículo del pago (plan seleccionado)
          payer.email     — pre-carga el email del usuario en el checkout
          back_urls       — redirección post-pago (success/failure/pending)
          auto_return     — "approved": MP redirige automáticamente si el pago fue exitoso
          notification_url— URL del webhook que recibirá las notificaciones IPN
          external_reference— identificador propio; viaja en todas las notificaciones
        """
        if plan not in _VALID_PLANS:
            valid = ", ".join(sorted(_VALID_PLANS))
            raise ValueError(f"Plan no válido: '{plan}'. Opciones: {valid}")

        if not self.is_configured():
            raise RuntimeError("MercadoPago no configurado — falta MERCADOPAGO_ACCESS_TOKEN")

        catalog   = _PLAN_CATALOG[plan]
        user_id   = str(user["user_id"])
        email     = user.get("email", "")
        interval  = catalog["billing_interval"]

        # external_reference: viaja en todas las notificaciones de pago.
        # Formato: "user:<id>:plan:<slug>"  →  parseable en _parse_external_reference()
        external_ref = f"user:{user_id}:plan:{plan}"

        # notification_url: MP llamará a este endpoint con cada evento de pago.
        # Debe ser una URL HTTPS pública (no localhost). Se configura también en el
        # panel de MP: Tus integraciones → tu app → Notificaciones.
        notification_url = f"{_MP.WEBHOOK_BASE_URL}/billing/webhooks/mercadopago"

        # period_end para que el webhook lo pueda usar sin recalcular
        expires_delta = timedelta(days=32) if interval == "monthly" else timedelta(days=366)
        period_end    = (datetime.now(timezone.utc) + expires_delta).isoformat()

        # ── Payload de la preference ─────────────────────────────────────────
        # Ref: https://www.mercadopago.com.ar/developers/es/reference/preferences/_checkout_preferences/post
        preference_payload = {
            # Artículo del pago — un solo ítem por plan
            "items": [
                {
                    "id":          f"hostingguard-{plan}",
                    "title":       catalog["title"],
                    "description": (
                        f"HostingGuard · {catalog['title']} · "
                        f"facturación {'anual' if interval == 'yearly' else 'mensual'}"
                    ),
                    "quantity":    1,
                    "unit_price":  catalog["unit_price"],
                    "currency_id": "USD",
                }
            ],
            # Pre-carga email del usuario en el checkout de MP
            "payer": {
                "email": email,
            },
            # Redirección post-pago — el frontend maneja cada caso
            "back_urls": {
                "success": f"{_MP.FRONTEND_URL}/dashboard?billing=success",
                "failure": f"{_MP.FRONTEND_URL}/dashboard?billing=failure",
                "pending": f"{_MP.FRONTEND_URL}/dashboard?billing=pending",
            },
            # MP redirige automáticamente al usuario si el pago fue aprobado.
            # "approved" → solo redirige en pagos aprobados (comportamiento recomendado)
            "auto_return": "approved",
            # Webhook IPN — MP POST-ea aquí tras cada evento de pago
            "notification_url": notification_url,
            # Identificador propio — aparece en todas las notificaciones y en el panel de MP
            "external_reference": external_ref,
            # metadata: datos adicionales que MP almacena y devuelve en GET /payments/{id}
            "metadata": {
                "user_id":          user_id,
                "plan":             plan,
                "billing_interval": interval,
                "period_end":       period_end,
            },
            # Nombre del negocio que aparece en el resumen de la tarjeta del comprador
            "statement_descriptor": "HOSTINGGUARD",
        }

        # X-Idempotency-Key: previene preferencias duplicadas ante retries de red
        idempotency_key = f"{user_id}-{plan}-{uuid.uuid4()}"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{_MP_API_BASE}/checkout/preferences",
                json=preference_payload,
                headers=self._auth_headers(idempotency_key),
            )

        if resp.status_code not in (200, 201):
            logger.error(
                "MP create_preference error HTTP %s — user=%s plan=%s body=%s",
                resp.status_code, user_id, plan, resp.text[:400],
            )
            raise RuntimeError(
                f"Error al crear la preferencia en MercadoPago (HTTP {resp.status_code})"
            )

        data         = resp.json()
        preference_id = data.get("id", "")

        # Producción → init_point   |   Sandbox → sandbox_init_point
        # Seleccionar según el modo configurado en las variables de entorno
        if _MP.SANDBOX_MODE:
            payment_url = data.get("sandbox_init_point") or data.get("init_point", "")
        else:
            payment_url = data.get("init_point", "")

        logger.info(
            "MP preference created — id=%s plan=%s user=%s url=%s",
            preference_id, plan, user_id, payment_url[:60],
        )
        return CheckoutResult(payment_url=payment_url, preference_id=preference_id)

    # ── Webhook — validación de firma ─────────────────────────────────────────

    def _verify_signature(
        self,
        headers: dict[str, str],
        payload: dict,
    ) -> bool:
        """Verifica la firma HMAC-SHA256 del webhook según la doc oficial de MP.

        Algoritmo (ref oficial):
          1. Extraer ``ts`` y ``v1`` del header ``x-signature``
             Formato:   ``x-signature: ts=<timestamp>,v1=<hash>``
          2. Construir el manifest:
             ``id:<data.id>;request-id:<x-request-id>;ts:<ts>;``
             ⚠ El trailing semicolon es obligatorio según la documentación oficial.
          3. Calcular HMAC-SHA256(manifest, MERCADOPAGO_WEBHOOK_SECRET)
          4. Comparar con ``v1`` (timing-safe)

        Si MERCADOPAGO_WEBHOOK_SECRET no está configurado → se omite la
        verificación con un warning (útil en dev local; nunca en producción).
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
            logger.warning("MP webhook: header x-signature ausente — rechazando")
            return False

        # Parsear  ts=<timestamp>,v1=<hash>
        # Usamos split("=", 1) para manejar valores con "=" dentro del hash
        parts = {}
        for segment in x_signature.split(","):
            if "=" in segment:
                k, v = segment.split("=", 1)
                parts[k.strip()] = v.strip()

        ts = parts.get("ts", "")
        v1 = parts.get("v1", "")

        if not ts or not v1:
            logger.warning(
                "MP webhook: x-signature con formato inesperado: %s",
                x_signature[:100],
            )
            return False

        # data.id del payload es el payment_id que va en el manifest
        data_id = str(payload.get("data", {}).get("id", ""))

        # ⚠ Trailing semicolon obligatorio según doc oficial de MercadoPago:
        # https://www.mercadopago.com.ar/developers/es/docs/your-integrations/notifications/webhooks
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
        self,
        body: bytes,
        headers: dict[str, str],
        payload: dict,
    ) -> WebhookValidationResult:
        """Valida la firma del webhook de forma síncrona (sin I/O).

        Retorna inmediatamente con ``valid=False`` si la firma no es válida.
        El procesamiento completo (fetch al API de MP) ocurre en el background
        task vía ``process_webhook_payload()``.
        """
        valid       = self._verify_signature(headers, payload)
        payment_id  = str(payload.get("data", {}).get("id", ""))

        return WebhookValidationResult(
            valid=valid,
            event_type="unknown",
            user_id=None,
            plan=None,
            provider_payment_id=payment_id,
            provider_customer_id=None,
            provider_preference_id=None,
            period_end=None,
            raw_payload=payload,
        )

    # ── Webhook — resolución completa (con I/O) ───────────────────────────────

    async def _fetch_payment(self, payment_id: str) -> dict:
        """GET /v1/payments/{id} — obtiene el detalle completo del pago."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_MP_API_BASE}/v1/payments/{payment_id}",
                headers=self._auth_headers(),
            )
        if resp.status_code != 200:
            logger.error(
                "MP fetch_payment error — id=%s HTTP %s body=%s",
                payment_id, resp.status_code, resp.text[:300],
            )
            return {}
        return resp.json()

    def _parse_external_reference(self, ext_ref: str) -> tuple[int | None, str | None]:
        """Extrae (user_id, plan) del external_reference.

        Formato esperado: ``user:<user_id>:plan:<plan_slug>``
        Ejemplo:          ``user:42:plan:negocio``
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
            logger.warning(
                "MP external_reference imparseable '%s': %s", ext_ref, exc
            )
            return None, None

    async def process_webhook_payload(self, payload: dict) -> WebhookValidationResult:
        """Resuelve el detalle completo del evento de pago consultando la API de MP.

        Tipos de evento manejados (campo ``type`` o ``action``):
          payment.created  → pago nuevo
          payment.updated  → actualización de estado (aprobado, rechazado, etc.)

        Mapeo de status de MP a event_type interno:
          approved             → payment_approved  (activa el plan)
          rejected/cancelled   → payment_failed    (notifica al usuario)
          pending/in_process   → payment_pending   (marca como pendiente)
        """
        action     = payload.get("action", "")
        topic      = payload.get("type", "")
        payment_id = str(payload.get("data", {}).get("id", ""))

        # Solo procesamos eventos de tipo "payment"
        is_payment_action = action in ("payment.created", "payment.updated")
        is_payment_topic  = topic == "payment"

        if not is_payment_action and not is_payment_topic:
            logger.debug(
                "MP webhook: tipo ignorado — type=%s action=%s", topic, action
            )
            return _unknown_result(payment_id, payload)

        if not payment_id:
            logger.warning("MP webhook: data.id vacío — payload=%s", str(payload)[:200])
            return _unknown_result("", payload)

        # Consultar detalle del pago en la API de MP
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

        status        = payment.get("status", "")
        ext_ref       = payment.get("external_reference", "")
        preference_id = payment.get("preference_id", "")
        payer         = payment.get("payer") or {}
        payer_id      = str(payer.get("id", ""))
        payer_email   = payer.get("email", "")

        # Resolver user_id y plan desde external_reference
        user_id, plan = self._parse_external_reference(ext_ref)

        # period_end: viene en metadata de la preference, o se calcula
        metadata   = payment.get("metadata") or {}
        period_end = metadata.get("period_end")
        if not period_end and plan:
            catalog  = _PLAN_CATALOG.get(plan, {})
            interval = catalog.get("billing_interval", "yearly")
            delta    = timedelta(days=32) if interval == "monthly" else timedelta(days=366)
            period_end = (datetime.now(timezone.utc) + delta).isoformat()

        # Mapeo de status de MercadoPago → event_type interno
        # Ref: https://www.mercadopago.com.ar/developers/es/reference/payments/_payments_id/get
        if status == "approved":
            event_type = "payment_approved"
        elif status in ("rejected", "cancelled", "refunded", "charged_back"):
            event_type = "payment_failed"
        elif status in ("pending", "in_process", "authorized"):
            event_type = "payment_pending"
        else:
            logger.info("MP payment status desconocido: '%s' para id=%s", status, payment_id)
            event_type = "unknown"

        logger.info(
            "MP payment resolved — id=%s status=%s event=%s user=%s plan=%s",
            payment_id, status, event_type, user_id, plan,
        )

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
