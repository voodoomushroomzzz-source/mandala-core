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
from aiogram.filters import Command
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

# ========== KEYBOARDS ==========
def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🌱 Профиль")]],
        resize_keyboard=True
    )

# ========== COMMANDS ==========
@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = str(message.from_user.id)
    
    if not await is_authorized(user_id):
        args = message.text.replace("/start", "").strip()
        if args != ALLOWED_PASSWORD:
            await message.answer("🔐 Введи пароль: /start [пароль]")
            return
        
        gardener = await read_gardener()
        if gardener:
            gardener["identity"]["telegram_id"] = user_id
            await write_gardener_file("gardener.json", gardener)
            await message.answer(f"🌱 С возвращением, {gardener['identity'].get('name', 'Садовник')}!", reply_markup=get_main_keyboard())
            return
        else:
            await message.answer("🌱 Сад ещё не создан. Ожидай создания gardener_001.")
            return
    
    gardener = await read_gardener()
    name = gardener.get("identity", {}).get("name", "Садовник") if gardener else "Садовник"
    await message.answer(f"🌱 С возвращением, {name}!", reply_markup=get_main_keyboard())

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