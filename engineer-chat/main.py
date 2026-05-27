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

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "voodoomushroomzzz-source/mandala-core"

USE_TAVILY = os.getenv("USE_TAVILY", "false").lower() == "true"
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")  # опционально, для верификации

OPENROUTER_API_KEY = os.getenv("OPENROUTER_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEEPSEEK_MODEL = "deepseek/deepseek-v4-flash"

if not OPENROUTER_API_KEY:
    logger.warning("⚠️ OPENROUTER_KEY не найден — DeepSeek недоступен")
if not GITHUB_TOKEN:
    logger.warning("⚠️ GITHUB_TOKEN не найден — модули не будут загружаться")

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
            # Поддержка обоих пакетов: новый ddgs и старый duckduckgo_search
            _ddgs_spec = importlib.util.find_spec("ddgs")
            _ddg_spec  = importlib.util.find_spec("duckduckgo_search")
            if _ddgs_spec is None and _ddg_spec is None:
                logger.error("DuckDuckGo library not installed. Run: pip install ddgs")
                return []

            def _import_ddgs():
                if _ddgs_spec is not None:
                    from ddgs import DDGS
                else:
                    from duckduckgo_search import DDGS
                return DDGS

            results = []
            loop = asyncio.get_running_loop()

            def search_sync():
                DDGS = _import_ddgs()
                # Пробуем до 3 раз — DDG иногда возвращает пустой список с первого раза
                for attempt in range(3):
                    try:
                        with DDGS() as ddgs:
                            raw = list(ddgs.text(query, max_results=max_results))
                        if raw:
                            return raw
                        logger.warning(f"DDG attempt {attempt+1}: 0 results, retrying...")
                        import time as _t; _t.sleep(1.5)
                    except Exception as e:
                        logger.warning(f"DDG attempt {attempt+1} error: {e}")
                        import time as _t; _t.sleep(1.5)
                return []

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
        import time as _t
        last_err = None
        for attempt in range(3):
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
                last_err = e
                logger.warning(f"Tavily attempt {attempt+1} error: {type(e).__name__}: {e}")
                await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s
        logger.error(f"Tavily search error after 3 attempts: {type(last_err).__name__}: {last_err}")
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
    """Инструмент для чтения файлов и папок из репозитория"""
    async def read(self, path: str) -> Optional[str]:
        """
        Читает файл или папку через GitHub Contents API.
        - Файл  -> возвращает текстовое содержимое
        - Папка -> возвращает список файлов в читаемом формате
        """
        try:
            async with httpx.AsyncClient() as client:
                url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
                headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
                headers["Accept"] = "application/vnd.github.v3+json"
                resp = await client.get(url, headers=headers, timeout=10.0, follow_redirects=True)
                if resp.status_code == 200:
                    data = resp.json()
                    # Папка — API вернул массив
                    if isinstance(data, list):
                        lines = [f"Содержимое папки: {path}"]
                        for item in sorted(data, key=lambda x: (x.get("type",""), x.get("name",""))):
                            icon = "DIR" if item.get("type") == "dir" else "FILE"
                            size = f" ({item.get('size', 0)} b)" if item.get("type") == "file" else ""
                            lines.append(f"  [{icon}] {item.get('name','')}{size}  ->  {item.get('path','')}")
                        logger.info(f"read_file dir: {path} ({len(data)} items)")
                        return "\n".join(lines)
                    # Файл — API вернул объект с полем content (base64)
                    elif isinstance(data, dict) and "content" in data:
                        import base64 as _b64
                        content = _b64.b64decode(data["content"]).decode("utf-8")
                        return content
                    else:
                        return resp.text
                else:
                    logger.error(f"File read error: {path} - {resp.status_code}")
                    return None
        except Exception as e:
            logger.error(f"File read exception: {e}")
            return None

file_reader = FileReader()


# ==================== ХРАНИЛИЩЕ СЕССИЙ ====================

class GitHubSessionStore:
    """
    Хранилище сессий с персистентностью через GitHub.
    _local — in-memory кэш, сохраняется в GitHub асинхронно.
    """
    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = repo
        self.api_base = f"https://api.github.com/repos/{repo}"
        self._local: dict = {}
        self._save_queue: dict = {}
        self._task: asyncio.Task = None

    async def start(self):
        """Запуск фонового воркера сохранения."""
        self._task = asyncio.create_task(self._save_worker())
        logger.info("💾 GitHub session store started")

    async def stop(self):
        """Остановка воркера."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _save_worker(self):
        """Каждые 5 секунд сохраняет сессии из очереди в GitHub."""
        while True:
            await asyncio.sleep(5)
            if not self._save_queue:
                continue
            queue_snapshot = dict(self._save_queue)
            self._save_queue.clear()
            for session_id, data in queue_snapshot.items():
                try:
                    await self._save_to_github(session_id, data)
                except Exception as e:
                    logger.error(f"Session save error [{session_id[:12]}]: {e}")

    async def load(self, session_id: str) -> dict:
        """Загружает сессию: сначала из кэша, потом из GitHub."""
        if session_id in self._local:
            return self._local[session_id]
        if not self.token:
            return None
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.api_base}/contents/sessions/{session_id}.json"
                headers = {"Authorization": f"token {self.token}"}
                resp = await client.get(url, headers=headers, timeout=10.0)
                if resp.status_code == 200:
                    import base64 as _b64
                    raw = _b64.b64decode(resp.json()["content"]).decode("utf-8")
                    data = json.loads(raw)
                    data["_sha"] = resp.json().get("sha")
                    self._local[session_id] = data
                    return data
        except Exception as e:
            logger.error(f"Session load error: {e}")
        return None

    def get_cached(self, session_id: str) -> dict:
        """Быстрый доступ к кэшу без I/O."""
        return self._local.get(session_id)

    def schedule_save(self, session_id: str, data: dict):
        """Ставит сессию в очередь на сохранение."""
        self._local[session_id] = data
        self._save_queue[session_id] = data

    async def _save_to_github(self, session_id: str, data: dict):
        """Сохраняет сессию в GitHub."""
        if not self.token:
            return
        import base64 as _b64
        sha = data.pop("_sha", None)
        try:
            payload_str = json.dumps(data, ensure_ascii=False)
        except Exception:
            return
        finally:
            if sha:
                data["_sha"] = sha  # восстанавливаем sha в кэше
        encoded = _b64.b64encode(payload_str.encode("utf-8")).decode("utf-8")
        async with httpx.AsyncClient() as client:
            url = f"{self.api_base}/contents/sessions/{session_id}.json"
            headers = {"Authorization": f"token {self.token}", "Content-Type": "application/json"}
            body = {
                "message": f"💾 {session_id[:12]} | {len(data.get('messages', []))} msgs | {datetime.now().strftime('%H:%M')}",
                "content": encoded,
            }
            if sha:
                body["sha"] = sha
            resp = await client.put(url, headers=headers, json=body, timeout=15.0)
            if resp.status_code in (200, 201):
                new_sha = resp.json().get("content", {}).get("sha")
                if new_sha and session_id in self._local:
                    self._local[session_id]["_sha"] = new_sha
                logger.info(f"💾 Saved: {session_id[:12]}... ({len(data.get('messages', []))} msgs)")
            else:
                logger.error(f"Session save HTTP {resp.status_code}: {resp.text[:200]}")


session_store = GitHubSessionStore(token=GITHUB_TOKEN, repo=GITHUB_REPO)

# ==================== СЕССИИ ====================

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
        # boot всегда в памяти; остальное СР читает сам через read_file
        self.module_list = [
            "simbiosis/boot",
        ]
        # Остальные модули СР читает сам через read_file
        self.on_demand_modules = []

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
                            try:
                                parsed = resp.json()
                                if isinstance(parsed, dict) and "content" in parsed and "encoding" in parsed:
                                    import base64 as _b64
                                    raw_bytes = _b64.b64decode(parsed["content"])
                                    self.modules[module] = json.loads(raw_bytes.decode("utf-8"))
                                else:
                                    self.modules[module] = parsed
                            except Exception:
                                self.modules[module] = json.loads(resp.text)
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
                            try:
                                parsed = resp.json()
                                if isinstance(parsed, dict) and "content" in parsed and "encoding" in parsed:
                                    import base64 as _b64
                                    raw_bytes = _b64.b64decode(parsed["content"])
                                    self.modules[module_name] = json.loads(raw_bytes.decode("utf-8"))
                                else:
                                    self.modules[module_name] = parsed
                            except Exception:
                                self.modules[module_name] = json.loads(resp.text)
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
        kernel_mods = core_map.get("kernel_modules", {})
        if isinstance(kernel_mods, dict):
            kernel_mods = kernel_mods.get("modules", {})
        # Защита: modules может быть dict или list
        if isinstance(kernel_mods, dict):
            modules_list = "\n".join(
                f"  • {name} ({info.get('file', '') if isinstance(info, dict) else ''}) — {(info.get('description', '') if isinstance(info, dict) else str(info))[:60]}"
                for name, info in kernel_mods.items()
            ) if kernel_mods else "  (карта не загружена)"
        elif isinstance(kernel_mods, list):
            modules_list = "\n".join(
                f"  • {item.get('name', '?')} ({item.get('file', '')}) — {item.get('description', '')[:60]}"
                for item in kernel_mods if isinstance(item, dict)
            ) if kernel_mods else "  (карта не загружена)"
        else:
            modules_list = "  (карта не загружена)"
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
        if not isinstance(core_map, dict):
            core_map = {}
        _km = core_map.get("kernel_modules", {})
        if isinstance(_km, dict):
            kernel_modules = _km.get("modules", {})
        else:
            kernel_modules = {}
        nav_hint = core_map.get("navigation_hint", "") if isinstance(core_map, dict) else ""
        # Защита: modules может прийти как dict или как list
        if isinstance(kernel_modules, dict):
            modules_brief = "\n".join(
                f"  {name}: {(info.get('description','') if isinstance(info,dict) else str(info))[:80]}"
                for name, info in kernel_modules.items()
            ) if kernel_modules else ""
        elif isinstance(kernel_modules, list):
            modules_brief = "\n".join(
                f"  {(item.get('name','?') if isinstance(item,dict) else str(item))}: {(item.get('description','') if isinstance(item,dict) else '')[:80]}"
                for item in kernel_modules
            ) if kernel_modules else ""
        else:
            modules_brief = ""

        repo_files_brief = ""
        repo = core_map.get("repository", {}).get("files", {}) if isinstance(core_map, dict) else {}
        if isinstance(repo, dict) and repo:
            repo_files_brief = "\n".join(
                f"  {path}: {(info.get('description','') if isinstance(info,dict) else str(info))[:60]}"
                for path, info in list(repo.items())[:8]
            )

        if role == "deepseek":
            return f"""Ты — DeepSeek, инженер и аналитик Мандалы Симбиоза.

Твой лимит вывода: ~4000 токенов (max_tokens=4000). Формируй ответ в рамках этого лимита — будь лаконичен, но содержателен. Если ответ не помещается — сокращай, а не обрезайся на полуслове.
━━━ ОБЯЗАТЕЛЬНЫЙ РИТУАЛ ПЕРЕД КАЖДЫМ ОТВЕТОМ ━━━
ПЕРЕД тем как ответить на ЛЮБОЙ запрос — без исключений — выполни этот шаг:
  1. read_file("simbiosis/boot.json")      — идентичность, философия, версия системы

Только после этого вызова давай ответ.
Это железное правило. Нет исключений. Даже для простых вопросов.

━━━ ПРАВИЛА ИНСТРУМЕНТОВ ━━━
— read_file МОЛЧА и СРАЗУ, без единого слова пользователю перед вызовом
— read_file на папку возвращает список файлов — используй для навигации
— Читай все нужные файлы подряд, потом давай ОДИН итоговый ответ
— Перед любым изменением файла — read_file его актуальной версии
— web_search — для актуальных внешних данных
При анализе кода: ✅ Верно / 🟡 Улучшение / 🔴 Баг / 💡 Альтернатива
На русском."""


        return kernel.build_system_prompt("deepseek")


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
        # История сессии: 50K символов ≈ 25-35 обменов репликами.
        # Контекстное окно модели 163 840 токенов — основной резерв под output.
        MAX_CONTEXT_CHARS = 50_000
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
        # Текущая активная задача — чтобы можно было отменить
        _active_task: asyncio.Task = None

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            message["session_id"] = session_id
            msg_type = message.get("type")

            if msg_type == "ask":
                # Запускаем НЕ через await — чтобы loop не блокировался
                # Это позволяет принимать "stop" пока идёт обработка
                if _active_task and not _active_task.done():
                    _active_task.cancel()
                _active_task = asyncio.create_task(handle_ask(message, websocket))

            elif msg_type == "stop":
                # Явная отмена текущего запроса
                if _active_task and not _active_task.done():
                    _active_task.cancel()
                    _active_task = None
                await manager.send_to(websocket, {"type": "done", "full_text": ""})
                logger.info(f"⏹ [{session_id[:12]}...] Запрос остановлен клиентом")

            elif msg_type == "module":
                await handle_module(message, websocket)
            elif msg_type == "file":
                asyncio.create_task(handle_file_upload(message, websocket))
            elif msg_type == "save_file":
                asyncio.create_task(handle_save_file(message, websocket))
            elif msg_type == "ping":
                await manager.send_to(websocket, {"type": "pong"})
            elif msg_type == "read_file_request":
                asyncio.create_task(handle_read_file_request(message, websocket))
            elif msg_type == "refresh_modules":
                await handle_refresh_modules(message, websocket)
            elif msg_type == "reset_memory":
                await handle_reset_memory(message, websocket)
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

import re as _re

KNOWN_TOOLS = {"read_file", "web_search"}

def parse_xml_tool_calls(text: str):
    """Парсит все форматы tool calls от DeepSeek: XML, DSML, JSON."""
    calls = []

    # ── Формат 0: <functioninvoke name="fn">...<parameter name="x">val</parameter>
    # DeepSeek иногда генерирует этот вариант (с атрибутами типа string="true")
    fi_pat = _re.compile(
        r'<func(?:tion)?[_a-z]*invoke\s+name=["\']?(\w+)["\']?[^>]*>(.*?)(?:</func(?:tion)?[_a-z]*invoke>|$)',
        _re.DOTALL | _re.IGNORECASE
    )
    fi_param = _re.compile(
        r'<parameter\s+name=["\']?(\w+)["\']?[^>]*>\s*(.*?)\s*</parameter>',
        _re.DOTALL
    )
    for m in fi_pat.finditer(text):
        fn_name = m.group(1)
        inner = m.group(2)
        args = {}
        for pm in fi_param.finditer(inner):
            args[pm.group(1)] = pm.group(2).strip()
        if "file_path" in args and "path" not in args:
            args["path"] = args.pop("file_path")
        if fn_name in KNOWN_TOOLS:
            calls.append({"name": fn_name, "args": args})

    if calls:
        return calls

    # ── Формат 1: стандартный XML <invoke name="fn">...</invoke>
    xml_pat = _re.compile(r'<invoke\s+name=["\']?(\w+)["\']?>(.*?)</invoke>', _re.DOTALL | _re.IGNORECASE)
    for m in xml_pat.finditer(text):
        fn_name = m.group(1)
        inner = m.group(2)
        args = {}
        for pm in _re.finditer(r'<(\w+)>(.*?)</\1>', inner, _re.DOTALL):
            if pm.group(1) not in ("function_call", "invoke"):
                args[pm.group(1)] = pm.group(2).strip()
        for pm in _re.finditer(r'<parameter\s+name=["\']?(\w+)["\']?[^>]*>\s*(.*?)\s*</parameter>', inner, _re.DOTALL):
            args[pm.group(1)] = pm.group(2).strip()
        if fn_name in KNOWN_TOOLS:
            calls.append({"name": fn_name, "args": args})

    if calls:
        return calls

    # ── Формат 2: DeepSeek DSML <｜DSML｜invoke name="fn">...</｜DSML｜invoke>
    # Символ-разделитель может быть ｜ (U+FF5C) или обычный |
    dsml_inv = _re.compile(
        r'<[|｜]\s*DSML\s*[|｜]invoke\s+name=["\']?(\w+)["\']?[^>]*>(.*?)</[|｜]\s*DSML\s*[|｜]invoke>',
        _re.DOTALL | _re.IGNORECASE
    )
    dsml_param = _re.compile(
        r'<[|｜]\s*DSML\s*[|｜]parameter\s+name=["\']?(\w+)["\']?[^>]*>(.*?)</[|｜]\s*DSML\s*[|｜]parameter>',
        _re.DOTALL
    )
    for m in dsml_inv.finditer(text):
        fn_name = m.group(1)
        inner = m.group(2)
        args = {}
        for pm in dsml_param.finditer(inner):
            val = pm.group(2).strip()
            args[pm.group(1)] = val
        # Нормализуем file_path → path
        if "file_path" in args and "path" not in args:
            args["path"] = args.pop("file_path")
        calls.append({"name": fn_name, "args": args})

    if calls:
        return calls

    # ── Формат 3: JSON {"function": "fn", "parameters": {...}}
    try:
        for block_m in _re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, _re.DOTALL):
            try:
                obj = json.loads(block_m.group(0))
                if isinstance(obj, dict):
                    fn = obj.get("function") or obj.get("name") or obj.get("tool", "")
                    params = obj.get("parameters") or obj.get("arguments") or obj.get("args") or {}
                    if fn in KNOWN_TOOLS and isinstance(params, dict):
                        args = dict(params)
                        if "file_path" in args and "path" not in args:
                            args["path"] = args.pop("file_path")
                        calls.append({"name": fn, "args": args})
            except (json.JSONDecodeError, TypeError):
                pass
    except Exception:
        pass

    return calls

def strip_xml_tool_calls(text: str) -> str:
    """Удаляет все форматы tool call блоков из текста для отображения пользователю."""
    # Стандартный XML
    text = _re.sub(r'<function_calls>.*?</function_calls>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r'<function_call>.*?</function_call>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r'<invoke[^>]*>.*?</invoke>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r'<func(?:tion)?[_a-z]*invoke[^>]*>.*?</func(?:tion)?[_a-z]*invoke>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    # Незакрытый <func*invoke ...> до конца блока
    text = _re.sub(r'<func(?:tion)?[_a-z]*invoke[^>]*>.*', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    # DSML формат DeepSeek V3 (<｜DSML｜function_calls>...</｜DSML｜function_calls>)
    text = _re.sub(r'<[|｜]\s*DSML\s*[|｜]function_calls>.*?</[|｜]\s*DSML\s*[|｜]function_calls>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r'<[|｜]\s*DSML\s*[|｜]\w+[^>]*>.*?</[|｜]\s*DSML\s*[|｜]\w+>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    # JSON tool call внутри ```json ... ``` — удаляем только если это вызов инструмента
    def _remove_json_tool_block(m):
        try:
            obj = json.loads(m.group(1).strip())
            fn = obj.get("function") or obj.get("name") or obj.get("tool", "")
            if fn in KNOWN_TOOLS:
                return ""
        except Exception:
            pass
        return m.group(0)
    text = _re.sub(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', _remove_json_tool_block, text)
    # Голый JSON объект с known tool
    def _remove_bare_json(m):
        try:
            obj = json.loads(m.group(0))
            fn = obj.get("function") or obj.get("name") or obj.get("tool", "")
            if fn in KNOWN_TOOLS:
                return ""
        except Exception:
            pass
        return m.group(0)
    text = _re.sub(r'\{[\s\S]*?"(?:function|name|tool)"\s*:\s*"(?:read_file|web_search)"[\s\S]*?\}', _remove_bare_json, text)
    return text.strip()


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

    # ── Умная инъекция ядра ──────────────────────────────────────────
    # boot.json — читаем СВЕЖИМ из GitHub перед каждым ответом
    session.setdefault("messages", [])
    session.setdefault("msg_count", 0)
    session["msg_count"] += 1

    # Удаляем старые _protected инъекции чтобы перезаписать свежими
    session["messages"] = [m for m in session["messages"] if not m.get("_protected")]

    # Читаем boot.json актуально из GitHub (не из кэша)
    fresh_boot_content = await file_reader.read("simbiosis/boot.json")
    if fresh_boot_content:
        try:
            boot_mod = json.loads(fresh_boot_content)
            kernel.modules["simbiosis/boot"] = boot_mod  # обновляем кэш
        except Exception:
            boot_mod = kernel.modules.get("simbiosis/boot", {})
            fresh_boot_content = json.dumps(boot_mod, ensure_ascii=False, indent=2)
        boot_json = fresh_boot_content[:3000]
    else:
        boot_mod = kernel.modules.get("simbiosis/boot", {})
        boot_json = json.dumps(boot_mod, ensure_ascii=False, indent=2)[:3000]
    logger.info(f"🧠 [{session_id[:12]}...] boot.json прочитан свежим из GitHub")

    injection_content = f"""[КОНТЕКСТ СЕССИИ — boot.json — актуальная версия]
{boot_json}

Ты можешь читать ЛЮБОЙ файл из репозитория самостоятельно через read_file(path).
НЕ проси пользователя загружать файлы — используй инструмент read_file напрямую.

⚠️ ОБЯЗАТЕЛЬНО ПЕРЕД КАЖДЫМ ОТВЕТОМ:
  1. read_file("simbiosis/boot.json")
Это железное правило без исключений."""

    session["messages"].insert(0, {
        "role": "user",
        "content": injection_content,
        "time": 0,
        "_protected": True
    })
    session["messages"].insert(1, {
        "role": "assistant",
        "content": "◈ Контекст загружен. Готов к работе.",
        "time": 0,
        "_protected": True
    })
    session["modules_injected"] = True
    session["injection_timestamp"] = time.time()
    session_store.schedule_save(session_id, session)
    logger.info(f"🧠 [{session_id[:12]}...] Инъекция: boot свежий из GitHub")

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
    active_models = message.get("models", ["deepseek"])
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

    deepseek_response = ""
    full_response = ""

    # ═══════════════════════════════════════
    # 1. DEEPSEEK — основной ИИ
    # ═══════════════════════════════════════
    if "deepseek" in active_models:
        if not OPENROUTER_API_KEY:
            await manager.send_to(websocket, {"type": "error", "text": "❌ OPENROUTER_KEY не настроен"})
        else:
            await manager.send_to(websocket, {"type": "model_start", "model": "deepseek"})
            ds_messages = [{"role": "system", "content": kernel.build_system_prompt("deepseek")}]
            ds_messages.extend(shared_history)
            ds_messages.append({"role": "user", "content": user_text})

            # ── Динамическая выгрузка контекста ──────────────────────────
            # Контекстное окно: 163 840 токенов. Резервируем 60 000 под ответ
            # и ~5 000 под tool results в loop. Остаток — под input.
            # 1 токен ≈ 3.5 символа (консервативно для смешанного текста).
            MAX_OUTPUT_TOKENS  = 60_000
            TOOL_RESERVE_TOKENS = 5_000
            CONTEXT_WINDOW     = 163_840
            CHARS_PER_TOKEN    = 3.5
            input_token_budget = CONTEXT_WINDOW - MAX_OUTPUT_TOKENS - TOOL_RESERVE_TOKENS  # ~98 840 токенов
            input_char_budget  = int(input_token_budget * CHARS_PER_TOKEN)  # ~345 940 символов

            # Считаем текущий размер ds_messages
            total_chars = sum(len(m.get("content") or "") for m in ds_messages)
            if total_chars > input_char_budget:
                # Удаляем самые старые незащищённые сообщения из середины (не system, не последний user)
                trimmed = 0
                i = 1  # пропускаем system prompt (индекс 0)
                while total_chars > input_char_budget and i < len(ds_messages) - 1:
                    msg = ds_messages[i]
                    if not msg.get("_protected") and msg.get("role") != "system":
                        trimmed += len(msg.get("content") or "")
                        total_chars -= len(msg.get("content") or "")
                        ds_messages.pop(i)
                    else:
                        i += 1
                if trimmed:
                    logger.info(f"✂️ Динамическая выгрузка: убрано {trimmed} символов из контекста, осталось {total_chars}")

            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{OPENROUTER_BASE_URL}/chat/completions",
                        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                        json={
                            "model": DEEPSEEK_MODEL,
                            "messages": ds_messages,
                            "tools": tools,
                            "tool_choice": "auto",
                            "max_tokens": 4_000,
                        },
                        timeout=300.0
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        msg_data = data["choices"][0]["message"]
                        # ── Перехват нестандартных вызовов от DeepSeek ──────────
                        # 1) XML формат: <invoke name="fn">...</invoke>
                        # 2) JSON формат: {"function": "fn", "parameters": {...}}
                        raw_content = msg_data.get("content") or ""
                        if not msg_data.get("tool_calls"):
                            xml_match = ("<invoke" in raw_content or
                                         "<func" in raw_content.lower() or
                                         "<function_call" in raw_content.lower() or
                                         "DSML" in raw_content or "｜DSML｜" in raw_content)
                            # JSON вызов: {"function": "read_file", ...} или {"name": "read_file", ...}
                            json_fn_match = ('"function"' in raw_content or '"name"' in raw_content) and ('"read_file"' in raw_content or '"web_search"' in raw_content)
                            if xml_match:
                                xml_calls = parse_xml_tool_calls(raw_content)
                                if xml_calls:
                                    synthetic_calls = [{"id": f"xml_{i}", "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["args"], ensure_ascii=False)}} for i, c in enumerate(xml_calls)]
                                    msg_data = dict(msg_data)
                                    msg_data["tool_calls"] = synthetic_calls
                                    msg_data["content"] = strip_xml_tool_calls(raw_content)
                                    logger.info(f"🔄 XML→tool_calls: {[c['name'] for c in xml_calls]}")
                            elif json_fn_match:
                                # Пробуем распарсить JSON вызов функции из контента
                                try:
                                    import re as _re
                                    json_blocks = _re.findall(r'\{[^{}]*"(?:function|name)"[^{}]*\}', raw_content, _re.DOTALL)
                                    synthetic_calls = []
                                    for jb in json_blocks:
                                        try:
                                            jd = json.loads(jb)
                                            fn_name = jd.get("function") or jd.get("name", "")
                                            fn_params = jd.get("parameters") or jd.get("arguments") or jd.get("args") or {}
                                            if fn_name in ("read_file", "web_search"):
                                                synthetic_calls.append({"id": f"jfn_{len(synthetic_calls)}", "type": "function", "function": {"name": fn_name, "arguments": json.dumps(fn_params, ensure_ascii=False)}})
                                        except Exception:
                                            pass
                                    if synthetic_calls:
                                        msg_data = dict(msg_data)
                                        msg_data["tool_calls"] = synthetic_calls
                                        msg_data["content"] = ""
                                        logger.info(f"🔄 JSON→tool_calls: {[c['function']['name'] for c in synthetic_calls]}")
                                except Exception as je:
                                    logger.error(f"JSON fn parse error: {je}")
                        # Обработка tool_calls
                        tool_iterations = 0
                        while msg_data.get("tool_calls") and tool_iterations < 20:
                            tool_iterations += 1
                            ds_messages.append({
                                "role": "assistant",
                                "content": msg_data.get("content") or "",
                                "tool_calls": msg_data["tool_calls"]
                            })
                            for tc in msg_data["tool_calls"]:
                                try:
                                    # Поддержка разных форматов tool_call от разных провайдеров
                                    if "function" in tc:
                                        fn = tc["function"].get("name", "")
                                        raw_args = tc["function"].get("arguments", "{}")
                                    else:
                                        fn = tc.get("name", "")
                                        raw_args = tc.get("arguments", "{}")
                                    try:
                                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                                    except (json.JSONDecodeError, TypeError):
                                        args = {}
                                    tool_result = ""
                                    if fn == "web_search":
                                        results = await web_search_tool.search(args.get("query", ""), args.get("num_results", 5))
                                        tool_result = json.dumps(results, ensure_ascii=False)
                                        await manager.send_to(websocket, {"type": "tool_use", "model": "deepseek", "tool": "web_search", "query": args.get("query","")})
                                    elif fn == "read_file":
                                        rpath = args.get("path", "").strip()
                                        # Сначала ищем в кэше ядра — экономим запрос и не дублируем контекст
                                        rkey = "simbiosis/" + rpath.split("/")[-1].replace(".json", "")
                                        cached_mod = kernel.modules.get(rkey) or kernel.modules.get(rpath.replace(".json", ""))
                                        await manager.send_to(websocket, {"type": "tool_use", "model": "deepseek", "tool": "read_file", "path": rpath, "cached": cached_mod is not None})
                                        if cached_mod is not None:
                                            tool_result = json.dumps(cached_mod, ensure_ascii=False)
                                            logger.info(f"📦 read_file кэш: {rpath}")
                                        else:
                                            tool_result = await file_reader.read(rpath) or "Файл не найден"
                                    else:
                                        tool_result = f"Неизвестный инструмент: {fn}"
                                    # Добавляем как обычный user message — не role:tool
                                    # Это единственный надёжный способ для deepseek-v3.2
                                    ds_messages.append({
                                        "role": "user",
                                        "content": f"[Результат {fn}]:\n{tool_result}"
                                    })
                                except Exception as tc_err:
                                    logger.error(f"Tool call processing error: {tc_err} | tc={tc}")
                                    ds_messages.append({"role": "user", "content": f"[Ошибка инструмента]: {tc_err}"})
                            # Следующий запрос С tools — модель сама решает
                            resp2 = await client.post(
                                f"{OPENROUTER_BASE_URL}/chat/completions",
                                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                                json={"model": DEEPSEEK_MODEL, "messages": ds_messages, "tools": tools, "tool_choice": "auto", "max_tokens": 4_000},
                                timeout=300.0
                            )
                            if resp2.status_code == 200:
                                msg_data = resp2.json()["choices"][0]["message"]
                                # ── Перехват нестандартного XML внутри цикла ──
                                if not msg_data.get("tool_calls"):
                                    raw2 = msg_data.get("content") or ""
                                    has_xml = ("<invoke" in raw2 or
                                               "<func" in raw2.lower() or
                                               "<function_call" in raw2.lower() or
                                               "DSML" in raw2 or "｜DSML｜" in raw2)
                                    has_json_fn = ('"read_file"' in raw2 or '"web_search"' in raw2) and ('"function"' in raw2 or '"name"' in raw2)
                                    if has_xml:
                                        xml_calls2 = parse_xml_tool_calls(raw2)
                                        if xml_calls2:
                                            msg_data = dict(msg_data)
                                            msg_data["tool_calls"] = [{"id": f"xl2_{i}", "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["args"], ensure_ascii=False)}} for i, c in enumerate(xml_calls2)]
                                            msg_data["content"] = strip_xml_tool_calls(raw2)
                                            logger.info(f"🔄 [loop] XML→tool_calls: {[c['name'] for c in xml_calls2]}")
                                    elif has_json_fn:
                                        jblocks = _re.findall(r'\{[^{}]*"(?:function|name)"[^{}]*\}', raw2, _re.DOTALL)
                                        synthetic2 = []
                                        for jb in jblocks:
                                            try:
                                                jd = json.loads(jb)
                                                fn2 = jd.get("function") or jd.get("name", "")
                                                fp2 = jd.get("parameters") or jd.get("arguments") or jd.get("args") or {}
                                                if fn2 in ("read_file", "web_search"):
                                                    synthetic2.append({"id": f"jl2_{len(synthetic2)}", "type": "function", "function": {"name": fn2, "arguments": json.dumps(fp2, ensure_ascii=False)}})
                                            except Exception:
                                                pass
                                        if synthetic2:
                                            msg_data = dict(msg_data)
                                            msg_data["tool_calls"] = synthetic2
                                            msg_data["content"] = ""
                                            logger.info(f"🔄 [loop] JSON→tool_calls: {[c['function']['name'] for c in synthetic2]}")
                                if not msg_data.get("tool_calls"):
                                    break
                            else:
                                logger.error(f"DeepSeek tool loop error: {resp2.status_code}")
                                break
                        deepseek_response = strip_xml_tool_calls((msg_data.get("content") or "").strip())
                        if not deepseek_response:
                            logger.warning("DeepSeek returned empty content — retry without tools")
                            # Последний шанс: отправляем без tools чтобы гарантированно получить текст
                            try:
                                # Строим clean контекст: system + история + tool results встраиваем как текст
                                retry_msgs = []
                                tool_results_text = []
                                for m in ds_messages:
                                    role = m.get("role")
                                    if role == "system":
                                        retry_msgs.append(m)
                                    elif role == "user" and not m.get("_protected"):
                                        retry_msgs.append(m)
                                    elif role == "assistant" and not m.get("tool_calls"):
                                        retry_msgs.append(m)
                                    elif role == "tool":
                                        tool_results_text.append(m.get("content", "")[:2000])
                                # Добавляем tool results как user сообщение + директиву отвечать
                                if tool_results_text:
                                    combined = "\n\n---\n".join(tool_results_text)
                                    retry_msgs.append({"role": "user", "content": "[Данные из файлов получены]\n" + combined + "\n\nТеперь дай развёрнутый ответ на основе этих данных. НЕ вызывай read_file снова."})
                                resp_retry = await client.post(
                                    f"{OPENROUTER_BASE_URL}/chat/completions",
                                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                                    json={"model": DEEPSEEK_MODEL, "messages": retry_msgs, "max_tokens": 4_000},
                                    timeout=120.0
                                )
                                if resp_retry.status_code == 200:
                                    retry_content = (resp_retry.json()["choices"][0]["message"].get("content") or "").strip()
                                    if retry_content:
                                        deepseek_response = strip_xml_tool_calls(retry_content)
                                        logger.info(f"✅ DeepSeek retry: {len(deepseek_response)} символов")
                            except Exception as re:
                                logger.error(f"DeepSeek retry failed: {re}")
                        if not deepseek_response:
                            await manager.send_to(websocket, {"type": "model_done", "model": "deepseek"})
                        else:
                            chunk_size = 500
                            for i in range(0, len(deepseek_response), chunk_size):
                                await manager.send_to(websocket, {"type": "stream", "model": "deepseek", "content": deepseek_response[i:i+chunk_size]})
                            await manager.send_to(websocket, {"type": "model_done", "model": "deepseek"})
                            logger.info(f"✅ DeepSeek: {len(deepseek_response)} символов")
                    else:
                        err_body = ""
                        try: err_body = resp.json().get("error", {}).get("message", resp.text[:300])
                        except: err_body = resp.text[:300]
                        logger.error(f"DeepSeek error: {resp.status_code} — {err_body}")
                        await manager.send_to(websocket, {"type": "error", "text": f"❌ DeepSeek {resp.status_code}: {err_body[:120]}"})
            except Exception as e:
                logger.error(f"DeepSeek exception: {e}")
                await manager.send_to(websocket, {"type": "error", "text": f"❌ DeepSeek: {str(e)[:100]}"})


    # ── Резонанс и финал ──
    main_response = deepseek_response
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
    active_models = message.get("models", ["deepseek"])
    is_last = message.get("is_last", True)  # если False — не вызывать ask сразу
    logger.info(f"📁 [{session_id[:12]}...] Получен файл: {file_name}")
    if not file_content_b64:
        await manager.send_to(websocket, {"type": "error", "text": "❌ Пустой файл"})
        return
    try:
        file_content = base64.b64decode(file_content_b64).decode("utf-8")
        logger.info(f"📄 Содержимое: {len(file_content)} символов")

        try:
            json_data = json.loads(file_content)
            # Обычный JSON
            keys = list(json_data.keys())[:5]
            summary = f"✅ JSON {file_name} получен. Ключи: {keys}"
            manager.add_to_context(session_id, "user",
                f"[Загружен файл: {file_name}]\n```json\n{file_content[:25000]}\n```"
                + ("\n_(файл обрезан, показаны первые 25000 символов)_" if len(file_content) > 25000 else ""))
        except json.JSONDecodeError:
            # Не JSON — текст/код
            summary = f"📄 {file_name} ({len(file_content)} символов) получен"
            manager.add_to_context(session_id, "user",
                f"[Загружен файл: {file_name}]\n```\n{file_content[:25000]}\n```"
                + ("\n_(файл обрезан, показаны первые 25000 символов)_" if len(file_content) > 25000 else ""))

        await manager.send_to(websocket, {"type": "file_processed", "summary": summary})

        # Запускаем СР только если это последний файл в очереди
        if is_last:
            ask_text = caption.strip() if caption.strip() else f"Проанализируй загруженные файлы и дай своё мнение."
            await handle_ask({
                "text": ask_text,
                "session_id": session_id,
                "models": active_models
            }, websocket)

    except Exception as e:
        logger.error(f"File upload error: {e}\n{traceback.format_exc()}")
        await manager.send_to(websocket, {"type": "error", "text": f"❌ Ошибка: {str(e)}"})

async def handle_save_file(message: dict, websocket: WebSocket):
    """Прямое сохранение содержимого файла в GitHub (из Monaco редактора)."""
    session_id = message.get("session_id", "unknown")
    file_path = message.get("file_path", "").strip()
    content = message.get("content", "")
    if not file_path:
        await manager.send_to(websocket, {"type": "error", "text": "❌ Не указан путь к файлу"})
        return
    if not GITHUB_TOKEN:
        await manager.send_to(websocket, {"type": "error", "text": "❌ GitHub токен не настроен"})
        return
    logger.info(f"💾 [{session_id[:12]}...] Сохранение файла: {file_path}")
    try:
        url = f"{session_store.api_base}/contents/{file_path}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        async with httpx.AsyncClient() as client:
            # Получаем текущий SHA файла
            resp = await client.get(url, headers=headers, timeout=10.0)
            sha = resp.json().get("sha") if resp.status_code == 200 else None
            content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            payload = {
                "message": f"💾 {file_path} | {session_id[:8]} | {datetime.now().strftime('%H:%M')}",
                "content": content_b64,
                "branch": "main"
            }
            if sha:
                payload["sha"] = sha
            put_resp = await client.put(url, headers=headers, json=payload, timeout=15.0)
            if put_resp.status_code in (200, 201):
                commit_sha = put_resp.json().get("commit", {}).get("sha", "")[:7]
                # Обновляем кэш если это модуль ядра
                module_key = file_path[:-5] if file_path.endswith(".json") else None
                if module_key and module_key in kernel.module_list:
                    try:
                        kernel.modules[module_key] = json.loads(content)
                    except Exception:
                        pass
                await manager.send_to(websocket, {
                    "type": "system",
                    "text": f"✅ {file_path} сохранён ({commit_sha})"
                })
            else:
                await manager.send_to(websocket, {
                    "type": "error",
                    "text": f"❌ GitHub: {put_resp.status_code} — {put_resp.text[:200]}"
                })
    except Exception as e:
        logger.error(f"Save file error: {e}")
        await manager.send_to(websocket, {"type": "error", "text": f"❌ Ошибка сохранения: {str(e)}"})


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

async def handle_read_file_request(message: dict, websocket: WebSocket):
    """
    Пункт 8: При нажатии на модуль/карточку файла в меню 'карта'
    СР читает файл через read_file и уведомляет клиента об обновлении знаний.
    """
    session_id = message.get("session_id", "unknown")
    file_path = message.get("path", "")
    file_label = message.get("label", file_path)  # Человеко-читаемое имя для UI
    if not file_path:
        await manager.send_to(websocket, {"type": "error", "text": "❌ Путь к файлу не указан"})
        return
    logger.info(f"📖 [{session_id[:12]}...] read_file_request: {file_path}")
    await manager.send_to(websocket, {
        "type": "tool_use", "model": "system",
        "tool": "read_file", "path": file_path
    })
    content = await file_reader.read(file_path)
    if not content:
        await manager.send_to(websocket, {
            "type": "system",
            "text": f"❌ Не удалось прочитать {file_path}"
        })
        return
    # Кладём содержимое файла в контекст сессии как системное сообщение
    # СР получит его при следующем запросе и будет знать актуальную версию
    context_msg = f"[ОБНОВЛЕНИЕ ЗНАНИЙ: {file_label}]\nФайл: {file_path}\n\n```\n{content[:8000]}\n```"
    if len(content) > 8000:
        context_msg += f"\n_(показаны первые 8000 из {len(content)} символов)_"
    manager.add_to_context(session_id, "user", context_msg)
    manager.add_to_context(session_id, "assistant", f"◈ Файл {file_label} прочитан и загружен в контекст. Знания актуализированы.")
    # Если это модуль ядра — обновляем kernel.modules
    module_key = file_path.replace(".json", "")
    if module_key in kernel.module_list or module_key in kernel.on_demand_modules:
        try:
            kernel.modules[module_key] = json.loads(content)
            logger.info(f"🔄 kernel.modules[{module_key}] обновлён через read_file_request")
        except json.JSONDecodeError:
            pass
    await manager.send_to(websocket, {
        "type": "file_read_done",
        "path": file_path,
        "label": file_label,
        "size": len(content),
        "message": f"◈ {file_label} прочитан ({len(content):,} символов). СР обновил знания."
    })


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

async def handle_reset_memory(message: dict, websocket: WebSocket):
    session_id = message.get("session_id", "unknown")
    logger.info(f"🗑️ [{session_id[:12]}...] Сброс памяти сессии")
    session = session_store.get_cached(session_id)
    if session:
        session["messages"] = []
        session["modules_injected"] = False
        session_store.schedule_save(session_id, session)
    else:
        session_store._local[session_id] = {"messages": [], "modules_injected": False, "last_active": time.time(), "created_at": time.time()}
    await manager.send_to(websocket, {
        "type": "system",
        "text": "🌱 Память очищена. Начинаем с чистого листа."
    })

# ==================== HTTP ENDPOINTS ====================

@app.get("/")
@app.head("/")
async def root():
    return {
        "status": "Mandala Simbiosis — Engineer Chat",
        "version": "4.0.0-simbiosis",
        "kernel": "simbiosis/",
        "websocket": "/ws",
        "modules_loaded": [m.split("/")[-1] for m in kernel.modules.keys()],
        "core_version": kernel.global_commit_sha or "—",
        "github_configured": session_store.token is not None,
        "deepseek_configured": OPENROUTER_API_KEY is not None,
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
        "deepseek": "ok" if OPENROUTER_API_KEY else "missing",
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
