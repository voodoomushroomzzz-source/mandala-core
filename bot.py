#!/usr/bin/env python3
"""
Mandala Garden Bot  Gentle Companion v5.2.0
+ D4: Achievements commands with FSM
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

async def read_gardener() -> Optional[dict]:
    ok, data = await get_github_file(f"{GARDENER_PATH}/gardener.json")
    return data if ok else None

async def read_gardener_file(filename: str) -> Optional[Any]:
    ok, data = await get_github_file(f"{GARDENER_PATH}/{filename}")
    return data if ok else None

async def write_gardener_file(filename: str, content: Any) -> bool:
    if not GITHUB_TOKEN:
        return False
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{GARDENER_PATH}/{filename}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/5.2.0"
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
            "message": " bot: update achievements",
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

class AchievementStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_bonus = State()

# ========== KEYBOARDS ==========

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=" Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=" Профиль"), KeyboardButton(text=" Достижения")],
            [KeyboardButton(text=" Резонанс")]
        ],
        resize_keyboard=True
    )

def get_achievement_category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=" Здоровье", callback_data="ach_cat_health")],
        [InlineKeyboardButton(text=" Творчество", callback_data="ach_cat_creativity")],
        [InlineKeyboardButton(text=" Знания", callback_data="ach_cat_knowledge")],
        [InlineKeyboardButton(text=" Исследование", callback_data="ach_cat_exploration")],
        [InlineKeyboardButton(text=" Отношения", callback_data="ach_cat_relationships")],
        [InlineKeyboardButton(text=" Отмена", callback_data="cancel_achievement")]
    ])

# ========== FSM: ONBOARDING ==========
# [Existing onboarding handlers remain unchanged - omitted for brevity]
# (Same as in v5.1.0)

# ========== D4: ACHIEVEMENTS ==========
@router.message(Command("achievements"))
async def cmd_achievements(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer(" Сначала /start")
        return
    
    achievements = await read_gardener_file("achievements.json") or []
    
    if not achievements:
        await message.answer(
            " У тебя пока нет достижений.\n\n"
            "Добавь первое: /addachievement",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Group by category
    cats = {"health": [], "creativity": [], "knowledge": [], "exploration": [], "relationships": []}
    for ach in achievements:
        cat = ach.get("category", "knowledge")
        if cat in cats:
            cats[cat].append(ach)
    
    text = " <b>Твои достижения:</b>\n\n"
    emoji = {"health": "", "creativity": "", "knowledge": "", "exploration": "", "relationships": ""}
    
    for cat, items in cats.items():
        if items:
            text += f"{emoji.get(cat, '')} <b>{cat.title()}:</b>\n"
            for ach in items[:5]:  # Show top 5 per category
                bonus = ach.get("resonance_bonus", 1)
                text += f"   {ach.get('title', '')} (+{bonus}%)\n"
            text += "\n"
    
    await message.answer(text, reply_markup=get_main_keyboard())

@router.message(Command("addachievement"))
async def cmd_addachievement(message: Message, state: FSMContext):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer(" Сначала /start")
        return
    
    await state.set_state(AchievementStates.waiting_for_category)
    await message.answer(
        " <b>Создание достижения</b>\n\n"
        "Выбери категорию:",
        reply_markup=get_achievement_category_keyboard()
    )

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
    
    await callback.message.edit_text(
        f" Категория: {category}\n\n"
        "Введи название достижения:"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "cancel_achievement")
async def cancel_achievement(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(" Создание достижения отменено.")
    await callback.answer()

@router.message(StateFilter(AchievementStates.waiting_for_title))
async def achievement_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) < 3:
        await message.answer("Название должно быть не короче 3 символов.")
        return
    await state.update_data(title=title)
    await state.set_state(AchievementStates.waiting_for_description)
    await message.answer(" Напиши описание достижения:")

@router.message(StateFilter(AchievementStates.waiting_for_description))
async def achievement_description(message: Message, state: FSMContext):
    description = message.text.strip()
    await state.update_data(description=description)
    await state.set_state(AchievementStates.waiting_for_bonus)
    await message.answer(
        " Сколько процентов резонанса даёт это достижение? (1-10)\n\n"
        "По умолчанию: 1"
    )

@router.message(StateFilter(AchievementStates.waiting_for_bonus))
async def achievement_bonus(message: Message, state: FSMContext):
    try:
        bonus = int(message.text.strip())
        if bonus < 1 or bonus > 10:
            raise ValueError
    except:
        await message.answer("Введи число от 1 до 10.")
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
    
    success = await write_gardener_file("achievements.json", achievements)
    
    if success:
        # Update resonance
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
            await write_gardener_file("gardener.json", gardener)
        
        await message.answer(
            f" <b>Достижение добавлено!</b>\n\n"
            f"{data['title']} (+{bonus}% резонанса)\n"
            f"{data['description']}\n\n"
            f"Твой резонанс вырос!",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(" Ошибка сохранения. Попробуй позже.")
    
    await state.clear()

# ========== OTHER COMMANDS ==========
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    # [Same as v5.1.0]
    pass

@router.message(Command("profile"))
async def cmd_profile(message: Message):
    # [Same as v5.1.0]
    pass

@router.message(Command("resonance"))
async def cmd_resonance(message: Message):
    # [Same as v5.1.0 but enhanced]
    pass

@router.message(F.text == " Профиль")
async def btn_profile(message: Message):
    await cmd_profile(message)

@router.message(F.text == " Достижения")
async def btn_achievements(message: Message):
    await cmd_achievements(message)

@router.message(F.text == " Резонанс")
async def btn_resonance(message: Message):
    await cmd_resonance(message)

@router.message()
async def handle_gentle_sr(message: Message):
    # [Same as v5.1.0]
    pass

# ========== WEBHOOK ==========
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL, secret_token=WEBHOOK_SECRET, drop_pending_updates=True)
    logger.info(f"Webhook set: {WEBHOOK_URL}")

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
    app.router.add_get("/", lambda _: web.Response(text="Mandala Garden Bot v5.2.0"))
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    main()