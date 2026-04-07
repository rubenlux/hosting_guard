"""
API REST para el sistema de chat de soporte.

Endpoints:
  GET  /support/categories                    — categorías activas
  POST /support/tickets                       — cliente crea ticket + IA responde
  GET  /support/tickets                       — lista tickets (cliente: los suyos; staff: todos)
  GET  /support/tickets/{ticket_id}           — detalle + mensajes
  POST /support/tickets/{ticket_id}/messages  — enviar mensaje
  POST /support/tickets/{ticket_id}/escalate  — cliente pide humano
  POST /support/tickets/{ticket_id}/assign    — colaborador toma el ticket
  POST /support/tickets/{ticket_id}/resolve   — cerrar con resolución
  GET  /support/queue                         — cola de tickets (solo staff)
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.api.security import verify_token, verify_staff_token, require_staff_role
from app.core.support_ai import generate_support_response, get_ticket_priority
from app.infra.audit.hosting_repository import HostingRepository
from app.infra.audit.staff_repository import StaffRepository
from app.infra.audit.ticket_repository import TicketRepository
from app.infra.audit.support_cache_repository import SupportCacheRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["support"])

_ticket_repo  = TicketRepository()
_hosting_repo = HostingRepository()
_staff_repo   = StaffRepository()
_cache_repo   = SupportCacheRepository()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ip(request: Request) -> str:
    for header in ("X-Real-IP", "X-Forwarded-For"):
        val = request.headers.get(header)
        if val:
            return val.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_staff_token(request: Request) -> bool:
    return "staff_token" in request.cookies


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CreateTicketRequest(BaseModel):
    category: str
    description: str
    hosting_id: Optional[int] = None
    title: Optional[str] = None


class SendMessageRequest(BaseModel):
    content: str


class ResolveTicketRequest(BaseModel):
    resolution_note: str


class EscalateRequest(BaseModel):
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/categories")
def list_categories():
    """Lista de categorías activas con nombre, descripción e icono."""
    ICONS = {
        "Sitio caído":        "🔴",
        "Sitio lento":        "🐌",
        "Error en WordPress": "⚠️",
        "Problema de billing":"💳",
        "Ayuda técnica":      "🔧",
        "Otro":               "❓",
    }
    categories = _ticket_repo.list_categories()
    for cat in categories:
        cat["icon"] = ICONS.get(cat["name"], "❓")
    return categories


@router.post("/tickets", status_code=status.HTTP_201_CREATED)
async def create_ticket(
    request: Request,
    body: CreateTicketRequest,
    user: dict = Depends(verify_token),
):
    """
    Cliente crea un ticket. La IA genera la primera respuesta automáticamente.
    Retorna ticket_id y la respuesta inicial de la IA.
    """
    user_id = user["user_id"]

    # Obtener hint de la categoría
    cat_info = _ticket_repo.get_category_by_name(body.category)
    ai_prompt_hint = cat_info.get("ai_prompt_hint", "") if cat_info else ""
    priority = (cat_info.get("priority_default") if cat_info else None) or get_ticket_priority(body.category)

    # Obtener datos del hosting si se especificó
    hosting_data = None
    if body.hosting_id:
        try:
            hosting_data = _hosting_repo.get_hosting_by_id(body.hosting_id)
            # Validar que pertenece al usuario
            if hosting_data and hosting_data.get("user_id") != user_id:
                hosting_data = None
        except Exception:
            hosting_data = None

    # Título por defecto
    title = body.title or f"{body.category}: {body.description[:60]}"

    # Crear ticket
    ticket_id = _ticket_repo.create_ticket(
        user_id=user_id,
        category=body.category,
        title=title,
        priority=priority,
        hosting_id=body.hosting_id,
    )

    # Guardar mensaje inicial del cliente
    _ticket_repo.add_message(
        ticket_id=ticket_id,
        sender_type="user",
        sender_id=user_id,
        content=body.description,
    )

    # Notificar "IA analizando..." como mensaje de sistema
    _ticket_repo.add_message(
        ticket_id=ticket_id,
        sender_type="system",
        content="🤖 La IA está analizando tu consulta...",
    )

    # Generar respuesta IA
    ai_response, cache_id = await generate_support_response(
        category=body.category,
        description=body.description,
        ai_prompt_hint=ai_prompt_hint,
        hosting_data=hosting_data,
    )

    # Guardar respuesta IA y actualizar status
    _ticket_repo.add_message(
        ticket_id=ticket_id,
        sender_type="ai",
        content=ai_response,
        metadata={
            "category": body.category, 
            "ai_prompt_hint": ai_prompt_hint,
            "cache_id": cache_id
        },
    )
    _ticket_repo.update_ticket_status(
        ticket_id=ticket_id,
        status="ai_handled",
        ai_summary=ai_response[:300],
    )

    logger.info("Ticket %s created by user %s (category=%s)", ticket_id, user_id, body.category)

    return {
        "ticket_id":    ticket_id,
        "status":       "ai_handled",
        "ai_response":  ai_response,
        "priority":     priority,
    }


@router.get("/tickets")
def list_tickets(request: Request):
    """
    Cliente: ve sus propios tickets.
    Staff: ve todos los tickets (o los asignados si tiene rol support).
    """
    # Intentar auth de staff primero
    if _is_staff_token(request):
        try:
            payload = verify_staff_token(request)
            staff_id = payload["staff_id"]
            role     = payload.get("role", "support")
            # Admin y billing ven todos; support ve los suyos
            if role in ("admin", "billing", "readonly"):
                return _ticket_repo.list_tickets_for_staff(limit=100)
            return _ticket_repo.list_tickets_for_staff(staff_id=staff_id, limit=100)
        except HTTPException:
            pass

    # Auth de usuario normal
    user = verify_token(request)
    return _ticket_repo.list_tickets_for_user(user["user_id"])


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, request: Request):
    """Detalle completo del ticket con todos los mensajes."""
    ticket = _ticket_repo.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")

    # Verificar acceso
    if _is_staff_token(request):
        verify_staff_token(request)  # solo valida que el token sea válido
    else:
        user = verify_token(request)
        if ticket["user_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="Sin acceso a este ticket")

    messages = _ticket_repo.list_messages(ticket_id)
    return {**ticket, "messages": messages}


@router.post("/tickets/{ticket_id}/messages")
def send_message(
    ticket_id: int,
    request: Request,
    body: SendMessageRequest,
):
    """
    Envía un mensaje al ticket.
    Detecta automáticamente si viene de staff o cliente.
    Difunde el mensaje a los WebSocket conectados.
    """
    ticket = _ticket_repo.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")

    if _is_staff_token(request):
        payload   = verify_staff_token(request)
        sender_id = payload["staff_id"]
        sender_type = "staff"
    else:
        user = verify_token(request)
        if ticket["user_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="Sin acceso a este ticket")
        sender_id   = user["user_id"]
        sender_type = "user"

    msg_id = _ticket_repo.add_message(
        ticket_id=ticket_id,
        sender_type=sender_type,
        sender_id=sender_id,
        content=body.content,
    )

    # Broadcast vía WebSocket (importación diferida para evitar ciclo)
    try:
        from app.api.websocket.support_ws import broadcast_to_ticket
        import asyncio
        msg_data = {
            "type":        "message",
            "message_id":  msg_id,
            "ticket_id":   ticket_id,
            "sender_type": sender_type,
            "sender_id":   sender_id,
            "content":     body.content,
            "created_at":  datetime.now(timezone.utc).isoformat(),
        }
        asyncio.create_task(broadcast_to_ticket(ticket_id, msg_data))
    except Exception as ws_err:
        logger.debug("WS broadcast non-critical error: %s", ws_err)

    return {"message_id": msg_id, "ok": True}


@router.post("/tickets/{ticket_id}/escalate")
def escalate_ticket(
    ticket_id: int,
    request: Request,
    body: EscalateRequest = EscalateRequest(),
):
    """Cliente solicita hablar con un humano. Cambia status a 'waiting'."""
    user   = verify_token(request)
    ticket = _ticket_repo.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    if ticket["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Sin acceso a este ticket")
    if ticket["status"] in ("in_progress", "resolved", "closed"):
        raise HTTPException(status_code=400, detail="El ticket ya tiene un colaborador asignado o está cerrado")

    reason_msg = body.reason or "El cliente solicitó hablar con un colaborador."
    _ticket_repo.add_message(
        ticket_id=ticket_id,
        sender_type="system",
        content=f"📢 {reason_msg} Buscando colaborador disponible...",
    )
    _ticket_repo.update_ticket_status(ticket_id=ticket_id, status="waiting")

    # Notificar por WS
    try:
        from app.api.websocket.support_ws import broadcast_to_ticket
        import asyncio
        asyncio.create_task(broadcast_to_ticket(ticket_id, {
            "type":    "status_change",
            "status":  "waiting",
            "message": "Buscando colaborador disponible...",
        }))
    except Exception:
        pass

    logger.info("Ticket %s escalated to waiting by user %s", ticket_id, user["user_id"])
    return {"ok": True, "status": "waiting"}


@router.post("/tickets/{ticket_id}/assign")
def assign_ticket(
    ticket_id: int,
    request: Request,
    payload: dict = Depends(require_staff_role("support", "billing", "readonly")),
):
    """Colaborador toma el ticket. Cambia status a 'in_progress'."""
    ticket = _ticket_repo.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    if ticket["status"] == "in_progress" and ticket.get("assigned_to") != payload["staff_id"]:
        raise HTTPException(status_code=409, detail="El ticket ya fue tomado por otro colaborador")

    staff_id   = payload["staff_id"]
    staff_name = payload.get("full_name", "Colaborador")

    _ticket_repo.update_ticket_status(
        ticket_id=ticket_id,
        status="in_progress",
        assigned_to=staff_id,
    )
    _ticket_repo.add_message(
        ticket_id=ticket_id,
        sender_type="system",
        content=f"✅ {staff_name} se unió al chat y revisará tu caso.",
    )

    # Log de actividad del staff
    try:
        _staff_repo.log_activity(
            staff_id=staff_id,
            action_type="support_ticket_assigned",
            description=f"Tomó el ticket #{ticket_id} — {ticket.get('category')}",
            target_user_id=ticket.get("user_id"),
        )
    except Exception:
        pass

    # Broadcast WS
    try:
        from app.api.websocket.support_ws import broadcast_to_ticket
        import asyncio
        asyncio.create_task(broadcast_to_ticket(ticket_id, {
            "type":         "status_change",
            "status":       "in_progress",
            "staff_name":   staff_name,
            "message":      f"{staff_name} se unió al chat.",
        }))
    except Exception:
        pass

    logger.info("Ticket %s assigned to staff %s", ticket_id, staff_id)
    return {"ok": True, "status": "in_progress", "assigned_to": staff_id}


@router.post("/tickets/{ticket_id}/resolve")
def resolve_ticket(
    ticket_id: int,
    request: Request,
    body: ResolveTicketRequest,
):
    """Cierra el ticket con una nota de resolución. Puede hacerlo staff o cliente."""
    ticket = _ticket_repo.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")

    resolved_at = datetime.now(timezone.utc).isoformat()

    if _is_staff_token(request):
        payload  = verify_staff_token(request)
        staff_id = payload["staff_id"]
        _ticket_repo.update_ticket_status(
            ticket_id=ticket_id,
            status="resolved",
            resolved_at=resolved_at,
        )
        _ticket_repo.add_message(
            ticket_id=ticket_id,
            sender_type="system",
            content=f"✅ Ticket resuelto. Nota: {body.resolution_note}",
        )
        # Log de actividad
        try:
            _staff_repo.log_activity(
                staff_id=staff_id,
                action_type="issue_resolved",
                description=f"Resolvió el ticket #{ticket_id}: {body.resolution_note[:100]}",
                target_user_id=ticket.get("user_id"),
            )
        except Exception:
            pass
    else:
        user = verify_token(request)
        if ticket["user_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="Sin acceso")
        _ticket_repo.update_ticket_status(
            ticket_id=ticket_id,
            status="resolved",
            resolved_at=resolved_at,
        )
        _ticket_repo.add_message(
            ticket_id=ticket_id,
            sender_type="system",
            content="✅ El cliente confirmó que el problema fue resuelto.",
        )

        # Buscar si hubo una respuesta de IA con cache_id para darle feedback
        try:
            messages = _ticket_repo.list_messages(ticket_id)
            for msg in messages:
                if msg.get("sender_type") == "ai" and msg.get("metadata"):
                    cache_id = msg["metadata"].get("cache_id")
                    if cache_id:
                        _cache_repo.record_feedback(cache_id, resolved=True)
                        break
        except Exception as e:
            logger.debug("Cache feedback non-critical error: %s", e)

    # Broadcast WS
    try:
        from app.api.websocket.support_ws import broadcast_to_ticket
        import asyncio
        asyncio.create_task(broadcast_to_ticket(ticket_id, {
            "type":    "status_change",
            "status":  "resolved",
            "message": "Ticket resuelto.",
        }))
    except Exception:
        pass

    logger.info("Ticket %s resolved", ticket_id)
    return {"ok": True, "status": "resolved"}


@router.get("/queue")
def get_queue(
    payload: dict = Depends(require_staff_role("support", "billing", "readonly")),
):
    """Cola de tickets en espera. Solo staff. Ordenada por prioridad y tiempo."""
    tickets = _ticket_repo.list_queue()
    waiting_count = _ticket_repo.count_waiting_tickets()
    return {
        "waiting_count": waiting_count,
        "tickets":       tickets,
    }
