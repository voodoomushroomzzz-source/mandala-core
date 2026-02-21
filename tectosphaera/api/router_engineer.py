import asyncio
import json
import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tectosphaera.services.github_client import GitHubClient
from tectosphaera.services.websocket_manager import WebSocketManager

logger = logging.getLogger("engineer-chat")
router = APIRouter(prefix="/engineer")

manager = WebSocketManager()
github = GitHubClient(
    token=os.getenv("GITHUB_TOKEN"),
    repo=os.getenv("GITHUB_REPO", "voodoomushroomzzz-source/mandala-core"),
)


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            msg: Dict[str, Any] = json.loads(raw)
            await route_message(msg, ws)
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        logger.exception("Engineer WS error")
        await manager.send_to(ws, {"type": "error", "text": str(e)})


async def route_message(msg: Dict[str, Any], ws: WebSocket):
    """Маршрутизировать сообщение по типу."""
    msg_type = msg.get("type")
    if msg_type == "get_file":
        path = msg.get("path", "")
        async with github:
            content = await github.get_file(path)
        await manager.send_to(ws, {"type": "file", "path": path, "content": content})
    else:
        await manager.send_to(ws, {"type": "echo", "text": json.dumps(msg, ensure_ascii=False)})