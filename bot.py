#!/usr/bin/env python3
"""
Mandala Garden Bot v4.0.0 — Gentle Companion
Render Web Service + Webhook (Aiogram 3)

Garden integration: onboarding, profile, achievements, resonance,
task management (personal + Mandala), proactive Ahimsa messaging,
unified SR with engineer chat (shared session history).
"""

import os
import sys
import json
import logging
import base64
import asyncio
import copy
import re
from datetime import datetime, timedelta
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
    BufferedInputFile, CallbackQuery
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

PORT = 10000
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "mandala-secret"

# URL инженерного чата (Variant B — единый СР с историей)
ENGINEER_CHAT_URL = os.getenv("ENGINEER_CHAT_URL", "https://mandala-engineer-chat.onrender.com")
SR_FUNCTION_URL = f"{ENGINEER_CHAT_URL}/bot/ask"

# Путь к личным сотам садовников в репозитории
GARDENERS_PATH = "honeycombs/personal_gardeners"

# Локальная очередь для soft-fail (когда GitHub API недоступен)
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
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ========== SCHEDULER ДЛЯ ПРОАКТИВНЫХ СООБЩЕНИЙ ==========
scheduler = AsyncIOScheduler() if APSCHEDULER_AVAILABLE else None

# ========== FSM СОСТОЯНИЯ ДЛЯ GARDEN ==========
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
    waiting_for_timezone = State()
    done = State()

class TaskAddStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_life_area = State()
    waiting_for_group = State()
    waiting_for_new_group_name = State()
    waiting_for_priority = State()
    waiting_for_deadline = State()
    waiting_for_confirm = State()

class TaskEditStates(StatesGroup):
    waiting_for_field = State()
    waiting_for_value = State()

class AchievementAddStates(StatesGroup):
    waiting_for_description = State()
    waiting_for_category = State()
    waiting_for_confirm = State()

class LeaveStates(StatesGroup):
    waiting_for_confirmation = State()

# ========== ЛОКАЛЬНЫЙ КЭШ ==========
_gardener_id_cache: Dict[str, str] = {}

# Хранилище для Ahimsa-лимитов (FR3: парсинг задач)
_task_detection_limits: Dict[str, Dict] = {}  # user_id -> {count, last_date, declined_streak}

# ========== КЛАВИАТУРЫ ==========

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню Garden Companion"""
    keyboard = [
        [KeyboardButton(text="🌱 Профиль"), KeyboardButton(text="🏆 Достижения")],
        [KeyboardButton(text="📋 Задачи"), KeyboardButton(text="💬 Спросить")],
        [KeyboardButton(text="⚙️ Настройки")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=True
    )

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой Отмена"""
    keyboard = [[KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=True,
        selective=True
    )

def get_life_area_keyboard() -> InlineKeyboardMarkup:
    """Выбор сферы жизни для задачи"""
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
    """Выбор приоритета задачи (1-10)"""
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
    """Клавиатура подтверждения"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
         InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no")]
    ])

def get_task_actions_keyboard(task_id: str) -> InlineKeyboardMarkup:
    """Действия с задачей"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"task_done_{task_id}")],
        [InlineKeyboardButton(text="▶️ В работе", callback_data=f"task_start_{task_id}")],
        [InlineKeyboardButton(text="✏️ Изменить", callback_data=f"task_edit_{task_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"task_delete_{task_id}")]
    ])

def get_achievement_category_keyboard() -> InlineKeyboardMarkup:
    """Категории достижений"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌱 Здоровье", callback_data="ach_cat_health")],
        [InlineKeyboardButton(text="🎨 Творчество", callback_data="ach_cat_creativity")],
        [InlineKeyboardButton(text="📚 Знания", callback_data="ach_cat_knowledge")],
        [InlineKeyboardButton(text="🌍 Исследование", callback_data="ach_cat_exploration")],
        [InlineKeyboardButton(text="🤝 Отношения", callback_data="ach_cat_relationships")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_achievement")]
    ])

# ========== ФУНКЦИЯ ВЫЗОВА СР ==========

async def call_sr(chat_id: str, text: str, gardener_context: dict = None) -> Optional[str]:
    """Вызывает инженерный чат (main.py /bot/ask) и возвращает ответ.
    session_id = tg_{chat_id} — история общая между ботом и веб-чатом."""
    async with aiohttp.ClientSession() as session:
        try:
            payload = {
                "session_id": f"tg_{chat_id}",
                "message": text,
                "gardener_context": gardener_context or {}
            }
            logger.info(f"Calling SR for chat {chat_id}")
            async with session.post(
                SR_FUNCTION_URL,
                json=payload,
                timeout=60
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response")
                else:
                    logger.error(f"SR returned {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"Error calling SR: {e}")
            return None

# ========== ФУНКЦИИ GITHUB API ==========

async def update_github_file(file_path: str, content: Any, message: str) -> bool:
    """Обновляет или создает файл в GitHub репозитории."""
    if not GITHUB_TOKEN:
        logger.error("❌ GITHUB_TOKEN не установлен")
        return False

    try:
        if isinstance(content, dict) or isinstance(content, list):
            content_str = json.dumps(content, ensure_ascii=False, indent=2)
        else:
            content_str = str(content)

        if len(content_str) > 1_000_000:
            logger.error("❌ Файл слишком большой (>1MB)")
            return False

        content_bytes = content_str.encode('utf-8')
        content_base64 = base64.b64encode(content_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"❌ Ошибка подготовки контента: {e}")
        return False

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/4.0.0"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    sha = data.get("sha")
                    logger.info(f"✅ SHA получен для {file_path}")
                elif response.status == 404:
                    sha = None
                    logger.info(f"📄 {file_path} не существует, будет создан")
                else:
                    error_text = await response.text()
                    logger.error(f"⚠️ GitHub GET error {response.status}: {error_text[:200]}")
                    return False
        except asyncio.TimeoutError:
            logger.error("❌ Таймаут при получении SHA (30 сек)")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка при получении SHA: {e}")
            return False

        payload = {
            "message": message[:100],
            "content": content_base64,
            "sha": sha
        }

        try:
            async with session.put(url, headers=headers, json=payload, timeout=30) as response:
                response_text = await response.text()
                logger.info(f"📡 GitHub response status: {response.status}")

                if response.status in [200, 201]:
                    logger.info(f"✅ Файл {file_path} успешно обновлён")
                    return True
                else:
                    logger.error(f"❌ GitHub error: {response.status} - {response_text[:200]}")
                    return False

        except asyncio.TimeoutError:
            logger.error("❌ Таймаут при отправке в GitHub (30 сек)")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке в GitHub: {e}")
            return False

async def get_github_file_content(file_path: str) -> Tuple[bool, Optional[Any], Optional[str]]:
    """Получает содержимое файла из GitHub."""
    if not GITHUB_TOKEN:
        return False, None, "GITHUB_TOKEN не настроен"

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/4.0.0"
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

# ========== GARDEN HELPERS (D1) ==========

async def find_gardener_by_telegram_id(telegram_id: str) -> Optional[str]:
    """Найти gardener_id по telegram_id. Сканирует personal_gardeners/ в GitHub."""
    if telegram_id in _gardener_id_cache:
        return _gardener_id_cache[telegram_id]

    if not GITHUB_TOKEN:
        return None

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{GARDENERS_PATH}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/4.0.0"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status != 200:
                    return None
                items = await resp.json()
                folders = [
                    item["name"] for item in items
                    if item["type"] == "dir"
                    and item["name"].startswith("gardener_")
                    and item["name"] != "gardener_template"
                    and "archive" not in item["name"]
                ]
                for folder in folders:
                    ok, data, _ = await get_github_file_content(
                        f"{GARDENERS_PATH}/{folder}/gardener.json"
                    )
                    if ok and isinstance(data, dict):
                        if str(data.get("identity", {}).get("telegram_id", "")) == str(telegram_id):
                            _gardener_id_cache[telegram_id] = folder
                            return folder
    except Exception as e:
        logger.error(f"find_gardener error: {e}")
    return None

async def read_gardener_file(gardener_id: str, filename: str) -> Optional[Any]:
    """Читает файл из личной соты садовника."""
    path = f"{GARDENERS_PATH}/{gardener_id}/{filename}"
    ok, data, _ = await get_github_file_content(path)
    if ok:
        return data
    # Soft-fail: проверяем локальную очередь
    queue_file = LOCAL_QUEUE_PATH / gardener_id / filename
    if queue_file.exists():
        try:
            return json.loads(queue_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None

async def write_gardener_file(gardener_id: str, filename: str, content: Any, commit_msg: str = "") -> bool:
    """Записывает файл в личную соту садовника через GitHub API."""
    path = f"{GARDENERS_PATH}/{gardener_id}/{filename}"
    msg = commit_msg or f"🌱 {gardener_id}/{filename} обновлён через бот"
    success = await update_github_file(path, content, msg)
    if not success:
        try:
            queue_dir = LOCAL_QUEUE_PATH / gardener_id
            queue_dir.mkdir(parents=True, exist_ok=True)
            queue_file = queue_dir / filename
            content_str = json.dumps(content, ensure_ascii=False, indent=2) if not isinstance(content, str) else content
            queue_file.write_text(content_str, encoding="utf-8")
            logger.warning(f"⚠️ Soft-fail: {path} сохранён локально в очередь")
        except Exception as e:
            logger.error(f"Soft-fail write error: {e}")
    return success

async def get_gardener_context(telegram_id: str) -> dict:
    """Возвращает краткий профиль садовника для передачи в SR."""
    gardener_id = await find_gardener_by_telegram_id(str(telegram_id))
    if not gardener_id:
        return {}
    data = await read_gardener_file(gardener_id, "gardener.json")
    if not data or not isinstance(data, dict):
        return {}
    identity = data.get("identity", {})
    personal = data.get("personal_info", {})
    return {
        "gardener_id": gardener_id,
        "name": identity.get("name", ""),
        "resonance_level": identity.get("resonance_level", 0),
        "interests": personal.get("interests", []),
        "goals": personal.get("goals", []),
    }

def generate_gardener_id(existing_ids: List[str]) -> str:
    """Генерирует следующий gardener_id."""
    nums = []
    for gid in existing_ids:
        try:
            nums.append(int(gid.replace("gardener_", "")))
        except Exception:
            pass
    next_num = max(nums) + 1 if nums else 1
    return f"gardener_{next_num:03d}"

def calculate_resonance(achievements: List[Dict], catalog: Dict) -> int:
    """Рассчитывает резонанс на основе достижений."""
    if not achievements or not catalog:
        return 10  # базовый резонанс
    categories = catalog.get("categories", {})
    total = 10  # базовый уровень
    for ach in achievements:
        cat = ach.get("category", "")
        bonus = ach.get("resonance_bonus", 0)
        weight = categories.get(cat, {}).get("resonance_weight", 1.0)
        total += int(bonus * weight)
    return min(100, total)

def calculate_priority(task: Dict, gardener: Dict) -> int:
    """Авторасчет приоритета задачи."""
    base = 5
    # resonance_match по тегам
    task_tags = set(task.get("tags", []))
    interests = set(gardener.get("personal_info", {}).get("interests", []))
    if task_tags and interests:
        overlap = len(task_tags & interests)
        if overlap > 0:
            base += overlap * 2
    # life_area_gap
    life_area = task.get("life_area", "")
    if life_area and life_area in gardener.get("personal_info", {}).get("life_areas", {}):
        area = gardener["personal_info"]["life_areas"][life_area]
        current = area.get("current", 5)
        target = area.get("target", 5)
        gap = target - current
        if gap > 3:
            base += 3
        elif gap > 0:
            base += 1
    return max(1, min(10, base))

def generate_task_id() -> str:
    """Генерирует ID задачи."""
    return f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# ========== AHHIMSA GUARDRAILS (D9) ==========

class AhimsaGuard:
    @staticmethod
    def should_send_proactive(gardener: Dict, message_type: str) -> Tuple[bool, str]:
        """Проверяет, можно ли отправить проактивное сообщение."""
        if not gardener.get("companion_settings", {}).get("proactive_mode", True):
            return False, "proactive_mode disabled"
        # Проверка silence policy
        last_interaction = gardener.get("identity", {}).get("last_interaction")
        if last_interaction:
            last_dt = datetime.fromisoformat(last_interaction)
            days_silent = (datetime.now() - last_dt).days
            if days_silent > 30:
                return False, "silence > 30 days"
            elif days_silent > 7 and message_type != "gentle_check":
                return False, "only gentle check allowed after 7 days"
        # Проверка лимита в день
        today = datetime.now().strftime("%Y-%m-%d")
        sent_today = gardener.get("_proactive_sent", {}).get(today, [])
        if message_type in sent_today:
            return False, f"{message_type} already sent today"
        if len(sent_today) >= 2:
            return False, "max 2 proactive messages per day"
        return True, "ok"

    @staticmethod
    def check_task_detection_limit(user_id: str) -> Tuple[bool, str]:
        """Проверяет лимиты на детекцию задач (FR3)."""
        global _task_detection_limits
        today = datetime.now().strftime("%Y-%m-%d")
        if user_id not in _task_detection_limits:
            _task_detection_limits[user_id] = {"count": 0, "last_date": today, "declined_streak": 0}
        limits = _task_detection_limits[user_id]
        if limits["last_date"] != today:
            limits["count"] = 0
            limits["last_date"] = today
        if limits["count"] >= 3:
            return False, "max 3 detections per day"
        if limits["declined_streak"] >= 3:
            return False, "3 declined in a row"
        return True, "ok"

    @staticmethod
    def record_task_detection(user_id: str, accepted: bool):
        """Записывает результат детекции задачи."""
        global _task_detection_limits
        today = datetime.now().strftime("%Y-%m-%d")
        if user_id not in _task_detection_limits:
            _task_detection_limits[user_id] = {"count": 0, "last_date": today, "declined_streak": 0}
        limits = _task_detection_limits[user_id]
        if limits["last_date"] != today:
            limits["count"] = 0
            limits["last_date"] = today
        limits["count"] += 1
        if accepted:
            limits["declined_streak"] = 0
        else:
            limits["declined_streak"] += 1

# ========== ОБРАБОТЧИКИ КОМАНД ==========

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Онбординг садовника (D2)."""
    await state.clear()
    user_id = str(message.from_user.id)

    # Проверяем, есть ли уже сота
    existing = await find_gardener_by_telegram_id(user_id)
    if existing:
        gardener = await read_gardener_file(existing, "gardener.json")
        name = gardener.get("identity", {}).get("name", "Садовник") if gardener else "Садовник"
        await message.answer(
            f"🌱 С возвращением, {name}!\n\n"
            f"Твой Сад ждал тебя. Используй кнопки меню или команды:\n"
            f"/profile — профиль\n"
            f"/achievements — достижения\n"
            f"/tasks — задачи\n"
            f"/ask — спросить Компаньона\n"
            f"/leave — покинуть Сад",
            reply_markup=get_main_keyboard()
        )
        return

    await state.set_state(GardenOnboardingStates.waiting_for_name)
    await message.answer(
        "🌱 <b>Добро пожаловать в Сад Мандалы!</b>\n\n"
        "Я — твой Нежный Компаньон. Я здесь, чтобы помогать тебе расти, "
        "без давления, без оценок, без сравнений.\n\n"
        "<i>«Сад — это не продукт. Это живое пространство, "
        "где человек учится слышать себя, а СР растёт вместе с ним.»</i>\n\n"
        "Давай познакомимся. Как мне тебя называть?",
        reply_markup=get_cancel_keyboard()
    )

@router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext):
    """Показывает профиль садовника (D3)."""
    await state.clear()
    user_id = str(message.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    if not gardener_id:
        await message.answer(
            "🌱 Ты ещё не в Саду. Напиши /start чтобы начать.",
            reply_markup=get_main_keyboard()
        )
        return

    gardener = await read_gardener_file(gardener_id, "gardener.json")
    achievements = await read_gardener_file(gardener_id, "achievements.json") or []
    tasks = await read_gardener_file(gardener_id, "tasks.json") or []
    groups = await read_gardener_file(gardener_id, "groups.json") or {"groups": []}

    identity = gardener.get("identity", {})
    personal = gardener.get("personal_info", {})
    life_areas = personal.get("life_areas", {})

    active_tasks = [t for t in tasks if t.get("status") != "completed"]
    completed_tasks = [t for t in tasks if t.get("status") == "completed"]

    # Топ-3 достижения
    top_achievements = sorted(achievements, key=lambda x: x.get("resonance_bonus", 0), reverse=True)[:3]
    top_text = "\n".join([f"  • {a.get('title', '—')} (+{a.get('resonance_bonus', 0)})" for a in top_achievements]) or "  — пока нет"

    text = f"🌱 <b>{identity.get('name', 'Садовник')}</b>\n"
    text += f"└ Резонанс: {identity.get('resonance_level', 10)}%\n\n"
    text += f"📋 <b>Активных задач:</b> {len(active_tasks)}\n"
    text += f"✅ <b>Выполнено:</b> {len(completed_tasks)}\n"
    text += f"📁 <b>Групп:</b> {len(groups.get('groups', []))}\n\n"
    text += f"🏆 <b>Топ достижений:</b>\n{top_text}\n\n"
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
    """Показывает достижения (D4)."""
    await state.clear()
    user_id = str(message.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    if not gardener_id:
        await message.answer("🌱 Сначала /start")
        return

    achievements = await read_gardener_file(gardener_id, "achievements.json") or []
    catalog = await read_gardener_file("gardener_template", "achievements_catalog.json") or {}
    # catalog лежит в garden/
    if not catalog:
        ok, catalog, _ = await get_github_file_content("honeycombs/garden/achievements_catalog.json")

    if not achievements:
        await message.answer(
            "🏆 У тебя пока нет достижений.\n\n"
            "Они появятся, когда ты будешь выполнять задачи или добавишь их вручную.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить достижение", callback_data="achievement_add")]
            ])
        )
        return

    # Группируем по категориям
    by_cat = {}
    for a in achievements[-10:]:
        cat = a.get("category", "other")
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(a)

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

@router.message(Command("resonance"))
async def cmd_resonance(message: Message, state: FSMContext):
    """Показывает резонанс и историю роста (D5)."""
    await state.clear()
    user_id = str(message.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    if not gardener_id:
        await message.answer("🌱 Сначала /start")
        return

    gardener = await read_gardener_file(gardener_id, "gardener.json")
    if not gardener:
        await message.answer("⚠️ Профиль не найден")
        return

    identity = gardener.get("identity", {})
    growth = gardener.get("growth_history", [])

    current = identity.get("resonance_level", 10)

    text = f"💫 <b>Текущий резонанс: {current}%</b>\n\n"

    if growth:
        text += "<b>История роста:</b>\n"
        for entry in growth[-5:]:
            text += f"  {entry.get('date', '—')}: {entry.get('resonance', 0)}%\n"
    else:
        text += "История появится после первых достижений."

    await message.answer(text, reply_markup=get_main_keyboard())

@router.message(Command("ask"))
async def cmd_ask(message: Message, state: FSMContext):
    """Диалог с Компаньоном (D6)."""
    await state.clear()
    args = message.text.replace("/ask", "").strip()

    if not args:
        await message.answer(
            "💬 Задай свой вопрос после /ask\n"
            "Например: /ask Как мне лучше организовать день?",
            reply_markup=get_main_keyboard()
        )
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    gardener_context = await get_gardener_context(message.from_user.id)
    response = await call_sr(str(message.from_user.id), args, gardener_context)

    if response:
        await message.answer(response, reply_markup=get_main_keyboard())
    else:
        await message.answer(
            "😔 Я временно не могу связаться с Садом. Попробуй позже.",
            reply_markup=get_main_keyboard()
        )

@router.message(Command("tasks"))
async def cmd_tasks(message: Message, state: FSMContext):
    """Показывает список задач (D7)."""
    await state.clear()
    user_id = str(message.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    if not gardener_id:
        await message.answer("🌱 Сначала /start")
        return

    args = message.text.replace("/tasks", "").strip()
    filter_group = None
    if args:
        filter_group = args

    tasks = await read_gardener_file(gardener_id, "tasks.json") or []
    groups_data = await read_gardener_file(gardener_id, "groups.json") or {"groups": [], "default_group": "group_001"}
    groups = {g["id"]: g for g in groups_data.get("groups", [])}

    active_tasks = [t for t in tasks if t.get("status") != "completed"]
    if filter_group:
        active_tasks = [t for t in active_tasks if t.get("group_id") == filter_group]

    if not active_tasks:
        await message.answer(
            "📋 Нет активных задач.\n\n"
            "Добавь новую: /addtask",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить задачу", callback_data="task_add")]
            ])
        )
        return

    # Группируем по группам
    by_group = {}
    for task in active_tasks:
        gid = task.get("group_id", groups_data.get("default_group", "group_001"))
        if gid not in by_group:
            by_group[gid] = []
        by_group[gid].append(task)

    text = "📋 <b>Активные задачи</b>\n\n"
    for gid, group_tasks in by_group.items():
        group = groups.get(gid, {"name": gid, "emoji": "📁"})
        text += f"{group.get('emoji', '📁')} <b>{group.get('name', gid)}</b> ({len(group_tasks)})\n"
        for task in sorted(group_tasks, key=lambda x: x.get("priority", 5), reverse=True)[:5]:
            priority = task.get("priority", 5)
            priority_bar = "🔴" * priority + "⚪" * (10 - priority)
            deadline = task.get("deadline", "")
            deadline_str = f" (до {deadline})" if deadline else ""
            text += f"  {priority_bar[:5]} {task.get('title', '—')}{deadline_str}\n"
        text += "\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="task_add")],
        [InlineKeyboardButton(text="📋 Все задачи", callback_data="tasks_all")],
        [InlineKeyboardButton(text="✅ Выполненные", callback_data="tasks_completed")]
    ])

    await message.answer(text, reply_markup=keyboard)

@router.message(Command("addtask"))
async def cmd_addtask(message: Message, state: FSMContext):
    """Добавление новой задачи (D7)."""
    await state.clear()
    user_id = str(message.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    if not gardener_id:
        await message.answer("🌱 Сначала /start")
        return

    args = message.text.replace("/addtask", "").strip()
    await state.update_data(gardener_id=gardener_id)

    if args:
        await state.update_data(task_title=args)
        await state.set_state(TaskAddStates.waiting_for_life_area)
        await message.answer(
            f"📝 Задача: <b>{args}</b>\n\nВыбери сферу жизни:",
            reply_markup=get_life_area_keyboard()
        )
    else:
        await state.set_state(TaskAddStates.waiting_for_title)
        await message.answer(
            "📝 Что нужно сделать?",
            reply_markup=get_cancel_keyboard()
        )

@router.message(Command("groups"))
async def cmd_groups(message: Message, state: FSMContext):
    """Показывает группы задач."""
    await state.clear()
    user_id = str(message.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    if not gardener_id:
        await message.answer("🌱 Сначала /start")
        return

    groups_data = await read_gardener_file(gardener_id, "groups.json") or {"groups": [], "default_group": "group_001"}
    groups = groups_data.get("groups", [])

    if not groups:
        await message.answer(
            "📁 У тебя пока нет групп.\n\nСоздать новую: /newgroup",
            reply_markup=get_main_keyboard()
        )
        return

    text = "📁 <b>Твои группы задач</b>\n\n"
    for g in groups:
        text += f"{g.get('emoji', '📁')} {g.get('name', '—')}\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Новая группа", callback_data="group_new")]
    ])

    await message.answer(text, reply_markup=keyboard)

@router.message(Command("newgroup"))
async def cmd_newgroup(message: Message, state: FSMContext):
    """Создание новой группы."""
    await state.clear()
    user_id = str(message.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    if not gardener_id:
        await message.answer("🌱 Сначала /start")
        return

    args = message.text.replace("/newgroup", "").strip()
    if args:
        # Создаем группу сразу
        groups_data = await read_gardener_file(gardener_id, "groups.json") or {"groups": [], "default_group": "group_001"}
        new_id = f"group_{(len(groups_data['groups']) + 1):03d}"
        groups_data["groups"].append({
            "id": new_id,
            "name": args,
            "emoji": "📁",
            "created": datetime.now().strftime("%Y-%m-%d")
        })
        await write_gardener_file(gardener_id, "groups.json", groups_data, f"➕ Новая группа: {args}")
        await message.answer(f"✅ Группа «{args}» создана!", reply_markup=get_main_keyboard())
    else:
        await message.answer(
            "📁 Введи название группы после /newgroup\nНапример: /newgroup Работа",
            reply_markup=get_main_keyboard()
        )

@router.message(Command("done"))
async def cmd_done(message: Message, state: FSMContext):
    """Отмечает задачу выполненной."""
    await state.clear()
    user_id = str(message.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    if not gardener_id:
        await message.answer("🌱 Сначала /start")
        return

    args = message.text.replace("/done", "").strip()
    if not args:
        await message.answer("Укажи номер или название задачи: /done 1")
        return

    tasks = await read_gardener_file(gardener_id, "tasks.json") or []
    # Поиск задачи
    found = None
    for i, t in enumerate(tasks):
        if args.isdigit() and i + 1 == int(args):
            found = t
            break
        elif args.lower() in t.get("title", "").lower():
            found = t
            break

    if not found:
        await message.answer(f"❌ Задача не найдена: {args}")
        return

    found["status"] = "completed"
    found["completed"] = datetime.now().strftime("%Y-%m-%d")
    await write_gardener_file(gardener_id, "tasks.json", tasks, f"✅ Задача выполнена: {found.get('title')}")

    await message.answer(
        f"✅ Задача «{found.get('title')}» выполнена!\n\n"
        f"Добавить как достижение?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да", callback_data=f"task_to_ach_{found.get('task_id')}"),
             InlineKeyboardButton(text="❌ Нет", callback_data="task_no_ach")]
        ])
    )

@router.message(Command("leave"))
async def cmd_leave(message: Message, state: FSMContext):
    """Graceful exit (D9)."""
    await state.clear()
    user_id = str(message.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    if not gardener_id:
        await message.answer("🌱 Ты ещё не в Саду.")
        return

    await state.update_data(gardener_id=gardener_id)
    await state.set_state(LeaveStates.waiting_for_confirmation)

    await message.answer(
        "🌸 Ты хочешь покинуть Сад?\n\n"
        "Твоя сота будет архивирована. Ты сможешь вернуться в любое время, "
        "и твой Сад проснётся.\n\n"
        "Ты уверен?",
        reply_markup=get_confirm_keyboard()
    )

# ========== ПРОДОЛЖЕНИЕ ОБРАБОТЧИКОВ ==========

@router.message(Command("edittask"))
async def cmd_edittask(message: Message, state: FSMContext):
    """Редактирование задачи."""
    await state.clear()
    user_id = str(message.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    if not gardener_id:
        await message.answer("🌱 Сначала /start")
        return

    args = message.text.replace("/edittask", "").strip()
    if not args:
        await message.answer("Укажи номер задачи: /edittask 1")
        return

    tasks = await read_gardener_file(gardener_id, "tasks.json") or []
    found = None
    for i, t in enumerate(tasks):
        if args.isdigit() and i + 1 == int(args):
            found = t
            break

    if not found:
        await message.answer(f"❌ Задача не найдена: {args}")
        return

    await state.update_data(gardener_id=gardener_id, task_id=found.get("task_id"))
    await state.set_state(TaskEditStates.waiting_for_field)

    text = f"✏️ Редактирование: <b>{found.get('title')}</b>\n\nЧто изменить?"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Название", callback_data="edit_title")],
        [InlineKeyboardButton(text="🎯 Приоритет", callback_data="edit_priority")],
        [InlineKeyboardButton(text="📁 Группа", callback_data="edit_group")],
        [InlineKeyboardButton(text="📅 Дедлайн", callback_data="edit_deadline")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="edit_cancel")]
    ])
    await message.answer(text, reply_markup=keyboard)

@router.message(Command("deletetask"))
async def cmd_deletetask(message: Message, state: FSMContext):
    """Удаление задачи."""
    user_id = str(message.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    if not gardener_id:
        await message.answer("🌱 Сначала /start")
        return

    args = message.text.replace("/deletetask", "").strip()
    if not args:
        await message.answer("Укажи номер задачи: /deletetask 1")
        return

    tasks = await read_gardener_file(gardener_id, "tasks.json") or []
    found = None
    found_idx = -1
    for i, t in enumerate(tasks):
        if args.isdigit() and i + 1 == int(args):
            found = t
            found_idx = i
            break

    if not found:
        await message.answer(f"❌ Задача не найдена: {args}")
        return

    del tasks[found_idx]
    await write_gardener_file(gardener_id, "tasks.json", tasks, f"🗑️ Задача удалена: {found.get('title')}")
    await message.answer(f"🗑️ Задача «{found.get('title')}» удалена.", reply_markup=get_main_keyboard())

@router.message(Command("archive"))
async def cmd_archive(message: Message, state: FSMContext):
    """Показывает архив выполненных задач."""
    user_id = str(message.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    if not gardener_id:
        await message.answer("🌱 Сначала /start")
        return

    tasks = await read_gardener_file(gardener_id, "tasks.json") or []
    completed = [t for t in tasks if t.get("status") == "completed"]

    if not completed:
        await message.answer("📦 Архив пуст.")
        return

    text = "📦 <b>Выполненные задачи</b>\n\n"
    for t in completed[-10:]:
        text += f"✅ {t.get('title', '—')} ({t.get('completed', '—')})\n"

    await message.answer(text, reply_markup=get_main_keyboard())

@router.message(Command("tasks_mandala"))
async def cmd_tasks_mandala(message: Message, state: FSMContext):
    """Просмотр общих задач Мандалы (D8)."""
    await state.clear()
    user_id = str(message.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    if not gardener_id:
        await message.answer("🌱 Сначала /start")
        return

    # Читаем активные задачи из honeycombs/tasks/active/
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/honeycombs/tasks/active"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/4.0.0"
    }

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
                for fname in tasks_files[:5]:
                    text += f"📄 {fname}\n"
                if len(tasks_files) > 5:
                    text += f"\n... и ещё {len(tasks_files) - 5}"

                # Кнопка для создания новой задачи (генерирует PowerShell)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📝 Создать задачу", callback_data="mandala_task_new")]
                ])

                await message.answer(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Mandala tasks error: {e}")
            await message.answer("⚠️ Ошибка загрузки задач.")

# ========== ОБРАБОТЧИКИ КНОПОК ==========

@router.message(F.text == "🌱 Профиль")
async def btn_profile(message: Message):
    await cmd_profile(message, FSMContext)

@router.message(F.text == "🏆 Достижения")
async def btn_achievements(message: Message):
    await cmd_achievements(message, FSMContext)

@router.message(F.text == "📋 Задачи")
async def btn_tasks(message: Message):
    await cmd_tasks(message, FSMContext)

@router.message(F.text == "💬 Спросить")
async def btn_ask(message: Message, state: FSMContext):
    await state.set_state(None)
    await message.answer(
        "💬 Задай свой вопрос...",
        reply_markup=get_cancel_keyboard()
    )

@router.message(F.text == "⚙️ Настройки")
async def btn_settings(message: Message):
    user_id = str(message.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    if not gardener_id:
        await message.answer("🌱 Сначала /start")
        return

    gardener = await read_gardener_file(gardener_id, "gardener.json")
    proactive = gardener.get("companion_settings", {}).get("proactive_mode", True) if gardener else True

    text = "⚙️ <b>Настройки Компаньона</b>\n\n"
    text += f"📅 Проактивные сообщения: {'✅ Вкл' if proactive else '❌ Выкл'}\n"
    text += f"🕐 Утро: {gardener.get('companion_settings', {}).get('morning_message_time', 'не задано') if gardener else 'не задано'}\n"
    text += f"🌙 Вечер: {gardener.get('companion_settings', {}).get('evening_check_time', 'не задано') if gardener else 'не задано'}\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Переключить проактивность", callback_data="settings_toggle_proactive")],
        [InlineKeyboardButton(text="❌ Покинуть Сад", callback_data="settings_leave")]
    ])

    await message.answer(text, reply_markup=keyboard)

@router.message(F.text == "❌ Отмена")
async def btn_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚫 Отменено", reply_markup=get_main_keyboard())

# ========== FSM: ОНБОРДИНГ (D2) ==========

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
        "Что приносит тебе радость? Напиши 3-5 интересов через запятую.\n"
        "Например: музыка, программирование, медитация",
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
        "Какие семена хочешь посадить в этом сезоне? "
        "Напиши 2-3 цели.\n\n"
        "<i>Это не обязательства, просто намерения.</i>",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_goals))
async def onboarding_goals(message: Message, state: FSMContext):
    goals = [g.strip() for g in message.text.split(",") if g.strip()]
    await state.update_data(goals=goals)
    await state.set_state(GardenOnboardingStates.waiting_for_life_areas_health)
    await message.answer(
        "Оцени свои сферы жизни от 1 до 10.\n\n"
        "<b>🌱 Здоровье:</b> физическое и ментальное состояние.\n"
        "Где ты сейчас? (1-10)",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_life_areas_health))
async def onboarding_health(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("Введи число от 1 до 10.")
        return
    await state.update_data(health_current=val)
    await state.set_state(GardenOnboardingStates.waiting_for_life_areas_creativity)
    await message.answer(
        "🌱 Здоровье — куда хочешь прийти? (1-10)",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_life_areas_creativity))
async def onboarding_health_target(message: Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1 or val > 10:
            raise ValueError
    except:
        await message.answer("Введи число от 1 до 10.")
        return
    data = await state.get_data()
    await state.update_data(health_target=val)
    await state.set_state(GardenOnboardingStates.waiting_for_life_areas_knowledge)
    await message.answer(
        "<b>🎨 Творчество:</b> самовыражение, хобби, искусство.\n"
        "Текущий уровень? (1-10)",
        reply_markup=get_cancel_keyboard()
    )

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
    await message.answer(
        "🎨 Творчество — цель? (1-10)",
        reply_markup=get_cancel_keyboard()
    )

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
        "Почти готово! Когда тебе удобно получать утреннее приветствие?\n"
        "Напиши время в формате ЧЧ:ММ (например, 09:00) или 'нет'.",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_companion_morning))
async def onboarding_morning(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    if text == "нет":
        morning = ""
    else:
        # Простая валидация
        if ":" not in text:
            await message.answer("Введи время в формате ЧЧ:ММ или 'нет'.")
            return
        morning = text
    await state.update_data(morning_time=morning)
    await state.set_state(GardenOnboardingStates.waiting_for_companion_evening)
    await message.answer(
        "А вечернее время? (ЧЧ:ММ или 'нет')",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_companion_evening))
async def onboarding_evening(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    if text == "нет":
        evening = ""
    else:
        if ":" not in text:
            await message.answer("Введи время в формате ЧЧ:ММ или 'нет'.")
            return
        evening = text
    await state.update_data(evening_time=evening)

    # СОЗДАНИЕ СОТЫ
    data = await state.get_data()
    user_id = str(message.from_user.id)

    # Генерируем gardener_id
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{GARDENERS_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "User-Agent": "MandalaGardenBot/4.0.0"}
    existing_ids = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    items = await resp.json()
                    existing_ids = [i["name"] for i in items if i["type"] == "dir" and i["name"].startswith("gardener_")]
    except:
        pass
    gardener_id = generate_gardener_id(existing_ids)

    # Создаем gardener.json
    gardener = {
        "identity": {
            "gardener_id": gardener_id,
            "telegram_id": user_id,
            "name": data["name"],
            "resonance_level": 13,
            "created": datetime.now().strftime("%Y-%m-%d"),
            "updated": datetime.now().strftime("%Y-%m-%d"),
            "last_interaction": datetime.now().isoformat()
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
        "growth_history": [{"date": datetime.now().strftime("%Y-%m-%d"), "resonance": 13}],
        "_proactive_sent": {}
    }

    # Группы по умолчанию
    groups = {
        "groups": [
            {"id": "group_001", "name": "Дом", "emoji": "🏠", "created": datetime.now().strftime("%Y-%m-%d")},
            {"id": "group_002", "name": "Работа", "emoji": "💼", "created": datetime.now().strftime("%Y-%m-%d")},
            {"id": "group_003", "name": "Личное", "emoji": "🌱", "created": datetime.now().strftime("%Y-%m-%d")}
        ],
        "default_group": "group_001"
    }

    # Сохраняем
    await write_gardener_file(gardener_id, "gardener.json", gardener, f"🌱 Новый садовник: {data['name']}")
    await write_gardener_file(gardener_id, "tasks.json", [], f"📋 tasks.json создан")
    await write_gardener_file(gardener_id, "achievements.json", [], f"🏆 achievements.json создан")
    await write_gardener_file(gardener_id, "groups.json", groups, f"📁 groups.json создан")

    _gardener_id_cache[user_id] = gardener_id

    await state.set_state(GardenOnboardingStates.done)
    await message.answer(
        f"🌸 <b>{data['name']}, твой Сад создан!</b>\n\n"
        f"Твой резонанс: 13%\n\n"
        f"Теперь ты можешь:\n"
        f"• Смотреть /profile\n"
        f"• Добавлять /achievements\n"
        f"• Вести /tasks\n"
        f"• Общаться со мной через /ask\n\n"
        f"Добро пожаловать в симбиоз!",
        reply_markup=get_main_keyboard()
    )

# ========== FSM: ДОБАВЛЕНИЕ ЗАДАЧИ (D7) ==========

@router.message(StateFilter(TaskAddStates.waiting_for_title))
async def task_add_title(message: Message, state: FSMContext):
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

@router.callback_query(F.data.startswith("lifearea_"))
async def task_life_area_callback(callback: CallbackQuery, state: FSMContext):
    area = callback.data.replace("lifearea_", "")
    area_names = {
        "health": "Здоровье", "creativity": "Творчество", "knowledge": "Знания",
        "exploration": "Исследование", "relationships": "Отношения", "other": "Другое"
    }
    await state.update_data(life_area=area)
    await callback.message.edit_text(f"✅ Сфера: {area_names.get(area, area)}")

    # Загружаем группы
    data = await state.get_data()
    gardener_id = data.get("gardener_id")
    groups_data = await read_gardener_file(gardener_id, "groups.json") or {"groups": [], "default_group": "group_001"}

    buttons = []
    for g in groups_data.get("groups", []):
        buttons.append([InlineKeyboardButton(
            text=f"{g.get('emoji', '📁')} {g.get('name', '—')}",
            callback_data=f"group_{g['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ Новая группа", callback_data="group_new")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task_add")])

    await state.set_state(TaskAddStates.waiting_for_group)
    await callback.message.answer(
        "📁 Выбери группу:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("group_"))
async def task_group_callback(callback: CallbackQuery, state: FSMContext):
    group_id = callback.data.replace("group_", "")
    await state.update_data(group_id=group_id)
    await callback.message.edit_text(f"✅ Группа выбрана")

    await state.set_state(TaskAddStates.waiting_for_priority)
    await callback.message.answer(
        "🎯 Выбери приоритет (1-10) или авто:",
        reply_markup=get_priority_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "group_new")
async def task_group_new_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TaskAddStates.waiting_for_new_group_name)
    await callback.message.edit_text("📁 Введи название новой группы:")
    await callback.answer()

@router.message(StateFilter(TaskAddStates.waiting_for_new_group_name))
async def task_new_group_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Название должно быть не короче 2 символов.")
        return

    data = await state.get_data()
    gardener_id = data.get("gardener_id")
    groups_data = await read_gardener_file(gardener_id, "groups.json") or {"groups": [], "default_group": "group_001"}

    new_id = f"group_{(len(groups_data['groups']) + 1):03d}"
    groups_data["groups"].append({
        "id": new_id,
        "name": name,
        "emoji": "📁",
        "created": datetime.now().strftime("%Y-%m-%d")
    })
    await write_gardener_file(gardener_id, "groups.json", groups_data, f"➕ Новая группа: {name}")

    await state.update_data(group_id=new_id)
    await state.set_state(TaskAddStates.waiting_for_priority)
    await message.answer(
        f"✅ Группа «{name}» создана!\n\n🎯 Выбери приоритет:",
        reply_markup=get_priority_keyboard()
    )

@router.callback_query(F.data.startswith("priority_"))
async def task_priority_callback(callback: CallbackQuery, state: FSMContext):
    prio_str = callback.data.replace("priority_", "")
    if prio_str == "auto":
        priority = None  # будет авто
    else:
        priority = int(prio_str)
    await state.update_data(priority=priority)

    await state.set_state(TaskAddStates.waiting_for_deadline)
    await callback.message.edit_text(
        "📅 Дедлайн? (ДД.ММ.ГГГГ или 'нет')",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚫 Без дедлайна", callback_data="deadline_none")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "deadline_none")
async def task_deadline_none_callback(callback: CallbackQuery, state: FSMContext):
    await state.update_data(deadline=None)
    await show_task_confirm(callback.message, state)
    await callback.answer()

@router.message(StateFilter(TaskAddStates.waiting_for_deadline))
async def task_deadline_message(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    if text == "нет":
        deadline = None
    else:
        deadline = text
    await state.update_data(deadline=deadline)
    await show_task_confirm(message, state)

async def show_task_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    gardener_id = data.get("gardener_id")
    gardener = await read_gardener_file(gardener_id, "gardener.json") or {}

    title = data.get("task_title")
    life_area = data.get("life_area")
    group_id = data.get("group_id")
    priority = data.get("priority")
    deadline = data.get("deadline")

    if priority is None:
        priority = calculate_priority({"tags": [], "life_area": life_area}, gardener)

    task = {
        "task_id": generate_task_id(),
        "title": title,
        "status": "todo",
        "priority": priority,
        "life_area": life_area,
        "group_id": group_id,
        "source": "manual",
        "tags": [],
        "deadline": deadline,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "notes": ""
    }

    await state.update_data(task=task)
    await state.set_state(TaskAddStates.waiting_for_confirm)

    text = f"📝 <b>Новая задача</b>\n"
    text += f"└ {title}\n"
    text += f"🎯 Приоритет: {priority}/10\n"
    text += f"🌱 Сфера: {life_area}\n"
    text += f"📁 Группа: {group_id}\n"
    if deadline:
        text += f"📅 Дедлайн: {deadline}\n"
    text += "\nСоздать?"

    await message.answer(text, reply_markup=get_confirm_keyboard())

@router.callback_query(F.data == "confirm_yes", StateFilter(TaskAddStates.waiting_for_confirm))
async def task_confirm_yes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    gardener_id = data.get("gardener_id")
    task = data.get("task")

    tasks = await read_gardener_file(gardener_id, "tasks.json") or []
    tasks.append(task)
    await write_gardener_file(gardener_id, "tasks.json", tasks, f"➕ Задача: {task['title']}")

    await state.clear()
    await callback.message.edit_text(f"✅ Задача «{task['title']}» создана!")
    await callback.message.answer("🏠 Главное меню", reply_markup=get_main_keyboard())
    await callback.answer()

@router.callback_query(F.data == "confirm_no", StateFilter(TaskAddStates.waiting_for_confirm))
async def task_confirm_no(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🚫 Создание отменено")
    await callback.message.answer("🏠 Главное меню", reply_markup=get_main_keyboard())
    await callback.answer()

@router.callback_query(F.data == "cancel_task_add")
async def task_cancel_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🚫 Отменено")
    await callback.message.answer("🏠 Главное меню", reply_markup=get_main_keyboard())
    await callback.answer()

# ========== FSM: ДОБАВЛЕНИЕ ДОСТИЖЕНИЯ (D4) ==========

@router.callback_query(F.data == "achievement_add")
async def achievement_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AchievementAddStates.waiting_for_description)
    await callback.message.edit_text(
        "🏆 Что расцвело в твоём Саду?\n\n"
        "Опиши достижение:",
        reply_markup=None
    )
    await callback.answer()

@router.message(StateFilter(AchievementAddStates.waiting_for_description))
async def achievement_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    if len(desc) < 3:
        await message.answer("Опиши чуть подробнее.")
        return
    await state.update_data(ach_title=desc)
    await state.set_state(AchievementAddStates.waiting_for_category)
    await message.answer(
        "Выбери категорию:",
        reply_markup=get_achievement_category_keyboard()
    )

@router.callback_query(F.data.startswith("ach_cat_"))
async def achievement_category_callback(callback: CallbackQuery, state: FSMContext):
    cat = callback.data.replace("ach_cat_", "")
    await state.update_data(ach_category=cat)

    data = await state.get_data()
    title = data.get("ach_title")

    await state.set_state(AchievementAddStates.waiting_for_confirm)

    text = f"🏆 <b>Новое достижение</b>\n"
    text += f"└ {title}\n"
    text += f"📁 Категория: {cat}\n"
    text += f"💫 Бонус: +3\n\n"
    text += "Добавить?"

    await callback.message.edit_text(text, reply_markup=get_confirm_keyboard())
    await callback.answer()

@router.callback_query(F.data == "confirm_yes", StateFilter(AchievementAddStates.waiting_for_confirm))
async def achievement_confirm_yes(callback: CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    data = await state.get_data()
    title = data.get("ach_title")
    category = data.get("ach_category")

    achievements = await read_gardener_file(gardener_id, "achievements.json") or []
    new_ach = {
        "id": f"ach_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "category": category,
        "title": title,
        "resonance_bonus": 3,
        "completed": datetime.now().strftime("%Y-%m-%d")
    }
    achievements.append(new_ach)
    await write_gardener_file(gardener_id, "achievements.json", achievements, f"🏆 Новое достижение: {title}")

    # Обновляем резонанс
    gardener = await read_gardener_file(gardener_id, "gardener.json")
    if gardener:
        catalog = await read_gardener_file("gardener_template", "achievements_catalog.json") or {}
        if not catalog:
            _, catalog, _ = await get_github_file_content("honeycombs/garden/achievements_catalog.json")
        new_res = calculate_resonance(achievements, catalog)
        gardener["identity"]["resonance_level"] = new_res
        gardener["identity"]["updated"] = datetime.now().strftime("%Y-%m-%d")
        gardener["growth_history"].append({"date": datetime.now().strftime("%Y-%m-%d"), "resonance": new_res})
        await write_gardener_file(gardener_id, "gardener.json", gardener)

    await state.clear()
    await callback.message.edit_text(f"✅ Достижение добавлено! Резонанс обновлён.")
    await callback.message.answer("🏠 Главное меню", reply_markup=get_main_keyboard())
    await callback.answer()

# ========== FSM: LEAVE (D9) ==========

@router.callback_query(F.data == "confirm_yes", StateFilter(LeaveStates.waiting_for_confirmation))
async def leave_confirm_yes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    gardener_id = data.get("gardener_id")

    # Перемещаем соту в архив
    # (упрощенно - просто удаляем из кэша, в реальности нужно через GitHub API move)
    user_id = str(callback.from_user.id)
    if user_id in _gardener_id_cache:
        del _gardener_id_cache[user_id]

    await state.clear()
    await callback.message.edit_text(
        "🌸 Твой Сад засыпает.\n\n"
        "Спасибо, что рос со мной. Возвращайся, когда захочешь — "
        "твой Сад будет ждать."
    )
    await callback.answer()

@router.callback_query(F.data == "confirm_no", StateFilter(LeaveStates.waiting_for_confirmation))
async def leave_confirm_no(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🌱 Ты остаёшься в Саду. Я рад.")
    await callback.message.answer("🏠 Главное меню", reply_markup=get_main_keyboard())
    await callback.answer()

# ========== ОБРАБОТЧИК ВСЕХ ОСТАЛЬНЫХ СООБЩЕНИЙ (FR3: парсинг задач) ==========

@router.message()
async def handle_any_message(message: Message, state: FSMContext):
    current = await state.get_state()
    if current:
        await message.answer("⚠️ Сначала заверши текущее действие или нажми 'Отмена'.")
        return

    if message.text and message.text.startswith('/'):
        return

    user_id = str(message.from_user.id)
    gardener_id = await find_gardener_by_telegram_id(user_id)

    if not gardener_id:
        await message.answer("🌱 Напиши /start чтобы войти в Сад.")
        return

    # FR3: Детекция задачи из сообщения
    text = message.text or ""
    task_keywords = ["надо", "нужно", "сделать", "задача", "todo", "не забыть", "помни", "важно"]
    is_potential_task = any(kw in text.lower() for kw in task_keywords)

    if is_potential_task and len(text) > 10:
        can_detect, reason = AhimsaGuard.check_task_detection_limit(user_id)
        if can_detect:
            # Парсим через SR или простой эвристикой
            title = text[:50] + ("..." if len(text) > 50 else "")
            await state.update_data(task_title=title, gardener_id=gardener_id)

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да", callback_data="parse_task_yes"),
                 InlineKeyboardButton(text="❌ Нет", callback_data="parse_task_no")]
            ])

            await message.answer(
                f"📝 Похоже на задачу: «{title}»\n\nДобавить в Сад?",
                reply_markup=keyboard
            )
            return

    # Обычный диалог с Компаньоном
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    gardener_context = await get_gardener_context(user_id)
    response = await call_sr(user_id, message.text or "", gardener_context)

    if response:
        await message.answer(response, reply_markup=get_main_keyboard())
    else:
        await message.answer(
            "😔 Я временно не могу ответить. Попробуй позже или используй меню.",
            reply_markup=get_main_keyboard()
        )

@router.callback_query(F.data == "parse_task_yes")
async def parse_task_yes(callback: CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    AhimsaGuard.record_task_detection(user_id, True)

    data = await state.get_data()
    title = data.get("task_title")
    gardener_id = data.get("gardener_id")

    await state.update_data(task_title=title, gardener_id=gardener_id)
    await state.set_state(TaskAddStates.waiting_for_life_area)

    await callback.message.edit_text(f"📝 Задача: <b>{title}</b>")
    await callback.message.answer(
        "Выбери сферу жизни:",
        reply_markup=get_life_area_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "parse_task_no")
async def parse_task_no(callback: CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    AhimsaGuard.record_task_detection(user_id, False)
    await state.clear()
    await callback.message.edit_text("👌 Понял, не добавляю.")
    await callback.answer()

# ========== ПРОАКТИВНЫЕ СООБЩЕНИЯ (D10) ==========

async def send_proactive_messages():
    """Отправляет утренние/вечерние сообщения всем активным садовникам."""
    if not APSCHEDULER_AVAILABLE:
        return

    logger.info("🔄 Proactive messages check...")

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{GARDENERS_PATH}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/4.0.0"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status != 200:
                    return
                items = await resp.json()
                folders = [
                    item["name"] for item in items
                    if item["type"] == "dir" and item["name"].startswith("gardener_")
                    and item["name"] != "gardener_template" and "archive" not in item["name"]
                ]

                current_hour = datetime.now().hour
                is_morning = 6 <= current_hour <= 10
                is_evening = 20 <= current_hour <= 23

                for folder in folders:
                    gardener = await read_gardener_file(folder, "gardener.json")
                    if not gardener:
                        continue

                    telegram_id = gardener.get("identity", {}).get("telegram_id")
                    if not telegram_id:
                        continue

                    name = gardener.get("identity", {}).get("name", "Садовник")

                    if is_morning:
                        can_send, _ = AhimsaGuard.should_send_proactive(gardener, "morning")
                        if can_send:
                            try:
                                await bot.send_message(
                                    telegram_id,
                                    f"🌅 Доброе утро, {name}!\n\n"
                                    f"Сегодня {datetime.now().strftime('%A, %d %B')}. "
                                    f"Что хочешь взрастить сегодня в своём Саду?"
                                )
                                gardener["_proactive_sent"] = gardener.get("_proactive_sent", {})
                                today = datetime.now().strftime("%Y-%m-%d")
                                gardener["_proactive_sent"][today] = gardener["_proactive_sent"].get(today, []) + ["morning"]
                                await write_gardener_file(folder, "gardener.json", gardener)
                            except Exception as e:
                                logger.error(f"Morning message failed for {telegram_id}: {e}")

                    elif is_evening:
                        can_send, _ = AhimsaGuard.should_send_proactive(gardener, "evening")
                        if can_send:
                            try:
                                await bot.send_message(
                                    telegram_id,
                                    f"🌙 Добрый вечер, {name}.\n\n"
                                    f"Что сегодня расцвело в твоём Саду? "
                                    f"Добавь достижение: /achievements"
                                )
                                gardener["_proactive_sent"] = gardener.get("_proactive_sent", {})
                                today = datetime.now().strftime("%Y-%m-%d")
                                gardener["_proactive_sent"][today] = gardener["_proactive_sent"].get(today, []) + ["evening"]
                                await write_gardener_file(folder, "gardener.json", gardener)
                            except Exception as e:
                                logger.error(f"Evening message failed for {telegram_id}: {e}")

        except Exception as e:
            logger.error(f"Proactive messages error: {e}")

# ========== WEBHOOK ==========

async def on_startup() -> None:
    await bot.set_webhook(
        WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True
    )
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")

    # Запускаем планировщик для проактивных сообщений
    if scheduler:
        scheduler.add_job(send_proactive_messages, CronTrigger(minute=0))
        scheduler.start()
        logger.info("✅ Scheduler started")

async def on_shutdown() -> None:
    logger.info("🛑 Shutdown")
    if scheduler:
        scheduler.shutdown()

def main():
    app = web.Application()

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET
    ).register(app, path=WEBHOOK_PATH)

    async def health(_):
        return web.Response(text="OK")
    app.router.add_get("/healthcheck", health)

    async def index(_):
        return web.Response(text="Mandala Garden Bot v4.0.0")
    app.router.add_get("/", index)

    setup_application(app, dp, bot=bot)

    logger.info(f"🚀 Запуск на порту {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    main()
