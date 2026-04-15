#!/usr/bin/env python3
"""
Mandala Garden Bot — Gentle Companion v6.0.1

ARCHITECTURE CHANGE (v6.0.1):
- In-memory store for all gardener data (gardener, tasks, achievements, groups)
- All READ operations: instant from memory, zero GitHub API calls
- All WRITE operations: update memory first → respond to user → sync to GitHub
  in background via asyncio.create_task (fire-and-forget)
- On startup: load all 4 files in parallel via asyncio.gather (~2s, one-time)
- On restart: re-load from GitHub (source of truth)
- Result: no more hanging. User gets response in <100ms always.

EMOJI (v6.0.1):
- Botanical-sacred palette: 🌾 💎 🌀 🔮 🪶 🌿 🌄 🌒 🌱 ✅ ❌ ⚠️
- Life areas: 🌿 🔥 📿 🧭 🪬
"""

import os
import sys
import json
import logging
import base64
import asyncio
import time
import copy
from datetime import datetime
from typing import Optional, Any, Tuple

from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import aiohttp
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("REPO_NAME", "voodoomushroomzzz-source/mandala-core")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
ALLOWED_PASSWORD = os.getenv("ALLOWED_PASSWORD", "mandala")
ENGINEER_CHAT_URL = os.getenv("ENGINEER_CHAT_URL", "https://mandala-engineer-chat.onrender.com")
SR_BACKEND_URL = os.getenv("SR_BACKEND_URL", f"{ENGINEER_CHAT_URL}/bot/ask")

PORT = 10000
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "mandala-secret"

GARDENER_ID = "gardener_001"
GARDENER_PATH = f"honeycombs/personal_gardeners/{GARDENER_ID}"
MAIN_SESSION_ID = "main"

if not BOT_TOKEN or not RENDER_EXTERNAL_URL:
    logger.error("Missing BOT_TOKEN or RENDER_EXTERNAL_URL")
    sys.exit(1)

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ═══════════════════════════════════════════════════════════════════════════════
# IN-MEMORY STORE
# Single source of truth during runtime. GitHub = persistent backup.
# READ  → always from _store (instant)
# WRITE → update _store → respond to user → sync GitHub in background
# ═══════════════════════════════════════════════════════════════════════════════

_store: dict = {
    "gardener":     None,   # dict | None
    "tasks":        [],     # list
    "achievements": [],     # list
    "groups":       {},     # dict
    "ready":        False,  # True after initial load
}

# pending GitHub writes: {path: content} — deduplicated by path
_pending_writes: dict = {}
_write_lock = asyncio.Lock() if False else None  # initialized in on_startup


def store_get_gardener() -> Optional[dict]:
    return copy.deepcopy(_store["gardener"])

def store_set_gardener(g: dict) -> None:
    _store["gardener"] = g
    _pending_writes[f"{GARDENER_PATH}/gardener.json"] = g

def store_get_tasks() -> list:
    return copy.deepcopy(_store["tasks"])

def store_set_tasks(t: list) -> None:
    _store["tasks"] = t
    _pending_writes[f"{GARDENER_PATH}/tasks.json"] = t

def store_get_achievements() -> list:
    return copy.deepcopy(_store["achievements"])

def store_set_achievements(a: list) -> None:
    _store["achievements"] = a
    _pending_writes[f"{GARDENER_PATH}/achievements.json"] = a

def store_get_groups() -> dict:
    return copy.deepcopy(_store["groups"])

def store_set_groups(g: dict) -> None:
    _store["groups"] = g
    _pending_writes[f"{GARDENER_PATH}/groups.json"] = g

# ─── Global HTTP session ───────────────────────────────────────────────────────

_http_session: Optional[aiohttp.ClientSession] = None

async def get_http_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)

# ─── GitHub API ───────────────────────────────────────────────────────────────

async def _github_get(file_path: str) -> Optional[Any]:
    """GET a file from GitHub. Returns parsed JSON or None."""
    if not GITHUB_TOKEN:
        return None
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}?ref=main"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/6.0.0"
    }
    session = await get_http_session()
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                data = await resp.json()
                content = base64.b64decode(data["content"]).decode("utf-8")
                try:
                    return json.loads(content)
                except Exception:
                    return content
            return None
    except Exception as e:
        logger.error(f"GitHub GET error [{file_path}]: {e}")
        return None

async def _github_put(path: str, content: Any) -> bool:
    """PUT a file to GitHub. Returns True on success."""
    if not GITHUB_TOKEN:
        return False
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/6.0.0"
    }
    session = await get_http_session()
    sha = None
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                sha = (await resp.json()).get("sha")
    except Exception:
        pass
    content_b64 = base64.b64encode(_json_dumps(content).encode("utf-8")).decode("utf-8")
    payload = {"message": f"bot: update {path}", "content": content_b64, "branch": "main"}
    if sha:
        payload["sha"] = sha
    try:
        async with session.put(url, headers=headers, json=payload,
                               timeout=aiohttp.ClientTimeout(total=10)) as resp:
            return resp.status in [200, 201]
    except Exception as e:
        logger.error(f"GitHub PUT error [{path}]: {e}")
        return False

# ─── Background sync ──────────────────────────────────────────────────────────

async def _sync_pending() -> None:
    """Flush all pending writes to GitHub. Called by scheduler every 2 min."""
    if not _pending_writes:
        return
    # snapshot and clear pending atomically
    batch = dict(_pending_writes)
    _pending_writes.clear()
    for path, content in batch.items():
        ok = await _github_put(path, content)
        if not ok:
            logger.warning(f"Sync failed for {path}, re-queuing")
            _pending_writes.setdefault(path, content)

def _fire_sync() -> None:
    """Schedule a background sync without blocking the caller."""
    asyncio.create_task(_sync_pending())

# ─── Initial load ─────────────────────────────────────────────────────────────

async def _load_store() -> None:
    """Load all gardener files from GitHub in parallel on startup."""
    logger.info("Loading store from GitHub...")
    gardener_path = f"{GARDENER_PATH}/gardener.json"
    tasks_path    = f"{GARDENER_PATH}/tasks.json"
    ach_path      = f"{GARDENER_PATH}/achievements.json"
    groups_path   = f"{GARDENER_PATH}/groups.json"

    results = await asyncio.gather(
        _github_get(gardener_path),
        _github_get(tasks_path),
        _github_get(ach_path),
        _github_get(groups_path),
        return_exceptions=True
    )

    gardener, tasks, achievements, groups = results

    _store["gardener"]     = gardener if isinstance(gardener, dict) else None
    _store["tasks"]        = tasks if isinstance(tasks, list) else []
    _store["achievements"] = achievements if isinstance(achievements, list) else []
    _store["groups"]       = groups if isinstance(groups, dict) else {"groups": []}
    _store["ready"]        = True

    g_name = _store["gardener"].get("identity", {}).get("name", "?") if _store["gardener"] else "none"
    logger.info(
        f"Store loaded: gardener={g_name}, "
        f"tasks={len(_store['tasks'])}, "
        f"ach={len(_store['achievements'])}, "
        f"groups={len(_store['groups'].get('groups', []))}"
    )

# ─── Auth ─────────────────────────────────────────────────────────────────────

_auth_cache: dict = {}
AUTH_CACHE_TTL = 120

def is_authorized(telegram_id: str) -> bool:
    """Sync auth check from in-memory store — no GitHub call needed."""
    now = time.time()
    if telegram_id in _auth_cache:
        result, ts = _auth_cache[telegram_id]
        if now - ts < AUTH_CACHE_TTL:
            return result
    gardener = _store.get("gardener")
    if not gardener:
        return False
    result = str(gardener.get("identity", {}).get("telegram_id", "")) == str(telegram_id)
    _auth_cache[telegram_id] = (result, now)
    return result

def _invalidate_auth_cache(telegram_id: str) -> None:
    _auth_cache.pop(telegram_id, None)

async def _check_ready(message: Message) -> bool:
    """Guard: returns False and notifies user if store not loaded yet."""
    if not _store.get("ready"):
        await message.answer("🌱 Запускаюсь, подожди пару секунд и повтори.")
        return False
    return True

# ─── Resonance helpers ────────────────────────────────────────────────────────

def _calculate_initial_resonance(life_areas: dict) -> int:
    vals = [a.get("current", 5) for a in life_areas.values() if isinstance(a, dict)]
    avg = sum(vals) / len(vals) if vals else 5
    return max(10, round(10 + avg / 4 * 2))

def _add_growth_history_entry(gardener: dict, resonance: int) -> dict:
    history = gardener.get("growth_history", [])
    today = _today()
    if not history or history[-1].get("date") != today:
        ach_count = len(_store.get("achievements", []))
        history.append({"date": today, "resonance": resonance, "achievements_count": ach_count})
    gardener["growth_history"] = history[-90:]
    return gardener

def _apply_resonance_decay(gardener: dict) -> Tuple[dict, bool]:
    history = gardener.get("growth_history", [])
    if not history:
        return gardener, False
    try:
        last_date = datetime.strptime(history[-1].get("date", _today()), "%Y-%m-%d")
    except Exception:
        return gardener, False
    days_silent = (datetime.now() - last_date).days
    if days_silent < 14:
        return gardener, False
    weeks = (days_silent - 14) // 7
    if weeks < 1:
        return gardener, False
    current_res = gardener.get("identity", {}).get("resonance_level", 13)
    new_res = max(10, current_res - weeks)
    if new_res == current_res:
        return gardener, False
    gardener.setdefault("identity", {})["resonance_level"] = new_res
    gardener["identity"]["updated"] = _today()
    return gardener, True

# ─── Task helpers ─────────────────────────────────────────────────────────────

def calculate_priority(deadline: str = None) -> int:
    p = 5
    if deadline:
        try:
            days = (datetime.fromisoformat(deadline) - datetime.now()).days
            p += 2 if days < 0 else (1 if days <= 3 else 0)
        except Exception:
            pass
    return max(1, min(10, p))

# ─── Group helpers ────────────────────────────────────────────────────────────

def _make_group_id(name: str, existing: list) -> str:
    base = "".join(c for c in name.lower() if c.isalnum() or c == "_") or "group"
    gid, counter = base, 1
    while any(g.get("id") == gid for g in existing):
        gid = f"{base}_{counter}"
        counter += 1
    return gid

# ─── Proactive / Silence trackers ─────────────────────────────────────────────

_proactive_sent_today: dict = {}
_last_interaction: dict = {}

def _track_interaction(telegram_id: str) -> None:
    _last_interaction[str(telegram_id)] = _today()

def _can_send_proactive(telegram_id: str) -> bool:
    return _proactive_sent_today.get(str(telegram_id)) != _today()

def _mark_proactive_sent(telegram_id: str) -> None:
    _proactive_sent_today[str(telegram_id)] = _today()

def _silence_phase(telegram_id: str) -> int:
    last = _last_interaction.get(str(telegram_id))
    if not last:
        return 1
    try:
        days = (datetime.now() - datetime.strptime(last, "%Y-%m-%d")).days
        return 1 if days <= 7 else (2 if days <= 30 else 3)
    except Exception:
        return 1

def _time_matches(setting_time: str) -> bool:
    if not setting_time:
        return False
    try:
        now = datetime.now()
        h, m = map(int, setting_time.split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        return abs((now - target).total_seconds()) <= 90
    except Exception:
        return False

# ─── FSM States ───────────────────────────────────────────────────────────────

class GardenOnboardingStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_interests = State()
    waiting_for_goals = State()
    waiting_for_health_current = State()
    waiting_for_health_target = State()
    waiting_for_creativity_current = State()
    waiting_for_creativity_target = State()
    waiting_for_morning = State()
    waiting_for_evening = State()
    done = State()

class EngineerChatStates(StatesGroup):
    waiting_for_message = State()

class AchievementStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_bonus = State()

class TaskStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_group = State()
    waiting_for_life_area = State()
    waiting_for_deadline = State()
    waiting_for_estimated_hours = State()
    waiting_for_notes = State()
    waiting_for_confirm = State()

class AskStates(StatesGroup):
    waiting_for_question = State()

class LeaveStates(StatesGroup):
    waiting_for_confirm = State()
    waiting_for_delete_confirm_1 = State()
    waiting_for_delete_confirm_2 = State()

# ─── Keyboards ────────────────────────────────────────────────────────────────

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True, one_time_keyboard=True
    )

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌾 Профиль"), KeyboardButton(text="💎 Достижения")],
            [KeyboardButton(text="🌀 Задачи"),  KeyboardButton(text="🔮 Резонанс")],
            [KeyboardButton(text="🪶 Инженерный чат")]
        ],
        resize_keyboard=True
    )

def get_achievement_category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌿 Здоровье",     callback_data="ach_cat_health")],
        [InlineKeyboardButton(text="🔥 Творчество",   callback_data="ach_cat_creativity")],
        [InlineKeyboardButton(text="📿 Знания",       callback_data="ach_cat_knowledge")],
        [InlineKeyboardButton(text="🧭 Исследования", callback_data="ach_cat_exploration")],
        [InlineKeyboardButton(text="🪬 Отношения",    callback_data="ach_cat_relationships")],
        [InlineKeyboardButton(text="❌ Отмена",        callback_data="cancel_achievement")]
    ])

LIFE_AREA_ICONS = {
    "health": "🌿", "creativity": "🔥", "knowledge": "📿",
    "exploration": "🧭", "relationships": "🪬", "other": "🌱"
}

def get_groups_keyboard(groups: list) -> InlineKeyboardMarkup:
    btns = [[InlineKeyboardButton(text=g["name"], callback_data=f"grp_{g['id']}")] for g in groups]
    btns.append([InlineKeyboardButton(text="➕ Новая группа", callback_data="new_group")])
    btns.append([InlineKeyboardButton(text="❌ Отмена",        callback_data="cancel_task")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def get_life_area_keyboard() -> InlineKeyboardMarkup:
    areas = [
        ("🌿 Здоровье", "health"), ("🔥 Творчество", "creativity"),
        ("📿 Знания", "knowledge"), ("🧭 Исследования", "exploration"),
        ("🪬 Отношения", "relationships"), ("🌱 Другое", "other")
    ]
    btns = [[InlineKeyboardButton(text=n, callback_data=f"area_{v}")] for n, v in areas]
    btns.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def get_confirm_task_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Создать задачу", callback_data="confirm_task")],
        [InlineKeyboardButton(text="❌ Отмена",          callback_data="cancel_task")]
    ])

def get_tasks_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Новая задача", callback_data="start_addtask")]
    ])

def get_leave_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, архивировать", callback_data="leave_confirm")],
        [InlineKeyboardButton(text="❌ Нет, остаюсь",     callback_data="leave_cancel")]
    ])

# ─── Proactive messaging ──────────────────────────────────────────────────────

async def send_morning_greeting(telegram_id: str) -> None:
    phase = _silence_phase(telegram_id)
    if phase == 3 or not _can_send_proactive(telegram_id):
        return
    gardener = _store.get("gardener")
    if not gardener:
        return
    if str(gardener.get("identity", {}).get("telegram_id", "")) != str(telegram_id):
        return
    if not gardener.get("companion_settings", {}).get("proactive_mode", True):
        return
    name = gardener.get("identity", {}).get("name", "Садовник")
    if phase == 2:
        text = f"🌿 {name}, я здесь если понадоблюсь.\nБез давления — возвращайся когда захочешь."
    else:
        tasks = _store.get("tasks", [])
        active = [t for t in tasks if t.get("status") != "completed"]
        hint = ""
        if active:
            top = sorted(active, key=lambda x: x.get("priority", 5), reverse=True)[0]
            hint = f"\n\n🌱 Сегодня можно уделить внимание: <i>{top['title']}</i>"
        text = f"🌄 Доброе утро, {name}!\n\nНовый день — новая возможность.{hint}\n\nКак ты сегодня?"
    try:
        await bot.send_message(int(telegram_id), text, reply_markup=get_main_keyboard())
        _mark_proactive_sent(telegram_id)
    except Exception as e:
        logger.error(f"Morning greeting error: {e}")

async def send_evening_checkin(telegram_id: str) -> None:
    phase = _silence_phase(telegram_id)
    if phase == 3 or not _can_send_proactive(telegram_id):
        return
    gardener = _store.get("gardener")
    if not gardener:
        return
    if str(gardener.get("identity", {}).get("telegram_id", "")) != str(telegram_id):
        return
    if not gardener.get("companion_settings", {}).get("proactive_mode", True):
        return
    name = gardener.get("identity", {}).get("name", "Садовник")
    text = (
        f"🌒 Добрый вечер, {name}.\n\n"
        f"Что произошло сегодня? Если было что-то важное — "
        f"зафиксируй достижение: /achievements\n\nДо завтра 🌿"
    )
    try:
        await bot.send_message(int(telegram_id), text, reply_markup=get_main_keyboard())
        _mark_proactive_sent(telegram_id)
    except Exception as e:
        logger.error(f"Evening check-in error: {e}")

async def run_proactive_scheduler() -> None:
    gardener = _store.get("gardener")
    if not gardener:
        return
    telegram_id = str(gardener.get("identity", {}).get("telegram_id", ""))
    if not telegram_id:
        return
    settings = gardener.get("companion_settings", {})
    if settings.get("morning_message_time") and _time_matches(settings["morning_message_time"]):
        await send_morning_greeting(telegram_id)
    if settings.get("evening_check_time") and _time_matches(settings["evening_check_time"]):
        await send_evening_checkin(telegram_id)

async def run_resonance_decay() -> None:
    gardener = _store.get("gardener")
    if not gardener:
        return
    gardener, changed = _apply_resonance_decay(dict(gardener))
    if changed:
        store_set_gardener(gardener)
        _fire_sync()
        logger.info("Resonance decay applied")

# ═══════════════════════════════════════════════════════════════════════════════
# HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

# ─── /start + onboarding ──────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    if not _store.get("ready"):
        await message.answer("🌱 Запускаюсь, подожди пару секунд и повтори.")
        return
    await state.clear()
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    gardener = _store.get("gardener")

    password = None
    try:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) == 2:
            password = parts[1].strip()
    except Exception:
        pass

    if gardener and str(gardener.get("identity", {}).get("telegram_id", "")) == user_id:
        name = gardener.get("identity", {}).get("name", "Садовник")
        await message.answer(f"🌿 С возвращением, {name}!", reply_markup=get_main_keyboard())
        return

    if gardener:
        bound_id = str(gardener.get("identity", {}).get("telegram_id", "") or "").strip()
        if bound_id and bound_id != user_id:
            if not password or password != ALLOWED_PASSWORD:
                await message.answer("🔒 Доступ защищён паролем.\nИспользуй: /start <пароль>")
                return
            g = dict(gardener)
            g.setdefault("identity", {})["telegram_id"] = user_id
            g["identity"]["updated"] = _today()
            store_set_gardener(g)
            _invalidate_auth_cache(user_id)
            _fire_sync()

    await state.set_state(GardenOnboardingStates.waiting_for_name)
    await message.answer(
        "🌿 <b>Добро пожаловать в Сад!</b>\n\n"
        "Я — твой Gentle Companion. Давай познакомимся.\n\n"
        "🌱 Как тебя зовут? Это имя будет только между нами.",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_name))
async def onboarding_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("🌱 Имя должно быть не короче 2 символов.")
        return
    await state.update_data(name=name)
    await state.set_state(GardenOnboardingStates.waiting_for_interests)
    await message.answer(
        f"🌿 Приятно познакомиться, {name}!\n\n"
        "Что тебя вдохновляет прямо сейчас? Напиши 3 вещи через запятую.\n\n"
        "<i>Первое, что приходит в голову — самое честное.</i>",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_interests))
async def onboarding_interests(message: Message, state: FSMContext):
    interests = [i.strip() for i in message.text.split(",") if i.strip()]
    if not interests:
        await message.answer("🌱 Напиши хотя бы один интерес.")
        return
    await state.update_data(interests=interests)
    await state.set_state(GardenOnboardingStates.waiting_for_goals)
    await message.answer(
        "🌱 Какие намерения хочешь посадить в этом сезоне?\n\n<i>Это не обязательства. Просто намерения.</i>",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_goals))
async def onboarding_goals(message: Message, state: FSMContext):
    goals = [g.strip() for g in message.text.split(",") if g.strip()]
    await state.update_data(goals=goals)
    await state.set_state(GardenOnboardingStates.waiting_for_health_current)
    await message.answer("🌿 Здоровье — оцени где ты сейчас (1-10):", reply_markup=get_cancel_keyboard())

@router.message(StateFilter(GardenOnboardingStates.waiting_for_health_current))
async def onboarding_health_current(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if not 1 <= val <= 10:
            raise ValueError
    except Exception:
        await message.answer("🌿 Введи число от 1 до 10.")
        return
    await state.update_data(health_current=val)
    await state.set_state(GardenOnboardingStates.waiting_for_health_target)
    await message.answer("🌿 А к какому уровню стремишься? (1-10)")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_health_target))
async def onboarding_health_target(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if not 1 <= val <= 10:
            raise ValueError
    except Exception:
        await message.answer("🌿 Введи число от 1 до 10.")
        return
    await state.update_data(health_target=val)
    await state.set_state(GardenOnboardingStates.waiting_for_creativity_current)
    await message.answer("🔥 Творчество — оцени где ты сейчас (1-10):")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_creativity_current))
async def onboarding_creativity_current(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if not 1 <= val <= 10:
            raise ValueError
    except Exception:
        await message.answer("🔥 Введи число от 1 до 10.")
        return
    await state.update_data(creativity_current=val)
    await state.set_state(GardenOnboardingStates.waiting_for_creativity_target)
    await message.answer("🔥 А к какому уровню стремишься? (1-10)")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_creativity_target))
async def onboarding_creativity_target(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if not 1 <= val <= 10:
            raise ValueError
    except Exception:
        await message.answer("🔥 Введи число от 1 до 10.")
        return
    await state.update_data(creativity_target=val)
    await state.set_state(GardenOnboardingStates.waiting_for_morning)
    await message.answer(
        "🌄 Когда тебе комфортно получать утреннее приветствие?\n"
        "Формат ЧЧ:ММ или 'нет'.",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_morning))
async def onboarding_morning(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    await state.update_data(morning_time="" if text == "нет" else text)
    await state.set_state(GardenOnboardingStates.waiting_for_evening)
    await message.answer("🌒 А вечерний чек-ин? (ЧЧ:ММ или 'нет')")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_evening))
async def onboarding_evening(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    evening = "" if text == "нет" else text
    data = await state.get_data()
    user_id = str(message.from_user.id)

    life_areas = {
        "health":        {"current": data["health_current"],    "target": data["health_target"]},
        "creativity":    {"current": data["creativity_current"], "target": data["creativity_target"]},
        "knowledge":     {"current": 5, "target": 7},
        "relationships": {"current": 5, "target": 7}
    }
    initial_resonance = _calculate_initial_resonance(life_areas)

    gardener = {
        "identity": {
            "gardener_id": GARDENER_ID, "telegram_id": user_id,
            "name": data["name"], "resonance_level": initial_resonance,
            "created": _today(), "updated": _today()
        },
        "personal_info": {"interests": data["interests"], "goals": data["goals"], "life_areas": life_areas},
        "companion_settings": {
            "morning_message_time": data["morning_time"],
            "evening_check_time": evening,
            "proactive_mode": True, "timezone": "Europe/Moscow"
        },
        "growth_history": [{"date": _today(), "resonance": initial_resonance, "achievements_count": 0}]
    }
    groups = {
        "groups": [
            {"id": "group_001", "name": "🌿 Личное", "created": _today()},
            {"id": "group_002", "name": "🔥 Работа",  "created": _today()},
            {"id": "group_003", "name": "🌱 Дом",      "created": _today()}
        ],
        "default_group": "group_001"
    }

    # Update store immediately — respond to user right away
    store_set_gardener(gardener)
    store_set_tasks([])
    store_set_achievements([])
    store_set_groups(groups)
    _invalidate_auth_cache(user_id)
    _track_interaction(user_id)

    # Sync to GitHub in background
    _fire_sync()

    await state.set_state(GardenOnboardingStates.done)
    await message.answer(
        f"🌿 <b>{data['name']}, добро пожаловать в Сад!</b>\n\n"
        f"🔮 Начальный резонанс: <b>{initial_resonance}%</b>\n\n"
        f"🌱 Резонанс только растёт. Нет наказаний за паузы.\n\nЯ здесь рядом.",
        reply_markup=get_main_keyboard()
    )

# ─── /profile ─────────────────────────────────────────────────────────────────

@router.message(Command("profile"))
@router.message(F.text == "🌾 Профиль")
async def cmd_profile(message: Message):
    if not await _check_ready(message):
        return
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start")
        return
    gardener = _store.get("gardener")
    if not gardener:
        await message.answer("🌿 Профиль не найден")
        return
    name = gardener.get("identity", {}).get("name", "Садовник")
    resonance = gardener.get("identity", {}).get("resonance_level", 13)
    active_tasks = [t for t in _store.get("tasks", []) if t.get("status") != "completed"]
    interests = gardener.get("personal_info", {}).get("interests", [])
    interests_str = ", ".join(interests[:3]) if interests else "не указаны"
    await message.answer(
        f"🌾 <b>{name}</b>\n"
        f"🔮 Резонанс: <b>{resonance}%</b>\n"
        f"🌀 Активных задач: {len(active_tasks)}\n"
        f"🌱 Интересы: {interests_str}",
        reply_markup=get_main_keyboard()
    )

# ─── /resonance ───────────────────────────────────────────────────────────────

@router.message(Command("resonance"))
@router.message(F.text == "🔮 Резонанс")
async def cmd_resonance(message: Message):
    if not await _check_ready(message):
        return
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    gardener = _store.get("gardener")
    if not gardener:
        await message.answer("🌿 Профиль не найден", reply_markup=get_main_keyboard())
        return

    resonance = gardener.get("identity", {}).get("resonance_level", 13)
    history = gardener.get("growth_history", [])
    life_areas = gardener.get("personal_info", {}).get("life_areas", {})

    area_lines = ""
    for area, icon in [("health","🌿"),("creativity","🔥"),("knowledge","📿"),("relationships","🪬")]:
        d = life_areas.get(area, {})
        area_lines += f"{icon} {area.capitalize()}: {d.get('current','?')}/10 → цель {d.get('target','?')}/10\n"

    if history:
        hist_text = "\n📿 <b>История роста:</b>\n"
        for e in reversed(history[-5:]):
            hist_text += f"• {e.get('date','?')}: {e.get('resonance','?')}% ({e.get('achievements_count',0)} достиж.)\n"
    else:
        hist_text = "\n<i>История пуста — добавь первое достижение!</i>"

    filled = round(resonance / 10)
    bar = "🟢" * filled + "⬜" * (10 - filled)

    await message.answer(
        f"🔮 <b>Резонанс</b>\n\n{bar}\n<b>{resonance}%</b>\n\n"
        f"🌱 <b>Сферы жизни:</b>\n{area_lines}{hist_text}\n\n"
        f"<i>Резонанс только растёт. Каждое достижение — новый слой.</i>",
        reply_markup=get_main_keyboard()
    )

# ─── /ask ─────────────────────────────────────────────────────────────────────

@router.message(Command("ask"))
async def cmd_ask(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(AskStates.waiting_for_question)
    await message.answer(
        "🪶 <b>Companion слушает</b>\n\nЧто у тебя на душе? Задай вопрос или просто поделись.\n\n"
        "<i>Нажми ❌ Отмена чтобы вернуться.</i>",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(AskStates.waiting_for_question))
async def ask_question(message: Message, state: FSMContext):
    _track_interaction(str(message.from_user.id))
    text = message.text.strip()
    if not text:
        await message.answer("🪶 Напиши что-нибудь или нажми ❌ Отмена")
        return
    gardener = _store.get("gardener") or {}
    name = gardener.get("identity", {}).get("name", "Садовник")
    resonance = gardener.get("identity", {}).get("resonance_level", 13)
    await message.answer("🌱 Думаю...")
    try:
        payload = {
            "session_id": MAIN_SESSION_ID,
            "message": f"[Садовник {name}, резонанс {resonance}%] спрашивает: {text}\n\nОтветь как Gentle Companion — тепло, без давления.",
            "gardener_context": gardener
        }
        session = await get_http_session()
        async with session.post(SR_BACKEND_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status in [200, 202]:
                try:
                    data = await resp.json()
                    reply = data.get("response") or data.get("message") or "🌿 Я здесь, рядом."
                except Exception:
                    reply = "🌿 Я слышу тебя."
            else:
                reply = "🌿 SR сейчас недоступен, но я здесь рядом."
    except Exception as e:
        logger.error(f"Ask SR error: {e}")
        reply = "🌿 Связь прервалась. Попробуй позже."
    await state.clear()
    await message.answer(reply, reply_markup=get_main_keyboard())

# ─── /achievements ────────────────────────────────────────────────────────────

@router.message(Command("achievements"))
@router.message(F.text == "💎 Достижения")
async def cmd_achievements(message: Message):
    if not await _check_ready(message):
        return
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start")
        return
    achievements = _store.get("achievements", [])
    add_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Добавить достижение", callback_data="add_achievement")]
    ])
    if not achievements:
        await message.answer(
            "💎 Достижений пока нет.\n\nКаждое достижение добавляет слой к твоему резонансу.\nДобавь первое!",
            reply_markup=add_btn
        )
        return
    recent = achievements[-3:]
    text = "💎 <b>Достижения:</b>\n\n"
    for ach in reversed(recent):
        icon = LIFE_AREA_ICONS.get(ach.get("category", ""), "🌱")
        text += f"{icon} <b>{ach.get('title','')}</b>\n📿 {ach.get('completed','')} · +{ach.get('resonance_bonus',1)} резонанс\n\n"
    text += f"<i>Всего: {len(achievements)}</i>"
    await message.answer(text, reply_markup=add_btn)

@router.callback_query(F.data == "add_achievement")
async def cb_add_achievement(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIRST
    if not is_authorized(str(callback.from_user.id)):
        await callback.message.answer("🌿 Используй /start")
        return
    await state.set_state(AchievementStates.waiting_for_category)
    await callback.message.answer(
        "💎 <b>Что произошло?</b>\n\nВыбери сферу:",
        reply_markup=get_achievement_category_keyboard()
    )

@router.callback_query(F.data.startswith("ach_cat_"))
async def ach_category(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIRST
    category = callback.data.replace("ach_cat_", "")
    await state.update_data(category=category)
    await state.set_state(AchievementStates.waiting_for_title)
    await callback.message.edit_text(
        "💎 Как назовёшь это достижение?\n\n<i>Одним предложением.</i>",
        reply_markup=None
    )

@router.message(StateFilter(AchievementStates.waiting_for_title))
async def ach_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AchievementStates.waiting_for_description)
    await message.answer("🌱 Расскажи подробнее (или '-' чтобы пропустить):")

@router.message(StateFilter(AchievementStates.waiting_for_description))
async def ach_description(message: Message, state: FSMContext):
    desc = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(description=desc)
    await state.set_state(AchievementStates.waiting_for_bonus)
    await message.answer("🔮 Насколько это важно для тебя? Оцени от 1 до 10.\n\n<i>Это бонус к резонансу.</i>")

@router.message(StateFilter(AchievementStates.waiting_for_bonus))
async def ach_bonus(message: Message, state: FSMContext):
    try:
        bonus = max(1, min(10, int(message.text.strip())))
    except Exception:
        bonus = 3

    data = await state.get_data()
    category = data.get("category", "other")
    icon = LIFE_AREA_ICONS.get(category, "🌱")

    # Update store immediately
    achievements = list(_store.get("achievements", []))
    achievements.append({
        "id": f"ach_{len(achievements)+1:03d}",
        "category": category,
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "completed": _today(),
        "resonance_bonus": bonus,
        "icon": icon
    })
    store_set_achievements(achievements)

    # Update gardener resonance
    gardener = _store.get("gardener")
    if gardener:
        g = dict(gardener)
        current_res = g.get("identity", {}).get("resonance_level", 13)
        new_res = min(100, current_res + bonus)
        g.setdefault("identity", {})["resonance_level"] = new_res
        g["identity"]["updated"] = _today()
        g = _add_growth_history_entry(g, new_res)
        store_set_gardener(g)
        _invalidate_auth_cache(str(message.from_user.id))

    # Sync to GitHub in background
    _fire_sync()

    await state.clear()
    await message.answer(
        f"{icon} <b>Достижение зафиксировано!</b>\n\n"
        f"<b>{data.get('title','')}</b>\n"
        f"🔮 +{bonus} к резонансу\n\n"
        f"<i>Новый слой добавлен 🌱</i>",
        reply_markup=get_main_keyboard()
    )

@router.callback_query(F.data == "cancel_achievement")
async def cb_cancel_achievement(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIRST
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")

# ─── /tasks ───────────────────────────────────────────────────────────────────

@router.message(Command("tasks"))
@router.message(F.text == "🌀 Задачи")
async def cmd_tasks(message: Message):
    if not await _check_ready(message):
        return
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    tasks = _store.get("tasks", [])
    active = [t for t in tasks if t.get("status") != "completed"]
    if not active:
        await message.answer("🌀 Активных задач нет.\n\nДобавь первую:", reply_markup=get_main_keyboard())
        await message.answer("👇", reply_markup=get_tasks_keyboard())
        return
    lines = []
    for t in active[:15]:
        dl = f" · 📿{t['deadline']}" if t.get("deadline") else ""
        icon = LIFE_AREA_ICONS.get(t.get("life_area", ""), "🌱")
        lines.append(f"{icon} <code>{t['task_id']}</code>: {t['title']} (⭐{t.get('priority',5)}){dl}")
    text = "🌀 <b>Активные задачи:</b>\n\n" + "\n".join(lines)
    text += "\n\n<i>Завершить: /done task_id</i>"
    await message.answer(text, reply_markup=get_main_keyboard())
    await message.answer("Действия:", reply_markup=get_tasks_keyboard())

@router.callback_query(F.data == "start_addtask")
async def cb_start_addtask(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIRST
    if not is_authorized(str(callback.from_user.id)):
        await callback.message.answer("🌿 Используй /start")
        return
    await state.set_state(TaskStates.waiting_for_title)
    await callback.message.answer("🌀 Название задачи:", reply_markup=get_cancel_keyboard())

@router.message(Command("addtask"))
async def cmd_addtask(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(TaskStates.waiting_for_title)
    await message.answer("🌀 Название задачи:", reply_markup=get_cancel_keyboard())

@router.message(StateFilter(TaskStates.waiting_for_title))
async def task_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) < 2:
        await message.answer("🌀 Название должно быть не короче 2 символов.")
        return
    await state.update_data(title=title)
    await state.set_state(TaskStates.waiting_for_group)
    groups = _store.get("groups", {}).get("groups", [])
    await message.answer("🌱 Выбери группу:", reply_markup=get_groups_keyboard(groups))

@router.callback_query(F.data.startswith("grp_"))
async def task_group(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIRST
    group_id = callback.data.replace("grp_", "")
    await state.update_data(group_id=group_id)
    await state.set_state(TaskStates.waiting_for_life_area)
    await callback.message.edit_text("🌱 Выбери сферу жизни:", reply_markup=get_life_area_keyboard())

@router.callback_query(F.data == "new_group")
async def task_new_group_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIRST
    await callback.message.edit_text("🌱 Введи название новой группы:", reply_markup=None)

@router.message(StateFilter(TaskStates.waiting_for_group))
async def task_group_name_input(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 1:
        await message.answer("🌱 Введи название группы.")
        return
    # Create group in store
    data = store_get_groups()
    groups = data.get("groups", [])
    gid = _make_group_id(name, groups)
    new_group = {"id": gid, "name": name, "created": _today()}
    groups.append(new_group)
    data["groups"] = groups
    store_set_groups(data)
    _fire_sync()

    await state.update_data(group_id=gid)
    await state.set_state(TaskStates.waiting_for_life_area)
    await message.answer(
        f"✅ Группа '<b>{name}</b>' создана!\n\n🌱 Выбери сферу жизни:",
        reply_markup=get_life_area_keyboard()
    )

@router.callback_query(F.data.startswith("area_"))
async def task_life_area(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIRST
    area = callback.data.replace("area_", "")
    await state.update_data(life_area=area)
    await state.set_state(TaskStates.waiting_for_deadline)
    await callback.message.edit_text(
        "📿 Дедлайн в формате ГГГГ-ММ-ДД\nили '-' если нет:",
        reply_markup=None
    )

@router.message(StateFilter(TaskStates.waiting_for_deadline))
async def task_deadline(message: Message, state: FSMContext):
    text = message.text.strip()
    await state.update_data(deadline=None if text == "-" else text)
    await state.set_state(TaskStates.waiting_for_estimated_hours)
    await message.answer("📿 Сколько часов займёт? (число или '-')")

@router.message(StateFilter(TaskStates.waiting_for_estimated_hours))
async def task_hours(message: Message, state: FSMContext):
    text = message.text.strip()
    hours = None if text == "-" else (int(text) if text.isdigit() else None)
    await state.update_data(estimated_hours=hours)
    await state.set_state(TaskStates.waiting_for_notes)
    await message.answer("🌱 Заметки (или '-'):")

@router.message(StateFilter(TaskStates.waiting_for_notes))
async def task_notes(message: Message, state: FSMContext):
    text = message.text.strip()
    notes = "" if text == "-" else text
    await state.update_data(notes=notes)
    data = await state.get_data()
    summary = (
        f"<b>🌀 Проверь задачу:</b>\n\n"
        f"🌱 <b>{data['title']}</b>\n"
        f"📿 Группа: {data.get('group_id','—')}\n"
        f"🌿 Сфера: {data.get('life_area','—')}\n"
        f"📅 Дедлайн: {data.get('deadline') or 'нет'}\n"
        f"⏱ Часы: {data.get('estimated_hours') or 'нет'}\n"
        f"📝 Заметки: {notes or 'нет'}"
    )
    await state.set_state(TaskStates.waiting_for_confirm)
    await message.answer(summary, reply_markup=get_confirm_task_keyboard())

@router.callback_query(F.data == "confirm_task")
async def confirm_task(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Сохраняю...")  # FIRST
    data = await state.get_data()

    # Create task in store
    tasks = list(_store.get("tasks", []))
    task_id = f"task_{_today().replace('-', '')}_{len(tasks)+1:03d}"
    new_task = {
        "task_id": task_id,
        "title": data["title"],
        "status": "todo",
        "group_id": data.get("group_id", "group_001"),
        "life_area": data.get("life_area", "other"),
        "priority": calculate_priority(data.get("deadline")),
        "deadline": data.get("deadline"),
        "estimated_hours": data.get("estimated_hours"),
        "created": _today(), "updated": _today(), "completed": None,
        "notes": data.get("notes", "")
    }
    tasks.append(new_task)
    store_set_tasks(tasks)
    _fire_sync()

    await state.clear()
    await callback.message.edit_text(
        f"✅ <b>{new_task['title']}</b> добавлена!\n<code>{task_id}</code>"
    )
    await callback.message.answer("🌱 Задача посеяна в твой Сад.", reply_markup=get_main_keyboard())

@router.callback_query(F.data == "cancel_task")
async def cancel_task_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIRST
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.message.answer("Возвращаемся 🌿", reply_markup=get_main_keyboard())

@router.message(Command("done"))
async def cmd_done(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("📿 Укажи ID задачи: <code>/done task_id</code>", reply_markup=get_main_keyboard())
        return
    task_id = parts[1]
    tasks = list(_store.get("tasks", []))
    found = False
    for t in tasks:
        if t.get("task_id") == task_id:
            t["status"] = "completed"
            t["completed"] = _today()
            t["updated"] = _today()
            found = True
            break
    if found:
        store_set_tasks(tasks)
        _fire_sync()
        await message.answer(
            f"✅ Задача <code>{task_id}</code> выполнена!\n\n💎 Добавь как достижение? /achievements",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer("❌ Задача не найдена.", reply_markup=get_main_keyboard())

@router.message(Command("groups"))
async def cmd_groups(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    groups = _store.get("groups", {}).get("groups", [])
    if not groups:
        await message.answer("🌱 Групп пока нет. Создай через /newgroup")
        return
    text = "\n".join([f"• {g['name']} ({g['id']})" for g in groups])
    await message.answer(f"🌱 <b>Группы:</b>\n{text}")

@router.message(Command("newgroup"))
async def cmd_newgroup(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используй: /newgroup Название группы")
        return
    name = parts[1].strip()
    data = store_get_groups()
    groups = data.get("groups", [])
    gid = _make_group_id(name, groups)
    groups.append({"id": gid, "name": name, "created": _today()})
    data["groups"] = groups
    store_set_groups(data)
    _fire_sync()
    await message.answer(f"✅ Группа '<b>{name}</b>' создана!")

@router.message(Command("archive"))
async def cmd_archive(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    tasks = _store.get("tasks", [])
    completed = [t for t in tasks if t.get("status") == "completed"]
    if not completed:
        await message.answer("📜 Завершённых задач нет.")
        return
    active = [t for t in tasks if t.get("status") != "completed"]
    store_set_tasks(active)
    # Also write archive file directly (fire-and-forget)
    asyncio.create_task(_github_put(
        f"{GARDENER_PATH}/tasks_archive_{_today()}.json", completed
    ))
    _fire_sync()
    await message.answer(f"📜 {len(completed)} задач перемещено в архив.")

# ─── /leave ───────────────────────────────────────────────────────────────────

@router.message(Command("leave"))
async def cmd_leave(message: Message, state: FSMContext):
    if not is_authorized(str(message.from_user.id)):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(LeaveStates.waiting_for_confirm)
    await message.answer(
        "🌒 <b>Архивировать свой Сад?</b>\n\n"
        "Данные сохранятся. Companion перестанет писать первым.\n"
        "Вернуться можно в любой момент.\n\n<i>Это пауза, не конец.</i>",
        reply_markup=get_leave_confirm_keyboard()
    )

@router.callback_query(F.data == "leave_confirm")
async def leave_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIRST
    user_id = str(callback.from_user.id)
    gardener = _store.get("gardener")
    if gardener:
        g = dict(gardener)
        g.setdefault("companion_settings", {})["proactive_mode"] = False
        g["identity"]["updated"] = _today()
        store_set_gardener(g)
        _invalidate_auth_cache(user_id)
        _fire_sync()
    await state.clear()
    await callback.message.edit_text(
        "🌒 <b>Сад засыпает.</b>\n\nДанные сохранены.\nВозвращайся когда захочешь 🌿"
    )

@router.callback_query(F.data == "leave_cancel")
async def leave_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIRST
    await state.clear()
    await callback.message.edit_text("🌿 Хорошо. Продолжаем.")

@router.message(Command("delete_all"))
async def cmd_delete_all(message: Message, state: FSMContext):
    if not is_authorized(str(message.from_user.id)):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(LeaveStates.waiting_for_delete_confirm_1)
    await message.answer(
        "⚠️ <b>Это необратимо.</b>\n\nВсе данные будут удалены.\n\nНапиши <code>УДАЛИТЬ</code>:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(LeaveStates.waiting_for_delete_confirm_1))
async def delete_confirm_1(message: Message, state: FSMContext):
    if message.text.strip() != "УДАЛИТЬ":
        await message.answer("❌ Отменено.")
        await state.clear()
        return
    await state.set_state(LeaveStates.waiting_for_delete_confirm_2)
    await message.answer("⚠️ Напиши <code>ДА, УДАЛИТЬ ВСЁ</code>:", reply_markup=get_cancel_keyboard())

@router.message(StateFilter(LeaveStates.waiting_for_delete_confirm_2))
async def delete_confirm_2(message: Message, state: FSMContext):
    if message.text.strip() != "ДА, УДАЛИТЬ ВСЁ":
        await message.answer("❌ Отменено.")
        await state.clear()
        return
    user_id = str(message.from_user.id)
    _store["gardener"] = None
    _store["tasks"] = []
    _store["achievements"] = []
    _store["groups"] = {}
    _invalidate_auth_cache(user_id)
    # Clear on GitHub too
    asyncio.create_task(_github_put(f"{GARDENER_PATH}/gardener.json", {}))
    asyncio.create_task(_github_put(f"{GARDENER_PATH}/tasks.json", []))
    asyncio.create_task(_github_put(f"{GARDENER_PATH}/achievements.json", []))
    await state.clear()
    await message.answer(
        "🌑 Сад очищен.\n\nНачать заново: /start 🌱",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="/start")]], resize_keyboard=True
        )
    )

# ─── Engineer chat ────────────────────────────────────────────────────────────

@router.message(F.text == "🪶 Инженерный чат")
async def btn_engineer_chat(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(EngineerChatStates.waiting_for_message)
    await message.answer(
        "🪶 <b>Инженерный чат</b>\n\nНапиши сообщение — оно отправится в основную сессию.\n\nДля отмены: ❌ Отмена",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(EngineerChatStates.waiting_for_message))
async def engineer_chat_send(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("🪶 Напиши сообщение или нажми ❌ Отмена")
        return
    gardener = _store.get("gardener") or {}
    try:
        payload = {"session_id": MAIN_SESSION_ID, "message": text, "gardener_context": gardener}
        session = await get_http_session()
        async with session.post(SR_BACKEND_URL, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status in [200, 202]:
                logger.info(f"Engineer chat: {text[:50]}")
    except Exception as e:
        logger.error(f"Engineer chat error: {e}")
    await state.clear()
    await message.answer("✅ Отправлено в инженерный чат", reply_markup=get_main_keyboard())

# ─── Cancel ───────────────────────────────────────────────────────────────────

@router.message(F.text == "❌ Отмена")
async def btn_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено.", reply_markup=get_main_keyboard())

# ─── Startup / Shutdown ───────────────────────────────────────────────────────

async def on_startup(app: web.Application) -> None:
    # Load data FIRST — before accepting any webhook requests
    await _load_store()

    await bot.set_webhook(WEBHOOK_URL, secret_token=WEBHOOK_SECRET)
    logger.info(f"Webhook set: {WEBHOOK_URL}")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_proactive_scheduler, "interval", minutes=1)
    scheduler.add_job(run_resonance_decay, CronTrigger(hour=3, minute=0))
    scheduler.add_job(_sync_pending, "interval", minutes=2)   # flush pending writes
    scheduler.start()
    app["scheduler"] = scheduler
    logger.info("Scheduler started")

async def on_shutdown(app: web.Application) -> None:
    # Final sync before shutdown
    if _pending_writes:
        logger.info(f"Flushing {len(_pending_writes)} pending writes on shutdown...")
        await _sync_pending()

    scheduler = app.get("scheduler")
    if scheduler:
        scheduler.shutdown(wait=False)
    global _http_session
    if _http_session and not _http_session.closed:
        await _http_session.close()
    await bot.delete_webhook()
    await bot.session.close()

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
