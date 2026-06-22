"""Live room websocket: WebRTC signaling + automated attendance capture.

This is where attendance becomes *automatic*. Every client that joins a room
opens a websocket here. The server:

  * logs a `join` PresenceEvent on connect,
  * logs periodic `heartbeat` events (so crashes don't inflate attendance),
  * logs a `leave` PresenceEvent on disconnect,
  * relays WebRTC SDP/ICE between peers so audio/video flows,
  * notifies the coordinator dashboard of every membership change.

No human marks a register — the attendance engine derives it from this log for
all sessions, including all 100 running at once.

Auth: the client passes its JWT as the `token` query param (browsers can't set
headers on WebSocket). The room is identified by `room_id`.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.realtime import hub
from app.core.security import decode_access_token
from app.database import SessionLocal
from app.models import (
    CourseSession,
    PresenceEvent,
    PresenceEventType,
    SessionStatus,
    User,
)

router = APIRouter(tags=["rooms"])


def _log_event(session_id: int, user_id: int, event_type: PresenceEventType) -> None:
    db = SessionLocal()
    try:
        db.add(
            PresenceEvent(
                session_id=session_id,
                user_id=user_id,
                event_type=event_type,
                at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    finally:
        db.close()


def _resolve(token: str, room_id: str) -> tuple[User, CourseSession] | None:
    db = SessionLocal()
    try:
        payload = decode_access_token(token)
        user = db.get(User, int(payload["sub"]))
        session = db.execute(
            select(CourseSession).where(CourseSession.room_id == room_id)
        ).scalar_one_or_none()
        if not user or not session:
            return None
        return user, session
    except Exception:
        return None
    finally:
        db.close()


async def _push_dashboard(room_id: str) -> None:
    await hub.broadcast_dashboard(
        {"type": "presence", "room_id": room_id, "live_now": hub.room_size(room_id)}
    )


@router.websocket("/ws/rooms/{room_id}")
async def room_ws(websocket: WebSocket, room_id: str, token: str = Query(...)):
    resolved = _resolve(token, room_id)
    if resolved is None:
        await websocket.close(code=4401)
        return
    user, session = resolved

    if session.status != SessionStatus.live:
        await websocket.close(code=4403)  # room not open
        return

    await websocket.accept()
    peers = await hub.join_room(room_id, user.id, websocket)
    _log_event(session.id, user.id, PresenceEventType.join)
    await _push_dashboard(room_id)

    # Tell the newcomer who's already here so it can initiate WebRTC offers.
    await websocket.send_json({"type": "peers", "peers": peers, "self_id": user.id})
    # Tell existing peers a newcomer arrived.
    await hub.relay_to_room(room_id, user.id, {"type": "peer-joined", "peer_id": user.id})

    try:
        while True:
            msg = await websocket.receive_json()
            mtype = msg.get("type")

            if mtype == "heartbeat":
                _log_event(session.id, user.id, PresenceEventType.heartbeat)
            elif mtype in ("offer", "answer", "ice-candidate"):
                # WebRTC signaling — forward to the targeted peer.
                msg["from"] = user.id
                await hub.relay_to_room(room_id, user.id, msg, target_id=msg.get("target"))
            elif mtype == "chat":
                await hub.relay_to_room(
                    room_id, user.id, {"type": "chat", "from": user.id, "text": msg.get("text", "")}
                )
    except WebSocketDisconnect:
        pass
    finally:
        await hub.leave_room(room_id, user.id)
        _log_event(session.id, user.id, PresenceEventType.leave)
        await hub.relay_to_room(room_id, user.id, {"type": "peer-left", "peer_id": user.id})
        await _push_dashboard(room_id)
