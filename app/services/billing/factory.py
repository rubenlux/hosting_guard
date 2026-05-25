"""Factory de PaymentProvider.

El resto del sistema importa `get_payment_provider()` — nunca importa
un proveedor concreto directamente. Cambiar de proveedor en el futuro
solo requiere añadir una nueva implementación y actualizar esta función.
"""

from __future__ import annotations

from functools import lru_cache

from app.services.billing.interface import PaymentProvider


@lru_cache(maxsize=1)
def get_payment_provider() -> PaymentProvider:
    """Retorna la instancia singleton del proveedor activo.

    El proveedor activo es MercadoPago. Para cambiar de proveedor en el
    futuro, crear una nueva clase que implemente PaymentProvider y
    retornarla aquí (o leerlo de una variable de entorno).
    """
    from app.services.billing.mercadopago_provider import MercadoPagoProvider
    return MercadoPagoProvider()
