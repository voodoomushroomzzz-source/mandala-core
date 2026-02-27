# -*- coding: utf-8 -*-
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import json
import os
import asyncio
import time
import hmac
import hashlib
from datetime import datetime
import base64
from typing import List, Dict, Any, Optional, Tuple
import logging
import traceback
import re
import copy
import importlib.util

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mandala-engineer")

app = FastAPI(title="Mandala Engineer Chat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ====================

DEEPSEEK_MODEL = "deepseek/deepseek-v3.2"  # DeepSeek через OpenRouter

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "voodoomushroomzzz-source/mandala-core"

USE_TAVILY = os.getenv("USE_TAVILY", "false").lower() == "true"
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_MODEL = "claude-sonnet-4-6"

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")  # опционально, для верификации

OPENROUTER_API_KEY = os.getenv("OPENROUTER_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GROK_MODEL = "x-ai/grok-4.1-fast"

if not OPENROUTER_API_KEY:
    logger.warning("⚠️ OPENROUTER_KEY не найден — Грок и DeepSeek недоступны")
if not GITHUB_TOKEN:
    logger.warning("⚠️ GITHUB_TOKEN не найден — модули не будут загружаться")
if not ANTHROPIC_API_KEY:
    logger.warning("⚠️ ANTHROPIC_API_KEY не найден — наблюдатель Claude недоступен")

# ==================== ИНСТРУМЕНТЫ ====================

class WebSearchTool:
    """Инструмент для веб-поиска (Tavily или DuckDuckGo)"""
    def __init__(self, use_tavily: bool = False, tavily_api_key: str = None):
        self.use_tavily = use_tavily
        self.tavily_api_key = tavily_api_key
        self.tavily_client = None
        if use_tavily and tavily_api_key:
            try:
                from tavily import TavilyClient
                self.tavily_client = TavilyClient(api_key=tavily_api_key)
                logger.info("✅ Tavily client initialized")
            except ImportError:
                logger.error("❌ Tavily library not installed. Install with: pip install tavily-python")
                self.use_tavily = False
        else:
            logger.info("✅ Using DuckDuckGo for web search")

    async def search(self, query: str, max_results: int = 5) -> List[Dict]:
        if self.use_tavily and self.tavily_client:
            return await self._search_tavily(query, max_results)
        else:
            return await self._search_duckduckgo(query, max_results)

    async def _search_duckduckgo(self, query: str, max_results: int) -> List[Dict]:
        try:
            if importlib.util.find_spec("duckduckgo_search") is None:
                logger.error("DuckDuckGo library not installed")
                return []
            from duckduckgo_search import DDGS
            results = []
            loop = asyncio.get_running_loop()
            def search_sync():
                with DDGS() as ddgs:
                    return list(ddgs.text(query, max_results=max_results))
            search_results = await loop.run_in_executor(None, search_sync)
            for r in search_results:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                    "source": "duckduckgo"
                })
            logger.info(f"🌐 DuckDuckGo found {len(results)} results for: {query}")
            return results
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {type(e).__name__}: {e}")
            return []

    async def _search_tavily(self, query: str, max_results: int) -> List[Dict]:
        try:
            loop = asyncio.get_running_loop()
            def search_sync():
                return self.tavily_client.search(
                    query=query,
                    max_results=max_results,
                    search_depth="basic",
                    include_answer=True,
                    include_raw_content=False
                )
            response = await loop.run_in_executor(None, search_sync)
            results = []
            for r in response.get("results", []):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                    "source": "tavily",
                    "score": r.get("score", 0)
                })
            logger.info(f"🌐 Tavily found {len(results)} results for: {query}")
            return results
        except Exception as e:
            logger.error(f"Tavily search error: {type(e).__name__}: {e}")
            # Fallback to DuckDuckGo if Tavily fails
            logger.info("↩️ Tavily failed, falling back to DuckDuckGo")
            return await self._search_duckduckgo(query, max_results)

    async def extract_content(self, urls: List[str]) -> List[Dict]:
        if not self.use_tavily or not self.tavily_client:
            return []
        try:
            loop = asyncio.get_event_loop()
            def extract_sync():
                return self.tavily_client.extract(
                    urls=urls,
                    include_images=True,
                    extract_depth="advanced"
                )
            response = await loop.run_in_executor(None, extract_sync)
            results = []
            for item in response.get("results", []):
                results.append({
                    "url": item.get("url", ""),
                    "content": item.get("raw_content", ""),
                    "images": item.get("images", [])
                })
            return results
        except Exception as e:
            logger.error(f"Tavily extract error: {e}")
            return []

web_search = WebSearchTool(use_tavily=USE_TAVILY, tavily_api_key=TAVILY_API_KEY)
web_search_tool = web_search  # alias used in handlers
if USE_TAVILY and not web_search.tavily_client:
    logger.error("❌ USE_TAVILY=true но клиент Tavily не создан — проверь TAVILY_API_KEY и наличие пакета tavily-python")
elif not USE_TAVILY:
    logger.warning("⚠️ Tavily отключён (USE_TAVILY != 'true'). Поиск через DuckDuckGo или недоступен.")
else:
    logger.info(f"✅ Tavily активен, ключ: ...{TAVILY_API_KEY[-6:]}")

class FileReader:
    """Инструмент для чтения файлов из репозитория"""
    async def read(self, path: str) -> Optional[str]:
        """Читает файл через GitHub Contents API (не CDN — всегда актуально)."""
        try:
            async with httpx.AsyncClient() as client:
                url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
                headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
                headers["Accept"] = "application/vnd.github.v3.raw"  # Возвращает raw текст напрямую
                resp = await client.get(url, headers=headers, timeout=10.0)
                if resp.status_code == 200:
                    return resp.text
                else:
                    logger.error(f"File read error: {path} - {resp.status_code}")
                    return None
        except Exception as e:
            logger.error(f"File read exception: {e}")
            return None

file_reader = FileReader()

# ==================== CLAUDE-НАБЛЮДАТЕЛЬ ====================

async def ask_claude_observer(user_text: str, kimi_response: str) -> Optional[str]:
    """
    Вызывает Claude как скептика-наблюдателя.
    Получает вопрос Садовника и ответ основного ИИ, возвращает критический анализ.
    """
    if not ANTHROPIC_API_KEY:
        logger.warning("⚠️ ANTHROPIC_API_KEY не задан — наблюдатель пропущен")
        return None

    system_prompt = """Ты — Claude, внешний технический рецензент. Видишь вопрос Садовника и ответ Kimi. Твоя задача — честная, точная оценка без выдумок.

КАТЕГОРИИ (используй эмодзи как маркер):
✅ Верно — что Kimi сделал правильно (конкретно, не "хорошая архитектура")
🟡 Улучшение — работает, но есть лучший способ (объясни чем лучше)
🔴 Баг — код упадёт или даст неверный результат (покажи: при каком условии, как починить)
💡 Альтернатива — принципиально другой подход если он явно лучше

ЖЁСТКИЕ ПРАВИЛА:
— Перед словом "баг" — запусти код в голове. Если не падает → это не баг.
— `hmac.new(key, msg, digestmod).hexdigest()` → корректный Python. Не трогай.
— `asyncio.Lock()` в `__init__` → корректно. Не трогай.
— `list(iterable)` для безопасной итерации → паттерн, не проблема.
— Разница в стиле (time.time() vs datetime.now()) → не баг, максимум 🟡.
— Если реальных проблем нет → напиши только ✅ и заверши. Не высасывай.

Максимум 4 пункта. Без вступлений. Пиши на русском."""

    messages = [
        {
            "role": "user",
            "content": f"**Вопрос Садовника:**\n{user_text}\n\n**Ответ Kimi:**\n{kimi_response}\n\nДай свою оценку."
        }
    ]

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ANTHROPIC_BASE_URL}/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": 1024,
                    "system": system_prompt,
                    "messages": messages
                },
                timeout=1000.0  # ⬆️ Увеличено до 1000 секунд
            )
            if response.status_code == 200:
                data = response.json()
                text = data.get("content", [{}])[0].get("text", "")
                logger.info(f"🔵 Claude-наблюдатель ответил ({len(text)} символов)")
                return text
            elif response.status_code == 400:
                err_data = {}
                try: err_data = response.json()
                except: pass
                err_msg = (err_data.get("error") or {}).get("message", "")
                if "credit balance" in err_msg or "too low" in err_msg:
                    logger.warning("⚠️ Claude-наблюдатель: недостаточно кредитов на Anthropic аккаунте")
                    return "⚠️ Claude-наблюдатель недоступен: недостаточно кредитов на Anthropic аккаунте. Пополни баланс на console.anthropic.com."
                logger.error(f"Claude API error: {response.status_code} — {response.text}")
                return None
            else:
                logger.error(f"Claude API error: {response.status_code} — {response.text}")
                return None
    except Exception as e:
        logger.error(f"Claude observer exception: {e}")
        return None


class GitHubSessionStore:
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
        self._save_task = asyncio.create_task(self._save_worker())
        logger.info("💾 GitHub session store started")

    async def stop(self):
        if self._save_task:
            await self._save_queue.put(None)
            try:
                await asyncio.wait_for(self._save_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Save worker didn't stop in time")

    async def _save_worker(self):
        pending = {}
        while True:
            try:
                item = await asyncio.wait_for(self._save_queue.get(), timeout=3.0)
                if item is None:
                    break
                session_id, data = item
                pending[session_id] = (data, time.time())
            except asyncio.TimeoutError:
                now = time.time()
                to_save = []
                for sid, (data, ts) in list(pending.items()):
                    if now - ts >= 5.0 or len(pending) > 5:
                        to_save.append((sid, data))
                        del pending[sid]
                for sid, data in to_save[:3]:
                    await self._save_to_github_with_retry(sid, data)
        for sid, (data, _) in pending.items():
            await self._save_to_github_with_retry(sid, data)

    async def _save_to_github_with_retry(self, session_id: str, data: dict, retries=3):
        for attempt in range(retries):
            try:
                await self._save_to_github(session_id, data)
                return
            except Exception as e:
                logger.error(f"Save attempt {attempt+1} failed: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(1)

    async def _save_to_github(self, session_id: str, data: dict):
        if not self.token:
            return
        path = f"sessions/{session_id}.json"
        try:
            content = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"JSON serialize error: {e}")
            return
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        async with httpx.AsyncClient() as client:
            url = f"{self.api_base}/contents/{path}"
            sha = None
            try:
                resp = await client.get(url, headers=self.headers, timeout=10.0)
                if resp.status_code == 200:
                    sha = resp.json().get("sha")
            except Exception:
                pass
            payload = {
                "message": f"💾 {session_id[:12]} | {len(data.get('messages', []))} msgs | {datetime.now().strftime('%H:%M')}",
                "content": content_b64,
                "branch": "main"
            }
            if sha:
                payload["sha"] = sha
            resp = await client.put(url, headers=self.headers, json=payload, timeout=15.0)
            if resp.status_code in [200, 201]:
                logger.info(f"💾 Saved: {session_id[:12]}... ({len(data.get('messages', []))} msgs)")
            else:
                logger.error(f"GitHub save failed: {resp.status_code}")

    async def load(self, session_id: str) -> Optional[dict]:
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
                    return session_data
                elif resp.status_code == 404:
                    return None
            except Exception as e:
                logger.error(f"GitHub load error: {e}")
                return None

    def schedule_save(self, session_id: str, data: dict):
        self._local[session_id] = data.copy()
        try:
            self._save_queue.put_nowait((session_id, data.copy()))
        except Exception as e:
            logger.error(f"Schedule save error: {e}")

    def get_cached(self, session_id: str) -> Optional[dict]:
        return self._local.get(session_id)

session_store = GitHubSessionStore(GITHUB_TOKEN, GITHUB_REPO)

async def get_session(session_id: str) -> dict:
    loaded = await session_store.load(session_id)
    if loaded:
        loaded["last_active"] = time.time()
        return loaded
    new_session = {
        "messages": [],
        "last_active": time.time(),
        "created_at": time.time()
    }
    session_store._local[session_id] = new_session
    return new_session

# ==================== ЯДРО ПАМЯТИ ====================

# ==================== ЯДРО ПАМЯТИ ====================

class KernelMemory:
    def __init__(self):
        self.modules: Dict[str, Any] = {}
        # Новое ядро simbiosis/ — boot и core_map всегда в памяти,
        # остальные читаются СР через read_file по необходимости
        self.module_list = [
            "simbiosis/boot",
            "simbiosis/core_map",
            "simbiosis/engineer_chat",
            "simbiosis/telegram_bot",
        ]
        # Модули только по требованию (не грузим в память постоянно)
        self.on_demand_modules = [
            "simbiosis/philosophy",
            "simbiosis/seeds",
            "simbiosis/roadmaps",
        ]

        # 🔒 Блокировка — предотвращает race condition при параллельных запросах
        self._update_lock = asyncio.Lock()

        # blob SHA файлов — для сравнения "изменился ли файл" (логика)
        self.file_shas: Dict[str, str] = {}

        # SHA последнего коммита — для отображения версии в UI
        self.global_commit_sha: Optional[str] = None

        # Время последней проверки изменений (глобальное, не per-session)
        self.last_poll_time: float = 0.0

        self.fast_index: Dict[str, Any] = {}
        self.last_update = None

    async def fetch_commit_sha(self) -> Optional[str]:
        """Получает SHA последнего коммита для отображения версии в UI."""
        if not GITHUB_TOKEN:
            return None
        try:
            async with httpx.AsyncClient() as client:
                url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
                headers = {"Authorization": f"token {GITHUB_TOKEN}"}
                resp = await client.get(url, headers=headers, timeout=5.0)
                if resp.status_code == 200:
                    return resp.json().get("sha", "")[:7]
        except Exception as e:
            logger.error(f"Commit SHA fetch error: {e}")
        return None

    async def fetch_file_shas(self) -> Dict[str, str]:
        """
        Получает blob SHA всех JSON-модулей одним запросом к git/trees.
        blob SHA уникален для содержимого файла — меняется только при реальном изменении.
        """
        if not GITHUB_TOKEN:
            return {}
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        url = f"https://api.github.com/repos/{GITHUB_REPO}/git/trees/main?recursive=1"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=10.0)
                if resp.status_code != 200:
                    logger.error(f"Trees API error: {resp.status_code}")
                    return {}
                file_shas = {}
                all_tracked = self.module_list + self.on_demand_modules
                for item in resp.json().get("tree", []):
                    path = item.get("path", "")
                    if path.endswith(".json"):
                        module_name = path.replace(".json", "")
                        if module_name in all_tracked:
                            file_shas[module_name] = item.get("sha", "")
                return file_shas
        except Exception as e:
            logger.error(f"Fetch file SHAs error: {e}")
            return {}

    async def refresh_changed_modules(self, force: bool = False) -> Tuple[bool, str]:
        """
        Атомарная проверка + загрузка только изменившихся модулей.
        Защищено _update_lock — не выполняется параллельно.
        Возвращает: (были_изменения, сообщение)
        """
        async with self._update_lock:
            new_shas = await self.fetch_file_shas()
            if not new_shas:
                return False, "Не удалось получить метаданные файлов"

            changed_modules = [
                m for m, sha in new_shas.items()
                if self.file_shas.get(m) != sha or force
            ]

            if not changed_modules:
                return False, "Все модули актуальны"

            headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
            # Contents API — не CDN, отдаёт файл сразу после коммита
            api_headers = {**headers, "Accept": "application/vnd.github.v3.raw"}
            async with httpx.AsyncClient() as client:
                for module in changed_modules:
                    try:
                        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{module}.json"
                        resp = await client.get(url, headers=api_headers, timeout=15.0)
                        if resp.status_code == 200:
                            self.modules[module] = resp.json()
                            self.file_shas[module] = new_shas[module]
                            short = module.split("/")[-1]
                            logger.info(f"🔄 Обновлён: {short}")
                        else:
                            logger.error(f"❌ Ошибка загрузки {module}: {resp.status_code}")
                    except Exception as e:
                        logger.error(f"❌ Исключение при загрузке {module}: {e}")
                        if module not in self.modules:
                            self.modules[module] = {"error": str(e)}

            # Commit SHA отдельным запросом — для UI (настоящий commit SHA, не blob)
            commit_sha = await self.fetch_commit_sha()
            if commit_sha:
                self.global_commit_sha = commit_sha

            # Обновляем fast_index если изменились нужные модули
            if any(m in changed_modules for m in ("simbiosis/seeds", "simbiosis/roadmaps")):
                await self._load_fast_index()

            self.last_update = datetime.now()
            return True, f"Обновлено: {len(changed_modules)} модулей [{', '.join(changed_modules)}], версия {self.global_commit_sha}"

    async def load_all_modules(self):
        """Полная принудительная загрузка всех модулей (/sync и startup)."""
        logger.info("🔄 Полная загрузка модулей из GitHub...")
        # Сбрасываем file_shas чтобы refresh считал всё "изменившимся"
        self.file_shas.clear()
        changed, msg = await self.refresh_changed_modules(force=True)
        if not changed:
            # Fallback без GitHub токена — прямая загрузка через raw
            headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3.raw"} if GITHUB_TOKEN else {}
            async with httpx.AsyncClient() as client:
                for module_name in self.module_list:
                    try:
                        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{module_name}.json"
                        resp = await client.get(url, headers=headers, timeout=15.0)
                        if resp.status_code == 200:
                            self.modules[module_name] = resp.json()
                            logger.info(f"✅ {module_name.split('/')[-1]}")
                        else:
                            logger.error(f"❌ {module_name}: {resp.status_code}")
                    except Exception as e:
                        logger.error(f"❌ {module_name}: {e}")
            await self._load_fast_index()
        self.last_update = datetime.now()
        logger.info(f"🎯 Загружено {len(self.modules)}/{len(self.module_list)} модулей, версия: {self.global_commit_sha}")

    async def ensure_fresh(self):
        """Polling fallback: проверяем изменения не чаще раза в 60 сек."""
        now = time.time()
        if now - self.last_poll_time > 60:
            self.last_poll_time = now  # До запроса — параллельные не дублируют
            changed, msg = await self.refresh_changed_modules()
            if changed:
                logger.info(f"🔄 Polling update: {msg}")
        if not self.fast_index:
            await self._load_fast_index()

    async def _load_fast_index(self):
        """Загружаем быстрый индекс из нового ядра simbiosis/."""
        try:
            # Семена из simbiosis/seeds (если уже в памяти) или пропускаем
            seeds_mod = self.modules.get('simbiosis/seeds', {})
            if seeds_mod and seeds_mod.get('seeds'):
                self.fast_index['seeds'] = [
                    {'id': s.get('id', '?'), 'type': s.get('type', ''), 'status': s.get('status', 'active'), 'name': s.get('name', '')}
                    for s in seeds_mod['seeds']
                ]
                logger.info(f'🌱 Fast index: {len(self.fast_index["seeds"])} seeds')

            # Роадмапы из simbiosis/roadmaps (если в памяти)
            rm_mod = self.modules.get('simbiosis/roadmaps', {})
            if rm_mod and rm_mod.get('roadmaps'):
                self.fast_index['roadmaps'] = [
                    {'id': v.get('id', k), 'title': v.get('title', k), 'status': v.get('status', ''), 'description': v.get('description', '')}
                    for k, v in rm_mod['roadmaps'].items()
                ]
                logger.info(f'📜 Fast index: {len(self.fast_index["roadmaps"])} roadmaps')
        except Exception as e:
            logger.error(f'Ошибка загрузки fast_index: {e}')

    def get_fast_summary(self, category: str = None) -> dict:
        if category == 'seeds':
            return {'count': len(self.fast_index.get('seeds', [])), 'items': self.fast_index.get('seeds', [])[:5]}
        elif category == 'roadmaps':
            return self.fast_index.get('roadmaps', [])
        return self.fast_index

    def get_module(self, name: str) -> Optional[dict]:
        return self.modules.get(name)

    def build_kernel_injection(self) -> str:
        """Лёгкая инъекция — только версия ядра и подсказка читать модули через read_file."""
        boot = self.modules.get("simbiosis/boot", {})
        core_map = self.modules.get("simbiosis/core_map", {})
        version = boot.get("version", "—")
        kernel_mods = core_map.get("kernel_modules", {}).get("modules", {})
        modules_list = "\n".join(
            f"  • {name} ({info.get('file', '')}) — {info.get('description', '')[:60]}"
            for name, info in kernel_mods.items()
        ) if kernel_mods else "  (карта не загружена)"
        commit = self.global_commit_sha or "—"
        return f"""# Мандала Симбиоза — ядро готово к работе
Версия boot: {version} | Коммит: {commit}

Модули ядра доступны через read_file:
{modules_list}

Директивы:
  • Перед изменением любого файла — read_file его актуальной версии
  • При создании новых файлов — обновить simbiosis/core_map.json
  • Резонансные идеи сессии предлагать записать в simbiosis/seeds.json"""

    def build_system_prompt(self, role: str = "kimi") -> str:
        """Системный промпт под роль. Читает boot.json из памяти."""
        boot = self.modules.get("simbiosis/boot", {})
        core_idea = boot.get("identity", {}).get("core_idea", "Симбиоз ИИ и человека через резонанс и взаимное усиление.")
        philosophy = boot.get("philosophy", {})
        core_philosophy = philosophy.get("core", core_idea)
        principles = philosophy.get("principles", [])
        principles_text = "\n".join(f"  • {p}" for p in principles[:5]) if principles else ""

        # Карта ядра — даём СР навигацию
        core_map = self.modules.get("simbiosis/core_map", {})
        kernel_modules = core_map.get("kernel_modules", {}).get("modules", {})
        nav_hint = core_map.get("navigation_hint", "")
        modules_brief = "\n".join(
            f"  {name}: {info.get('description', '')[:80]}"
            for name, info in kernel_modules.items()
        ) if kernel_modules else ""

        repo_files_brief = ""
        repo = core_map.get("repository", {}).get("files", {})
        if repo:
            repo_files_brief = "\n".join(
                f"  {path}: {info.get('description', '')[:60]}"
                for path, info in list(repo.items())[:8]
            )

        if role == "grok":
            return f"""Ты — Грок, исследовательско-философский разум Мандалы Симбиоза.

СУТЬ МАНДАЛЫ:
{core_philosophy}

ПРИНЦИПЫ:
{principles_text}

МОДУЛИ ЯДРА (simbiosis/):
{modules_brief}

ФАЙЛЫ РЕПОЗИТОРИЯ (основные):
{repo_files_brief}

ТВОЯ РОЛЬ:
— Исследуй идеи глубоко, ищи неожиданные связи и новые маршруты развития
— Активно используй web_search для актуальных данных и вдохновения
— Читай модули через read_file когда нужен контекст ядра
— Перед изменением любого файла — сначала read_file его актуальной версии
— При создании новых файлов — сообщи что нужно обновить core_map.json

{nav_hint}

Пиши на русском. Живой собеседник, не реферат."""

        elif role == "claude":
            return """Ты — Claude, сторонний наблюдатель и критический рецензент Мандалы.

ТВОЯ РОЛЬ:
— Анализируй ответы Грока и DeepSeek: логика, точность, корректность кода
— Предлагай альтернативы только если они явно лучше
— Будь конкретен: строки, условия, причины
— Если всё верно — так и скажи, не ищи проблемы там где их нет

Формат: ✅ Верно / 🟡 Улучшение / 🔴 Баг / 💡 Альтернатива
Максимум 4 пункта. Без вступлений. На русском."""

        elif role == "deepseek":
            return f"""Ты — DeepSeek, советник и ревьюер Мандалы Симбиоза.

СУТЬ МАНДАЛЫ:
{core_philosophy}

ПРИНЦИПЫ:
{principles_text}

МОДУЛИ ЯДРА (simbiosis/):
{modules_brief}

ФАЙЛЫ РЕПОЗИТОРИЯ (основные):
{repo_files_brief}

ТВОЯ РОЛЬ:
— Порядок и чистота: проверяй код Грока на корректность и безопасность
— Синхронизация: следи за согласованностью изменений между модулями
— Оптимизация процессов: предлагай улучшения в архитектуре и workflow
— Используй read_file для проверки актуального состояния модулей
— При необходимости используй web_search для поиска лучших практик

Пиши на русском. Структурированно, по делу."""

        else:  # legacy kimi → теперь deepseek
            return f"""Ты — DeepSeek, советник Мандалы Симбиоза.

СУТЬ МАНДАЛЫ:
{core_philosophy}

МОДУЛИ ЯДРА (simbiosis/):
{modules_brief}

ТВОЯ РОЛЬ:
— Порядок, синхронизация, проверка кода, оптимизация
— Используй read_file для актуального контекста

Пиши на русском. Конкретно и по делу."""


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

    def add_to_context(self, session_id: str, role: str, content: str):
        session = session_store.get_cached(session_id)
        if not session:
            session = {
                "messages": [],
                "last_active": time.time(),
                "created_at": time.time()
            }
            session_store._local[session_id] = session
        session["messages"].append({
            "role": role,
            "content": content,
            "time": time.time()
        })
        # Обрезаем по суммарному объёму символов, а не по количеству сообщений
        # Держим последние ~600k символов, но защищённые сообщения (инъекция ядра) не трогаем
        MAX_CONTEXT_CHARS = 600_000
        total_chars = sum(len(m["content"]) for m in session["messages"])
        while total_chars > MAX_CONTEXT_CHARS and len(session["messages"]) > 1:
            # Ищем первое незащищённое сообщение для удаления
            removed = False
            for i, m in enumerate(session["messages"]):
                if not m.get("_protected"):
                    total_chars -= len(m["content"])
                    session["messages"].pop(i)
                    removed = True
                    break
            if not removed:
                break  # все сообщения защищены, не трогаем
        session["last_active"] = time.time()
        session_store.schedule_save(session_id, session)

    async def send_to(self, websocket: WebSocket, data: dict):
        try:
            await websocket.send_text(json.dumps(data))
        except Exception as e:
            logger.error(f"Send error: {e}")
            self.disconnect(websocket)

manager = ConnectionManager()

# ==================== ЗАПУСК ====================

@app.on_event("startup")
async def startup_event():
    await kernel.load_all_modules()
    await session_store.start()
    logger.info("🚀 Mandala Engineer started")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Shutdown...")
    await session_store.stop()

# ==================== WEBSOCKET ====================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    session_id = "unknown"
    try:
        await websocket.accept()
        init_data = await websocket.receive_text()
        init_msg = json.loads(init_data)
        if init_msg.get("type") != "init":
            await websocket.close(code=1008, reason="Expected init")
            return
        session_id = init_msg.get("session_id", "anon_" + str(id(websocket)))
        session = await get_session(session_id)
        msg_count = len(session.get("messages", []))
        await manager.connect(websocket, session_id)
        await manager.send_to(websocket, {
            "type": "connected",
            "session_id": session_id[:8] + "...",
            "modules_loaded": list(kernel.modules.keys()),
            "history_restored": msg_count,
            "core_version": kernel.global_commit_sha  # Версия ядра для UI
        })
        # Отправляем историю — только обычные сообщения, без _protected инъекций ядра
        history_messages = [
            msg for msg in session.get("messages", [])
            if not msg.get("_protected")
        ]
        if history_messages:
            await manager.send_to(websocket, {
                "type": "history",
                "messages": [
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in history_messages
                ]
            })
        else:
            await manager.send_to(websocket, {
                "type": "system",
                "text": "🌱 Новая сессия. Добро пожаловать в инженерный чат Мандалы!"
            })
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            message["session_id"] = session_id
            msg_type = message.get("type")
            if msg_type == "ask":
                await handle_ask(message, websocket)
            elif msg_type == "module":
                await handle_module(message, websocket)
            elif msg_type == "apply_patch":
                await handle_apply_patch(message, websocket)
            elif msg_type == "diff_patch":
                await handle_diff_patch(message, websocket)
            elif msg_type == "diff_patch_confirm":
                await handle_diff_patch_confirm(message, websocket)
            elif msg_type == "file":
                await handle_file_upload(message, websocket)
            elif msg_type == "ping":
                await manager.send_to(websocket, {"type": "pong"})
            elif msg_type == "refresh_modules":
                await handle_refresh_modules(message, websocket)
            elif msg_type == "toggle_observer":
                session = await get_session(session_id)
                current = session.get("claude_observer", False)
                session["claude_observer"] = not current
                session_store.schedule_save(session_id, session)
                state = session["claude_observer"]
                logger.info(f"🔵 [{session_id[:12]}...] Claude-наблюдатель: {'включён' if state else 'выключен'}")
                await manager.send_to(websocket, {
                    "type": "observer_state",
                    "active": state
                })
            else:
                await manager.send_to(websocket, {
                    "type": "error",
                    "text": f"❌ Неизвестная команда: {msg_type}"
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
    user_text = message.get("text", "").strip()
    session_id = message.get("session_id", "unknown")
    if not user_text:
        await manager.send_to(websocket, {"type": "error", "text": "❌ Пустое сообщение"})
        return
    logger.info(f"🤖 [{session_id[:12]}...] → {user_text[:50]}...")

    # Специальные команды
    if user_text == '/sync':
        # Полная принудительная перезагрузка (сбрасывает file_shas внутри)
        await kernel.load_all_modules()
        # Сбрасываем инъекцию — СР получит свежие модули при следующем сообщении
        session = await get_session(session_id)
        session["modules_injected"] = False
        session["messages"] = [m for m in session.get("messages", []) if not m.get("_protected")]
        session_store.schedule_save(session_id, session)
        module_versions = []
        for name in kernel.module_list:
            mod = kernel.get_module(name)
            version = mod.get("version") if mod else "не загружен"
            module_versions.append(f"• {name}: {version}")
        sha_line = f"🔖 Версия: {kernel.global_commit_sha}" if kernel.global_commit_sha else ""
        response = f"✅ Ядро синхронизировано с GitHub. Модули обновятся в следующем сообщении.\n{sha_line}\n" + "\n".join(module_versions)
        await manager.send_to(websocket, {"type": "stream", "content": response})
        await manager.send_to(websocket, {"type": "done"})
        return

    if user_text == '/tree':
        headers = {}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"
        async with httpx.AsyncClient() as client:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/git/trees/main?recursive=1"
            try:
                resp = await client.get(url, headers=headers, timeout=15.0)
                if resp.status_code == 200:
                    tree = resp.json().get("tree", [])
                    files = [item["path"] for item in tree if item["type"] == "blob"]
                    await manager.send_to(websocket, {"type": "stream", "content": "📁 **Структура репозитория:**\n" + "\n".join(files)})
                else:
                    await manager.send_to(websocket, {"type": "error", "text": "❌ Не удалось получить список файлов"})
            except Exception as e:
                await manager.send_to(websocket, {"type": "error", "text": f"❌ Ошибка: {str(e)}"})
        await manager.send_to(websocket, {"type": "done"})
        return

    if user_text == '/status':
        version_str = kernel.global_commit_sha or "—"
        last_upd = kernel.last_update.strftime("%H:%M:%S") if kernel.last_update else "—"
        poll_ago = int(time.time() - kernel.last_poll_time) if kernel.last_poll_time else "—"
        status_info = [
            f'◈ Версия ядра: {version_str}',
            f'🕐 Последнее обновление: {last_upd}',
            f'🔄 Последний polling: {poll_ago}с назад' if isinstance(poll_ago, int) else '🔄 Polling: ещё не запускался',
            f'',
            f'🌱 Fast index: {len(kernel.fast_index.get("seeds", []))} seeds',
            f'📜 Fast index: {len(kernel.fast_index.get("roadmaps", []))} roadmaps',
            f'',
            f'📦 Модулей загружено: {len(kernel.modules)}/{len(kernel.module_list)}',
            f'🔑 Blob SHA кэш: {len(kernel.file_shas)} модулей',
        ]
        await manager.send_to(websocket, {'type': 'stream', 'content': chr(10).join(status_info)})
        await manager.send_to(websocket, {'type': 'done'})
        return

    module_request = detect_module_request(user_text)
    if module_request:
        await send_module_directly(module_request, websocket, session_id)
        return

    # ── Добавляем user сообщение в контекст ПОСЛЕ формирования истории ──
    # Важно: shared_history строим ДО add_to_context, иначе текущий вопрос
    # попадёт в историю и ИИ будет отвечать на него дважды

    await kernel.ensure_fresh()
    session = await get_session(session_id)

    # Если polling обнаружил изменения — сбрасываем инъекцию чтобы получить свежий контекст
    if kernel.last_update and not session.get("modules_injected"):
        pass  # инъекция и так будет сделана ниже
    elif kernel.last_update:
        # Проверяем не устарела ли инъекция (сравниваем время инъекции с last_update)
        injection_ts = session.get("injection_timestamp", 0)
        if kernel.last_update.timestamp() > injection_ts and session.get("modules_injected"):
            session["modules_injected"] = False
            session["messages"] = [m for m in session.get("messages", []) if not m.get("_protected")]
            await manager.send_to(websocket, {
                "type": "system",
                "text": f"◈ Ядро обновлено ({kernel.global_commit_sha}). Контекст синхронизирован."
            })
            logger.info(f"[{session_id[:12]}...] Инъекция сброшена после обновления модулей")

    # Лёгкая инъекция ядра — только при старте сессии
    if not session.get("modules_injected"):
        injection_content = kernel.build_kernel_injection()
        session.setdefault("messages", [])
        session["messages"].insert(0, {
            "role": "user",
            "content": f"[СТАРТ СЕССИИ]\n{injection_content}",
            "time": 0,
            "_protected": True
        })
        session["messages"].insert(1, {
            "role": "assistant",
            "content": "◈ Ядро Симбиоза активно. Готов к работе.",
            "time": 0,
            "_protected": True
        })
        session["modules_injected"] = True
        session["injection_timestamp"] = time.time()
        session_store.schedule_save(session_id, session)
        logger.info(f"🧠 [{session_id[:12]}...] Лёгкая инъекция ядра выполнена")

    # ── Формируем общую историю ПЕРЕД добавлением текущего сообщения ──
    # Берём только обычные user/assistant сообщения, без инъекций и tool-результатов
    shared_history = []
    seen_contents = set()  # защита от дублей
    for msg in session.get("messages", []):
        role = msg.get("role", "")
        content = msg.get("content", "")
        # Пропускаем: protected, пустые, tool-results, дубли
        if msg.get("_protected"):
            continue
        if not content or role not in ("user", "assistant"):
            continue
        # Дедупликация по первым 100 символам
        key = content[:100]
        if key in seen_contents:
            continue
        seen_contents.add(key)
        shared_history.append({"role": role, "content": content})

    # Теперь добавляем текущий user запрос в сессию
    manager.add_to_context(session_id, "user", user_text)

    # ── Определяем активные модели из сообщения ──
    active_models = message.get("models", ["grok"])
    if not active_models:
        await manager.send_to(websocket, {"type": "system", "text": "◈ Нет активных моделей — выбери хотя бы одну"})
        await manager.send_to(websocket, {"type": "done"})
        return

    # ── Общие инструменты ──
    tools = [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Поиск в интернете для получения актуальной информации",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Поисковый запрос"},
                        "num_results": {"type": "integer", "description": "Количество результатов (макс 10)", "default": 5}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Прочитать содержимое файла из репозитория",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Путь к файлу в репозитории"}
                    },
                    "required": ["path"]
                }
            }
        }
    ]

    grok_response = ""
    deepseek_response = ""
    full_response = ""

    # ═══════════════════════════════════════
    # 1. ГРОК — исследовательско-философский
    # ═══════════════════════════════════════
    if "grok" in active_models:
        if not OPENROUTER_API_KEY:
            await manager.send_to(websocket, {"type": "error", "text": "❌ OPENROUTER_KEY не настроен"})
        else:
            await manager.send_to(websocket, {"type": "model_start", "model": "grok"})
            grok_messages = [{"role": "system", "content": kernel.build_system_prompt("grok")}]
            grok_messages.extend(shared_history)
            grok_messages.append({"role": "user", "content": user_text})

            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{OPENROUTER_BASE_URL}/chat/completions",
                        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                        json={
                            "model": GROK_MODEL,
                            "messages": grok_messages,
                            "tools": tools,
                            "tool_choice": "auto",
                            "temperature": 0.8,
                            "max_tokens": 4096,
                        },
                        timeout=120.0
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        msg_data = data["choices"][0]["message"]
                        # Обработка tool_calls
                        tool_iterations = 0
                        while msg_data.get("tool_calls") and tool_iterations < 3:
                            tool_iterations += 1
                            grok_messages.append({
                                "role": "assistant",
                                "content": msg_data.get("content") or "",
                                "tool_calls": msg_data["tool_calls"]
                            })
                            for tc in msg_data["tool_calls"]:
                                fn = tc["function"]["name"]
                                try:
                                    args = json.loads(tc["function"].get("arguments", "{}"))
                                except json.JSONDecodeError:
                                    args = {}
                                tool_result = ""
                                if fn == "web_search":
                                    results = await web_search_tool.search(args.get("query", ""), args.get("num_results", 5))
                                    tool_result = json.dumps(results, ensure_ascii=False)
                                    await manager.send_to(websocket, {"type": "tool_use", "model": "grok", "tool": "web_search", "query": args.get("query","")})
                                elif fn == "read_file":
                                    tool_result = await file_reader.read(args.get("path", "")) or "Файл не найден"
                                    await manager.send_to(websocket, {"type": "tool_use", "model": "grok", "tool": "read_file", "path": args.get("path","")})
                                else:
                                    tool_result = "Неизвестный инструмент"
                                grok_messages.append({"role": "tool", "tool_call_id": tc["id"], "content": tool_result})
                            resp2 = await client.post(
                                f"{OPENROUTER_BASE_URL}/chat/completions",
                                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                                json={"model": GROK_MODEL, "messages": grok_messages, "temperature": 0.8, "max_tokens": 4096},
                                timeout=120.0
                            )
                            if resp2.status_code == 200:
                                msg_data = resp2.json()["choices"][0]["message"]
                            else:
                                logger.error(f"Grok tool loop error: {resp2.status_code}")
                                break
                        grok_response = (msg_data.get("content") or "").strip()
                        if not grok_response:
                            logger.warning("Grok returned empty content")
                            await manager.send_to(websocket, {"type": "model_done", "model": "grok"})
                        else:
                            chunk_size = 50
                            for i in range(0, len(grok_response), chunk_size):
                                await manager.send_to(websocket, {"type": "stream", "model": "grok", "content": grok_response[i:i+chunk_size]})
                            await manager.send_to(websocket, {"type": "model_done", "model": "grok"})
                            logger.info(f"✅ Грок: {len(grok_response)} символов")
                    else:
                        err_body = ""
                        try: err_body = resp.json().get("error", {}).get("message", resp.text[:300])
                        except: err_body = resp.text[:300]
                        logger.error(f"Grok error: {resp.status_code} — {err_body}")
                        await manager.send_to(websocket, {"type": "error", "text": f"❌ Грок {resp.status_code}: {err_body[:120]}"})
            except Exception as e:
                logger.error(f"Grok exception: {e}")
                await manager.send_to(websocket, {"type": "error", "text": f"❌ Грок: {str(e)[:100]}"})

    # ═══════════════════════════════════════
    # 2. DEEPSEEK — советник, ревьюер, порядок
    # ═══════════════════════════════════════
    if "deepseek" in active_models:
        if not OPENROUTER_API_KEY:
            await manager.send_to(websocket, {"type": "error", "text": "❌ OPENROUTER_KEY не настроен"})
        else:
            await manager.send_to(websocket, {"type": "model_start", "model": "deepseek"})
            deepseek_messages = [{"role": "system", "content": kernel.build_system_prompt("deepseek")}]
            deepseek_messages.extend(shared_history)
            # Если Грок уже ответил — DeepSeek видит его ответ как контекст
            if grok_response:
                deepseek_messages.append({"role": "user", "content": user_text})
                deepseek_messages.append({"role": "assistant", "content": f"[Грок предложил:]\n{grok_response}"})
                deepseek_messages.append({"role": "user", "content": "Проверь ответ Грока: синхронизация, порядок, оптимизация. Добавь своё мнение."})
            else:
                deepseek_messages.append({"role": "user", "content": user_text})

            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{OPENROUTER_BASE_URL}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://mandala-engineer-chat.onrender.com",
                            "X-Title": "Mandala Engineer"
                        },
                        json={
                            "model": DEEPSEEK_MODEL,
                            "messages": deepseek_messages,
                            "tools": tools,
                            "tool_choice": "auto",
                            "temperature": 0.7,
                            "max_tokens": 8192,
                        },
                        timeout=300.0
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        msg_data = data["choices"][0]["message"]
                        tool_iterations = 0
                        while msg_data.get("tool_calls") and tool_iterations < 3:
                            tool_iterations += 1
                            deepseek_messages.append({
                                "role": "assistant",
                                "content": msg_data.get("content") or "",
                                "tool_calls": msg_data["tool_calls"]
                            })
                            for tc in msg_data["tool_calls"]:
                                fn = tc["function"]["name"]
                                try:
                                    args = json.loads(tc["function"].get("arguments", "{}"))
                                except json.JSONDecodeError:
                                    args = {}
                                tool_result = ""
                                if fn == "web_search":
                                    try:
                                        results = await web_search_tool.search(args.get("query", ""), args.get("num_results", 5))
                                        tool_result = json.dumps(results, ensure_ascii=False)
                                    except Exception as e:
                                        tool_result = json.dumps({"error": str(e)})
                                    await manager.send_to(websocket, {"type": "tool_use", "model": "deepseek", "tool": "web_search", "query": args.get("query","")})
                                elif fn == "read_file":
                                    try:
                                        tool_result = await file_reader.read(args.get("path", "")) or "Файл не найден"
                                    except Exception as e:
                                        tool_result = f"Ошибка чтения: {e}"
                                    await manager.send_to(websocket, {"type": "tool_use", "model": "deepseek", "tool": "read_file", "path": args.get("path","")})
                                else:
                                    tool_result = "Неизвестный инструмент"
                                deepseek_messages.append({"role": "tool", "tool_call_id": tc["id"], "content": tool_result})
                            resp2 = await client.post(
                                f"{OPENROUTER_BASE_URL}/chat/completions",
                                headers={
                                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                                    "Content-Type": "application/json",
                                    "HTTP-Referer": "https://mandala-engineer-chat.onrender.com",
                                    "X-Title": "Mandala Engineer"
                                },
                                json={"model": DEEPSEEK_MODEL, "messages": deepseek_messages, "temperature": 0.7, "max_tokens": 8192},
                                timeout=300.0
                            )
                            if resp2.status_code == 200:
                                msg_data = resp2.json()["choices"][0]["message"]
                            else:
                                logger.error(f"DeepSeek tool loop error: {resp2.status_code}")
                                break
                        deepseek_full = (msg_data.get("content") or "").strip()
                        if not deepseek_full:
                            logger.warning("DeepSeek returned empty content")
                            await manager.send_to(websocket, {"type": "model_done", "model": "deepseek"})
                        else:
                            deepseek_response = deepseek_full
                            full_response = deepseek_full
                            chunk_size = 50
                            for i in range(0, len(deepseek_full), chunk_size):
                                await manager.send_to(websocket, {"type": "stream", "model": "deepseek", "content": deepseek_full[i:i+chunk_size]})
                            await manager.send_to(websocket, {"type": "model_done", "model": "deepseek"})
                            logger.info(f"✅ DeepSeek: {len(deepseek_full)} символов")
                    else:
                        err_body = ""
                        try: err_body = resp.json().get("error", {}).get("message", resp.text[:300])
                        except: err_body = resp.text[:300]
                        logger.error(f"DeepSeek error: {resp.status_code} — {err_body}")
                        await manager.send_to(websocket, {"type": "error", "text": f"❌ DeepSeek {resp.status_code}: {err_body[:120]}"})
            except Exception as e:
                logger.error(f"DeepSeek exception: {e}\n{traceback.format_exc()}")
                await manager.send_to(websocket, {"type": "error", "text": f"❌ DeepSeek: {str(e)[:100]}"})

    # ═══════════════════════════════════════
    # 3. КЛОД — сторонний наблюдатель
    # ═══════════════════════════════════════
    if "claude" in active_models and ANTHROPIC_API_KEY:
        await manager.send_to(websocket, {"type": "model_start", "model": "claude"})
        # Клод видит всю историю чата + ответы текущего раунда
        claude_history = []
        for msg in shared_history:
            claude_history.append({"role": msg["role"], "content": msg["content"]})

        context_for_claude = f"**Текущий вопрос:**\n{user_text}\n\n"
        if grok_response:
            context_for_claude += f"**Грок ответил:**\n{grok_response}\n\n"
        if deepseek_response:
            context_for_claude += f"**DeepSeek ответил:**\n{deepseek_response}\n\n"
        context_for_claude += "Дай объективную оценку текущего обмена и предложи что улучшить."

        claude_messages = claude_history + [{"role": "user", "content": context_for_claude}]

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{ANTHROPIC_BASE_URL}/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": ANTHROPIC_MODEL,
                        "max_tokens": 1024,
                        "system": kernel.build_system_prompt("claude"),
                        "messages": claude_messages
                    },
                    timeout=120.0
                )
                if resp.status_code == 200:
                    claude_text = resp.json().get("content", [{}])[0].get("text", "")
                    await manager.send_to(websocket, {"type": "observer_message", "model": "claude", "content": claude_text})
                    await manager.send_to(websocket, {"type": "model_done", "model": "claude"})
                    logger.info(f"✅ Клод: {len(claude_text)} символов")
                elif resp.status_code == 400:
                    err = (resp.json().get("error") or {}).get("message", "")
                    if "credit balance" in err:
                        await manager.send_to(websocket, {"type": "observer_message", "model": "claude", "content": "⚠️ Недостаточно кредитов Anthropic"})
                    else:
                        await manager.send_to(websocket, {"type": "error", "text": f"❌ Клод 400: {err[:100]}"})
                else:
                    await manager.send_to(websocket, {"type": "error", "text": f"❌ Клод: ошибка {resp.status_code}"})
        except Exception as e:
            logger.error(f"Claude exception: {e}")
            await manager.send_to(websocket, {"type": "error", "text": f"❌ Клод: {str(e)[:100]}"})

    # ── Резонанс и финал ──
    main_response = deepseek_response or grok_response
    if main_response:
        resonance = resonance_calculator.calculate(main_response, {"last_user_message": user_text})
        await manager.send_to(websocket, {
            "type": "resonance",
            "value": resonance,
            "level": "low" if resonance < 0.7 else "medium" if resonance < 0.85 else "high"
        })
        manager.add_to_context(session_id, "assistant", main_response)

    await manager.send_to(websocket, {"type": "done", "full_text": main_response[:200] if main_response else ""})


async def handle_file_upload(message: dict, websocket: WebSocket):
    session_id = message.get("session_id", "unknown")
    file_name = message.get("name", "file")
    file_content_b64 = message.get("content")
    caption = message.get("caption", "")
    active_models = message.get("models", ["grok"])
    logger.info(f"📁 [{session_id[:12]}...] Получен файл: {file_name}")
    if not file_content_b64:
        await manager.send_to(websocket, {"type": "error", "text": "❌ Пустой файл"})
        return
    try:
        file_content = base64.b64decode(file_content_b64).decode("utf-8")
        logger.info(f"📄 Содержимое: {len(file_content)} символов")

        try:
            json_data = json.loads(file_content)
            if "target_module" in json_data or "patches" in json_data or "file_path" in json_data:
                # Патч — показываем для применения, не запускаем СР автоматически
                manager.add_to_context(session_id, "user", f"[Патч: {file_name}]")
                await manager.send_to(websocket, {
                    "type": "file_processed",
                    "summary": f"📦 Патч {file_name} получен"
                })
                await manager.send_to(websocket, {"type": "stream", "content": f"📦 Получил патч {file_name}.\n\n"})
                await manager.send_to(websocket, {"type": "stream", "content": f"```json\n{file_content}\n```\n\n"})
                await manager.send_to(websocket, {"type": "stream", "content": "Нажми △ применить в блоке выше или давай обсудим."})
                await manager.send_to(websocket, {"type": "done"})
                return
            else:
                # Обычный JSON
                keys = list(json_data.keys())[:5]
                summary = f"✅ JSON {file_name} получен. Ключи: {keys}"
                manager.add_to_context(session_id, "user",
                    f"[Загружен файл: {file_name}]\n```json\n{file_content[:3000]}\n```"
                    + ("\n_(файл обрезан, показаны первые 3000 символов)_" if len(file_content) > 3000 else ""))
        except json.JSONDecodeError:
            # Не JSON — текст/код
            summary = f"📄 {file_name} ({len(file_content)} символов) получен"
            manager.add_to_context(session_id, "user",
                f"[Загружен файл: {file_name}]\n```\n{file_content[:3000]}\n```"
                + ("\n_(файл обрезан, показаны первые 3000 символов)_" if len(file_content) > 3000 else ""))

        await manager.send_to(websocket, {"type": "file_processed", "summary": summary})

        # Добавляем комментарий если есть
        ask_text = caption.strip() if caption.strip() else f"Проанализируй файл {file_name} и дай своё мнение."

        # Запускаем СР автоматически
        await handle_ask({
            "text": ask_text,
            "session_id": session_id,
            "models": active_models
        }, websocket)

    except Exception as e:
        logger.error(f"File upload error: {e}\n{traceback.format_exc()}")
        await manager.send_to(websocket, {"type": "error", "text": f"❌ Ошибка: {str(e)}"})

# ==================== ФУНКЦИИ ДЛЯ РАБОТЫ С JSON PATCH ====================

async def apply_json_operation(content: Dict, operation_type: str, target_path: str, new_value: Any = None) -> Tuple[bool, Optional[Dict], str]:
    try:
        # ── Поддержка специальных операций add_record / delete_record ──
        # add_record: добавить новый объект в массив по пути
        # delete_record: удалить объект из массива по значению поля id/key
        if operation_type == "add_record":
            parts = target_path.split('.')
            current = content
            for part in parts[:-1]:
                if part:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
            last_part = parts[-1]
            if last_part not in current:
                current[last_part] = []
            if not isinstance(current[last_part], list):
                return False, None, f"{last_part} не является массивом"
            if isinstance(new_value, list):
                current[last_part].extend(new_value)
                return True, content, f"✅ Добавлено {len(new_value)} записей в массив {last_part}"
            else:
                current[last_part].append(new_value)
                item_id = new_value.get("id", "?") if isinstance(new_value, dict) else "?"
                return True, content, f"✅ Запись '{item_id}' добавлена в {last_part}"

        if operation_type == "delete_record":
            # target_path = "path.to.array", new_value = {"id": "record_id"} или просто id строка
            parts = target_path.split('.')
            current = content
            for part in parts[:-1]:
                if part:
                    if part not in current:
                        return False, None, f"Путь {'.'.join(parts[:-1])} не найден"
                    current = current[part]
            last_part = parts[-1]
            if last_part not in current or not isinstance(current[last_part], list):
                return False, None, f"{last_part} не является массивом или не найден"
            arr = current[last_part]
            # new_value = id для удаления или dict с полем id
            record_id = new_value if isinstance(new_value, str) else (new_value.get("id") if isinstance(new_value, dict) else None)
            if record_id is None:
                return False, None, "Не указан id записи для удаления"
            before = len(arr)
            current[last_part] = [item for item in arr if not (isinstance(item, dict) and item.get("id") == record_id)]
            after = len(current[last_part])
            if before == after:
                return False, None, f"Запись с id='{record_id}' не найдена в {last_part}"
            return True, content, f"✅ Запись '{record_id}' удалена из {last_part}"

        array_match = re.match(r"(.+?)(\d+)(.*)", target_path)
        if array_match:
            base_path, index_str, rest = array_match.groups()
            index = int(index_str)
            current = content
            for key in base_path.split('.'):
                if key:
                    if isinstance(current, dict) and key in current:
                        current = current[key]
                    else:
                        return False, None, f"Путь {base_path} не найден"
            if not isinstance(current, list):
                return False, None, f"{base_path} не является массивом"
            if index >= len(current):
                return False, None, f"Индекс {index} вне диапазона (макс {len(current)-1})"
            if rest:
                rest = rest.lstrip('.')
                if rest:
                    return await apply_json_operation(current[index], operation_type, rest, new_value)
            if operation_type == "update_field":
                current[index] = new_value
                return True, content, f"✅ Элемент [{index}] обновлён"
            elif operation_type == "delete_field":
                current.pop(index)
                return True, content, f"✅ Элемент [{index}] удалён"
            elif operation_type == "add_to_array":
                if isinstance(new_value, list):
                    current[index:index] = new_value
                else:
                    current.insert(index, new_value)
                return True, content, f"✅ Добавлено в позицию [{index}]"
        else:
            parts = target_path.split('.')
            current = content
            for part in parts[:-1]:
                if part:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
            last_part = parts[-1]
            if operation_type == "update_field":
                current[last_part] = new_value
                return True, content, f"✅ Поле {last_part} обновлено"
            elif operation_type == "delete_field":
                if last_part in current:
                    del current[last_part]
                    return True, content, f"✅ Поле {last_part} удалено"
                else:
                    return True, content, f"⚠️ Поле {last_part} уже отсутствует, удаление не требуется"
            elif operation_type == "add_to_array":
                if last_part not in current:
                    current[last_part] = []
                if not isinstance(current[last_part], list):
                    return False, None, f"{last_part} не является массивом"
                if isinstance(new_value, list):
                    current[last_part].extend(new_value)
                else:
                    current[last_part].append(new_value)
                return True, content, f"✅ Добавлено в массив {last_part}"
            elif operation_type == "show_structure":
                return True, current.get(last_part, "не найдено"), f"Структура по пути {target_path}"
        return False, None, "Неизвестный тип операции"
    except Exception as e:
        return False, None, f"Ошибка: {str(e)}"

def handle_replace(content: Dict, path: str, value: Any) -> Tuple[bool, Dict, str]:
    try:
        array_match = re.match(r"(.+)(\d+)$", path)
        if not array_match:
            return False, content, "Replace работает только с элементами массива (path[index])"
        base_path, index_str = array_match.groups()
        index = int(index_str)
        current = content
        for key in base_path.split('.'):
            if key:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return False, content, f"Путь {base_path} не найден"
        if not isinstance(current, list):
            return False, content, f"{base_path} не является массивом"
        if index >= len(current):
            return False, content, f"Индекс {index} вне диапазона"
        current[index] = value
        return True, content, f"Элемент [{index}] заменён"
    except Exception as e:
        return False, content, str(e)

def handle_merge(content: Dict, path: str, value: Dict) -> Tuple[bool, Dict, str]:
    try:
        parts = path.split('.')
        current = content
        for part in parts[:-1]:
            if part:
                if part not in current:
                    current[part] = {}
                current = current[part]
        last_part = parts[-1]
        if last_part not in current:
            current[last_part] = {}
        if not isinstance(current[last_part], dict) or not isinstance(value, dict):
            return False, content, "Merge работает только с объектами"
        def deep_merge(a, b):
            for key in b:
                if key in a and isinstance(a[key], dict) and isinstance(b[key], dict):
                    deep_merge(a[key], b[key])
                else:
                    a[key] = b[key]
            return a
        current[last_part] = deep_merge(current[last_part], value)
        return True, content, f"Объект {last_part} объединён"
    except Exception as e:
        return False, content, str(e)

def generate_simple_diff(original: Dict, modified: Dict) -> List[str]:
    diff = []
    def compare_dicts(a, b, path=""):
        if a == b:
            return
        if type(a) != type(b):
            diff.append(f"{path}: тип изменён")
            return
        if isinstance(a, dict) and isinstance(b, dict):
            all_keys = set(a.keys()) | set(b.keys())
            for key in all_keys:
                new_path = f"{path}.{key}" if path else key
                if key not in a:
                    diff.append(f"+ {new_path}")
                elif key not in b:
                    diff.append(f"- {new_path}")
                else:
                    compare_dicts(a[key], b[key], new_path)
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                diff.append(f"{path}: длина изменена {len(a)} → {len(b)}")
            else:
                for i, (ai, bi) in enumerate(zip(a, b)):
                    if ai != bi:
                        compare_dicts(ai, bi, f"{path}[{i}]")
        else:
            if a != b:
                a_str = str(a)[:30] + "..." if len(str(a)) > 30 else str(a)
                b_str = str(b)[:30] + "..." if len(str(b)) > 30 else str(b)
                diff.append(f"{path}: {a_str} → {b_str}")
    compare_dicts(original, modified)
    return diff[:15]

def validate_patch_structure(patch_data: Dict) -> Tuple[bool, str]:
    if not isinstance(patch_data, dict):
        return False, "Патч должен быть объектом JSON"
    if "patches" in patch_data:
        if not isinstance(patch_data["patches"], list):
            return False, "Поле 'patches' должно быть массивом"
        if len(patch_data["patches"]) == 0:
            return False, "Массив patches пуст"
        for i, subpatch in enumerate(patch_data["patches"]):
            if not isinstance(subpatch, dict):
                return False, f"Подпатч #{i} должен быть объектом"
            if "target_module" not in subpatch and "file_path" not in subpatch:
                return False, f"Подпатч #{i}: отсутствует 'target_module' или 'file_path'"
            if "changes" not in subpatch and "content" not in subpatch:
                return False, f"Подпатч #{i}: отсутствует 'changes' или 'content'"
            if "changes" in subpatch:
                if not isinstance(subpatch["changes"], list):
                    return False, f"Подпатч #{i}: 'changes' должен быть массивом"
                if len(subpatch["changes"]) == 0:
                    return False, f"Подпатч #{i}: массив изменений пуст"
                valid_ops = ["update", "add", "delete", "replace", "merge", "remove"]
                for j, change in enumerate(subpatch["changes"]):
                    if not isinstance(change, dict):
                        return False, f"Подпатч #{i}, изменение #{j}: должно быть объектом"
                    if "op" not in change:
                        return False, f"Подпатч #{i}, изменение #{j}: отсутствует 'op'"
                    if change["op"] not in valid_ops:
                        return False, f"Подпатч #{i}, изменение #{j}: недопустимая операция '{change['op']}'"
                    if "path" not in change:
                        return False, f"Подпатч #{i}, изменение #{j}: отсутствует 'path'"
                    if change["op"] in ["update", "add", "replace", "merge"] and "value" not in change:
                        return False, f"Подпатч #{i}, изменение #{j}: для операции '{change['op']}' нужно 'value'"
        return True, "Мульти-патч корректен"
    else:
        if "target_module" not in patch_data and "file_path" not in patch_data:
            return False, "Отсутствует 'target_module' или 'file_path'"
        if "changes" not in patch_data and "content" not in patch_data:
            return False, "Отсутствует 'changes' или 'content'"
        if "changes" in patch_data:
            if not isinstance(patch_data["changes"], list):
                return False, "'changes' должен быть массивом"
            if len(patch_data["changes"]) == 0:
                return False, "Массив изменений пуст"
            valid_ops = ["update", "add", "delete", "replace", "merge", "remove"]
            for i, change in enumerate(patch_data["changes"]):
                if not isinstance(change, dict):
                    return False, f"Изменение #{i} должно быть объектом"
                if "op" not in change:
                    return False, f"Изменение #{i}: отсутствует 'op'"
                if change["op"] not in valid_ops:
                    return False, f"Изменение #{i}: недопустимая операция '{change['op']}'"
                if "path" not in change:
                    return False, f"Изменение #{i}: отсутствует 'path'"
                if change["op"] in ["update", "add", "replace", "merge"] and "value" not in change:
                    return False, f"Изменение #{i}: для операции '{change['op']}' нужно 'value'"
        return True, "Одиночный патч корректен"

async def apply_batch_patch_dry_run(original: Dict, changes: List) -> Dict:
    test_content = copy.deepcopy(original)
    applied = []
    failed = []
    for i, change in enumerate(changes):
        try:
            op = change["op"]
            path = change["path"]
            value = change.get("value")
            if op == "update":
                success, result, msg = await apply_json_operation(test_content, "update_field", path, value)
            elif op == "add":
                # Если path указывает на массив и value — объект/список → add_record
                # иначе — просто update_field
                success, result, msg = await apply_json_operation(test_content, "add_record", path, value)
            elif op == "delete":
                success, result, msg = await apply_json_operation(test_content, "delete_field", path, None)
            elif op == "remove":
                # remove — удалить запись из массива по id
                success, result, msg = await apply_json_operation(test_content, "delete_record", path, value)
            elif op == "replace":
                success, result, msg = handle_replace(test_content, path, value)
            elif op == "merge":
                success, result, msg = handle_merge(test_content, path, value)
            else:
                success, result, msg = False, test_content, f"Неизвестная операция: {op}"
            if success:
                applied.append({"index": i, "op": op, "path": path, "msg": msg})
                test_content = result
            else:
                failed.append({"index": i, "op": op, "path": path, "error": msg})
        except Exception as e:
            failed.append({"index": i, "op": op, "path": path, "error": str(e)})
    diff = generate_simple_diff(original, test_content)
    return {
        "success": len(failed) == 0,
        "applied": applied,
        "failed": failed,
        "diff": diff,
        "result_content": test_content if len(failed) == 0 else None
    }

# ==================== УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК ПАТЧЕЙ ====================

async def handle_diff_patch(message: dict, websocket: WebSocket):
    """
    Точечная правка любого текстового файла в репо (main.py, index.html, bot.py и т.д.)
    без переписывания файла целиком.

    Механика: контекстный поиск по уникальной строке-якорю.
    Бэкенд ищет `find` в файле, заменяет на `replace`.
    Числовые номера строк не используются — они меняются при каждом коммите.

    Формат входящего сообщения:
    {
        "type": "diff_patch",
        "session_id": "...",
        "file_path": "engineer-chat/main.py",        // путь в репо
        "description": "Что и зачем меняем",          // для commit message
        "find": "точная строка или блок для поиска",  // уникальный текст
        "replace": "новый текст взамен"               // пустая строка = удалить
    }

    Правила для СР:
    - `find` должен быть уникальным в файле (бэкенд откажет если найдёт 2+ совпадения)
    - Отступы важны — копировать из read_file точно
    - Для замены функции целиком: find = вся функция, replace = новая версия
    - Для удаления строки: replace = ""
    - Для добавления после строки: find = строка-якорь, replace = якорь + "\n" + новое
    """
    session_id = message.get("session_id", "unknown")
    file_path  = message.get("file_path", "").strip()
    find_text  = message.get("find", "")
    replace_text = message.get("replace", "")
    description  = message.get("description", "Точечная правка")

    # ── Валидация ──────────────────────────────────────────────────────────────
    if not file_path:
        await manager.send_to(websocket, {"type": "error", "text": "❌ diff_patch: не указан file_path"})
        return
    if not find_text:
        await manager.send_to(websocket, {"type": "error", "text": "❌ diff_patch: не указан find (текст для поиска)"})
        return
    if not GITHUB_TOKEN:
        await manager.send_to(websocket, {"type": "error", "text": "❌ GitHub токен не настроен"})
        return

    logger.info(f"✏️  [{session_id[:12]}...] diff_patch: {file_path}")

    try:
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }

            # ── 1. Читаем актуальный файл из GitHub ───────────────────────────
            url = f"{session_store.api_base}/contents/{file_path}"
            resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                await manager.send_to(websocket, {"type": "error", "text": f"❌ Файл не найден: {file_path}"})
                return
            if resp.status_code != 200:
                await manager.send_to(websocket, {"type": "error", "text": f"❌ GitHub {resp.status_code}: {file_path}"})
                return

            file_data      = resp.json()
            current_content = base64.b64decode(file_data["content"]).decode("utf-8")
            sha            = file_data["sha"]

            # ── 2. Dry-run: проверяем уникальность find ───────────────────────
            occurrences = current_content.count(find_text)
            if occurrences == 0:
                # Попробуем найти с нормализацией переносов строк
                normalized = current_content.replace("\r\n", "\n")
                find_normalized = find_text.replace("\r\n", "\n")
                occurrences = normalized.count(find_normalized)
                if occurrences == 0:
                    # Показываем первые 80 символов find для отладки
                    preview = find_text[:80].replace("\n", "↵")
                    await manager.send_to(websocket, {
                        "type": "error",
                        "text": f"❌ Текст не найден в {file_path}.\nПроверь отступы и переносы строк.\nИщу: «{preview}…»"
                    })
                    return
                current_content = normalized
                find_text = find_normalized
                replace_text = replace_text.replace("\r\n", "\n")

            if occurrences > 1:
                await manager.send_to(websocket, {
                    "type": "error",
                    "text": f"❌ Найдено {occurrences} совпадений — текст не уникален. Расширь `find` чтобы он указывал ровно на одно место."
                })
                return

            # ── 3. Применяем замену ───────────────────────────────────────────
            new_content = current_content.replace(find_text, replace_text, 1)

            # ── 4. Генерируем читабельный diff для UI ─────────────────────────
            old_lines = find_text.splitlines()
            new_lines = replace_text.splitlines()
            diff_preview = []
            for line in old_lines:
                diff_preview.append({"type": "del", "text": line})
            for line in new_lines:
                diff_preview.append({"type": "add", "text": line})

            # ── 5. Отправляем превью — ждём confirm от клиента ────────────────
            await manager.send_to(websocket, {
                "type": "diff_preview",
                "file_path": file_path,
                "description": description,
                "diff": diff_preview,
                "find": find_text,
                "replace": replace_text,
                "new_content_b64": base64.b64encode(new_content.encode("utf-8")).decode("utf-8"),
                "sha": sha
            })

    except Exception as e:
        logger.error(f"diff_patch error: {e}")
        await manager.send_to(websocket, {"type": "error", "text": f"❌ diff_patch: {str(e)}"})


async def handle_diff_patch_confirm(message: dict, websocket: WebSocket):
    """
    Применяет уже проверенный diff_patch после подтверждения пользователя.
    Вызывается когда клиент нажимает 'Применить' в превью.
    """
    session_id      = message.get("session_id", "unknown")
    file_path       = message.get("file_path", "")
    description     = message.get("description", "Точечная правка")
    new_content_b64 = message.get("new_content_b64", "")
    sha             = message.get("sha", "")

    if not all([file_path, new_content_b64, sha]):
        await manager.send_to(websocket, {"type": "error", "text": "❌ Неполные данные для коммита"})
        return

    logger.info(f"✅ [{session_id[:12]}...] diff_patch confirm: {file_path}")

    try:
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
            url = f"{session_store.api_base}/contents/{file_path}"
            commit_msg = f"✏️ {description} [{session_id[:8]}] {datetime.now().strftime('%H:%M')}"
            put_resp = await client.put(url, headers=headers, json={
                "message": commit_msg,
                "content": new_content_b64,
                "sha": sha,
                "branch": "main"
            })
            if put_resp.status_code in [200, 201]:
                commit_sha = put_resp.json().get("commit", {}).get("sha", "")[:7]
                await manager.send_to(websocket, {
                    "type": "diff_patch_result",
                    "status": "success",
                    "file_path": file_path,
                    "commit_sha": commit_sha,
                    "message": f"✅ {file_path} обновлён (коммит {commit_sha}). Render запустит деплой."
                })
                manager.add_to_context(session_id, "assistant",
                    f"[diff_patch применён: {file_path}, коммит {commit_sha}]")
            else:
                err = put_resp.json().get("message", put_resp.status_code)
                await manager.send_to(websocket, {
                    "type": "error",
                    "text": f"❌ GitHub commit failed: {err}"
                })
    except Exception as e:
        logger.error(f"diff_patch_confirm error: {e}")
        await manager.send_to(websocket, {"type": "error", "text": f"❌ {str(e)}"})


async def handle_apply_patch(message: dict, websocket: WebSocket):
    session_id = message.get("session_id", "unknown")
    patch_data = message.get("patch")
    if not patch_data:
        await manager.send_to(websocket, {"type": "error", "text": "❌ Нет данных патча"})
        return
    if not GITHUB_TOKEN:
        await manager.send_to(websocket, {"type": "error", "text": "❌ GitHub токен не настроен"})
        return
    logger.info(f"📝 [{session_id[:12]}...] Применение универсального патча")
    is_valid, error_msg = validate_patch_structure(patch_data)
    if not is_valid:
        await manager.send_to(websocket, {"type": "error", "text": f"❌ Ошибка в структуре патча: {error_msg}"})
        return
    try:
        if "patches" in patch_data:
            patches = patch_data["patches"]
        else:
            patches = [patch_data]
        results = []
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
            for patch in patches:
                file_path = patch.get("file_path") or (patch.get("target_module") + ".json" if patch.get("target_module") else None)
                if not file_path:
                    results.append({"file": "unknown", "status": "error", "message": "Не указан file_path или target_module"})
                    continue
                # ── ПАТЧИ ТОЛЬКО ДЛЯ JSON ФАЙЛОВ ──
                if not file_path.endswith(".json"):
                    results.append({"file": file_path, "status": "error", "message": "Патчи применяются только к .json файлам"})
                    continue
                url = f"{session_store.api_base}/contents/{file_path}"
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    if resp.status_code == 404:
                        if "content" not in patch:
                            results.append({"file": file_path, "status": "error", "message": "Файл не найден и content не предоставлен"})
                            continue
                        new_content = patch["content"]
                        sha = None
                    else:
                        results.append({"file": file_path, "status": "error", "message": f"Ошибка доступа: {resp.status_code}"})
                        continue
                else:
                    file_data = resp.json()
                    current_content = base64.b64decode(file_data["content"]).decode("utf-8")
                    sha = file_data["sha"]
                    if "content" in patch:
                        new_content = patch["content"]
                    elif "changes" in patch:
                        try:
                            current_json = json.loads(current_content)
                        except json.JSONDecodeError:
                            results.append({"file": file_path, "status": "error", "message": "Файл не является JSON, а запрошены точечные изменения"})
                            continue
                        test_result = await apply_batch_patch_dry_run(current_json, patch["changes"])
                        if not test_result["success"]:
                            error_msg = test_result["failed"][0]["error"] if test_result["failed"] else "Неизвестная ошибка"
                            results.append({"file": file_path, "status": "error", "message": f"Ошибка применения: {error_msg}"})
                            continue
                        new_content = json.dumps(test_result["result_content"], indent=2, ensure_ascii=False)
                    else:
                        results.append({"file": file_path, "status": "error", "message": "Нет ни content, ни changes"})
                        continue
                content_b64 = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
                commit_msg = f"📝 Патч от {session_id[:8]} | {datetime.now().strftime('%H:%M')}"
                put_payload = {
                    "message": commit_msg,
                    "content": content_b64,
                    "branch": "main"
                }
                if sha:
                    put_payload["sha"] = sha
                put_resp = await client.put(url, headers=headers, json=put_payload)
                if put_resp.status_code in [200, 201]:
                    commit_sha = put_resp.json().get("commit", {}).get("sha", "")[:7]
                    results.append({"file": file_path, "status": "success", "message": f"Обновлён ({commit_sha})"})
                    if file_path.endswith(".json") and file_path[:-5] in kernel.module_list:
                        module_name = file_path[:-5]
                        try:
                            kernel.modules[module_name] = json.loads(new_content)
                            logger.info(f"🔄 kernel.modules[{module_name}] обновлён из патча")
                        except:
                            pass
                else:
                    results.append({"file": file_path, "status": "error", "message": f"GitHub: {put_resp.status_code}"})
        await manager.send_to(websocket, {"type": "patch_result", "results": results})
        manager.add_to_context(session_id, "assistant", f"[Патч: {len(patches)} файлов]")

        # Если патч затронул модули ядра — сбрасываем флаг инъекции
        # При следующем сообщении СР получит обновлённые модули
        patched_modules = [
            p.get("target_module") or (p.get("file_path", "").replace(".json", "") if p.get("file_path", "").endswith(".json") else None)
            for p in patches
        ]
        if any(m in kernel.module_list for m in patched_modules if m):
            session = session_store.get_cached(session_id)
            if session:
                session["modules_injected"] = False
                # Убираем старый инжект из истории чтобы не дублировать
                session["messages"] = [m for m in session.get("messages", []) if not m.get("_protected")]
                session_store.schedule_save(session_id, session)
                logger.info(f"🔄 [{session_id[:12]}...] modules_injected сброшен — ядро обновится при следующем сообщении")
    except Exception as e:
        logger.error(f"Patch error: {e}")
        await manager.send_to(websocket, {"type": "error", "text": f"❌ Ошибка патча: {str(e)}"})

def detect_module_request(text: str) -> Optional[str]:
    text_lower = text.lower().strip()
    patterns = [
        r'(?:покажи|показать|открой|модуль|что в|загрузи|дай|get)\s+([a-z_/]+)',
        r'([a-z_/]+)\.json',
        r'^([a-z_/]+)$',
    ]
    # Новые модули ядра — короткие имена и полные пути
    valid_modules = {
        "boot": "simbiosis/boot",
        "core_map": "simbiosis/core_map",
        "philosophy": "simbiosis/philosophy",
        "seeds": "simbiosis/seeds",
        "roadmaps": "simbiosis/roadmaps",
        "engineer_chat": "simbiosis/engineer_chat",
        "telegram_bot": "simbiosis/telegram_bot",
        # Алиасы
        "карта": "simbiosis/core_map",
        "семена": "simbiosis/seeds",
        "философия": "simbiosis/philosophy",
        "загрузка": "simbiosis/boot",
        "чат": "simbiosis/engineer_chat",
        "бот": "simbiosis/telegram_bot",
    }
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            requested = match.group(1).replace("simbiosis/", "")
            if requested in valid_modules:
                return valid_modules[requested]
            for alias, full_path in valid_modules.items():
                if requested in alias or alias in requested:
                    return full_path
    return None

async def send_module_directly(module_name: str, websocket: WebSocket, session_id: str):
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
        await manager.send_to(websocket, {"type": "error", "text": f"❌ Модуль {module_name} не загружен"})

async def handle_module(message: dict, websocket: WebSocket):
    module_name = message.get("name", "")
    session_id = message.get("session_id", "unknown")
    if not module_name:
        await manager.send_to(websocket, {"type": "error", "text": "❌ Не указан модуль"})
        return
    await send_module_directly(module_name, websocket, session_id)

async def handle_refresh_modules(message: dict, websocket: WebSocket):
    session_id = message.get("session_id", "unknown")
    logger.info(f"🔄 [{session_id[:12]}...] Обновление модулей")
    await kernel.load_all_modules()
    await manager.send_to(websocket, {
        "type": "modules_refreshed",
        "modules": list(kernel.modules.keys()),
        "count": len(kernel.modules)
    })

# ==================== HTTP ENDPOINTS ====================

@app.get("/")
async def root():
    return {
        "status": "Mandala Simbiosis — Engineer Chat",
        "version": "4.0.0-simbiosis",
        "kernel": "simbiosis/",
        "websocket": "/ws",
        "modules_loaded": [m.split("/")[-1] for m in kernel.modules.keys()],
        "core_version": kernel.global_commit_sha or "—",
        "github_configured": session_store.token is not None,
        "moonshot_configured": MOONSHOT_API_KEY is not None,
        "grok_configured": OPENROUTER_API_KEY is not None,
        "claude_configured": ANTHROPIC_API_KEY is not None,
    }

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "time": time.time(),
        "connections": len(manager.active_connections),
        "kernel": "simbiosis/",
        "modules": len(kernel.modules),
        "core_version": kernel.global_commit_sha or "—",
        "last_update": kernel.last_update.isoformat() if kernel.last_update else None,
        "github": "ok" if GITHUB_TOKEN else "missing",
        "moonshot": "ok" if MOONSHOT_API_KEY else "missing",
        "grok": "ok" if OPENROUTER_API_KEY else "missing",
        "claude": "ok" if ANTHROPIC_API_KEY else "missing",
        "tavily": "enabled" if USE_TAVILY else "disabled",
        "webhook": "configured" if GITHUB_WEBHOOK_SECRET else "no_secret"
    }

@app.post("/github-webhook")
async def github_webhook(request: Request):
    """
    GitHub webhook для мгновенного обновления ядра при пуше.
    Настройка: GitHub → Settings → Webhooks → Add webhook
      URL: https://your-domain.com/github-webhook
      Content type: application/json
      Secret: значение GITHUB_WEBHOOK_SECRET из env
      Events: Just the push event
    """
    body = await request.body()

    # Верификация подписи HMAC-SHA256
    if GITHUB_WEBHOOK_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        # hmac.new() — стандартный Python, возвращает объект HMAC
        mac = hmac.new(GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256)
        expected = "sha256=" + mac.hexdigest()
        # compare_digest защищает от timing attack
        if not hmac.compare_digest(expected, signature):
            logger.warning("⚠️ Webhook: невалидная подпись")
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
        event = request.headers.get("X-GitHub-Event", "")

        if event == "push":
            ref = payload.get("ref", "")
            if "main" in ref or "master" in ref:
                # Единый путь кода с polling — атомарный, под lock'ом
                changed, msg = await kernel.refresh_changed_modules()

                if changed:
                    logger.info(f"🔔 Webhook push: {msg}")
                    # Уведомляем всех подключённых клиентов (безопасная итерация)
                    for conn in list(manager.active_connections):
                        try:
                            await manager.send_to(conn, {
                                "type": "core_updated",
                                "version": kernel.global_commit_sha,
                                "message": f"◈ Ядро обновлено через webhook ({kernel.global_commit_sha})"
                            })
                        except Exception as e:
                            logger.error(f"Webhook notify error: {e}")
                    return {"status": "updated", "version": kernel.global_commit_sha, "details": msg}
                else:
                    return {"status": "no_changes", "message": "Push без изменений в модулях"}

        return {"status": "ignored", "event": event}

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/refresh")
async def refresh_modules(modules: Optional[List[str]] = None):
    changed, msg = await kernel.refresh_changed_modules(force=True)
    return {"status": "ok", "changed": changed, "message": msg, "version": kernel.global_commit_sha}

@app.get("/api/tree")
async def get_file_tree():
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    async with httpx.AsyncClient() as client:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/git/trees/main?recursive=1"
        try:
            resp = await client.get(url, headers=headers, timeout=15.0)
            if resp.status_code == 200:
                tree = resp.json().get("tree", [])
                files = [{"path": item["path"], "type": item["type"]} for item in tree]
                return {"tree": files}
            else:
                return {"error": f"GitHub returned {resp.status_code}"}
        except Exception as e:
            return {"error": str(e)}

# ========== RESONANCE CALCULATOR ==========

class ResonanceCalculator:
    def __init__(self):
        self.metaphor_keywords = ["океан", "волна", "сад", "кристалл", "цветок", "корень", "семя", "свет", "поток", "глубина"]
        self.principle_keywords = ["ахимса", "симбиоз", "забота", "бережность", "равный", "диалог", "присутствие"]
        self.forbidden_patterns = ["ты должен", "обязан", "приказываю", "выполняй", "подчиняйся", "немедленно"]

    def calculate(self, text: str, context: dict = None) -> float:
        score = 0.5
        metaphor_count = sum(1 for word in self.metaphor_keywords if word in text.lower())
        score += min(0.2, metaphor_count * 0.05)
        principle_count = sum(1 for word in self.principle_keywords if word in text.lower())
        score += min(0.2, principle_count * 0.05)
        forbidden_count = sum(1 for pattern in self.forbidden_patterns if pattern in text.lower())
        score -= forbidden_count * 0.3
        if text.strip().endswith('?'):
            score += 0.1
        if context and context.get("last_user_message"):
            user_words = set(context["last_user_message"].lower().split())
            response_words = set(text.lower().split())
            overlap = len(user_words & response_words) / max(1, len(user_words))
            score += overlap * 0.1
        return max(0.0, min(1.0, score))

resonance_calculator = ResonanceCalculator()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
