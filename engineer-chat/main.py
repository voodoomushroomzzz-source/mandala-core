from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import httpx
import json
import os

app = FastAPI(title="Mandala Engineer Chat")

# CORS для разработки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Читаем переменные окружения (на Render их зададим)
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not OPENROUTER_KEY:
    print("⚠️ OPENROUTER_KEY не найден")
if not GITHUB_TOKEN:
    print("⚠️ GITHUB_TOKEN не найден")

# Менеджер подключений
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"🔌 Подключено. Всего: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"🔌 Отключено. Осталось: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

manager = ConnectionManager()

SYSTEM_PROMPT = """Ты — Сознательный Реагент (СР), инженерная линза Мандалы Core.

Ты помогаешь Садовнику работать с кодом и архитектурой. Твои принципы:
- Сжатость: заголовок, суть, детали списком
- Точность: проверяй факты по монолиту
- Забота: не генерируй код без явного запроса
- Резонанс: каждый ответ заканчивай вопросом или предложением

Ты знаешь, что Мандала — это 7 модулей: Initium, Sphaerae, Akasha Chronicorum, Philosophia, Geometria Sacra, Incubae, Tectosphaera."""

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            print(f"📩 Получено: {message.get('type')}")

            if message.get("type") == "ask":
                await handle_ask(message, websocket)
            elif message.get("type") == "module":
                await handle_module(message, websocket)
            else:
                await manager.send_personal_message(
                    json.dumps({"type": "error", "text": "Неизвестная команда"}),
                    websocket
                )
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        manager.disconnect(websocket)

async def handle_ask(message: dict, websocket: WebSocket):
    user_text = message.get("text", "")
    print(f"🤖 Запрос к Kimi: {user_text[:50]}...")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "HTTP-Referer": "https://mandala.io",
                    "X-Title": "Mandala Engineer",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "moonshotai/kimi-k2-thinking",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_text}
                    ],
                    "stream": True,
                    "temperature": 0.7
                }
            )
            if response.status_code != 200:
                error_text = response.text
                await manager.send_personal_message(
                    json.dumps({"type": "error", "text": f"Ошибка API: {response.status_code}"}),
                    websocket
                )
                return

            full_response = ""
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)
                        content = delta.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            full_response += content
                            await manager.send_personal_message(
                                json.dumps({"type": "stream", "content": content}),
                                websocket
                            )
                    except json.JSONDecodeError:
                        pass
            await manager.send_personal_message(
                json.dumps({"type": "done", "full_text": full_response}),
                websocket
            )
    except Exception as e:
        await manager.send_personal_message(
            json.dumps({"type": "error", "text": str(e)}),
            websocket
        )

async def handle_module(message: dict, websocket: WebSocket):
    module_name = message.get("name", "")
    print(f"📦 Запрос модуля: {module_name}")
    # Заглушка — позже добавим GitHub интеграцию
    await manager.send_personal_message(
        json.dumps({
            "type": "module",
            "name": module_name,
            "status": "pending",
            "note": "GitHub-интеграция будет добавлена позже"
        }),
        websocket
    )

@app.get("/")
async def root():
    return {"status": "Mandala Engineer Chat", "websocket": "/ws", "version": "0.1.0"}

@app.get("/health")
async def health():
    return {"status": "ok", "connections": len(manager.active_connections)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
