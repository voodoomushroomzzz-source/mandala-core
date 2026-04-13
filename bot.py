# Force deploy 
#!/usr/bin/env python3
"""
Mandala Garden Bot — Gentle Companion v5.1.0
Integrated with /bot/ask endpoint. Password protected. Hardcoded to gardener_001.
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
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import aiohttp
from dotenv import load_dotenv

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
BOT_ASK_URL = f"{ENGINEER_CHAT_URL}/bot/ask"

PORT = 10000
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "mandala-secret"

# ========== GARDEN CONSTANTS ==========
GARDENER_ID = "gardener_001"
GARDENER_PATH = f"honeycombs/personal_gardeners/{GARDENER_ID}"

if not BOT_TOKEN or not RENDER_EXTERNAL_URL:
    logger.error("Missing BOT_TOKEN or RENDER_EXTERNAL_URL")
    sys.exit(1)

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ========== GITHUB API ==========
async def get_github_file(file_path: str) -> Tuple[bool, Optional[Any]]:
    if not GITHUB_TOKEN:
        return False, None
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/5.1.0"
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

async def read_gardener() -> Optional[dict]:
    ok, data = await get_github_file(f"{GARDENER_PATH}/gardener.json")
    return data if ok else None

async def write_gardener_file(filename: str, content: Any) -> bool:
    if not GITHUB_TOKEN:
        return False
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{GARDENER_PATH}/{filename}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/5.1.0"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=30) as resp:
                sha = (await resp.json()).get("sha") if resp.status == 200 else None
        except:
            sha = None
        
        content_str = json.dumps(content, ensure_ascii=False, indent=2)
        content_b64 = base64.b64encode(content_str.encode('utf-8')).decode('utf-8')
        payload = {
            "message": f"🌱 bot: update {filename}",
            "content": content_b64,
            "sha": sha
        }
        try:
            async with session.put(url, headers=headers, json=payload, timeout=30) as resp:
                return resp.status in [200, 201]
        except:
            return False

async def is_authorized(telegram_id: str) -> bool:
    gardener = await read_gardener()
    if not gardener:
        return False
    return str(gardener.get("identity", {}).get("telegram_id", "")) == str(telegram_id)

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
            async with session.post(BOT_ASK_URL, json=payload, timeout=60) as resp:
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
        keyboard=[[KeyboardButton(text="🌱 Профиль")]],
        resize_keyboard=True
    )


# ========== FSM: ONBOARDING ==========

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

    # Сохранение в GitHub
    success = await write_gardener_file("gardener.json", gardener)
    if not success:
        await message.answer("⚠️ Ошибка сохранения профиля. Попробуй позже.")
        await state.clear()
        return

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


# ========== COMMANDS ==========
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)
    
    gardener = await read_gardener()
    
    # Файл существует и telegram_id совпадает — приветствуем
    if gardener and str(gardener.get("identity", {}).get("telegram_id", "")) == user_id:
        name = gardener.get("identity", {}).get("name", "Садовник")
        await message.answer(f"🌱 С возвращением, {name}!", reply_markup=get_main_keyboard())
        return
    
    # Файла нет или telegram_id не совпадает — запускаем онбординг
    await state.set_state(GardenOnboardingStates.waiting_for_name)
    await message.answer(
        "🌱 <b>Добро пожаловать в Сад Мандалы!</b>\n\n"
        "Я — твой Нежный Спутник. Давай познакомимся.\n\n"
        "Как мне тебя называть?",
        reply_markup=get_cancel_keyboard()
    )

@router.message(Command("profile"))
async def cmd_profile(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌱 Сначала /start [пароль]")
        return
    
    gardener = await read_gardener()
    if not gardener:
        await message.answer("⚠️ Профиль не найден")
        return
    
    name = gardener.get("identity", {}).get("name", "Садовник")
    resonance = gardener.get("identity", {}).get("resonance_level", 13)
    await message.answer(f"🌱 <b>{name}</b>\n└ Резонанс: {resonance}%")

@router.message(F.text == "🌱 Профиль")
async def btn_profile(message: Message):
    await cmd_profile(message)

# ========== MAIN HANDLER (Gentle SR) ==========
@router.message()
async def handle_gentle_sr(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer("🌱 Сначала /start [пароль]")
        return
    
    user_text = message.text or ""
    if not user_text.strip():
        return
    
    gardener = await read_gardener()
    gardener_context = {
        "gardener_id": GARDENER_ID,
        "name": gardener.get("identity", {}).get("name", ""),
        "resonance_level": gardener.get("identity", {}).get("resonance_level", 13),
        "interests": gardener.get("personal_info", {}).get("interests", []),
        "goals": gardener.get("personal_info", {}).get("goals", [])
    }
    
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    session_id = f"tg_{message.from_user.id}"
    response = await call_bot_ask(session_id, user_text, gardener_context)
    
    if response:
        await message.answer(response, reply_markup=get_main_keyboard())
    else:
        await message.answer("😔 СР временно недоступен. Попробуй позже.", reply_markup=get_main_keyboard())

# ========== WEBHOOK ==========
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL, secret_token=WEBHOOK_SECRET, drop_pending_updates=True)
    logger.info(f"Webhook set: {WEBHOOK_URL}")

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
    app.router.add_get("/", lambda _: web.Response(text="Mandala Garden Bot v5.1.0"))
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    main()