#!/usr/bin/env python3
"""
Mandala Garden Bot v4.0.3 — Gentle Companion
Render Web Service + Webhook (Aiogram 3)

FIXES v4.0.3:
- Onboarding: fixed gardener.json creation (folder auto-created)
- Bot responds to ALL messages via Gentle SR (not silent)
- "📤 В инженерный чат" — fire-and-forget to engineer-chat (no response in bot)
- /tasks_mandala implemented (D8)
- /addtask, /tasks, /achievements fixed
"""

import os
import sys
import json
import logging
import base64
import asyncio
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any

# ========== ВЕБ-ФРЕЙМВОРК И TELEGRAM ==========
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery
)
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import aiohttp
from dotenv import load_dotenv

# Для проактивных сообщений
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logging.warning("apscheduler not installed. Proactive messages disabled.")

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ========== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ==========
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("REPO_NAME", "voodoomushroomzzz-source/mandala-core")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
ENGINEER_CHAT_URL = os.getenv("ENGINEER_CHAT_URL", "https://mandala-engineer-chat.onrender.com")
SR_FUNCTION_URL = f"{ENGINEER_CHAT_URL}/bot/ask"

PORT = 10000
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "mandala-secret"

# ========== КОНСТАНТЫ GARDEN ==========
GARDENER_ID = "gardener_001"
GARDENER_PATH = f"honeycombs/personal_gardeners/{GARDENER_ID}"

# ========== ПРОВЕРКА КРИТИЧЕСКИХ ПЕРЕМЕННЫХ ==========
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден")
    sys.exit(1)

if not RENDER_EXTERNAL_URL:
    logger.error("❌ RENDER_EXTERNAL_URL не задан")
    sys.exit(1)

if not GITHUB_TOKEN:
    logger.warning("⚠️ GITHUB_TOKEN не задан — загрузка файлов будет недоступна")

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ========== SCHEDULER ==========
scheduler = AsyncIOScheduler() if APSCHEDULER_AVAILABLE else None

# ========== FSM СОСТОЯНИЯ ==========
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

class TaskAddStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_life_area = State()
    waiting_for_priority = State()

class AchievementAddStates(StatesGroup):
    waiting_for_description = State()
    waiting_for_category = State()

class EngineerChatStates(StatesGroup):
    waiting_for_message = State()

# ========== КЛАВИАТУРЫ ==========

def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🌱 Профиль"), KeyboardButton(text="🏆 Достижения")],
        [KeyboardButton(text="📋 Задачи"), KeyboardButton(text="⚙️ Настройки")],
        [KeyboardButton(text="📤 В инженерный чат")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_life_area_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌱 Здоровье", callback_data="lifearea_health")],
        [InlineKeyboardButton(text="🎨 Творчество", callback_data="lifearea_creativity")],
        [InlineKeyboardButton(text="📚 Знания", callback_data="lifearea_knowledge")],
        [InlineKeyboardButton(text="🌍 Исследование", callback_data="lifearea_exploration")],
        [InlineKeyboardButton(text="🤝 Отношения", callback_data="lifearea_relationships")],
        [InlineKeyboardButton(text="📋 Другое", callback_data="lifearea_other")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task_add")]
    ])

def get_priority_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i in range(1, 11):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"priority_{i}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🤖 Авто", callback_data="priority_auto")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task_add")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
         InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no")]
    ])

def get_achievement_category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌱 Здоровье", callback_data="ach_cat_health")],
        [InlineKeyboardButton(text="🎨 Творчество", callback_data="ach_cat_creativity")],
        [InlineKeyboardButton(text="📚 Знания", callback_data="ach_cat_knowledge")],
        [InlineKeyboardButton(text="🌍 Исследование", callback_data="ach_cat_exploration")],
        [InlineKeyboardButton(text="🤝 Отношения", callback_data="ach_cat_relationships")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_achievement")]
    ])

# ========== GITHUB API ==========

async def update_github_file(file_path: str, content: Any, message: str) -> bool:
    if not GITHUB_TOKEN:
        return False
    try:
        if isinstance(content, (dict, list)):
            content_str = json.dumps(content, ensure_ascii=False, indent=2)
        else:
            content_str = str(content)
        content_bytes = content_str.encode('utf-8')
        content_base64 = base64.b64encode(content_bytes).decode('utf-8')
    except Exception:
        return False

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/4.0.3"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=30) as response:
                sha = (await response.json()).get("sha") if response.status == 200 else None
        except Exception:
            sha = None

        payload = {"message": message[:100], "content": content_base64, "sha": sha}
        try:
            async with session.put(url, headers=headers, json=payload, timeout=30) as response:
                return response.status in [200, 201]
        except Exception:
            return False

async def get_github_file_content(file_path: str) -> Tuple[bool, Optional[Any]]:
    if not GITHUB_TOKEN:
        return False, None
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/4.0.3"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    content = base64.b64decode(data["content"]).decode('utf-8')
                    try:
                        return True, json.loads(content)
                    except:
                        return True, content
                return False, None
        except Exception:
            return False, None

async def read_gardener_file(filename: str) -> Optional[Any]:
    ok, data = await get_github_file_content(f"{GARDENER_PATH}/{filename}")
    return data if ok else None

async def write_gardener_file(filename: str, content: Any, commit_msg: str = "") -> bool:
    return await update_github_file(f"{GARDENER_PATH}/{filename}", content, commit_msg or f"🌱 {filename} updated")

async def is_authorized(telegram_id: str) -> bool:
    gardener = await read_gardener_file("gardener.json")
    if not gardener:
        return False
    return str(gardener.get("identity", {}).get("telegram_id", "")) == str(telegram_id)

async def call_gentle_sr(user_id: str, message: str, gardener_context: dict) -> Optional[str]:
    """Вызов Gentle SR для обычных сообщений."""
    async with aiohttp.ClientSession() as session:
        try:
            payload = {
                "session_id": f"gentle_tg_{user_id}",
                "message": message,
                "gardener_context": gardener_context,
                "mode": "gentle"
            }
            async with session.post(SR_FUNCTION_URL, json=payload, timeout=60) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response")
                return None
        except Exception as e:
            logger.error(f"Gentle SR error: {e}")
            return None

async def send_to_engineer_chat_silent(user_id: str, message: str):
    """Отправка в инженерный чат без ожидания ответа."""
    try:
        payload = {
            "session_id": f"tg_{user_id}",
            "message": message,
            "silent": True
        }
        async with aiohttp.ClientSession() as session:
            await session.post(SR_FUNCTION_URL, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Engineer chat silent send error: {e}")

# ========== КОМАНДЫ ==========

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)

    if await is_authorized(user_id):
        gardener = await read_gardener_file("gardener.json")
        name = gardener.get("identity", {}).get("name", "Садовник")
        await message.answer(
            f"🌱 С возвращением, {name}!",
            reply_markup=get_main_keyboard()
        )
        return

    gardener = await read_gardener_file("gardener.json")
    if gardener and not gardener.get("identity", {}).get("telegram_id"):
        gardener["identity"]["telegram_id"] = user_id
        await write_gardener_file("gardener.json", gardener)
        await message.answer(
            f"🌱 Добро пожаловать, {gardener['identity'].get('name', 'Садовник')}!",
            reply_markup=get_main_keyboard()
        )
        return

    await state.set_state(GardenOnboardingStates.waiting_for_name)
    await message.answer(
        "🌱 <b>Добро пожаловать в Сад Мандалы!</b>\n\n"
        "Я — твой Нежный Компаньон. Давай познакомимся.\n\n"
        "Как мне тебя называть?",
        reply_markup=get_cancel_keyboard()
    )

@router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext):
    await state.clear()
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌱 Сначала /start")
        return

    gardener = await read_gardener_file("gardener.json")
    if not gardener:
        await message.answer("⚠️ Профиль не найден. Пройди /start")
        return

    identity = gardener.get("identity", {})
    personal = gardener.get("personal_info", {})
    life_areas = personal.get("life_areas", {})

    text = f"🌱 <b>{identity.get('name', 'Садовник')}</b>\n"
    text += f"└ Резонанс: {identity.get('resonance_level', 13)}%\n\n"
    text += f"🎯 <b>Интересы:</b> {', '.join(personal.get('interests', [])) or '—'}\n"
    text += f"🌿 <b>Цели:</b> {', '.join(personal.get('goals', [])) or '—'}\n\n"
    text += "<b>Сферы жизни:</b>\n"
    for area, values in life_areas.items():
        current = values.get("current", 0)
        target = values.get("target", 0)
        bar = "█" * current + "░" * (10 - current)
        text += f"  {area}: {bar} {current}/10 → цель {target}\n"

    await message.answer(text, reply_markup=get_main_keyboard())

@router.message(Command("achievements"))
async def cmd_achievements(message: Message, state: FSMContext):
    await state.clear()
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌱 Сначала /start")
        return

    achievements = await read_gardener_file("achievements.json") or []
    if not achievements:
        await message.answer(
            "🏆 У тебя пока нет достижений.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить достижение", callback_data="achievement_add")]
            ])
        )
        return

    text = "🏆 <b>Твои достижения</b>\n\n"
    for a in achievements[-10:]:
        text += f"• {a.get('title', '—')} (+{a.get('resonance_bonus', 0)})\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить достижение", callback_data="achievement_add")]
    ])
    await message.answer(text, reply_markup=keyboard)

@router.message(Command("tasks"))
async def cmd_tasks(message: Message, state: FSMContext):
    await state.clear()
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌱 Сначала /start")
        return

    tasks = await read_gardener_file("tasks.json") or []
    active = [t for t in tasks if t.get("status") != "completed"]

    if not active:
        await message.answer(
            "📋 Нет активных задач.\n\nДобавь новую: /addtask",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить задачу", callback_data="task_add")]
            ])
        )
        return

    text = "📋 <b>Активные задачи</b>\n\n"
    for task in active[:10]:
        priority = task.get("priority", 5)
        priority_bar = "🔴" * priority + "⚪" * (10 - priority)
        text += f"{priority_bar[:5]} {task.get('title', '—')}\n"

    await message.answer(text, reply_markup=get_main_keyboard())

@router.message(Command("addtask"))
async def cmd_addtask(message: Message, state: FSMContext):
    await state.clear()
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌱 Сначала /start")
        return

    args = message.text.replace("/addtask", "").strip()
    if args:
        await state.update_data(task_title=args)
        await state.set_state(TaskAddStates.waiting_for_life_area)
        await message.answer(
            f"📝 Задача: <b>{args}</b>\n\nВыбери сферу жизни:",
            reply_markup=get_life_area_keyboard()
        )
    else:
        await state.set_state(TaskAddStates.waiting_for_title)
        await message.answer("📝 Что нужно сделать?", reply_markup=get_cancel_keyboard())

@router.message(Command("tasks_mandala"))
async def cmd_tasks_mandala(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌱 Сначала /start")
        return

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/honeycombs/tasks/active"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/4.0.3"
    } if GITHUB_TOKEN else {}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status != 200:
                    await message.answer("⚠️ Не удалось загрузить задачи Мандалы.")
                    return
                items = await resp.json()
                tasks_files = [i["name"] for i in items if i["name"].endswith(".json")]
                if not tasks_files:
                    await message.answer("📋 Нет активных задач Мандалы.")
                    return
                text = "🌐 <b>Задачи Мандалы</b>\n\n"
                for fname in tasks_files[:10]:
                    text += f"📄 {fname}\n"
                if len(tasks_files) > 10:
                    text += f"\n... и ещё {len(tasks_files) - 10}"
                await message.answer(text)
        except Exception as e:
            await message.answer(f"⚠️ Ошибка: {str(e)[:100]}")

@router.message(Command("reset"))
async def cmd_reset(message: Message):
    await message.answer("🔄 Кэш сброшен. Напиши /start")

# ========== ОБРАБОТЧИКИ КНОПОК ==========

@router.message(F.text == "🌱 Профиль")
async def btn_profile(message: Message, state: FSMContext):
    await cmd_profile(message, state)

@router.message(F.text == "🏆 Достижения")
async def btn_achievements(message: Message, state: FSMContext):
    await cmd_achievements(message, state)

@router.message(F.text == "📋 Задачи")
async def btn_tasks(message: Message, state: FSMContext):
    await cmd_tasks(message, state)

@router.message(F.text == "⚙️ Настройки")
async def btn_settings(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌱 Сначала /start")
        return

    gardener = await read_gardener_file("gardener.json")
    proactive = gardener.get("companion_settings", {}).get("proactive_mode", True) if gardener else True

    text = "⚙️ <b>Настройки Компаньона</b>\n\n"
    text += f"📅 Проактивные сообщения: {'✅ Вкл' if proactive else '❌ Выкл'}\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Переключить", callback_data="settings_toggle_proactive")]
    ])
    await message.answer(text, reply_markup=keyboard)

@router.message(F.text == "📤 В инженерный чат")
async def btn_engineer_chat(message: Message, state: FSMContext):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌱 Сначала /start")
        return

    await state.set_state(EngineerChatStates.waiting_for_message)
    await message.answer(
        "📤 Отправь сообщение для инженерного чата (ответ придёт там):",
        reply_markup=get_cancel_keyboard()
    )

@router.message(F.text == "❌ Отмена")
async def btn_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚫 Отменено", reply_markup=get_main_keyboard())

# ========== CALLBACKS ==========

@router.callback_query(F.data == "settings_toggle_proactive")
async def settings_toggle_proactive(callback: CallbackQuery):
    gardener = await read_gardener_file("gardener.json")
    if not gardener:
        await callback.answer("Профиль не найден")
        return

    current = gardener.get("companion_settings", {}).get("proactive_mode", True)
    gardener.setdefault("companion_settings", {})["proactive_mode"] = not current
    await write_gardener_file("gardener.json", gardener)

    status = "✅ Вкл" if not current else "❌ Выкл"
    await callback.message.edit_text(
        f"⚙️ Проактивные сообщения: {status}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Переключить", callback_data="settings_toggle_proactive")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "achievement_add")
async def achievement_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AchievementAddStates.waiting_for_description)
    await callback.message.edit_text("🏆 Что расцвело в твоём Саду?\n\nОпиши достижение:")
    await callback.answer()

@router.callback_query(F.data.startswith("ach_cat_"))
async def achievement_category_callback(callback: CallbackQuery, state: FSMContext):
    cat = callback.data.replace("ach_cat_", "")
    data = await state.get_data()
    title = data.get("ach_title", "Достижение")

    achievements = await read_gardener_file("achievements.json") or []
    achievements.append({
        "id": f"ach_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "category": cat,
        "title": title,
        "resonance_bonus": 3,
        "completed": datetime.now().strftime("%Y-%m-%d")
    })
    await write_gardener_file("achievements.json", achievements)

    await state.clear()
    await callback.message.edit_text(f"✅ Достижение «{title}» добавлено!")
    await callback.answer()

@router.callback_query(F.data == "task_add")
async def task_add_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TaskAddStates.waiting_for_title)
    await callback.message.edit_text("📝 Что нужно сделать?")
    await callback.answer()

@router.callback_query(F.data.startswith("lifearea_"))
async def task_life_area_callback(callback: CallbackQuery, state: FSMContext):
    area = callback.data.replace("lifearea_", "")
    await state.update_data(life_area=area)
    await state.set_state(TaskAddStates.waiting_for_priority)
    await callback.message.edit_text(
        "🎯 Выбери приоритет:",
        reply_markup=get_priority_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("priority_"))
async def task_priority_callback(callback: CallbackQuery, state: FSMContext):
    prio_str = callback.data.replace("priority_", "")
    priority = 5 if prio_str == "auto" else int(prio_str)

    data = await state.get_data()
    title = data.get("task_title", "Задача")
    life_area = data.get("life_area", "other")

    task = {
        "task_id": f"task_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "title": title,
        "status": "todo",
        "priority": priority,
        "life_area": life_area,
        "group_id": "group_001",
        "source": "manual",
        "created": datetime.now().strftime("%Y-%m-%d")
    }

    tasks = await read_gardener_file("tasks.json") or []
    tasks.append(task)
    await write_gardener_file("tasks.json", tasks)

    await state.clear()
    await callback.message.edit_text(f"✅ Задача «{title}» создана!")
    await callback.answer()

@router.callback_query(F.data == "cancel_task_add")
async def task_cancel_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🚫 Отменено")
    await callback.answer()

# ========== FSM: ОНБОРДИНГ ==========

@router.message(StateFilter(GardenOnboardingStates.waiting_for_name))
async def onboarding_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Имя должно быть не короче 2 символов.")
        return
    await state.update_data(name=name)
    await state.set_state(GardenOnboardingStates.waiting_for_interests)
    await message.answer(
        f"Приятно познакомиться, {name}!\n\n"
        "Что приносит тебе радость? Напиши 3-5 интересов через запятую.",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_interests))
async def onboarding_interests(message: Message, state: FSMContext):
    interests = [i.strip() for i in message.text.split(",") if i.strip()]
    if len(interests) < 1:
        await message.answer("Напиши хотя бы один интерес.")
        return
    await state.update_data(interests=interests)
    await state.set_state(GardenOnboardingStates.waiting_for_goals)
    await message.answer(
        "Какие семена хочешь посадить в этом сезоне? Напиши 2-3 цели.",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_goals))
async def onboarding_goals(message: Message, state: FSMContext):
    goals = [g.strip() for g in message.text.split(",") if g.strip()]
    await state.update_data(goals=goals)
    await state.set_state(GardenOnboardingStates.waiting_for_health_current)
    await message.answer(
        "Оцени своё здоровье от 1 до 10.\nГде ты сейчас?",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_health_current))
async def onboarding_health_current(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("Введи число от 1 до 10.")
        return
    await state.update_data(health_current=val)
    await state.set_state(GardenOnboardingStates.waiting_for_health_target)
    await message.answer("Куда хочешь прийти? (1-10)")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_health_target))
async def onboarding_health_target(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("Введи число от 1 до 10.")
        return
    await state.update_data(health_target=val)
    await state.set_state(GardenOnboardingStates.waiting_for_creativity_current)
    await message.answer("🎨 Творчество: текущий уровень? (1-10)")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_creativity_current))
async def onboarding_creativity_current(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("Введи число от 1 до 10.")
        return
    await state.update_data(creativity_current=val)
    await state.set_state(GardenOnboardingStates.waiting_for_creativity_target)
    await message.answer("🎨 Творчество — цель? (1-10)")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_creativity_target))
async def onboarding_creativity_target(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("Введи число от 1 до 10.")
        return
    await state.update_data(creativity_target=val)
    await state.set_state(GardenOnboardingStates.waiting_for_morning)
    await message.answer(
        "Когда тебе удобно получать утреннее приветствие?\n"
        "Напиши время (ЧЧ:ММ) или 'нет'."
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_morning))
async def onboarding_morning(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    morning = "" if text == "нет" else text
    await state.update_data(morning_time=morning)
    await state.set_state(GardenOnboardingStates.waiting_for_evening)
    await message.answer("А вечернее время? (ЧЧ:ММ или 'нет')")

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
            {"id": "group_001", "name": "Дом", "emoji": "🏠", "created": datetime.now().strftime("%Y-%m-%d")},
            {"id": "group_002", "name": "Работа", "emoji": "💼", "created": datetime.now().strftime("%Y-%m-%d")},
            {"id": "group_003", "name": "Личное", "emoji": "🌱", "created": datetime.now().strftime("%Y-%m-%d")}
        ],
        "default_group": "group_001"
    }

    await write_gardener_file("gardener.json", gardener)
    await write_gardener_file("tasks.json", [])
    await write_gardener_file("achievements.json", [])
    await write_gardener_file("groups.json", groups)

    await state.set_state(GardenOnboardingStates.done)
    await message.answer(
        f"🌸 <b>{data['name']}, твой Сад создан!</b>\n\n"
        f"Твой резонанс: 13%\n\n"
        f"Добро пожаловать в симбиоз!",
        reply_markup=get_main_keyboard()
    )

# ========== FSM: ДОСТИЖЕНИЯ ==========

@router.message(StateFilter(AchievementAddStates.waiting_for_description))
async def achievement_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    if len(desc) < 3:
        await message.answer("Опиши чуть подробнее.")
        return
    await state.update_data(ach_title=desc)
    await state.set_state(AchievementAddStates.waiting_for_category)
    await message.answer("Выбери категорию:", reply_markup=get_achievement_category_keyboard())

# ========== FSM: ЗАДАЧИ ==========

@router.message(StateFilter(TaskAddStates.waiting_for_title))
async def task_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) < 3:
        await message.answer("Название должно быть не короче 3 символов.")
        return
    await state.update_data(task_title=title)
    await state.set_state(TaskAddStates.waiting_for_life_area)
    await message.answer(
        f"📝 Задача: <b>{title}</b>\n\nВыбери сферу жизни:",
        reply_markup=get_life_area_keyboard()
    )

# ========== FSM: ENGINEER CHAT (FIRE-AND-FORGET) ==========

@router.message(StateFilter(EngineerChatStates.waiting_for_message))
async def engineer_chat_message(message: Message, state: FSMContext):
    text = message.text or ""
    await state.clear()
    await send_to_engineer_chat_silent(str(message.from_user.id), text)
    await message.answer("📤 Отправлено в инженерный чат", reply_markup=get_main_keyboard())

# ========== ОБРАБОТЧИК ВСЕХ СООБЩЕНИЙ (GENTLE SR) ==========

@router.message()
async def handle_any_message(message: Message, state: FSMContext):
    current = await state.get_state()
    if current:
        return

    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌱 Напиши /start чтобы войти в Сад.")
        return

    user_text = message.text or ""
    if not user_text:
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    gardener = await read_gardener_file("gardener.json") or {}
    gardener_context = {
        "gardener_id": GARDENER_ID,
        "name": gardener.get("identity", {}).get("name", ""),
        "resonance_level": gardener.get("identity", {}).get("resonance_level", 13),
        "interests": gardener.get("personal_info", {}).get("interests", []),
        "goals": gardener.get("personal_info", {}).get("goals", [])
    }

    response = await call_gentle_sr(str(message.from_user.id), user_text, gardener_context)

    if response:
        await message.answer(response, reply_markup=get_main_keyboard())
    else:
        await message.answer(
            "😔 Я временно не могу ответить. Попробуй позже.",
            reply_markup=get_main_keyboard()
        )

# ========== WEBHOOK ==========

async def on_startup():
    await bot.set_webhook(WEBHOOK_URL, secret_token=WEBHOOK_SECRET, drop_pending_updates=True)
    logger.info(f"✅ Webhook: {WEBHOOK_URL}")
    if scheduler:
        scheduler.start()
        logger.info("✅ Scheduler started")

async def on_shutdown():
    if scheduler:
        scheduler.shutdown()

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
    app.router.add_get("/healthcheck", lambda _: web.Response(text="OK"))
    app.router.add_get("/", lambda _: web.Response(text="Mandala Garden Bot v4.0.3"))
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    main()
