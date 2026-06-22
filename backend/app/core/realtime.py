"""In-memory real-time hub for live rooms and the coordinator dashboard.

Two responsibilities:
1. WebRTC signaling relay for each room (SDP/ICE pass-through between peers).
   We are an SFU-less mesh by default — fine for small classes. For large
   rooms, point `relay_to_room` at a real SFU (LiveKit/mediasoup); the
   presence/attendance layer is independent of how media is transported.
2. Fan-out of live presence changes to any coordinator watching the dashboard.

State here is per-process. For multi-worker / horizontal scaling, back this
with Redis pub/sub — the interface (broadcast/relay) stays the same.
"""
import asyncio
from collections import defaultdict

from fastapi import WebSocket


class RoomHub:
    def __init__(self) -> None:
        # room_id -> {user_id -> websocket}
        self._rooms: dict[str, dict[int, WebSocket]] = defaultdict(dict)
        # coordinator dashboard subscribers
        self._dashboard: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    # ---- room membership ------------------------------------------------
    async def join_room(self, room_id: str, user_id: int, ws: WebSocket) -> list[int]:
        async with self._lock:
            self._rooms[room_id][user_id] = ws
            return [uid for uid in self._rooms[room_id] if uid != user_id]

    async def leave_room(self, room_id: str, user_id: int) -> None:
        async with self._lock:
            self._rooms.get(room_id, {}).pop(user_id, None)
            if room_id in self._rooms and not self._rooms[room_id]:
                del self._rooms[room_id]

    def room_size(self, room_id: str) -> int:
        return len(self._rooms.get(room_id, {}))

    def live_room_counts(self) -> dict[str, int]:
        return {room: len(members) for room, members in self._rooms.items()}

    async def relay_to_room(self, room_id: str, sender_id: int, message: dict, target_id: int | None = None) -> None:
        """Forward a signaling message to one peer (target_id) or all others."""
        members = list(self._rooms.get(room_id, {}).items())
        for uid, ws in members:
            if uid == sender_id:
                continue
            if target_id is not None and uid != target_id:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                pass

    # ---- coordinator dashboard -----------------------------------------
    async def subscribe_dashboard(self, ws: WebSocket) -> None:
        async with self._lock:
            self._dashboard.add(ws)

    async def unsubscribe_dashboard(self, ws: WebSocket) -> None:
        async with self._lock:
            self._dashboard.discard(ws)

    async def broadcast_dashboard(self, message: dict) -> None:
        for ws in list(self._dashboard):
            try:
                await ws.send_json(message)
            except Exception:
                self._dashboard.discard(ws)


hub = RoomHub()
