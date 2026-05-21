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
from app.infra.db import get_connection, release_connection
from app.services.ai_quota_service import check_ai_quota, record_ai_usage

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


def _get_user_plan(user_id: int) -> str:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT plan FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        return (row or {}).get("plan") or "free"
    finally:
        release_connection(conn)


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

    # Obtener datos del hosting — usar el especificado o auto-detectar
    hosting_data = None
    if body.hosting_id:
        try:
            hosting_data = _hosting_repo.get_hosting_any(body.hosting_id)
            if hosting_data and hosting_data.get("user_id") != user_id:
                hosting_data = None
        except Exception:
            hosting_data = None

    if hosting_data is None:
        # Auto-detectar: usar el primer hosting activo del usuario
        try:
            user_hostings = [
                h for h in _hosting_repo.get_user_hostings(user_id)
                if h.get("status") == "active"
            ]
            if user_hostings:
                hosting_data = user_hostings[0]
        except Exception:
            pass

    # Título por defecto
    title = body.title or f"{body.category}: {body.description[:60]}"

    # Verificar cuota IA antes de crear el ticket — evita tickets fantasma
    _user_plan = _get_user_plan(user_id)
    check_ai_quota(user_id, "support_chat", _user_plan)

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
    ai_response, cache_id, _ai_source = await generate_support_response(
        category=body.category,
        description=body.description,
        ai_prompt_hint=ai_prompt_hint,
        hosting_data=hosting_data,
    )
    if _ai_source == "claude":
        record_ai_usage(user_id, "support_chat", _user_plan)

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

    # Broadcast vía WebSocket
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

    # Auto-reply: if message is from user and ticket is still AI-handled, generate AI follow-up
    if sender_type == "user" and ticket.get("status") == "ai_handled":
        try:
            import asyncio as _asyncio
            _asyncio.create_task(_ai_followup_reply(ticket_id, ticket))
        except Exception as exc:
            logger.debug("AI follow-up task creation failed (non-critical): %s", exc)

    return {"message_id": msg_id, "ok": True}


async def _ai_followup_reply(ticket_id: int, ticket: dict) -> None:
    """Generate and save an AI reply for a follow-up user message."""
    try:
        from app.core.support_ai import generate_support_response

        messages = _ticket_repo.list_messages(ticket_id)
        history = [
            m for m in messages
            if m.get("sender_type") in ("user", "ai", "staff") and m.get("content", "").strip()
        ]
        if not history:
            return

        last_user_msg = next(
            (m for m in reversed(history) if m.get("sender_type") == "user"), None
        )
        if not last_user_msg:
            return

        # Fetch hosting context
        hosting_data = None
        if ticket.get("hosting_id"):
            try:
                hosting_data = _hosting_repo.get_hosting_any(ticket["hosting_id"])
            except Exception:
                pass

        cat_info = _ticket_repo.get_category_by_name(ticket.get("category", ""))
        ai_prompt_hint = cat_info.get("ai_prompt_hint", "") if cat_info else ""

        _followup_user_id = ticket["user_id"]
        _followup_plan = _get_user_plan(_followup_user_id)
        try:
            check_ai_quota(_followup_user_id, "support_chat", _followup_plan)
        except Exception:
            logger.info("AI quota exceeded for user_id=%s in followup reply", _followup_user_id)
            _ticket_repo.add_message(
                ticket_id=ticket_id,
                sender_type="system",
                content="Alcanzaste el límite de consultas IA de tu plan. Un colaborador podrá continuar la conversación.",
            )
            return

        ai_response, _, _ai_source = await generate_support_response(
            category=ticket.get("category", "Ayuda técnica"),
            description=last_user_msg["content"],
            ai_prompt_hint=ai_prompt_hint,
            hosting_data=hosting_data,
            message_history=history[:-1],  # history without the last user message
        )
        if _ai_source == "claude":
            record_ai_usage(_followup_user_id, "support_chat", _followup_plan)

        _ticket_repo.add_message(
            ticket_id=ticket_id,
            sender_type="ai",
            content=ai_response,
        )

        # Broadcast AI response via WebSocket
        try:
            from app.api.websocket.support_ws import broadcast_to_ticket
            await broadcast_to_ticket(ticket_id, {
                "type":        "message",
                "ticket_id":   ticket_id,
                "sender_type": "ai",
                "content":     ai_response,
                "created_at":  datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass

        logger.info("AI follow-up reply sent for ticket %s", ticket_id)
    except Exception as exc:
        logger.error("AI follow-up reply failed for ticket %s: %s", ticket_id, exc, exc_info=True)


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
