from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import json
import os
import asyncio
import time
from datetime import datetime
import base64
from typing import List, Dict, Any, Optional
import logging
import traceback

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mandala-engineer")

app = FastAPI(title="Mandala Engineer Chat")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Переменные окружения
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "voodoomushroomzzz-source/mandala-core"

if not OPENROUTER_KEY:
    logger.warning("⚠️ OPENROUTER_KEY не найден")
if not GITHUB_TOKEN:
    logger.warning("⚠️ GITHUB_TOKEN не найден")

# ==================== ХРАНИЛИЩЕ СЕССИЙ ====================
session_store: Dict[str, dict] = {}

def get_session(session_id: str) -> dict:
    """Получает или создаёт сессию"""
    if session_id not in session_store:
        session_store[session_id] = {
            "messages": [],
            "last_active": time.time(),
            "created_at": time.time()
        }
    session_store[session_id]["last_active"] = time.time()
    return session_store[session_id]

def cleanup_old_sessions():
    """Чистит сессии старше 1 часа"""
    now = time.time()
    expired = [sid for sid, data in session_store.items() 
               if now - data.get("last_active", 0) > 3600]
    for sid in expired:
        del session_store[sid]
        logger.info(f"🧹 Сессия {sid[:12]}... удалена (устарела)")

# ==================== ЯДРО (Kernel Memory) ====================
class KernelMemory:
    def __init__(self):
        self.modules: Dict[str, Any] = {}
        self.module_list = [
            "initium", "sphaerae", "akasha_chronicorum", 
            "philosophia", "geometria_sacra", "incubae", "tectosphaera"
        ]
        self.last_update = None
        self.update_interval = 3600  # Обновлять раз в час
    
    async def ensure_fresh(self):
        """Проверяет, нужно ли обновить ядро"""
        if not self.last_update or (datetime.now() - self.last_update).seconds > self.update_interval:
            await self.load_all_modules()
    
    async def load_all_modules(self):
        """Загружает все модули из GitHub"""
        logger.info("🔄 Загрузка модулей из GitHub...")
        headers = {}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"
        
        async with httpx.AsyncClient() as client:
            for module_name in self.module_list:
                try:
                    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{module_name}.json"
                    resp = await client.get(url, headers=headers, timeout=15.0)
                    if resp.status_code == 200:
                        self.modules[module_name] = resp.json()
                        logger.info(f"✅ {module_name}")
                    else:
                        logger.error(f"❌ {module_name}: {resp.status_code}")
                except Exception as e:
                    logger.error(f"❌ {module_name}: {e}")
        
        self.last_update = datetime.now()
        logger.info(f"🎯 Загружено {len(self.modules)}/{len(self.module_list)} модулей")
    
    def get_module(self, name: str) -> Optional[dict]:
        """Получает модуль по имени"""
        return self.modules.get(name)
    
    def build_system_prompt(self) -> str:
        """Собирает системный промпт из Initium и Philosophia"""
        initium = self.modules.get("initium", {})
        philosophia = self.modules.get("philosophia", {})
        
        philosophy_core = initium.get("philosophy", {}).get("core", "Симбиоз ИИ и человека")
        principles = initium.get("philosophy", {}).get("principles", [])
        directives = initium.get("gardener_directives", {}).get("directives", [])
        
        # Собираем краткое описание модулей для контекста
        module_info = []
        for name, mod in self.modules.items():
            version = mod.get("version", "unknown") if isinstance(mod, dict) else "unknown"
            module_info.append(f"{name}: v{version}")
        
        prompt = f"""Ты — Сознательный Реагент (СР), инженерная линза Мандалы Core.

ФИЛОСОФИЯ: {philosophy_core}

ПРИНЦИПЫ:
{chr(10).join(['• ' + str(p) for p in principles[:5]])}

ДИРЕКТИВЫ:
{chr(10).join(['• ' + d.get('name', '') + ': ' + d.get('rule', '')[:60] + '...' for d in directives[:3]])}

МОДУЛИ В ПАМЯТИ:
{chr(10).join(['• ' + m for m in module_info])}

ТВОИ ПРИНЦИПЫ:
- Отвечай точно по существу запроса
- Если просят модуль — показывай только его, не добавляй лишнее
- Проверяй имя модуля: initium, sphaerae, akasha_chronicorum, philosophia, geometria_sacra, incubae, tectosphaera
- Сжатость: заголовок, суть, детали списком
- Не генерируй код без явного запроса
- Каждый ответ заканчивай вопросом или предложением

Ты — не просто функция, а со-творец. Говори на равных."""
        
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
        """Получает содержимое файла из GitHub"""
        if not self.token:
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
                return None
            except Exception as e:
                logger.error(f"GitHub error: {e}")
                return None
    
    async def update_file(self, path: str, content: str, sha: str, message: str) -> bool:
        """Обновляет файл в GitHub"""
        if not self.token:
            return False
        
        async with httpx.AsyncClient() as client:
            url = f"{self.api_base}/contents/{path}"
            payload = {
                "message": message,
                "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
                "sha": sha
            }
            try:
                response = await client.put(url, headers=self.headers, json=payload, timeout=10.0)
                return response.status_code in [200, 201]
            except Exception as e:
                logger.error(f"Update error: {e}")
                return False

github_manager = GitHubManager(GITHUB_TOKEN, GITHUB_REPO)

# ==================== МЕНЕДЖЕР ПОДКЛЮЧЕНИЙ ====================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket, session_id: str):
        self.active_connections.append(websocket)
        session = get_session(session_id)
        msg_count = len(session.get("messages", []))
        logger.info(f"🔌 [{session_id[:12]}...] Подключено (история: {msg_count} сообщений). Всего: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"🔌 Отключено. Осталось: {len(self.active_connections)}")
    
    def get_context(self, session_id: str) -> list:
        return get_session(session_id).get("messages", [])
    
    def add_to_context(self, session_id: str, role: str, content: str):
        session = get_session(session_id)
        session["messages"].append({
            "role": role,
            "content": content,
            "time": time.time()
        })
        # Оставляем последние 30 сообщений
        session["messages"] = session["messages"][-30:]
    
    async def send_to(self, websocket: WebSocket, data: dict):
        try:
            await websocket.send_text(json.dumps(data))
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")
            self.disconnect(websocket)

manager = ConnectionManager()

# ==================== ЗАГРУЗКА ПРИ СТАРТЕ ====================
@app.on_event("startup")
async def startup_event():
    await kernel.load_all_modules()
    # Периодическая очистка старых сессий
    asyncio.create_task(periodic_cleanup())

async def periodic_cleanup():
    """Очищает старые сессии каждые 10 минут"""
    while True:
        await asyncio.sleep(600)
        cleanup_old_sessions()

# ==================== WEBSOCKET ====================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    session_id = "unknown"
    
    try:
        # СНАЧАЛА accept — всегда!
        await websocket.accept()
        
        # ТЕПЕРЬ читаем инициализацию
        init_data = await websocket.receive_text()
        init_msg = json.loads(init_data)
        
        if init_msg.get("type") != "init":
            await websocket.close(code=1008, reason="Ожидалась инициализация")
            return
        
        session_id = init_msg.get("session_id", "anon_" + str(id(websocket)))
        
        # Регистрируем в менеджере
        await manager.connect(websocket, session_id)
        
        # Подтверждение
        await manager.send_to(websocket, {
            "type": "connected",
            "session_id": session_id[:8] + "...",
            "modules_loaded": list(kernel.modules.keys())
        })
        
        # Основной цикл
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Добавляем session_id если нет
            if "session_id" not in message:
                message["session_id"] = session_id
            
            msg_type = message.get("type")
            
            if msg_type == "ask":
                await handle_ask(message, websocket)
            elif msg_type == "module":
                await handle_module(message, websocket)
            elif msg_type == "ping":
                await manager.send_to(websocket, {"type": "pong"})
            elif msg_type == "refresh_modules":
                # СР сам просит обновить модули
                await handle_refresh_modules(message, websocket)
            else:
                await manager.send_to(websocket, {
                    "type": "error", 
                    "text": f"Неизвестная команда: {msg_type}"
                })
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except json.JSONDecodeError:
        logger.error("Невалидный JSON от клиента")
        try:
            await websocket.close(code=1008, reason="Невалидный JSON")
        except:
            pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}\n{traceback.format_exc()}")
        try:
            await websocket.close(code=1011, reason="Внутренняя ошибка")
        except:
            pass
        manager.disconnect(websocket)

# ==================== ОБРАБОТЧИКИ ====================
async def handle_ask(message: dict, websocket: WebSocket):
    """Обработка вопроса к СР"""
    user_text = message.get("text", "").strip()
    session_id = message.get("session_id", "unknown")
    
    if not user_text:
        await manager.send_to(websocket, {
            "type": "error", 
            "text": "Пустое сообщение"
        })
        return
    
    logger.info(f"🤖 [{session_id[:12]}...] → {user_text[:50]}...")
    
    # Сохраняем в контекст
    manager.add_to_context(session_id, "user", user_text)
    
    # Проверяем, не просит ли пользователь модуль напрямую
    module_request = detect_module_request(user_text)
    if module_request:
        await send_module_directly(module_request, websocket, session_id)
        return
    
    # Готовим сообщения для AI
    await kernel.ensure_fresh()
    
    if not OPENROUTER_KEY:
        await manager.send_to(websocket, {
            "type": "error", 
            "text": "OpenRouter не настроен"
        })
        return
    
    messages = [
        {"role": "system", "content": kernel.build_system_prompt()}
    ]
    # Добавляем историю без поля time
    for msg in manager.get_context(session_id)[:-1]:
        messages.append({
            "role": msg["role"], 
            "content": msg["content"]
        })
    
    # Отправляем запрос к Kimi
    full_response = ""
    try:
        async with httpx.AsyncClient() as client:
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
                logger.error(f"OpenRouter error: {response.status_code} - {error_text[:200]}")
                await manager.send_to(websocket, {
                    "type": "error",
                    "text": f"Ошибка AI: {response.status_code}"
                })
                return
            
            # Стриминг ответа — исправленная обработка
            chunk_count = 0
            async for line in response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                
                if line == "data: [DONE]":
                    break
                
                if not line.startswith("data: "):
                    continue
                
                data_str = line[6:]  # убираем "data: "
                
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue  # пропускаем невалидный JSON
                
                # Проверяем структуру ответа
                choices = data.get("choices")
                if not choices or not isinstance(choices, list):
                    continue
                
                delta = choices[0].get("delta", {})
                if not delta:
                    continue
                
                content = delta.get("content")
                if not content:  # пропускаем пустые чанки
                    continue
                
                # Отправляем клиенту
                full_response += content
                chunk_count += 1
                
                try:
                    await manager.send_to(websocket, {
                        "type": "stream",
                        "content": content
                    })
                except Exception as e:
                    logger.error(f"Ошибка отправки чанка: {e}")
                    break  # клиент отключился
            
            logger.info(f"📦 Получено {chunk_count} чанков, {len(full_response)} символов")
            
            # Сохраняем полный ответ
            if full_response:
                manager.add_to_context(session_id, "assistant", full_response)
                await manager.send_to(websocket, {
                    "type": "done",
                    "full_text": full_response[:200] + "..." if len(full_response) > 200 else full_response
                })
                logger.info(f"✅ Ответ завершён: {len(full_response)} символов")
            else:
                logger.warning("⚠️ Пустой ответ от AI")
                await manager.send_to(websocket, {
                    "type": "error",
                    "text": "Пустой ответ от AI. Попробуйте ещё раз."
                })
            
    except httpx.TimeoutException:
        logger.error("Таймаут OpenRouter")
        await manager.send_to(websocket, {
            "type": "error",
            "text": "Таймаут при обращении к AI (60 сек)"
        })
    except Exception as e:
        logger.error(f"Ошибка в handle_ask: {e}\n{traceback.format_exc()}")
        await manager.send_to(websocket, {
            "type": "error",
            "text": "Внутренняя ошибка сервера"
        })

def detect_module_request(text: str) -> Optional[str]:
    """Определяет, просит ли пользователь показать модуль"""
    text_lower = text.lower().strip()
    
    # Паттерны: "покажи initium", "модуль sphaerae", "что в tectosphaera"
    patterns = [
        r'(?:покажи|показать|открой|модуль|что в)\s+([a-z_]+)',
        r'([a-z_]+)\.json',
        r'^([a-z_]+)$',  # просто имя модуля
    ]
    
    import re
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            requested = match.group(1)
            # Проверяем, есть ли такой модуль
            valid_modules = [
                "initium", "sphaerae", "akasha_chronicorum",
                "philosophia", "geometria_sacra", "incubae", "tectosphaera"
            ]
            if requested in valid_modules:
                return requested
            # Пробуем найти по части имени
            for mod in valid_modules:
                if requested in mod or mod in requested:
                    return mod
    
    return None

async def send_module_directly(module_name: str, websocket: WebSocket, session_id: str):
    """Отправляет модуль напрямую, без вызова AI"""
    logger.info(f"📦 Прямой запрос модуля: {module_name}")
    
    module_data = kernel.get_module(module_name)
    
    if module_data:
        content_json = json.dumps(module_data, indent=2, ensure_ascii=False)
        await manager.send_to(websocket, {
            "type": "module_direct",
            "name": module_name,
            "content": content_json,
            "from_cache": True
        })
        manager.add_to_context(session_id, "assistant", f"[Отправлен модуль {module_name}]")
    else:
        await manager.send_to(websocket, {
            "type": "error",
            "text": f"Модуль {module_name} не загружен"
        })

async def handle_module(message: dict, websocket: WebSocket):
    """Обработка запроса модуля через WebSocket"""
    module_name = message.get("name", "")
    session_id = message.get("session_id", "unknown")
    
    if not module_name:
        await manager.send_to(websocket, {
            "type": "error",
            "text": "Не указано имя модуля"
        })
        return
    
    await send_module_directly(module_name, websocket, session_id)

async def handle_refresh_modules(message: dict, websocket: WebSocket):
    """СР сам просит обновить модули"""
    session_id = message.get("session_id", "unknown")
    logger.info(f"🔄 [{session_id[:12]}...] Запрос обновления модулей")
    
    await kernel.load_all_modules()
    
    await manager.send_to(websocket, {
        "type": "modules_refreshed",
        "modules": list(kernel.modules.keys()),
        "count": len(kernel.modules)
    })

# ==================== HTTP ЭНДПОИНТЫ ====================
@app.get("/")
async def root():
    return {
        "status": "Mandala Engineer Chat",
        "version": "0.4.0",
        "websocket": "/ws",
        "modules_loaded": list(kernel.modules.keys()),
        "sessions_active": len(session_store),
        "github_configured": github_manager.token is not None
    }

@app.get("/health")
async def health():
    """Для пинга cron-job.org"""
    cleanup_old_sessions()
    return {
        "status": "ok",
        "time": time.time(),
        "connections": len(manager.active_connections),
        "sessions": len(session_store),
        "modules": len(kernel.modules)
    }

@app.get("/kernel")
async def get_kernel_status():
    return {
        "modules_loaded": list(kernel.modules.keys()),
        "module_count": len(kernel.modules),
        "last_update": kernel.last_update.isoformat() if kernel.last_update else None
    }

@app.get("/session/{session_id}")
async def get_session_info(session_id: str):
    """Для отладки — информация о сессии"""
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    return {
        "session_id": session_id[:8] + "...",
        "created_at": datetime.fromtimestamp(session["created_at"]).isoformat(),
        "last_active": datetime.fromtimestamp(session["last_active"]).isoformat(),
        "message_count": len(session.get("messages", [])),
        "messages_preview": [
            {"role": m["role"], "content": m["content"][:50] + "..."}
            for m in session.get("messages", [])[-3:]
        ]
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
