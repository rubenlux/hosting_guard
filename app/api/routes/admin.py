from fastapi import APIRouter, Depends
from app.api.security import require_role
from app.infra.audit.user_repository import UserRepository
from app.infra.audit.hosting_repository import HostingRepository

router = APIRouter(prefix="/admin", tags=["admin"])

_user_repo    = UserRepository()
_hosting_repo = HostingRepository()


@router.get("/users")
def list_all_users(user: dict = Depends(require_role("admin"))):
    """Lista todos los usuarios registrados. Solo admin."""
    return _user_repo.get_all_users()


@router.get("/hostings")
def list_all_hostings(user: dict = Depends(require_role("admin"))):
    """Lista todos los hostings de todos los usuarios. Solo admin."""
    return _hosting_repo.get_all_hostings()
