# -*- coding: utf-8 -*-
"""
config.py — Globals & Configuration
Imports, constants, environment variables, bot/dispatcher init,
global data structures (_store, _sessions, _sha_cache), middleware.

Part of: honeycombs/fruits/gentle_companion/
Phase: 2 (no dependencies — entry point for all other modules)

Key globals:
  BOT_TOKEN, GITHUB_TOKEN, GARDENERS_TOKEN — credentials
  REPO_NAME, GARDENERS_REPO               — repository routing
  ARCHITECT_TELEGRAM_ID, BOT_VERSION      — identity
  bot, dp, router                         — aiogram instances
  _store, _sessions, _pending_writes      — runtime data
  _sha_cache, _sync_lock                  — sync helpers
  AutoLoadMiddleware                      — auto-load on demand
"""

#!/usr/bin/env python3

import re
import os
import sys
import json
import logging
import base64
import asyncio
import time
import copy
from datetime import datetime
from typing import Optional, Any, Tuple

from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import aiohttp
import httpx
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN    = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "MandalasGardener_bot")  # для deep link
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("REPO_NAME", "voodoomushroomzzz-source/mandala-core")
# Separate repo for gardener data
GARDENERS_TOKEN = os.getenv("GARDENERS_TOKEN", GITHUB_TOKEN)
GARDENERS_REPO  = os.getenv("GARDENERS_REPO",  "voodoomushroomzzz-source/mandala-gardeners")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
ALLOWED_PASSWORD = os.getenv("ALLOWED_PASSWORD", "mandala")
ARCHITECT_TELEGRAM_ID = os.getenv("ARCHITECT_TELEGRAM_ID", "224736062")
ENGINEER_CHAT_URL = os.getenv("ENGINEER_CHAT_URL", "https://mandala-engineer-chat.onrender.com")
SR_BACKEND_URL = os.getenv("SR_BACKEND_URL", f"{ENGINEER_CHAT_URL}/bot/ask")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SR_MODEL_CHAIN = [
    "deepseek/deepseek-v4-flash",   # primary — 284B MoE, 13B active, 1M ctx
    "qwen/qwen3.5-flash-02-23",     # fallback — проверенный боевой
]
SESSION_MAX_MESSAGES = 50

# ── Версия бота ───────────────────────────────────────────────────────────────
BOT_VERSION = "7.39.23"
# ⚠️ DEV RULE: Update this on EVERY patch. Keep last 5 versions. Delete oldest.
BOT_LATEST_UPDATE = {
    "version": "7.39.23",
    "date": "2026-05-12",
    "text": (
        "🌱 Мандала · Что нового\n"
        "\n"
        "v7.39.23 · 12.05.2026\n"
        "  · 🔄 Данные задач и история чата обновлены — начинаем с чистого листа\n"
        "  · Профиль и настройки сохранены\n"
        "  · Профиль: ближайшие задачи (5) и напоминания (3)\n"
        "  · Все садовники загружаются при старте\n"
        "\n"
        "v7.39.22 · 11.05.2026\n"
        "  · Параллельная загрузка садовников при старте\n"
        "  · Резонанс через сферы — больше не раздувается от достижений\n"
        "  · Кнопка Дополнить → полное меню редактирования\n"
        "  · Голос не блокирует бот (Groq в executor)\n"
        "\n"
        "v7.39.21 · 11.05.2026\n"
        "  · Утренние брифы приходят всем садовникам\n"
        "\n"
        "v7.39.9 · 09.05.2026\n"
        "  · Меню Задач: группы, список задач, повторы, своя дата"
    ),
}

# ─── Business limits ──────────────────────────────────────────────────────────
TASK_CTX_FREE    = "free"      # task visible in tasks menu

TASK_LIMIT_HARD  = 30  # P-67
TASK_LIMIT_SOFT  = 25  # warn when approaching hard limit
LABEL_LIMIT_HARD = 7
LABEL_LIMIT_SOFT = 6
CHECKLIST_LIMIT      = 3    # max checklists per user
CHECKLIST_ITEMS_LIMIT = 20  # max items per checklist
REMINDER_LIMIT         = 20  # max reminders per user — P-67
REMINDER_LIMIT_SOFT    = 15  # warn when approaching reminder limit

PORT = 10000
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = ""  # No secret — HTTPS on Render is sufficient

GARDENERS_ROOT = "gardeners"  # gardeners/{telegram_id}/profile.json etc

if not BOT_TOKEN or not RENDER_EXTERNAL_URL:
    logger.error("Missing BOT_TOKEN or RENDER_EXTERNAL_URL")
    sys.exit(1)

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ── AutoLoad Middleware ────────────────────────────────────────────────────
# If user store is not ready (e.g. after redeploy), load user data on demand
# before any handler runs. Fixes "dead buttons" after Render restart.
from aiogram import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable
from aiogram.types import TelegramObject

class AutoLoadMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        try:
            user = getattr(event, "from_user", None)
            if user:
                uid = str(user.id)
                store = _get_user_store(uid)
                if not store.get("ready"):
                    await _load_user(uid)
        except Exception:
            pass
        return await handler(event, data)

dp.message.middleware(AutoLoadMiddleware())
dp.callback_query.middleware(AutoLoadMiddleware())

# ═══════════════════════════════════════════════════════════════════════════════
# IN-MEMORY STORE
# Single source of truth during runtime. GitHub = persistent backup.
# READ  → always from _store (instant)
# WRITE → update _store → respond to user → sync GitHub in background
# ═══════════════════════════════════════════════════════════════════════════════

# Multi-user store: {telegram_id: {"profile": dict, "workspace": dict, "ready": bool}}
_store: dict = {}
_last_bot_message: dict = {}  # {uid: {"message_id": int, "text": str}}

def _get_user_store(telegram_id: str) -> dict:
    uid = str(telegram_id)
    if uid not in _store:
        _store[uid] = {"profile": None, "workspace": None, "ready": False}
    return _store[uid]

# pending GitHub writes: {path: content} — deduplicated by path
_pending_writes: dict = {}
# SHA cache: {path: sha} — skip download if SHA unchanged
_sha_cache: dict = {}
_write_lock = asyncio.Lock() if False else None  # initialized in on_startup
_sync_lock   = asyncio.Lock()  # prevents parallel GitHub syncs

def _user_path(telegram_id: str) -> str:
    return f"{GARDENERS_ROOT}/gardener_{telegram_id}"
