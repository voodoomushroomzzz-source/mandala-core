#!/usr/bin/env python3
"""
Mandala Garden Bot — Gentle Companion v5.3.0
Integrated with /bot/ask endpoint. Password protected. Hardcoded to gardener_001.
D7: Personal Task Management added.
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
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
LOCAL_QUEUE_PATH = os.getenv("LOCAL_QUEUE_PATH", os.path.join(os.getcwd(), f".{GARDENER_ID}.json.queue"))

if not BOT_TOKEN or not RENDER_EXTERNAL_URL:
    logger.error("Missing BOT_TOKEN or RENDER_EXTERNAL_URL")
    sys.exit(1)

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

def _utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)

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

async def get_github_file(file_path: str) -> Tuple[bool, Optional[Any]]:
    if not GITHUB_TOKEN:
        return False, None
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}?ref=main"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json", "User-Agent": "MandalaGardenBot/5.3.0"}
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
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json", "User-Agent": "MandalaGardenBot/5.3.0"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=30) as resp:
                sha = (await resp.json()).get("sha") if resp.status == 200 else None
        except Exception:
            sha = None
        content_str = _json_dumps(content)
        content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
        payload = {"message": f"bot: update {path}", "content": content_b64, "branch": "main"}
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

_scheduler: Optional[AsyncIOScheduler] = None

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

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True, one_time_keyboard=True)

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

async def load_tasks() -> list[dict]:
    tasks = await read_gardener_file("tasks.json")
    return tasks if isinstance(tasks, list) else []

async def save_tasks(tasks: list[dict]) -> bool:
    return await safe_write_gardener_file("tasks.json", tasks)

@router.message(StateFilter(GardenOnboardingStates.waiting_for_name))
async def onboarding_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("🌱 Имя должно быть не короче 2 символов.")
        return
    await state.update_data(name=name)
    await state.set_state(GardenOnboardingStates.waiting_for_interests)
    await message.answer(f"✨ Приятно познакомиться, {name}!\n\n🎯 Что тебя вдохновляет? Напиши 3-5 интересов через запятую.", reply_markup=get_cancel_keyboard())

@router.message(StateFilter(GardenOnboardingStates.waiting_for_interests))
async def onboarding_interests(message: Message, state: FSMContext):
    interests = [i.strip() for i in message.text.split(",") if i.strip()]
    if len(interests) < 1:
        await message.answer("🌱 Напиши хотя бы один интерес.")
        return
    await state.update_data(interests=interests)
    await state.set_state(GardenOnboardingStates.waiting_for_goals)
    await message.answer("🎯 Какие у тебя цели на ближайшее время? Напиши 2-3.", reply_markup=get_cancel_keyboard())

@router.message(StateFilter(GardenOnboardingStates.waiting_for_goals))
async def onboarding_goals(message: Message, state: FSMContext):
    goals = [g.strip() for g in message.text.split(",") if g.strip()]
    await state.update_data(goals=goals)
    await state.set_state(GardenOnboardingStates.waiting_for_health_current)
    await message.answer("💚 Оцени текущее состояние здоровья от 1 до 10.", reply_markup=get_cancel_keyboard())

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
    await message.answer("⏰ В какое время тебе комфортно получать утреннее приветствие?\nНапиши время (ЧЧ:ММ) или 'нет'.")

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
    tasks = await load_tasks()
    active_tasks = [t for t in tasks if t.get("status") != "completed"]
    await message.answer(f"🌿 <b>{name}</b>\n✨ Резонанс: {resonance}%\n📋 Активных задач: {len(active_tasks)}", reply_markup=get_main_keyboard())

@router.message(Command("achievements"))
@router.message(F.text == "🏆 Достижения")
async def cmd_achievements(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌸 Используй /start")
        return
    await message.answer("🏆 Раздел достижений в разработке.", reply_markup=get_main_keyboard())

@router.message(F.text == "💬 В инженерный чат")
async def btn_engineer_chat(message: Message, state: FSMContext):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(EngineerChatStates.waiting_for_message)
    await message.answer("💬 <b>Инженерный чат</b>\n\nНапиши сообщение — оно отправится в основную сессию engineer-chat.\n\nДля отмены нажми ❌ Отмена", reply_markup=get_cancel_keyboard())

@router.message(StateFilter(EngineerChatStates.waiting_for_message))
async def engineer_chat_send(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("💬 Напиши сообщение или нажми ❌ Отмена")
        return
    gardener = await read_gardener() or {}
    try:
        payload = {"session_id": MAIN_SESSION_ID, "message": text, "gardener_context": gardener}
        async with aiohttp.ClientSession() as session:
            async with session.post(SR_BACKEND_URL, json=payload, timeout=10) as resp:
                if resp.status in [200, 202]:
                    logger.info(f"Message sent to engineer-chat: {text[:50]}...")
    except Exception as e:
        logger.error(f"Bot ask exception: {e}")
    await state.clear()
    await message.answer("✅ Отправлено в инженерный чат", reply_markup=get_main_keyboard())

# ---------- D7: TASK MANAGEMENT ----------

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
        except:
            pass
    return max(1, min(10, p))

async def create_task(title: str, group_id: str, life_area: str, deadline: str = None, estimated_hours: int = None, notes: str = "") -> dict:
    tasks = await load_tasks()
    task_id = f"task_{_today().replace('-', '')}_{len(tasks)+1:03d}"
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

def get_groups_keyboard(groups: list) -> InlineKeyboardMarkup:
    btns = [[InlineKeyboardButton(text=g["name"], callback_data=f"grp_{g['id']}")] for g in groups]
    btns.append([InlineKeyboardButton(text="➕ Новая группа", callback_data="new_group")])
    btns.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def get_life_area_keyboard() -> InlineKeyboardMarkup:
    areas = [("❤️ Здоровье", "health"), ("🎨 Творчество", "creativity"),
             ("📚 Знания", "knowledge"), ("🗺️ Исследования", "exploration"),
             ("👥 Отношения", "relationships"), ("📌 Другое", "other")]
    btns = [[InlineKeyboardButton(text=name, callback_data=f"area_{val}")] for name, val in areas]
    btns.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def get_confirm_task_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Создать", callback_data="confirm_task")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task")]
    ])

@router.message(Command("addtask"))
async def cmd_addtask(message: Message, state: FSMContext):
    if not await is_authorized(str(message.from_user.id)):
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
    await callback.message.edit_text("📂 Введи название новой группы:", reply_markup=get_cancel_keyboard())
    await state.set_state(TaskStates.waiting_for_group)
    await callback.answer()

@router.callback_query(F.data.startswith("area_"))
async def task_life_area(callback: CallbackQuery, state: FSMContext):
    area = callback.data.replace("area_", "")
    await state.update_data(life_area=area)
    await state.set_state(TaskStates.waiting_for_deadline)
    await callback.message.edit_text("📅 Введи дедлайн в формате ГГГГ-ММ-ДД\nили отправь '-' если нет:", reply_markup=get_cancel_keyboard())
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
    summary = f"<b>📋 Проверь задачу:</b>\n🏷️ {data['title']}\n📂 Группа: {data['group_id']}\n🌈 Сфера: {data['life_area']}\n📅 Дедлайн: {data.get('deadline', 'нет')}\n⏱️ Часы: {data.get('estimated_hours', 'нет')}\n📝 Заметки: {notes or 'нет'}"
    await state.set_state(TaskStates.waiting_for_confirm)
    await message.answer(summary, reply_markup=get_confirm_task_keyboard())

@router.callback_query(F.data == "confirm_task")
async def confirm_task(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    new_task = await create_task(
        title=data["title"], group_id=data["group_id"], life_area=data["life_area"],
        deadline=data.get("deadline"), estimated_hours=data.get("estimated_hours"),
        notes=data.get("notes", "")
    )
    await callback.message.edit_text(f"✅ Задача '{new_task['title']}' создана!")
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "cancel_task")
async def cancel_task_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Создание задачи отменено.")
    await callback.answer()

@router.message(Command("tasks"))
@router.message(F.text == "📋 Задачи")
async def cmd_tasks(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    tasks = await load_tasks()
    active = [t for t in tasks if t.get("status") != "completed"]
    if not active:
        await message.answer("✨ Нет активных задач.", reply_markup=get_main_keyboard())
        return
    text = "\n".join([f"• <code>{t['task_id']}</code>: {t['title']} (⭐{t.get('priority',5)})" for t in active[:15]])
    await message.answer(f"📋 <b>Активные задачи:</b>\n{text}", reply_markup=get_main_keyboard())

@router.message(Command("done"))
async def cmd_done(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌸 Используй /start", reply_markup=get_main_keyboard())
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Укажи ID задачи: /done task_20260415_001")
        return
    task_id = parts[1]
    if await complete_task(task_id):
        await message.answer(f"✅ Задача <code>{task_id}</code> выполнена!")
    else:
        await message.answer("❌ Задача не найдена.")

@router.message(Command("groups"))
async def cmd_groups(message: Message):
    if not await is_authorized(str(message.from_user.id)):
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
    if not await is_authorized(str(message.from_user.id)):
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
    if not await is_authorized(str(message.from_user.id)):
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

@router.message(F.text == "❌ Отмена")
async def btn_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=get_main_keyboard())

async def on_startup(app: web.Application):
    await bot.set_webhook(WEBHOOK_URL, secret_token=WEBHOOK_SECRET)
    logger.info(f"Webhook set: {WEBHOOK_URL}")

async def on_shutdown(app: web.Application):
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
