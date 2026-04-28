import os as _os

class Settings:
    DOMAIN = "hostingguard.lat"
    BASE_PATH = "/opt/clients/"


def _ls_env(test_key: str, prod_key: str) -> str:
    """Return test env var if set, else prod env var. Allows dual test/prod config."""
    return _os.getenv(test_key) or _os.getenv(prod_key, "")


class LemonSqueezySettings:
    # Keys — test vars take priority over prod vars so test mode is the default.
    # Switch to prod by unsetting the _TEST vars and setting the plain ones.
    API_KEY        = _ls_env("LEMONSQUEEZY_API_KEY_TEST",        "LEMONSQUEEZY_API_KEY")
    WEBHOOK_SECRET = _ls_env("LEMONSQUEEZY_WEBHOOK_SECRET_TEST", "LEMONSQUEEZY_WEBHOOK_SECRET")
    STORE_ID       = _ls_env("LEMONSQUEEZY_STORE_ID_TEST",       "LEMONSQUEEZY_STORE_ID")

    # Annual variant IDs — one per paid plan
    VARIANT_PERSONAL = _ls_env("LS_VARIANT_PERSONAL_YEARLY_TEST", "LS_VARIANT_PERSONAL_YEARLY")
    VARIANT_NEGOCIO  = _ls_env("LS_VARIANT_NEGOCIO_YEARLY_TEST",  "LS_VARIANT_NEGOCIO_YEARLY")
    VARIANT_AGENCIA  = _ls_env("LS_VARIANT_AGENCIA_YEARLY_TEST",  "LS_VARIANT_AGENCIA_YEARLY")

    @classmethod
    def variant_map(cls) -> dict:
        """plan_slug → variant_id"""
        return {
            "personal": cls.VARIANT_PERSONAL,
            "negocio":  cls.VARIANT_NEGOCIO,
            "agencia":  cls.VARIANT_AGENCIA,
        }

    @classmethod
    def plan_from_variant(cls, variant_id: str) -> str | None:
        """variant_id → plan_slug"""
        return {v: k for k, v in cls.variant_map().items() if v}.get(str(variant_id))
