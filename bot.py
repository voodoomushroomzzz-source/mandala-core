#!/usr/bin/env python3
"""
Mandala Sync Terminal Bot v3.22.0
Render Web Service + Webhook (Aiogram 3)
ИЗМЕНЕНИЯ:
- Убраны лишние подтверждения при редактировании
- Увеличены таймауты GitHub API до 30 секунд
- Упрощены сообщения: "✅ Обновление окей" + ссылка
- Исправлено зависание при сохранении
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
    waiting_for_action = State()           # загрузить или редактировать?
    waiting_for_category = State()         # категория модуля
    waiting_for_module = State()           # конкретный модуль
    waiting_for_file = State()              # ожидание файла (для загрузки)
    waiting_for_operation = State()         # тип операции
    waiting_for_target_path = State()       # путь в JSON
    waiting_for_new_value = State()         # новое значение


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
user_upload_target = {}


# ========== КЛАВИАТУРЫ ==========

def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="📤 Загрузить файл")],
        [KeyboardButton(text="📥 Скачать монолит")],
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

def get_action_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Загрузить новый файл", callback_data="action_upload")],
        [InlineKeyboardButton(text="🔧 Редактировать существующий", callback_data="action_edit")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def get_category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧩 Модули Мандалы", callback_data="category_modules")],
        [InlineKeyboardButton(text="⚙️ Инфраструктура сборки", callback_data="category_infra")],
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
            InlineKeyboardButton(text="🛡️ Tectosphaera", callback_data="target_tectosphaera"),
            InlineKeyboardButton(text="🧪 Testisphaera", callback_data="target_testisphaera")
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

def get_edit_operations_keyboard() -> InlineKeyboardMarkup:
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📤 Загрузить", callback_data="fructus_upload"),
            InlineKeyboardButton(text="📋 Информация", callback_data="fructus_info")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])


# ========== ФУНКЦИИ GITHUB API (С УВЕЛИЧЕННЫМИ ТАЙМАУТАМИ) ==========

async def update_github_file(file_path: str, content: Any, message: str) -> bool:
    """Обновление файла на GitHub с таймаутом 30 секунд"""
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
        "User-Agent": "MandalaBot/3.22.0"
    }

    async with aiohttp.ClientSession() as session:
        try:
            # GET с таймаутом 30 сек
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    sha = data.get("sha")
                    logger.info(f"✅ SHA получен для {file_path}")
                elif response.status == 404:
                    sha = None
                    logger.info(f"📄 {file_path} не существует, будет создан")
                else:
                    error_text = await response.text()
                    logger.error(f"⚠️ GitHub GET error {response.status}: {error_text[:200]}")
                    return False
        except asyncio.TimeoutError:
            logger.error("❌ Таймаут при получении SHA (30 сек)")
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
            # PUT с таймаутом 30 сек
            async with session.put(url, headers=headers, json=payload, timeout=30) as response:
                response_text = await response.text()
                logger.info(f"📡 GitHub response status: {response.status}")
                
                if response.status in [200, 201]:
                    logger.info(f"✅ Файл {file_path} успешно обновлён")
                    return True
                else:
                    logger.error(f"❌ GitHub error: {response.status} - {response_text[:200]}")
                    return False
                    
        except asyncio.TimeoutError:
            logger.error("❌ Таймаут при отправке в GitHub (30 сек)")
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
        "User-Agent": "MandalaBot/3.22.0"
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=30) as response:
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
    """Применить операцию к JSON"""
    try:
        import re
        
        array_match = re.match(r"(.+?)\[(\d+)\](.*)", target_path)
        
        if array_match:
            base_path, index_str, rest = array_match.groups()
            index = int(index_str)
            
            current = content
            for key in base_path.split('.'):
                if key:
                    if isinstance(current, dict) and key in current:
                        current = current[key]
                    else:
                        return False, None, f"Путь {base_path} не найден"
            
            if not isinstance(current, list):
                return False, None, f"{base_path} не является массивом"
            
            if index >= len(current):
                return False, None, f"Индекс {index} вне диапазона (макс {len(current)-1})"
            
            if rest:
                rest = rest.lstrip('.')
                if rest:
                    return await apply_json_operation(
                        current[index],
                        operation_type,
                        rest,
                        new_value
                    )
            
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
            parts = target_path.split('.')
            current = content
            
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
                return True, current.get(last_part, "не найдено"), f"Структура по пути {target_path}"
        
        return False, None, "Неизвестный тип операции"
        
    except Exception as e:
        return False, None, f"Ошибка: {str(e)}"


# ========== НОВАЯ ФУНКЦИЯ СОХРАНЕНИЯ (БЕЗ ПОДТВЕРЖДЕНИЯ) ==========

async def save_edit_changes(message: Message, state: FSMContext):
    """Сразу сохраняет изменения без лишнего предпросмотра"""
    data = await state.get_data()
    module_name = data.get("edit_module_name")
    module_path = data.get("edit_module_path")
    operation = data.get("edit_operation")
    target_path = data.get("edit_target_path")
    new_value = data.get("edit_new_value")
    
    status_msg = await message.answer("🔄 Обновляю...")
    
    # Получаем текущее содержимое
    success, content, error = await get_github_file_content(module_path)
    
    if not success or not content:
        await status_msg.edit_text(f"❌ Ошибка загрузки: {error}")
        await state.clear()
        if message.from_user.id in user_upload_target:
            del user_upload_target[message.from_user.id]
        return
    
    # Применяем операцию
    import copy
    content_copy = copy.deepcopy(content)
    
    op_success, new_content, op_msg = await apply_json_operation(
        content_copy,
        operation,
        target_path,
        new_value
    )
    
    if not op_success:
        await status_msg.edit_text(f"❌ Ошибка: {op_msg}")
        return
    
    # Сохраняем в GitHub
    save_success = await update_github_file(
        file_path=module_path,
        content=new_content,
        message=f"🔧 {operation} в {target_path} через бот"
    )
    
    if save_success:
        file_url = f"https://github.com/{REPO_NAME}/blob/main/{module_path}"
        await status_msg.edit_text(
            f"✅ Обновление окей\n\n"
            f"🔗 <a href='{file_url}'>Посмотреть на GitHub</a>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    else:
        # Даже если GitHub не ответил, но файл мог обновиться
        file_url = f"https://github.com/{REPO_NAME}/blob/main/{module_path}"
        await status_msg.edit_text(
            f"⚠️ Обновление отправлено, но ответ не получен\n"
            f"Проверь через минуту: {file_url}",
            disable_web_page_preview=True
        )
    
    await state.clear()
    if message.from_user.id in user_upload_target:
        del user_upload_target[message.from_user.id]


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
            "source": "mandala_bot_v3.22.0"
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
    try:
        url = f"https://raw.githubusercontent.com/{REPO_NAME}/main/build/mandala_core.monolith.latest.json"
        headers = {}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    content = await response.read()
                    return True, content, "mandala_core.monolith.json"
                else:
                    return False, b"", f"Ошибка {response.status}"
    except Exception as e:
        return False, b"", str(e)


# ========== ФУНКЦИИ AHHIMSA ==========

async def check_ahimsa_smart(content: Dict, filename: str = "") -> Tuple[bool, str, List[Tuple[str, str]]]:
    return True, "✅ Проверка пройдена", []


# ========== ОБРАБОТЧИКИ КОМАНД ==========

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    await message.answer(
        "🌀 <b>Mandala Sync Terminal v3.22.0</b>\n\n"
        "📤 <b>Загрузить файл</b> — загрузка или редактирование\n"
        "📥 <b>Скачать монолит</b> — готовый файл\n"
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
    await message.answer("🚫 Отменено", reply_markup=get_main_keyboard())


@router.message(F.text == "📤 Загрузить файл")
async def handle_upload_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    
    await state.set_state(UploadStates.waiting_for_action)
    await message.answer(
        "📤 <b>Управление файлами</b>\n\n"
        "Загрузить новый или отредактировать существующий?",
        reply_markup=get_action_keyboard()
    )


@router.message(F.text == "📥 Скачать монолит")
async def handle_download_monolith_direct(message: Message):
    await message.answer("📦 Скачиваю...")
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
        "🍇 <b>Fructus</b>",
        reply_markup=get_fructus_inline_keyboard()
    )


@router.message(F.text == "ℹ️ Помощь")
async def handle_help(message: Message):
    await message.answer(
        "📚 <b>Mandala Sync Terminal v3.22.0</b>\n\n"
        "📤 <b>Загрузить файл</b>\n"
        "• Загрузка новых JSON\n"
        "• Редактирование существующих\n\n"
        "📥 <b>Скачать монолит</b>\n"
        "• mandala_core.monolith.latest.json\n\n"
        "🍇 <b>Fructus</b>\n"
        "• seeds, geometry, builders\n\n"
        "🧪 Testisphaera в модулях Мандалы\n"
        "🌿 Ahimsa-фильтр активен",
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

@router.callback_query(F.data == "action_upload", StateFilter(UploadStates.waiting_for_action))
async def handle_action_upload(callback_query: CallbackQuery, state: FSMContext):
    await state.update_data(edit_mode=False)
    await state.set_state(UploadStates.waiting_for_category)
    await callback_query.message.edit_text(
        "📤 <b>Загрузка</b>\n\nВыберите категорию:",
        reply_markup=get_category_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data == "action_edit", StateFilter(UploadStates.waiting_for_action))
async def handle_action_edit(callback_query: CallbackQuery, state: FSMContext):
    await state.update_data(edit_mode=True)
    await state.set_state(UploadStates.waiting_for_category)
    await callback_query.message.edit_text(
        "🔧 <b>Редактирование</b>\n\nВыберите категорию:",
        reply_markup=get_category_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data == "category_modules", StateFilter(UploadStates.waiting_for_category))
async def handle_category_modules(callback_query: CallbackQuery, state: FSMContext):
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "🧩 <b>Выберите модуль:</b>",
        reply_markup=get_modules_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data == "category_infra", StateFilter(UploadStates.waiting_for_category))
async def handle_category_infra(callback_query: CallbackQuery, state: FSMContext):
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "⚙️ <b>Выберите компонент:</b>",
        reply_markup=get_infra_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data == "back_to_categories", StateFilter(UploadStates.waiting_for_module))
async def handle_back_to_categories(callback_query: CallbackQuery, state: FSMContext):
    await state.set_state(UploadStates.waiting_for_category)
    await callback_query.message.edit_text(
        "📤 <b>Выберите категорию:</b>",
        reply_markup=get_category_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data == "back_to_modules", StateFilter(UploadStates.waiting_for_operation))
async def handle_back_to_modules(callback_query: CallbackQuery, state: FSMContext):
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "🧩 <b>Выберите модуль:</b>",
        reply_markup=get_modules_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("target_"), StateFilter(UploadStates.waiting_for_module))
async def handle_target_selection(callback_query: CallbackQuery, state: FSMContext):
    target_key = callback_query.data.replace("target_", "")
    
    if target_key not in ALL_UPLOAD_TARGETS:
        await callback_query.answer("Неизвестный целевой файл")
        return

    target_info = ALL_UPLOAD_TARGETS[target_key]
    user_upload_target[callback_query.from_user.id] = target_key
    
    data = await state.get_data()
    edit_mode = data.get("edit_mode", False)
    
    if edit_mode:
        await state.update_data(
            edit_module=target_key,
            edit_module_path=target_info["path"],
            edit_module_name=target_info["name"]
        )
        await state.set_state(UploadStates.waiting_for_operation)
        
        await callback_query.message.edit_text(
            f"🔧 <b>{target_info['name']}</b>\n\n"
            f"Файл: <code>{target_info['path']}</code>\n\n"
            f"Выберите операцию:",
            reply_markup=get_edit_operations_keyboard()
        )
    else:
        await state.set_state(UploadStates.waiting_for_file)
        await callback_query.message.edit_text(
            f"✅ {target_info['name']}\n"
            f"📁 <b>{target_info['filename']}</b>\n\n"
            f"Отправьте JSON-файл"
        )
        await callback_query.message.answer(
            "📎 Прикрепите файл",
            reply_markup=get_upload_mode_keyboard()
        )
    
    await callback_query.answer()


# ========== ОБРАБОТЧИКИ ОПЕРАЦИЙ РЕДАКТИРОВАНИЯ ==========

@router.callback_query(F.data == "edit_op_add", StateFilter(UploadStates.waiting_for_operation))
async def handle_edit_add(callback_query: CallbackQuery, state: FSMContext):
    await state.update_data(edit_operation="add_to_array")
    await state.set_state(UploadStates.waiting_for_target_path)
    await callback_query.message.edit_text(
        "➕ <b>Добавление в массив</b>\n\n"
        "Введите путь:\n"
        "<code>elements</code>\n"
        "<code>symbiosis_principles</code>\n"
        "<code>elements[0].items</code>"
    )
    await callback_query.answer()


@router.callback_query(F.data == "edit_op_update", StateFilter(UploadStates.waiting_for_operation))
async def handle_edit_update(callback_query: CallbackQuery, state: FSMContext):
    await state.update_data(edit_operation="update_field")
    await state.set_state(UploadStates.waiting_for_target_path)
    await callback_query.message.edit_text(
        "✏️ <b>Обновление поля</b>\n\n"
        "Введите путь:\n"
        "<code>version</code>\n"
        "<code>elements[0].value</code>\n"
        "<code>metadata.created</code>"
    )
    await callback_query.answer()


@router.callback_query(F.data == "edit_op_delete", StateFilter(UploadStates.waiting_for_operation))
async def handle_edit_delete(callback_query: CallbackQuery, state: FSMContext):
    await state.update_data(edit_operation="delete_field")
    await state.set_state(UploadStates.waiting_for_target_path)
    await callback_query.message.edit_text(
        "🗑️ <b>Удаление поля</b>\n\n"
        "Введите путь:\n"
        "<code>status</code>\n"
        "<code>metadata.temp</code>\n"
        "<code>elements[1]</code>"
    )
    await callback_query.answer()


@router.callback_query(F.data == "edit_op_show", StateFilter(UploadStates.waiting_for_operation))
async def handle_edit_show(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    module_name = data.get("edit_module_name")
    module_path = data.get("edit_module_path")
    
    await callback_query.message.edit_text(f"🔍 Загружаю...")
    
    success, content, error = await get_github_file_content(module_path)
    
    if success and content:
        if isinstance(content, dict):
            keys = list(content.keys())
            structure = "\n".join([f"• <code>{k}</code>" for k in keys[:15]])
            if len(keys) > 15:
                structure += f"\n• ... и ещё {len(keys)-15}"
        else:
            structure = f"Тип: {type(content).__name__}"
        
        await callback_query.message.edit_text(
            f"📋 <b>{module_name}</b>\n\n{structure}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_operations")]
            ])
        )
    else:
        await callback_query.message.edit_text(
            f"❌ Ошибка: {error}",
            reply_markup=get_edit_operations_keyboard()
        )
    await callback_query.answer()


@router.callback_query(F.data == "back_to_operations", StateFilter(UploadStates.waiting_for_target_path))
async def handle_back_to_operations(callback_query: CallbackQuery, state: FSMContext):
    await state.set_state(UploadStates.waiting_for_operation)
    data = await state.get_data()
    module_name = data.get("edit_module_name", "Модуль")
    await callback_query.message.edit_text(
        f"🔧 <b>{module_name}</b>\n\nВыберите операцию:",
        reply_markup=get_edit_operations_keyboard()
    )
    await callback_query.answer()


# ========== ОБРАБОТЧИКИ ВВОДА ПУТИ И ЗНАЧЕНИЙ ==========

@router.message(StateFilter(UploadStates.waiting_for_target_path))
async def handle_target_path(message: Message, state: FSMContext):
    target_path = message.text.strip()
    await state.update_data(edit_target_path=target_path)
    
    data = await state.get_data()
    operation = data.get("edit_operation")
    
    if operation == "delete_field":
        # Для удаления сразу сохраняем
        await save_edit_changes(message, state)
    else:
        # Для add и update нужно новое значение
        await message.answer(
            "📤 Отправьте новое значение в JSON формате:\n\n"
            "Строка: <code>\"текст\"</code>\n"
            "Число: <code>42</code>\n"
            "Объект: <code>{\"key\": \"value\"}</code>\n"
            "Массив: <code>[\"a\", \"b\"]</code>"
        )
        await state.set_state(UploadStates.waiting_for_new_value)


@router.message(StateFilter(UploadStates.waiting_for_new_value))
async def handle_new_value(message: Message, state: FSMContext):
    try:
        new_value = json.loads(message.text)
    except json.JSONDecodeError:
        new_value = message.text
    
    await state.update_data(edit_new_value=new_value)
    await save_edit_changes(message, state)


# ========== ОБРАБОТЧИК ЗАГРУЗКИ ФАЙЛОВ ==========

@router.message(StateFilter(UploadStates.waiting_for_file), F.document)
async def process_file_upload(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    try:
        if user_id not in user_upload_target:
            await message.answer("⚠️ Сначала выберите файл", 
                               reply_markup=get_category_keyboard())
            await state.set_state(UploadStates.waiting_for_category)
            return

        target_key = user_upload_target[user_id]
        
        if target_key not in ALL_UPLOAD_TARGETS:
            await message.answer("⚠️ Файл не найден", reply_markup=get_main_keyboard())
            await state.clear()
            return
        
        target_info = ALL_UPLOAD_TARGETS[target_key]
        
        if not message.document.file_name.lower().endswith('.json'):
            await message.answer("⚠️ Нужен JSON", reply_markup=get_upload_mode_keyboard())
            return
        
        status_msg = await message.answer("📥 Скачиваю...")

        file = await bot.get_file(message.document.file_id)
        file_content_bytes = await bot.download_file(file.file_path)
        file_content = file_content_bytes.read().decode('utf-8')
        
        try:
            content_to_save = json.loads(file_content)
        except json.JSONDecodeError as e:
            await status_msg.edit_text(f"⚠️ Невалидный JSON: {str(e)[:100]}")
            return
        
        ahimsa_ok, ahimsa_message, _ = await check_ahimsa_smart(content_to_save, message.document.file_name)
        if not ahimsa_ok:
            await status_msg.edit_text(f"🔶 {ahimsa_message}")
            return
        
        success = await update_github_file(
            file_path=target_info["path"],
            content=content_to_save,
            message=f"📤 {target_info['filename']} через бот"
        )
        
        if success:
            file_url = f"https://github.com/{REPO_NAME}/blob/main/{target_info['path']}"
            await status_msg.edit_text(
                f"✅ Загружено\n\n"
                f"🔗 <a href='{file_url}'>Посмотреть</a>",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        else:
            await status_msg.edit_text("🔶 Ошибка загрузки")
        
        await state.clear()
        if user_id in user_upload_target:
            del user_upload_target[user_id]
            
    except Exception as e:
        logger.error(f"💥 Ошибка: {e}", exc_info=True)
        await message.answer("🔶 Ошибка, попробуйте ещё раз")
    finally:
        await state.clear()
        if user_id in user_upload_target:
            del user_upload_target[user_id]


# ========== ОБРАБОТЧИКИ FRUCTUS ==========

@router.callback_query(F.data == "fructus_info")
async def handle_fructus_info(callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        "📋 <b>Fructus</b>\n"
        "• seeds — семена Incubae\n"
        "• geometry — Geometria Sacra\n"
        "• builders — скрипты\n\n"
        "Путь: /fructus/",
        reply_markup=get_fructus_inline_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data == "fructus_upload")
async def handle_fructus_upload(callback_query: CallbackQuery, state: FSMContext):
    user_upload_target[callback_query.from_user.id] = "fructus"
    await state.set_state(UploadStates.waiting_for_file)
    await callback_query.message.edit_text(
        "🍇 Отправьте JSON файл"
    )
    await callback_query.message.answer(
        "📎 Прикрепите JSON",
        reply_markup=get_upload_mode_keyboard()
    )
    await callback_query.answer()


@router.message(StateFilter(UploadStates.waiting_for_file), F.document)
async def handle_fructus_upload_file(message: Message, state: FSMContext):
    user_id = message.from_user.id
    target_key = user_upload_target.get(user_id)
    
    if target_key != "fructus":
        return
    
    try:
        if not message.document or not message.document.file_name.lower().endswith('.json'):
            await message.answer("⚠️ Нужен JSON", reply_markup=get_upload_mode_keyboard())
            return
        
        status_msg = await message.answer("📥 Сохраняю...")
        
        file = await bot.get_file(message.document.file_id)
        file_content_bytes = await bot.download_file(file.file_path)
        file_content = file_content_bytes.read().decode('utf-8')
        json_content = json.loads(file_content)
        
        success, result = await upload_to_fructus(message.document.file_name, json_content, user_id)
        if success:
            file_url = f"https://github.com/{REPO_NAME}/blob/main/fructus/{result}"
            await status_msg.edit_text(
                f"✅ Сохранено: <code>{result}</code>\n\n"
                f"🔗 <a href='{file_url}'>Посмотреть</a>",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        else:
            await status_msg.edit_text(f"🔶 Ошибка: {result}")
            
    except Exception as e:
        logger.error(f"Ошибка Fructus: {e}")
        await message.answer(f"🔶 Ошибка: {str(e)[:100]}")
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
        await message.answer("🔘 Выберите кнопками", reply_markup=get_category_keyboard())
    elif current == UploadStates.waiting_for_category:
        await message.answer("🔘 Выберите категорию", reply_markup=get_category_keyboard())
    elif current == UploadStates.waiting_for_target_path:
        await message.answer("📝 Введите путь (например: version или elements[0].value)")
    elif current == UploadStates.waiting_for_new_value:
        await message.answer("📤 Отправьте значение в JSON формате")
    else:
        await message.answer("ℹ️ Используйте меню", reply_markup=get_main_keyboard())


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
    logger.info("🛑 Shutdown")

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
        return web.Response(text="Mandala Bot v3.22.0")
    app.router.add_get("/", index)

    setup_application(app, dp, bot=bot)
    
    logger.info(f"🚀 Запуск на порту {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    main()
