"""User notification endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.security import verify_token
from app.infra.audit.notification_repository import NotificationRepository

router = APIRouter(prefix="/notifications", tags=["notifications"])
_repo = NotificationRepository()


@router.get("")
def list_notifications(
    status:   Optional[str] = Query(default="all", regex="^(unread|read|archived|all)$"),
    category: Optional[str] = Query(default=None),
    limit:    int = Query(default=30, ge=1, le=100),
    offset:   int = Query(default=0, ge=0),
    user: dict = Depends(verify_token),
):
    items = _repo.get_for_user(
        user["user_id"], status=status, category=category, limit=limit, offset=offset,
    )
    unread = _repo.get_unread_count(user["user_id"])
    return {"items": items, "unread": unread}


@router.get("/count")
def unread_count(user: dict = Depends(verify_token)):
    return {"unread": _repo.get_unread_count(user["user_id"])}


@router.patch("/{notification_id}/read")
def mark_read(notification_id: int, user: dict = Depends(verify_token)):
    _repo.mark_read(notification_id, user["user_id"])
    return {"ok": True}


@router.patch("/read-all")
def mark_all_read(user: dict = Depends(verify_token)):
    updated = _repo.mark_all_read(user["user_id"])
    return {"ok": True, "updated": updated}


@router.delete("/{notification_id}")
def archive_notification(notification_id: int, user: dict = Depends(verify_token)):
    _repo.archive(notification_id, user["user_id"])
    return {"ok": True}
