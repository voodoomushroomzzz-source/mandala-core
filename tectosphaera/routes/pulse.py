"""Роуты для pulse-forge."""
from fastapi import APIRouter, WebSocket

from tectosphaera.services.pulse_forge import ws_handler

router = APIRouter(prefix="/pulse")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_handler(websocket)
