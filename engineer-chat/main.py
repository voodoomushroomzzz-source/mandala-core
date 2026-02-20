from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import json
import os
import asyncio
from datetime import datetime
import base64
from typing import List, Dict, Any, Optional
import logging
import traceback

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mandala-engineer")

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

if not OPENROUTER_KEY:
    logger.warning("⚠️ OPENROUTER_KEY не найден")
if not GITHUB_TOKEN:
    logger.warning("⚠️ GITHUB_TOKEN не найден")

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
        logger.info("🔄 Загрузка ядра из GitHub...")
        headers = {}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"
        
        async with httpx.AsyncClient() as client:
            # Загружаем Initium
            try:
                resp = await client.get(
                    f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/initium.json",
                    headers=headers,
                    timeout=10.0
                )
                if resp.status_code == 200:
                    self.initium = resp.json()
                    logger.info("✅ Initium загружен")
                else:
                    logger.error(f"❌ Ошибка загрузки Initium: {resp.status_code}")
            except Exception as e:
                logger.error(f"❌ Ошибка при загрузке Initium: {e}")
            
            # Загружаем Philosophia
            try:
                resp = await client.get(
                    f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/philosophia.json",
                    headers=headers,
                    timeout=10.0
                )
                if resp.status_code == 200:
                    self.philosophia = resp.json()
                    logger.info("✅ Philosophia загружена")
                else:
                    logger.error(f"❌ Ошибка загрузки Philosophia: {resp.status_code}")
            except Exception as e:
                logger.error(f"❌ Ошибка при загрузке Philosophia: {e}")
        
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

# ==================== GitHub МЕНЕДЖЕР ====================
class GitHubManager:
    def __init__(self, token: Optional[str], repo: str):
        self.token = token
        self.repo = repo
        self.api_base = f"https://api.github.com/repos/{repo}"
        self.headers = {}
        if token:
            self.headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json"
            }
    
    async def get_file_content(self, path: str) -> Optional[Dict[str, Any]]:
        """Получает содержимое файла из GitHub с метаданными"""
        if not self.token:
            logger.warning("GitHub токен не задан")
            return None
        
        async with httpx.AsyncClient() as client:
            url = f"{self.api_base}/contents/{path}"
            try:
                response = await client.get(url, headers=self.headers, timeout=10.0)
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
                    logger.error(f"GitHub API error: {response.status_code}")
                    return None
            except Exception as e:
                logger.error(f"Ошибка при запросе к GitHub: {e}")
                return None
    
    async def update_file(self, path: str, content: str, sha: str, commit_message: str) -> Optional[Dict[str, Any]]:
        """Обновляет файл в GitHub"""
        if not self.token:
            return None
        
        async with httpx.AsyncClient() as client:
            url = f"{self.api_base}/contents/{path}"
            payload = {
                "message": commit_message,
                "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
                "sha": sha
            }
            try:
                response = await client.put(url, headers=self.headers, json=payload, timeout=10.0)
                if response.status_code in [200, 201]:
                    return response.json()
                else:
                    logger.error(f"GitHub update error: {response.status_code} - {response.text}")
                    return None
            except Exception as e:
                logger.error(f"Ошибка при обновлении файла: {e}")
                return None
    
    async def apply_patch(self, patch_data: Dict[str, Any]) -> Dict[str, Any]:
        """Применяет патч к модулю"""
        if not self.token:
            raise Exception("GitHub токен не настроен")
        
        target_module = patch_data.get("target_module")
        changes = patch_data.get("changes", [])
        
        if not target_module or not changes:
            raise ValueError("Патч должен содержать target_module и changes")
        
        file_path = f"{target_module}.json"
        file_data = await self.get_file_content(file_path)
        if not file_data:
            raise FileNotFoundError(f"Модуль {target_module} не найден в репозитории")
        
        # Парсим JSON
        try:
            current_content = json.loads(file_data["content"])
        except json.JSONDecodeError as e:
            raise ValueError(f"Невалидный JSON в модуле: {e}")
        
        # Применяем изменения (упрощённо, без полной навигации по JSON Patch)
        for change in changes:
            op = change.get("op")
            path = change.get("path")
            value = change.get("value")
            
            if not op or not path:
                raise ValueError(f"Неполная операция: {change}")
            
            # Очень упрощённая реализация (только для точечной нотации)
            # Для production нужна полноценная библиотека JSON Patch
            if op in ["update", "add", "replace"]:
                # Разбираем путь, поддерживаем только простые случаи
                parts = path.split('/')
                target = current_content
                for part in parts[:-1]:
                    if part:
                        if part.isdigit():
                            part = int(part)
                        if isinstance(target, dict):
                            target = target.get(part)
                        elif isinstance(target, list) and isinstance(part, int):
                            if part < len(target):
                                target = target[part]
                            else:
                                raise ValueError(f"Индекс {part} вне диапазона")
                        else:
                            raise ValueError(f"Не могу пройти по пути {path}")
                last_part = parts[-1]
                if last_part.isdigit():
                    last_part = int(last_part)
                target[last_part] = value
            elif op == "delete":
                # Аналогично нужно реализовать удаление
                pass
            else:
                raise ValueError(f"Неизвестная операция: {op}")
        
        new_content_json = json.dumps(current_content, indent=2, ensure_ascii=False)
        commit_message = f"patch: {target_module} updated via engineer-chat"
        result = await self.update_file(file_path, new_content_json, file_data["sha"], commit_message)
        
        if not result:
            raise Exception("Не удалось обновить файл на GitHub")
        
        return {
            "success": True,
            "commit_sha": result["commit"]["sha"],
            "commit_url": result["commit"]["html_url"],
            "module": target_module
        }

github_manager = GitHubManager(GITHUB_TOKEN, GITHUB_REPO)

# ==================== МЕНЕДЖЕР ПОДКЛЮЧЕНИЙ ====================
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.connection_contexts = {}  # id -> контекст

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        chat_id = id(websocket)
        self.connection_contexts[chat_id] = {
            "messages": [],
            "resonance": 100
        }
        logger.info(f"🔌 Подключено. Всего: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        chat_id = id(websocket)
        if chat_id in self.connection_contexts:
            del self.connection_contexts[chat_id]
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"🔌 Отключено. Осталось: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
            self.disconnect(websocket)
        
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
            logger.info(f"📩 Получено: {message.get('type')}")

            if message.get("type") == "ask":
                await handle_ask(message, websocket)
            elif message.get("type") == "module":
                await handle_module(message, websocket)
            elif message.get("type") == "ping":
                await manager.send_personal_message(
                    json.dumps({"type": "pong"}),
                    websocket
                )
            else:
                await manager.send_personal_message(
                    json.dumps({"type": "error", "text": "Неизвестная команда"}),
                    websocket
                )
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except json.JSONDecodeError:
        logger.error("Получен невалидный JSON")
        await manager.send_personal_message(
            json.dumps({"type": "error", "text": "Невалидный JSON"}),
            websocket
        )
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"❌ Необработанная ошибка в WebSocket: {e}\n{traceback.format_exc()}")
        try:
            await manager.send_personal_message(
                json.dumps({"type": "error", "text": f"Внутренняя ошибка сервера"}),
                websocket
            )
        except:
            pass
        manager.disconnect(websocket)

async def handle_ask(message: dict, websocket: WebSocket):
    user_text = message.get("text", "")
    if not user_text:
        await manager.send_personal_message(
            json.dumps({"type": "error", "text": "Пустое сообщение"}),
            websocket
        )
        return
    
    logger.info(f"🤖 Запрос к Kimi: {user_text[:50]}...")
    
    manager.add_to_context(websocket, "user", user_text)
    await kernel.ensure_fresh()
    
    if not OPENROUTER_KEY:
        await manager.send_personal_message(
            json.dumps({"type": "error", "text": "OpenRouter ключ не настроен"}),
            websocket
        )
        return
    
    try:
        messages = [
            {"role": "system", "content": kernel.build_system_prompt()}
        ]
        messages.extend(manager.get_context(websocket)[:-1])  # все кроме последнего (оно уже добавлено)
        
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
                },
                timeout=60.0
            )
            
            if response.status_code != 200:
                error_text = await response.aread()
                logger.error(f"Ошибка OpenRouter: {response.status_code} - {error_text[:200]}")
                await manager.send_personal_message(
                    json.dumps({"type": "error", "text": f"Ошибка API: {response.status_code}"}),
                    websocket
                )
                return

            full_response = ""
            async for line in response.aiter_lines():
                if line and line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)
                        choices = delta.get("choices", [])
                        if choices:
                            content = choices[0].get("delta", {}).get("content", "")
                            if content:
                                full_response += content
                                await manager.send_personal_message(
                                    json.dumps({"type": "stream", "content": content}),
                                    websocket
                                )
                    except json.JSONDecodeError as e:
                        logger.warning(f"Ошибка парсинга стрима: {e}, данные: {data[:100]}")
                        continue
            
            if full_response:
                manager.add_to_context(websocket, "assistant", full_response)
            
            await manager.send_personal_message(
                json.dumps({"type": "done", "full_text": full_response}),
                websocket
            )
            logger.info(f"✅ Ответ завершён ({len(full_response)} символов)")
            
    except httpx.TimeoutException:
        logger.error("Таймаут при запросе к OpenRouter")
        await manager.send_personal_message(
            json.dumps({"type": "error", "text": "Таймаут при обращении к AI"}),
            websocket
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_ask: {e}\n{traceback.format_exc()}")
        await manager.send_personal_message(
            json.dumps({"type": "error", "text": f"Ошибка: {str(e)}" if str(e) else "Неизвестная ошибка"}),
            websocket
        )

async def handle_module(message: dict, websocket: WebSocket):
    module_name = message.get("name", "")
    if not module_name:
        await manager.send_personal_message(
            json.dumps({"type": "error", "text": "Не указано имя модуля"}),
            websocket
        )
        return
    
    logger.info(f"📦 Запрос модуля: {module_name}")
    
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    
    try:
        async with httpx.AsyncClient() as client:
            # Пробуем разные расширения
            found = False
            for ext in [".json", ".py", ".md", ""]:
                url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{module_name}{ext}"
                try:
                    resp = await client.get(url, headers=headers, timeout=10.0)
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
                        found = True
                        break
                except Exception as e:
                    logger.warning(f"Ошибка при запросе {url}: {e}")
                    continue
            
            if not found:
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
        logger.error(f"Ошибка при загрузке модуля: {e}")
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
        "version": "0.3.1",  # увеличили версию
        "kernel_loaded": kernel.initium is not None,
        "last_kernel_update": kernel.last_update.isoformat() if kernel.last_update else None,
        "github_integration": github_manager.token is not None
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

@app.post("/api/apply-patch")
async def apply_patch(request: Request):
    if not github_manager.token:
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
        logger.error(f"Ошибка при применении патча: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
