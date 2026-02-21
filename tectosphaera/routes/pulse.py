"""Роуты для pulse-forge."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from tectosphaera.services.pulse_forge import ws_handler, start_pulse_task

router = APIRouter(prefix="/pulse")

@router.on_event("startup")
async def startup_pulse():
    start_pulse_task()

@router.websocket("/ws")
async def websocket_pulse(websocket: WebSocket):
    await ws_handler(websocket)
