#!/usr/bin/env python3
"""
Mandala Garden Bot v4.0.1 — Gentle Companion (Private)
Render Web Service + Webhook (Aiogram 3)

FIXES v4.0.1:
- D15: Button handlers fixed (state param added)
- D16: Onboarding FSM fixed (data saved correctly)
- D14: Hardcoded to gardener_001 only
- D13: Password protection (ALLOWED_PASSWORD)
- D17: /reset command
- D19: settings_toggle_proactive handler
- D18: /ask removed, replaced with "📤 В инженерный чат"
"""

import os
import sys
import json
import logging
import base64
import asyncio
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path

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
ALLOWED_PASSWORD = os.getenv("ALLOWED_PASSWORD", "mandala_secret_2026")
ENGINEER_CHAT_URL = os.getenv("ENGINEER_CHAT_URL", "https://mandala-engineer-chat.onrender.com")
SR_FUNCTION_URL = f"{ENGINEER_CHAT_URL}/bot/ask"

PORT = 10000
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "mandala-secret"

# Путь к личной соте садовника
GARDENER_ID = "gardener_001"
GARDENER_PATH = f"honeycombs/personal_gardeners/{GARDENER_ID}"

# Локальная очередь для soft-fail
LOCAL_QUEUE_PATH = Path("./garden_queue")

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
    waiting_for_life_areas_health = State()
    waiting_for_life_areas_creativity = State()
    waiting_for_life_areas_knowledge = State()
    waiting_for_life_areas_relationships = State()
    waiting_for_companion_morning = State()
    waiting_for_companion_evening = State()
    done = State()

class TaskAddStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_life_area = State()
    waiting_for_group = State()
    waiting_for_new_group_name = State()
    waiting_for_priority = State()
    waiting_for_deadline = State()
    waiting_for_confirm = State()

class AchievementAddStates(StatesGroup):
    waiting_for_description = State()
    waiting_for_category = State()
    waiting_for_confirm = State()

class EngineerChatStates(StatesGroup):
    waiting_for_message = State()

# ========== ЛОКАЛЬНЫЙ КЭШ ==========
_authorized: Dict[str, bool] = {}  # telegram_id -> authorized

# ========== КЛАВИАТУРЫ ==========

def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🌱 Профиль"), KeyboardButton(text="🏆 Достижения")],
        [KeyboardButton(text="📋 Задачи"), KeyboardButton(text="⚙️ Настройки")],
        [KeyboardButton(text="📤 В инженерный чат")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, selective=True)

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
        logger.error("❌ GITHUB_TOKEN не установлен")
        return False

    try:
        if isinstance(content, (dict, list)):
            content_str = json.dumps(content, ensure_ascii=False, indent=2)
        else:
            content_str = str(content)

        content_bytes = content_str.encode('utf-8')
        content_base64 = base64.b64encode(content_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"❌ Ошибка подготовки контента: {e}")
        return False

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/4.0.1"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    sha = data.get("sha")
                elif response.status == 404:
                    sha = None
                else:
                    return False
        except Exception:
            return False

        payload = {"message": message[:100], "content": content_base64, "sha": sha}

        try:
            async with session.put(url, headers=headers, json=payload, timeout=30) as response:
                return response.status in [200, 201]
        except Exception:
            return False

async def get_github_file_content(file_path: str) -> Tuple[bool, Optional[Any], Optional[str]]:
    if not GITHUB_TOKEN:
        return False, None, "GITHUB_TOKEN не настроен"

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/4.0.1"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    content = base64.b64decode(data["content"]).decode('utf-8')
                    try:
                        return True, json.loads(content), data.get("sha")
                    except:
                        return True, content, data.get("sha")
                elif response.status == 404:
                    return False, None, "Файл не найден"
                else:
                    return False, None, f"Ошибка {response.status}"
        except Exception as e:
            return False, None, str(e)

async def read_gardener_file(filename: str) -> Optional[Any]:
    path = f"{GARDENER_PATH}/{filename}"
    ok, data, _ = await get_github_file_content(path)
    return data if ok else None

async def write_gardener_file(filename: str, content: Any, commit_msg: str = "") -> bool:
    path = f"{GARDENER_PATH}/{filename}"
    msg = commit_msg or f"🌱 {GARDENER_ID}/{filename} обновлён через бот"
    return await update_github_file(path, content, msg)

# ========== ПРОВЕРКА АВТОРИЗАЦИИ ==========

def is_authorized(telegram_id: str) -> bool:
    return _authorized.get(telegram_id, False)

async def check_gardener_auth() -> bool:
    gardener = await read_gardener_file("gardener.json")
    return gardener is not None and gardener.get("identity", {}).get("telegram_id") != ""

# ========== КОМАНДЫ ==========

@router.message(Command("reset"))
async def cmd_reset(message: Message):
    user_id = str(message.from_user.id)
    if user_id in _authorized:
        del _authorized[user_id]
    await message.answer("🔄 Кэш сброшен. Отправь пароль для входа.")

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)

    if is_authorized(user_id):
        await message.answer(
            "🌱 С возвращением в Сад!",
            reply_markup=get_main_keyboard()
        )
        return

    # Проверяем, есть ли уже авторизованный gardener_001
    gardener = await read_gardener_file("gardener.json")
    if gardener and gardener.get("identity", {}).get("telegram_id") == user_id:
        _authorized[user_id] = True
        await message.answer(
            f"🌱 С возвращением, {gardener['identity'].get('name', 'Садовник')}!",
            reply_markup=get_main_keyboard()
        )
        return

    # Если gardener_001 есть, но telegram_id пустой — запускаем онбординг
    if gardener and gardener.get("identity", {}).get("telegram_id") == "":
        await state.set_state(GardenOnboardingStates.waiting_for_name)
        await message.answer(
            "🌱 <b>Добро пожаловать в Сад Мандалы!</b>\n\n"
            "Давай познакомимся. Как мне тебя называть?",
            reply_markup=get_cancel_keyboard()
        )
        return

    # Иначе требуем пароль
    await message.answer("🔐 Введи пароль для входа в Сад:")

@router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)

    if not is_authorized(user_id):
        await message.answer("🔐 Сначала введи пароль.")
        return

    gardener = await read_gardener_file("gardener.json")
    if not gardener:
        await message.answer("⚠️ Профиль не найден")
        return

    identity = gardener.get("identity", {})
    personal = gardener.get("personal_info", {})
    life_areas = personal.get("life_areas", {})

    text = f"🌱 <b>{identity.get('name', 'Садовник')}</b>\n"
    text += f"└ Резонанс: {identity.get('resonance_level', 10)}%\n\n"
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
    user_id = str(message.from_user.id)

    if not is_authorized(user_id):
        await message.answer("🔐 Сначала введи пароль.")
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

    by_cat = {}
    for a in achievements[-10:]:
        cat = a.get("category", "other")
        by_cat.setdefault(cat, []).append(a)

    text = "🏆 <b>Твои достижения</b>\n\n"
    for cat, items in by_cat.items():
        text += f"<b>{cat}:</b>\n"
        for item in items:
            text += f"  • {item.get('title', '—')} (+{item.get('resonance_bonus', 0)})\n"
        text += "\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить достижение", callback_data="achievement_add")]
    ])
    await message.answer(text, reply_markup=keyboard)

@router.message(Command("tasks"))
async def cmd_tasks(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)

    if not is_authorized(user_id):
        await message.answer("🔐 Сначала введи пароль.")
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

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="task_add")],
        [InlineKeyboardButton(text="✅ Выполненные", callback_data="tasks_completed")]
    ])
    await message.answer(text, reply_markup=keyboard)

@router.message(Command("addtask"))
async def cmd_addtask(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)

    if not is_authorized(user_id):
        await message.answer("🔐 Сначала введи пароль.")
        return

    args = message.text.replace("/addtask", "").strip()
    await state.update_data(gardener_id=GARDENER_ID)

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

@router.message(Command("leave"))
async def cmd_leave(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)

    if not is_authorized(user_id):
        await message.answer("🔐 Сначала введи пароль.")
        return

    await message.answer(
        "🌸 Ты хочешь покинуть Сад?\n\nТы уверен?",
        reply_markup=get_confirm_keyboard()
    )

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
    user_id = str(message.from_user.id)
    if not is_authorized(user_id):
        await message.answer("🔐 Сначала введи пароль.")
        return

    gardener = await read_gardener_file("gardener.json")
    proactive = gardener.get("companion_settings", {}).get("proactive_mode", True) if gardener else True

    text = "⚙️ <b>Настройки Компаньона</b>\n\n"
    text += f"📅 Проактивные сообщения: {'✅ Вкл' if proactive else '❌ Выкл'}\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Переключить проактивность", callback_data="settings_toggle_proactive")],
        [InlineKeyboardButton(text="❌ Покинуть Сад", callback_data="settings_leave")]
    ])
    await message.answer(text, reply_markup=keyboard)

@router.message(F.text == "📤 В инженерный чат")
async def btn_engineer_chat(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    if not is_authorized(user_id):
        await message.answer("🔐 Сначала введи пароль.")
        return

    await state.set_state(EngineerChatStates.waiting_for_message)
    await message.answer(
        "📤 Отправь сообщение для инженерного чата:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(F.text == "❌ Отмена")
async def btn_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚫 Отменено", reply_markup=get_main_keyboard())

# ========== CALLBACKS ==========

@router.callback_query(F.data == "settings_toggle_proactive")
async def settings_toggle_proactive(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    if not is_authorized(user_id):
        await callback.answer("Сначала авторизуйся")
        return

    gardener = await read_gardener_file("gardener.json")
    if not gardener:
        await callback.answer("Профиль не найден")
        return

    current = gardener.get("companion_settings", {}).get("proactive_mode", True)
    gardener.setdefault("companion_settings", {})["proactive_mode"] = not current
    await write_gardener_file("gardener.json", gardener)

    status = "✅ Вкл" if not current else "❌ Выкл"
    await callback.message.edit_text(
        f"⚙️ <b>Настройки обновлены</b>\n\nПроактивные сообщения: {status}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Переключить", callback_data="settings_toggle_proactive")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "settings_leave")
async def settings_leave(callback: CallbackQuery):
    await callback.message.edit_text(
        "🌸 Ты хочешь покинуть Сад?\n\nТы уверен?",
        reply_markup=get_confirm_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "confirm_yes")
async def confirm_yes(callback: CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    if user_id in _authorized:
        del _authorized[user_id]
    await state.clear()
    await callback.message.edit_text("🌸 Твой Сад засыпает. Возвращайся, когда захочешь.")
    await callback.answer()

@router.callback_query(F.data == "confirm_no")
async def confirm_no(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🌱 Ты остаёшься в Саду.")
    await callback.answer()

@router.callback_query(F.data == "achievement_add")
async def achievement_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AchievementAddStates.waiting_for_description)
    await callback.message.edit_text("🏆 Что расцвело в твоём Саду?\n\nОпиши достижение:")
    await callback.answer()

@router.callback_query(F.data.startswith("ach_cat_"))
async def achievement_category_callback(callback: CallbackQuery, state: FSMContext):
    cat = callback.data.replace("ach_cat_", "")
    await state.update_data(ach_category=cat)
    data = await state.get_data()
    title = data.get("ach_title")

    await state.set_state(AchievementAddStates.waiting_for_confirm)
    text = f"🏆 <b>Новое достижение</b>\n└ {title}\n📁 Категория: {cat}\n💫 Бонус: +3\n\nДобавить?"
    await callback.message.edit_text(text, reply_markup=get_confirm_keyboard())
    await callback.answer()

@router.callback_query(F.data == "task_add")
async def task_add_callback(callback: CallbackQuery, state: FSMContext):
    await state.update_data(gardener_id=GARDENER_ID)
    await state.set_state(TaskAddStates.waiting_for_title)
    await callback.message.edit_text("📝 Что нужно сделать?")
    await callback.answer()

@router.callback_query(F.data.startswith("lifearea_"))
async def task_life_area_callback(callback: CallbackQuery, state: FSMContext):
    area = callback.data.replace("lifearea_", "")
    await state.update_data(life_area=area)
    await state.set_state(TaskAddStates.waiting_for_priority)
    await callback.message.edit_text(
        f"✅ Сфера выбрана\n\n🎯 Выбери приоритет:",
        reply_markup=get_priority_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("priority_"))
async def task_priority_callback(callback: CallbackQuery, state: FSMContext):
    prio_str = callback.data.replace("priority_", "")
    priority = None if prio_str == "auto" else int(prio_str)
    await state.update_data(priority=priority)

    data = await state.get_data()
    title = data.get("task_title")
    life_area = data.get("life_area")

    task = {
        "task_id": f"task_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "title": title,
        "status": "todo",
        "priority": priority or 5,
        "life_area": life_area,
        "group_id": "group_001",
        "source": "manual",
        "created": datetime.now().strftime("%Y-%m-%d")
    }

    tasks = await read_gardener_file("tasks.json") or []
    tasks.append(task)
    await write_gardener_file("tasks.json", tasks, f"➕ Задача: {title}")

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
    await state.set_state(GardenOnboardingStates.waiting_for_life_areas_health)
    await message.answer(
        "Оцени свои сферы жизни от 1 до 10.\n\n"
        "<b>🌱 Здоровье:</b> где ты сейчас? (1-10)",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_life_areas_health))
async def onboarding_health_current(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("Введи число от 1 до 10.")
        return
    await state.update_data(health_current=val)
    await state.set_state(GardenOnboardingStates.waiting_for_life_areas_creativity)
    await message.answer("🌱 Здоровье — куда хочешь прийти? (1-10)")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_life_areas_creativity))
async def onboarding_health_target(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("Введи число от 1 до 10.")
        return
    await state.update_data(health_target=val)
    await state.set_state(GardenOnboardingStates.waiting_for_life_areas_knowledge)
    await message.answer("<b>🎨 Творчество:</b> текущий уровень? (1-10)")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_life_areas_knowledge))
async def onboarding_creativity_current(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("Введи число от 1 до 10.")
        return
    await state.update_data(creativity_current=val)
    await state.set_state(GardenOnboardingStates.waiting_for_life_areas_relationships)
    await message.answer("🎨 Творчество — цель? (1-10)")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_life_areas_relationships))
async def onboarding_creativity_target(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("Введи число от 1 до 10.")
        return
    await state.update_data(creativity_target=val)
    await state.set_state(GardenOnboardingStates.waiting_for_companion_morning)
    await message.answer(
        "Когда тебе удобно получать утреннее приветствие?\n"
        "Напиши время (ЧЧ:ММ) или 'нет'."
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_companion_morning))
async def onboarding_morning(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    morning = "" if text == "нет" else text
    await state.update_data(morning_time=morning)
    await state.set_state(GardenOnboardingStates.waiting_for_companion_evening)
    await message.answer("А вечернее время? (ЧЧ:ММ или 'нет')")

@router.message(StateFilter(GardenOnboardingStates.waiting_for_companion_evening))
async def onboarding_evening(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    evening = "" if text == "нет" else text
    await state.update_data(evening_time=evening)

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
            "evening_check_time": data["evening_time"],
            "proactive_mode": True,
            "timezone": "Europe/Moscow"
        },
        "growth_history": [{"date": datetime.now().strftime("%Y-%m-%d"), "resonance": 13}]
    }

    groups = {
        "groups": [
            {"id": "group_001", "name": "Дом", "emoji": "🏠", "created": datetime.now().strftime("%Y-%m-%d")},
            {"id": "group_002", "name": "Работа", "emoji": "💼", "created": datetime.now().strftime("%Y-%m-%d")},
            {"id": "group_003", "name": "Личное", "emoji": "🌱", "created": datetime.now().strftime("%Y-%m-%d")}
        ],
        "default_group": "group_001"
    }

    await write_gardener_file("gardener.json", gardener, f"🌱 Новый садовник: {data['name']}")
    await write_gardener_file("tasks.json", [])
    await write_gardener_file("achievements.json", [])
    await write_gardener_file("groups.json", groups)

    _authorized[user_id] = True

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

# ========== FSM: ENGINEER CHAT ==========

@router.message(StateFilter(EngineerChatStates.waiting_for_message))
async def engineer_chat_message(message: Message, state: FSMContext):
    text = message.text or ""
    await state.clear()

    async with aiohttp.ClientSession() as session:
        try:
            payload = {"session_id": f"tg_{message.from_user.id}", "message": text}
            async with session.post(SR_FUNCTION_URL, json=payload, timeout=60) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    response = data.get("response", "Нет ответа")
                else:
                    response = f"⚠️ Ошибка {resp.status}"
        except Exception as e:
            response = f"⚠️ {str(e)}"

    await message.answer(response, reply_markup=get_main_keyboard())

# ========== ОБРАБОТЧИК ВСЕХ СООБЩЕНИЙ (ПАРОЛЬ / АВТОРИЗАЦИЯ) ==========

@router.message()
async def handle_any_message(message: Message, state: FSMContext):
    current = await state.get_state()
    if current:
        return

    user_id = str(message.from_user.id)

    if is_authorized(user_id):
        await message.answer(
            "Используй кнопки меню или команды.",
            reply_markup=get_main_keyboard()
        )
        return

    gardener = await read_gardener_file("gardener.json")
    if gardener and gardener.get("identity", {}).get("telegram_id") == user_id:
        _authorized[user_id] = True
        await message.answer(
            f"🌱 С возвращением, {gardener['identity'].get('name', 'Садовник')}!",
            reply_markup=get_main_keyboard()
        )
        return

    text = message.text or ""
    if text.strip() == ALLOWED_PASSWORD:
        if gardener:
            gardener["identity"]["telegram_id"] = user_id
            await write_gardener_file("gardener.json", gardener)
        _authorized[user_id] = True
        await message.answer(
            "🌸 Пароль верный. Добро пожаловать в Сад!",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer("🔐 Введи пароль для входа в Сад:")

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
    app.router.add_get("/", lambda _: web.Response(text="Mandala Garden Bot v4.0.1"))
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    main()
