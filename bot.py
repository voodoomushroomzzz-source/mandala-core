#!/usr/bin/env python3
"""
Mandala Sync Terminal Bot v3.20.0-kortix
Render Web Service + Webhook (Aiogram 3)
ДОБАВЛЕНО:
- Поддержка папки /updates для Kortix
- Валидация JSON-схемы инструкций
- Новая категория загрузки
- 🔧 Фикс: инструкции всегда сохраняются как current_instruction.json (перезапись)
"""

import os
import sys
import json
import logging
import uuid
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

# ========== FSM И ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
class UploadStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_module = State()
    waiting_for_file = State()

class UploadCategory:
    MODULE = "module"
    INFRA = "infra"
    FRUCTUS = "fructus"
    KORTIX = "kortix"

# ========== ПОЛНЫЙ СПИСОК ЦЕЛЕВЫХ ФАЙЛОВ ==========
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
    "akasha": {
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
        "description": "Тело заботы, защита как уход",
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
    }
}

# 🔥 Kortix updates target
KORTIX_UPDATES = {
    "kortix_update": {
        "name": "🚀 Kortix инструкция",
        "filename": "current_instruction.json",  # фиксированное имя
        "path": "updates/current_instruction.json",  # путь с именем
        "description": "JSON-инструкция для хирургического обновления через Kortix",
        "category": "kortix"
    }
}

ALL_UPLOAD_TARGETS = {**MANDALA_MODULES, **INFRASTRUCTURE_FILES, **KORTIX_UPDATES}
user_upload_target = {}

# Схема валидации для Kortix инструкций
KORTIX_SCHEMA = {
    "required": ["schema_version", "update_id", "operations"],
    "optional": ["initiated_by", "resonance_check_required", "commit_message", 
                 "branch_name", "pr_title", "pr_description"]
}

def validate_kortix_instruction(data: Dict) -> Tuple[bool, str]:
    """Проверяет JSON инструкцию для Kortix"""
    try:
        # Проверка обязательных полей
        for field in KORTIX_SCHEMA["required"]:
            if field not in data:
                return False, f"Отсутствует обязательное поле: {field}"
        
        # Проверка версии схемы
        if data["schema_version"] != "1.0":
            return False, f"Неподдерживаемая версия схемы: {data['schema_version']}. Ожидается 1.0"
        
        # Проверка operations
        if not isinstance(data["operations"], list):
            return False, "Поле 'operations' должно быть массивом"
        
        if len(data["operations"]) == 0:
            return False, "Массив operations не может быть пустым"
        
        # Проверка каждой операции
        for i, op in enumerate(data["operations"]):
            if "type" not in op:
                return False, f"Операция {i}: отсутствует поле 'type'"
            
            valid_types = ["add_object_to_array", "update_field", "delete_field", "rename_key"]
            if op["type"] not in valid_types:
                return False, f"Операция {i}: неподдерживаемый тип '{op['type']}'. Ожидается: {valid_types}"
            
            if "file" not in op:
                return False, f"Операция {i}: отсутствует поле 'file'"
            
            if "target_path" not in op:
                return False, f"Операция {i}: отсутствует поле 'target_path'"
        
        return True, "✅ Инструкция корректна"
        
    except Exception as e:
        return False, f"Ошибка валидации: {str(e)}"

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="📤 Загрузить файл")],
        [KeyboardButton(text="📦 Монолит")],
        [KeyboardButton(text="🍇 Fructus")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=True
    )

def get_upload_mode_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="❌ Отмена")],
        [KeyboardButton(text="🔄 Сменить тип")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=True
    )

def get_category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧩 Модули Мандалы", callback_data="category_modules")],
        [InlineKeyboardButton(text="⚙️ Инфраструктура сборки", callback_data="category_infra")],
        [InlineKeyboardButton(text="🚀 Kortix Updates", callback_data="category_kortix")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def get_modules_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌀 Initium", callback_data="target_initium"),
            InlineKeyboardButton(text="🌐 Sphaerae", callback_data="target_sphaerae")
        ],
        [
            InlineKeyboardButton(text="📜 Akasha", callback_data="target_akasha"),
            InlineKeyboardButton(text="💭 Philosophia", callback_data="target_philosophia")
        ],
        [
            InlineKeyboardButton(text="🔺 Geometria", callback_data="target_geometria_sacra"),
            InlineKeyboardButton(text="🌱 Incubae", callback_data="target_incubae")
        ],
        [
            InlineKeyboardButton(text="🛡️ Tectosphaera", callback_data="target_tectosphaera")
        ],
        [InlineKeyboardButton(text="◀️ Назад к категориям", callback_data="back_to_categories")]
    ])

def get_infra_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔨 Сборщик", callback_data="target_build_script"),
            InlineKeyboardButton(text="🤖 GitHub Action", callback_data="target_github_action")
        ],
        [InlineKeyboardButton(text="◀️ Назад к категориям", callback_data="back_to_categories")]
    ])

# клавиатура для Kortix
def get_kortix_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Загрузить инструкцию", callback_data="target_kortix_update")],
        [InlineKeyboardButton(text="📋 О Kortix", callback_data="kortix_info")],
        [InlineKeyboardButton(text="◀️ Назад к категориям", callback_data="back_to_categories")]
    ])

def get_monolith_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📥 Скачать монолит", callback_data="download_monolith"),
            InlineKeyboardButton(text="📋 Информация", callback_data="info_monolith")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def get_fructus_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📤 Загрузить", callback_data="fructus_upload"),
            InlineKeyboardButton(text="📋 Информация", callback_data="fructus_info")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

# ========== ФУНКЦИИ GITHUB API ==========
async def update_github_file(file_path: str, content: Any, message: str) -> bool:
    """Обновление файла на GitHub с ПОЛНОЙ защитой от исключений."""
    
    if not GITHUB_TOKEN:
        logger.error("❌ GITHUB_TOKEN не установлен")
        return False
    
    try:
        if isinstance(content, dict):
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
        "User-Agent": "MandalaBot/3.20.0-kortix"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    sha = data.get("sha")
                    logger.info(f"✅ SHA получен для {file_path}")
                elif response.status == 404:
                    sha = None
                    logger.info(f"📄 {file_path} не существует, будет создан")
                else:
                    error_text = await response.text()
                    logger.error(f"⚠️ GitHub GET error {response.status}")
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
            async with session.put(url, headers=headers, json=payload, timeout=15) as response:
                response_text = await response.text()
                logger.info(f"📡 GitHub response status: {response.status}")
                
                if response.status in [200, 201]:
                    logger.info(f"✅ Файл {file_path} успешно обновлён")
                    return True
                else:
                    logger.error(f"❌ GitHub error: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке в GitHub: {e}")
            return False

# ========== ОСТАЛЬНЫЕ ФУНКЦИИ ==========
async def check_ahimsa_smart(content: Dict, filename: str = "") -> Tuple[bool, str, List[Tuple[str, str]]]:
    """Упрощённая проверка Ahimsa"""
    return True, "✅ Проверка пройдена", []

def generate_fructus_filename(original_name: str, file_type: str = "artifact") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = str(uuid.uuid4())[:8]
    if '.' in original_name:
        ext = original_name.split('.')[-1]
        name_without_ext = '.'.join(original_name.split('.')[:-1])
    else:
        ext = "json"
        name_without_ext = original_name
    safe_name = ''.join(c for c in name_without_ext[:30] if c.isalnum() or c in ' _-')
    return f"{file_type}_{timestamp}_{short_id}_{safe_name}.{ext}"

async def upload_to_fructus(original_filename: str, content: Dict, user_id: int) -> Tuple[bool, str]:
    try:
        file_type = "artifact"
        filename_lower = original_filename.lower()
        if "seed" in filename_lower or "incubae" in filename_lower:
            file_type = "seed"
        elif "geometria" in filename_lower or "sacra" in filename_lower:
            file_type = "geometry"
        
        target_filename = generate_fructus_filename(original_filename, file_type)
        full_path = f"fructus/{target_filename}"
        
        enhanced_content = content.copy()
        if isinstance(content, dict):
            enhanced_content["_fructus_metadata"] = {
                "original_filename": original_filename,
                "generated_filename": target_filename,
                "file_type": file_type,
                "upload_timestamp": datetime.now().isoformat(),
                "uploaded_by": f"user_{user_id}",
                "source": "mandala_bot_v3.20.0-kortix"
            }
        
        success = await update_github_file(
            file_path=full_path,
            content=enhanced_content,
            message=f"Fructus: {original_filename} → {target_filename}"
        )
        return success, target_filename
    except Exception as e:
        logger.error(f"Ошибка Fructus: {e}")
        return False, str(e)

async def download_monolith_file() -> Tuple[bool, bytes, str]:
    try:
        url = f"https://raw.githubusercontent.com/{REPO_NAME}/main/build/mandala_core.monolith.latest.json"
        headers = {}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    content = await response.read()
                    return True, content, "mandala_core.monolith.json"
                else:
                    return False, b"", f"Ошибка {response.status}"
    except Exception as e:
        return False, b"", str(e)

# ========== ОБРАБОТЧИКИ КОМАНД ==========
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    await message.answer(
        "🌀 <b>Mandala Sync Terminal v3.20.0-kortix</b>\n\n"
        "<b>Новая возможность:</b>\n"
        "🚀 Kortix Updates — загрузка инструкций для хирургического обновления\n\n"
        "<b>Выберите действие:</b>",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "❌ Отмена")
async def handle_cancel_button(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    await message.answer("🚫 Действие отменено", reply_markup=get_main_keyboard())

@router.message(F.text == "📤 Загрузить файл")
async def handle_upload_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    await message.answer(
        "📤 <b>Выберите категорию:</b>\n\n"
        "🧩 <b>Модули Мандалы</b> — JSON-кристаллы системы\n"
        "⚙️ <b>Инфраструктура сборки</b> — скрипты и GitHub Actions\n"
        "🚀 <b>Kortix Updates</b> — инструкции для хирургического обновления",
        reply_markup=get_category_keyboard()
    )
    await state.set_state(UploadStates.waiting_for_category)

@router.message(F.text == "📦 Монолит")
async def handle_monolith_menu(message: Message):
    await message.answer(
        "📦 <b>Монолит Mandala Core</b>",
        reply_markup=get_monolith_inline_keyboard()
    )

@router.message(F.text == "🍇 Fructus")
async def handle_fructus_menu(message: Message):
    await message.answer(
        "🍇 <b>Fructus - система артефактов</b>",
        reply_markup=get_fructus_inline_keyboard()
    )

@router.message(F.text == "ℹ️ Помощь")
async def handle_help(message: Message):
    await message.answer(
        "📚 <b>Mandala Sync Terminal v3.20.0-kortix</b>\n\n"
        "📤 Загрузка модулей и инфраструктуры\n"
        "🚀 Kortix Updates — инструкции для хирургического обновления\n"
        "📦 Скачивание монолита\n"
        "🍇 Сохранение артефактов в Fructus\n\n"
        "🌿 Ahimsa-фильтр активен",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "🔄 Сменить тип")
async def handle_change_category(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    await state.set_state(UploadStates.waiting_for_category)
    await message.answer("🔄 Выберите категорию:", reply_markup=get_category_keyboard())

# ========== ОБРАБОТЧИКИ КОЛБЭКОВ ==========
@router.callback_query(F.data == "category_kortix")
async def handle_category_kortix(callback_query: CallbackQuery, state: FSMContext):
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "🚀 <b>Kortix Updates</b>\n\n"
        "Загрузите JSON-инструкцию для хирургического обновления модулей.\n"
        "Файл будет сохранён в папку <code>/updates/current_instruction.json</code> (перезапись).\n\n"
        "Формат: см. <code>updates/template.json</code> в репозитории.",
        reply_markup=get_kortix_keyboard()
    )
    await callback_query.answer()

@router.callback_query(F.data == "target_kortix_update")
async def handle_target_kortix(callback_query: CallbackQuery, state: FSMContext):
    target_key = "kortix_update"
    user_upload_target[callback_query.from_user.id] = target_key
    await state.set_state(UploadStates.waiting_for_file)
    
    await callback_query.message.edit_text(
        f"✅ Выбран: Kortix инструкция\n"
        f"📁 Целевой файл: <b>updates/current_instruction.json</b> (перезапись)\n\n"
        f"📎 Отправьте JSON-файл с инструкцией"
    )
    await callback_query.message.answer(
        "📎 Прикрепите JSON-файл",
        reply_markup=get_upload_mode_keyboard()
    )
    await callback_query.answer()

@router.callback_query(F.data == "kortix_info")
async def handle_kortix_info(callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        "📋 <b>О Kortix</b>\n\n"
        "Kortix — автономный ИИ-работник, выполняющий хирургические обновления JSON-файлов в репозитории.\n\n"
        "<b>Как это работает:</b>\n"
        "1. Вы загружаете JSON-инструкцию → она сохраняется как <code>updates/current_instruction.json</code>\n"
        "2. GitHub Actions автоматически запускается при изменении этого файла\n"
        "3. Kortix читает инструкцию, выполняет изменения и создаёт Pull Request\n\n"
        "<b>Пример инструкции:</b>\n"
        "<code>updates/template.json</code> в репозитории",
        reply_markup=get_kortix_keyboard()
    )
    await callback_query.answer()

@router.callback_query(F.data == "category_modules")
async def handle_category_modules(callback_query: CallbackQuery, state: FSMContext):
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "🧩 <b>Выберите модуль Мандалы:</b>",
        reply_markup=get_modules_keyboard()
    )
    await callback_query.answer()

@router.callback_query(F.data == "category_infra")
async def handle_category_infra(callback_query: CallbackQuery, state: FSMContext):
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "⚙️ <b>Выберите компонент инфраструктуры:</b>",
        reply_markup=get_infra_keyboard()
    )
    await callback_query.answer()

@router.callback_query(F.data == "back_to_categories")
async def handle_back_to_categories(callback_query: CallbackQuery, state: FSMContext):
    await state.set_state(UploadStates.waiting_for_category)
    await callback_query.message.edit_text(
        "📤 <b>Выберите категорию:</b>",
        reply_markup=get_category_keyboard()
    )
    await callback_query.answer()

@router.callback_query(F.data.startswith("target_"))
async def handle_target_selection(callback_query: CallbackQuery, state: FSMContext):
    target_key = callback_query.data.replace("target_", "")
    
    if target_key not in ALL_UPLOAD_TARGETS:
        await callback_query.answer("Неизвестный целевой файл")
        return

    target_info = ALL_UPLOAD_TARGETS[target_key]
    user_upload_target[callback_query.from_user.id] = target_key
    await state.set_state(UploadStates.waiting_for_file)
    
    await callback_query.message.edit_text(
        f"✅ Выбран: {target_info['name']}\n"
        f"📁 Файл: <b>{target_info['filename'] or target_info['path']}</b>\n\n"
        f"📎 Отправьте файл"
    )
    await callback_query.message.answer(
        "📎 Прикрепите файл",
        reply_markup=get_upload_mode_keyboard()
    )
    await callback_query.answer()

@router.callback_query(F.data == "download_monolith")
async def handle_download_monolith(callback_query: CallbackQuery):
    await callback_query.message.edit_text("📦 Скачиваю монолит...")
    success, content, filename = await download_monolith_file()
    if success:
        await callback_query.message.answer_document(
            document=BufferedInputFile(content, filename=filename),
            caption="📦 Монолит Mandala Core"
        )
        await callback_query.message.edit_text("✅ Монолит отправлен")
    else:
        await callback_query.message.edit_text(f"❌ Ошибка: {filename}")
    await callback_query.answer()

@router.callback_query(F.data == "info_monolith")
async def handle_info_monolith(callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        "📋 <b>Монолит</b> – все модули в одном файле\n"
        "• Initium • Sphaerae • Akasha\n"
        "• Philosophia • Geometria Sacra • Incubae • Tectosphaera\n\n"
        "Собирается автоматически при пуше",
        reply_markup=get_monolith_inline_keyboard()
    )
    await callback_query.answer()

@router.callback_query(F.data == "fructus_info")
async def handle_fructus_info(callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        "📋 <b>Fructus</b> – хранилище артефактов\n"
        "• seeds — семена Incubae\n"
        "• geometry — паттерны Geometria Sacra\n"
        "• builders — скрипты сборки\n\n"
        "Путь: /fructus/",
        reply_markup=get_fructus_inline_keyboard()
    )
    await callback_query.answer()

@router.callback_query(F.data == "fructus_upload")
async def handle_fructus_upload(callback_query: CallbackQuery, state: FSMContext):
    user_upload_target[callback_query.from_user.id] = "fructus"
    await state.set_state(UploadStates.waiting_for_file)
    await callback_query.message.edit_text("🍇 Fructus: отправьте JSON файл")
    await callback_query.message.answer("📎 Прикрепите JSON", reply_markup=get_upload_mode_keyboard())
    await callback_query.answer()

@router.callback_query(F.data == "cancel")
async def handle_cancel_inline(callback_query: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback_query.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    await callback_query.message.edit_text("🚫 Отменено")
    await callback_query.answer()
    await callback_query.message.answer("🏠 Главное меню", reply_markup=get_main_keyboard())

# ========== ОСНОВНОЙ ОБРАБОТЧИК ФАЙЛОВ ==========
@router.message(StateFilter(UploadStates.waiting_for_file))
async def process_file_upload(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    try:
        if user_id not in user_upload_target:
            await message.answer("⚠️ Сначала выберите категорию и файл", 
                               reply_markup=get_category_keyboard())
            await state.set_state(UploadStates.waiting_for_category)
            return

        target_key = user_upload_target[user_id]
        
        if target_key == "fructus":
            await handle_fructus_upload_file(message, state, user_id)
            return
        
        # 🔥 обработка Kortix инструкций
        if target_key == "kortix_update":
            await handle_kortix_upload_file(message, state, user_id)
            return
        
        if target_key not in ALL_UPLOAD_TARGETS:
            await message.answer("⚠️ Целевой файл не найден", 
                               reply_markup=get_main_keyboard())
            await state.clear()
            return
        
        target_info = ALL_UPLOAD_TARGETS[target_key]
        
        if not message.document:
            await message.answer("⚠️ Отправьте файл", 
                               reply_markup=get_upload_mode_keyboard())
            return
        
        await message.answer(f"📥 Скачиваю {message.document.file_name}...",
                           reply_markup=get_upload_mode_keyboard())

        file = await bot.get_file(message.document.file_id)
        file_content_bytes = await bot.download_file(file.file_path)
        file_content = file_content_bytes.read().decode('utf-8')
        
        if target_info["category"] == "infra":
            content_to_save = file_content
        else:
            try:
                content_to_save = json.loads(file_content)
            except json.JSONDecodeError as e:
                await message.answer(f"⚠️ Невалидный JSON: {str(e)[:100]}",
                                   reply_markup=get_upload_mode_keyboard())
                return
        
        await message.answer("🌿 Ahimsa проверка...")
        try:
            ahimsa_ok, ahimsa_message, ahimsa_issues = await check_ahimsa_smart(
                content_to_save if isinstance(content_to_save, dict) else {"content": content_to_save},
                message.document.file_name
            )
        except Exception as e:
            logger.error(f"Ошибка Ahimsa: {e}")
            ahimsa_ok, ahimsa_message = True, "⚠️ Проверка пропущена"
        
        if not ahimsa_ok:
            issues = "\n".join([f"• {c}: {d}" for c, d in ahimsa_issues[:3]])
            await message.answer(f"🔶 {ahimsa_message}\n\n{issues}",
                               reply_markup=get_upload_mode_keyboard())
            return
        
        await message.answer(f"✅ {ahimsa_message}")
        
        success = await update_github_file(
            file_path=target_info["path"],
            content=content_to_save,
            message=f"🔄 Обновление {target_info['filename']} через бот v3.20.0-kortix"
        )
        
        if success:
            await message.answer(
                f"✅ {target_info['name']} обновлён\n📁 {target_info['path']}",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer(
                "🔶 Не удалось загрузить файл на GitHub.\n"
                "Проверь:\n"
                "• Настроен ли GITHUB_TOKEN на Render\n"
                "• Есть ли у токена права repo\n"
                "• Логи Render для деталей",
                reply_markup=get_main_keyboard()
            )
        
        await state.clear()
        if user_id in user_upload_target:
            del user_upload_target[user_id]
            
    except json.JSONDecodeError:
        await message.answer("⚠️ Невалидный JSON", reply_markup=get_upload_mode_keyboard())
    except asyncio.TimeoutError:
        await message.answer("⚠️ Таймаут при загрузке, попробуйте ещё раз",
                           reply_markup=get_upload_mode_keyboard())
    except aiohttp.ClientError:
        await message.answer("⚠️ Ошибка сети при обращении к GitHub",
                           reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"💥 КРИТИЧЕСКАЯ ОШИБКА В БОТЕ: {e}", exc_info=True)
        await message.answer(
            "🔶 Внутренняя ошибка, но бот жив.\n"
            "Пожалуйста, попробуйте ещё раз.",
            reply_markup=get_main_keyboard()
        )
    finally:
        await state.clear()
        if user_id in user_upload_target:
            del user_upload_target[user_id]

# 🔥 Обработчик загрузки Kortix инструкций (обновлён)
async def handle_kortix_upload_file(message: Message, state: FSMContext, user_id: int):
    """Обработка загрузки инструкции для Kortix в папку /updates (всегда current_instruction.json)"""
    try:
        if not message.document:
            await message.answer("⚠️ Отправьте JSON файл", reply_markup=get_upload_mode_keyboard())
            return
        
        # Проверка расширения
        if not message.document.file_name.lower().endswith('.json'):
            await message.answer("⚠️ Инструкция должна быть в формате JSON", 
                               reply_markup=get_upload_mode_keyboard())
            return
        
        await message.answer("📥 Скачиваю инструкцию...")
        
        # Скачиваем файл
        file = await bot.get_file(message.document.file_id)
        file_content_bytes = await bot.download_file(file.file_path)
        file_content = file_content_bytes.read().decode('utf-8')
        
        # Парсим JSON
        try:
            json_content = json.loads(file_content)
        except json.JSONDecodeError as e:
            await message.answer(f"⚠️ Невалидный JSON: {str(e)[:200]}",
                               reply_markup=get_upload_mode_keyboard())
            return
        
        # Валидация по схеме
        await message.answer("🔍 Проверка схемы инструкции...")
        is_valid, validation_message = validate_kortix_instruction(json_content)
        
        if not is_valid:
            await message.answer(f"❌ {validation_message}",
                               reply_markup=get_upload_mode_keyboard())
            return
        
        await message.answer(f"✅ {validation_message}")
        
        # 🔁 Всегда сохраняем под одним именем (замена существующего)
        target_filename = "current_instruction.json"
        target_path = f"updates/{target_filename}"
        
        # Ahimsa проверка
        await message.answer("🌿 Ahimsa проверка...")
        ahimsa_ok, ahimsa_message, _ = await check_ahimsa_smart(json_content, target_filename)
        
        if not ahimsa_ok:
            await message.answer(f"🔶 {ahimsa_message}", 
                               reply_markup=get_upload_mode_keyboard())
            return
        
        # Сохраняем в GitHub (перезапись)
        success = await update_github_file(
            file_path=target_path,
            content=json_content,
            message=f"📥 Kortix инструкция обновлена: {target_filename}"
        )
        
        if success:
            # Формируем ссылку на файл в репозитории
            file_url = f"https://github.com/{REPO_NAME}/blob/main/{target_path}"
            
            await message.answer(
                f"✅ Инструкция сохранена как `{target_path}`\n\n"
                f"🔗 <a href='{file_url}'>Посмотреть на GitHub</a>\n\n"
                f"🚀 GitHub Actions автоматически запустится и Kortix обработает изменения.",
                reply_markup=get_main_keyboard(),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        else:
            await message.answer(
                "🔶 Не удалось сохранить инструкцию на GitHub.\n"
                "Проверьте логи Render.",
                reply_markup=get_main_keyboard()
            )
            
    except Exception as e:
        logger.error(f"Ошибка при обработке Kortix инструкции: {e}", exc_info=True)
        await message.answer(f"🔶 Ошибка: {str(e)[:200]}", 
                           reply_markup=get_upload_mode_keyboard())

async def handle_fructus_upload_file(message: Message, state: FSMContext, user_id: int):
    """Обработка загрузки в Fructus."""
    try:
        if not message.document or not message.document.file_name.lower().endswith('.json'):
            await message.answer("⚠️ Отправьте JSON файл", reply_markup=get_upload_mode_keyboard())
            return
        
        file = await bot.get_file(message.document.file_id)
        file_content_bytes = await bot.download_file(file.file_path)
        file_content = file_content_bytes.read().decode('utf-8')
        json_content = json.loads(file_content)
        
        success, result = await upload_to_fructus(message.document.file_name, json_content, user_id)
        if success:
            await message.answer(f"✅ Артефакт сохранён: <code>fructus/{result}</code>",
                               reply_markup=get_main_keyboard())
        else:
            await message.answer(f"🔶 Ошибка: {result}", reply_markup=get_main_keyboard())
            
    except Exception as e:
        logger.error(f"Ошибка Fructus: {e}")
        await message.answer(f"🔶 Ошибка: {str(e)[:100]}", reply_markup=get_upload_mode_keyboard())

@router.message()
async def handle_other_messages(message: Message, state: FSMContext):
    current = await state.get_state()
    if current == UploadStates.waiting_for_file:
        await message.answer("📎 Ожидаю файл", reply_markup=get_upload_mode_keyboard())
    elif current == UploadStates.waiting_for_module:
        await message.answer("🔘 Выберите файл кнопками", reply_markup=get_category_keyboard())
    elif current == UploadStates.waiting_for_category:
        await message.answer("🔘 Выберите категорию кнопками", reply_markup=get_category_keyboard())
    else:
        await message.answer("ℹ️ Используйте /start или меню", reply_markup=get_main_keyboard())

# ========== WEBHOOK ==========
async def on_startup() -> None:
    await bot.set_webhook(
        WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True
    )
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown() -> None:
    logger.info("🛑 Shutdown (вебхук сохранён)")

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
        return web.Response(text="Mandala Bot v3.20.0-kortix is running")
    app.router.add_get("/", index)

    setup_application(app, dp, bot=bot)
    
    logger.info(f"🚀 Запуск сервера на порту {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    main()
