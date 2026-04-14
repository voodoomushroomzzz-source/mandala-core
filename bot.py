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
            "message": f" bot: update {filename}",
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
        keyboard=[[KeyboardButton(text=" РћС‚РјРµРЅР°")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=" РџСЂРѕС„РёР»СЊ"), KeyboardButton(text=" Р”РѕСЃС‚РёР¶РµРЅРёСЏ")]
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

    # РЎРѕС…СЂР°РЅРµРЅРёРµ РІ GitHub
    success = await write_gardener_file("gardener.json", gardener)
    if not success:
        await message.answer(" РћС€РёР±РєР° СЃРѕС…СЂР°РЅРµРЅРёСЏ РїСЂРѕС„РёР»СЏ. РџРѕРїСЂРѕР±СѓР№ РїРѕР·Р¶Рµ.")
        await state.clear()
        return

    await write_gardener_file("tasks.json", [])
    await write_gardener_file("achievements.json", [])
    await write_gardener_file("groups.json", groups)

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

    achievements = await read_gardener_file("achievements.json") or []
    if not achievements:
        await message.answer(" РЈ С‚РµР±СЏ РїРѕРєР° РЅРµС‚ РґРѕСЃС‚РёР¶РµРЅРёР№.\n\nР”РѕР±Р°РІСЊ РїРµСЂРІРѕРµ: /addachievement", reply_markup=get_main_keyboard())
        return

    cats = {"health": [], "creativity": [], "knowledge": [], "exploration": [], "relationships": []}
    for ach in achievements:
        cat = ach.get("category", "knowledge")
        if cat in cats:
            cats[cat].append(ach)

    text = " <b>РўРІРѕРё РґРѕСЃС‚РёР¶РµРЅРёСЏ:</b>\n\n"
    emoji = {"health": "", "creativity": "", "knowledge": "", "exploration": "", "relationships": ""}
    for cat, items in cats.items():
        if items:
            text += f"{emoji.get(cat, '')} <b>{cat.title()}:</b>\n"
            for ach in items[:5]:
                text += f"   {ach.get('title', '')} (+{ach.get('resonance_bonus', 1)}%)\n"
            text += "\n"
    await message.answer(text, reply_markup=get_main_keyboard())

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

    success = await write_gardener_file("achievements.json", achievements)

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
            await write_gardener_file("gardener.json", gardener)

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

    if gardener and str(gardener.get("identity", {}).get("telegram_id", "")) == user_id:
        name = gardener.get("identity", {}).get("name", "РЎР°РґРѕРІРЅРёРє")
        await message.answer(f" РЎ РІРѕР·РІСЂР°С‰РµРЅРёРµРј, {name}!", reply_markup=get_main_keyboard())
        return

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
    achievements = await read_gardener_file("achievements.json") or []
    top_achievements = sorted(achievements, key=lambda x: x.get("resonance_bonus", 0), reverse=True)[:3]

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

    achievements = await read_gardener_file("achievements.json") or []

    weights = {
        "health": 1.2,
        "creativity": 1.1,
        "knowledge": 1.0,
        "exploration": 1.1,
        "relationships": 1.0
    }

    total = 13
    for ach in achievements:
        cat = ach.get("category", "knowledge")
        bonus = ach.get("resonance_bonus", 1)
        total += bonus * weights.get(cat, 1.0)

    total = min(100, int(total))

    gardener = await read_gardener()
    history = gardener.get("growth_history", []) if gardener else []

    text = f" <b>Р РµР·РѕРЅР°РЅСЃ: {total}%</b>"
    if history:
        text += "\n\n РСЃС‚РѕСЂРёСЏ:\n"
        for h in history[-5:]:
            text += f"  {h.get('date', '?')}: {h.get('resonance', '?')}%\n"

    await message.answer(text)

@router.message(F.text == " РџСЂРѕС„РёР»СЊ")
async def btn_profile(message: Message):
    await cmd_profile(message)

# ========== MAIN HANDLER (Gentle SR) ==========
@router.message()
async def handle_gentle_sr(message: Message):
    if not await is_authorized(str(message.from_user.id)):
        await message.answer(" РЎРЅР°С‡Р°Р»Р° /start [РїР°СЂРѕР»СЊ]")
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
        await message.answer(" РЎР  РІСЂРµРјРµРЅРЅРѕ РЅРµРґРѕСЃС‚СѓРїРµРЅ. РџРѕРїСЂРѕР±СѓР№ РїРѕР·Р¶Рµ.", reply_markup=get_main_keyboard())

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