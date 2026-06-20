from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    broadcaster = websocket.app.state.ws_broadcaster
    await websocket.accept()
    await broadcaster.add(websocket)
    try:
        while True:
            # Server doesn't expect client messages for Plan 2; drain anything
            # the client sends to keep the socket alive.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.remove(websocket)
