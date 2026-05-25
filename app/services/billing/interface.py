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
    """Resultado de validar + parsear un webhook de pago.

    ``valid``                  — False indica firma inválida; el endpoint debe retornar 401.
    ``event_type``             — "payment_approved" | "payment_failed" | "payment_pending" | "unknown"
    ``user_id``                — ID del usuario resuelto desde el payload.
    ``provider_subscription_id`` — ID de suscripción (planes mensuales); None para pagos únicos.
    """
    valid: bool
    event_type: str
    user_id: int | None
    plan: str | None
    provider_payment_id: str | None
    provider_customer_id: str | None
    provider_preference_id: str | None
    provider_subscription_id: str | None  # ID de suscripción recurrente (preapproval)
    period_end: str | None
    raw_payload: dict


class PaymentProvider(ABC):
    """Interfaz que todo proveedor de pagos debe implementar.

    El route layer importa únicamente esta interfaz — nunca una clase concreta.
    """

    # ── Checkout ──────────────────────────────────────────────────────────────

    @abstractmethod
    async def create_payment_link(self, plan: str, user: dict) -> CheckoutResult:
        """Genera un link de pago para el plan solicitado.

        Args:
            plan:  slug del plan (personal | negocio | agencia | agencia_pro |
                   enterprise_annual | enterprise_monthly)
            user:  dict con al menos ``user_id`` y ``email``

        Returns:
            CheckoutResult con la URL de pago y el ID de preferencia.

        Raises:
            ValueError:   si el plan no es válido.
            RuntimeError: si el proveedor no está configurado.
        """

    # ── Webhooks ─────────────────────────────────────────────────────────────

    @abstractmethod
    def validate_webhook(
        self,
        body: bytes,
        headers: dict[str, str],
        payload: dict,
    ) -> WebhookValidationResult:
        """Valida la firma del webhook *de forma síncrona* (sin I/O).

        Args:
            body:    cuerpo raw de la petición (para HMAC sobre body, si aplica).
            headers: cabeceras HTTP del request (claves en minúscula).
            payload: JSON ya parseado del body.

        Returns:
            WebhookValidationResult con ``valid=False`` si la firma no es válida.
            El endpoint debe retornar 401 inmediatamente en ese caso.
        """

    @abstractmethod
    async def process_webhook_payload(self, payload: dict) -> WebhookValidationResult:
        """Resuelve el detalle completo del evento de pago (puede hacer I/O).

        Se llama desde un background task *después* de que ``validate_webhook``
        haya confirmado la autenticidad. Implementaciones típicas:
        - Consultan la API del proveedor para obtener estado del pago.
        - Mapean ese estado al event_type interno del sistema.

        Args:
            payload: JSON parseado del webhook (mismo que se pasó a validate_webhook).

        Returns:
            WebhookValidationResult completo con user_id, plan y event_type resueltos.
        """

    # ── Helpers ───────────────────────────────────────────────────────────────

    @abstractmethod
    def is_configured(self) -> bool:
        """True si las credenciales mínimas están presentes en el entorno."""
