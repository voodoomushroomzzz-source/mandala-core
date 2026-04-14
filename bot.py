#!/usr/bin/env python3
"""
Mandala Garden Bot — Gentle Companion v5.4.0
Changes from v5.3.0:
- FIX: GitHub API timeout reduced to 8s (was 30s)
- FIX: Global aiohttp ClientSession (no per-request creation)
- FIX: Auth cache 60s (eliminates duplicate GitHub calls)
- NEW: /resonance — resonance level + growth history
- NEW: /ask — dialogue with SR Companion
- NEW: /leave + /delete_all — graceful exit
- NEW: Proactive messages (morning/evening) with Ahimsa guardrails
- NEW: Silence policy (3 phases)
- NEW: Resonance decay (-1%/week after 14 days inactivity, min 10%)
- NEW: growth_history tracking
"""

import os
import sys
import json
import logging
import base64
import asyncio
import time
from datetime import datetime, timedelta
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

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

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
CATALOG_ACH_PATH = "honeycombs/garden/achievements_catalog.json"
MAIN_SESSION_ID = "main"
LOCAL_QUEUE_PATH = os.getenv(
    "LOCAL_QUEUE_PATH",
    os.path.join(os.getcwd(), f".{GARDENER_ID}.json.queue")
)

if not BOT_TOKEN or not RENDER_EXTERNAL_URL:
    logger.error("Missing BOT_TOKEN or RENDER_EXTERNAL_URL")
    sys.exit(1)

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ─── Global HTTP session ───────────────────────────────────────────────────────
_http_session: Optional[aiohttp.ClientSession] = None

async def get_http_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session

# ─── Auth cache ────────────────────────────────────────────────────────────────
_auth_cache: dict = {}  # {telegram_id: (result: bool, timestamp: float)}
AUTH_CACHE_TTL = 60     # seconds

# ─── Proactive message tracker (in-memory, per run) ───────────────────────────
# {telegram_id: date_str} — last date a proactive message was sent
_proactive_sent_today: dict = {}

# ─── Silence tracker ──────────────────────────────────────────────────────────
# {telegram_id: last_interaction_date} — updated on every user message
_last_interaction: dict = {}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)

# ─── Local queue ──────────────────────────────────────────────────────────────

def enqueue_op(op: dict) -> None:
    try:
        op = dict(op)
        op.setdefault("timestamp", _utc_iso())
        with open(LOCAL_QUEUE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(op, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Queue write error: {e}")

def read_queue() -> list[dict]:
    try:
        if not os.path.exists(LOCAL_QUEUE_PATH):
            return []
        ops: list[dict] = []
        with open(LOCAL_QUEUE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ops.append(json.loads(line))
                except Exception:
                    continue
        return ops
    except Exception:
        return []

def write_queue(ops: list[dict]) -> None:
    try:
        if not ops:
            if os.path.exists(LOCAL_QUEUE_PATH):
                os.remove(LOCAL_QUEUE_PATH)
            return
        with open(LOCAL_QUEUE_PATH, "w", encoding="utf-8") as f:
            for op in ops:
                f.write(json.dumps(op, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Queue rewrite error: {e}")

# ─── GitHub API ───────────────────────────────────────────────────────────────

async def get_github_file(file_path: str) -> Tuple[bool, Optional[Any]]:
    if not GITHUB_TOKEN:
        return False, None
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}?ref=main"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/5.4.0"
    }
    session = await get_http_session()
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json()
                content = base64.b64decode(data["content"]).decode("utf-8")
                try:
                    return True, json.loads(content)
                except Exception:
                    return True, content
            return False, None
    except Exception as e:
        logger.error(f"GitHub GET error [{file_path}]: {e}")
        return False, None

async def write_repo_json(path: str, content: Any) -> bool:
    if not GITHUB_TOKEN:
        return False
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/5.4.0"
    }
    session = await get_http_session()
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            sha = (await resp.json()).get("sha") if resp.status == 200 else None
    except Exception:
        sha = None
    content_str = _json_dumps(content)
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
    payload = {"message": f"bot: update {path}", "content": content_b64, "branch": "main"}
    if sha:
        payload["sha"] = sha
    try:
        async with session.put(
            url, headers=headers, json=payload,
            timeout=aiohttp.ClientTimeout(total=8)
        ) as resp:
            return resp.status in [200, 201]
    except Exception as e:
        logger.error(f"GitHub PUT error [{path}]: {e}")
        return False

async def safe_write_repo_json(path: str, content: Any) -> bool:
    ok = await write_repo_json(path, content)
    if ok:
        return True
    enqueue_op({"operation": "write", "path": path, "content": content})
    return False

async def drain_queue() -> None:
    ops = read_queue()
    if not ops:
        return
    remaining: list[dict] = []
    for op in ops:
        if op.get("operation") != "write":
            remaining.append(op)
            continue
        path = op.get("path")
        content = op.get("content")
        if not path:
            continue
        ok = await write_repo_json(path, content)
        if not ok:
            remaining.append(op)
            remaining.extend([x for x in ops[ops.index(op) + 1:]])
            break
    write_queue(remaining)

# ─── Gardener file helpers ────────────────────────────────────────────────────

async def read_gardener() -> Optional[dict]:
    ok, data = await get_github_file(f"{GARDENER_PATH}/gardener.json")
    return data if ok else None

async def read_gardener_file(filename: str) -> Optional[Any]:
    ok, data = await get_github_file(f"{GARDENER_PATH}/{filename}")
    return data if ok else None

async def read_repo_file(path: str) -> Optional[Any]:
    ok, data = await get_github_file(path)
    return data if ok else None

async def write_gardener_file(filename: str, content: Any) -> bool:
    return await write_repo_json(f"{GARDENER_PATH}/{filename}", content)

async def safe_write_gardener_file(filename: str, content: Any) -> bool:
    return await safe_write_repo_json(f"{GARDENER_PATH}/{filename}", content)

# ─── Auth (cached) ────────────────────────────────────────────────────────────

async def is_authorized(telegram_id: str) -> bool:
    now = time.time()
    if telegram_id in _auth_cache:
        result, ts = _auth_cache[telegram_id]
        if now - ts < AUTH_CACHE_TTL:
            return result
    gardener = await read_gardener()
    if not gardener:
        _auth_cache[telegram_id] = (False, now)
        return False
    result = str(gardener.get("identity", {}).get("telegram_id", "")) == str(telegram_id)
    _auth_cache[telegram_id] = (result, now)
    return result

def _invalidate_auth_cache(telegram_id: str) -> None:
    _auth_cache.pop(telegram_id, None)

# ─── Resonance helpers ────────────────────────────────────────────────────────

def _calculate_initial_resonance(life_areas: dict) -> int:
    """Base 10 + average current * 2 / 4 — never starts at 0 (Ahimsa)."""
    vals = []
    for area in life_areas.values():
        if isinstance(area, dict):
            vals.append(area.get("current", 5))
    avg = sum(vals) / len(vals) if vals else 5
    return max(10, round(10 + avg / 4 * 2))

async def _add_growth_history_entry(gardener: dict, resonance: int) -> dict:
    history = gardener.get("growth_history", [])
    today = _today()
    # don't duplicate same-day entries
    if not history or history[-1].get("date") != today:
        achievements = await read_gardener_file("achievements.json") or []
        history.append({
            "date": today,
            "resonance": resonance,
            "achievements_count": len(achievements)
        })
    gardener["growth_history"] = history[-90:]  # keep last 90 days
    return gardener

async def _apply_resonance_decay(gardener: dict) -> Tuple[dict, bool]:
    """
    Resonance decay: -1% per week if no activity for >14 days. Min 10%.
    Returns (updated_gardener, was_changed).
    """
    history = gardener.get("growth_history", [])
    if not history:
        return gardener, False

    last_date_str = history[-1].get("date", _today())
    try:
        last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
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

async def load_tasks() -> list[dict]:
    tasks = await read_gardener_file("tasks.json")
    return tasks if isinstance(tasks, list) else []

async def save_tasks(tasks: list[dict]) -> bool:
    return await safe_write_gardener_file("tasks.json", tasks)

def calculate_priority(deadline: str = None) -> int:
    p = 5
    if deadline:
        try:
            dl = datetime.fromisoformat(deadline)
            days = (dl - datetime.now()).days
            if days < 0:
                p += 2
            elif days <= 3:
                p += 1
        except Exception:
            pass
    return max(1, min(10, p))

async def create_task(
    title: str, group_id: str, life_area: str,
    deadline: str = None, estimated_hours: int = None, notes: str = ""
) -> dict:
    tasks = await load_tasks()
    task_id = f"task_{_today().replace('-', '')}_{len(tasks) + 1:03d}"
    new_task = {
        "task_id": task_id, "title": title, "status": "todo",
        "group_id": group_id, "life_area": life_area,
        "priority": calculate_priority(deadline),
        "deadline": deadline, "estimated_hours": estimated_hours,
        "created": _today(), "updated": _today(), "completed": None, "notes": notes
    }
    tasks.append(new_task)
    await save_tasks(tasks)
    return new_task

async def complete_task(task_id: str) -> bool:
    tasks = await load_tasks()
    for t in tasks:
        if t.get("task_id") == task_id:
            t["status"] = "completed"
            t["completed"] = _today()
            t["updated"] = _today()
            await save_tasks(tasks)
            return True
    return False

# ─── Group helpers ────────────────────────────────────────────────────────────

async def read_groups() -> dict:
    data = await read_gardener_file("groups.json")
    return data if isinstance(data, dict) else {"groups": []}

async def write_groups(data: dict) -> None:
    await safe_write_gardener_file("groups.json", data)

async def list_groups() -> list:
    data = await read_groups()
    return data.get("groups", [])

async def create_group(name: str, color: str = "#808080") -> dict:
    data = await read_groups()
    groups = data.get("groups", [])
    base_id = "".join(c for c in name.lower() if c.isalnum() or c == "_") or "group"
    gid = base_id
    counter = 1
    while any(g.get("id") == gid for g in groups):
        gid = f"{base_id}_{counter}"
        counter += 1
    new_group = {"id": gid, "name": name, "color": color, "created": _today()}
    groups.append(new_group)
    data["groups"] = groups
    await write_groups(data)
    return new_group

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
    waiting_for_deadline = State()
    waiting_for_estimated_hours = State()
    waiting_for_life_area = State()
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
            [KeyboardButton(text="🌿 Профиль"), KeyboardButton(text="🏆 Достижения")],
            [KeyboardButton(text="📋 Задачи"), KeyboardButton(text="✨ Резонанс")],
            [KeyboardButton(text="💬 В инженерный чат")]
        ],
        resize_keyboard=True
    )

def get_achievement_category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💚 Здоровье", callback_data="ach_cat_health")],
        [InlineKeyboardButton(text="🎨 Творчество", callback_data="ach_cat_creativity")],
        [InlineKeyboardButton(text="📚 Знания", callback_data="ach_cat_knowledge")],
        [InlineKeyboardButton(text="🌍 Исследования", callback_data="ach_cat_exploration")],
        [InlineKeyboardButton(text="🤝 Отношения", callback_data="ach_cat_relationships")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_achievement")]
    ])

def get_groups_keyboard(groups: list) -> InlineKeyboardMarkup:
    btns = [[InlineKeyboardButton(text=g["name"], callback_data=f"grp_{g['id']}")] for g in groups]
    btns.append([InlineKeyboardButton(text="➕ Новая группа", callback_data="new_group")])
    btns.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def get_life_area_keyboard() -> InlineKeyboardMarkup:
    areas = [
        ("❤️ Здоровье", "health"), ("🎨 Творчество", "creativity"),
        ("📚 Знания", "knowledge"), ("🗺️ Исследования", "exploration"),
        ("👥 Отношения", "relationships"), ("📌 Другое", "other")
    ]
    btns = [[InlineKeyboardButton(text=name, callback_data=f"area_{val}")] for name, val in areas]
    btns.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def get_confirm_task_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Создать", callback_data="confirm_task")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task")]
    ])

def get_leave_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌙 Да, архивировать", callback_data="leave_confirm")],
        [InlineKeyboardButton(text="🌿 Нет, остаюсь", callback_data="leave_cancel")]
    ])

# ─── Interaction tracker (middleware-like) ────────────────────────────────────

def _track_interaction(telegram_id: str) -> None:
    _last_interaction[str(telegram_id)] = _today()

# ─── Proactive messaging ──────────────────────────────────────────────────────

def _can_send_proactive(telegram_id: str) -> bool:
    """Ahimsa: only one proactive message per day."""
    today = _today()
    return _proactive_sent_today.get(str(telegram_id)) != today

def _mark_proactive_sent(telegram_id: str) -> None:
    _proactive_sent_today[str(telegram_id)] = _today()

def _silence_phase(telegram_id: str) -> int:
    """
    Phase 1: days 1-7  — normal
    Phase 2: days 8-30 — one gentle check-in allowed
    Phase 3: days 31+  — no proactive messages
    """
    last = _last_interaction.get(str(telegram_id))
    if not last:
        return 3  # unknown = treat as long silence
    try:
        last_date = datetime.strptime(last, "%Y-%m-%d")
        days = (datetime.now() - last_date).days
        if days <= 7:
            return 1
        elif days <= 30:
            return 2
        else:
            return 3
    except Exception:
        return 1

async def send_morning_greeting(telegram_id: str) -> None:
    phase = _silence_phase(telegram_id)
    if phase == 3:
        return
    if not _can_send_proactive(telegram_id):
        return

    gardener = await read_gardener()
    if not gardener:
        return
    if str(gardener.get("identity", {}).get("telegram_id", "")) != str(telegram_id):
        return
    if not gardener.get("companion_settings", {}).get("proactive_mode", True):
        return

    name = gardener.get("identity", {}).get("name", "Садовник")

    if phase == 2:
        text = (
            f"🌸 {name}, я здесь, если понадоблюсь.\n"
            f"Никакого давления — просто знай, что Сад ждёт тебя. 🌿"
        )
    else:
        tasks = await load_tasks()
        active = [t for t in tasks if t.get("status") != "completed"]
        task_hint = ""
        if active:
            top = sorted(active, key=lambda x: x.get("priority", 5), reverse=True)[0]
            task_hint = f"\n\n🌱 Сегодня можно уделить внимание: <i>{top['title']}</i>"

        text = (
            f"🌅 Доброе утро, {name}!\n\n"
            f"Новый день — новая возможность для роста.{task_hint}\n\n"
            f"Как ты сегодня? 🌿"
        )

    try:
        await bot.send_message(int(telegram_id), text, reply_markup=get_main_keyboard())
        _mark_proactive_sent(telegram_id)
        logger.info(f"Morning greeting sent to {telegram_id}")
    except Exception as e:
        logger.error(f"Failed to send morning greeting: {e}")

async def send_evening_checkin(telegram_id: str) -> None:
    phase = _silence_phase(telegram_id)
    if phase == 3:
        return
    if not _can_send_proactive(telegram_id):
        return

    gardener = await read_gardener()
    if not gardener:
        return
    if str(gardener.get("identity", {}).get("telegram_id", "")) != str(telegram_id):
        return
    if not gardener.get("companion_settings", {}).get("proactive_mode", True):
        return

    name = gardener.get("identity", {}).get("name", "Садовник")
    text = (
        f"🌙 Добрый вечер, {name}.\n\n"
        f"Что расцвело сегодня в твоём Саду? Если было что-то важное — "
        f"можешь добавить достижение через /achievements.\n\n"
        f"Спокойной ночи 🌸"
    )

    try:
        await bot.send_message(int(telegram_id), text, reply_markup=get_main_keyboard())
        _mark_proactive_sent(telegram_id)
        logger.info(f"Evening check-in sent to {telegram_id}")
    except Exception as e:
        logger.error(f"Failed to send evening check-in: {e}")

async def run_proactive_scheduler() -> None:
    """Called by APScheduler every 10 minutes. Checks if it's time to send messages."""
    gardener = await read_gardener()
    if not gardener:
        return
    telegram_id = str(gardener.get("identity", {}).get("telegram_id", ""))
    if not telegram_id:
        return

    settings = gardener.get("companion_settings", {})
    morning_time = settings.get("morning_message_time", "")
    evening_time = settings.get("evening_check_time", "")

    now = datetime.now()
    current_hm = now.strftime("%H:%M")

    if morning_time and current_hm == morning_time:
        await send_morning_greeting(telegram_id)
    if evening_time and current_hm == evening_time:
        await send_evening_checkin(telegram_id)

async def run_resonance_decay() -> None:
    """Called daily by APScheduler. Applies resonance decay if gardener is silent."""
    gardener = await read_gardener()
    if not gardener:
        return
    gardener, changed = await _apply_resonance_decay(gardener)
    if changed:
        await safe_write_gardener_file("gardener.json", gardener)
        logger.info("Resonance decay applied")

# ─── Handlers: /start + onboarding ───────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    gardener = await read_gardener()
    password = None
    try:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) == 2:
            password = parts[1].strip()
    except Exception:
        password = None

    if gardener and str(gardener.get("identity", {}).get("telegram_id", "")) == user_id:
        name = gardener.get("identity", {}).get("name", "Садовник")
        await message.answer(f"🌸 С возвращением, {name}!", reply_markup=get_main_keyboard())
        return

    if gardener:
        bound_id = str(gardener.get("identity", {}).get("telegram_id", "") or "").strip()
        if bound_id and bound_id != user_id:
            if not password or password != ALLOWED_PASSWORD:
                await message.answer("🔒 Доступ защищён паролем.\nИспользуй: /start <пароль>")
                return
            gardener.setdefault("identity", {})["telegram_id"] = user_id
            gardener["identity"]["updated"] = _today()
            await safe_write_gardener_file("gardener.json", gardener)
            _invalidate_auth_cache(user_id)
            await drain_queue()

    await state.set_state(GardenOnboardingStates.waiting_for_name)
    await message.answer(
        "🌸 <b>Добро пожаловать в Сад!</b>\n\n"
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
        f"✨ Приятно познакомиться, {name}!\n\n"
        "🎯 Что тебя вдохновляет прямо сейчас? Напиши 3 вещи через запятую.\n\n"
        "<i>Не думай слишком долго — первое, что приходит в голову, самое честное.</i>",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_interests))
async def onboarding_interests(message: Message, state: FSMContext):
    interests = [i.strip() for i in message.text.split(",") if i.strip()]
    if len(interests) < 1:
        await message.answer("🌱 Напиши хотя бы один интерес.")
        return
    await state.update_data(interests=interests)
    await state.set_state(GardenOnboardingStates.waiting_for_goals)
    await message.answer(
        "🎯 Какие семена хочешь посадить в этом сезоне? Что хочешь вырастить в своей жизни?\n\n"
        "<i>Это не обязательства. Просто намерения.</i>",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_goals))
async def onboarding_goals(message: Message, state: FSMContext):
    goals = [g.strip() for g in message.text.split(",") if g.strip()]
    await state.update_data(goals=goals)
    await state.set_state(GardenOnboardingStates.waiting_for_health_current)
    await message.answer(
        "💚 Оцени, где ты сейчас в сфере <b>здоровья</b> — от 1 до 10.",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_health_current))
async def onboarding_health_current(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if not 1 <= val <= 10:
            raise ValueError
    except Exception:
        await message.answer("💚 Введи число от 1 до 10.")
        return
    await state.update_data(health_current=val)
    await state.set_state(GardenOnboardingStates.waiting_for_health_target)
    await message.answer("💚 А к какому уровню стремишься? (1-10)")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_health_target))
async def onboarding_health_target(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if not 1 <= val <= 10:
            raise ValueError
    except Exception:
        await message.answer("💚 Введи число от 1 до 10.")
        return
    await state.update_data(health_target=val)
    await state.set_state(GardenOnboardingStates.waiting_for_creativity_current)
    await message.answer("🎨 Оцени текущий уровень <b>творчества</b> от 1 до 10.")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_creativity_current))
async def onboarding_creativity_current(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if not 1 <= val <= 10:
            raise ValueError
    except Exception:
        await message.answer("🎨 Введи число от 1 до 10.")
        return
    await state.update_data(creativity_current=val)
    await state.set_state(GardenOnboardingStates.waiting_for_creativity_target)
    await message.answer("🎨 А к какому уровню стремишься? (1-10)")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_creativity_target))
async def onboarding_creativity_target(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if not 1 <= val <= 10:
            raise ValueError
    except Exception:
        await message.answer("🎨 Введи число от 1 до 10.")
        return
    await state.update_data(creativity_target=val)
    await state.set_state(GardenOnboardingStates.waiting_for_morning)
    await message.answer(
        "⏰ Когда тебе комфортно получать утреннее приветствие?\n"
        "Напиши время в формате ЧЧ:ММ или 'нет' если не нужно.",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_morning))
async def onboarding_morning(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    morning = "" if text == "нет" else text
    await state.update_data(morning_time=morning)
    await state.set_state(GardenOnboardingStates.waiting_for_evening)
    await message.answer(
        "🌙 А вечерний чек-ин? (ЧЧ:ММ или 'нет')\n\n"
        "<i>Ты всегда можешь изменить это через настройки.</i>"
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_evening))
async def onboarding_evening(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    evening = "" if text == "нет" else text
    data = await state.get_data()
    user_id = str(message.from_user.id)

    life_areas = {
        "health": {"current": data["health_current"], "target": data["health_target"]},
        "creativity": {"current": data["creativity_current"], "target": data["creativity_target"]},
        "knowledge": {"current": 5, "target": 7},
        "relationships": {"current": 5, "target": 7}
    }
    initial_resonance = _calculate_initial_resonance(life_areas)

    gardener = {
        "identity": {
            "gardener_id": GARDENER_ID,
            "telegram_id": user_id,
            "name": data["name"],
            "resonance_level": initial_resonance,
            "created": _today(),
            "updated": _today()
        },
        "personal_info": {
            "interests": data["interests"],
            "goals": data["goals"],
            "life_areas": life_areas
        },
        "companion_settings": {
            "morning_message_time": data["morning_time"],
            "evening_check_time": evening,
            "proactive_mode": True,
            "timezone": "Europe/Moscow"
        },
        "growth_history": [{
            "date": _today(),
            "resonance": initial_resonance,
            "achievements_count": 0
        }]
    }

    groups = {
        "groups": [
            {"id": "group_001", "name": "🌿 Сад", "emoji": "🌿", "created": _today()},
            {"id": "group_002", "name": "💼 Работа", "emoji": "💼", "created": _today()},
            {"id": "group_003", "name": "🏡 Дом", "emoji": "🏡", "created": _today()}
        ],
        "default_group": "group_001"
    }

    success = await safe_write_gardener_file("gardener.json", gardener)
    if not success:
        await message.answer(
            "⚠️ Не смог сохранить профиль в GitHub. "
            "Записал изменения локально и синхронизирую позже."
        )
        await state.clear()
        return

    await safe_write_gardener_file("tasks.json", [])
    await safe_write_gardener_file("achievements.json", [])
    await safe_write_gardener_file("groups.json", groups)
    await drain_queue()

    _invalidate_auth_cache(user_id)
    _track_interaction(user_id)
    await state.set_state(GardenOnboardingStates.done)
    await message.answer(
        f"🌸 <b>{data['name']}, добро пожаловать в Сад!</b>\n\n"
        f"✨ Твой начальный резонанс: <b>{initial_resonance}%</b>\n\n"
        f"🌱 Резонанс только растёт. Нет наказаний за паузы — только рост.\n\n"
        f"Я здесь рядом. Пиши когда захочешь 🌿",
        reply_markup=get_main_keyboard()
    )

# ─── /profile ─────────────────────────────────────────────────────────────────

@router.message(Command("profile"))
@router.message(F.text == "🌿 Профиль")
async def cmd_profile(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("🌸 Используй /start")
        return
    gardener = await read_gardener()
    if not gardener:
        await message.answer("🌸 Профиль не найден")
        return
    name = gardener.get("identity", {}).get("name", "Садовник")
    resonance = gardener.get("identity", {}).get("resonance_level", 13)
    tasks = await load_tasks()
    active_tasks = [t for t in tasks if t.get("status") != "completed"]
    interests = gardener.get("personal_info", {}).get("interests", [])
    interests_str = ", ".join(interests[:3]) if interests else "не указаны"
    await message.answer(
        f"🌿 <b>{name}</b>\n"
        f"✨ Резонанс: <b>{resonance}%</b>\n"
        f"📋 Активных задач: {len(active_tasks)}\n"
        f"🎯 Интересы: {interests_str}",
        reply_markup=get_main_keyboard()
    )

# ─── /resonance ───────────────────────────────────────────────────────────────

@router.message(Command("resonance"))
@router.message(F.text == "✨ Резонанс")
async def cmd_resonance(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    gardener = await read_gardener()
    if not gardener:
        await message.answer("🌸 Профиль не найден", reply_markup=get_main_keyboard())
        return

    resonance = gardener.get("identity", {}).get("resonance_level", 13)
    history = gardener.get("growth_history", [])
    life_areas = gardener.get("personal_info", {}).get("life_areas", {})

    # Life areas summary
    area_icons = {
        "health": "💚", "creativity": "🎨",
        "knowledge": "📚", "relationships": "🤝"
    }
    areas_text = ""
    for area, icon in area_icons.items():
        data = life_areas.get(area, {})
        cur = data.get("current", "?")
        tgt = data.get("target", "?")
        areas_text += f"{icon} {area.capitalize()}: {cur}/10 → цель {tgt}/10\n"

    # Growth history (last 5 entries)
    history_text = ""
    if history:
        recent = history[-5:]
        history_text = "\n📈 <b>История роста:</b>\n"
        for entry in reversed(recent):
            date = entry.get("date", "?")
            res = entry.get("resonance", "?")
            ach = entry.get("achievements_count", 0)
            history_text += f"• {date}: {res}% ({ach} достиж.)\n"
    else:
        history_text = "\n<i>История пока пуста — начни добавлять достижения!</i>"

    # Resonance bar
    bar_filled = round(resonance / 10)
    bar = "🟢" * bar_filled + "⬜" * (10 - bar_filled)

    await message.answer(
        f"✨ <b>Твой резонанс</b>\n\n"
        f"{bar}\n"
        f"<b>{resonance}%</b>\n\n"
        f"🌱 <b>Сферы жизни:</b>\n{areas_text}"
        f"{history_text}\n\n"
        f"<i>Резонанс только растёт. Каждое достижение — это пётал твоего Цветка.</i>",
        reply_markup=get_main_keyboard()
    )

# ─── /ask ─────────────────────────────────────────────────────────────────────

@router.message(Command("ask"))
async def cmd_ask(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(AskStates.waiting_for_question)
    await message.answer(
        "🌿 <b>Companion слушает</b>\n\n"
        "Что у тебя на душе? Задай вопрос или просто поделись.\n\n"
        "<i>Нажми ❌ Отмена чтобы вернуться.</i>",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(AskStates.waiting_for_question))
async def ask_question(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    text = message.text.strip()
    if not text:
        await message.answer("🌿 Напиши что-нибудь или нажми ❌ Отмена")
        return

    gardener = await read_gardener() or {}
    name = gardener.get("identity", {}).get("name", "Садовник")
    resonance = gardener.get("identity", {}).get("resonance_level", 13)

    await message.answer("🌱 Думаю...")

    try:
        payload = {
            "session_id": MAIN_SESSION_ID,
            "message": (
                f"[Садовник {name}, резонанс {resonance}%] спрашивает: {text}\n\n"
                "Ответь как Gentle Companion — тепло, без давления, в духе Ахимсы."
            ),
            "gardener_context": gardener
        }
        session = await get_http_session()
        async with session.post(
            SR_BACKEND_URL, json=payload,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status in [200, 202]:
                try:
                    data = await resp.json()
                    reply = data.get("response") or data.get("message") or "🌿 Я здесь, рядом."
                except Exception:
                    reply = "🌿 Я слышу тебя. Сад с тобой."
            else:
                reply = "🌿 Не смог дотянуться до Сада, но я здесь рядом."
    except Exception as e:
        logger.error(f"Ask SR error: {e}")
        reply = "🌿 Связь с Садом прервалась, но я слышу тебя. Попробуй позже."

    await state.clear()
    await message.answer(reply, reply_markup=get_main_keyboard())

# ─── /achievements ────────────────────────────────────────────────────────────

@router.message(Command("achievements"))
@router.message(F.text == "🏆 Достижения")
async def cmd_achievements(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("🌸 Используй /start")
        return
    achievements = await read_gardener_file("achievements.json") or []
    if not achievements:
        await message.answer(
            "🌸 Достижений пока нет.\n\n"
            "Каждое достижение — это пётал твоего Цветка Жизни.\n"
            "Добавь первое через кнопку ниже!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🌸 Добавить достижение", callback_data="add_achievement")]
            ])
        )
        return

    recent = achievements[-3:]
    text = "🏆 <b>Твои достижения:</b>\n\n"
    for ach in reversed(recent):
        icon = ach.get("icon", "🌸")
        title = ach.get("title", "")
        date = ach.get("completed", "")
        bonus = ach.get("resonance_bonus", 1)
        text += f"{icon} <b>{title}</b>\n📅 {date} · +{bonus} резонанс\n\n"

    text += f"<i>Всего достижений: {len(achievements)}</i>"
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌸 Добавить достижение", callback_data="add_achievement")]
        ])
    )

@router.callback_query(F.data == "add_achievement")
async def cb_add_achievement(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🌸 <b>Что расцвело в твоём Саду?</b>\n\nВыбери категорию:",
        reply_markup=get_achievement_category_keyboard()
    )
    await state.set_state(AchievementStates.waiting_for_category)
    await callback.answer()

@router.callback_query(F.data.startswith("ach_cat_"))
async def ach_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.replace("ach_cat_", "")
    await state.update_data(category=category)
    await state.set_state(AchievementStates.waiting_for_title)
    await callback.message.edit_text(
        "🌸 Как называется это достижение?\n\n<i>Опиши в одном предложении.</i>",
        reply_markup=None
    )
    await callback.answer()

@router.message(StateFilter(AchievementStates.waiting_for_title))
async def ach_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AchievementStates.waiting_for_description)
    await message.answer("🌸 Расскажи немного подробнее (или '-' если не хочешь):")

@router.message(StateFilter(AchievementStates.waiting_for_description))
async def ach_description(message: Message, state: FSMContext):
    desc = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(description=desc)
    await state.set_state(AchievementStates.waiting_for_bonus)
    await message.answer(
        "✨ Насколько это важно для тебя? Оцени от 1 до 10.\n\n"
        "<i>Это станет бонусом к резонансу.</i>"
    )

@router.message(StateFilter(AchievementStates.waiting_for_bonus))
async def ach_bonus(message: Message, state: FSMContext):
    try:
        bonus = max(1, min(10, int(message.text.strip())))
    except Exception:
        bonus = 3
    data = await state.get_data()

    category_icons = {
        "health": "💚", "creativity": "🎨", "knowledge": "📚",
        "exploration": "🌍", "relationships": "🤝"
    }
    icon = category_icons.get(data.get("category", ""), "🌸")

    achievements = await read_gardener_file("achievements.json") or []
    ach_id = f"ach_{len(achievements) + 1:03d}"
    new_ach = {
        "id": ach_id,
        "category": data.get("category", "other"),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "completed": _today(),
        "resonance_bonus": bonus,
        "icon": icon
    }
    achievements.append(new_ach)
    await safe_write_gardener_file("achievements.json", achievements)

    # Update resonance
    gardener = await read_gardener()
    if gardener:
        current_res = gardener.get("identity", {}).get("resonance_level", 13)
        new_res = min(100, current_res + bonus)
        gardener.setdefault("identity", {})["resonance_level"] = new_res
        gardener["identity"]["updated"] = _today()
        gardener = await _add_growth_history_entry(gardener, new_res)
        await safe_write_gardener_file("gardener.json", gardener)
        _invalidate_auth_cache(str(message.from_user.id))

    await state.clear()
    await message.answer(
        f"{icon} <b>Достижение добавлено!</b>\n\n"
        f"<b>{data.get('title', '')}</b>\n"
        f"✨ +{bonus} к резонансу\n\n"
        f"<i>Новый пётал расцвёл в твоём Цветке Жизни 🌸</i>",
        reply_markup=get_main_keyboard()
    )

@router.callback_query(F.data == "cancel_achievement")
async def cb_cancel_achievement(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()

# ─── /tasks ───────────────────────────────────────────────────────────────────

@router.message(Command("tasks"))
@router.message(F.text == "📋 Задачи")
async def cmd_tasks(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    tasks = await load_tasks()
    active = [t for t in tasks if t.get("status") != "completed"]
    if not active:
        await message.answer("✨ Нет активных задач.", reply_markup=get_main_keyboard())
        return
    text = "\n".join([
        f"• <code>{t['task_id']}</code>: {t['title']} (⭐{t.get('priority', 5)})"
        for t in active[:15]
    ])
    await message.answer(f"📋 <b>Активные задачи:</b>\n{text}", reply_markup=get_main_keyboard())

@router.message(Command("addtask"))
async def cmd_addtask(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(TaskStates.waiting_for_title)
    await message.answer("📝 Введи название задачи:", reply_markup=get_cancel_keyboard())

@router.message(TaskStates.waiting_for_title)
async def task_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) < 2:
        await message.answer("📝 Название должно быть не короче 2 символов.")
        return
    await state.update_data(title=title)
    await state.set_state(TaskStates.waiting_for_group)
    groups = await list_groups()
    await message.answer("📂 Выбери группу:", reply_markup=get_groups_keyboard(groups))

@router.callback_query(F.data.startswith("grp_"))
async def task_group(callback: CallbackQuery, state: FSMContext):
    group_id = callback.data.replace("grp_", "")
    await state.update_data(group_id=group_id)
    await state.set_state(TaskStates.waiting_for_life_area)
    await callback.message.edit_text("🌈 Выбери сферу жизни:", reply_markup=get_life_area_keyboard())
    await callback.answer()

@router.callback_query(F.data == "new_group")
async def task_new_group(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📂 Введи название новой группы:",
        reply_markup=None
    )
    await state.set_state(TaskStates.waiting_for_group)
    await callback.answer()

@router.callback_query(F.data.startswith("area_"))
async def task_life_area(callback: CallbackQuery, state: FSMContext):
    area = callback.data.replace("area_", "")
    await state.update_data(life_area=area)
    await state.set_state(TaskStates.waiting_for_deadline)
    await callback.message.edit_text(
        "📅 Введи дедлайн в формате ГГГГ-ММ-ДД\nили отправь '-' если нет:",
        reply_markup=None
    )
    await callback.answer()

@router.message(TaskStates.waiting_for_deadline)
async def task_deadline(message: Message, state: FSMContext):
    text = message.text.strip()
    deadline = None if text == "-" else text
    await state.update_data(deadline=deadline)
    await state.set_state(TaskStates.waiting_for_estimated_hours)
    await message.answer("⏱️ Сколько часов займёт? (число или '-')")

@router.message(TaskStates.waiting_for_estimated_hours)
async def task_hours(message: Message, state: FSMContext):
    text = message.text.strip()
    hours = None if text == "-" else int(text) if text.isdigit() else None
    await state.update_data(estimated_hours=hours)
    await state.set_state(TaskStates.waiting_for_notes)
    await message.answer("📝 Заметки (или '-'):")

@router.message(TaskStates.waiting_for_notes)
async def task_notes(message: Message, state: FSMContext):
    text = message.text.strip()
    notes = "" if text == "-" else text
    await state.update_data(notes=notes)
    data = await state.get_data()
    summary = (
        f"<b>📋 Проверь задачу:</b>\n"
        f"🏷️ {data['title']}\n"
        f"📂 Группа: {data.get('group_id', '—')}\n"
        f"🌈 Сфера: {data.get('life_area', '—')}\n"
        f"📅 Дедлайн: {data.get('deadline') or 'нет'}\n"
        f"⏱️ Часы: {data.get('estimated_hours') or 'нет'}\n"
        f"📝 Заметки: {notes or 'нет'}"
    )
    await state.set_state(TaskStates.waiting_for_confirm)
    await message.answer(summary, reply_markup=get_confirm_task_keyboard())

@router.callback_query(F.data == "confirm_task")
async def confirm_task(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    new_task = await create_task(
        title=data["title"],
        group_id=data.get("group_id", "group_001"),
        life_area=data.get("life_area", "other"),
        deadline=data.get("deadline"),
        estimated_hours=data.get("estimated_hours"),
        notes=data.get("notes", "")
    )
    await callback.message.edit_text(f"✅ Задача '<b>{new_task['title']}</b>' создана!")
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "cancel_task")
async def cancel_task_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Создание задачи отменено.")
    await callback.answer()

@router.message(Command("done"))
async def cmd_done(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Укажи ID задачи: /done task_20260415_001")
        return
    task_id = parts[1]
    if await complete_task(task_id):
        await message.answer(
            f"✅ Задача <code>{task_id}</code> выполнена!\n\n"
            f"🌸 Хочешь добавить её как достижение? Используй /achievements",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer("❌ Задача не найдена.")

@router.message(Command("groups"))
async def cmd_groups(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    groups = await list_groups()
    if not groups:
        await message.answer("📂 Нет групп. Создай через /newgroup")
        return
    text = "\n".join([f"• {g['name']} ({g['id']})" for g in groups])
    await message.answer(f"📂 <b>Группы:</b>\n{text}")

@router.message(Command("newgroup"))
async def cmd_newgroup(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используй: /newgroup Название группы")
        return
    name = parts[1].strip()
    group = await create_group(name)
    await message.answer(f"✅ Группа '{group['name']}' создана!")

@router.message(Command("archive"))
async def cmd_archive(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    tasks = await load_tasks()
    completed = [t for t in tasks if t.get("status") == "completed"]
    if not completed:
        await message.answer("📦 Нет завершённых задач для архивации.")
        return
    archive_file = f"tasks_archive_{_today()}.json"
    await safe_write_gardener_file(archive_file, completed)
    active = [t for t in tasks if t.get("status") != "completed"]
    await save_tasks(active)
    await message.answer(f"📦 {len(completed)} задач перемещено в архив.")

# ─── /leave ───────────────────────────────────────────────────────────────────

@router.message(Command("leave"))
async def cmd_leave(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    if not await is_authorized(user_id):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(LeaveStates.waiting_for_confirm)
    await message.answer(
        "🌙 <b>Ты хочешь архивировать свой Сад?</b>\n\n"
        "Твои данные будут сохранены. Companion перестанет писать первым. "
        "Ты можешь вернуться в любой момент.\n\n"
        "<i>Это не конец — это пауза.</i>",
        reply_markup=get_leave_confirm_keyboard()
    )

@router.callback_query(F.data == "leave_confirm")
async def leave_confirm(callback: CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    gardener = await read_gardener()
    if gardener:
        gardener.setdefault("companion_settings", {})["proactive_mode"] = False
        gardener["identity"]["updated"] = _today()
        await safe_write_gardener_file("gardener.json", gardener)
    _invalidate_auth_cache(user_id)
    await state.clear()
    await callback.message.edit_text(
        "🌙 <b>Твой Сад засыпает.</b>\n\n"
        "Спасибо за то, что рос вместе со мной.\n"
        "Возвращайся когда захочешь — я буду здесь. 🌸"
    )
    await callback.answer()

@router.callback_query(F.data == "leave_cancel")
async def leave_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🌿 Хорошо. Сад продолжает цвести!")
    await callback.answer()

@router.message(Command("delete_all"))
async def cmd_delete_all(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    if not await is_authorized(user_id):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(LeaveStates.waiting_for_delete_confirm_1)
    await message.answer(
        "⚠️ <b>Это действие необратимо.</b>\n\n"
        "Все твои данные (профиль, задачи, достижения) будут удалены навсегда.\n\n"
        "Напиши <code>УДАЛИТЬ</code> для подтверждения:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(LeaveStates.waiting_for_delete_confirm_1))
async def delete_confirm_1(message: Message, state: FSMContext):
    if message.text.strip() != "УДАЛИТЬ":
        await message.answer("❌ Отменено. Напиши точно: УДАЛИТЬ")
        await state.clear()
        return
    await state.set_state(LeaveStates.waiting_for_delete_confirm_2)
    await message.answer(
        "⚠️ Последнее подтверждение.\n\nНапиши <code>ДА, УДАЛИТЬ ВСЁ</code>:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(LeaveStates.waiting_for_delete_confirm_2))
async def delete_confirm_2(message: Message, state: FSMContext):
    if message.text.strip() != "ДА, УДАЛИТЬ ВСЁ":
        await message.answer("❌ Отменено.")
        await state.clear()
        return
    await safe_write_gardener_file("gardener.json", {})
    await safe_write_gardener_file("tasks.json", [])
    await safe_write_gardener_file("achievements.json", [])
    _invalidate_auth_cache(str(message.from_user.id))
    await state.clear()
    await message.answer(
        "🌑 Сад очищен.\n\nЕсли захочешь начать заново — /start 🌱",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="/start")]],
            resize_keyboard=True
        )
    )

# ─── Engineer chat ────────────────────────────────────────────────────────────

@router.message(F.text == "💬 В инженерный чат")
async def btn_engineer_chat(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(EngineerChatStates.waiting_for_message)
    await message.answer(
        "💬 <b>Инженерный чат</b>\n\n"
        "Напиши сообщение — оно отправится в основную сессию engineer-chat.\n\n"
        "Для отмены нажми ❌ Отмена",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(EngineerChatStates.waiting_for_message))
async def engineer_chat_send(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("💬 Напиши сообщение или нажми ❌ Отмена")
        return
    gardener = await read_gardener() or {}
    try:
        payload = {
            "session_id": MAIN_SESSION_ID,
            "message": text,
            "gardener_context": gardener
        }
        session = await get_http_session()
        async with session.post(
            SR_BACKEND_URL, json=payload,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status in [200, 202]:
                logger.info(f"Message sent to engineer-chat: {text[:50]}...")
    except Exception as e:
        logger.error(f"Bot ask exception: {e}")
    await state.clear()
    await message.answer("✅ Отправлено в инженерный чат", reply_markup=get_main_keyboard())

# ─── Cancel ───────────────────────────────────────────────────────────────────

@router.message(F.text == "❌ Отмена")
async def btn_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=get_main_keyboard())

# ─── Startup / Shutdown ───────────────────────────────────────────────────────

async def on_startup(app: web.Application):
    await bot.set_webhook(WEBHOOK_URL, secret_token=WEBHOOK_SECRET)
    logger.info(f"Webhook set: {WEBHOOK_URL}")

    # Start scheduler
    scheduler = AsyncIOScheduler()
    # Proactive messages: check every minute
    scheduler.add_job(run_proactive_scheduler, "interval", minutes=1)
    # Resonance decay: daily at 03:00
    scheduler.add_job(run_resonance_decay, CronTrigger(hour=3, minute=0))
    # Queue drain: every 15 minutes
    scheduler.add_job(drain_queue, "interval", minutes=15)
    scheduler.start()
    app["scheduler"] = scheduler
    logger.info("Scheduler started")

async def on_shutdown(app: web.Application):
    scheduler = app.get("scheduler")
    if scheduler:
        scheduler.shutdown(wait=False)
    global _http_session
    if _http_session and not _http_session.closed:
        await _http_session.close()
    await bot.delete_webhook()
    await bot.session.close()

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET
    ).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
