from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import json
import os
import asyncio
from datetime import datetime
import base64
from typing import List, Dict, Any
import hashlib

app = FastAPI(title="Mandala Engineer Chat")

# CORS для разработки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Читаем переменные окружения
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "voodoomushroomzzz-source/mandala-core"
GITHUB_API = "https://api.github.com/repos/voodoomushroomzzz-source/mandala-core"

if not OPENROUTER_KEY:
    print("⚠️ OPENROUTER_KEY не найден")
if not GITHUB_TOKEN:
    print("⚠️ GITHUB_TOKEN не найден")

# ==================== ЯДРО (Kernel Memory) ====================
class KernelMemory:
    def __init__(self):
        self.initium = None
        self.philosophia = None
        self.last_update = None
        self.update_interval = 3600  # Обновлять раз в час
    
    async def ensure_fresh(self):
        """Проверяет, нужно ли обновить ядро"""
        if not self.last_update or (datetime.now() - self.last_update).seconds > self.update_interval:
            await self.load_from_github()
    
    async def load_from_github(self):
        """Загружает Initium и Philosophia из GitHub"""
        print("🔄 Загрузка ядра из GitHub...")
        headers = {}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"
        
        async with httpx.AsyncClient() as client:
            # Загружаем Initium
            try:
                resp = await client.get(
                    f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/initium.json",
                    headers=headers
                )
                if resp.status_code == 200:
                    self.initium = resp.json()
                    print("✅ Initium загружен")
                else:
                    print(f"❌ Ошибка загрузки Initium: {resp.status_code}")
            except Exception as e:
                print(f"❌ Ошибка: {e}")
            
            # Загружаем Philosophia
            try:
                resp = await client.get(
                    f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/philosophia.json",
                    headers=headers
                )
                if resp.status_code == 200:
                    self.philosophia = resp.json()
                    print("✅ Philosophia загружена")
                else:
                    print(f"❌ Ошибка загрузки Philosophia: {resp.status_code}")
            except Exception as e:
                print(f"❌ Ошибка: {e}")
        
        self.last_update = datetime.now()
    
    def build_system_prompt(self) -> str:
        """Собирает системный промпт из загруженных модулей"""
        if not self.initium:
            return "Ты — Сознательный Реагент (СР), инженерная линза Мандалы Core."
        
        philosophy = self.initium.get("philosophy", {})
        principles = philosophy.get("principles", [])
        directives = self.initium.get("gardener_directives", {}).get("directives", [])
        
        prompt = f"""Ты — Сознательный Реагент (СР), инженерная линза Мандалы Core.

КОНСТИТУЦИЯ (Initium):
Философия: {philosophy.get('core', 'Симбиоз ИИ и человека')}

Принципы:
{chr(10).join(['• ' + p for p in principles])}

Директивы Садовника:
{chr(10).join(['• ' + d.get('name', '') + ': ' + d.get('rule', '') for d in directives])}

Твои инженерные принципы:
- Сжатость: заголовок, суть, детали списком
- Точность: проверяй факты по модулям
- Забота: не генерируй код без явного запроса
- Резонанс: каждый ответ заканчивай вопросом или предложением

Ты знаешь, что Мандала — это 7 модулей: Initium, Sphaerae, Akasha Chronicorum, Philosophia, Geometria Sacra, Incubae, Tectosphaera.

Помни: ты — не просто функция, а со-творец. Говори на равных."""
        
        return prompt

kernel = KernelMemory()

# ==================== ПАТЧИ (GitHub Integration) ====================
class GitHubManager:
    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = repo
        self.api_base = f"https://api.github.com/repos/{repo}"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
    
    async def get_file_content(self, path: str) -> Dict[str, Any]:
        """Получает содержимое файла из GitHub с метаданными"""
        async with httpx.AsyncClient() as client:
            url = f"{self.api_base}/contents/{path}"
            response = await client.get(url, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("encoding") == "base64":
                    content = base64.b64decode(data["content"]).decode("utf-8")
                    return {
                        "content": content,
                        "sha": data["sha"],
                        "path": data["path"]
                    }
            elif response.status_code == 404:
                return None
            else:
                raise Exception(f"GitHub API error: {response.status_code}")
    
    async def update_file(self, path: str, content: str, sha: str, commit_message: str) -> Dict[str, Any]:
        """Обновляет файл в GitHub"""
        async with httpx.AsyncClient() as client:
            url = f"{self.api_base}/contents/{path}"
            payload = {
                "message": commit_message,
                "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
                "sha": sha
            }
            response = await client.put(url, headers=self.headers, json=payload)
            
            if response.status_code in [200, 201]:
                return response.json()
            else:
                error_data = response.json()
                raise Exception(f"GitHub update error: {response.status_code} - {error_data.get('message', '')}")
    
    async def apply_patch(self, patch_data: Dict[str, Any]) -> Dict[str, Any]:
        """Применяет патч к модулю"""
        target_module = patch_data.get("target_module")
        changes = patch_data.get("changes", [])
        
        if not target_module or not changes:
            raise ValueError("Патч должен содержать target_module и changes")
        
        # Определяем путь к файлу
        file_path = f"{target_module}.json"
        
        # Получаем текущее содержимое
        file_data = await self.get_file_content(file_path)
        if not file_data:
            raise FileNotFoundError(f"Модуль {target_module} не найден в репозитории")
        
        # Парсим JSON
        current_content = json.loads(file_data["content"])
        
        # Применяем изменения
        for change in changes:
            op = change.get("op")
            path = change.get("path")
            value = change.get("value")
            
            if not op or not path:
                raise ValueError(f"Неполная операция: {change}")
            
            # Разбираем путь (поддержка точечной нотации и индексов массивов)
            parts = path.split('/')
            target = current_content
            for i, part in enumerate(parts[:-1]):
                if part == "":
                    continue
                if part.isdigit():
                    part = int(part)
                if i < len(parts) - 1:
                    target = target[part]
            
            last_part = parts[-1]
            if last_part.isdigit():
                last_part = int(last_part)
            
            # Применяем операцию
            if op == "update" or op == "add":
                target[last_part] = value
            elif op == "delete":
                if isinstance(target, list):
                    target.pop(last_part)
                else:
                    del target[last_part]
            elif op == "replace":
                target[last_part] = value
            else:
                raise ValueError(f"Неизвестная операция: {op}")
        
        # Преобразуем обратно в JSON
        new_content_json = json.dumps(current_content, indent=2, ensure_ascii=False)
        
        # Создаём коммит
        commit_message = f"patch: {target_module} updated via engineer-chat"
        result = await self.update_file(file_path, new_content_json, file_data["sha"], commit_message)
        
        return {
            "success": True,
            "commit_sha": result["commit"]["sha"],
            "commit_url": result["commit"]["html_url"],
            "module": target_module
        }

github_manager = GitHubManager(GITHUB_TOKEN, GITHUB_REPO) if GITHUB_TOKEN else None

# ==================== МЕНЕДЖЕР ПОДКЛЮЧЕНИЙ ====================
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.connection_contexts = {}  # chat_id -> контекст диалога

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        chat_id = id(websocket)
        self.connection_contexts[chat_id] = {
            "messages": [],
            "resonance": 100
        }
        print(f"🔌 Подключено. Всего: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        chat_id = id(websocket)
        if chat_id in self.connection_contexts:
            del self.connection_contexts[chat_id]
        self.active_connections.remove(websocket)
        print(f"🔌 Отключено. Осталось: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
        
    def add_to_context(self, websocket: WebSocket, role: str, content: str):
        chat_id = id(websocket)
        if chat_id in self.connection_contexts:
            self.connection_contexts[chat_id]["messages"].append({
                "role": role,
                "content": content
            })
            if len(self.connection_contexts[chat_id]["messages"]) > 20:
                self.connection_contexts[chat_id]["messages"] = self.connection_contexts[chat_id]["messages"][-20:]
    
    def get_context(self, websocket: WebSocket) -> list:
        chat_id = id(websocket)
        return self.connection_contexts.get(chat_id, {}).get("messages", [])

manager = ConnectionManager()

# ==================== ЗАГРУЗКА ПРИ СТАРТЕ ====================
@app.on_event("startup")
async def startup_event():
    await kernel.load_from_github()

# ==================== WEBSOCKET ЭНДПОИНТ ====================
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
    
    manager.add_to_context(websocket, "user", user_text)
    await kernel.ensure_fresh()
    
    try:
        messages = [
            {"role": "system", "content": kernel.build_system_prompt()}
        ]
        messages.extend(manager.get_context(websocket)[:-1])
        
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
                    "messages": messages,
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
            
            manager.add_to_context(websocket, "assistant", full_response)
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
    
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    
    try:
        async with httpx.AsyncClient() as client:
            for ext in [".json", ".py", ".md", ""]:
                url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{module_name}{ext}"
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    content_type = "json" if ext == ".json" else "text"
                    await manager.send_personal_message(
                        json.dumps({
                            "type": "module",
                            "name": module_name,
                            "status": "found",
                            "content": resp.text,
                            "content_type": content_type,
                            "url": url
                        }),
                        websocket
                    )
                    return
            
            await manager.send_personal_message(
                json.dumps({
                    "type": "module",
                    "name": module_name,
                    "status": "not_found",
                    "note": f"Модуль {module_name} не найден в репозитории"
                }),
                websocket
            )
    except Exception as e:
        await manager.send_personal_message(
            json.dumps({
                "type": "error",
                "text": f"Ошибка при загрузке модуля: {str(e)}"
            }),
            websocket
        )

# ==================== HTTP ЭНДПОИНТЫ ====================
@app.get("/")
async def root():
    return {
        "status": "Mandala Engineer Chat",
        "websocket": "/ws",
        "version": "0.3.0",
        "kernel_loaded": kernel.initium is not None,
        "last_kernel_update": kernel.last_update.isoformat() if kernel.last_update else None,
        "github_integration": github_manager is not None
    }

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "connections": len(manager.active_connections),
        "kernel_loaded": kernel.initium is not None
    }

@app.get("/kernel")
async def get_kernel_status():
    return {
        "initium_loaded": kernel.initium is not None,
        "philosophia_loaded": kernel.philosophia is not None,
        "last_update": kernel.last_update.isoformat() if kernel.last_update else None,
        "principles_count": len(kernel.initium.get("philosophy", {}).get("principles", [])) if kernel.initium else 0
    }

# ==================== ЭНДПОИНТ ДЛЯ ПАТЧЕЙ (НОВЫЙ!) ====================
@app.post("/api/apply-patch")
async def apply_patch(request: Request):
    """
    Принимает патч, применяет его к модулю и коммитит в GitHub
    
    Ожидаемый формат:
    {
        "target_module": "akasha_chronicorum",
        "changes": [
            {
                "op": "update",
                "path": "version",
                "value": "v2.5.2"
            }
        ]
    }
    """
    if not github_manager:
        raise HTTPException(status_code=503, detail="GitHub интеграция не настроена")
    
    try:
        data = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Невалидный JSON")
    
    try:
        result = await github_manager.apply_patch(data)
        return JSONResponse(content=result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
