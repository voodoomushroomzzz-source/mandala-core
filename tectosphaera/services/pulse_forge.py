import asyncio
from datetime import datetime

from fastapi import WebSocket

PULSE_INTERVAL = 30
ws_clients: list[WebSocket] = []


async def beat():
    while True:
        now = datetime.utcnow().isoformat()
        dead = []
        for ws in ws_clients:
            try:
                await ws.send_text(now)
            except Exception:
                dead.append(ws)
        for ws in dead:
            ws_clients.remove(ws)
        await asyncio.sleep(PULSE_INTERVAL)


async def register(ws: WebSocket):
    ws_clients.append(ws)


async def unregister(ws: WebSocket):
    if ws in ws_clients:
        ws_clients.remove(ws)


async def ws_handler(websocket: WebSocket):
    await websocket.accept()
    await register(websocket)
    try:
        while True:
            _ = await websocket.receive_text()
    except Exception:
        pass
    finally:
        await unregister(websocket)