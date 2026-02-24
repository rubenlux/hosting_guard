from fastapi import Header, HTTPException, status

from app.api.tenancy import Tenant

# MVP: mapping estático (luego DB)
API_KEY_TO_TENANT = {
    "key-client-1": Tenant(tenant_id="tenant_1", name="Cliente Uno"),
    "key-client-2": Tenant(tenant_id="tenant_2", name="Cliente Dos"),
}


def resolve_tenant(x_api_key: str = Header(...)) -> Tenant:
    tenant = API_KEY_TO_TENANT.get(x_api_key)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant API key",
        )

    return tenant
