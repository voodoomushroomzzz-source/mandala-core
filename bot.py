#!/usr/bin/env python3
"""
Mandala Sync Terminal Bot v3.19
Render Web Service + Webhook (Aiogram 3)
ИНФРАСТРУКТУРНОЕ ОБНОВЛЕНИЕ:
- Добавлен раздел "⚙️ Инфраструктура"
- Загрузка build_monolith.py и build-monolith.yml
- Полная синхронизация с системой сборки v5.0
"""

import os
import sys
import json
import logging
import uuid
import base64
import asyncio
from datetime import datetime
from typing import Dict, List, Tuple, Optional
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

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден")
    sys.exit(1)

if not RENDER_EXTERNAL_URL:
    logger.error("❌ RENDER_EXTERNAL_URL не задан")
    sys.exit(1)

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
    waiting_for_category = State()      # Выбор категории (модули/инфраструктура)
    waiting_for_module = State()        # Выбор конкретного модуля/файла
    waiting_for_file = State()          # Ожидание файла

class UploadCategory:
    MODULE = "module"          # Основные модули Мандалы
    INFRA = "infra"           # Инфраструктура сборки
    FRUCTUS = "fructus"       # Артефакты

# ========== 🔴 ПОЛНЫЙ СПИСОК МОДУЛЕЙ МАНДАЛЫ ==========
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
    }
}

# ========== 🔴 ИНФРАСТРУКТУРА СБОРКИ ==========
INFRASTRUCTURE_FILES = {
    "build_script": {
        "name": "🔨 Сборщик монолита",
        "filename": "build_monolith.py",
        "path": "build_monolith.py",
        "description": "Скрипт сборки v5.0",
        "category": "infra",
        "validation_hint": "Должен содержать 'Mandala Core Monolith Builder'"
    },
    "github_action": {
        "name": "🤖 GitHub Action",
        "filename": "build-monolith.yml",
        "path": ".github/workflows/build-monolith.yml",
        "description": "Автоматическая сборка",
        "category": "infra",
        "validation_hint": "Должен быть валидным YAML"
    }
}

# ВСЕ ДОСТУПНЫЕ ДЛЯ ЗАГРУЗКИ ФАЙЛЫ
ALL_UPLOAD_TARGETS = {**MANDALA_MODULES, **INFRASTRUCTURE_FILES}

user_upload_target = {}  # user_id -> target_key

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

# ========== 🔴 НОВАЯ КЛАВИАТУРА: ВЫБОР КАТЕГОРИИ ==========
def get_category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧩 Модули Мандалы", callback_data="category_modules")],
        [InlineKeyboardButton(text="⚙️ Инфраструктура сборки", callback_data="category_infra")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

# ========== 🔴 НОВАЯ КЛАВИАТУРА: МОДУЛИ МАНДАЛЫ ==========
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
        [InlineKeyboardButton(text="◀️ Назад к категориям", callback_data="back_to_categories")]
    ])

# ========== 🔴 НОВАЯ КЛАВИАТУРА: ИНФРАСТРУКТУРА ==========
def get_infra_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔨 Сборщик", callback_data="target_build_script"),
            InlineKeyboardButton(text="🤖 GitHub Action", callback_data="target_github_action")
        ],
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

# ========== AHIMSA-ФИЛЬТР (УНИВЕРСАЛЬНЫЙ) ==========
async def check_ahimsa_smart(content: Dict, filename: str = "") -> Tuple[bool, str, List[Tuple[str, str]]]:
    try:
        # Для Python/YAML файлов проверяем только наличие явно опасных фраз
        if filename.endswith(('.py', '.yml', '.yaml')):
            content_str = json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else str(content)
            content_lower = content_str.lower()
            
            problem_phrases = [
                "rm -rf /", "format c:", "rd /s /q",
                "удалить всё", "delete all files",
                "токен", "token", "password", "секрет"
            ]
            
            found_issues = []
            for phrase in problem_phrases:
                if phrase in content_lower:
                    found_issues.append(("⚠️ Потенциально опасная конструкция", f"Найдено: {phrase}"))
            
            if found_issues:
                return False, "🔶 Обнаружены потенциально опасные конструкции", found_issues
            return True, "✅ Инфраструктурный файл прошёл проверку", []
        
        # Для JSON-модулей — стандартная проверка
        code_fields = [
            "complete_source_code", "source_code", "code",
            "content", "technical_specifications", "deployment_instructions",
            "test_scenarios", "ai_replication_guide", "final_verification"
        ]

        text_only_content = {}
        for key, value in content.items():
            if key not in code_fields:
                if isinstance(value, (dict, list)):
                    text_only_content[key] = value
                else:
                    text_only_content[key] = value

        if not text_only_content:
            return True, "✅ Контент содержит только код/технические данные - проверка не требуется", []

        content_str = json.dumps(text_only_content, ensure_ascii=False)
        content_lower = content_str.lower()

        problem_phrases = [
            "применение насилия", "физическое воздействие", "принуждение к работе",
            "эксплуатация человека", "дискриминация по", "унижение достоинства",
            "причинение вреда здоровью", "угроза жизни", "психологическое давление"
        ]

        found_issues = []
        for phrase in problem_phrases:
            if phrase in content_lower:
                idx = content_lower.find(phrase)
                start = max(0, idx - 50)
                end = min(len(content_str), idx + len(phrase) + 50)
                context = content_str[start:end].replace('\n', ' ').replace('\r', ' ')
                context = ' '.join(context.split())
                found_issues.append(("Потенциальное нарушение", f"Фраза '{phrase}' в контексте: ...{context}..."))

        if found_issues:
            return False, "🔶 Обнаружены фразы, требующие внимания", found_issues
        return True, "✅ Текстовый контент соответствует принципам Ahimsa", []

    except Exception as e:
        logger.error(f"Ошибка при проверке Ahimsa: {e}")
        return True, f"⚠️ Проверка пропущена (ошибка: {str(e)[:50]})", []

# ========== GITHUB ФУНКЦИИ ==========
async def update_github_file(file_path: str, content: any, message: str) -> bool:
    """Универсальная функция загрузки любого файла в репозиторий."""
    try:
        url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        async with aiohttp.ClientSession() as session:
            # Получаем текущий SHA файла, если существует
            async with session.get(url, headers=headers) as response:
                sha = None
                if response.status == 200:
                    data = await response.json()
                    sha = data.get("sha")
                elif response.status != 404:
                    logger.error(f"GitHub error: {response.status}")
                    return False

            # Преобразуем контент в base64
            if isinstance(content, dict):
                content_str = json.dumps(content, ensure_ascii=False, indent=2)
            else:
                content_str = str(content)
            
            content_bytes = content_str.encode('utf-8')
            content_base64 = base64.b64encode(content_bytes).decode('utf-8')

            payload = {
                "message": message,
                "content": content_base64,
                "sha": sha
            }

            async with session.put(url, headers=headers, json=payload) as response:
                return response.status in [200, 201]
    except Exception as e:
        logger.error(f"Ошибка в update_github_file: {e}")
        return False

def generate_fructus_filename(original_name: str, file_type: str = "artifact") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = str(uuid.uuid4())[:8]

    if '.' in original_name:
        ext = original_name.split('.')[-1]
        name_without_ext = '.'.join(original_name.split('.')[:-1])
    else:
        ext = "json" if file_type == "artifact" else "txt"
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
        elif "build" in filename_lower or "monolith" in filename_lower:
            file_type = "builder"
        elif "action" in filename_lower or "workflow" in filename_lower:
            file_type = "workflow"
        elif "mandala" in filename_lower or "core" in filename_lower:
            file_type = "mandala"
        elif "log" in filename_lower or "report" in filename_lower:
            file_type = "log"
        elif "export" in filename_lower or "data" in filename_lower:
            file_type = "export"

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
                "source": "mandala_bot_v3.19"
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
        "🌀 <b>Mandala Sync Terminal v3.19</b>\n\n"
        "<b>Инфраструктурное обновление:</b>\n"
        "✅ Загрузка модулей Мандалы (6 модулей)\n"
        "✅ Загрузка инфраструктуры сборки\n"
        "   • 🔨 Сборщик монолита (build_monolith.py)\n"
        "   • 🤖 GitHub Action (build-monolith.yml)\n"
        "✅ Полная синхронизация с системой сборки v5.0\n\n"
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

# ========== 🔴 НОВЫЙ: ОБРАБОТЧИК ЗАГРУЗКИ ФАЙЛА ==========
@router.message(F.text == "📤 Загрузить файл")
async def handle_upload_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    
    await message.answer(
        "📤 <b>Выберите категорию:</b>\n\n"
        "🧩 <b>Модули Мандалы</b> — JSON-кристаллы системы\n"
        "⚙️ <b>Инфраструктура сборки</b> — скрипты и GitHub Actions",
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
        "🍇 <b>Fructus - система артефактов</b>\n"
        "📦 Хранилище: seeds, geometry, builders, workflows, artifacts",
        reply_markup=get_fructus_inline_keyboard()
    )

@router.message(F.text == "ℹ️ Помощь")
async def handle_help(message: Message):
    await message.answer(
        "📚 <b>Mandala Sync Terminal v3.19</b>\n\n"
        "<b>📤 Загрузка файлов:</b>\n"
        "• 🧩 Модули Мандалы — JSON в корень репозитория\n"
        "• ⚙️ Инфраструктура — Python/YAML для сборки\n"
        "• 🍇 Fructus — артефакты в /fructus\n\n"
        "<b>📦 Монолит:</b> скачать полную сборку\n\n"
        "🌿 Ahimsa-фильтр адаптирован для кода",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "🔄 Сменить тип")
async def handle_change_category(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    await state.set_state(UploadStates.waiting_for_category)
    await message.answer(
        "🔄 Выберите категорию:",
        reply_markup=get_category_keyboard()
    )

# ========== ОБРАБОТЧИКИ КОЛБЭКОВ ==========
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
    
    # Разные инструкции в зависимости от типа
    if target_info["category"] == "infra":
        instruction = (
            f"✅ Выбран: {target_info['name']}\n"
            f"📁 Путь: <code>{target_info['path']}</code>\n\n"
            f"📎 Отправьте <b>{target_info['filename']}</b>\n"
            f"⚠️ Проверка Ahimsa будет смягчена для кода"
        )
    else:
        instruction = (
            f"✅ Выбран: {target_info['name']}\n"
            f"📁 Файл: <b>{target_info['filename']}</b>\n\n"
            f"📎 Отправьте JSON файл"
        )
    
    await callback_query.message.edit_text(instruction)
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
        "• Philosophia • Geometria Sacra • Incubae\n\n"
        "🤖 Сборка: GitHub Actions (build-monolith.yml)\n"
        "🔨 Скрипт: build_monolith.py v5.0\n\n"
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
        "• builders — скрипты сборки\n"
        "• workflows — GitHub Actions\n"
        "• artifacts — общие артефакты\n\n"
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

# ========== 🔴 НОВЫЙ: УНИВЕРСАЛЬНАЯ ОБРАБОТКА ФАЙЛОВ ==========
@router.message(StateFilter(UploadStates.waiting_for_file))
async def process_file_upload(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Проверяем, есть ли целевой файл
    if user_id not in user_upload_target:
        await message.answer("⚠️ Сначала выберите категорию и файл", reply_markup=get_category_keyboard())
        await state.set_state(UploadStates.waiting_for_category)
        return

    target_key = user_upload_target[user_id]
    
    # Специальная обработка для Fructus
    if target_key == "fructus":
        await handle_fructus_upload_file(message, state, user_id)
        return
    
    # Проверяем, существует ли целевой файл в нашей конфигурации
    if target_key not in ALL_UPLOAD_TARGETS:
        await message.answer("⚠️ Целевой файл не найден в конфигурации", reply_markup=get_main_keyboard())
        await state.clear()
        return
    
    target_info = ALL_UPLOAD_TARGETS[target_key]
    
    # Проверка наличия файла
    if not message.document:
        await message.answer("⚠️ Отправьте файл", reply_markup=get_upload_mode_keyboard())
        return
    
    # Проверка расширения
    filename = message.document.file_name
    file_ext = filename.lower().split('.')[-1] if '.' in filename else ''
    
    if target_info["category"] == "infra":
        # Для инфраструктуры принимаем .py и .yml/.yaml
        if target_key == "build_script" and file_ext != 'py':
            await message.answer("⚠️ Сборщик должен быть .py файлом", reply_markup=get_upload_mode_keyboard())
            return
        if target_key == "github_action" and file_ext not in ['yml', 'yaml']:
            await message.answer("⚠️ GitHub Action должен быть .yml файлом", reply_markup=get_upload_mode_keyboard())
            return
    else:
        # Для модулей только .json
        if file_ext != 'json':
            await message.answer("⚠️ Модули Мандалы должны быть .json файлами", reply_markup=get_upload_mode_keyboard())
            return
    
    await message.answer(f"📥 Скачиваю {filename}...", reply_markup=get_upload_mode_keyboard())

    try:
        # Скачиваем файл
        file = await bot.get_file(message.document.file_id)
        file_content_bytes = await bot.download_file(file.file_path)
        file_content = file_content_bytes.read().decode('utf-8')
        
        # Парсим контент в зависимости от типа
        if target_info["category"] == "infra":
            # Для инфраструктуры сохраняем как текст
            content_to_save = file_content
            # Проверяем на валидность YAML для GitHub Action
            if target_key == "github_action":
                try:
                    import yaml
                    yaml.safe_load(file_content)
                except ImportError:
                    pass  # yaml не установлен, пропускаем глубокую проверку
                except Exception as e:
                    await message.answer(f"⚠️ Невалидный YAML: {str(e)[:100]}", reply_markup=get_upload_mode_keyboard())
                    return
        else:
            # Для модулей парсим JSON
            try:
                content_to_save = json.loads(file_content)
            except json.JSONDecodeError as e:
                await message.answer(f"⚠️ Невалидный JSON: {str(e)[:100]}", reply_markup=get_upload_mode_keyboard())
                return
        
        # Ahimsa проверка
        await message.answer("🌿 Ahimsa проверка...")
        ahimsa_ok, ahimsa_message, ahimsa_issues = await check_ahimsa_smart(
            content_to_save if isinstance(content_to_save, dict) else {"content": content_to_save},
            filename
        )

        if not ahimsa_ok:
            issues = "\n".join([f"• {c}: {d}" for c, d in ahimsa_issues[:3]])
            await message.answer(f"🔶 {ahimsa_message}\n\n{issues}", reply_markup=get_upload_mode_keyboard())
            return

        await message.answer(f"✅ {ahimsa_message}")

        # Сохраняем в репозиторий
        success = await update_github_file(
            file_path=target_info["path"],
            content=content_to_save,
            message=f"🔄 Обновление {target_info['filename']} через бот v3.19"
        )
        
        if success:
            await message.answer(
                f"✅ {target_info['name']} обновлён\n📁 {target_info['path']}",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer("🔶 Ошибка загрузки на GitHub", reply_markup=get_main_keyboard())

        await state.clear()
        if user_id in user_upload_target:
            del user_upload_target[user_id]

    except Exception as e:
        logger.error(f"Ошибка обработки файла: {e}")
        await message.answer(f"🔶 Ошибка: {str(e)[:100]}", reply_markup=get_main_keyboard())
        await state.clear()

# ========== ОБРАБОТЧИК FRUCTUS (ВЫНЕСЕН ДЛЯ ЧИТАЕМОСТИ) ==========
async def handle_fructus_upload_file(message: Message, state: FSMContext, user_id: int):
    """Обработка загрузки в Fructus."""
    if not message.document:
        await message.answer("⚠️ Отправьте JSON файл", reply_markup=get_upload_mode_keyboard())
        return
    
    if not message.document.file_name.lower().endswith('.json'):
        await message.answer("⚠️ Fructus принимает только .json", reply_markup=get_upload_mode_keyboard())
        return
    
    await message.answer("📥 Скачиваю...", reply_markup=get_upload_mode_keyboard())
    
    try:
        file = await bot.get_file(message.document.file_id)
        file_content_bytes = await bot.download_file(file.file_path)
        file_content = file_content_bytes.read().decode('utf-8')
        json_content = json.loads(file_content)
        
        await message.answer("🌿 Ahimsa проверка...")
        ahimsa_ok, ahimsa_message, ahimsa_issues = await check_ahimsa_smart(json_content)
        
        if not ahimsa_ok:
            issues = "\n".join([f"• {c}: {d}" for c, d in ahimsa_issues[:3]])
            await message.answer(f"🔶 {ahimsa_message}\n\n{issues}", reply_markup=get_upload_mode_keyboard())
            return
        
        await message.answer(f"✅ {ahimsa_message}")
        
        success, result = await upload_to_fructus(message.document.file_name, json_content, user_id)
        if success:
            await message.answer(f"✅ Артефакт сохранён: <code>fructus/{result}</code>", reply_markup=get_main_keyboard())
        else:
            await message.answer(f"🔶 Ошибка: {result}", reply_markup=get_main_keyboard())
        
        await state.clear()
        if user_id in user_upload_target:
            del user_upload_target[user_id]
            
    except json.JSONDecodeError:
        await message.answer("⚠️ Невалидный JSON", reply_markup=get_upload_mode_keyboard())
    except Exception as e:
        logger.error(f"Ошибка Fructus: {e}")
        await message.answer(f"🔶 Ошибка: {str(e)[:100]}", reply_markup=get_main_keyboard())
        await state.clear()

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
        return web.Response(text="Mandala Bot v3.19 is running")
    app.router.add_get("/", index)

    setup_application(app, dp, bot=bot)
    
    logger.info(f"🚀 Запуск сервера на порту {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    main()
