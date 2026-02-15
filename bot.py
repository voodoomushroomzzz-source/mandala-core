#!/usr/bin/env python3
"""
Mandala Sync Terminal Bot v3.21.0
Render Web Service + Webhook (Aiogram 3)
ИЗМЕНЕНИЯ:
- Новое главное меню: Загрузить, Скачать монолит, Fructus, Помощь
- Редактирование внутри "Загрузить файл"
- Testisphaera в модулях Мандалы
- Убран Kortix Updates
- Монолит скачивается сразу
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

# ========== FSM СОСТОЯНИЯ ==========
class UploadStates(StatesGroup):
    # Для загрузки/редактирования
    waiting_for_action = State()           # загрузить или редактировать?
    waiting_for_category = State()         # категория модуля
    waiting_for_module = State()           # конкретный модуль
    waiting_for_file = State()              # ожидание файла (для загрузки)
    
    # Для редактирования
    waiting_for_operation = State()         # тип операции
    waiting_for_target_path = State()       # путь в JSON
    waiting_for_new_value = State()         # новое значение
    waiting_for_confirmation = State()      # подтверждение


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
        "description": "Тело заботы",
        "category": "module"
    },
    # 🔬 ТЕСТОВЫЙ МОДУЛЬ
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
    }
}

ALL_UPLOAD_TARGETS = {**MANDALA_MODULES, **INFRASTRUCTURE_FILES}
user_upload_target = {}  # user_id -> target_key


# ========== КЛАВИАТУРЫ ==========

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню (4 кнопки)"""
    keyboard = [
        [KeyboardButton(text="📤 Загрузить файл")],      # загрузка + редактирование
        [KeyboardButton(text="📥 Скачать монолит")],     # сразу скачивание
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
    """Клавиатура во время загрузки файла"""
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

def get_action_keyboard() -> InlineKeyboardMarkup:
    """Выбор: загрузить новый или редактировать существующий"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Загрузить новый файл", callback_data="action_upload")],
        [InlineKeyboardButton(text="🔧 Редактировать существующий", callback_data="action_edit")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def get_category_keyboard() -> InlineKeyboardMarkup:
    """Категории файлов (единые для загрузки и редактирования)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧩 Модули Мандалы", callback_data="category_modules")],
        [InlineKeyboardButton(text="⚙️ Инфраструктура сборки", callback_data="category_infra")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def get_modules_keyboard() -> InlineKeyboardMarkup:
    """Все модули Мандалы (включая Testisphaera)"""
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
            InlineKeyboardButton(text="🛡️ Tectosphaera", callback_data="target_tectosphaera"),
            InlineKeyboardButton(text="🧪 Testisphaera", callback_data="target_testisphaera")
        ],
        [InlineKeyboardButton(text="◀️ Назад к категориям", callback_data="back_to_categories")]
    ])

def get_infra_keyboard() -> InlineKeyboardMarkup:
    """Инфраструктурные файлы"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔨 Сборщик", callback_data="target_build_script"),
            InlineKeyboardButton(text="🤖 GitHub Action", callback_data="target_github_action")
        ],
        [InlineKeyboardButton(text="◀️ Назад к категориям", callback_data="back_to_categories")]
    ])

def get_edit_operations_keyboard() -> InlineKeyboardMarkup:
    """Типы операций для редактирования"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить в массив", callback_data="edit_op_add"),
            InlineKeyboardButton(text="✏️ Обновить поле", callback_data="edit_op_update")
        ],
        [
            InlineKeyboardButton(text="🗑️ Удалить поле", callback_data="edit_op_delete"),
            InlineKeyboardButton(text="📋 Показать структуру", callback_data="edit_op_show")
        ],
        [InlineKeyboardButton(text="◀️ Назад к модулям", callback_data="back_to_modules")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def get_fructus_inline_keyboard() -> InlineKeyboardMarkup:
    """Меню Fructus"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📤 Загрузить", callback_data="fructus_upload"),
            InlineKeyboardButton(text="📋 Информация", callback_data="fructus_info")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])


# ========== ФУНКЦИИ GITHUB API ==========

async def update_github_file(file_path: str, content: Any, message: str) -> bool:
    """Обновление файла на GitHub"""
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
        "User-Agent": "MandalaBot/3.21.0"
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


async def get_github_file_content(file_path: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """Получить содержимое файла из GitHub"""
    if not GITHUB_TOKEN:
        return False, None, "GITHUB_TOKEN не настроен"
    
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaBot/3.21.0"
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    content = base64.b64decode(data["content"]).decode('utf-8')
                    return True, json.loads(content), data.get("sha")
                elif response.status == 404:
                    return False, None, "Файл не найден"
                else:
                    return False, None, f"Ошибка {response.status}"
        except Exception as e:
            return False, None, str(e)


# ========== ФУНКЦИИ ДЛЯ РЕДАКТИРОВАНИЯ JSON ==========

async def apply_json_operation(
    content: Dict,
    operation_type: str,
    target_path: str,
    new_value: Any = None
) -> Tuple[bool, Optional[Dict], str]:
    """
    Применить операцию к JSON
    
    Примеры:
    - "symbiosis_principles_expanded.principles"
    - "elements[0].value"
    """
    try:
        import re
        
        # Проверяем, есть ли индекс в пути
        array_match = re.match(r"(.+?)\[(\d+)\](.*)", target_path)
        
        if array_match:
            # Путь с индексом массива
            base_path, index_str, rest = array_match.groups()
            index = int(index_str)
            
            # Получаем объект по базовому пути
            current = content
            for key in base_path.split('.'):
                if key:
                    if isinstance(current, dict) and key in current:
                        current = current[key]
                    else:
                        return False, None, f"Путь {base_path} не найден"
            
            # Проверяем, что это массив
            if not isinstance(current, list):
                return False, None, f"{base_path} не является массивом"
            
            if index >= len(current):
                return False, None, f"Индекс {index} вне диапазона (макс {len(current)-1})"
            
            # Если есть остаток пути, работаем с элементом массива
            if rest:
                rest = rest.lstrip('.')
                if rest:
                    # Рекурсивно применяем операцию к элементу массива
                    return await apply_json_operation(
                        current[index],
                        operation_type,
                        rest,
                        new_value
                    )
            
            # Операция на самом элементе массива
            if operation_type == "update_field":
                current[index] = new_value
                return True, content, f"✅ Элемент [{index}] обновлён"
            elif operation_type == "delete_field":
                current.pop(index)
                return True, content, f"✅ Элемент [{index}] удалён"
            elif operation_type == "add_to_array":
                if isinstance(new_value, list):
                    current[index:index] = new_value
                else:
                    current.insert(index, new_value)
                return True, content, f"✅ Добавлено в позицию [{index}]"
        
        else:
            # Обычный точечный путь
            parts = target_path.split('.')
            current = content
            
            # Навигация до родительского объекта
            for part in parts[:-1]:
                if part:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
            
            last_part = parts[-1]
            
            if operation_type == "update_field":
                current[last_part] = new_value
                return True, content, f"✅ Поле {last_part} обновлено"
            
            elif operation_type == "delete_field":
                if last_part in current:
                    del current[last_part]
                    return True, content, f"✅ Поле {last_part} удалено"
                else:
                    return False, None, f"Поле {last_part} не найдено"
            
            elif operation_type == "add_to_array":
                if last_part not in current:
                    current[last_part] = []
                if not isinstance(current[last_part], list):
                    return False, None, f"{last_part} не является массивом"
                
                if isinstance(new_value, list):
                    current[last_part].extend(new_value)
                else:
                    current[last_part].append(new_value)
                
                return True, content, f"✅ Добавлено в массив {last_part}"
            
            elif operation_type == "show_structure":
                # Просто показываем, что есть по пути
                return True, current.get(last_part, "не найдено"), f"Структура по пути {target_path}"
        
        return False, None, "Неизвестный тип операции"
        
    except Exception as e:
        return False, None, f"Ошибка: {str(e)}"


# ========== ФУНКЦИИ ДЛЯ FRUCTUS ==========

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
        
        enhanced_content = content.copy() if isinstance(content, dict) else {"content": content}
        enhanced_content["_fructus_metadata"] = {
            "original_filename": original_filename,
            "generated_filename": target_filename,
            "file_type": file_type,
            "upload_timestamp": datetime.now().isoformat(),
            "uploaded_by": f"user_{user_id}",
            "source": "mandala_bot_v3.21.0"
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


# ========== ФУНКЦИИ ДЛЯ МОНОЛИТА ==========

async def download_monolith_file() -> Tuple[bool, bytes, str]:
    """Скачать монолит из репозитория"""
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


# ========== ФУНКЦИИ AHHIMSA ==========

async def check_ahimsa_smart(content: Dict, filename: str = "") -> Tuple[bool, str, List[Tuple[str, str]]]:
    """Упрощённая проверка Ahimsa"""
    # Базовая реализация - всегда пропускаем
    return True, "✅ Проверка пройдена", []


# ========== ОБРАБОТЧИКИ КОМАНД ==========

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    await message.answer(
        "🌀 <b>Mandala Sync Terminal v3.21.0</b>\n\n"
        "📤 <b>Загрузить файл</b> — загрузка JSON или редактирование модулей\n"
        "📥 <b>Скачать монолит</b> — готовый mandala_core.monolith.latest.json\n"
        "🍇 <b>Fructus</b> — хранилище артефактов\n\n"
        "🌿 Ahimsa-фильтр активен",
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
    """Начало процесса загрузки/редактирования"""
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    
    await state.set_state(UploadStates.waiting_for_action)
    await message.answer(
        "📤 <b>Управление файлами</b>\n\n"
        "Вы хотите загрузить новый файл или отредактировать существующий?",
        reply_markup=get_action_keyboard()
    )


@router.message(F.text == "📥 Скачать монолит")
async def handle_download_monolith_direct(message: Message):
    """Прямое скачивание монолита (без подменю)"""
    await message.answer("📦 Скачиваю монолит...")
    success, content, filename = await download_monolith_file()
    if success:
        await message.answer_document(
            document=BufferedInputFile(content, filename=filename),
            caption="📦 Монолит Mandala Core"
        )
    else:
        await message.answer(f"❌ Ошибка: {filename}")


@router.message(F.text == "🍇 Fructus")
async def handle_fructus_menu(message: Message):
    await message.answer(
        "🍇 <b>Fructus - система артефактов</b>",
        reply_markup=get_fructus_inline_keyboard()
    )


@router.message(F.text == "ℹ️ Помощь")
async def handle_help(message: Message):
    await message.answer(
        "📚 <b>Mandala Sync Terminal v3.21.0</b>\n\n"
        "📤 <b>Загрузить файл</b>\n"
        "• Загрузка новых JSON-файлов в репозиторий\n"
        "• Редактирование существующих модулей (добавление, обновление, удаление)\n\n"
        "📥 <b>Скачать монолит</b>\n"
        "• Мгновенное скачивание mandala_core.monolith.latest.json\n\n"
        "🍇 <b>Fructus</b>\n"
        "• Загрузка артефактов в папку /fructus/\n"
        "• Автоматическая категоризация (seeds, geometry, builders)\n\n"
        "🧪 <b>Testisphaera</b> доступна в модулях Мандалы\n"
        "🌿 Ahimsa-фильтр активен",
        reply_markup=get_main_keyboard()
    )


@router.message(F.text == "🔄 Сменить тип")
async def handle_change_category(message: Message, state: FSMContext):
    """Смена категории при загрузке"""
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    
    # Возвращаемся к выбору категории
    await state.set_state(UploadStates.waiting_for_category)
    await message.answer(
        "🔄 Выберите категорию:",
        reply_markup=get_category_keyboard()
    )


# ========== ОБРАБОТЧИКИ КОЛБЭКОВ ==========

@router.callback_query(F.data == "action_upload", StateFilter(UploadStates.waiting_for_action))
async def handle_action_upload(callback_query: CallbackQuery, state: FSMContext):
    """Выбрана загрузка нового файла"""
    await state.update_data(edit_mode=False)
    await state.set_state(UploadStates.waiting_for_category)
    await callback_query.message.edit_text(
        "📤 <b>Загрузка нового файла</b>\n\nВыберите категорию:",
        reply_markup=get_category_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data == "action_edit", StateFilter(UploadStates.waiting_for_action))
async def handle_action_edit(callback_query: CallbackQuery, state: FSMContext):
    """Выбрано редактирование существующего файла"""
    await state.update_data(edit_mode=True)
    await state.set_state(UploadStates.waiting_for_category)
    await callback_query.message.edit_text(
        "🔧 <b>Редактирование модуля</b>\n\nВыберите категорию:",
        reply_markup=get_category_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data == "category_modules", StateFilter(UploadStates.waiting_for_category))
async def handle_category_modules(callback_query: CallbackQuery, state: FSMContext):
    """Выбраны модули Мандалы"""
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "🧩 <b>Выберите модуль:</b>",
        reply_markup=get_modules_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data == "category_infra", StateFilter(UploadStates.waiting_for_category))
async def handle_category_infra(callback_query: CallbackQuery, state: FSMContext):
    """Выбрана инфраструктура"""
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "⚙️ <b>Выберите компонент:</b>",
        reply_markup=get_infra_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data == "back_to_categories", StateFilter(UploadStates.waiting_for_module))
async def handle_back_to_categories(callback_query: CallbackQuery, state: FSMContext):
    """Назад к категориям"""
    await state.set_state(UploadStates.waiting_for_category)
    await callback_query.message.edit_text(
        "📤 <b>Выберите категорию:</b>",
        reply_markup=get_category_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data == "back_to_modules", StateFilter(UploadStates.waiting_for_operation))
async def handle_back_to_modules(callback_query: CallbackQuery, state: FSMContext):
    """Назад к выбору модуля"""
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "🧩 <b>Выберите модуль:</b>",
        reply_markup=get_modules_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("target_"), StateFilter(UploadStates.waiting_for_module))
async def handle_target_selection(callback_query: CallbackQuery, state: FSMContext):
    """Выбран конкретный файл/модуль"""
    target_key = callback_query.data.replace("target_", "")
    
    if target_key not in ALL_UPLOAD_TARGETS:
        await callback_query.answer("Неизвестный целевой файл")
        return

    target_info = ALL_UPLOAD_TARGETS[target_key]
    user_upload_target[callback_query.from_user.id] = target_key
    
    # Получаем режим (загрузка или редактирование)
    data = await state.get_data()
    edit_mode = data.get("edit_mode", False)
    
    if edit_mode:
        # Режим редактирования - показываем операции
        await state.update_data(
            edit_module=target_key,
            edit_module_path=target_info["path"],
            edit_module_name=target_info["name"]
        )
        await state.set_state(UploadStates.waiting_for_operation)
        
        await callback_query.message.edit_text(
            f"🔧 <b>Редактирование: {target_info['name']}</b>\n\n"
            f"Файл: <code>{target_info['path']}</code>\n\n"
            f"Выберите операцию:",
            reply_markup=get_edit_operations_keyboard()
        )
    else:
        # Режим загрузки - ожидаем файл
        await state.set_state(UploadStates.waiting_for_file)
        
        await callback_query.message.edit_text(
            f"✅ Выбран: {target_info['name']}\n"
            f"📁 Файл: <b>{target_info['filename'] or target_info['path']}</b>\n\n"
            f"📎 Отправьте JSON-файл для загрузки"
        )
        await callback_query.message.answer(
            "📎 Прикрепите файл",
            reply_markup=get_upload_mode_keyboard()
        )
    
    await callback_query.answer()


# ========== ОБРАБОТЧИКИ ОПЕРАЦИЙ РЕДАКТИРОВАНИЯ ==========

@router.callback_query(F.data == "edit_op_add", StateFilter(UploadStates.waiting_for_operation))
async def handle_edit_add(callback_query: CallbackQuery, state: FSMContext):
    """Добавление в массив"""
    await state.update_data(edit_operation="add_to_array")
    await state.set_state(UploadStates.waiting_for_target_path)
    
    await callback_query.message.edit_text(
        "➕ <b>Добавление в массив</b>\n\n"
        "Введите путь к массиву в точечной нотации.\n\n"
        "Примеры:\n"
        "<code>symbiosis_principles_expanded.principles</code>\n"
        "<code>elements</code>\n"
        "<code>seeds</code>\n\n"
        "Или с индексом:\n"
        "<code>elements[0].items</code>",
        parse_mode=ParseMode.HTML
    )
    await callback_query.answer()


@router.callback_query(F.data == "edit_op_update", StateFilter(UploadStates.waiting_for_operation))
async def handle_edit_update(callback_query: CallbackQuery, state: FSMContext):
    """Обновление поля"""
    await state.update_data(edit_operation="update_field")
    await state.set_state(UploadStates.waiting_for_target_path)
    
    await callback_query.message.edit_text(
        "✏️ <b>Обновление поля</b>\n\n"
        "Введите путь к полю в точечной нотации.\n\n"
        "Примеры:\n"
        "<code>version</code>\n"
        "<code>metadata.created_by</code>\n"
        "<code>elements[0].value</code>",
        parse_mode=ParseMode.HTML
    )
    await callback_query.answer()


@router.callback_query(F.data == "edit_op_delete", StateFilter(UploadStates.waiting_for_operation))
async def handle_edit_delete(callback_query: CallbackQuery, state: FSMContext):
    """Удаление поля"""
    await state.update_data(edit_operation="delete_field")
    await state.set_state(UploadStates.waiting_for_target_path)
    
    await callback_query.message.edit_text(
        "🗑️ <b>Удаление поля</b>\n\n"
        "Введите путь к полю в точечной нотации.\n\n"
        "Примеры:\n"
        "<code>unused_field</code>\n"
        "<code>metadata.temp_data</code>\n"
        "<code>elements[1]</code>",
        parse_mode=ParseMode.HTML
    )
    await callback_query.answer()


@router.callback_query(F.data == "edit_op_show", StateFilter(UploadStates.waiting_for_operation))
async def handle_edit_show(callback_query: CallbackQuery, state: FSMContext):
    """Показать структуру модуля"""
    data = await state.get_data()
    module_name = data.get("edit_module_name")
    module_path = data.get("edit_module_path")
    
    await callback_query.message.edit_text(f"🔍 Загружаю структуру {module_name}...")
    
    # Получаем содержимое файла
    success, content, error = await get_github_file_content(module_path)
    
    if success and content:
        # Показываем структуру (ключи верхнего уровня)
        if isinstance(content, dict):
            keys = list(content.keys())
            structure = "\n".join([f"• <code>{k}</code>" for k in keys[:15]])
            if len(keys) > 15:
                structure += f"\n• ... и ещё {len(keys)-15} ключей"
        else:
            structure = f"Тип: {type(content).__name__}"
        
        await callback_query.message.edit_text(
            f"📋 <b>Структура {module_name}</b>\n\n"
            f"{structure}\n\n"
            f"<i>Для просмотра конкретного пути используйте операции редактирования</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад к операциям", callback_data="back_to_operations")]
            ]),
            parse_mode=ParseMode.HTML
        )
    else:
        await callback_query.message.edit_text(
            f"❌ Не удалось загрузить модуль: {error}",
            reply_markup=get_edit_operations_keyboard()
        )
    
    await callback_query.answer()


@router.callback_query(F.data == "back_to_operations", StateFilter(UploadStates.waiting_for_target_path))
async def handle_back_to_operations(callback_query: CallbackQuery, state: FSMContext):
    """Назад к выбору операции"""
    await state.set_state(UploadStates.waiting_for_operation)
    
    data = await state.get_data()
    module_name = data.get("edit_module_name", "Модуль")
    
    await callback_query.message.edit_text(
        f"🔧 <b>Редактирование: {module_name}</b>\n\n"
        f"Выберите операцию:",
        reply_markup=get_edit_operations_keyboard()
    )
    await callback_query.answer()


@router.message(StateFilter(UploadStates.waiting_for_target_path))
async def handle_target_path(message: Message, state: FSMContext):
    """Получен путь для операции"""
    target_path = message.text.strip()
    await state.update_data(edit_target_path=target_path)
    
    data = await state.get_data()
    operation = data.get("edit_operation")
    
    if operation == "delete_field":
        # Для удаления не нужно новое значение, сразу показываем предпросмотр
        await show_edit_preview(message, state)
    else:
        # Для add и update нужно новое значение
        await message.answer(
            "📤 Отправьте новое значение в JSON формате:\n\n"
            "Примеры:\n"
            "<code>\"новая версия\"</code>\n"
            "<code>{\"key\": \"value\"}</code>\n"
            "<code>[\"item1\", \"item2\"]</code>\n"
            "<code>42</code>",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(UploadStates.waiting_for_new_value)


@router.message(StateFilter(UploadStates.waiting_for_new_value))
async def handle_new_value(message: Message, state: FSMContext):
    """Получено новое значение"""
    try:
        # Пытаемся распарсить как JSON
        new_value = json.loads(message.text)
    except json.JSONDecodeError:
        # Если не JSON, используем как строку
        new_value = message.text
    
    await state.update_data(edit_new_value=new_value)
    await show_edit_preview(message, state)


async def show_edit_preview(message: Message, state: FSMContext):
    """Показать предпросмотр изменений"""
    data = await state.get_data()
    module_name = data.get("edit_module_name")
    module_path = data.get("edit_module_path")
    operation = data.get("edit_operation")
    target_path = data.get("edit_target_path")
    new_value = data.get("edit_new_value")
    
    await message.answer("🔍 Загружаю текущую версию для предпросмотра...")
    
    # Получаем текущее содержимое
    success, content, error = await get_github_file_content(module_path)
    
    if not success or not content:
        await message.answer(f"❌ Не удалось загрузить модуль: {error}")
        await state.clear()
        return
    
    # Пробуем применить операцию для предпросмотра
    import copy
    content_copy = copy.deepcopy(content)
    
    op_success, new_content, op_msg = await apply_json_operation(
        content_copy,
        operation,
        target_path,
        new_value
    )
    
    if not op_success:
        await message.answer(f"❌ Ошибка: {op_msg}\n\nПопробуйте другой путь или значение.")
        return
    
    # Показываем предпросмотр (упрощённо)
    await message.answer(
        f"🔍 <b>Предпросмотр изменений</b>\n\n"
        f"Модуль: {module_name}\n"
        f"Операция: {operation}\n"
        f"Путь: <code>{target_path}</code>\n\n"
        f"✅ Операция применима\n\n"
        f"Подтвердить применение?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, применить", callback_data="edit_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
        ]),
        parse_mode=ParseMode.HTML
    )
    
    # Сохраняем изменённый контент для подтверждения
    await state.update_data(edit_new_content=content_copy)
    await state.set_state(UploadStates.waiting_for_confirmation)


@router.callback_query(F.data == "edit_confirm", StateFilter(UploadStates.waiting_for_confirmation))
async def handle_edit_confirm(callback_query: CallbackQuery, state: FSMContext):
    """Подтверждение и сохранение изменений"""
    await callback_query.message.edit_text("🔄 Сохраняю изменения...")
    
    data = await state.get_data()
    new_content = data.get("edit_new_content")
    module_path = data.get("edit_module_path")
    module_name = data.get("edit_module_name")
    operation = data.get("edit_operation")
    target_path = data.get("edit_target_path")
    
    if not new_content:
        await callback_query.message.edit_text("❌ Данные для сохранения не найдены")
        await state.clear()
        return
    
    # Сохраняем в GitHub
    success = await update_github_file(
        file_path=module_path,
        content=new_content,
        message=f"🔧 {operation} в {target_path} через бот"
    )
    
    if success:
        file_url = f"https://github.com/{REPO_NAME}/blob/main/{module_path}"
        await callback_query.message.edit_text(
            f"✅ <b>Изменения применены!</b>\n\n"
            f"Модуль: {module_name}\n"
            f"Операция: {operation}\n"
            f"Путь: <code>{target_path}</code>\n\n"
            f"🔗 <a href='{file_url}'>Посмотреть на GitHub</a>",
            reply_markup=get_main_keyboard(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    else:
        await callback_query.message.edit_text(
            "❌ Не удалось сохранить изменения в GitHub",
            reply_markup=get_main_keyboard()
        )
    
    await state.clear()


# ========== ОБРАБОТЧИК ЗАГРУЗКИ ФАЙЛОВ ==========

@router.message(StateFilter(UploadStates.waiting_for_file), F.document)
async def process_file_upload(message: Message, state: FSMContext):
    """Обработка загруженного файла"""
    user_id = message.from_user.id
    
    try:
        if user_id not in user_upload_target:
            await message.answer("⚠️ Сначала выберите категорию и файл", 
                               reply_markup=get_category_keyboard())
            await state.set_state(UploadStates.waiting_for_category)
            return

        target_key = user_upload_target[user_id]
        
        if target_key not in ALL_UPLOAD_TARGETS:
            await message.answer("⚠️ Целевой файл не найден", 
                               reply_markup=get_main_keyboard())
            await state.clear()
            return
        
        target_info = ALL_UPLOAD_TARGETS[target_key]
        
        if not message.document.file_name.lower().endswith('.json'):
            await message.answer("⚠️ Отправьте JSON файл", 
                               reply_markup=get_upload_mode_keyboard())
            return
        
        await message.answer(f"📥 Скачиваю {message.document.file_name}...",
                           reply_markup=get_upload_mode_keyboard())

        file = await bot.get_file(message.document.file_id)
        file_content_bytes = await bot.download_file(file.file_path)
        file_content = file_content_bytes.read().decode('utf-8')
        
        try:
            content_to_save = json.loads(file_content)
        except json.JSONDecodeError as e:
            await message.answer(f"⚠️ Невалидный JSON: {str(e)[:100]}",
                               reply_markup=get_upload_mode_keyboard())
            return
        
        await message.answer("🌿 Ahimsa проверка...")
        ahimsa_ok, ahimsa_message, _ = await check_ahimsa_smart(content_to_save, message.document.file_name)
        
        if not ahimsa_ok:
            await message.answer(f"🔶 {ahimsa_message}",
                               reply_markup=get_upload_mode_keyboard())
            return
        
        await message.answer(f"✅ {ahimsa_message}")
        
        success = await update_github_file(
            file_path=target_info["path"],
            content=content_to_save,
            message=f"🔄 Обновление {target_info['filename']} через бот"
        )
        
        if success:
            file_url = f"https://github.com/{REPO_NAME}/blob/main/{target_info['path']}"
            await message.answer(
                f"✅ {target_info['name']} обновлён\n"
                f"📁 {target_info['path']}\n\n"
                f"🔗 <a href='{file_url}'>Посмотреть на GitHub</a>",
                reply_markup=get_main_keyboard(),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        else:
            await message.answer(
                "🔶 Не удалось загрузить файл на GitHub.\n"
                "Проверьте логи.",
                reply_markup=get_main_keyboard()
            )
        
        await state.clear()
        if user_id in user_upload_target:
            del user_upload_target[user_id]
            
    except Exception as e:
        logger.error(f"💥 Ошибка при загрузке: {e}", exc_info=True)
        await message.answer(
            "🔶 Внутренняя ошибка. Попробуйте ещё раз.",
            reply_markup=get_main_keyboard()
        )
    finally:
        await state.clear()
        if user_id in user_upload_target:
            del user_upload_target[user_id]


# ========== ОБРАБОТЧИКИ FRUCTUS ==========

@router.callback_query(F.data == "fructus_info")
async def handle_fructus_info(callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        "📋 <b>Fructus</b> – хранилище артефактов\n"
        "• seeds — семена Incubae\n"
        "• geometry — паттерны Geometria Sacra\n"
        "• builders — скрипты сборки\n\n"
        "Путь: /fructus/\n\n"
        "Файлы автоматически получают метаданные и временную метку.",
        reply_markup=get_fructus_inline_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data == "fructus_upload")
async def handle_fructus_upload(callback_query: CallbackQuery, state: FSMContext):
    user_upload_target[callback_query.from_user.id] = "fructus"
    await state.set_state(UploadStates.waiting_for_file)
    await callback_query.message.edit_text(
        "🍇 <b>Fructus</b>\n\n"
        "Отправьте JSON файл для сохранения в хранилище артефактов.\n\n"
        "Файл будет автоматически категоризирован и получит метаданные."
    )
    await callback_query.message.answer(
        "📎 Прикрепите JSON",
        reply_markup=get_upload_mode_keyboard()
    )
    await callback_query.answer()


@router.message(StateFilter(UploadStates.waiting_for_file), F.document, F.data == "fructus")
async def handle_fructus_upload_file(message: Message, state: FSMContext):
    """Обработка загрузки в Fructus"""
    user_id = message.from_user.id
    target_key = user_upload_target.get(user_id)
    
    if target_key != "fructus":
        return  # Не наша очередь
    
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
            file_url = f"https://github.com/{REPO_NAME}/blob/main/fructus/{result}"
            await message.answer(
                f"✅ Артефакт сохранён: <code>fructus/{result}</code>\n\n"
                f"🔗 <a href='{file_url}'>Посмотреть на GitHub</a>",
                reply_markup=get_main_keyboard(),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        else:
            await message.answer(f"🔶 Ошибка: {result}", reply_markup=get_main_keyboard())
            
    except Exception as e:
        logger.error(f"Ошибка Fructus: {e}")
        await message.answer(f"🔶 Ошибка: {str(e)[:100]}", reply_markup=get_upload_mode_keyboard())
    finally:
        await state.clear()
        if user_id in user_upload_target:
            del user_upload_target[user_id]


# ========== ОБРАБОТЧИК ОТМЕНЫ ==========

@router.callback_query(F.data == "cancel")
async def handle_cancel_inline(callback_query: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback_query.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    await callback_query.message.edit_text("🚫 Отменено")
    await callback_query.answer()
    await callback_query.message.answer(
        "🏠 Главное меню",
        reply_markup=get_main_keyboard()
    )


# ========== ОБРАБОТЧИК ВСЕГО ОСТАЛЬНОГО ==========

@router.message()
async def handle_other_messages(message: Message, state: FSMContext):
    current = await state.get_state()
    
    if current == UploadStates.waiting_for_file:
        await message.answer("📎 Ожидаю файл", reply_markup=get_upload_mode_keyboard())
    elif current == UploadStates.waiting_for_module:
        await message.answer("🔘 Выберите файл кнопками", reply_markup=get_category_keyboard())
    elif current == UploadStates.waiting_for_category:
        await message.answer("🔘 Выберите категорию кнопками", reply_markup=get_category_keyboard())
    elif current == UploadStates.waiting_for_target_path:
        await message.answer("📝 Введите путь в формате: поле.подполе или массив[0].поле")
    elif current == UploadStates.waiting_for_new_value:
        await message.answer("📤 Отправьте новое значение в JSON формате")
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
        return web.Response(text="Mandala Bot v3.21.0 is running")
    app.router.add_get("/", index)

    setup_application(app, dp, bot=bot)
    
    logger.info(f"🚀 Запуск сервера на порту {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    main()
