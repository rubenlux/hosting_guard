"""
WebSocket para el chat de soporte en tiempo real.

Ruta: WS /ws/support/{ticket_id}

El servidor mantiene un dict en memoria de conexiones activas por ticket_id.
Cuando llega un mensaje, lo guarda en la DB y lo retransmite a todos los
conectados al mismo ticket (cliente + colaborador).

Traefik v3 soporta WebSockets de forma nativa sin configuración adicional.
"""
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# Dict en memoria: ticket_id -> set de WebSocket activos
_connections: Dict[int, Set[WebSocket]] = defaultdict(set)


# ---------------------------------------------------------------------------
# Gestión de conexiones
# ---------------------------------------------------------------------------

async def _connect(ticket_id: int, ws: WebSocket) -> None:
    await ws.accept()
    _connections[ticket_id].add(ws)
    logger.debug("WS connected: ticket=%s (total=%d)", ticket_id, len(_connections[ticket_id]))


def _disconnect(ticket_id: int, ws: WebSocket) -> None:
    _connections[ticket_id].discard(ws)
    if not _connections[ticket_id]:
        del _connections[ticket_id]
    logger.debug("WS disconnected: ticket=%s", ticket_id)


async def broadcast_to_ticket(ticket_id: int, data: dict) -> None:
    """Envía un mensaje JSON a todos los conectados al ticket. Safe to call from REST endpoints."""
    sockets = list(_connections.get(ticket_id, set()))
    if not sockets:
        return
    payload = json.dumps(data, ensure_ascii=False, default=str)
    dead: list = []
    for ws in sockets:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _connections[ticket_id].discard(ws)


# ---------------------------------------------------------------------------
# Handler principal del WebSocket
# ---------------------------------------------------------------------------

async def support_ws_handler(websocket: WebSocket, ticket_id: int) -> None:
    """
    Punto de entrada del WebSocket. Registrado en main.py como:
      app.add_api_websocket_route("/ws/support/{ticket_id}", support_ws_handler)
    """
    from app.infra.audit.ticket_repository import TicketRepository
    from app.infra.audit.sqlite import get_connection  # noqa: needed for thread safety check

    ticket_repo = TicketRepository()

    # Verificar que el ticket existe antes de aceptar la conexión
    ticket = ticket_repo.get_ticket(ticket_id)
    if not ticket:
        await websocket.close(code=4004)
        return

    await _connect(ticket_id, websocket)

    # Enviar evento de bienvenida con historial reciente
    try:
        messages = ticket_repo.list_messages(ticket_id)
        await websocket.send_text(json.dumps({
            "type":     "init",
            "ticket":   {
                "ticket_id": ticket["ticket_id"],
                "status":    ticket["status"],
                "category":  ticket["category"],
                "title":     ticket["title"],
            },
            "messages": messages[-20:],  # últimos 20 mensajes
        }, ensure_ascii=False, default=str))
    except Exception as exc:
        logger.error("Error sending init event: %s", exc)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "detail": "JSON inválido"}))
                continue

            msg_type = data.get("type", "message")

            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            if msg_type == "message":
                content     = (data.get("content") or "").strip()
                sender_type = data.get("sender_type", "user")
                sender_id   = data.get("sender_id")

                if not content:
                    continue

                # Guardar en DB
                try:
                    msg_id = ticket_repo.add_message(
                        ticket_id=ticket_id,
                        sender_type=sender_type,
                        sender_id=sender_id,
                        content=content,
                    )
                except Exception as db_err:
                    logger.error("Error saving WS message: %s", db_err)
                    await websocket.send_text(json.dumps({
                        "type": "error", "detail": "Error guardando mensaje"
                    }))
                    continue

                # Broadcast a todos los conectados
                broadcast_data = {
                    "type":        "message",
                    "message_id":  msg_id,
                    "ticket_id":   ticket_id,
                    "sender_type": sender_type,
                    "sender_id":   sender_id,
                    "content":     content,
                    "created_at":  datetime.now(timezone.utc).isoformat(),
                }
                await broadcast_to_ticket(ticket_id, broadcast_data)

            elif msg_type == "typing":
                # Notificar al otro lado que el usuario está escribiendo
                sender_type = data.get("sender_type", "user")
                await broadcast_to_ticket(ticket_id, {
                    "type":        "typing",
                    "sender_type": sender_type,
                })

    except WebSocketDisconnect:
        _disconnect(ticket_id, websocket)
        logger.debug("WS client disconnected: ticket=%s", ticket_id)
    except Exception as exc:
        logger.error("WS unexpected error (ticket=%s): %s", ticket_id, exc)
        _disconnect(ticket_id, websocket)
