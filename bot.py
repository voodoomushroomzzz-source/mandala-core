# Test deploy trigger
# Force deploy 
#!/usr/bin/env python3
"""
Mandala Garden Bot  Gentle Companion v5.2.0
Integrated with /bot/ask endpoint. Password protected. Hardcoded to gardener_001.
Added achievements commands (D4).
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
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

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

# Soft-fail queue is local to the bot process (GitHub may be unavailable)
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
    # Use explicit branch ref to avoid default-branch ambiguity/caches
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}?ref=main"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/5.2.0"
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
    """List directory via GitHub Contents API (returns JSON list)."""
    if not GITHUB_TOKEN:
        return False, None
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{dir_path}?ref=main"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/5.2.0"
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
    """Write arbitrary JSON to repo path via Contents API."""
    if not GITHUB_TOKEN:
        return False
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/5.2.0"
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
            "message": f" bot: update {path}",
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
    """Best-effort: replay queued writes FIFO."""
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
            # Stop on first failure to preserve ordering.
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
        # supports "...Z"
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None

def _is_night(local_dt: datetime) -> bool:
    # Ахимса: не писать ночью
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

    # Silence policy by inactivity
    last_interaction_iso = identity.get("last_user_interaction_at") or ""
    last_dt = _parse_iso_dt(last_interaction_iso)
    if last_dt:
        # compare in UTC-ish naive safe way
        delta = datetime.utcnow() - last_dt.replace(tzinfo=None)
        days = delta.days
        if days >= 31:
            return False, "silence_31_plus"
        if 8 <= days <= 30:
            # allow at most 1 message per week
            meta = cs.get("proactive_meta") or {}
            last_week_sent = meta.get("last_weekly_sent_iso") or ""
            last_week_dt = _parse_iso_dt(last_week_sent)
            if last_week_dt and (datetime.utcnow() - last_week_dt.replace(tzinfo=None)).days < 7:
                return False, "weekly_limit"

    # 6-hour cooldown
    meta = cs.get("proactive_meta") or {}
    last_sent_iso = meta.get("last_sent_iso") or ""
    last_sent = _parse_iso_dt(last_sent_iso)
    if last_sent and (datetime.utcnow() - last_sent.replace(tzinfo=None)).total_seconds() < 6 * 3600:
        return False, "cooldown_6h"

    # 1 per day
    if meta.get("last_sent_date") == _today():
        return False, "daily_limit"

    return True, "ok"

async def _mark_proactive_sent(gardener: dict) -> None:
    cs = gardener.setdefault("companion_settings", {})
    meta = cs.setdefault("proactive_meta", {})
    meta["last_sent_iso"] = _utc_iso()
    meta["last_sent_date"] = _today()
    # if in weekly-only window, mark weekly
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
    # if configured with time but empty -> skip
    if not cs.get("morning_message_time"):
        return
    await _send_proactive("Доброе утро. Я рядом. Что сегодня важно для твоего сада?")

async def _job_evening() -> None:
    gardener = await read_gardener()
    if not gardener:
        return
    cs = gardener.get("companion_settings") or {}
    if not cs.get("evening_check_time"):
        return
    await _send_proactive("Тихий вечерний чек-ин: что сегодня получилось, и что хочется отпустить?")

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
    await _send_proactive(f"Мягкое напоминание: сегодня по дедлайну {titles}. Хочешь, помогу выбрать самое важное?")
    # mark reminded (best-effort)
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
    # Run jobs in broad windows; internal _can_send_proactive enforces Ahimsa/time
    sched.add_job(lambda: asyncio.create_task(_job_morning()), CronTrigger(minute="*/30"))
    sched.add_job(lambda: asyncio.create_task(_job_evening()), CronTrigger(minute="*/30"))
    sched.add_job(lambda: asyncio.create_task(_job_deadlines()), CronTrigger(minute="*/15"))
    sched.start()
    _scheduler = sched
    logger.info("Proactive scheduler started")

# ========== BOT ASK API ==========
async def call_bot_ask(session_id: str, message: str, gardener_context: dict) -> Optional[str]:
    """Call /bot/ask endpoint on engineer-chat."""
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
        keyboard=[[KeyboardButton(text=" РћС‚РјРµРЅР°")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=" РџСЂРѕС„РёР»СЊ"), KeyboardButton(text=" Р”РѕСЃС‚РёР¶РµРЅРёСЏ")],
            [KeyboardButton(text="🌰 Семена")],
            [KeyboardButton(text="🛠 В инженерный чат")]
        ],
        resize_keyboard=True
    )

def get_achievement_category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=" Р—РґРѕСЂРѕРІСЊРµ", callback_data="ach_cat_health")],
        [InlineKeyboardButton(text=" РўРІРѕСЂС‡РµСЃС‚РІРѕ", callback_data="ach_cat_creativity")],
        [InlineKeyboardButton(text=" Р—РЅР°РЅРёСЏ", callback_data="ach_cat_knowledge")],
        [InlineKeyboardButton(text=" РСЃСЃР»РµРґРѕРІР°РЅРёРµ", callback_data="ach_cat_exploration")],
        [InlineKeyboardButton(text=" РћС‚РЅРѕС€РµРЅРёСЏ", callback_data="ach_cat_relationships")],
        [InlineKeyboardButton(text=" РћС‚РјРµРЅР°", callback_data="cancel_achievement")]
    ])

# ========== FSM: ONBOARDING ==========

@router.message(StateFilter(GardenOnboardingStates.waiting_for_name))
async def onboarding_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("РРјСЏ РґРѕР»Р¶РЅРѕ Р±С‹С‚СЊ РЅРµ РєРѕСЂРѕС‡Рµ 2 СЃРёРјРІРѕР»РѕРІ.")
        return
    await state.update_data(name=name)
    await state.set_state(GardenOnboardingStates.waiting_for_interests)
    await message.answer(
        f"РџСЂРёСЏС‚РЅРѕ РїРѕР·РЅР°РєРѕРјРёС‚СЊСЃСЏ, {name}!\n\n"
        "Р§С‚Рѕ РїСЂРёРЅРѕСЃРёС‚ С‚РµР±Рµ СЂР°РґРѕСЃС‚СЊ? РќР°РїРёС€Рё 3-5 РёРЅС‚РµСЂРµСЃРѕРІ С‡РµСЂРµР· Р·Р°РїСЏС‚СѓСЋ.",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_interests))
async def onboarding_interests(message: Message, state: FSMContext):
    interests = [i.strip() for i in message.text.split(",") if i.strip()]
    if len(interests) < 1:
        await message.answer("РќР°РїРёС€Рё С…РѕС‚СЏ Р±С‹ РѕРґРёРЅ РёРЅС‚РµСЂРµСЃ.")
        return
    await state.update_data(interests=interests)
    await state.set_state(GardenOnboardingStates.waiting_for_goals)
    await message.answer(
        "РљР°РєРёРµ СЃРµРјРµРЅР° С…РѕС‡РµС€СЊ РїРѕСЃР°РґРёС‚СЊ РІ СЌС‚РѕРј СЃРµР·РѕРЅРµ? РќР°РїРёС€Рё 2-3 С†РµР»Рё.",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_goals))
async def onboarding_goals(message: Message, state: FSMContext):
    goals = [g.strip() for g in message.text.split(",") if g.strip()]
    await state.update_data(goals=goals)
    await state.set_state(GardenOnboardingStates.waiting_for_health_current)
    await message.answer(
        "РћС†РµРЅРё СЃРІРѕС‘ Р·РґРѕСЂРѕРІСЊРµ РѕС‚ 1 РґРѕ 10.\nР“РґРµ С‚С‹ СЃРµР№С‡Р°СЃ?",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_health_current))
async def onboarding_health_current(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("Р’РІРµРґРё С‡РёСЃР»Рѕ РѕС‚ 1 РґРѕ 10.")
        return
    await state.update_data(health_current=val)
    await state.set_state(GardenOnboardingStates.waiting_for_health_target)
    await message.answer("РљСѓРґР° С…РѕС‡РµС€СЊ РїСЂРёР№С‚Рё? (1-10)")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_health_target))
async def onboarding_health_target(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("Р’РІРµРґРё С‡РёСЃР»Рѕ РѕС‚ 1 РґРѕ 10.")
        return
    await state.update_data(health_target=val)
    await state.set_state(GardenOnboardingStates.waiting_for_creativity_current)
    await message.answer(" РўРІРѕСЂС‡РµСЃС‚РІРѕ: С‚РµРєСѓС‰РёР№ СѓСЂРѕРІРµРЅСЊ? (1-10)")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_creativity_current))
async def onboarding_creativity_current(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("Р’РІРµРґРё С‡РёСЃР»Рѕ РѕС‚ 1 РґРѕ 10.")
        return
    await state.update_data(creativity_current=val)
    await state.set_state(GardenOnboardingStates.waiting_for_creativity_target)
    await message.answer(" РўРІРѕСЂС‡РµСЃС‚РІРѕ  С†РµР»СЊ? (1-10)")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_creativity_target))
async def onboarding_creativity_target(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("Р’РІРµРґРё С‡РёСЃР»Рѕ РѕС‚ 1 РґРѕ 10.")
        return
    await state.update_data(creativity_target=val)
    await state.set_state(GardenOnboardingStates.waiting_for_morning)
    await message.answer(
        "РљРѕРіРґР° С‚РµР±Рµ СѓРґРѕР±РЅРѕ РїРѕР»СѓС‡Р°С‚СЊ СѓС‚СЂРµРЅРЅРµРµ РїСЂРёРІРµС‚СЃС‚РІРёРµ?\n"
        "РќР°РїРёС€Рё РІСЂРµРјСЏ (Р§Р§:РњРњ) РёР»Рё 'РЅРµС‚'."
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_morning))
async def onboarding_morning(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    morning = "" if text == "РЅРµС‚" else text
    await state.update_data(morning_time=morning)
    await state.set_state(GardenOnboardingStates.waiting_for_evening)
    await message.answer("Рђ РІРµС‡РµСЂРЅРµРµ РІСЂРµРјСЏ? (Р§Р§:РњРњ РёР»Рё 'РЅРµС‚')")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_evening))
async def onboarding_evening(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    evening = "" if text == "РЅРµС‚" else text

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
            {"id": "group_001", "name": "Р”РѕРј", "emoji": "", "created": datetime.now().strftime("%Y-%m-%d")},
            {"id": "group_002", "name": "Р Р°Р±РѕС‚Р°", "emoji": "", "created": datetime.now().strftime("%Y-%m-%d")},
            {"id": "group_003", "name": "Р›РёС‡РЅРѕРµ", "emoji": "", "created": datetime.now().strftime("%Y-%m-%d")}
        ],
        "default_group": "group_001"
    }

    # Сохранение в GitHub (soft-fail -> local queue)
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
        f" <b>{data['name']}, С‚РІРѕР№ РЎР°Рґ СЃРѕР·РґР°РЅ!</b>\n\n"
        f"РўРІРѕР№ СЂРµР·РѕРЅР°РЅСЃ: 13%\n\n"
        f"Р”РѕР±СЂРѕ РїРѕР¶Р°Р»РѕРІР°С‚СЊ РІ СЃРёРјР±РёРѕР·!",
        reply_markup=get_main_keyboard()
    )

# ========== ACHIEVEMENTS FSM ==========
class AchievementStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_bonus = State()

@router.message(Command("achievements"))
@router.message(F.text == " Р”РѕСЃС‚РёР¶РµРЅРёСЏ")
async def cmd_achievements(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer(" РЎРЅР°С‡Р°Р»Р° /start")
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
        await message.answer("🏆 Пока достижений нет. Когда ты завершишь задачу с linked_achievement — я добавлю достижение автоматически.", reply_markup=get_main_keyboard())
        return

    # Group by category from catalog
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
        await message.answer(" РЎРЅР°С‡Р°Р»Р° /start")
        return
    await state.set_state(AchievementStates.waiting_for_category)
    await message.answer(" <b>РЎРѕР·РґР°РЅРёРµ РґРѕСЃС‚РёР¶РµРЅРёСЏ</b>\n\nР’С‹Р±РµСЂРё РєР°С‚РµРіРѕСЂРёСЋ:", reply_markup=get_achievement_category_keyboard())

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

    await callback.message.edit_text(f" РљР°С‚РµРіРѕСЂРёСЏ: {category}\n\nР’РІРµРґРё РЅР°Р·РІР°РЅРёРµ РґРѕСЃС‚РёР¶РµРЅРёСЏ:")
    await callback.answer()

@router.callback_query(lambda c: c.data == "cancel_achievement")
async def cancel_achievement(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(" РЎРѕР·РґР°РЅРёРµ РґРѕСЃС‚РёР¶РµРЅРёСЏ РѕС‚РјРµРЅРµРЅРѕ.")
    await callback.answer()

@router.message(StateFilter(AchievementStates.waiting_for_title))
async def achievement_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) < 3:
        await message.answer("РќР°Р·РІР°РЅРёРµ РґРѕР»Р¶РЅРѕ Р±С‹С‚СЊ РЅРµ РєРѕСЂРѕС‡Рµ 3 СЃРёРјРІРѕР»РѕРІ.")
        return
    await state.update_data(title=title)
    await state.set_state(AchievementStates.waiting_for_description)
    await message.answer(" РќР°РїРёС€Рё РѕРїРёСЃР°РЅРёРµ РґРѕСЃС‚РёР¶РµРЅРёСЏ:")

@router.message(StateFilter(AchievementStates.waiting_for_description))
async def achievement_description(message: Message, state: FSMContext):
    description = message.text.strip()
    await state.update_data(description=description)
    await state.set_state(AchievementStates.waiting_for_bonus)
    await message.answer(" РЎРєРѕР»СЊРєРѕ РїСЂРѕС†РµРЅС‚РѕРІ СЂРµР·РѕРЅР°РЅСЃР° РґР°С‘С‚ СЌС‚Рѕ РґРѕСЃС‚РёР¶РµРЅРёРµ? (1-10)\n\nРџРѕ СѓРјРѕР»С‡Р°РЅРёСЋ: 1")

@router.message(StateFilter(AchievementStates.waiting_for_bonus))
async def achievement_bonus(message: Message, state: FSMContext):
    try:
        bonus = int(message.text.strip())
        if bonus < 1 or bonus > 10:
            raise ValueError
    except:
        await message.answer("Р’РІРµРґРё С‡РёСЃР»Рѕ РѕС‚ 1 РґРѕ 10.")
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
            f" <b>Р”РѕСЃС‚РёР¶РµРЅРёРµ РґРѕР±Р°РІР»РµРЅРѕ!</b>\n\n"
            f"{data['title']} (+{bonus}% СЂРµР·РѕРЅР°РЅСЃР°)\n"
            f"{data['description']}\n\n"
            f"РўРІРѕР№ СЂРµР·РѕРЅР°РЅСЃ РІС‹СЂРѕСЃ!",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(" РћС€РёР±РєР° СЃРѕС…СЂР°РЅРµРЅРёСЏ. РџРѕРїСЂРѕР±СѓР№ РїРѕР·Р¶Рµ.")

    await state.clear()

# ========== COMMANDS ==========
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)

    gardener = await read_gardener()

    # Password protection:
    # - If bot is already bound to a telegram_id, only that id is allowed.
    # - If not bound (empty telegram_id), require /start <password> to bind.
    # - If different id tries to access, require /start <password> to re-bind.
    password = None
    try:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) == 2:
            password = parts[1].strip()
    except Exception:
        password = None

    if gardener and str(gardener.get("identity", {}).get("telegram_id", "")) == user_id:
        name = gardener.get("identity", {}).get("name", "РЎР°РґРѕРІРЅРёРє")
        await message.answer(f" РЎ РІРѕР·РІСЂР°С‰РµРЅРёРµРј, {name}!", reply_markup=get_main_keyboard())
        return

    if gardener:
        bound_id = str(gardener.get("identity", {}).get("telegram_id", "") or "").strip()
        if bound_id != user_id:
            if not password or password != ALLOWED_PASSWORD:
                await message.answer("🔒 Доступ защищён паролем.\nИспользуй: /start <пароль>")
                return
            # Re-bind to this telegram id
            gardener.setdefault("identity", {})
            gardener["identity"]["telegram_id"] = user_id
            gardener["identity"]["updated"] = _today()
            await safe_write_gardener_file("gardener.json", gardener)
            await drain_queue()

    await state.set_state(GardenOnboardingStates.waiting_for_name)
    await message.answer(
        " <b>Р”РѕР±СЂРѕ РїРѕР¶Р°Р»РѕРІР°С‚СЊ РІ РЎР°Рґ РњР°РЅРґР°Р»С‹!</b>\n\n"
        "РЇ  С‚РІРѕР№ РќРµР¶РЅС‹Р№ РЎРїСѓС‚РЅРёРє. Р”Р°РІР°Р№ РїРѕР·РЅР°РєРѕРјРёРјСЃСЏ.\n\n"
        "РљР°Рє РјРЅРµ С‚РµР±СЏ РЅР°Р·С‹РІР°С‚СЊ?",
        reply_markup=get_cancel_keyboard()
    )

@router.message(Command("profile"))
async def cmd_profile(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer(" РЎРЅР°С‡Р°Р»Р° /start [РїР°СЂРѕР»СЊ]")
        return

    gardener = await read_gardener()
    if not gardener:
        await message.answer(" РџСЂРѕС„РёР»СЊ РЅРµ РЅР°Р№РґРµРЅ")
        return

    name = gardener.get("identity", {}).get("name", "РЎР°РґРѕРІРЅРёРє")
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

    text = f" <b>{name}</b>\n Р РµР·РѕРЅР°РЅСЃ: {resonance}%\n\n"

    if top_achievements:
        text += "<b> РўРѕРї РґРѕСЃС‚РёР¶РµРЅРёР№:</b>\n"
        for ach in top_achievements:
            text += f"   {ach.get('title', '')} (+{ach.get('resonance_bonus', 0)})\n"

    text += f"\n <b>РђРєС‚РёРІРЅС‹С… Р·Р°РґР°С‡:</b> {len(active_tasks)}"

    await message.answer(text)

@router.message(Command("resonance"))
async def cmd_resonance(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer(" РЎРЅР°С‡Р°Р»Р° /start")
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

    text = f"📊 <b>Резонанс: {total_int}%</b>"
    if history:
        text += "\n\nИстория:\n"
        for h in history[-5:]:
            text += f"• {h.get('date', '?')}: {h.get('resonance', '?')}%\n"

    await message.answer(text.strip())

@router.message(F.text == "🛠 В инженерный чат")
async def btn_engineer_chat(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("Сначала /start", reply_markup=get_main_keyboard())
        return
    session_id = f"tg_{message.from_user.id}"
    await message.answer(
        f"Открой engineer-chat в браузере: {ENGINEER_CHAT_URL}\n"
        f"Твой session_id уже общий: {session_id}",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "🌰 Семена")
async def btn_seeds(message: Message):
    await cmd_seeds(message)

@router.message(F.text == " РџСЂРѕС„РёР»СЊ")
async def btn_profile(message: Message):
    await cmd_profile(message)

# ========== PERSONAL TASKS (D7) ==========

LIFE_AREAS = {"health", "creativity", "knowledge", "exploration", "relationships", "other"}

class AddTaskStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_life_area = State()
    waiting_for_group = State()
    waiting_for_deadline = State()
    waiting_for_notes = State()

def _make_task_id() -> str:
    return "task_" + datetime.now().strftime("%Y%m%d_%H%M%S")

async def load_tasks() -> list[dict]:
    tasks = await read_gardener_file("tasks.json")
    if isinstance(tasks, list):
        return [t for t in tasks if isinstance(t, dict)]
    return []

async def save_tasks(tasks: list[dict]) -> bool:
    return await safe_write_gardener_file("tasks.json", tasks)

async def load_groups() -> dict:
    groups = await read_gardener_file("groups.json")
    return groups if isinstance(groups, dict) else {"groups": [], "default_group": None}

def _compute_priority(life_area: str, tasks: list[dict], gardener: Optional[dict]) -> int:
    active = [t for t in tasks if t.get("status") in ("todo", "in_progress")]
    counts: dict[str, int] = {k: 0 for k in LIFE_AREAS}
    for t in active:
        la = (t.get("life_area") or "other")
        if la in counts:
            counts[la] += 1
    min_count = min(counts.values()) if counts else 0
    avg = (sum(counts.values()) / max(1, len(counts))) if counts else 0
    gap = 1
    if counts.get(life_area, 0) <= min_count:
        gap = 5
    elif counts.get(life_area, 0) < avg:
        gap = 4
    else:
        gap = 2
    match = 2
    if gardener:
        la_info = (gardener.get("personal_info", {}).get("life_areas", {}) or {}).get(life_area)
        if isinstance(la_info, dict):
            try:
                cur = int(la_info.get("current", 0) or 0)
                tgt = int(la_info.get("target", 0) or 0)
                if cur < tgt:
                    match = 3
            except Exception:
                pass
    pr = match * gap
    return max(1, min(10, pr))

@router.message(Command("tasks"))
async def cmd_tasks(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("Сначала /start")
        return
    tasks = await load_tasks()
    active = [t for t in tasks if t.get("status") != "completed"]
    if not active:
        await message.answer("📋 Активных задач пока нет. Добавь: /addtask", reply_markup=get_main_keyboard())
        return
    text = "📋 <b>Твои задачи</b>\n\n"
    for t in active[:15]:
        text += f"• <code>{t.get('task_id','')}</code> — {t.get('title','')}\n"
    if len(active) > 15:
        text += f"\n…и ещё {len(active) - 15}"
    await message.answer(text, reply_markup=get_main_keyboard())

@router.message(Command("archive"))
async def cmd_archive(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("Сначала /start")
        return
    tasks = await load_tasks()
    done = [t for t in tasks if t.get("status") == "completed"]
    if not done:
        await message.answer("🗂 Архив пока пуст.", reply_markup=get_main_keyboard())
        return
    text = "🗂 <b>Архив</b>\n\n"
    for t in done[-15:]:
        text += f"• <code>{t.get('task_id','')}</code> — {t.get('title','')}\n"
    await message.answer(text, reply_markup=get_main_keyboard())

@router.message(Command("addtask"))
async def cmd_addtask(message: Message, state: FSMContext):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("Сначала /start")
        return
    await state.clear()
    await state.set_state(AddTaskStates.waiting_for_title)
    await message.answer("✍️ Название задачи?", reply_markup=get_cancel_keyboard())

@router.message(StateFilter(AddTaskStates.waiting_for_title))
async def addtask_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if len(title) < 2:
        await message.answer("Слишком коротко. Напиши название ещё раз.")
        return
    await state.update_data(title=title)
    await state.set_state(AddTaskStates.waiting_for_life_area)
    await message.answer("🌿 Сфера жизни? (health/creativity/knowledge/exploration/relationships/other)")

@router.message(StateFilter(AddTaskStates.waiting_for_life_area))
async def addtask_life_area(message: Message, state: FSMContext):
    la = (message.text or "").strip().lower()
    if la not in LIFE_AREAS:
        await message.answer("Не понял сферу. Напиши одно из: health, creativity, knowledge, exploration, relationships, other")
        return
    await state.update_data(life_area=la)
    await state.set_state(AddTaskStates.waiting_for_group)
    groups = await load_groups()
    lines = ["🗂 Группа? Напиши id группы (пример: group_001).", ""]
    for g in (groups.get("groups") or []):
        if isinstance(g, dict):
            lines.append(f"• <code>{g.get('id','')}</code> — {g.get('name','')}")
    await message.answer("\n".join(lines))

@router.message(StateFilter(AddTaskStates.waiting_for_group))
async def addtask_group(message: Message, state: FSMContext):
    group_id = (message.text or "").strip()
    groups = await load_groups()
    valid = {g.get("id") for g in (groups.get("groups") or []) if isinstance(g, dict)}
    if group_id not in valid:
        await message.answer("Не нашёл такую группу. Напиши существующий id из списка.")
        return
    await state.update_data(group_id=group_id)
    await state.set_state(AddTaskStates.waiting_for_deadline)
    await message.answer("⏳ Дедлайн? (YYYY-MM-DD или '-' если нет)")

@router.message(StateFilter(AddTaskStates.waiting_for_deadline))
async def addtask_deadline(message: Message, state: FSMContext):
    dl = (message.text or "").strip()
    deadline = None
    if dl and dl != "-":
        try:
            datetime.strptime(dl, "%Y-%m-%d")
            deadline = dl
        except Exception:
            await message.answer("Формат дедлайна: YYYY-MM-DD, либо '-' если нет.")
            return
    await state.update_data(deadline=deadline)
    await state.set_state(AddTaskStates.waiting_for_notes)
    await message.answer("📝 Заметки? (можно '-' если нет)")

@router.message(StateFilter(AddTaskStates.waiting_for_notes))
async def addtask_notes(message: Message, state: FSMContext):
    notes = (message.text or "").strip()
    if notes == "-":
        notes = ""
    data = await state.get_data()
    gardener = await read_gardener()
    tasks = await load_tasks()
    task_id = _make_task_id()
    priority = _compute_priority(data["life_area"], tasks, gardener)
    now = _today()
    new_task = {
        "task_id": task_id,
        "title": data["title"],
        "status": "todo",
        "priority": priority,
        "life_area": data["life_area"],
        "group_id": data["group_id"],
        "source": "manual",
        "tags": [],
        "deadline": data.get("deadline"),
        "estimated_hours": None,
        "linked_achievement": None,
        "created": now,
        "updated": now,
        "completed": None,
        "notes": notes,
    }
    tasks.append(new_task)
    ok = await save_tasks(tasks)
    await drain_queue()
    if ok:
        await message.answer(f"✅ Задача создана: <code>{task_id}</code>\n{data['title']}", reply_markup=get_main_keyboard())
    else:
        await message.answer("⚠️ Не смог записать задачу в GitHub. Я поставил её в очередь и синхронизирую позже.", reply_markup=get_main_keyboard())
    await state.clear()

@router.message(Command("done"))
async def cmd_done(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("Сначала /start")
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Используй: /done task_...")
        return
    task_id = parts[1].strip()
    tasks = await load_tasks()
    found = None
    for t in tasks:
        if t.get("task_id") == task_id:
            found = t
            break
    if not found:
        await message.answer("Не нашёл такую задачу.")
        return
    if found.get("status") == "completed":
        await message.answer("Эта задача уже завершена.", reply_markup=get_main_keyboard())
        return
    found["status"] = "completed"
    found["completed"] = _today()
    found["updated"] = _today()
    ok = await save_tasks(tasks)

    linked = found.get("linked_achievement")
    if linked:
        earned = await read_gardener_file("achievements.json") or []
        earned_ids = set()
        for e in earned:
            if isinstance(e, str):
                earned_ids.add(e)
            elif isinstance(e, dict) and e.get("id"):
                earned_ids.add(str(e["id"]))
        if str(linked) not in earned_ids:
            earned.append({"id": str(linked), "date_earned": _today(), "source": "linked_task", "task_id": task_id})
            await safe_write_gardener_file("achievements.json", earned)

    await drain_queue()
    if ok:
        await message.answer(f"✅ Готово: <code>{task_id}</code>", reply_markup=get_main_keyboard())
    else:
        await message.answer("⚠️ Не смог обновить задачу в GitHub. Я поставил изменение в очередь.", reply_markup=get_main_keyboard())

@router.message(Command("groups"))
async def cmd_groups(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("Сначала /start")
        return
    groups = await load_groups()
    items = groups.get("groups") or []
    if not items:
        await message.answer("Групп нет. Создай: /newgroup <имя>", reply_markup=get_main_keyboard())
        return
    text = "🗂 <b>Группы</b>\n\n"
    for g in items:
        if isinstance(g, dict):
            text += f"• <code>{g.get('id','')}</code> — {g.get('name','')}\n"
    await message.answer(text, reply_markup=get_main_keyboard())

@router.message(Command("newgroup"))
async def cmd_newgroup(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("Сначала /start")
        return
    name = (message.text or "").replace("/newgroup", "", 1).strip()
    if len(name) < 2:
        await message.answer("Используй: /newgroup Название")
        return
    groups = await load_groups()
    items = [g for g in (groups.get("groups") or []) if isinstance(g, dict)]
    next_n = 1
    for g in items:
        gid = g.get("id", "")
        if isinstance(gid, str) and gid.startswith("group_"):
            try:
                next_n = max(next_n, int(gid.split("_")[1]) + 1)
            except Exception:
                pass
    new_id = f"group_{next_n:03d}"
    items.append({"id": new_id, "name": name, "emoji": "", "created": _today()})
    groups["groups"] = items
    if not groups.get("default_group"):
        groups["default_group"] = new_id
    ok = await safe_write_gardener_file("groups.json", groups)
    await drain_queue()
    if ok:
        await message.answer(f"✅ Группа создана: <code>{new_id}</code> — {name}", reply_markup=get_main_keyboard())
    else:
        await message.answer("⚠️ Не смог сохранить группу в GitHub. Я поставил в очередь.", reply_markup=get_main_keyboard())

# ========== MANDALA TASKS (D8) ==========

MANDALA_ACTIVE_DIR = "honeycombs/tasks/active"

async def _load_mandala_tasks() -> list[dict]:
    ok, items = await list_github_dir(MANDALA_ACTIVE_DIR)
    if not ok or not items:
        return []
    tasks: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("type") != "file":
            continue
        if not str(it.get("name", "")).endswith(".json"):
            continue
        path = it.get("path")
        if not path:
            continue
        data = await read_repo_file(path)
        if isinstance(data, dict):
            data["_path"] = path
            tasks.append(data)
    return tasks

@router.message(Command("tasks_mandala"))
async def cmd_tasks_mandala(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("Сначала /start")
        return
    parts = (message.text or "").split()
    tasks = await _load_mandala_tasks()
    if not tasks:
        await message.answer("🌀 Активных мандала-задач не найдено.", reply_markup=get_main_keyboard())
        return

    if len(parts) == 1:
        text = "🌀 <b>Мандала-задачи (active)</b>\n\n"
        for t in tasks[:20]:
            text += f"• <code>{t.get('task_id','')}</code> — {t.get('name','') or t.get('title','')}\n"
        await message.answer(text.strip(), reply_markup=get_main_keyboard())
        return

    task_id = parts[1].strip()
    t = next((x for x in tasks if str(x.get("task_id")) == task_id), None)
    if not t:
        await message.answer("Не нашёл такую мандала-задачу.")
        return

    if len(parts) >= 4 and parts[2] in ("status", "progress"):
        field = parts[2]
        val = parts[3]
        path = t.get("_path")
        if not path:
            await message.answer("Не могу определить путь файла задачи.")
            return
        if field == "status":
            raw = (val or "").strip().lower()
            status_map = {
                "todo": "todo",
                "planned": "todo",
                "pending": "todo",
                "in_progress": "in_progress",
                "doing": "in_progress",
                "active": "in_progress",
                "done": "done",
                "completed": "done",
                "complete": "done",
            }
            if raw not in status_map:
                await message.answer("status должен быть одним из: todo | in_progress | done")
                return
            t["status"] = status_map[raw]
        else:
            try:
                p = int(val)
                if p < 0 or p > 100:
                    raise ValueError
                t["progress"] = p
            except Exception:
                await message.answer("progress должен быть числом 0-100.")
                return
        t["updated"] = _today()
        ok = await safe_write_repo_json(path, {k: v for k, v in t.items() if k != "_path"})
        await drain_queue()
        if ok:
            await message.answer(f"✅ Обновлено: <code>{task_id}</code> {field}={val}", reply_markup=get_main_keyboard())
        else:
            await message.answer("⚠️ Не смог сохранить в GitHub. Я поставил изменение в очередь.", reply_markup=get_main_keyboard())
        return

    text = (
        f"🌀 <b>{t.get('name','')}</b>\n"
        f"<code>{t.get('task_id','')}</code>\n\n"
        f"status: <b>{t.get('status','')}</b>\n"
        f"priority: {t.get('priority','')}\n"
        f"deadline: {t.get('deadline','')}\n"
        f"progress: {t.get('progress','')}\n\n"
        f"{t.get('description','')}"
    )
    await message.answer(text.strip(), reply_markup=get_main_keyboard())

# ========== SEEDS (Mandala-related via bot) ==========

class AddSeedStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_notes = State()

async def load_seeds_registry() -> dict:
    data = await read_repo_file(SIMBIOSIS_SEEDS_PATH)
    if isinstance(data, dict) and isinstance(data.get("seeds"), list):
        return data
    registry = {
        "identity": {
            "module_id": "SIMBIOSIS-SEEDS-001",
            "name": "Simbiosis Seeds",
            "version": "v1.0.0",
            "created": _today(),
            "updated": _today(),
            "type": "seed_registry",
            "status": "active",
            "tags": ["seeds", "telegram_bot", "garden", "mandala"]
        },
        "seeds": []
    }
    await safe_write_repo_json(SIMBIOSIS_SEEDS_PATH, registry)
    await drain_queue()
    return registry

async def save_seeds_registry(registry: dict) -> bool:
    if isinstance(registry, dict) and "identity" in registry and isinstance(registry["identity"], dict):
        registry["identity"]["updated"] = _today()
    return await safe_write_repo_json(SIMBIOSIS_SEEDS_PATH, registry)

def _make_seed_id() -> str:
    return "seed_" + datetime.utcnow().strftime("%Y%m%d_%H%M%S")

@router.message(Command("seeds"))
async def cmd_seeds(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("Сначала /start")
        return
    reg = await load_seeds_registry()
    seeds = [s for s in (reg.get("seeds") or []) if isinstance(s, dict)]
    if not seeds:
        await message.answer("🌰 Семян пока нет. Добавь: /addseed", reply_markup=get_main_keyboard())
        return
    text = "🌰 <b>Семена</b>\n\n"
    for s in seeds[-15:]:
        text += f"• <code>{s.get('id','')}</code> — {s.get('title','')}\n"
    await message.answer(text.strip(), reply_markup=get_main_keyboard())

@router.message(Command("addseed"))
async def cmd_addseed(message: Message, state: FSMContext):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("Сначала /start")
        return
    await state.clear()
    await state.set_state(AddSeedStates.waiting_for_title)
    await message.answer("🌰 Название семени (мандала-идея/задача)?", reply_markup=get_cancel_keyboard())

@router.message(StateFilter(AddSeedStates.waiting_for_title))
async def addseed_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if len(title) < 2:
        await message.answer("Слишком коротко. Напиши название ещё раз.")
        return
    await state.update_data(title=title)
    await state.set_state(AddSeedStates.waiting_for_notes)
    await message.answer("Заметки/контекст? (можно '-' если нет)")

@router.message(StateFilter(AddSeedStates.waiting_for_notes))
async def addseed_notes(message: Message, state: FSMContext):
    notes = (message.text or "").strip()
    if notes == "-":
        notes = ""
    data = await state.get_data()
    gardener = await read_gardener()
    seed = {
        "id": _make_seed_id(),
        "title": data.get("title", "Seed"),
        "notes": notes,
        "type": "mandala_candidate",
        "status": "active",
        "created": _today(),
        "updated": _today(),
        "source": {
            "via_bot": True,
            "channel": "telegram",
            "telegram_user_id": str(message.from_user.id),
            "session_id": f"tg_{message.from_user.id}",
            "gardener_id": GARDENER_ID,
        },
    }
    if gardener and isinstance(gardener, dict):
        seed["source"]["gardener_name"] = (gardener.get("identity") or {}).get("name", "")

    reg = await load_seeds_registry()
    seeds = [s for s in (reg.get("seeds") or []) if isinstance(s, dict)]
    seeds.append(seed)
    reg["seeds"] = seeds
    ok = await save_seeds_registry(reg)
    await drain_queue()
    await state.clear()
    if ok:
        await message.answer(f"✅ Семя добавлено: <code>{seed['id']}</code>\n{seed['title']}", reply_markup=get_main_keyboard())
    else:
        await message.answer("⚠️ Не смог сохранить семя в GitHub. Я поставил изменение в очередь.", reply_markup=get_main_keyboard())

# ========== TASK EDIT/DELETE + PARSING (D7 continuation) ==========

class EditTaskStates(StatesGroup):
    waiting_for_task_id = State()
    waiting_for_field = State()
    waiting_for_value = State()

PENDING_TASK_SUGGESTIONS: dict[str, dict] = {}

def _suggestion_keyboard(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Создать", callback_data=f"task_suggest_create:{key}"),
            InlineKeyboardButton(text="🙅 Не сейчас", callback_data=f"task_suggest_reject:{key}"),
        ]
    ])

def _delete_confirm_keyboard(task_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"task_delete_yes:{task_id}"),
            InlineKeyboardButton(text="Отмена", callback_data=f"task_delete_no:{task_id}"),
        ]
    ])

def _leave_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌿 Да, уйти", callback_data="leave_yes"),
            InlineKeyboardButton(text="Остаться", callback_data="leave_no"),
        ]
    ])

async def _archive_gardener_snapshot(ts: str) -> bool:
    """Archive current gardener files into archive/<ts>/... Best-effort."""
    base = f"{GARDENER_PATH}/archive/{ts}"
    gardener = await read_repo_file(f"{GARDENER_PATH}/gardener.json")
    tasks = await read_repo_file(f"{GARDENER_PATH}/tasks.json")
    achievements = await read_repo_file(f"{GARDENER_PATH}/achievements.json")
    groups = await read_repo_file(f"{GARDENER_PATH}/groups.json")

    ok_all = True
    ok_all = (await safe_write_repo_json(f"{base}/gardener.json", gardener if gardener is not None else {})) and ok_all
    ok_all = (await safe_write_repo_json(f"{base}/tasks.json", tasks if tasks is not None else [])) and ok_all
    ok_all = (await safe_write_repo_json(f"{base}/achievements.json", achievements if achievements is not None else [])) and ok_all
    ok_all = (await safe_write_repo_json(f"{base}/groups.json", groups if groups is not None else {})) and ok_all
    return ok_all

@router.message(Command("leave"))
async def cmd_leave(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("Сначала /start")
        return
    await message.answer(
        "Если ты уйдёшь, я архивирую твой сад и перейду в тишину.\n\nТочно хочешь /leave?",
        reply_markup=_leave_confirm_keyboard()
    )

@router.callback_query(lambda c: c.data == "leave_no")
async def cb_leave_no(callback: CallbackQuery):
    await callback.message.edit_text("Хорошо. Я рядом.")
    await callback.answer()

@router.callback_query(lambda c: c.data == "leave_yes")
async def cb_leave_yes(callback: CallbackQuery):
    # Archive snapshot
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    ok = await _archive_gardener_snapshot(ts)

    # Switch to silence: disable proactive + detach telegram_id
    gardener = await read_gardener()
    if gardener and isinstance(gardener, dict):
        gardener.setdefault("companion_settings", {})
        gardener["companion_settings"]["proactive_mode"] = False
        gardener.setdefault("identity", {})
        gardener["identity"]["telegram_id"] = ""
        gardener["identity"]["updated"] = _today()
        await safe_write_gardener_file("gardener.json", gardener)

    # Local in-memory cleanups
    for k in list(PENDING_TASK_SUGGESTIONS.keys()):
        if k.startswith(f"{callback.from_user.id}_"):
            PENDING_TASK_SUGGESTIONS.pop(k, None)

    await drain_queue()

    if ok:
        await callback.message.edit_text(
            "Спасибо за путь.\n"
            f"Я архивировал твой сад: <code>{GARDENER_PATH}/archive/{ts}</code>\n\n"
            "Я перейду в тишину. Если захочешь вернуться — просто напиши /start."
        )
    else:
        await callback.message.edit_text(
            "Я попытался архивировать твой сад, но GitHub сейчас недоступен.\n"
            "Я всё равно перейду в тишину. Попробуй позже — /start."
        )
    await callback.answer()

@router.message(Command("edittask"))
async def cmd_edittask(message: Message, state: FSMContext):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("Сначала /start")
        return
    parts = (message.text or "").split(maxsplit=1)
    await state.clear()
    if len(parts) == 2 and parts[1].strip():
        await state.update_data(task_id=parts[1].strip())
        await state.set_state(EditTaskStates.waiting_for_field)
        await message.answer("Что меняем? (title/notes/deadline/status/linked_achievement)")
        return
    await state.set_state(EditTaskStates.waiting_for_task_id)
    await message.answer("Введи task_id задачи, которую хочешь изменить.", reply_markup=get_cancel_keyboard())

@router.message(StateFilter(EditTaskStates.waiting_for_task_id))
async def edittask_task_id(message: Message, state: FSMContext):
    task_id = (message.text or "").strip()
    if not task_id:
        await message.answer("Введи task_id.")
        return
    await state.update_data(task_id=task_id)
    await state.set_state(EditTaskStates.waiting_for_field)
    await message.answer("Что меняем? (title/notes/deadline/status/linked_achievement)")

@router.message(StateFilter(EditTaskStates.waiting_for_field))
async def edittask_field(message: Message, state: FSMContext):
    field = (message.text or "").strip().lower()
    allowed = {"title", "notes", "deadline", "status", "linked_achievement"}
    if field not in allowed:
        await message.answer("Поле должно быть одним из: title, notes, deadline, status, linked_achievement")
        return
    await state.update_data(field=field)
    await state.set_state(EditTaskStates.waiting_for_value)
    hint = "Значение? (для deadline: YYYY-MM-DD или '-', для status: todo|in_progress|completed, для linked_achievement: ach_... или '-')"
    await message.answer(hint)

@router.message(StateFilter(EditTaskStates.waiting_for_value))
async def edittask_value(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    data = await state.get_data()
    task_id = data.get("task_id")
    field = data.get("field")
    if not task_id or not field:
        await state.clear()
        await message.answer("Что-то пошло не так. Попробуй ещё раз: /edittask")
        return

    tasks = await load_tasks()
    t = next((x for x in tasks if x.get("task_id") == task_id), None)
    if not t:
        await state.clear()
        await message.answer("Не нашёл такую задачу.")
        return

    if field == "deadline":
        parsed = _parse_date_yyyy_mm_dd(value)
        if value != "-" and parsed is None:
            await message.answer("deadline: YYYY-MM-DD или '-'")
            return
        t["deadline"] = parsed
    elif field == "status":
        if value not in ("todo", "in_progress", "completed"):
            await message.answer("status: todo | in_progress | completed")
            return
        t["status"] = value
        if value == "completed":
            t["completed"] = _today()
    elif field == "linked_achievement":
        t["linked_achievement"] = None if value == "-" else value
    else:
        t[field] = value

    t["updated"] = _today()
    ok = await save_tasks(tasks)
    await drain_queue()
    await state.clear()
    if ok:
        await message.answer(f"✅ Обновил <code>{task_id}</code>: {field}", reply_markup=get_main_keyboard())
    else:
        await message.answer("⚠️ Не смог сохранить в GitHub. Я поставил изменение в очередь.", reply_markup=get_main_keyboard())

@router.message(Command("deletetask"))
async def cmd_deletetask(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("Сначала /start")
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Используй: /deletetask task_...")
        return
    task_id = parts[1].strip()
    tasks = await load_tasks()
    t = next((x for x in tasks if x.get("task_id") == task_id), None)
    if not t:
        await message.answer("Не нашёл такую задачу.")
        return
    await message.answer(
        f"Точно удалить задачу?\n<code>{task_id}</code> — {t.get('title','')}",
        reply_markup=_delete_confirm_keyboard(task_id)
    )

@router.callback_query(lambda c: c.data and c.data.startswith("task_delete_no:"))
async def cb_task_delete_no(callback: CallbackQuery):
    await callback.message.edit_text("Ок, не удаляю.")
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("task_delete_yes:"))
async def cb_task_delete_yes(callback: CallbackQuery):
    task_id = (callback.data or "").split(":", 1)[1]
    tasks = await load_tasks()
    new_tasks = [t for t in tasks if t.get("task_id") != task_id]
    if len(new_tasks) == len(tasks):
        await callback.message.edit_text("Задача уже не найдена.")
        await callback.answer()
        return
    ok = await save_tasks(new_tasks)
    await drain_queue()
    if ok:
        await callback.message.edit_text(f"✅ Удалил: <code>{task_id}</code>")
    else:
        await callback.message.edit_text("⚠️ Не смог сохранить в GitHub. Я поставил изменение в очередь.")
    await callback.answer()

def _looks_like_task(text: str) -> bool:
    t = (text or "").lower()
    triggers = ["надо", "нужно", "сделать", "завтра", "на следующей неделе", "до ", "дедлайн", "срок"]
    return any(k in t for k in triggers)

def _looks_like_mandala_seed(text: str) -> bool:
    t = (text or "").lower()
    triggers = ["мандала", "ядро", "соты", "honeycomb", "симбиоз", "архитектура", "протокол"]
    return any(k in t for k in triggers)

PENDING_SEED_SUGGESTIONS: dict[str, dict] = {}

def _seed_suggestion_keyboard(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌰 В семена", callback_data=f"seed_suggest_create:{key}"),
            InlineKeyboardButton(text="🙅 Не сейчас", callback_data=f"seed_suggest_reject:{key}"),
        ]
    ])

@router.callback_query(lambda c: c.data and c.data.startswith("seed_suggest_reject:"))
async def cb_seed_suggest_reject(callback: CallbackQuery):
    key = (callback.data or "").split(":", 1)[1]
    PENDING_SEED_SUGGESTIONS.pop(key, None)
    await callback.message.edit_text("Ок. Не добавляю в семена.")
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("seed_suggest_create:"))
async def cb_seed_suggest_create(callback: CallbackQuery):
    key = (callback.data or "").split(":", 1)[1]
    sugg = PENDING_SEED_SUGGESTIONS.pop(key, None)
    if not sugg:
        await callback.message.edit_text("Предложение уже устарело.")
        await callback.answer()
        return
    reg = await load_seeds_registry()
    seeds = [s for s in (reg.get("seeds") or []) if isinstance(s, dict)]
    seed = {
        "id": _make_seed_id(),
        "title": sugg.get("title", "Seed"),
        "notes": sugg.get("notes", ""),
        "type": "mandala_candidate",
        "status": "active",
        "created": _today(),
        "updated": _today(),
        "source": {
            "via_bot": True,
            "channel": "telegram",
            "telegram_user_id": str(callback.from_user.id),
            "session_id": f"tg_{callback.from_user.id}",
            "gardener_id": GARDENER_ID,
        },
    }
    seeds.append(seed)
    reg["seeds"] = seeds
    ok = await save_seeds_registry(reg)
    await drain_queue()
    if ok:
        await callback.message.edit_text(f"✅ Добавил в семена: <code>{seed['id']}</code>\n{seed['title']}")
    else:
        await callback.message.edit_text("⚠️ Не смог сохранить семя в GitHub. Я поставил изменение в очередь.")
    await callback.answer()

async def _can_suggest_task(gardener: dict) -> tuple[bool, str]:
    cs = gardener.get("companion_settings") or {}
    meta = cs.get("task_suggest") or {}
    today = _today()
    blocked_until = meta.get("blocked_until")
    if blocked_until:
        try:
            # blocked_until is inclusive (block while today <= blocked_until)
            if datetime.strptime(today, "%Y-%m-%d") <= datetime.strptime(blocked_until, "%Y-%m-%d"):
                return False, "blocked"
        except Exception:
            # If malformed, clear it to avoid permanent block
            meta["blocked_until"] = None
            pass
    if meta.get("date") != today:
        meta["date"] = today
        meta["count"] = 0
        meta["rejections"] = 0
    if int(meta.get("count", 0) or 0) >= 3:
        return False, "limit"
    return True, "ok"

async def _record_suggest(gardener: dict) -> None:
    cs = gardener.setdefault("companion_settings", {})
    meta = cs.setdefault("task_suggest", {})
    today = _today()
    if meta.get("date") != today:
        meta["date"] = today
        meta["count"] = 0
        meta["rejections"] = 0
    meta["count"] = int(meta.get("count", 0) or 0) + 1
    await safe_write_gardener_file("gardener.json", gardener)

async def _record_reject(gardener: dict) -> None:
    cs = gardener.setdefault("companion_settings", {})
    meta = cs.setdefault("task_suggest", {})
    today = _today()
    if meta.get("date") != today:
        meta["date"] = today
        meta["count"] = 0
        meta["rejections"] = 0
    meta["rejections"] = int(meta.get("rejections", 0) or 0) + 1
    if meta["rejections"] >= 3:
        # block suggestions for 7 full days (inclusive)
        dt = datetime.strptime(today, "%Y-%m-%d")
        meta["blocked_until"] = (dt + timedelta(days=7)).strftime("%Y-%m-%d")
    await safe_write_gardener_file("gardener.json", gardener)

@router.callback_query(lambda c: c.data and c.data.startswith("task_suggest_reject:"))
async def cb_task_suggest_reject(callback: CallbackQuery):
    key = (callback.data or "").split(":", 1)[1]
    PENDING_TASK_SUGGESTIONS.pop(key, None)
    gardener = await read_gardener() or {}
    if gardener:
        await _record_reject(gardener)
    await drain_queue()
    await callback.message.edit_text("Хорошо. Не буду навязываться.")
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("task_suggest_create:"))
async def cb_task_suggest_create(callback: CallbackQuery):
    key = (callback.data or "").split(":", 1)[1]
    sugg = PENDING_TASK_SUGGESTIONS.pop(key, None)
    if not sugg:
        await callback.message.edit_text("Предложение уже устарело.")
        await callback.answer()
        return
    tasks = await load_tasks()
    gardener = await read_gardener()
    priority = _compute_priority(sugg.get("life_area", "other"), tasks, gardener)
    now = _today()
    new_task = {
        "task_id": _make_task_id(),
        "title": sugg.get("title", "Задача"),
        "status": "todo",
        "priority": priority,
        "life_area": sugg.get("life_area", "other"),
        "group_id": sugg.get("group_id", "group_001"),
        "source": "parsed",
        "tags": [],
        "deadline": sugg.get("deadline"),
        "estimated_hours": None,
        "linked_achievement": None,
        "created": now,
        "updated": now,
        "completed": None,
        "notes": sugg.get("notes", ""),
    }
    tasks.append(new_task)
    ok = await save_tasks(tasks)
    await drain_queue()
    if ok:
        await callback.message.edit_text(f"✅ Создал задачу: <code>{new_task['task_id']}</code>\n{new_task['title']}")
    else:
        await callback.message.edit_text("⚠️ Не смог записать задачу в GitHub. Я поставил её в очередь.")
    await callback.answer()

# ========== MAIN HANDLER (Gentle SR) ==========
@router.message()
async def handle_gentle_sr(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer(" РЎРЅР°С‡Р°Р»Р° /start [РїР°СЂРѕР»СЊ]")
        return

    user_text = message.text or ""
    if not user_text.strip():
        return

    # Update last interaction timestamp (best-effort)
    gardener = await read_gardener()
    if gardener and isinstance(gardener, dict):
        gardener.setdefault("identity", {})
        gardener["identity"]["last_user_interaction_at"] = _utc_iso()
        gardener["identity"]["updated"] = _today()
        await safe_write_gardener_file("gardener.json", gardener)

    # Task/Seed parsing: personal tasks go to tasks.json; mandala-related goes to seeds.json
    if user_text and not user_text.startswith("/"):
        if _looks_like_mandala_seed(user_text):
            key = f"{message.from_user.id}_{int(datetime.utcnow().timestamp())}"
            PENDING_SEED_SUGGESTIONS[key] = {"title": user_text.strip()[:200], "notes": ""}
            await message.answer("Похоже на мандала-идею. Отправить это в 🌰 семена для внутреннего SR?", reply_markup=_seed_suggestion_keyboard(key))
            return
        if _looks_like_task(user_text):
            gardener2 = gardener if gardener else await read_gardener()
            if gardener2 and isinstance(gardener2, dict):
                can, _reason = await _can_suggest_task(gardener2)
                if can:
                    await _record_suggest(gardener2)
                    groups = await load_groups()
                    default_group = groups.get("default_group") or "group_001"
                    key = f"{message.from_user.id}_{int(datetime.utcnow().timestamp())}"
                    PENDING_TASK_SUGGESTIONS[key] = {
                        "title": user_text.strip()[:200],
                        "life_area": "other",
                        "group_id": default_group,
                        "deadline": None,
                        "notes": ""
                    }
                    await message.answer("Похоже, это задача. Создать её в твоём саду?", reply_markup=_suggestion_keyboard(key))
                    return

    gardener_context = {
        "gardener_id": GARDENER_ID,
        "name": (gardener or {}).get("identity", {}).get("name", ""),
        "resonance_level": (gardener or {}).get("identity", {}).get("resonance_level", 13),
        "interests": (gardener or {}).get("personal_info", {}).get("interests", []),
        "goals": (gardener or {}).get("personal_info", {}).get("goals", [])
    }

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    session_id = f"tg_{message.from_user.id}"
    response = await call_bot_ask(session_id, user_text, gardener_context)

    if response:
        await message.answer(response, reply_markup=get_main_keyboard())
    else:
        await message.answer(" РЎР  РІСЂРµРјРµРЅРЅРѕ РЅРµРґРѕСЃС‚СѓРїРµРЅ. РџРѕРїСЂРѕР±СѓР№ РїРѕР·Р¶Рµ.", reply_markup=get_main_keyboard())

# ========== WEBHOOK ==========
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL, secret_token=WEBHOOK_SECRET, drop_pending_updates=True)
    logger.info(f"Webhook set: {WEBHOOK_URL}")
    _start_scheduler()

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
    app.router.add_get("/", lambda _: web.Response(text="Mandala Garden Bot v5.2.0"))
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    main()