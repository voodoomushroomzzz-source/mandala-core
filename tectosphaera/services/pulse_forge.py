"""Сервис 'pulse-forge' — фоновая метка каждые 30 с + WebSocket broadcast."""
import asyncio
import time
from datetime import datetime
from typing import List
import logging
from fastapi import WebSocket
from akasha_chronicorum import push_event  # импорт из ядра

logger = logging.getLogger("pulse-forge")

PULSE_INTERVAL = 30
ws_clients: List[WebSocket] = []

async def beat():
    """Бесконечный цикл: пишем метку и рассылаем подписчикам."""
    counter = 0
    while True:
        counter += 1
        ts = datetime.utcnow().isoformat()
        payload = {"n": counter, "ts": ts, "source": "pulse-forge"}
        # 1) в Akasha
        await push_event(topic="pulse-forge", data=payload)
        # 2) в WebSocket
        dead = []
        for ws in ws_clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for d in dead:
            ws_clients.remove(d)
        await asyncio.sleep(PULSE_INTERVAL)

def start_pulse_task():
    asyncio.create_task(beat())

async def ws_handler(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)
    try:
        while True:
            _ = await websocket.receive_text()  # keep-alive
    except Exception:
        pass
    finally:
        ws_clients.remove(websocket)
