#!/usr/bin/env python3
"""
Mandala Sync Terminal Bot v3.25.3
Render Web Service + Webhook (Aiogram 3)

ИЗМЕНЕНИЯ В v3.25.3:
- ФИКС: корневой обработчик (GET /) больше не блокирует вебхук
- Маршруты настроены правильно: вебхук на /webhook, health-check на /
- Добавлен информационный эндпоинт /status

Основано на v3.25.2 с исправлениями архитектора.
"""

import os
import sys
import json
import logging
import uuid
import base64
import asyncio
import re
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any, Union
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

# НОВЫЙ КЛАСС: для пакетных обновлений
class BatchUpdateStates(StatesGroup):
    waiting_for_module = State()      # выбор модуля
    waiting_for_batch = State()       # ожидание блока команд или файла
    waiting_for_confirmation = State()  # подтверждение транзакции

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

# ========== ДОБАВЛЯЕМ САМОГО БОТА КАК ЦЕЛЕВОЙ ФАЙЛ ==========
BOT_SELF = {
    "bot_script": {
        "name": "🤖 Сам бот (bot.py)",
        "filename": "bot.py",
        "path": "bot.py",
        "description": "Исходный код бота",
        "category": "infra"
    }
}

ALL_UPLOAD_TARGETS = {**MANDALA_MODULES, **INFRASTRUCTURE_FILES, **BOT_SELF}
user_upload_target = {}
user_batch_target = {}  # для пакетных обновлений

# ========== КЛАВИАТУРЫ ==========

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню с новой кнопкой пакетного обновления"""
    keyboard = [
        [KeyboardButton(text="📤 Загрузить файл")],
        [KeyboardButton(text="🔧 Редактировать модуль")],
        [KeyboardButton(text="📦 Пакетное обновление")],  # НОВАЯ КНОПКА
        [KeyboardButton(text="📦 Скачать монолит")],
        [KeyboardButton(text="🍇 Fructus")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=True
    )

def get_category_keyboard(for_edit: bool = False, for_batch: bool = False) -> InlineKeyboardMarkup:
    """Категории файлов. for_batch=True если вызывается из пакетного режима"""
    suffix = "_batch" if for_batch else ("_edit" if for_edit else "")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧩 Модули Мандалы", 
                            callback_data=f"category_modules{suffix}")],
        [InlineKeyboardButton(text="⚙️ Инфраструктура", 
                            callback_data=f"category_infra{suffix}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def get_modules_keyboard(for_edit: bool = False, for_batch: bool = False) -> InlineKeyboardMarkup:
    """Все модули Мандалы"""
    prefix = "batch_" if for_batch else ("edit_" if for_edit else "target_")
    back_to = "back_to_categories_batch" if for_batch else ("back_to_categories_edit" if for_edit else "back_to_categories")
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌀 Initium", callback_data=f"{prefix}initium"),
            InlineKeyboardButton(text="🌐 Sphaerae", callback_data=f"{prefix}sphaerae")
        ],
        [
            InlineKeyboardButton(text="📜 Akasha", callback_data=f"{prefix}akasha"),
            InlineKeyboardButton(text="💭 Philosophia", callback_data=f"{prefix}philosophia")
        ],
        [
            InlineKeyboardButton(text="🔺 Geometria", callback_data=f"{prefix}geometria_sacra"),
            InlineKeyboardButton(text="🌱 Incubae", callback_data=f"{prefix}incubae")
        ],
        [
            InlineKeyboardButton(text="🛡️ Tectosphaera", callback_data=f"{prefix}tectosphaera"),
            InlineKeyboardButton(text="🧪 Testisphaera", callback_data=f"{prefix}testisphaera")
        ],
        [InlineKeyboardButton(text="◀️ Назад к категориям", callback_data=back_to)]
    ])

def get_infra_keyboard(for_edit: bool = False, for_batch: bool = False) -> InlineKeyboardMarkup:
    """Инфраструктурные файлы + бот"""
    prefix = "batch_" if for_batch else ("edit_" if for_edit else "target_")
    back_to = "back_to_categories_batch" if for_batch else ("back_to_categories_edit" if for_edit else "back_to_categories")
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔨 Сборщик", callback_data=f"{prefix}build_script"),
            InlineKeyboardButton(text="🤖 GitHub Action", callback_data=f"{prefix}github_action")
        ],
        [
            InlineKeyboardButton(text="🤖 Сам бот", callback_data=f"{prefix}bot_script")
        ],
        [InlineKeyboardButton(text="◀️ Назад к категориям", callback_data=back_to)]
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
        [InlineKeyboardButton(text="◀️ Назад к модулям", callback_data="back_to_modules_edit")],
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

def get_batch_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Подтверждение транзакции перед применением"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, применить", callback_data="batch_confirm_yes"),
            InlineKeyboardButton(text="❌ Нет, отмена", callback_data="batch_confirm_no")
        ]
    ])


# ========== УТИЛИТЫ ДЛЯ РАБОТЫ С JSON-ПУТЯМИ ==========

def parse_json_path(path: str) -> List[Union[str, int]]:
    """
    Парсит путь вида "metadata.modified" или "spheres[0].modules"
    Возвращает список сегментов: ["metadata", "modified"] или ["spheres", 0, "modules"]
    """
    segments = []
    parts = path.split('.')
    for part in parts:
        bracket_match = re.search(r'\[(\d+)\]', part)
        if bracket_match:
            name = part[:bracket_match.start()]
            if name:
                segments.append(name)
            segments.append(int(bracket_match.group(1)))
            after_bracket = part[bracket_match.end():]
            if after_bracket and after_bracket.startswith('.'):
                remaining = after_bracket[1:]
                if remaining:
                    segments.extend(parse_json_path(remaining))
        else:
            if part:
                segments.append(part)
    return segments

def get_value_by_path(obj: Any, path: str) -> Tuple[Optional[Any], bool]:
    segments = parse_json_path(path)
    current = obj
    try:
        for seg in segments:
            if isinstance(current, dict):
                current = current.get(seg)
            elif isinstance(current, list) and isinstance(seg, int):
                if 0 <= seg < len(current):
                    current = current[seg]
                else:
                    return None, False
            else:
                return None, False
        return current, True
    except Exception:
        return None, False

def set_value_by_path(obj: Any, path: str, value: Any) -> Tuple[Any, bool]:
    segments = parse_json_path(path)
    if not segments:
        return obj, False
    
    current = obj
    for i, seg in enumerate(segments[:-1]):
        next_seg = segments[i + 1]
        if isinstance(current, dict):
            if seg not in current:
                if isinstance(next_seg, int):
                    current[seg] = []
                else:
                    current[seg] = {}
            current = current[seg]
        elif isinstance(current, list) and isinstance(seg, int):
            if seg >= len(current):
                current.extend([{} for _ in range(seg - len(current) + 1)])
            current = current[seg]
        else:
            return obj, False
    
    last_seg = segments[-1]
    try:
        if isinstance(current, dict):
            current[last_seg] = value
        elif isinstance(current, list) and isinstance(last_seg, int):
            if last_seg >= len(current):
                current.extend([None for _ in range(last_seg - len(current) + 1)])
            current[last_seg] = value
        else:
            return obj, False
        return obj, True
    except Exception:
        return obj, False

def delete_by_path(obj: Any, path: str) -> Tuple[Any, bool]:
    segments = parse_json_path(path)
    if not segments:
        return obj, False
    
    current = obj
    for seg in segments[:-1]:
        if isinstance(current, dict):
            if seg not in current:
                return obj, False
            current = current[seg]
        elif isinstance(current, list) and isinstance(seg, int):
            if seg >= len(current):
                return obj, False
            current = current[seg]
        else:
            return obj, False
    
    last_seg = segments[-1]
    try:
        if isinstance(current, dict):
            if last_seg in current:
                del current[last_seg]
        elif isinstance(current, list) and isinstance(last_seg, int):
            if 0 <= last_seg < len(current):
                del current[last_seg]
        else:
            return obj, False
        return obj, True
    except Exception:
        return obj, False

def add_to_array(obj: Any, path: str, value: Any) -> Tuple[Any, bool]:
    segments = parse_json_path(path)
    if not segments:
        return obj, False
    
    current = obj
    for seg in segments[:-1]:
        if isinstance(current, dict):
            if seg not in current:
                return obj, False
            current = current[seg]
        elif isinstance(current, list) and isinstance(seg, int):
            if seg >= len(current):
                return obj, False
            current = current[seg]
        else:
            return obj, False
    
    last_seg = segments[-1]
    try:
        if isinstance(current, dict):
            if last_seg not in current:
                return obj, False
            target = current[last_seg]
            if isinstance(target, list):
                target.append(value)
            else:
                return obj, False
        elif isinstance(current, list) and isinstance(last_seg, int):
            if last_seg >= len(current):
                return obj, False
            target = current[last_seg]
            if isinstance(target, list):
                target.append(value)
            else:
                return obj, False
        else:
            return obj, False
        return obj, True
    except Exception:
        return obj, False


# ========== ФУНКЦИИ GITHUB API ==========

async def get_github_file(file_path: str) -> Tuple[Optional[Any], Optional[str]]:
    """Получает файл с GitHub. Возвращает (контент, sha)"""
    if not GITHUB_TOKEN:
        logger.error("❌ GITHUB_TOKEN не установлен")
        return None, None
    
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaBot/3.25.3"
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    content_base64 = data.get("content", "")
                    sha = data.get("sha")
                    
                    try:
                        content_bytes = base64.b64decode(content_base64)
                        content_str = content_bytes.decode('utf-8')
                        try:
                            content = json.loads(content_str)
                        except json.JSONDecodeError:
                            content = content_str
                        return content, sha
                    except Exception as e:
                        logger.error(f"❌ Ошибка декодирования файла: {e}")
                        return None, None
                else:
                    logger.error(f"⚠️ GitHub GET error {response.status}")
                    return None, None
        except asyncio.TimeoutError:
            logger.error("❌ Таймаут при получении файла (30 сек)")
            return None, None
        except Exception as e:
            logger.error(f"❌ Ошибка при получении файла: {e}")
            return None, None

async def update_github_file(file_path: str, content: Any, message: str) -> Tuple[bool, Optional[str]]:
    """Обновление файла на GitHub. Возвращает (успех, ссылка_на_коммит)"""
    if not GITHUB_TOKEN:
        logger.error("❌ GITHUB_TOKEN не установлен")
        return False, None

    try:
        if isinstance(content, dict) or isinstance(content, list):
            content_str = json.dumps(content, ensure_ascii=False, indent=2)
        else:
            content_str = str(content)

        if len(content_str) > 1_000_000:
            logger.error("❌ Файл слишком большой (>1MB)")
            return False, None

        content_bytes = content_str.encode('utf-8')
        content_base64 = base64.b64encode(content_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"❌ Ошибка подготовки контента: {e}")
        return False, None

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaBot/3.25.3"
    }

    async with aiohttp.ClientSession() as session:
        # Получаем текущий SHA файла
        try:
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    sha = data.get("sha")
                elif response.status == 404:
                    sha = None
                else:
                    error_text = await response.text()
                    logger.error(f"⚠️ GitHub GET error {response.status}: {error_text[:200]}")
                    return False, None
        except asyncio.TimeoutError:
            logger.error("❌ Таймаут при получении SHA (30 сек)")
            return False, None
        except Exception as e:
            logger.error(f"❌ Ошибка при получении SHA: {e}")
            return False, None

        payload = {
            "message": message[:100],
            "content": content_base64,
        }
        if sha:
            payload["sha"] = sha

        try:
            async with session.put(url, headers=headers, json=payload, timeout=30) as response:
                if response.status in [200, 201]:
                    response_data = await response.json()
                    commit_url = response_data.get("commit", {}).get("html_url", "")
                    logger.info(f"✅ Файл {file_path} успешно обновлён")
                    return True, commit_url
                else:
                    error_text = await response.text()
                    logger.error(f"❌ GitHub error {response.status}: {error_text[:200]}")
                    return False, None
        except asyncio.TimeoutError:
            logger.error("❌ Таймаут при обновлении файла (30 сек)")
            return False, None
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении файла: {e}")
            return False, None

async def batch_update_github(file_path: str, operations: List[Dict], message: str) -> Tuple[bool, Optional[str], str]:
    """
    Выполняет несколько операций над одним файлом как одну транзакцию.
    Возвращает (успех, ссылка_на_коммит, детали_ошибки)
    """
    if not GITHUB_TOKEN:
        return False, None, "❌ GITHUB_TOKEN не установлен"

    current_content, sha = await get_github_file(file_path)
    if current_content is None:
        return False, None, f"❌ Не удалось получить файл {file_path}"

    updated_content = current_content
    operation_results = []
    
    for i, op in enumerate(operations):
        op_type = op.get("operation")
        path = op.get("path")
        value = op.get("value")

        if not op_type or not path:
            operation_results.append(f"❌ Операция {i+1}: пропущены обязательные поля")
            continue

        try:
            if op_type == "update":
                updated_content, success = set_value_by_path(updated_content, path, value)
                if success:
                    operation_results.append(f"✅ {i+1}. update {path}")
                else:
                    operation_results.append(f"❌ {i+1}. update {path} — не удалось обновить")
                    return False, None, "\n".join(operation_results)

            elif op_type == "add":
                updated_content, success = add_to_array(updated_content, path, value)
                if success:
                    operation_results.append(f"✅ {i+1}. add to {path}")
                else:
                    operation_results.append(f"❌ {i+1}. add to {path} — не удалось добавить")
                    return False, None, "\n".join(operation_results)

            elif op_type == "delete":
                updated_content, success = delete_by_path(updated_content, path)
                if success:
                    operation_results.append(f"✅ {i+1}. delete {path}")
                else:
                    operation_results.append(f"❌ {i+1}. delete {path} — не удалось удалить")
                    return False, None, "\n".join(operation_results)

            elif op_type == "show":
                value, found = get_value_by_path(updated_content, path)
                if found:
                    operation_results.append(f"ℹ️ {i+1}. show {path} → {json.dumps(value, ensure_ascii=False)[:100]}")
                else:
                    operation_results.append(f"⚠️ {i+1}. show {path} — путь не найден")
            else:
                operation_results.append(f"❌ {i+1}. неизвестная операция: {op_type}")
                return False, None, "\n".join(operation_results)
        except Exception as e:
            operation_results.append(f"❌ {i+1}. ошибка: {str(e)}")
            return False, None, "\n".join(operation_results)

    success, commit_url = await update_github_file(file_path, updated_content, message)
    if success:
        result_details = f"✅ Транзакция применена успешно\n" + "\n".join(operation_results)
        return True, commit_url, result_details
    else:
        return False, None, "❌ Ошибка при сохранении файла на GitHub"


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
            "source": "mandala_bot_v3.25.3"
        }
        
        success, _ = await update_github_file(
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


# ========== ФУНКЦИИ AHHIMSA (ЗАГЛУШКА) ==========

async def check_ahimsa_smart(content: Any, filename: str = "") -> Tuple[bool, str, List[Tuple[str, str]]]:
    # В реальности тут должна быть проверка, пока пропускаем всё
    return True, "✅ Проверка пройдена", []


# ========== ОБРАБОТЧИКИ КОМАНД ==========

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "🌱 **Mandala Bot v3.25.3**\n"
        "Я — интерфейс заботы для работы с Мандалой.\n\n"
        "📤 **Загрузить файл** — добавить новый модуль или инфраструктуру\n"
        "🔧 **Редактировать модуль** — точечные изменения JSON\n"
        "📦 **Пакетное обновление** — несколько изменений одним коммитом\n"
        "📦 **Скачать монолит** — получить полную сборку\n"
        "🍇 **Fructus** — хранилище артефактов\n"
        "ℹ️ **Помощь** — подсказки",
        reply_markup=get_main_keyboard()
    )

@router.message(Command("cancel"))
@router.message(F.text.lower() == "отмена")
async def cancel_command(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    if user_id in user_batch_target:
        del user_batch_target[user_id]
    await message.answer("❌ Отменено.", reply_markup=get_main_keyboard())

@router.message(F.text == "📤 Загрузить файл")
async def upload_file_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    
    await state.update_data(edit_mode=False)
    await state.set_state(UploadStates.waiting_for_category)
    await message.answer(
        "Выбери категорию файла:",
        reply_markup=get_category_keyboard(for_edit=False)
    )

@router.message(F.text == "🔧 Редактировать модуль")
async def edit_module_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    
    await state.update_data(edit_mode=True)
    await state.set_state(UploadStates.waiting_for_category)
    await message.answer(
        "🔧 Режим редактирования модуля\nВыбери категорию:",
        reply_markup=get_category_keyboard(for_edit=True)
    )

@router.message(F.text == "📦 Пакетное обновление")
async def batch_update_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(BatchUpdateStates.waiting_for_module)
    await message.answer(
        "📦 **Пакетное обновление**\n"
        "Ты можешь выполнить несколько операций над одним модулем одной транзакцией.\n\n"
        "Выбери модуль для обновления:",
        reply_markup=get_category_keyboard(for_batch=True)
    )

@router.message(F.text == "📦 Скачать монолит")
async def download_monolith(message: Message):
    await message.answer("🔍 Ищу актуальный монолит...")
    content, _ = await get_github_file("build/mandala_core.monolith.latest.json")
    if content and isinstance(content, dict):
        json_str = json.dumps(content, ensure_ascii=False, indent=2)
        file = BufferedInputFile(
            file=json_str.encode('utf-8'),
            filename="mandala_core.monolith.latest.json"
        )
        await message.answer_document(
            document=file,
            caption="📦 Актуальный монолит Mandala Core"
        )
    else:
        await message.answer("❌ Не удалось найти монолит в репозитории")

@router.message(F.text == "🍇 Fructus")
async def fructus_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🍇 **Fructus** — хранилище артефактов\n\n"
        "📤 Загрузить — добавить артефакт в Fructus\n"
        "📋 Информация — узнать, какие типы файлов куда попадают",
        reply_markup=get_fructus_inline_keyboard()
    )

@router.message(F.text == "ℹ️ Помощь")
async def help_command(message: Message):
    await message.answer(
        "🌱 **Mandala Bot v3.25.3 — Помощь**\n\n"
        "📤 **Загрузить файл** — загрузка новых JSON-файлов в репозиторий\n"
        "🔧 **Редактировать модуль** — точечные изменения JSON без полной перезаписи\n"
        "📦 **Пакетное обновление** — несколько изменений одним коммитом (атомарно!)\n"
        "📦 **Скачать монолит** — мгновенное скачивание mandala_core.monolith.latest.json\n"
        "🍇 **Fructus** — хранилище артефактов (семена, геометрия, скрипты)\n\n"
        "**Пакетные обновления**: отправь блок команд в формате:\n"
        "---\n"
        "операция: update\n"
        "путь: version\n"
        "значение: \"v2.3.1\"\n"
        "---\n"
        "операция: add\n"
        "путь: changes.details\n"
        "значение: \"Новое изменение\"\n"
        "---\n\n"
        "Поддерживаются пути: metadata.modified, spheres[0].modules и т.д."
    )


# ========== ОБРАБОТЧИКИ INLINE-КНОПОК ==========

@router.callback_query(F.data.startswith("category_modules"))
async def process_category_modules(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    is_edit = callback.data.endswith("_edit")
    is_batch = callback.data.endswith("_batch")

    if is_batch:
        await state.set_state(BatchUpdateStates.waiting_for_module)
        await callback.message.edit_text(
            "📦 Выбери модуль для пакетного обновления:",
            reply_markup=get_modules_keyboard(for_edit=False, for_batch=True)
        )
    else:
        await state.set_state(UploadStates.waiting_for_module)
        await callback.message.edit_text(
            "Выбери модуль:",
            reply_markup=get_modules_keyboard(for_edit=is_edit, for_batch=False)
        )

@router.callback_query(F.data.startswith("category_infra"))
async def process_category_infra(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    is_edit = callback.data.endswith("_edit")
    is_batch = callback.data.endswith("_batch")
    
    if is_batch:
        await state.set_state(BatchUpdateStates.waiting_for_module)
        await callback.message.edit_text(
            "📦 Выбери инфраструктурный файл для пакетного обновления:",
            reply_markup=get_infra_keyboard(for_edit=False, for_batch=True)
        )
    else:
        await state.set_state(UploadStates.waiting_for_module)
        await callback.message.edit_text(
            "Выбери файл:",
            reply_markup=get_infra_keyboard(for_edit=is_edit, for_batch=False)
        )

@router.callback_query(F.data.startswith("target_"))
async def process_target_selection(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    target_key = callback.data.replace("target_", "")
    if target_key in ALL_UPLOAD_TARGETS:
        user_upload_target[callback.from_user.id] = ALL_UPLOAD_TARGETS[target_key]
        await state.set_state(UploadStates.waiting_for_file)
        await callback.message.edit_text(
            f"📤 Отправь содержимое файла **{ALL_UPLOAD_TARGETS[target_key]['name']}**\n"
            f"({ALL_UPLOAD_TARGETS[target_key]['path']})\n\n"
            "Это может быть:\n"
            "- Текстовое содержимое (JSON или код)\n"
            "- Файл (как документ)\n\n"
            "Или нажми /cancel для отмены."
        )
    else:
        await callback.message.edit_text("❌ Неизвестный целевой файл")

@router.callback_query(F.data.startswith("edit_"))
async def process_edit_target(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    target_key = callback.data.replace("edit_", "")
    if target_key in ALL_UPLOAD_TARGETS:
        user_upload_target[callback.from_user.id] = ALL_UPLOAD_TARGETS[target_key]
        await state.set_state(UploadStates.waiting_for_operation)
        await callback.message.edit_text(
            f"🔧 Редактирование **{ALL_UPLOAD_TARGETS[target_key]['name']}**\n"
            f"Выбери операцию:",
            reply_markup=get_edit_operations_keyboard()
        )
    else:
        await callback.message.edit_text("❌ Неизвестный модуль")

@router.callback_query(F.data.startswith("batch_"))
async def process_batch_target(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    target_key = callback.data.replace("batch_", "")
    if target_key in ALL_UPLOAD_TARGETS:
        target = ALL_UPLOAD_TARGETS[target_key]
        user_batch_target[callback.from_user.id] = target
        await state.set_state(BatchUpdateStates.waiting_for_batch)
        await callback.message.edit_text(
            f"📦 **Пакетное обновление**: {target['name']}\n"
            f"Файл: `{target['path']}`\n\n"
            "Отправь блок операций в формате:\n\n"
            "---\n"
            "операция: update\n"
            "путь: version\n"
            "значение: \"v2.3.1\"\n"
            "---\n"
            "операция: add\n"
            "путь: changes.details\n"
            "значение: \"Новое изменение\"\n"
            "---\n\n"
            "Поддерживаемые операции: update, add, delete, show\n"
            "Пути: metadata.modified, spheres[0].modules и т.д.\n\n"
            "Отправь блок команд одним сообщением."
        )
    else:
        await callback.message.edit_text("❌ Неизвестный модуль")

@router.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(UploadStates.waiting_for_category)
    await callback.message.edit_text(
        "Выбери категорию файла:",
        reply_markup=get_category_keyboard(for_edit=False)
    )

@router.callback_query(F.data == "back_to_categories_edit")
async def back_to_categories_edit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(UploadStates.waiting_for_category)
    await callback.message.edit_text(
        "🔧 Режим редактирования\nВыбери категорию:",
        reply_markup=get_category_keyboard(for_edit=True)
    )

@router.callback_query(F.data == "back_to_categories_batch")
async def back_to_categories_batch(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(BatchUpdateStates.waiting_for_module)
    await callback.message.edit_text(
        "📦 Пакетное обновление\nВыбери категорию:",
        reply_markup=get_category_keyboard(for_batch=True)
    )

@router.callback_query(F.data == "back_to_modules_edit")
async def back_to_modules_edit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(UploadStates.waiting_for_module)
    await callback.message.edit_text(
        "Выбери модуль для редактирования:",
        reply_markup=get_modules_keyboard(for_edit=True)
    )

@router.callback_query(F.data.startswith("edit_op_"))
async def process_edit_operation(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    op_type = callback.data.replace("edit_op_", "")

    if op_type == "show":
        user_id = callback.from_user.id
        if user_id not in user_upload_target:
            await callback.message.edit_text("❌ Сессия истекла. Начни заново.")
            await state.clear()
            return

        target = user_upload_target[user_id]
        file_path = target["path"]
        
        content, _ = await get_github_file(file_path)
        if content is None:
            await callback.message.edit_text(f"❌ Не удалось получить файл {file_path}")
            return
        
        if isinstance(content, dict) or isinstance(content, list):
            content_str = json.dumps(content, ensure_ascii=False, indent=2)
            if len(content_str) > 3500:
                file = BufferedInputFile(
                    file=content_str.encode('utf-8'),
                    filename=f"{target['filename']}.json"
                )
                await callback.message.answer_document(
                    document=file,
                    caption=f"📋 Текущая структура {target['name']}"
                )
                await callback.message.delete()
            else:
                await callback.message.edit_text(
                    f"📋 Текущая структура {target['name']}:\n"
                    f"```json\n{content_str}\n```"
                )
        else:
            await callback.message.edit_text(
                f"📋 Файл {target['name']} (не JSON):\n{content[:1000]}..."
            )
        await state.clear()

    elif op_type in ["add", "update", "delete"]:
        await state.update_data(edit_operation=op_type)
        await state.set_state(UploadStates.waiting_for_target_path)
        
        examples = {
            "add": "➕ Добавить в массив\nПример: changes.details\nИли: spheres[0].modules",
            "update": "✏️ Обновить поле\nПример: version\nИли: metadata.modified",
            "delete": "🗑️ Удалить поле\nПример: deprecated_field\nИли: spheres[1].unused"
        }
        await callback.message.edit_text(
            f"{examples[op_type]}\n\n"
            "Введи путь к полю (поддерживается точечная нотация и индексы массивов):"
        )

@router.callback_query(F.data == "cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.message.answer("Возврат в главное меню.", reply_markup=get_main_keyboard())

@router.callback_query(F.data == "fructus_info")
async def fructus_info(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🍇 **Fructus** — хранилище артефактов\n\n"
        "Автоматическая категоризация:\n"
        "• seeds, incubae → 🌱 папка seeds\n"
        "• geometria, sacra → 🔺 папка geometry\n"
        "• build, script → 🔨 папка builders\n"
        "• остальное → 📁 прочее\n\n"
        "Используй 📤 Загрузить для добавления артефактов."
    )

@router.callback_query(F.data == "fructus_upload")
async def fructus_upload_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_upload_target[callback.from_user.id] = "fructus"
    await state.set_state(UploadStates.waiting_for_file)
    await callback.message.edit_text(
        "🍇 Отправь JSON файл для добавления в Fructus.\n"
        "Бот автоматически определит категорию."
    )

@router.callback_query(F.data.startswith("batch_confirm_"), BatchUpdateStates.waiting_for_confirmation)
async def process_batch_confirmation(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    action = callback.data.replace("batch_confirm_", "")
    
    if action == "no":
        await callback.message.edit_text("❌ Транзакция отменена.")
        await state.clear()
        await callback.message.answer("Возврат в главное меню.", reply_markup=get_main_keyboard())
        return
    
    data = await state.get_data()
    target = data.get("batch_target")
    operations = data.get("batch_operations", [])
    
    if not target or not operations:
        await callback.message.edit_text("❌ Ошибка: данные транзакции потеряны.")
        await state.clear()
        return

    await callback.message.edit_text(f"⏳ Применяю транзакцию к {target['name']}...")
    commit_message = f"Пакетное обновление {target['filename']} [{len(operations)} ops]"

    success, commit_url, details = await batch_update_github(
        target["path"],
        operations,
        commit_message
    )
    
    if success:
        response = f"✅ **Транзакция применена успешно**\n\n{details}"
        if commit_url:
            response += f"\n\n🔗 [Смотреть коммит]({commit_url})"
    else:
        response = f"❌ **Ошибка применения транзакции**\n\n{details}"
    
    await callback.message.edit_text(response, disable_web_page_preview=True)
    await state.clear()
    await callback.message.answer("Возврат в главное меню.", reply_markup=get_main_keyboard())


# ========== ОБРАБОТЧИКИ ПОЛУЧЕНИЯ ФАЙЛОВ ==========

@router.message(UploadStates.waiting_for_file, F.document)
async def handle_document_upload(message: Message, state: FSMContext):
    user_id = message.from_user.id
    target = user_upload_target.get(user_id)
    if not target or target == "fructus":
        # Обработка загрузки в Fructus
        if target == "fructus":
            try:
                file = await bot.get_file(message.document.file_id)
                file_content_bytes = await bot.download_file(file.file_path)
                file_content = file_content_bytes.read().decode('utf-8')
                json_content = json.loads(file_content)
                success, result = await upload_to_fructus(message.document.file_name, json_content, user_id)
                if success:
                    file_url = f"https://github.com/{REPO_NAME}/blob/main/fructus/{result}"
                    await message.answer(
                        f"✅ Сохранено: `{result}`\n\n🔗 [Посмотреть]({file_url})",
                        disable_web_page_preview=True
                    )
                else:
                    await message.answer(f"❌ Ошибка: {result}")
                await state.clear()
                return
            except Exception as e:
                await message.answer(f"❌ Ошибка обработки файла: {e}")
                await state.clear()
                return
        else:
            await message.answer("❌ Сессия истекла. Начни заново.", reply_markup=get_main_keyboard())
            await state.clear()
            return

    # Обычная загрузка
    file = await bot.get_file(message.document.file_id)
    file_path = file.file_path
    file_content_bytes = await bot.download_file(file_path)
    content_str = file_content_bytes.read().decode('utf-8')
    
    try:
        content = json.loads(content_str)
    except json.JSONDecodeError:
        content = content_str
    
    await message.answer(f"⏳ Загружаю {target['filename']} на GitHub...")
    success, commit_url = await update_github_file(
        target["path"],
        content,
        f"Обновление {target['filename']} через бота"
    )

    if success:
        response = f"✅ Файл **{target['name']}** успешно загружен!"
        if commit_url:
            response += f"\n\n🔗 [Смотреть изменения]({commit_url})"
        await message.answer(response, disable_web_page_preview=True)
    else:
        await message.answer("❌ Ошибка загрузки файла. Попробуй ещё раз.")
    
    await state.clear()
    if user_id in user_upload_target:
        del user_upload_target[user_id]

@router.message(UploadStates.waiting_for_file, F.text)
async def handle_text_upload(message: Message, state: FSMContext):
    user_id = message.from_user.id
    target = user_upload_target.get(user_id)
    if not target or target == "fructus":
        await message.answer("❌ Сессия истекла или неверный режим.", reply_markup=get_main_keyboard())
        await state.clear()
        return

    content_str = message.text
    try:
        content = json.loads(content_str)
    except json.JSONDecodeError:
        content = content_str

    await message.answer(f"⏳ Загружаю {target['filename']} на GitHub...")
    success, commit_url = await update_github_file(
        target["path"],
        content,
        f"Обновление {target['filename']} через бота"
    )
    
    if success:
        response = f"✅ Файл **{target['name']}** успешно загружен!"
        if commit_url:
            response += f"\n\n🔗 [Смотреть изменения]({commit_url})"
        await message.answer(response, disable_web_page_preview=True)
    else:
        await message.answer("❌ Ошибка загрузки файла. Попробуй ещё раз.")
    
    await state.clear()
    if user_id in user_upload_target:
        del user_upload_target[user_id]

@router.message(UploadStates.waiting_for_target_path)
async def process_edit_path(message: Message, state: FSMContext):
    path = message.text.strip()
    data = await state.get_data()
    op_type = data.get("edit_operation")
    await state.update_data(edit_path=path)
    
    if op_type == "delete":
        await perform_edit_operation(message, state, path, None)
    else:
        await state.set_state(UploadStates.waiting_for_new_value)
        examples = {
            "add": "➕ Введи значение для добавления в массив (в JSON-формате)\nПример: \"Новый элемент\" или {\"key\": \"value\"}",
            "update": "✏️ Введи новое значение (в JSON-формате)\nПример: \"v2.3.1\" или {\"name\": \"новое\"}"
        }
        await message.answer(examples[op_type])

@router.message(UploadStates.waiting_for_new_value)
async def process_edit_value(message: Message, state: FSMContext):
    value_str = message.text.strip()
    try:
        value = json.loads(value_str)
    except json.JSONDecodeError:
        value = value_str
    
    data = await state.get_data()
    path = data.get("edit_path")
    op_type = data.get("edit_operation")
    user_id = message.from_user.id
    
    if user_id not in user_upload_target:
        await message.answer("❌ Сессия истекла. Начни заново.", reply_markup=get_main_keyboard())
        await state.clear()
        return
    
    await perform_edit_operation(message, state, path, value)

async def perform_edit_operation(message: Message, state: FSMContext, path: str, value: Any):
    data = await state.get_data()
    op_type = data.get("edit_operation")
    user_id = message.from_user.id
    target = user_upload_target.get(user_id)
    
    if not target:
        await message.answer("❌ Сессия истекла.", reply_markup=get_main_keyboard())
        await state.clear()
        return

    await message.answer(f"⏳ Применяю операцию к {target['name']}...")
    
    current_content, sha = await get_github_file(target["path"])
    if current_content is None:
        await message.answer(f"❌ Не удалось получить файл {target['path']}")
        await state.clear()
        return

    updated_content = current_content
    success = False
    
    if op_type == "update":
        updated_content, success = set_value_by_path(current_content, path, value)
    elif op_type == "add":
        updated_content, success = add_to_array(current_content, path, value)
    elif op_type == "delete":
        updated_content, success = delete_by_path(current_content, path)
    
    if not success:
        await message.answer(f"❌ Не удалось применить операцию. Проверь путь: {path}")
        await state.clear()
        return
    
    commit_message = f"{op_type} {path} в {target['filename']}"
    success, commit_url = await update_github_file(target["path"], updated_content, commit_message)
    
    if success:
        response = f"✅ Операция {op_type} успешно применена к {target['name']}"
        if commit_url:
            response += f"\n\n🔗 [Смотреть изменения]({commit_url})"
        await message.answer(response, disable_web_page_preview=True)
    else:
        await message.answer("❌ Ошибка сохранения файла на GitHub")
    
    await state.clear()
    if user_id in user_upload_target:
        del user_upload_target[user_id]

@router.message(BatchUpdateStates.waiting_for_batch)
async def process_batch_commands(message: Message, state: FSMContext):
    user_id = message.from_user.id
    target = user_batch_target.get(user_id)
    if not target:
        await message.answer("❌ Сессия истекла. Начни заново.", reply_markup=get_main_keyboard())
        await state.clear()
        return
    
    batch_text = message.text
    operations = []
    current_op = {}
    
    lines = batch_text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line == '---':
            if current_op and "operation" in current_op:
                operations.append(current_op)
                current_op = {}
        elif ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()
            
            try:
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith('[') or value.startswith('{'):
                    value = json.loads(value)
                elif value.lower() == 'true':
                    value = True
                elif value.lower() == 'false':
                    value = False
                elif value.lower() == 'null':
                    value = None
                elif value.isdigit():
                    value = int(value)
            except:
                pass
            
            current_op[key] = value
    
    if current_op and "operation" in current_op:
        operations.append(current_op)
    
    if not operations:
        await message.answer(
            "❌ Не удалось распарсить операции. Убедись, что формат:\n"
            "---\nоперация: update\nпуть: version\nзначение: \"v2.3.1\"\n---"
        )
        return
    
    await state.update_data(batch_operations=operations, batch_target=target)
    await state.set_state(BatchUpdateStates.waiting_for_confirmation)
    
    preview = f"📦 **Пакетное обновление**: {target['name']}\n"
    preview += f"Файл: `{target['path']}`\n"
    preview += f"Операций: {len(operations)}\n\n**Операции:**\n"
    
    for i, op in enumerate(operations, 1):
        op_type = op.get("operation", "?")
        path = op.get("path", "?")
        value = op.get("value", "")
        preview += f"{i}. {op_type} {path}"
        if value and op_type != "delete":
            value_str = json.dumps(value, ensure_ascii=False)
            if len(value_str) > 50:
                value_str = value_str[:50] + "..."
            preview += f" → {value_str}"
        preview += "\n"
    
    preview += "\nПрименить транзакцию?"
    await message.answer(preview, reply_markup=get_batch_confirmation_keyboard())


# ========== УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК ==========

@router.message()
async def handle_other_messages(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        # Если мы в каком-то состоянии, предложим помощь или отмену
        await message.answer(
            "Пожалуйста, следуй инструкциям или нажми /cancel для отмены.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="❌ Отмена")]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
    else:
        await message.answer(
            "Используй меню для навигации.",
            reply_markup=get_main_keyboard()
        )


# ========== ВЕБХУК И ЗАПУСК ==========

async def on_startup() -> None:
    """Установка вебхука при старте"""
    try:
        await bot.set_webhook(
            WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=True
        )
        logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"❌ Ошибка установки webhook: {e}")

async def on_shutdown() -> None:
    """Удаление вебхука при остановке"""
    try:
        await bot.delete_webhook()
        logger.info("✅ Webhook удалён")
    except Exception as e:
        logger.error(f"❌ Ошибка удаления webhook: {e}")

async def handle_webhook(request: web.Request) -> web.Response:
    """Обработчик вебхука от Telegram"""
    return await SimpleRequestHandler(dp, bot).handle(request)

def main() -> None:
    """Главная функция запуска"""
    if not RENDER_EXTERNAL_URL:
        logger.error("❌ RENDER_EXTERNAL_URL не задан")
        sys.exit(1)
    
    if not GITHUB_TOKEN:
        logger.warning("⚠️ GITHUB_TOKEN не задан — загрузка файлов будет недоступна")

    logger.info(f"🚀 Запуск бота v3.25.3, webhook URL: {WEBHOOK_URL}")
    
    # Регистрируем startup и shutdown
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Запускаем aiohttp приложение
    app = web.Application()
    
    # РЕГИСТРИРУЕМ ОБРАБОТЧИК ВЕБХУКА (ЭТО ВАЖНО!)
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET
    ).register(app, path=WEBHOOK_PATH)

    # ---- ДОПОЛНИТЕЛЬНЫЕ МАРШРУТЫ ----
    async def health_check(request: web.Request) -> web.Response:
        return web.Response(text="OK")
    app.router.add_get("/", health_check)  # Health-check для Render

    async def status_page(request: web.Request) -> web.Response:
        return web.Response(text=f"Mandala Bot v3.25.3 is running. Webhook path: {WEBHOOK_PATH}")
    app.router.add_get("/status", status_page)  # Информационный эндпоинт

    logger.info(f"🚀 Запуск на порту {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
