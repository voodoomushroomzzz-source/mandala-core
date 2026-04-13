#!/usr/bin/env python3
"""
Mandala Garden Bot — Gentle Companion
Clean build. Password protected. Hardcoded to gardener_001.
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
        "User-Agent": "MandalaGardenBot/5.0.0"
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

async def is_authorized(telegram_id: str) -> bool:
    gardener = await read_gardener()
    if not gardener:
        return False
    return str(gardener.get("identity", {}).get("telegram_id", "")) == str(telegram_id)

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
    
    # Password check for new users
    if not await is_authorized(user_id):
        args = message.text.replace("/start", "").strip()
        if args != ALLOWED_PASSWORD:
            await message.answer("🔐 Введи пароль: /start [пароль]")
            return
        
        gardener = await read_gardener()
        if gardener:
            gardener["identity"]["telegram_id"] = user_id
            # TODO: save gardener
            await message.answer(f"🌱 С возвращением, {gardener['identity'].get('name', 'Садовник')}!")
            return
        else:
            await message.answer("🌱 Сад ещё не создан. Ожидай создания gardener_001.")
            return
    
    gardener = await read_gardener()
    name = gardener.get("identity", {}).get("name", "Садовник") if gardener else "Садовник"
    await message.answer(
        f"🌱 С возвращением, {name}!",
        reply_markup=get_main_keyboard()
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

# ========== WEBHOOK ==========
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL, secret_token=WEBHOOK_SECRET, drop_pending_updates=True)
    logger.info(f"Webhook set: {WEBHOOK_URL}")

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
    app.router.add_get("/", lambda _: web.Response(text="Mandala Garden Bot v5.0.0"))
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    main()