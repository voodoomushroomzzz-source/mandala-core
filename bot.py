#!/usr/bin/env python3
"""
Mandala Garden Bot — Gentle Companion v5.2.1
Integrated with /bot/ask endpoint. Password protected. Hardcoded to gardener_001.
Fixed encoding: all strings UTF-8, buttons readable.
"""

import os
import sys
import json
import logging
import base64
import asyncio
from datetime import datetime
from typing import Optional, Any, Tuple

from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import aiohttp
from dotenv import load_dotenv
from datetime import timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

# ========== LOGGING ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ========== ENV ==========
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

# ========== GARDEN CONSTANTS ==========
GARDENER_ID = "gardener_001"
GARDENER_PATH = f"honeycombs/personal_gardeners/{GARDENER_ID}"
CATALOG_ACH_PATH = "honeycombs/garden/achievements_catalog.json"
SIMBIOSIS_SEEDS_PATH = "simbiosis/seeds.json"

LOCAL_QUEUE_PATH = os.getenv("LOCAL_QUEUE_PATH", os.path.join(os.getcwd(), f".{GARDENER_ID}.json.queue"))

if not BOT_TOKEN or not RENDER_EXTERNAL_URL:
    logger.error("Missing BOT_TOKEN or RENDER_EXTERNAL_URL")
    sys.exit(1)

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ========== GITHUB API ==========
def _utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)

def _parse_date_yyyy_mm_dd(text: str) -> Optional[str]:
    t = (text or "").strip()
    if not t or t == "-":
        return None
    try:
        datetime.strptime(t, "%Y-%m-%d")
        return t
    except Exception:
        return None

def enqueue_op(op: dict) -> None:
    """Append operation to local JSONL queue. Best-effort."""
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

async def get_github_file(file_path: str) -> Tuple[bool, Optional[Any]]:
    if not GITHUB_TOKEN:
        return False, None
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}?ref=main"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/5.2.1"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = base64.b64decode(data["content"]).decode('utf-8')
                    try:
                        return True, json.loads(content)
                    except:
                        return True, content
                return False, None
        except Exception as e:
            logger.error(f"GitHub API error: {e}")
            return False, None

async def list_github_dir(dir_path: str) -> Tuple[bool, Optional[list[dict]]]:
    if not GITHUB_TOKEN:
        return False, None
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{dir_path}?ref=main"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/5.2.1"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, list):
                        return True, data
                return False, None
        except Exception as e:
            logger.error(f"GitHub dir list error: {e}")
            return False, None

async def read_gardener() -> Optional[dict]:
    ok, data = await get_github_file(f"{GARDENER_PATH}/gardener.json")
    return data if ok else None

async def read_gardener_file(filename: str) -> Optional[Any]:
    ok, data = await get_github_file(f"{GARDENER_PATH}/{filename}")
    return data if ok else None

async def read_repo_file(path: str) -> Optional[Any]:
    ok, data = await get_github_file(path)
    return data if ok else None

async def write_repo_json(path: str, content: Any) -> bool:
    if not GITHUB_TOKEN:
        return False
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/5.2.1"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=30) as resp:
                sha = (await resp.json()).get("sha") if resp.status == 200 else None
        except Exception:
            sha = None

        content_str = _json_dumps(content)
        content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
        payload = {
            "message": f"bot: update {path}",
            "content": content_b64,
            "branch": "main",
        }
        if sha:
            payload["sha"] = sha
        try:
            async with session.put(url, headers=headers, json=payload, timeout=30) as resp:
                return resp.status in [200, 201]
        except Exception:
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
            remaining.extend([x for x in ops[ops.index(op)+1:]])
            break
    write_queue(remaining)

async def write_gardener_file(filename: str, content: Any) -> bool:
    return await write_repo_json(f"{GARDENER_PATH}/{filename}", content)

async def safe_write_gardener_file(filename: str, content: Any) -> bool:
    return await safe_write_repo_json(f"{GARDENER_PATH}/{filename}", content)

async def is_authorized(telegram_id: str) -> bool:
    gardener = await read_gardener()
    if not gardener:
        return False
    return str(gardener.get("identity", {}).get("telegram_id", "")) == str(telegram_id)

# ========== PROACTIVE (D10) ==========

_scheduler: Optional[AsyncIOScheduler] = None

def _get_tz(tz_name: str):
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return None

def _parse_iso_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None

def _is_night(local_dt: datetime) -> bool:
    h = local_dt.hour
    return h < 8 or h >= 23

def _days_since(date_str: str) -> Optional[int]:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        return (datetime.now().date() - d).days
    except Exception:
        return None

async def _can_send_proactive(gardener: dict) -> tuple[bool, str]:
    if not gardener:
        return False, "no_profile"
    identity = gardener.get("identity") or {}
    tg_id = str(identity.get("telegram_id") or "").strip()
    if not tg_id:
        return False, "no_telegram_id"

    cs = gardener.get("companion_settings") or {}
    if cs.get("proactive_mode") is False:
        return False, "proactive_off"

    tz_name = cs.get("timezone") or "UTC"
    tz = _get_tz(tz_name)
    now_local = datetime.now(tz) if tz else datetime.now()
    if _is_night(now_local):
        return False, "night"

    last_interaction_iso = identity.get("last_user_interaction_at") or ""
    last_dt = _parse_iso_dt(last_interaction_iso)
    if last_dt:
        delta = datetime.utcnow() - last_dt.replace(tzinfo=None)
        days = delta.days
        if days >= 31:
            return False, "silence_31_plus"
        if 8 <= days <= 30:
            meta = cs.get("proactive_meta") or {}
            last_week_sent = meta.get("last_weekly_sent_iso") or ""
            last_week_dt = _parse_iso_dt(last_week_sent)
            if last_week_dt and (datetime.utcnow() - last_week_dt.replace(tzinfo=None)).days < 7:
                return False, "weekly_limit"

    meta = cs.get("proactive_meta") or {}
    last_sent_iso = meta.get("last_sent_iso") or ""
    last_sent = _parse_iso_dt(last_sent_iso)
    if last_sent and (datetime.utcnow() - last_sent.replace(tzinfo=None)).total_seconds() < 6 * 3600:
        return False, "cooldown_6h"

    if meta.get("last_sent_date") == _today():
        return False, "daily_limit"

    return True, "ok"

async def _mark_proactive_sent(gardener: dict) -> None:
    cs = gardener.setdefault("companion_settings", {})
    meta = cs.setdefault("proactive_meta", {})
    meta["last_sent_iso"] = _utc_iso()
    meta["last_sent_date"] = _today()
    identity = gardener.get("identity") or {}
    last_dt = _parse_iso_dt(identity.get("last_user_interaction_at") or "")
    if last_dt:
        days = (datetime.utcnow() - last_dt.replace(tzinfo=None)).days
        if 8 <= days <= 30:
            meta["last_weekly_sent_iso"] = _utc_iso()
    await safe_write_gardener_file("gardener.json", gardener)

async def _send_proactive(text: str) -> None:
    gardener = await read_gardener()
    if not gardener:
        return
    ok, reason = await _can_send_proactive(gardener)
    if not ok:
        return
    tg_id = str((gardener.get("identity") or {}).get("telegram_id") or "").strip()
    if not tg_id:
        return
    try:
        await bot.send_message(chat_id=int(tg_id), text=text, reply_markup=get_main_keyboard())
        await _mark_proactive_sent(gardener)
        await drain_queue()
    except Exception as e:
        logger.error(f"Proactive send error: {e}")

async def _job_morning() -> None:
    gardener = await read_gardener()
    if not gardener:
        return
    cs = gardener.get("companion_settings") or {}
    if not cs.get("morning_message_time"):
        return
    await _send_proactive("☀️ Доброе утро. Я рядом. Что сегодня важно для твоего сада?")

async def _job_evening() -> None:
    gardener = await read_gardener()
    if not gardener:
        return
    cs = gardener.get("companion_settings") or {}
    if not cs.get("evening_check_time"):
        return
    await _send_proactive("🌙 Тихий вечерний чек-ин: что сегодня получилось, и что хочется отпустить?")

async def _job_deadlines() -> None:
    gardener = await read_gardener()
    if not gardener:
        return
    cs = gardener.get("companion_settings") or {}
    if cs.get("task_reminders") is False:
        return
    tasks = await load_tasks()
    if not tasks:
        return
    today = _today()
    due = [t for t in tasks if t.get("status") != "completed" and t.get("deadline") == today and not t.get("_deadline_reminded")]
    if not due:
        return
    titles = ", ".join((t.get("title") or "").strip() for t in due[:3] if isinstance(t, dict)).strip()
    if not titles:
        titles = "есть задачи"
    await _send_proactive(f"⏰ Мягкое напоминание: сегодня по дедлайну {titles}. Хочешь, помогу выбрать самое важное?")
    changed = False
    for t in due:
        t["_deadline_reminded"] = True
        t["updated"] = _today()
        changed = True
    if changed:
        await save_tasks(tasks)
        await drain_queue()

def _start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    sched = AsyncIOScheduler()
    sched.add_job(lambda: asyncio.create_task(_job_morning()), CronTrigger(minute="*/30"))
    sched.add_job(lambda: asyncio.create_task(_job_evening()), CronTrigger(minute="*/30"))
    sched.add_job(lambda: asyncio.create_task(_job_deadlines()), CronTrigger(minute="*/15"))
    sched.start()
    _scheduler = sched
    logger.info("Proactive scheduler started")

# ========== BOT ASK API ==========
async def call_bot_ask(session_id: str, message: str, gardener_context: dict) -> Optional[str]:
    try:
        payload = {
            "session_id": session_id,
            "message": message,
            "gardener_context": gardener_context
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(SR_BACKEND_URL, json=payload, timeout=60) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response")
                logger.error(f"Bot ask error: {resp.status}")
                return None
    except Exception as e:
        logger.error(f"Bot ask exception: {e}")
        return None

# ========== FSM STATES ==========
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

# ========== KEYBOARDS ==========

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌿 Профиль"), KeyboardButton(text="🏆 Достижения")],
            [KeyboardButton(text="📋 Задачи")],
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

# ========== TASKS HELPERS ==========
async def load_tasks() -> list[dict]:
    tasks = await read_gardener_file("tasks.json")
    if isinstance(tasks, list):
        return tasks
    return []

async def save_tasks(tasks: list[dict]) -> bool:
    return await safe_write_gardener_file("tasks.json", tasks)

# ========== FSM: ONBOARDING ==========

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
        "🎯 Что тебя вдохновляет? Напиши 3-5 интересов через запятую.",
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
        "🎯 Какие у тебя цели на ближайшее время? Напиши 2-3.",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_goals))
async def onboarding_goals(message: Message, state: FSMContext):
    goals = [g.strip() for g in message.text.split(",") if g.strip()]
    await state.update_data(goals=goals)
    await state.set_state(GardenOnboardingStates.waiting_for_health_current)
    await message.answer(
        "💚 Оцени текущее состояние здоровья от 1 до 10.",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_health_current))
async def onboarding_health_current(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("💚 Введи число от 1 до 10.")
        return
    await state.update_data(health_current=val)
    await state.set_state(GardenOnboardingStates.waiting_for_health_target)
    await message.answer("💚 А к какому уровню стремишься? (1-10)")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_health_target))
async def onboarding_health_target(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("💚 Введи число от 1 до 10.")
        return
    await state.update_data(health_target=val)
    await state.set_state(GardenOnboardingStates.waiting_for_creativity_current)
    await message.answer("🎨 Оцени текущий уровень творчества от 1 до 10.")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_creativity_current))
async def onboarding_creativity_current(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("🎨 Введи число от 1 до 10.")
        return
    await state.update_data(creativity_current=val)
    await state.set_state(GardenOnboardingStates.waiting_for_creativity_target)
    await message.answer("🎨 А к какому уровню стремишься? (1-10)")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_creativity_target))
async def onboarding_creativity_target(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("🎨 Введи число от 1 до 10.")
        return
    await state.update_data(creativity_target=val)
    await state.set_state(GardenOnboardingStates.waiting_for_morning)
    await message.answer(
        "⏰ В какое время тебе комфортно получать утреннее приветствие?\n"
        "Напиши время (ЧЧ:ММ) или 'нет'."
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_morning))
async def onboarding_morning(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    morning = "" if text == "нет" else text
    await state.update_data(morning_time=morning)
    await state.set_state(GardenOnboardingStates.waiting_for_evening)
    await message.answer("🌙 А вечерний чек-ин? (ЧЧ:ММ или 'нет')")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_evening))
async def onboarding_evening(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    evening = "" if text == "нет" else text

    data = await state.get_data()
    user_id = str(message.from_user.id)

    gardener = {
        "identity": {
            "gardener_id": GARDENER_ID,
            "telegram_id": user_id,
            "name": data["name"],
            "resonance_level": 13,
            "created": datetime.now().strftime("%Y-%m-%d"),
            "updated": datetime.now().strftime("%Y-%m-%d")
        },
        "personal_info": {
            "interests": data["interests"],
            "goals": data["goals"],
            "life_areas": {
                "health": {"current": data["health_current"], "target": data["health_target"]},
                "creativity": {"current": data["creativity_current"], "target": data["creativity_target"]},
                "knowledge": {"current": 5, "target": 7},
                "relationships": {"current": 5, "target": 7}
            }
        },
        "companion_settings": {
            "morning_message_time": data["morning_time"],
            "evening_check_time": evening,
            "proactive_mode": True,
            "timezone": "Europe/Moscow"
        },
        "growth_history": []
    }

    groups = {
        "groups": [
            {"id": "group_001", "name": "🌿 Сад", "emoji": "🌿", "created": datetime.now().strftime("%Y-%m-%d")},
            {"id": "group_002", "name": "💼 Работа", "emoji": "💼", "created": datetime.now().strftime("%Y-%m-%d")},
            {"id": "group_003", "name": "🏡 Дом", "emoji": "🏡", "created": datetime.now().strftime("%Y-%m-%d")}
        ],
        "default_group": "group_001"
    }

    success = await safe_write_gardener_file("gardener.json", gardener)
    if not success:
        await message.answer("⚠️ Не смог сохранить профиль в GitHub. Я записал изменения локально и синхронизирую позже.")
        await state.clear()
        return
    await safe_write_gardener_file("tasks.json", [])
    await safe_write_gardener_file("achievements.json", [])
    await safe_write_gardener_file("groups.json", groups)
    await drain_queue()

    await state.set_state(GardenOnboardingStates.done)
    await message.answer(
        f"🌸 <b>{data['name']}, добро пожаловать в Сад!</b>\n\n"
        f"✨ Твой резонанс: 13%\n\n"
        f"🌱 Готов сопровождать тебя в этом путешествии!",
        reply_markup=get_main_keyboard()
    )

# ========== ACHIEVEMENTS FSM ==========
class AchievementStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_bonus = State()

@router.message(Command("achievements"))
@router.message(F.text == "🏆 Достижения")
async def cmd_achievements(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌸 Используй /start")
        return

    earned = await read_gardener_file("achievements.json") or []
    catalog = await read_repo_file(CATALOG_ACH_PATH) or {}
    cat_weights = (catalog.get("categories") or {}) if isinstance(catalog, dict) else {}
    cat_achs = (catalog.get("achievements") or []) if isinstance(catalog, dict) else []
    by_id = {a.get("id"): a for a in cat_achs if isinstance(a, dict) and a.get("id")}

    earned_ids: list[str] = []
    for e in earned:
        if isinstance(e, str):
            earned_ids.append(e)
        elif isinstance(e, dict) and e.get("id"):
            earned_ids.append(str(e["id"]))

    if not earned_ids:
        await message.answer("🏆 Пока достижений нет. Когда завершишь задачу с linked_achievement — я добавлю достижение автоматически.", reply_markup=get_main_keyboard())
        return

    cats: dict[str, list[dict]] = {"health": [], "creativity": [], "knowledge": [], "exploration": [], "relationships": []}
    for ach_id in earned_ids:
        a = by_id.get(ach_id)
        if not a:
            continue
        cat = a.get("category", "knowledge")
        if cat not in cats:
            cats[cat] = []
        cats[cat].append(a)

    text = "🏆 <b>Достижения</b>\n\n"
    for cat, items in cats.items():
        if not items:
            continue
        w = (cat_weights.get(cat) or {}).get("resonance_weight", 1.0)
        text += f"<b>{cat}</b> (вес {w})\n"
        for a in items[:10]:
            text += f"• {a.get('title','')} (+{a.get('resonance_bonus',0)}%)\n"
        text += "\n"
    await message.answer(text.strip(), reply_markup=get_main_keyboard())

@router.message(Command("addachievement"))
async def cmd_addachievement(message: Message, state: FSMContext):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌸 Используй /start")
        return
    await state.set_state(AchievementStates.waiting_for_category)
    await message.answer("🏆 <b>Новое достижение</b>\n\nВыбери категорию:", reply_markup=get_achievement_category_keyboard())

@router.callback_query(lambda c: c.data and c.data.startswith("ach_cat_"))
async def process_achievement_category(callback: CallbackQuery, state: FSMContext):
    cat_map = {
        "ach_cat_health": "health",
        "ach_cat_creativity": "creativity",
        "ach_cat_knowledge": "knowledge",
        "ach_cat_exploration": "exploration",
        "ach_cat_relationships": "relationships"
    }
    category = cat_map.get(callback.data, "knowledge")
    await state.update_data(category=category)
    await state.set_state(AchievementStates.waiting_for_title)

    await callback.message.edit_text(f"🏆 Категория: {category}\n\nВведи название достижения:")
    await callback.answer()

@router.callback_query(lambda c: c.data == "cancel_achievement")
async def cancel_achievement(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Добавление достижения отменено.")
    await callback.answer()

@router.message(StateFilter(AchievementStates.waiting_for_title))
async def achievement_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) < 3:
        await message.answer("🏆 Название должно быть не короче 3 символов.")
        return
    await state.update_data(title=title)
    await state.set_state(AchievementStates.waiting_for_description)
    await message.answer("📝 Опиши достижение:")

@router.message(StateFilter(AchievementStates.waiting_for_description))
async def achievement_description(message: Message, state: FSMContext):
    description = message.text.strip()
    await state.update_data(description=description)
    await state.set_state(AchievementStates.waiting_for_bonus)
    await message.answer("⭐ Сколько процентов резонанса добавляет это достижение? (1-10)\n\nПо умолчанию: 1")

@router.message(StateFilter(AchievementStates.waiting_for_bonus))
async def achievement_bonus(message: Message, state: FSMContext):
    try:
        bonus = int(message.text.strip())
        if bonus < 1 or bonus > 10:
            raise ValueError
    except:
        await message.answer("⭐ Введи число от 1 до 10.")
        return

    data = await state.get_data()

    new_achievement = {
        "id": f"ach_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "title": data["title"],
        "description": data["description"],
        "category": data["category"],
        "resonance_bonus": bonus,
        "date_earned": datetime.now().strftime("%Y-%m-%d"),
        "gardener_id": GARDENER_ID
    }

    achievements = await read_gardener_file("achievements.json") or []
    achievements.append(new_achievement)

    success = await safe_write_gardener_file("achievements.json", achievements)

    if success:
        gardener = await read_gardener()
        if gardener:
            current_res = gardener.get("identity", {}).get("resonance_level", 13)
            new_res = min(100, current_res + bonus)
            gardener["identity"]["resonance_level"] = new_res
            gardener["identity"]["updated"] = datetime.now().strftime("%Y-%m-%d")
            if "growth_history" not in gardener:
                gardener["growth_history"] = []
            gardener["growth_history"].append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "resonance": new_res,
                "change": bonus,
                "achievement": data["title"]
            })
            await safe_write_gardener_file("gardener.json", gardener)

        await message.answer(
            f"🏆 <b>Достижение добавлено!</b>\n\n"
            f"{data['title']} (+{bonus}% резонанса)\n"
            f"{data['description']}\n\n"
            f"✨ Резонанс обновлён!",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer("⚠️ Ошибка сохранения. Попробуй позже.")

    await state.clear()

# ========== COMMANDS ==========
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)

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
        if bound_id != user_id:
            if not password or password != ALLOWED_PASSWORD:
                await message.answer("🔒 Доступ защищён паролем.\nИспользуй: /start <пароль>")
                return
            gardener.setdefault("identity", {})
            gardener["identity"]["telegram_id"] = user_id
            gardener["identity"]["updated"] = _today()
            await safe_write_gardener_file("gardener.json", gardener)
            await drain_queue()

    await state.set_state(GardenOnboardingStates.waiting_for_name)
    await message.answer(
        "🌸 <b>Добро пожаловать в Сад!</b>\n\n"
        "Я — твой Gentle Companion. Давай познакомимся.\n\n"
        "🌱 Как тебя зовут?",
        reply_markup=get_cancel_keyboard()
    )

@router.message(Command("profile"))
@router.message(F.text == "🌿 Профиль")
async def cmd_profile(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌸 Используй /start")
        return

    gardener = await read_gardener()
    if not gardener:
        await message.answer("🌸 Профиль не найден")
        return

    name = gardener.get("identity", {}).get("name", "Садовник")
    resonance = gardener.get("identity", {}).get("resonance_level", 13)
    earned = await read_gardener_file("achievements.json") or []
    catalog = await read_repo_file(CATALOG_ACH_PATH) or {}
    cat_achs = (catalog.get("achievements") or []) if isinstance(catalog, dict) else []
    by_id = {a.get("id"): a for a in cat_achs if isinstance(a, dict) and a.get("id")}
    earned_ids: list[str] = []
    for e in earned:
        if isinstance(e, str):
            earned_ids.append(e)
        elif isinstance(e, dict) and e.get("id"):
            earned_ids.append(str(e["id"]))
    earned_full = [by_id.get(i) for i in earned_ids if by_id.get(i)]
    top_achievements = sorted(earned_full, key=lambda x: x.get("resonance_bonus", 0), reverse=True)[:3]

    tasks = await read_gardener_file("tasks.json") or []
    active_tasks = [t for t in tasks if t.get("status") != "completed"]

    text = f"🌿 <b>{name}</b>\n✨ Резонанс: {resonance}%\n\n"

    if top_achievements:
        text += "<b>🏆 Топ достижений:</b>\n"
        for ach in top_achievements:
            text += f"  {ach.get('title', '')} (+{ach.get('resonance_bonus', 0)})\n"

    text += f"\n📋 <b>Активных задач:</b> {len(active_tasks)}"

    await message.answer(text, reply_markup=get_main_keyboard())

@router.message(Command("resonance"))
async def cmd_resonance(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌸 Используй /start")
        return

    earned = await read_gardener_file("achievements.json") or []
    catalog = await read_repo_file(CATALOG_ACH_PATH) or {}
    cat_weights = (catalog.get("categories") or {}) if isinstance(catalog, dict) else {}
    cat_achs = (catalog.get("achievements") or []) if isinstance(catalog, dict) else []
    by_id = {a.get("id"): a for a in cat_achs if isinstance(a, dict) and a.get("id")}

    base = 10
    total = float(base)
    earned_ids: list[str] = []
    for e in earned:
        if isinstance(e, str):
            earned_ids.append(e)
        elif isinstance(e, dict) and e.get("id"):
            earned_ids.append(str(e["id"]))

    for ach_id in earned_ids:
        a = by_id.get(ach_id)
        if not a:
            continue
        cat = a.get("category", "knowledge")
        bonus = float(a.get("resonance_bonus", 0) or 0)
        w = float((cat_weights.get(cat) or {}).get("resonance_weight", 1.0) or 1.0)
        total += bonus * w

    total_int = max(10, min(100, int(total)))

    gardener = await read_gardener()
    history = gardener.get("growth_history", []) if gardener else []

    text = f"✨ <b>Резонанс: {total_int}%</b>"
    if history:
        text += "\n\nИстория:\n"
        for h in history[-5:]:
            text += f"• {h.get('date', '?')}: {h.get('resonance', '?')}%\n"

    await message.answer(text.strip(), reply_markup=get_main_keyboard())

@router.message(F.text == "💬 В инженерный чат")
async def btn_engineer_chat(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    session_id = f"tg_{message.from_user.id}"
    gardener = await read_gardener() or {}
    response = await call_bot_ask(session_id, "Привет, я из бота", gardener)
    if response:
        await message.answer(response, reply_markup=get_main_keyboard())
    else:
        await message.answer("💬 Инженерный чат временно недоступен. Попробуй позже.", reply_markup=get_main_keyboard())

@router.message(F.text == "📋 Задачи")
async def btn_tasks(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    await message.answer("📋 Раздел задач в разработке. Скоро здесь будет управление задачами.", reply_markup=get_main_keyboard())

@router.message(F.text == "❌ Отмена")
async def btn_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=get_main_keyboard())

# ========== WEBHOOK ==========
async def on_startup(app: web.Application):
    await bot.set_webhook(WEBHOOK_URL, secret_token=WEBHOOK_SECRET)
    logger.info(f"Webhook set: {WEBHOOK_URL}")
    _start_scheduler()

async def on_shutdown(app: web.Application):
    await bot.delete_webhook()
    await bot.session.close()
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
