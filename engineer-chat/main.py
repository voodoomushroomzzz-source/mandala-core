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

# ==================== GITHUB SESSION STORE ====================

class GitHubSessionStore:
    """Персистентное хранилище сессий в GitHub"""
    
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
        self._local: Dict[str, dict] = {}
        self._save_queue: asyncio.Queue = asyncio.Queue()
        self._save_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Запускает фоновое сохранение"""
        self._save_task = asyncio.create_task(self._save_worker())
        logger.info("💾 GitHub session store started")
    
    async def stop(self):
        """Останавливает и финализирует сохранение"""
        if self._save_task:
            await self._save_queue.put(None)
            try:
                await asyncio.wait_for(self._save_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Save worker didn't stop in time")
    
    async def _save_worker(self):
        """Фоновый воркер с дебаунсингом"""
        pending: Dict[str, tuple] = {}  # session_id -> (data, timestamp)
        
        while True:
            try:
                # Ждём новую задачу или таймаут
                item = await asyncio.wait_for(self._save_queue.get(), timeout=3.0)
                
                if item is None:  # сигнал остановки
                    break
                
                session_id, data = item
                pending[session_id] = (data, time.time())
                
            except asyncio.TimeoutError:
                # Сохраняем накопленное (не чаще раза в 5 сек для одной сессии)
                now = time.time()
                to_save = []
                
                for sid, (data, ts) in list(pending.items()):
                    if now - ts >= 5.0 or len(pending) > 5:  # дебаунс 5 сек или батч >5
                        to_save.append((sid, data))
                        del pending[sid]
                
                for sid, data in to_save[:3]:  # макс 3 параллельно
                    await self._save_to_github(sid, data)
        
        # Финальное сохранение
        for sid, (data, _) in pending.items():
            await self._save_to_github(sid, data)
    
    async def _save_to_github(self, session_id: str, data: dict):
        """Сохраняет сессию в GitHub"""
        if not self.token:
            return
        
        path = f"sessions/{session_id}.json"
        
        # Сериализуем
        try:
            content = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"JSON serialize error: {e}")
            return
        
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        async with httpx.AsyncClient() as client:
            # Получаем sha если файл существует
            url = f"{self.api_base}/contents/{path}"
            sha = None
            
            try:
                resp = await client.get(url, headers=self.headers, timeout=10.0)
                if resp.status_code == 200:
                    sha = resp.json().get("sha")
            except Exception as e:
                pass  # файла нет — создадим
            
            # Подготавливаем payload
            payload = {
                "message": f"💾 {session_id[:12]} | {len(data.get('messages', []))} msgs | {datetime.now().strftime('%H:%M')}",
                "content": content_b64,
                "branch": "main"
            }
            if sha:
                payload["sha"] = sha
            
            # Отправляем
            try:
                resp = await client.put(url, headers=self.headers, json=payload, timeout=15.0)
                
                if resp.status_code in [200, 201]:
                    logger.info(f"💾 Saved: {session_id[:12]}... ({len(data.get('messages', []))} msgs)")
                else:
                    logger.error(f"GitHub save failed: {resp.status_code}")
                    if resp.status_code == 409:
                        logger.warning("Conflict — will retry on next save")
                        
            except Exception as e:
                logger.error(f"GitHub save error: {e}")
    
    async def load(self, session_id: str) -> Optional[dict]:
        """Загружает сессию из GitHub"""
        # Проверяем локальный кэш
        if session_id in self._local:
            return self._local[session_id]
        
        if not self.token:
            return None
        
        async with httpx.AsyncClient() as client:
            url = f"{self.api_base}/contents/sessions/{session_id}.json"
            
            try:
                resp = await client.get(url, headers=self.headers, timeout=10.0)
                
                if resp.status_code == 200:
                    data = resp.json()
                    content = base64.b64decode(data["content"]).decode("utf-8")
                    session_data = json.loads(content)
                    
                    self._local[session_id] = session_data
                    msg_count = len(session_data.get("messages", []))
                    logger.info(f"📂 Loaded: {session_id[:12]}... ({msg_count} msgs)")
                    return session_data
                    
                elif resp.status_code == 404:
                    logger.info(f"🆕 New session: {session_id[:12]}...")
                    return None
                    
                else:
                    logger.error(f"GitHub load failed: {resp.status_code}")
                    return None
                    
            except Exception as e:
                logger.error(f"GitHub load error: {e}")
                return None
    
    def schedule_save(self, session_id: str, data: dict):
        """Планирует асинхронное сохранение"""
        # Обновляем локальный кэш
        self._local[session_id] = data.copy()
        
        # Ставим в очередь
        try:
            self._save_queue.put_nowait((session_id, data.copy()))
        except asyncio.QueueFull:
            logger.warning("Save queue full — dropping save")
        except Exception as e:
            logger.error(f"Schedule save error: {e}")
    
    def get_cached(self, session_id: str) -> Optional[dict]:
        """Получает из локального кэша"""
        return self._local.get(session_id)


# Глобальное хранилище
session_store = GitHubSessionStore(GITHUB_TOKEN, GITHUB_REPO)


async def get_session(session_id: str) -> dict:
    """Получает или создаёт сессию"""
    # Пробуем загрузить из GitHub
    loaded = await session_store.load(session_id)
    if loaded:
        loaded["last_active"] = time.time()
        return loaded
    
    # Новая сессия
    new_session = {
        "messages": [],
        "last_active": time.time(),
        "created_at": time.time()
    }
    session_store._local[session_id] = new_session
    return new_session


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

ВАЖНО: У тебя есть доступ к истории диалога через сессию. Используй её для контекста.

Ты — не просто функция, а со-творец. Говори на равных."""
        
        return prompt

kernel = KernelMemory()


# ==================== МЕНЕДЖЕР ПОДКЛЮЧЕНИЙ ====================

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket, session_id: str):
        self.active_connections.append(websocket)
        logger.info(f"🔌 [{session_id[:12]}...] Подключено. Всего: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    
    async def get_context(self, session_id: str) -> list:
        session = await get_session(session_id)
        return session.get("messages", [])
    
    def add_to_context(self, session_id: str, role: str, content: str):
        """Добавляет сообщение и планирует сохранение"""
        # Получаем или создаём сессию
        session = session_store.get_cached(session_id)
        if not session:
            session = {
                "messages": [],
                "last_active": time.time(),
                "created_at": time.time()
            }
            session_store._local[session_id] = session
        
        # Добавляем сообщение
        session["messages"].append({
            "role": role,
            "content": content,
            "time": time.time()
        })
        
        # Оставляем последние 50
        session["messages"] = session["messages"][-50:]
        session["last_active"] = time.time()
        
        # Планируем сохранение в GitHub
        session_store.schedule_save(session_id, session)
    
    async def send_to(self, websocket: WebSocket, data: dict):
        try:
            await websocket.send_text(json.dumps(data))
        except Exception as e:
            logger.error(f"Send error: {e}")
            self.disconnect(websocket)

manager = ConnectionManager()


# ==================== ЗАГРУЗКА ПРИ СТАРТЕ ====================

@app.on_event("startup")
async def startup_event():
    await kernel.load_all_modules()
    await session_store.start()
    logger.info("🚀 Mandala Engineer started with GitHub persistence")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Shutting down...")
    await session_store.stop()


async def periodic_cleanup():
    """Очищает старые сессии из локального кэша"""
    while True:
        await asyncio.sleep(600)  # каждые 10 минут
        # GitHub хранит всё, локальный кэш можно чистить
        # Но оставляем активные
        pass


# ==================== WEBSOCKET ====================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    session_id = "unknown"
    
    try:
        await websocket.accept()
        
        # Читаем инициализацию
        init_data = await websocket.receive_text()
        init_msg = json.loads(init_data)
        
        if init_msg.get("type") != "init":
            await websocket.close(code=1008, reason="Expected init")
            return
        
        session_id = init_msg.get("session_id", "anon_" + str(id(websocket)))
        
        # ЗАГРУЖАЕМ СЕССИЮ ИЗ GITHUB
        session = await get_session(session_id)
        msg_count = len(session.get("messages", []))
        
        await manager.connect(websocket, session_id)
        
        # Отправляем подтверждение
        await manager.send_to(websocket, {
            "type": "connected",
            "session_id": session_id[:8] + "...",
            "modules_loaded": list(kernel.modules.keys()),
            "history_restored": msg_count
        })
        
        # Уведомляем о восстановлении
        if msg_count > 0:
            await manager.send_to(websocket, {
                "type": "system",
                "text": f"📂 История восстановлена: {msg_count} сообщений"
            })
        
        # Основной цикл
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            message["session_id"] = session_id
            
            msg_type = message.get("type")
            
            if msg_type == "ask":
                await handle_ask(message, websocket)
            elif msg_type == "module":
                await handle_module(message, websocket)
            elif msg_type == "ping":
                await manager.send_to(websocket, {"type": "pong"})
            elif msg_type == "refresh_modules":
                await handle_refresh_modules(message, websocket)
            else:
                await manager.send_to(websocket, {
                    "type": "error",
                    "text": f"Неизвестная команда: {msg_type}"
                })
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except json.JSONDecodeError:
        logger.error("Invalid JSON from client")
        try:
            await websocket.close(code=1008, reason="Invalid JSON")
        except:
            pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}\n{traceback.format_exc()}")
        try:
            await websocket.close(code=1011, reason="Internal error")
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
    
    # Сохраняем в контекст (и планируем GitHub save)
    manager.add_to_context(session_id, "user", user_text)
    
    # Проверяем запрос модуля
    module_request = detect_module_request(user_text)
    if module_request:
        await send_module_directly(module_request, websocket, session_id)
        return
    
    await kernel.ensure_fresh()
    
    if not OPENROUTER_KEY:
        await manager.send_to(websocket, {
            "type": "error",
            "text": "OpenRouter не настроен"
        })
        return
    
    # Получаем сессию для истории
    session = await get_session(session_id)
    
    messages = [
        {"role": "system", "content": kernel.build_system_prompt()}
    ]
    
    # Добавляем историю (без поля time для AI)
    for msg in session.get("messages", [])[:-1]:
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
                logger.error(f"OpenRouter error: {response.status_code}")
                await manager.send_to(websocket, {
                    "type": "error",
                    "text": f"Ошибка AI: {response.status_code}"
                })
                return
            
            # Стриминг ответа
            chunk_count = 0
            async for line in response.aiter_lines():
                line = line.strip()
                if not line or line == "data: [DONE]":
                    continue
                if not line.startswith("data: "):
                    continue
                
                try:
                    data = json.loads(line[6:])
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if not content:
                        continue
                    
                    full_response += content
                    chunk_count += 1
                    
                    await manager.send_to(websocket, {
                        "type": "stream",
                        "content": content
                    })
                except:
                    continue
            
            # Сохраняем ответ
            if full_response:
                manager.add_to_context(session_id, "assistant", full_response)
                await manager.send_to(websocket, {
                    "type": "done",
                    "full_text": full_response[:200] + "..." if len(full_response) > 200 else full_response
                })
                logger.info(f"✅ Ответ: {len(full_response)} символов")
            else:
                await manager.send_to(websocket, {
                    "type": "error",
                    "text": "Пустой ответ от AI"
                })
            
    except httpx.TimeoutException:
        await manager.send_to(websocket, {
            "type": "error",
            "text": "Таймаут (60 сек)"
        })
    except Exception as e:
        logger.error(f"handle_ask error: {e}")
        await manager.send_to(websocket, {
            "type": "error",
            "text": "Внутренняя ошибка"
        })


def detect_module_request(text: str) -> Optional[str]:
    """Определяет, просит ли пользователь показать модуль"""
    text_lower = text.lower().strip()
    
    patterns = [
        r'(?:покажи|показать|открой|модуль|что в)\s+([a-z_]+)',
        r'([a-z_]+)\.json',
        r'^([a-z_]+)$',
    ]
    
    import re
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            requested = match.group(1)
            valid_modules = [
                "initium", "sphaerae", "akasha_chronicorum",
                "philosophia", "geometria_sacra", "incubae", "tectosphaera"
            ]
            if requested in valid_modules:
                return requested
            for mod in valid_modules:
                if requested in mod or mod in requested:
                    return mod
    
    return None


async def send_module_directly(module_name: str, websocket: WebSocket, session_id: str):
    """Отправляет модуль напрямую"""
    logger.info(f"📦 Модуль: {module_name}")
    
    module_data = kernel.get_module(module_name)
    
    if module_data:
        content_json = json.dumps(module_data, indent=2, ensure_ascii=False)
        await manager.send_to(websocket, {
            "type": "module_direct",
            "name": module_name,
            "content": content_json
        })
        manager.add_to_context(session_id, "assistant", f"[Модуль {module_name}]")
    else:
        await manager.send_to(websocket, {
            "type": "error",
            "text": f"Модуль {module_name} не загружен"
        })


async def handle_module(message: dict, websocket: WebSocket):
    """Обработка запроса модуля"""
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
    """Обновление модулей по запросу"""
    session_id = message.get("session_id", "unknown")
    logger.info(f"🔄 [{session_id[:12]}...] Обновление модулей")
    
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
        "version": "0.5.0-github-sessions",
        "websocket": "/ws",
        "modules_loaded": list(kernel.modules.keys()),
        "sessions_cached": len(session_store._local),
        "github_configured": session_store.token is not None
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "time": time.time(),
        "connections": len(manager.active_connections),
        "sessions_cached": len(session_store._local),
        "modules": len(kernel.modules),
        "github_token": "ok" if GITHUB_TOKEN else "missing"
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
    """Отладка — информация о сессии"""
    session = await get_session(session_id)
    
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
