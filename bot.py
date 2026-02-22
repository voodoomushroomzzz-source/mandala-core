#!/usr/bin/env python3
"""
Mandala Sync Terminal Bot v3.31.1
Render Web Service + Webhook (Aiogram 3)

НОВОЕ В v3.31.1:
- Экранирование HTML в предпросмотре файловых патчей (чтобы не ломались теги)

Предыдущие изменения v3.31.0:
- Универсальные патчи: поддержка file_path для любых файлов
"""

import os
import sys
import json
import logging
import uuid
import base64
import asyncio
import copy
import re
import html
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
    BufferedInputFile, CallbackQuery
)
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import aiohttp
from dotenv import load_dotenv

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

# URL нашей облачной функции СР
SR_FUNCTION_URL = "https://functions.yandexcloud.net/d4en8kkgifqjhadrc84i"

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

# ========== FSM СОСТОЯНИЯ ==========
class UploadStates(StatesGroup):
    waiting_for_action = State()
    waiting_for_category = State()
    waiting_for_module = State()
    waiting_for_file = State()
    waiting_for_patch_file = State()
    waiting_for_patch_confirmation = State()
    waiting_for_multi_patch_confirmation = State()

# ========== ДОСТУПНЫЕ МОДЕЛИ ==========
AVAILABLE_MODELS = {
    "deepseek": {
        "name": "DeepSeek-R1",
        "emoji": "🧠",
        "description": "Глубокие рассуждения, философия, метафоры"
    },
    "qwen": {
        "name": "Qwen3 235B",
        "emoji": "📊",
        "description": "Мощный анализ, стратегия, большие контексты"
    },
    "yandex": {
        "name": "YandexGPT Pro",
        "emoji": "⚙️",
        "description": "Точность, JSON, структурированный вывод"
    },
    "gemma": {
        "name": "Gemma 3 27B",
        "emoji": "🎨",
        "description": "Креатив, маркетинг, внешние коммуникации"
    }
}

# ========== ЦЕЛЕВЫЕ ФАЙЛЫ ==========
MANDALA_MODULES = {
    "initium": {
        "name": "🌀 Initium",
        "filename": "initium.json",
        "path": "initium.json",
        "description": "Конституционное ядро",
        "category": "module"
    },
    "sphaerae": {
        "name": "🌐 Sphaerae",
        "filename": "sphaerae.json",
        "path": "sphaerae.json",
        "description": "Карта Мандалы",
        "category": "module"
    },
    "akasha_chronicorum": {
        "name": "📜 Akasha Chronicorum",
        "filename": "akasha_chronicorum.json",
        "path": "akasha_chronicorum.json",
        "description": "Живая память",
        "category": "module"
    },
    "philosophia": {
        "name": "💭 Philosophia",
        "filename": "philosophia.json",
        "path": "philosophia.json",
        "description": "Философское ядро",
        "category": "module"
    },
    "geometria_sacra": {
        "name": "🔺 Geometria Sacra",
        "filename": "geometria_sacra.json",
        "path": "geometria_sacra.json",
        "description": "Язык Света",
        "category": "module"
    },
    "incubae": {
        "name": "🌱 Incubae",
        "filename": "incubae.json",
        "path": "incubae.json",
        "description": "Единый реестр семян",
        "category": "module"
    },
    "tectosphaera": {
        "name": "🛡️ Tectosphaera",
        "filename": "tectosphaera.json",
        "path": "tectosphaera.json",
        "description": "Тело заботы",
        "category": "module"
    },
    "testisphaera": {
        "name": "🧪 Testisphaera",
        "filename": "testisphaera_v0.1.json",
        "path": "testlab/testisphaera_v0.1.json",
        "description": "Песочница для тестирования",
        "category": "module"
    }
}

INFRASTRUCTURE_FILES = {
    "build_script": {
        "name": "🔨 Сборщик монолита",
        "filename": "build_monolith.py",
        "path": "build_monolith.py",
        "description": "Скрипт сборки v5.2",
        "category": "infra"
    },
    "github_action": {
        "name": "🤖 GitHub Action",
        "filename": "build-monolith.yml",
        "path": ".github/workflows/build-monolith.yml",
        "description": "Автоматическая сборка",
        "category": "infra"
    },
    "bot_script": {
        "name": "🤖 Сам бот (bot.py)",
        "filename": "bot.py",
        "path": "bot.py",
        "description": "Исходный код бота",
        "category": "infra"
    }
}

ALL_UPLOAD_TARGETS = {**MANDALA_MODULES, **INFRASTRUCTURE_FILES}
user_upload_target = {}

# Хранилище выбранной модели для каждого пользователя
user_selected_model = {}

# ========== ФУНКЦИЯ ВЫЗОВА СР ==========

async def call_sr(chat_id: str, text: str, selected_model: str = None) -> Optional[str]:
    async with aiohttp.ClientSession() as session:
        try:
            payload = {"chat_id": chat_id, "message": text, "selected_model": selected_model}
            logger.info(f"Calling SR for chat {chat_id} with model {selected_model}")
            async with session.post(SR_FUNCTION_URL, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response")
                else:
                    logger.error(f"SR function returned {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"Error calling SR function: {e}")
            return None

# ========== КЛАВИАТУРЫ ==========
# (полные определения клавиатур остаются без изменений — они уже есть в текущей версии)
# Для краткости я их опускаю, но в реальном патче они должны присутствовать.
# Вместо этого я приведу только изменённую функцию.

# ========== ФУНКЦИИ ДЛЯ ПАКЕТНЫХ ОБНОВЛЕНИЙ ==========

def format_file_patch_preview(patch_data: Dict) -> str:
    """Форматирование предпросмотра для файлового патча (с экранированием HTML)"""
    import html
    lines = []
    lines.append(f"📁 <b>Файл:</b> <code>{patch_data['file_path']}</code>")

    if patch_data.get("patch_id"):
        lines.append(f"📄 <b>ID патча:</b> {patch_data['patch_id']}")

    if patch_data.get("description"):
        lines.append(f"📝 <b>Описание:</b> {patch_data['description']}")

    content = patch_data.get("content", "")
    # Экранируем HTML-спецсимволы, чтобы Telegram не пытался интерпретировать их как теги
    escaped_content = html.escape(content[:500])
    if len(content) > 500:
        escaped_content += "..."
    lines.append(f"\n📄 <b>Новое содержимое (первые 500 символов):</b>\n<code>{escaped_content}</code>")

    return "\n".join(lines)

# Остальные функции (validate_patch_structure, process_file_patch и т.д.) остаются без изменений.
# После применения этого патча бот перезапустится.

# ========== WEBHOOK ==========

async def on_startup() -> None:
    await bot.set_webhook(WEBHOOK_URL, secret_token=WEBHOOK_SECRET, allowed_updates=dp.resolve_used_update_types(), drop_pending_updates=True)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown() -> None:
    logger.info("🛑 Shutdown")

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
    async def health(_): return web.Response(text="OK")
    app.router.add_get("/healthcheck", health)
    async def index(_): return web.Response(text="Mandala Bot v3.31.1")
    app.router.add_get("/", index)
    setup_application(app, dp, bot=bot)
    logger.info(f"🚀 Запуск на порту {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    main()
