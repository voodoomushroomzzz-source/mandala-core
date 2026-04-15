#!/usr/bin/env python3
"""
Mandala Garden Bot — Gentle Companion v5.5.0
Fixes from v5.4.0:
- BUG FIX: task_new_group — missing text handler for TaskStates.waiting_for_group
  caused infinite hang when user typed new group name → FIXED
- BUG FIX: /tasks showed no buttons to add/manage tasks → FIXED with inline keyboard
- BUG FIX: _silence_phase returned 3 for new users (no tracked interaction) →
  proactive messages never fired for new users → FIXED: unknown = phase 1
- BUG FIX: proactive scheduler used exact HH:MM string match → missed if scheduler
  ran at :37 but setting was :00 → FIXED: 90-second window
- BUG FIX: proactive scheduler called read_gardener() every minute (GitHub API) →
  FIXED: 5-minute gardener cache for scheduler
- BUG FIX: confirm_task callback didn't return main keyboard → FIXED
- IMPROVEMENT: cancel_task callback now returns main keyboard
- IMPROVEMENT: all FSM message handlers use StateFilter consistently
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
_auth_cache: dict = {}
AUTH_CACHE_TTL = 60

# ─── Gardener cache (for proactive scheduler) ─────────────────────────────────
_gardener_cache: Optional[dict] = None
_gardener_cache_ts: float = 0.0
GARDENER_CACHE_TTL = 300  # 5 minutes

async def get_gardener_cached() -> Optional[dict]:
    global _gardener_cache, _gardener_cache_ts
    now = time.time()
    if _gardener_cache is not None and (now - _gardener_cache_ts) < GARDENER_CACHE_TTL:
        return _gardener_cache
    gardener = await read_gardener()
    if gardener:
        _gardener_cache = gardener
        _gardener_cache_ts = now
    return gardener

def _invalidate_gardener_cache() -> None:
    global _gardener_cache, _gardener_cache_ts
    _gardener_cache = None
    _gardener_cache_ts = 0.0

# ─── Proactive / Silence trackers ─────────────────────────────────────────────
_proactive_sent_today: dict = {}
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
        "User-Agent": "MandalaGardenBot/5.4.1"
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
        "User-Agent": "MandalaGardenBot/5.4.1"
    }
    session = await get_http_session()
    sha = None
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                sha = (await resp.json()).get("sha")
    except Exception:
        pass
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
            ok = resp.status in [200, 201]
            if ok:
                _invalidate_gardener_cache()
            return ok
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
    vals = []
    for area in life_areas.values():
        if isinstance(area, dict):
            vals.append(area.get("current", 5))
    avg = sum(vals) / len(vals) if vals else 5
    return max(10, round(10 + avg / 4 * 2))

async def _add_growth_history_entry(gardener: dict, resonance: int) -> dict:
    history = gardener.get("growth_history", [])
    today = _today()
    if not history or history[-1].get("date") != today:
        achievements = await read_gardener_file("achievements.json") or []
        history.append({
            "date": today,
            "resonance": resonance,
            "achievements_count": len(achievements)
        })
    gardener["growth_history"] = history[-90:]
    return gardener

async def _apply_resonance_decay(gardener: dict) -> Tuple[dict, bool]:
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

async def list_groups() -> list:
    data = await read_groups()
    return data.get("groups", [])

async def create_group(name: str) -> dict:
    data = await read_groups()
    groups = data.get("groups", [])
    base_id = "".join(c for c in name.lower() if c.isalnum() or c == "_") or "group"
    gid = base_id
    counter = 1
    while any(g.get("id") == gid for g in groups):
        gid = f"{base_id}_{counter}"
        counter += 1
    new_group = {"id": gid, "name": name, "created": _today()}
    groups.append(new_group)
    data["groups"] = groups
    await safe_write_gardener_file("groups.json", data)
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
    waiting_for_group = State()   # handles both inline group select AND text input for new group
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
        keyboard=[[KeyboardButton(text="— Отмена")]],
        resize_keyboard=True, one_time_keyboard=True
    )

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="◈ Профиль"), KeyboardButton(text="◆ Достижения")],
            [KeyboardButton(text="⬡ Задачи"), KeyboardButton(text="⟁ Резонанс")],
            [KeyboardButton(text="⌬ Инженерный чат")]
        ],
        resize_keyboard=True
    )

def get_achievement_category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◆ Здоровье", callback_data="ach_cat_health")],
        [InlineKeyboardButton(text="◆ Творчество", callback_data="ach_cat_creativity")],
        [InlineKeyboardButton(text="◆ Знания", callback_data="ach_cat_knowledge")],
        [InlineKeyboardButton(text="◆ Исследования", callback_data="ach_cat_exploration")],
        [InlineKeyboardButton(text="◆ Отношения", callback_data="ach_cat_relationships")],
        [InlineKeyboardButton(text="— Отмена", callback_data="cancel_achievement")]
    ])

def get_groups_keyboard(groups: list) -> InlineKeyboardMarkup:
    btns = [[InlineKeyboardButton(text=g["name"], callback_data=f"grp_{g['id']}")] for g in groups]
    btns.append([InlineKeyboardButton(text="➕ Новая группа", callback_data="new_group")])
    btns.append([InlineKeyboardButton(text="— Отмена", callback_data="cancel_task")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def get_life_area_keyboard() -> InlineKeyboardMarkup:
    areas = [
        ("◆ Здоровье", "health"), ("◆ Творчество", "creativity"),
        ("◆ Знания", "knowledge"), ("◆ Исследования", "exploration"),
        ("◆ Отношения", "relationships"), ("◆ Другое", "other")
    ]
    btns = [[InlineKeyboardButton(text=name, callback_data=f"area_{val}")] for name, val in areas]
    btns.append([InlineKeyboardButton(text="— Отмена", callback_data="cancel_task")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def get_confirm_task_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◈ Подтвердить", callback_data="confirm_task")],
        [InlineKeyboardButton(text="— Отмена", callback_data="cancel_task")]
    ])

def get_tasks_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="+ Новая задача", callback_data="start_addtask")],
    ])

def get_leave_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◈ Да, архивировать", callback_data="leave_confirm")],
        [InlineKeyboardButton(text="◈ Нет, остаюсь", callback_data="leave_cancel")]
    ])

# ─── Interaction tracker ──────────────────────────────────────────────────────

def _track_interaction(telegram_id: str) -> None:
    _last_interaction[str(telegram_id)] = _today()

# ─── Proactive messaging ──────────────────────────────────────────────────────

def _can_send_proactive(telegram_id: str) -> bool:
    return _proactive_sent_today.get(str(telegram_id)) != _today()

def _mark_proactive_sent(telegram_id: str) -> None:
    _proactive_sent_today[str(telegram_id)] = _today()

def _silence_phase(telegram_id: str) -> int:
    """
    FIX: unknown interaction → phase 1 (was phase 3, broke proactive for new users).
    """
    last = _last_interaction.get(str(telegram_id))
    if not last:
        return 1  # FIX: was 3
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

def _time_matches(setting_time: str) -> bool:
    """FIX: 90-second window instead of exact HH:MM string match."""
    if not setting_time:
        return False
    try:
        now = datetime.now()
        h, m = map(int, setting_time.split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        diff = abs((now - target).total_seconds())
        return diff <= 90
    except Exception:
        return False

async def send_morning_greeting(telegram_id: str) -> None:
    phase = _silence_phase(telegram_id)
    if phase == 3:
        return
    if not _can_send_proactive(telegram_id):
        return
    gardener = await get_gardener_cached()
    if not gardener:
        return
    if str(gardener.get("identity", {}).get("telegram_id", "")) != str(telegram_id):
        return
    if not gardener.get("companion_settings", {}).get("proactive_mode", True):
        return
    name = gardener.get("identity", {}).get("name", "Садовник")
    if phase == 2:
        text = f"◈ {name}, я здесь если понадоблюсь.\nБез давления. Система ждёт твоего сигнала."
    else:
        tasks = await load_tasks()
        active = [t for t in tasks if t.get("status") != "completed"]
        task_hint = ""
        if active:
            top = sorted(active, key=lambda x: x.get("priority", 5), reverse=True)[0]
            task_hint = f"\n\n◈ Рекомендую сегодня: <i>{top['title']}</i>"
        text = f"◬ Утро, {name}!\n\nНовый цикл — новая возможность.{task_hint}\n\nКак ты? ◈"
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
    gardener = await get_gardener_cached()
    if not gardener:
        return
    if str(gardener.get("identity", {}).get("telegram_id", "")) != str(telegram_id):
        return
    if not gardener.get("companion_settings", {}).get("proactive_mode", True):
        return
    name = gardener.get("identity", {}).get("name", "Садовник")
    text = (
        f"◬ Вечер, {name}.\n\n"
        f"Что произошло сегодня? Если было что-то важное — "
        f"Зафикисруй достижение: /achievements\n\nДо следующего цикла. ◈"
    )
    try:
        await bot.send_message(int(telegram_id), text, reply_markup=get_main_keyboard())
        _mark_proactive_sent(telegram_id)
        logger.info(f"Evening check-in sent to {telegram_id}")
    except Exception as e:
        logger.error(f"Failed to send evening check-in: {e}")

async def run_proactive_scheduler() -> None:
    """Uses cached gardener — avoids GitHub API call every minute."""
    gardener = await get_gardener_cached()
    if not gardener:
        return
    telegram_id = str(gardener.get("identity", {}).get("telegram_id", ""))
    if not telegram_id:
        return
    settings = gardener.get("companion_settings", {})
    morning_time = settings.get("morning_message_time", "")
    evening_time = settings.get("evening_check_time", "")
    if morning_time and _time_matches(morning_time):
        await send_morning_greeting(telegram_id)
    if evening_time and _time_matches(evening_time):
        await send_evening_checkin(telegram_id)

async def run_resonance_decay() -> None:
    gardener = await read_gardener()
    if not gardener:
        return
    gardener, changed = await _apply_resonance_decay(gardener)
    if changed:
        await safe_write_gardener_file("gardener.json", gardener)
        _invalidate_gardener_cache()
        logger.info("Resonance decay applied")

# ─── /start + onboarding ──────────────────────────────────────────────────────

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
        await message.answer(f"◈ С возвращением, {name}!", reply_markup=get_main_keyboard())
        return

    if gardener:
        bound_id = str(gardener.get("identity", {}).get("telegram_id", "") or "").strip()
        if bound_id and bound_id != user_id:
            if not password or password != ALLOWED_PASSWORD:
                await message.answer("◈ Доступ защищён паролем.\nИспользуй: /start <пароль>")
                return
            gardener.setdefault("identity", {})["telegram_id"] = user_id
            gardener["identity"]["updated"] = _today()
            await safe_write_gardener_file("gardener.json", gardener)
            _invalidate_auth_cache(user_id)
            _invalidate_gardener_cache()
            await drain_queue()

    await state.set_state(GardenOnboardingStates.waiting_for_name)
    await message.answer(
        "◬ <b>Добро пожаловать в систему!</b>\n\n"
        "Я — твой Gentle Companion. Давай познакомимся.\n\n"
        "◈ Как тебя зовут? Это имя будет только между нами.",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_name))
async def onboarding_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("◈ Имя должно быть не короче 2 символов.")
        return
    await state.update_data(name=name)
    await state.set_state(GardenOnboardingStates.waiting_for_interests)
    await message.answer(
        f"◬ Приятно познакомиться, {name}!\n\n"
        "◈ Что тебя вдохновляет прямо сейчас? Напиши 3 вещи через запятую.\n\n"
        "<i>Первое, что приходит в голову — самое честное.</i>",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_interests))
async def onboarding_interests(message: Message, state: FSMContext):
    interests = [i.strip() for i in message.text.split(",") if i.strip()]
    if len(interests) < 1:
        await message.answer("◈ Напиши хотя бы один интерес.")
        return
    await state.update_data(interests=interests)
    await state.set_state(GardenOnboardingStates.waiting_for_goals)
    await message.answer(
        "◈ Какие намерения хочешь посадить в этом сезоне?\n\n<i>Это не обязательства. Просто намерения.</i>",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_goals))
async def onboarding_goals(message: Message, state: FSMContext):
    goals = [g.strip() for g in message.text.split(",") if g.strip()]
    await state.update_data(goals=goals)
    await state.set_state(GardenOnboardingStates.waiting_for_health_current)
    await message.answer("◆ Здоровье — оцени сейчас (1-10) — от 1 до 10.", reply_markup=get_cancel_keyboard())

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
    await message.answer("◆ Цель по здоровью (1-10)? (1-10)")

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
    await message.answer("◆ Творчество — оцени сейчас (1-10) от 1 до 10.")

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
    await message.answer("◆ Цель по творчеству (1-10)? (1-10)")

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
        "◷ Время утреннего сигнала (ЧЧ:ММ или 'нет') получать утреннее приветствие?\n"
        "Формат ЧЧ:ММ или 'нет'.",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_morning))
async def onboarding_morning(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    morning = "" if text == "нет" else text
    await state.update_data(morning_time=morning)
    await state.set_state(GardenOnboardingStates.waiting_for_evening)
    await message.answer("◷ Вечерний сигнал (ЧЧ:ММ или 'нет')? (ЧЧ:ММ или 'нет')")

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
            "gardener_id": GARDENER_ID, "telegram_id": user_id,
            "name": data["name"], "resonance_level": initial_resonance,
            "created": _today(), "updated": _today()
        },
        "personal_info": {
            "interests": data["interests"], "goals": data["goals"],
            "life_areas": life_areas
        },
        "companion_settings": {
            "morning_message_time": data["morning_time"],
            "evening_check_time": evening,
            "proactive_mode": True, "timezone": "Europe/Moscow"
        },
        "growth_history": [{"date": _today(), "resonance": initial_resonance, "achievements_count": 0}]
    }
    groups = {
        "groups": [
            {"id": "group_001", "name": "◈ Личное", "created": _today()},
            {"id": "group_002", "name": "◈ Работа", "created": _today()},
            {"id": "group_003", "name": "◈ Дом", "created": _today()}
        ],
        "default_group": "group_001"
    }

    success = await safe_write_gardener_file("gardener.json", gardener)
    if not success:
        await message.answer("⚠️ Не смог сохранить профиль в GitHub. Записал локально и синхронизирую позже.")
        await state.clear()
        return

    await safe_write_gardener_file("tasks.json", [])
    await safe_write_gardener_file("achievements.json", [])
    await safe_write_gardener_file("groups.json", groups)
    await drain_queue()

    _invalidate_auth_cache(user_id)
    _invalidate_gardener_cache()
    _track_interaction(user_id)
    await state.set_state(GardenOnboardingStates.done)
    await message.answer(
        f"◬ <b>{data['name']}, добро пожаловать в систему!</b>\n\n"
        f"◈ Начальный резонанс: <b>{initial_resonance}%</b>\n\n"
        f"— Резонанс только растёт. Нет наказаний за паузы.\n\nСистема активна ◈",
        reply_markup=get_main_keyboard()
    )

# ─── /profile ─────────────────────────────────────────────────────────────────

@router.message(Command("profile"))
@router.message(F.text == "◈ Профиль")
async def cmd_profile(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("◈ Используй /start")
        return
    gardener = await read_gardener()
    if not gardener:
        await message.answer("◈ Профиль не найден")
        return
    name = gardener.get("identity", {}).get("name", "Садовник")
    resonance = gardener.get("identity", {}).get("resonance_level", 13)
    tasks = await load_tasks()
    active_tasks = [t for t in tasks if t.get("status") != "completed"]
    interests = gardener.get("personal_info", {}).get("interests", [])
    interests_str = ", ".join(interests[:3]) if interests else "не указаны"
    await message.answer(
        f"◈ <b>{name}</b>\n⟁ Резонанс: <b>{resonance}%</b>\n"
        f"⬡ Активных задач: {len(active_tasks)}\n◈ Интересы: {interests_str}",
        reply_markup=get_main_keyboard()
    )

# ─── /resonance ───────────────────────────────────────────────────────────────

@router.message(Command("resonance"))
@router.message(F.text == "⟁ Резонанс")
async def cmd_resonance(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("◈ Используй /start", reply_markup=get_main_keyboard())
        return
    gardener = await read_gardener()
    if not gardener:
        await message.answer("◈ Профиль не найден", reply_markup=get_main_keyboard())
        return

    resonance = gardener.get("identity", {}).get("resonance_level", 13)
    history = gardener.get("growth_history", [])
    life_areas = gardener.get("personal_info", {}).get("life_areas", {})

    area_icons = {"health": "💚", "creativity": "🎨", "knowledge": "📚", "relationships": "🤝"}
    areas_text = ""
    for area, icon in area_icons.items():
        d = life_areas.get(area, {})
        areas_text += f"{icon} {area.capitalize()}: {d.get('current','?')}/10 → цель {d.get('target','?')}/10\n"

    if history:
        recent = history[-5:]
        history_text = "\n◈ <b>Хроника роста:</b>\n"
        for entry in reversed(recent):
            history_text += f"• {entry.get('date','?')}: {entry.get('resonance','?')}% ({entry.get('achievements_count',0)} достиж.)\n"
    else:
        history_text = "\n<i>История пока пуста — начни добавлять достижения!</i>"

    bar_filled = round(resonance / 10)
    bar = "■" * bar_filled + "□" * (10 - bar_filled)

    await message.answer(
        f"⟁ <b>Резонанс системы</b>\n\n{bar}\n<b>{resonance}%</b>\n\n"
        f"◆ <b>Орбиты:</b>\n{areas_text}{history_text}\n\n"
        f"<i>Резонанс только растёт. Каждое достижение расширяет орбиту.</i>",
        reply_markup=get_main_keyboard()
    )

# ─── /ask ─────────────────────────────────────────────────────────────────────

@router.message(Command("ask"))
async def cmd_ask(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("◈ Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(AskStates.waiting_for_question)
    await message.answer(
        "◬ <b>Companion слушает</b>\n\nЧто у тебя на душе? Задай вопрос или просто поделись.\n\n"
        "<i>Нажми — Отмена чтобы вернуться.</i>",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(AskStates.waiting_for_question))
async def ask_question(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    text = message.text.strip()
    if not text:
        await message.answer("◈ Напиши что-нибудь или нажми — Отмена")
        return
    gardener = await read_gardener() or {}
    name = gardener.get("identity", {}).get("name", "Садовник")
    resonance = gardener.get("identity", {}).get("resonance_level", 13)
    await message.answer("◈ Обрабатываю...")
    try:
        payload = {
            "session_id": MAIN_SESSION_ID,
            "message": f"[Садовник {name}, резонанс {resonance}%] спрашивает: {text}\n\nОтветь как Gentle Companion — тепло, без давления, в духе Ахимсы.",
            "gardener_context": gardener
        }
        session = await get_http_session()
        async with session.post(SR_BACKEND_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status in [200, 202]:
                try:
                    data = await resp.json()
                    reply = data.get("response") or data.get("message") or "◈ Система слышит тебя."
                except Exception:
                    reply = "◈ Я слышу тебя. SR с тобой."
            else:
                reply = "◈ SR недоступен, но я здесь рядом."
    except Exception as e:
        logger.error(f"Ask SR error: {e}")
        reply = "◈ Связь с SR прервалась. Попробуй позже."
    await state.clear()
    await message.answer(reply, reply_markup=get_main_keyboard())

# ─── /achievements ────────────────────────────────────────────────────────────

@router.message(Command("achievements"))
@router.message(F.text == "◆ Достижения")
async def cmd_achievements(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("◈ Используй /start")
        return
    achievements = await read_gardener_file("achievements.json") or []
    add_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◈ Добавить достижение", callback_data="add_achievement")]
    ])
    if not achievements:
        await message.answer(
            "◈ Достижений пока нет.\n\nКаждое достижение расширяет твою орбиту.\nДобавь первое.",
            reply_markup=add_btn
        )
        return
    recent = achievements[-3:]
    text = "◆ <b>Достижения:</b>\n\n"
    for ach in reversed(recent):
        text += f"{ach.get('icon','◈')} <b>{ach.get('title','')}</b>\n📅 {ach.get('completed','')} · +{ach.get('resonance_bonus',1)} резонанс\n\n"
    text += f"<i>◈ Всего: {len(achievements)}</i>"
    await message.answer(text, reply_markup=add_btn)

@router.callback_query(F.data == "add_achievement")
async def cb_add_achievement(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AchievementStates.waiting_for_category)
    await callback.message.answer(
        "◈ <b>Что проявилось в твоей орбите?</b>\n\nВыбери сферу:",
        reply_markup=get_achievement_category_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("ach_cat_"))
async def ach_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.replace("ach_cat_", "")
    await state.update_data(category=category)
    await state.set_state(AchievementStates.waiting_for_title)
    await callback.message.edit_text("◈ Как назовёшь это достижение?\n\n<i>Одним предложением.</i>", reply_markup=None)
    await callback.answer()

@router.message(StateFilter(AchievementStates.waiting_for_title))
async def ach_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AchievementStates.waiting_for_description)
    await message.answer("◈ Подробнее (или '-'): (или '-'):")

@router.message(StateFilter(AchievementStates.waiting_for_description))
async def ach_description(message: Message, state: FSMContext):
    desc = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(description=desc)
    await state.set_state(AchievementStates.waiting_for_bonus)
    await message.answer("◈ Значимость (1-10): для тебя? Оцени от 1 до 10.\n\n<i>Бонус к резонансу.</i>")

@router.message(StateFilter(AchievementStates.waiting_for_bonus))
async def ach_bonus(message: Message, state: FSMContext):
    try:
        bonus = max(1, min(10, int(message.text.strip())))
    except Exception:
        bonus = 3
    data = await state.get_data()
    icon = {"health": "◆", "creativity": "◆", "knowledge": "◆", "exploration": "◆", "relationships": "◆"}.get(data.get("category", ""), "◈")
    achievements = await read_gardener_file("achievements.json") or []
    achievements.append({
        "id": f"ach_{len(achievements)+1:03d}",
        "category": data.get("category", "other"),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "completed": _today(),
        "resonance_bonus": bonus,
        "icon": icon
    })
    await safe_write_gardener_file("achievements.json", achievements)
    gardener = await read_gardener()
    if gardener:
        current_res = gardener.get("identity", {}).get("resonance_level", 13)
        new_res = min(100, current_res + bonus)
        gardener.setdefault("identity", {})["resonance_level"] = new_res
        gardener["identity"]["updated"] = _today()
        gardener = await _add_growth_history_entry(gardener, new_res)
        await safe_write_gardener_file("gardener.json", gardener)
        _invalidate_auth_cache(str(message.from_user.id))
        _invalidate_gardener_cache()
    await state.clear()
    await message.answer(
        f"{icon} <b>Достижение добавлено!</b>\n\n<b>{data.get('title','')}</b>\n◈ +{bonus} к резонансу\n\n<i>Орбита расширяется ◈</i>",
        reply_markup=get_main_keyboard()
    )

@router.callback_query(F.data == "cancel_achievement")
async def cb_cancel_achievement(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("— Отменено.")
    await callback.answer()

# ─── /tasks ───────────────────────────────────────────────────────────────────

@router.message(Command("tasks"))
@router.message(F.text == "⬡ Задачи")
async def cmd_tasks(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("◈ Используй /start", reply_markup=get_main_keyboard())
        return
    tasks = await load_tasks()
    active = [t for t in tasks if t.get("status") != "completed"]
    if not active:
        await message.answer("◈ Активных задач нет.\n\nИнициируй первую задачу.", reply_markup=get_main_keyboard())
        await message.answer("Добавить:", reply_markup=get_tasks_keyboard())
        return
    lines = []
    for t in active[:15]:
        dl = f" 📅{t['deadline']}" if t.get("deadline") else ""
        lines.append(f"• <code>{t['task_id']}</code>: {t['title']} (⭐{t.get('priority',5)}){dl}")
    text = "⬡ <b>Активные задачи:</b>\n\n" + "\n".join(lines)
    text += "\n\n<i>Завершить: /done task_id</i>"
    await message.answer(text, reply_markup=get_main_keyboard())
    await message.answer("Действия:", reply_markup=get_tasks_keyboard())

# ─── /addtask ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "start_addtask")
async def cb_start_addtask(callback: CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    if not await is_authorized(user_id):
        await callback.answer("Используй /start")
        return
    await callback.answer()  # FIX: answer FIRST
    await state.set_state(TaskStates.waiting_for_title)
    await callback.message.answer("◈ Название задачи:", reply_markup=get_cancel_keyboard())

@router.message(Command("addtask"))
async def cmd_addtask(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("◈ Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(TaskStates.waiting_for_title)
    await message.answer("◈ Название задачи:", reply_markup=get_cancel_keyboard())

@router.message(StateFilter(TaskStates.waiting_for_title))
async def task_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) < 2:
        await message.answer("📝 Название должно быть не короче 2 символов.")
        return
    await state.update_data(title=title)
    await state.set_state(TaskStates.waiting_for_group)
    groups = await list_groups()
    await message.answer("⬡ Выбери орбиту или создай новую:", reply_markup=get_groups_keyboard(groups))

@router.callback_query(F.data.startswith("grp_"))
async def task_group(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIX: answer FIRST
    group_id = callback.data.replace("grp_", "")
    await state.update_data(group_id=group_id)
    await state.set_state(TaskStates.waiting_for_life_area)
    await callback.message.edit_text("⬡ Выбери сферу:", reply_markup=get_life_area_keyboard())

@router.callback_query(F.data == "new_group")
async def task_new_group_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIX: answer FIRST
    await callback.message.edit_text("⬡ Введи название новой орбиты:", reply_markup=None)

# ══════════════════════════════════════════════════════════════════════════════
# KEY FIX: This handler was MISSING in v5.3.0 and v5.4.0.
# When user types a group name after clicking "New group", the message was
# not handled (no text handler for TaskStates.waiting_for_group existed).
# Result: FSM stuck → bot hangs forever waiting for a callback that never comes.
# ══════════════════════════════════════════════════════════════════════════════
@router.message(StateFilter(TaskStates.waiting_for_group))
async def task_group_name_input(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 1:
        await message.answer("📂 Введи название группы (минимум 1 символ).")
        return
    new_group = await create_group(name)
    await state.update_data(group_id=new_group["id"])
    await state.set_state(TaskStates.waiting_for_life_area)
    await message.answer(
        f"✅ Группа '<b>{new_group['name']}</b>' создана!\n\n◆ Выбери сферу:",
        reply_markup=get_life_area_keyboard()
    )

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

@router.message(StateFilter(TaskStates.waiting_for_deadline))
async def task_deadline(message: Message, state: FSMContext):
    text = message.text.strip()
    deadline = None if text == "-" else text
    await state.update_data(deadline=deadline)
    await state.set_state(TaskStates.waiting_for_estimated_hours)
    await message.answer("⏱️ Сколько часов займёт? (число или '-')")

@router.message(StateFilter(TaskStates.waiting_for_estimated_hours))
async def task_hours(message: Message, state: FSMContext):
    text = message.text.strip()
    hours = None if text == "-" else int(text) if text.isdigit() else None
    await state.update_data(estimated_hours=hours)
    await state.set_state(TaskStates.waiting_for_notes)
    await message.answer("📝 Заметки (или '-'):")

@router.message(StateFilter(TaskStates.waiting_for_notes))
async def task_notes(message: Message, state: FSMContext):
    text = message.text.strip()
    notes = "" if text == "-" else text
    await state.update_data(notes=notes)
    data = await state.get_data()
    summary = (
        f"<b>◈ Проверь задачу:</b>\n\n"
        f"🏷️ <b>{data['title']}</b>\n"
        f"📂 Группа: {data.get('group_id','—')}\n"
        f"◆ Сфера: {data.get('life_area','—')}\n"
        f"◷ Дедлайн: {data.get('deadline') or 'нет'}\n"
        f"◈ Часы: {data.get('estimated_hours') or 'нет'}\n"
        f"◈ Заметки: {notes or 'нет'}"
    )
    await state.set_state(TaskStates.waiting_for_confirm)
    await message.answer(summary, reply_markup=get_confirm_task_keyboard())

@router.callback_query(F.data == "confirm_task")
async def confirm_task(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Сохраняю в систему...")  # FIX: answer FIRST
    data = await state.get_data()
    new_task = await create_task(
        title=data["title"],
        group_id=data.get("group_id", "group_001"),
        life_area=data.get("life_area", "other"),
        deadline=data.get("deadline"),
        estimated_hours=data.get("estimated_hours"),
        notes=data.get("notes", "")
    )
    await callback.message.edit_text(
        f"◈ Задача '<b>{new_task['title']}</b>' создана!\n<code>{new_task['task_id']}</code>"
    )
    await state.clear()
    await callback.answer("Задача зафиксирована ◈")
    await callback.message.answer("◈ Задача зафиксирована.", reply_markup=get_main_keyboard())

@router.callback_query(F.data == "cancel_task")
async def cancel_task_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIX: answer FIRST
    await state.clear()
    await callback.message.edit_text("— отменено")
    await callback.message.answer("◈ Возврат в систему", reply_markup=get_main_keyboard())

@router.message(Command("done"))
async def cmd_done(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("◈ Используй /start", reply_markup=get_main_keyboard())
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("◈ ID задачи: <code>/done task_20260415_001</code>", reply_markup=get_main_keyboard())
        return
    task_id = parts[1]
    if await complete_task(task_id):
        await message.answer(
            f"◈ Задача <code>{task_id}</code> выполнена!\n\n◈ Добавь как достижение? /achievements",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer("◈ Задача не найдена.", reply_markup=get_main_keyboard())

@router.message(Command("groups"))
async def cmd_groups(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("◈ Используй /start", reply_markup=get_main_keyboard())
        return
    groups = await list_groups()
    if not groups:
        await message.answer("⬡ Орбит нет. Создай через /newgroup")
        return
    text = "\n".join([f"• {g['name']} ({g['id']})" for g in groups])
    await message.answer(f"⬡ <b>Орбиты:</b>\n{text}")

@router.message(Command("newgroup"))
async def cmd_newgroup(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("◈ Используй /start", reply_markup=get_main_keyboard())
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используй: /newgroup Название группы")
        return
    group = await create_group(parts[1].strip())
    await message.answer(f"◈ Орбита '{group['name']}' создана.")

@router.message(Command("archive"))
async def cmd_archive(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("◈ Используй /start", reply_markup=get_main_keyboard())
        return
    tasks = await load_tasks()
    completed = [t for t in tasks if t.get("status") == "completed"]
    if not completed:
        await message.answer("◈ Завершённых задач нет.")
        return
    await safe_write_gardener_file(f"tasks_archive_{_today()}.json", completed)
    await save_tasks([t for t in tasks if t.get("status") != "completed"])
    await message.answer(f"◈ {len(completed)} задач перемещено в архив.")

# ─── /leave ───────────────────────────────────────────────────────────────────

@router.message(Command("leave"))
async def cmd_leave(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    if not await is_authorized(user_id):
        await message.answer("◈ Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(LeaveStates.waiting_for_confirm)
    await message.answer(
        "◈ <b>Архивировать свой Сад?</b>\n\n"
        "Твои данные будут сохранены. Companion перестанет писать первым.\n\n"
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
    _invalidate_gardener_cache()
    await state.clear()
    await callback.message.edit_text(
        "◈ <b>Система переходит в архив.</b>\n\nСпасибо за то, что рос вместе со мной.\n"
        "Возвращайся когда захочешь. ◈"
    )
    await callback.answer()

@router.callback_query(F.data == "leave_cancel")
async def leave_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("◈ Система активна. Продолжаем.")
    await callback.answer()

@router.message(Command("delete_all"))
async def cmd_delete_all(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    if not await is_authorized(user_id):
        await message.answer("◈ Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(LeaveStates.waiting_for_delete_confirm_1)
    await message.answer(
        "⚠️ <b>Это действие необратимо.</b>\n\n"
        "Все данные будут удалены навсегда.\n\nНапиши <code>УДАЛИТЬ</code>:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(LeaveStates.waiting_for_delete_confirm_1))
async def delete_confirm_1(message: Message, state: FSMContext):
    if message.text.strip() != "УДАЛИТЬ":
        await message.answer("— Отменено.")
        await state.clear()
        return
    await state.set_state(LeaveStates.waiting_for_delete_confirm_2)
    await message.answer("⚠️ Последнее подтверждение.\n\nНапиши <code>ДА, УДАЛИТЬ ВСЁ</code>:", reply_markup=get_cancel_keyboard())

@router.message(StateFilter(LeaveStates.waiting_for_delete_confirm_2))
async def delete_confirm_2(message: Message, state: FSMContext):
    if message.text.strip() != "ДА, УДАЛИТЬ ВСЁ":
        await message.answer("— Отменено.")
        await state.clear()
        return
    await safe_write_gardener_file("gardener.json", {})
    await safe_write_gardener_file("tasks.json", [])
    await safe_write_gardener_file("achievements.json", [])
    _invalidate_auth_cache(str(message.from_user.id))
    _invalidate_gardener_cache()
    await state.clear()
    await message.answer(
        "◈ Данные удалены.\n\nНачать заново: /start",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="/start")]], resize_keyboard=True)
    )

# ─── Engineer chat ────────────────────────────────────────────────────────────

@router.message(F.text == "⌬ Инженерный чат")
async def btn_engineer_chat(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not await is_authorized(user_id):
        await message.answer("◈ Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(EngineerChatStates.waiting_for_message)
    await message.answer(
        "⌬ <b>Инженерный чат</b>\n\nНапиши сообщение — оно отправится в основную сессию engineer-chat.\n\nДля отмены нажми — Отмена",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(EngineerChatStates.waiting_for_message))
async def engineer_chat_send(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("◈ Напиши сообщение или нажми — Отмена")
        return
    gardener = await read_gardener() or {}
    try:
        payload = {"session_id": MAIN_SESSION_ID, "message": text, "gardener_context": gardener}
        session = await get_http_session()
        async with session.post(SR_BACKEND_URL, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status in [200, 202]:
                logger.info(f"Message sent to engineer-chat: {text[:50]}...")
    except Exception as e:
        logger.error(f"Bot ask exception: {e}")
    await state.clear()
    await message.answer("◈ Отправлено в инженерный чат", reply_markup=get_main_keyboard())

# ─── Cancel ───────────────────────────────────────────────────────────────────

@router.message(F.text == "— Отмена")
async def btn_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("— Действие отменено.", reply_markup=get_main_keyboard())

# ─── Startup / Shutdown ───────────────────────────────────────────────────────

async def on_startup(app: web.Application):
    await bot.set_webhook(WEBHOOK_URL, secret_token=WEBHOOK_SECRET)
    logger.info(f"Webhook set: {WEBHOOK_URL}")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_proactive_scheduler, "interval", minutes=1)
    scheduler.add_job(run_resonance_decay, CronTrigger(hour=3, minute=0))
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

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
