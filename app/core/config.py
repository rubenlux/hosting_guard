import os as _os


class Settings:
    DOMAIN = "hostingguard.lat"
    BASE_PATH = "/opt/clients/"


class MercadoPagoSettings:
    """Configuración del proveedor de pagos MercadoPago.

    Variables de entorno requeridas en producción:
        MERCADOPAGO_ACCESS_TOKEN   — credencial privada para la API de MP
        MERCADOPAGO_PUBLIC_KEY     — clave pública para el SDK de frontend (no exponer al backend)
        MERCADOPAGO_WEBHOOK_SECRET — secreto para verificar firmas de webhooks

    Variables opcionales:
        MERCADOPAGO_SANDBOX        — "true" para usar sandbox_init_point (default: "false")
        MERCADOPAGO_WEBHOOK_BASE_URL — base para construir notification_url
                                       (default: https://api.hostingguard.lat)
        MERCADOPAGO_FRONTEND_URL   — base para back_urls (default: https://hostingguard.lat)
    """

    ACCESS_TOKEN    = _os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
    PUBLIC_KEY      = _os.getenv("MERCADOPAGO_PUBLIC_KEY", "")
    WEBHOOK_SECRET  = _os.getenv("MERCADOPAGO_WEBHOOK_SECRET", "")

    SANDBOX_MODE    = _os.getenv("MERCADOPAGO_SANDBOX", "false").lower() == "true"

    WEBHOOK_BASE_URL = _os.getenv(
        "MERCADOPAGO_WEBHOOK_BASE_URL",
        "https://api.hostingguard.lat",
    )
    FRONTEND_URL = _os.getenv(
        "MERCADOPAGO_FRONTEND_URL",
        "https://hostingguard.lat",
    )
