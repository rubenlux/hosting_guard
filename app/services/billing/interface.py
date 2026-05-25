"""PaymentProvider — interfaz abstracta de pagos.

Cualquier proveedor futuro (Stripe, Paddle, etc.) debe implementar esta
interfaz. La lógica de negocio nunca importa un proveedor concreto.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CheckoutResult:
    """Resultado de crear un link de pago."""
    payment_url: str        # URL a la que se redirige al usuario
    preference_id: str      # ID interno del proveedor (preference, session…)


@dataclass
class WebhookValidationResult:
    """Resultado de validar + parsear un webhook de pago."""
    valid: bool
    event_type: str         # "payment_approved" | "payment_failed" | "payment_pending" | "unknown"
    user_id: int | None
    plan: str | None
    provider_payment_id: str | None
    provider_customer_id: str | None
    provider_preference_id: str | None
    period_end: str | None
    raw_payload: dict


class PaymentProvider(ABC):
    """Interfaz que todo proveedor de pagos debe implementar."""

    # ── Checkout ──────────────────────────────────────────────────────────────

    @abstractmethod
    async def create_payment_link(self, plan: str, user: dict) -> CheckoutResult:
        """Genera un link de pago para el plan solicitado.

        Args:
            plan:  slug del plan (personal, negocio, agencia, agencia_pro,
                   enterprise_annual, enterprise_monthly)
            user:  dict con al menos ``user_id`` y ``email``

        Returns:
            CheckoutResult con la URL de pago y el ID de preferencia.

        Raises:
            ValueError: si el plan no es válido.
            RuntimeError: si el proveedor no está configurado.
        """

    # ── Webhooks ──────────────────────────────────────────────────────────────

    @abstractmethod
    def validate_webhook(
        self,
        body: bytes,
        headers: dict[str, str],
        payload: dict,
    ) -> WebhookValidationResult:
        """Valida la firma del webhook y extrae la info del pago.

        Args:
            body:     cuerpo raw de la petición (bytes) para verificar HMAC.
            headers:  cabeceras HTTP del request.
            payload:  JSON parseado del body.

        Returns:
            WebhookValidationResult.  Si ``valid=False``, el endpoint debe
            retornar 401.
        """

    # ── Helpers ───────────────────────────────────────────────────────────────

    @abstractmethod
    def is_configured(self) -> bool:
        """True si las credenciales mínimas están presentes en el entorno."""
