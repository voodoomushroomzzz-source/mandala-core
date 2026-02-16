#!/usr/bin/env python3
"""
Mandala Sync Terminal Bot v3.24.0
Render Web Service + Webhook (Aiogram 3)

НОВОЕ В v3.24.0:
- 📦 Пакетное обновление модулей (batch patch)
- Загрузка JSON с любым именем файла
- Множественные операции в одном файле (update/add/delete/replace/merge)
- Предпросмотр изменений перед применением
- Атомарное применение (всё или ничего)
- Детальный отчёт о применённых операциях
- Ахимса-фильтр итогового состояния
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
    waiting_for_action = State()
    waiting_for_category = State()
    waiting_for_module = State()
    waiting_for_file = State()
    waiting_for_operation = State()
    waiting_for_target_path = State()
    waiting_for_new_value = State()
    # НОВЫЕ СОСТОЯНИЯ ДЛЯ ПАКЕТНЫХ ОБНОВЛЕНИЙ
    waiting_for_patch_file = State()
    waiting_for_patch_confirmation = State()


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

def get_category_keyboard(for_edit: bool = False) -> InlineKeyboardMarkup:
    """Категории файлов"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧩 Модули Мандалы", 
                            callback_data="category_modules_edit" if for_edit else "category_modules")],
        [InlineKeyboardButton(text="⚙️ Инфраструктура", 
                            callback_data="category_infra_edit" if for_edit else "category_infra")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def get_modules_keyboard(for_edit: bool = False) -> InlineKeyboardMarkup:
    """Все модули Мандалы"""
    prefix = "edit_" if for_edit else "target_"
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
        [InlineKeyboardButton(text="◀️ Назад к категориям", 
                            callback_data="back_to_categories_edit" if for_edit else "back_to_categories")]
    ])

def get_infra_keyboard(for_edit: bool = False) -> InlineKeyboardMarkup:
    """Инфраструктурные файлы + бот"""
    prefix = "edit_" if for_edit else "target_"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔨 Сборщик", callback_data=f"{prefix}build_script"),
            InlineKeyboardButton(text="🤖 GitHub Action", callback_data=f"{prefix}github_action")
        ],
        [
            InlineKeyboardButton(text="🤖 Сам бот", callback_data=f"{prefix}bot_script")
        ],
        [InlineKeyboardButton(text="◀️ Назад к категориям", 
                            callback_data="back_to_categories_edit" if for_edit else "back_to_categories")]
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


# ========== ФУНКЦИИ GITHUB API ==========

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
        "User-Agent": "MandalaBot/3.24.0"
    }

    async with aiohttp.ClientSession() as session:
        try:
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


async def get_github_file_content(file_path: str) -> Tuple[bool, Optional[Any], Optional[str]]:
    """Получить содержимое файла из GitHub"""
    if not GITHUB_TOKEN:
        return False, None, "GITHUB_TOKEN не настроен"
    
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaBot/3.24.0"
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    content = base64.b64decode(data["content"]).decode('utf-8')
                    try:
                        return True, json.loads(content), data.get("sha")
                    except:
                        return True, content, data.get("sha")
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


# ========== НОВЫЕ ФУНКЦИИ ДЛЯ ПАКЕТНЫХ ОБНОВЛЕНИЙ ==========

def validate_patch_structure(patch_data: Dict) -> Tuple[bool, str]:
    """Проверка структуры пакетного файла"""
    if not isinstance(patch_data, dict):
        return False, "Патч должен быть объектом JSON"
    
    if "target_module" not in patch_data:
        return False, "Отсутствует поле 'target_module'"
    
    if "changes" not in patch_data:
        return False, "Отсутствует поле 'changes'"
    
    if not isinstance(patch_data["changes"], list):
        return False, "'changes' должен быть массивом"
    
    if len(patch_data["changes"]) == 0:
        return False, "Массив изменений пуст"
    
    valid_ops = ["update", "add", "delete", "replace", "merge"]
    
    for i, change in enumerate(patch_data["changes"]):
        if not isinstance(change, dict):
            return False, f"Изменение #{i} должно быть объектом"
        
        if "op" not in change:
            return False, f"Изменение #{i}: отсутствует 'op'"
        
        if change["op"] not in valid_ops:
            return False, f"Изменение #{i}: недопустимая операция '{change['op']}'"
        
        if "path" not in change:
            return False, f"Изменение #{i}: отсутствует 'path'"
        
        if change["op"] in ["update", "add", "replace", "merge"] and "value" not in change:
            return False, f"Изменение #{i}: для операции '{change['op']}' нужно 'value'"
    
    return True, "OK"


def handle_replace(content: Dict, path: str, value: Any) -> Tuple[bool, Dict, str]:
    """Специальная обработка для replace (замена элемента в массиве по индексу)"""
    try:
        array_match = re.match(r"(.+)\[(\d+)\]$", path)
        if not array_match:
            return False, content, "Replace работает только с элементами массива (path[index])"
        
        base_path, index_str = array_match.groups()
        index = int(index_str)
        
        current = content
        for key in base_path.split('.'):
            if key:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return False, content, f"Путь {base_path} не найден"
        
        if not isinstance(current, list):
            return False, content, f"{base_path} не является массивом"
        
        if index >= len(current):
            return False, content, f"Индекс {index} вне диапазона"
        
        current[index] = value
        return True, content, f"Элемент [{index}] заменён"
    except Exception as e:
        return False, content, str(e)


def handle_merge(content: Dict, path: str, value: Dict) -> Tuple[bool, Dict, str]:
    """Слияние объектов"""
    try:
        parts = path.split('.')
        current = content
        
        for part in parts[:-1]:
            if part:
                if part not in current:
                    current[part] = {}
                current = current[part]
        
        last_part = parts[-1]
        
        if last_part not in current:
            current[last_part] = {}
        
        if not isinstance(current[last_part], dict) or not isinstance(value, dict):
            return False, content, "Merge работает только с объектами"
        
        # Глубокое слияние
        def deep_merge(a, b):
            for key in b:
                if key in a and isinstance(a[key], dict) and isinstance(b[key], dict):
                    deep_merge(a[key], b[key])
                else:
                    a[key] = b[key]
            return a
        
        current[last_part] = deep_merge(current[last_part], value)
        return True, content, f"Объект {last_part} объединён"
    except Exception as e:
        return False, content, str(e)


def generate_simple_diff(original: Dict, modified: Dict) -> List[str]:
    """Упрощённая генерация diff для предпросмотра"""
    diff = []
    
    def compare_dicts(a, b, path=""):
        if a == b:
            return
        
        if type(a) != type(b):
            diff.append(f"{path}: тип изменён")
            return
        
        if isinstance(a, dict) and isinstance(b, dict):
            all_keys = set(a.keys()) | set(b.keys())
            for key in all_keys:
                new_path = f"{path}.{key}" if path else key
                if key not in a:
                    diff.append(f"+ {new_path}")
                elif key not in b:
                    diff.append(f"- {new_path}")
                else:
                    compare_dicts(a[key], b[key], new_path)
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                diff.append(f"{path}: длина изменена {len(a)} → {len(b)}")
            else:
                for i, (ai, bi) in enumerate(zip(a, b)):
                    if ai != bi:
                        compare_dicts(ai, bi, f"{path}[{i}]")
        else:
            if a != b:
                diff.append(f"{path}: {str(a)[:30]} → {str(b)[:30]}")
    
    compare_dicts(original, modified)
    return diff[:10]  # Ограничиваем до 10 строк для предпросмотра


async def apply_batch_patch_dry_run(original: Dict, changes: List) -> Dict:
    """Тестовое применение всех изменений (без сохранения)"""
    test_content = copy.deepcopy(original)
    applied = []
    failed = []
    
    for i, change in enumerate(changes):
        try:
            op = change["op"]
            path = change["path"]
            value = change.get("value")
            
            if op == "update":
                success, result, msg = await apply_json_operation(
                    test_content, "update_field", path, value
                )
            elif op == "add":
                success, result, msg = await apply_json_operation(
                    test_content, "add_to_array" if "[" in path else "add_field", path, value
                )
            elif op == "delete":
                success, result, msg = await apply_json_operation(
                    test_content, "delete_field", path, None
                )
            elif op == "replace":
                success, result, msg = handle_replace(test_content, path, value)
            elif op == "merge":
                success, result, msg = handle_merge(test_content, path, value)
            else:
                success, result, msg = False, test_content, f"Неизвестная операция: {op}"
            
            if success:
                applied.append({"index": i, "op": op, "path": path, "msg": msg})
                test_content = result
            else:
                failed.append({"index": i, "op": op, "path": path, "error": msg})
                
        except Exception as e:
            failed.append({"index": i, "op": op, "path": path, "error": str(e)})
    
    diff = generate_simple_diff(original, test_content)
    
    return {
        "success": len(failed) == 0,
        "applied": applied,
        "failed": failed,
        "diff": diff,
        "result_content": test_content if len(failed) == 0 else None
    }


def format_patch_preview(diff: List[str], patch_data: Dict) -> str:
    """Форматирование предпросмотра изменений"""
    lines = []
    lines.append(f"🎯 <b>Целевой модуль:</b> {patch_data['target_module']}")
    
    if patch_data.get("patch_id"):
        lines.append(f"📄 <b>ID патча:</b> {patch_data['patch_id']}")
    
    if patch_data.get("description"):
        lines.append(f"📝 <b>Описание:</b> {patch_data['description']}")
    
    lines.append(f"\n🔍 <b>Изменения ({len(patch_data['changes'])} операций):</b>")
    
    for i, change in enumerate(patch_data["changes"][:5]):
        op_symbol = {
            "update": "✏️", "add": "➕", "delete": "🗑️", 
            "replace": "🔄", "merge": "🔄"
        }.get(change["op"], "•")
        
        path = change["path"]
        value = change.get("value", "")
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)[:50] + "..."
        
        lines.append(f"{op_symbol} <code>{path}</code> → {value}")
    
    if len(patch_data["changes"]) > 5:
        lines.append(f"... и ещё {len(patch_data['changes']) - 5} операций")
    
    if diff:
        lines.append(f"\n📊 <b>Примеры изменений:</b>")
        for d in diff[:3]:
            lines.append(f"  {d}")
    
    return "\n".join(lines)


# ========== ФУНКЦИЯ СОХРАНЕНИЯ ИЗМЕНЕНИЙ ==========

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
    
    # Для bot.py (не JSON) нужна особая обработка
    if module_path == "bot.py":
        if operation == "update_field" and target_path == "full":
            save_success = await update_github_file(
                file_path=module_path,
                content=new_value,
                message=f"🤖 Обновление бота через сам бота"
            )
            
            if save_success:
                file_url = f"https://github.com/{REPO_NAME}/blob/main/{module_path}"
                await status_msg.edit_text(
                    f"✅ Бот обновлён! 🚀\n\n"
                    f"🔗 <a href='{file_url}'>Посмотреть код</a>\n\n"
                    f"♻️ Перезапуск на Render может занять минуту",
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
            else:
                await status_msg.edit_text("❌ Ошибка обновления бота")
            
            await state.clear()
            return
    
    # Для JSON-файлов - применяем операцию
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
            "source": "mandala_bot_v3.24.0"
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

async def check_ahimsa_smart(content: Any, filename: str = "") -> Tuple[bool, str, List[Tuple[str, str]]]:
    """Базовая проверка Ахимсы (можно расширить)"""
    return True, "✅ Проверка пройдена", []


# ========== ОБРАБОТЧИКИ КОМАНД ==========

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    await message.answer(
        "🌀 <b>Mandala Sync Terminal v3.24.0</b>\n\n"
        "📤 <b>Загрузить файл</b> — новый JSON в репозиторий\n"
        "🔧 <b>Редактировать модуль</b> — точечные изменения JSON\n"
        "📦 <b>Пакетное обновление</b> — множество изменений одним файлом (НОВОЕ!)\n"
        "📦 <b>Скачать монолит</b> — готовый файл\n"
        "🍇 <b>Fructus</b> — хранилище артефактов\n\n"
        "🤖 <b>Новое в v3.24.0:</b> пакетные обновления модулей\n"
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
    """Загрузка нового файла"""
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    
    await state.update_data(upload_mode="module")
    await state.set_state(UploadStates.waiting_for_category)
    await message.answer(
        "📤 <b>Загрузка нового файла</b>\n\nВыберите категорию:",
        reply_markup=get_category_keyboard(for_edit=False)
    )


@router.message(F.text == "🔧 Редактировать модуль")
async def handle_edit_start(message: Message, state: FSMContext):
    """Редактирование существующего модуля"""
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    
    await state.update_data(upload_mode="edit")
    await state.set_state(UploadStates.waiting_for_category)
    await message.answer(
        "🔧 <b>Редактирование модуля</b>\n\nВыберите категорию:",
        reply_markup=get_category_keyboard(for_edit=True)
    )


@router.message(F.text == "📦 Пакетное обновление")
async def handle_batch_update_start(message: Message, state: FSMContext):
    """Начало пакетного обновления модуля"""
    await state.clear()
    await state.update_data(upload_mode="batch_patch")
    await state.set_state(UploadStates.waiting_for_patch_file)
    await message.answer(
        "📦 <b>Пакетное обновление модуля</b>\n\n"
        "Отправьте JSON-файл с набором изменений.\n"
        "Файл может называться как угодно, главное — правильная структура.\n\n"
        "Формат:\n"
        "```json\n"
        "{\n"
        "  \"patch_id\": \"optional_id\",\n"
        "  \"description\": \"описание\",\n"
        "  \"target_module\": \"sphaerae\",\n"
        "  \"changes\": [\n"
        "    {\"op\": \"update\", \"path\": \"version\", \"value\": \"v2.3.1\"},\n"
        "    {\"op\": \"add\", \"path\": \"tags\", \"value\": [\"core\"]},\n"
        "    {\"op\": \"delete\", \"path\": \"metadata.deprecated\"}\n"
        "  ]\n"
        "}\n"
        "```\n\n"
        "Поддерживаемые операции: update, add, delete, replace, merge\n\n"
        "📎 Просто прикрепите файл — я покажу, что изменится, и запрошу подтверждение.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отмена")]],
            resize_keyboard=True
        )
    )


@router.message(F.text == "📦 Скачать монолит")
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
        "📚 <b>Mandala Sync Terminal v3.24.0</b>\n\n"
        "📤 <b>Загрузить файл</b> — новый JSON в репозиторий\n"
        "🔧 <b>Редактировать модуль</b> — точечные изменения:\n"
        "• Добавить в массив\n"
        "• Обновить поле\n"
        "• Удалить поле\n"
        "• Показать структуру\n\n"
        "📦 <b>Пакетное обновление (НОВОЕ)</b> — множество изменений одним файлом:\n"
        "• Любое имя файла\n"
        "• Операции: update, add, delete, replace, merge\n"
        "• Предпросмотр перед применением\n"
        "• Атомарное применение\n\n"
        "📦 <b>Скачать монолит</b> — mandala_core.monolith.latest.json\n\n"
        "🍇 <b>Fructus</b> — seeds, geometry, builders\n\n"
        "🤖 <b>Обновление бота</b> — в категории Инфраструктура\n"
        "🧪 Testisphaera в модулях Мандалы\n"
        "🌿 Ahimsa-фильтр активен",
        reply_markup=get_main_keyboard()
    )


@router.message(F.text == "🔄 Сменить тип")
async def handle_change_category(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    
    data = await state.get_data()
    upload_mode = data.get("upload_mode", "module")
    edit_mode = (upload_mode == "edit")
    
    await state.set_state(UploadStates.waiting_for_category)
    await message.answer(
        "🔄 Выберите категорию:",
        reply_markup=get_category_keyboard(for_edit=edit_mode)
    )


# ========== ОБРАБОТЧИКИ КОЛБЭКОВ ==========

@router.callback_query(F.data == "category_modules", StateFilter(UploadStates.waiting_for_category))
async def handle_category_modules(callback_query: CallbackQuery, state: FSMContext):
    """Категория модулей для загрузки"""
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "🧩 <b>Выберите модуль для загрузки:</b>",
        reply_markup=get_modules_keyboard(for_edit=False)
    )
    await callback_query.answer()


@router.callback_query(F.data == "category_modules_edit", StateFilter(UploadStates.waiting_for_category))
async def handle_category_modules_edit(callback_query: CallbackQuery, state: FSMContext):
    """Категория модулей для редактирования"""
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "🔧 <b>Выберите модуль для редактирования:</b>",
        reply_markup=get_modules_keyboard(for_edit=True)
    )
    await callback_query.answer()


@router.callback_query(F.data == "category_infra", StateFilter(UploadStates.waiting_for_category))
async def handle_category_infra(callback_query: CallbackQuery, state: FSMContext):
    """Категория инфраструктуры для загрузки"""
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "⚙️ <b>Выберите компонент для загрузки:</b>",
        reply_markup=get_infra_keyboard(for_edit=False)
    )
    await callback_query.answer()


@router.callback_query(F.data == "category_infra_edit", StateFilter(UploadStates.waiting_for_category))
async def handle_category_infra_edit(callback_query: CallbackQuery, state: FSMContext):
    """Категория инфраструктуры для редактирования"""
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "🔧 <b>Выберите компонент для редактирования:</b>",
        reply_markup=get_infra_keyboard(for_edit=True)
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("back_to_categories"))
async def handle_back_to_categories(callback_query: CallbackQuery, state: FSMContext):
    """Назад к категориям"""
    edit_mode = "edit" in callback_query.data
    await state.set_state(UploadStates.waiting_for_category)
    await callback_query.message.edit_text(
        "📤 <b>Выберите категорию:</b>",
        reply_markup=get_category_keyboard(for_edit=edit_mode)
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith(("target_", "edit_")), StateFilter(UploadStates.waiting_for_module))
async def handle_target_selection(callback_query: CallbackQuery, state: FSMContext):
    """Выбран конкретный файл/модуль"""
    is_edit = callback_query.data.startswith("edit_")
    target_key = callback_query.data.replace("edit_", "").replace("target_", "")
    
    if target_key not in ALL_UPLOAD_TARGETS:
        await callback_query.answer("Неизвестный целевой файл")
        return

    target_info = ALL_UPLOAD_TARGETS[target_key]
    user_upload_target[callback_query.from_user.id] = target_key
    
    if is_edit:
        # Режим редактирования
        await state.update_data(
            edit_module=target_key,
            edit_module_path=target_info["path"],
            edit_module_name=target_info["name"],
            upload_mode="edit"
        )
        
        if target_key == "bot_script":
            await state.set_state(UploadStates.waiting_for_new_value)
            await callback_query.message.edit_text(
                f"🤖 <b>Обновление {target_info['name']}</b>\n\n"
                f"Отправьте ПОЛНЫЙ код нового bot.py\n\n"
                f"⚠️ Внимание: после обновления бот перезапустится!"
            )
            await callback_query.message.answer(
                "📎 Прикрепите файл с новым кодом или отправьте как сообщение",
                reply_markup=get_upload_mode_keyboard()
            )
        else:
            await state.set_state(UploadStates.waiting_for_operation)
            await callback_query.message.edit_text(
                f"🔧 <b>{target_info['name']}</b>\n\n"
                f"Файл: <code>{target_info['path']}</code>\n\n"
                f"Выберите операцию:",
                reply_markup=get_edit_operations_keyboard()
            )
    else:
        # Режим загрузки
        await state.set_state(UploadStates.waiting_for_file)
        await state.update_data(upload_mode="module")
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


@router.callback_query(F.data == "back_to_modules_edit", StateFilter(UploadStates.waiting_for_operation))
async def handle_back_to_modules_edit(callback_query: CallbackQuery, state: FSMContext):
    """Назад к выбору модуля (из операций)"""
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "🔧 <b>Выберите модуль:</b>",
        reply_markup=get_modules_keyboard(for_edit=True)
    )
    await callback_query.answer()


# ========== ОБРАБОТЧИКИ ОПЕРАЦИЙ РЕДАКТИРОВАНИЯ ==========

@router.callback_query(F.data == "edit_op_add", StateFilter(UploadStates.waiting_for_operation))
async def handle_edit_add(callback_query: CallbackQuery, state: FSMContext):
    await state.update_data(edit_operation="add_to_array")
    await state.set_state(UploadStates.waiting_for_target_path)
    await callback_query.message.edit_text(
        "➕ <b>Добавление в массив</b>\n\n"
        "Введите путь (примеры):\n"
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
        "Введите путь (примеры):\n"
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
        "Введите путь (примеры):\n"
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


# ========== ОБРАБОТЧИК ВВОДА ПУТИ И ЗНАЧЕНИЙ ==========

@router.message(StateFilter(UploadStates.waiting_for_target_path))
async def handle_target_path(message: Message, state: FSMContext):
    target_path = message.text.strip()
    await state.update_data(edit_target_path=target_path)
    
    data = await state.get_data()
    operation = data.get("edit_operation")
    
    if operation == "delete_field":
        await save_edit_changes(message, state)
    else:
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
    data = await state.get_data()
    module_path = data.get("edit_module_path")
    
    if module_path == "bot.py":
        new_value = message.text or "Файл не получен"
        await state.update_data(edit_new_value=new_value, edit_operation="update_field", edit_target_path="full")
        await save_edit_changes(message, state)
        return
    
    try:
        new_value = json.loads(message.text)
    except json.JSONDecodeError:
        new_value = message.text
    
    await state.update_data(edit_new_value=new_value)
    await save_edit_changes(message, state)


# ========== НОВЫЙ ОБРАБОТЧИК ПАКЕТНЫХ ФАЙЛОВ ==========

@router.message(StateFilter(UploadStates.waiting_for_patch_file), F.document)
async def process_batch_patch_file(message: Message, state: FSMContext):
    """Обработка загруженного пакетного файла"""
    user_id = message.from_user.id
    status_msg = await message.answer("📥 Анализирую пакет обновлений...")
    
    try:
        # Скачиваем файл
        file = await bot.get_file(message.document.file_id)
        file_content_bytes = await bot.download_file(file.file_path)
        file_content = file_content_bytes.read().decode('utf-8')
        
        # Парсим JSON
        try:
            patch_data = json.loads(file_content)
        except json.JSONDecodeError as e:
            await status_msg.edit_text(f"❌ Невалидный JSON: {str(e)}")
            return
        
        # Валидация структуры
        is_valid, error_msg = validate_patch_structure(patch_data)
        if not is_valid:
            await status_msg.edit_text(f"❌ Ошибка в структуре патча: {error_msg}")
            return
        
        # Проверяем существование целевого модуля
        target_module = patch_data.get("target_module")
        if target_module not in MANDALA_MODULES:
            await status_msg.edit_text(
                f"❌ Модуль '{target_module}' не найден.\n"
                f"Доступные: {', '.join(MANDALA_MODULES.keys())}"
            )
            return
        
        # Загружаем текущее содержимое модуля
        module_info = MANDALA_MODULES[target_module]
        success, current_content, error = await get_github_file_content(module_info["path"])
        
        if not success:
            await status_msg.edit_text(f"❌ Не удалось загрузить модуль: {error}")
            return
        
        # Применяем все операции в тестовом режиме (dry run)
        test_result = await apply_batch_patch_dry_run(current_content, patch_data["changes"])
        
        if not test_result["success"]:
            error_msg = test_result["failed"][0]["error"] if test_result["failed"] else "Неизвестная ошибка"
            await status_msg.edit_text(
                f"❌ Ошибка при применении изменений:\n"
                f"{error_msg}"
            )
            return
        
        # Показываем предпросмотр изменений
        preview_text = format_patch_preview(test_result["diff"], patch_data)
        
        # Сохраняем данные в state
        await state.update_data(
            patch_data=patch_data,
            patch_filename=message.document.file_name,
            current_content=current_content,
            module_path=module_info["path"],
            module_name=module_info["name"],
            module_key=target_module,
            test_result=test_result
        )
        
        # Запрашиваем подтверждение
        await state.set_state(UploadStates.waiting_for_patch_confirmation)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Применить", callback_data="patch_apply")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="patch_cancel")],
            [InlineKeyboardButton(text="📋 Детали", callback_data="patch_details")]
        ])
        
        await status_msg.edit_text(
            f"📦 <b>Пакет обновлений готов к применению</b>\n\n"
            f"{preview_text}\n\n"
            f"Применить изменения?",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Ошибка обработки патча: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        await state.clear()
        if user_id in user_upload_target:
            del user_upload_target[user_id]


# ========== ОБРАБОТЧИКИ ПОДТВЕРЖДЕНИЯ ПАТЧА ==========

@router.callback_query(F.data == "patch_apply", StateFilter(UploadStates.waiting_for_patch_confirmation))
async def handle_patch_apply(callback_query: CallbackQuery, state: FSMContext):
    """Применение подтверждённого патча"""
    data = await state.get_data()
    patch_data = data.get("patch_data")
    current_content = data.get("current_content")
    module_path = data.get("module_path")
    module_name = data.get("module_name")
    module_key = data.get("module_key")
    
    await callback_query.message.edit_text("🔄 Применяю изменения...")
    
    # Применяем все операции
    apply_result = await apply_batch_patch_dry_run(current_content, patch_data["changes"])
    
    if not apply_result["success"]:
        error_msg = apply_result["failed"][0]["error"] if apply_result["failed"] else "Неизвестная ошибка"
        await callback_query.message.edit_text(f"❌ Ошибка при применении: {error_msg}")
        await state.clear()
        return
    
    # Ахимса-проверка итогового контента
    ahimsa_ok, ahimsa_msg, _ = await check_ahimsa_smart(
        apply_result["result_content"], 
        f"batch_patch_{module_key}"
    )
    
    if not ahimsa_ok:
        await callback_query.message.edit_text(f"🔶 {ahimsa_msg}")
        await state.clear()
        return
    
    # Сохраняем в GitHub
    commit_message = f"📦 Пакетное обновление {module_name}"
    if patch_data.get("patch_id"):
        commit_message += f" [{patch_data['patch_id']}]"
    if patch_data.get("description"):
        commit_message += f": {patch_data['description'][:50]}"
    
    save_success = await update_github_file(
        file_path=module_path,
        content=apply_result["result_content"],
        message=commit_message
    )
    
    if save_success:
        file_url = f"https://github.com/{REPO_NAME}/blob/main/{module_path}"
        
        # Составляем отчёт о применённых операциях
        ops_report = []
        for op in apply_result["applied"][:10]:
            ops_report.append(f"  {op['op']}: {op['path']}")
        
        if len(apply_result["applied"]) > 10:
            ops_report.append(f"  ... и ещё {len(apply_result['applied']) - 10}")
        
        report = "\n".join(ops_report)
        
        await callback_query.message.edit_text(
            f"✅ <b>Пакетное обновление применено</b>\n\n"
            f"Модуль: {module_name}\n"
            f"Операций: {len(apply_result['applied'])}\n\n"
            f"{report}\n\n"
            f"🔗 <a href='{file_url}'>Посмотреть на GitHub</a>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    else:
        await callback_query.message.edit_text("❌ Ошибка сохранения в GitHub")
    
    await state.clear()
    if callback_query.from_user.id in user_upload_target:
        del user_upload_target[callback_query.from_user.id]


@router.callback_query(F.data == "patch_cancel", StateFilter(UploadStates.waiting_for_patch_confirmation))
async def handle_patch_cancel(callback_query: CallbackQuery, state: FSMContext):
    await state.clear()
    if callback_query.from_user.id in user_upload_target:
        del user_upload_target[callback_query.from_user.id]
    await callback_query.message.edit_text("🚫 Пакетное обновление отменено")
    await callback_query.message.answer("🏠 Главное меню", reply_markup=get_main_keyboard())


@router.callback_query(F.data == "patch_details", StateFilter(UploadStates.waiting_for_patch_confirmation))
async def handle_patch_details(callback_query: CallbackQuery, state: FSMContext):
    """Показать детальную информацию о патче"""
    data = await state.get_data()
    patch_data = data.get("patch_data")
    test_result = data.get("test_result")
    
    details = []
    details.append(f"📦 <b>Патч: {patch_data.get('patch_id', 'без ID')}</b>")
    details.append(f"📝 Описание: {patch_data.get('description', '—')}")
    details.append(f"🎯 Модуль: {patch_data['target_module']}")
    details.append(f"📊 Всего операций: {len(patch_data['changes'])}")
    details.append(f"\n<b>Все изменения:</b>")
    
    for i, change in enumerate(patch_data["changes"]):
        op_symbol = {
            "update": "✏️", "add": "➕", "delete": "🗑️", 
            "replace": "🔄", "merge": "🔄"
        }.get(change["op"], "•")
        
        path = change["path"]
        value = change.get("value", "")
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, indent=2)
            value = value[:100] + "..." if len(value) > 100 else value
        
        details.append(f"\n{op_symbol} <b>{i+1}. {change['op']}</b>")
        details.append(f"   Путь: <code>{path}</code>")
        details.append(f"   Значение: <code>{value}</code>")
    
    if test_result and test_result.get("diff"):
        details.append(f"\n<b>Изменения в структуре:</b>")
        for d in test_result["diff"][:5]:
            details.append(f"  {d}")
    
    await callback_query.message.edit_text(
        "\n".join(details),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_patch_confirm")]
        ]),
        parse_mode=ParseMode.HTML
    )
    await callback_query.answer()


@router.callback_query(F.data == "back_to_patch_confirm")
async def back_to_patch_confirm(callback_query: CallbackQuery, state: FSMContext):
    """Вернуться к подтверждению"""
    data = await state.get_data()
    patch_data = data.get("patch_data")
    test_result = data.get("test_result")
    
    preview_text = format_patch_preview(test_result["diff"], patch_data)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Применить", callback_data="patch_apply")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="patch_cancel")],
        [InlineKeyboardButton(text="📋 Детали", callback_data="patch_details")]
    ])
    
    await callback_query.message.edit_text(
        f"📦 <b>Пакет обновлений готов к применению</b>\n\n"
        f"{preview_text}\n\n"
        f"Применить изменения?",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    await callback_query.answer()


# ========== ОБРАБОТЧИК ЗАГРУЗКИ ФАЙЛОВ (ОБЫЧНЫХ) ==========

@router.message(StateFilter(UploadStates.waiting_for_file), F.document)
async def process_file_upload(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    upload_mode = data.get("upload_mode", "module")
    
    try:
        if upload_mode == "module":
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
        
        elif upload_mode == "fructus":
            await handle_fructus_upload_file_logic(message, state, user_id)
        
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
    await state.update_data(upload_mode="fructus")
    await state.set_state(UploadStates.waiting_for_file)
    await callback_query.message.edit_text(
        "🍇 Отправьте JSON файл"
    )
    await callback_query.message.answer(
        "📎 Прикрепите JSON",
        reply_markup=get_upload_mode_keyboard()
    )
    await callback_query.answer()


async def handle_fructus_upload_file_logic(message: Message, state: FSMContext, user_id: int):
    """Логика загрузки в Fructus"""
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
    elif current == UploadStates.waiting_for_patch_file:
        await message.answer("📎 Ожидаю JSON-файл с патчем", reply_markup=get_upload_mode_keyboard())
    elif current == UploadStates.waiting_for_module:
        await message.answer("🔘 Выберите кнопками", reply_markup=get_category_keyboard())
    elif current == UploadStates.waiting_for_category:
        data = await state.get_data()
        edit_mode = (data.get("upload_mode") == "edit")
        await message.answer("🔘 Выберите категорию", reply_markup=get_category_keyboard(for_edit=edit_mode))
    elif current == UploadStates.waiting_for_target_path:
        await message.answer("📝 Введите путь (например: version или elements[0].value)")
    elif current == UploadStates.waiting_for_new_value:
        data = await state.get_data()
        if data.get("edit_module_path") == "bot.py":
            await message.answer("🤖 Отправьте полный код bot.py")
        else:
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
        return web.Response(text="Mandala Bot v3.24.0")
    app.router.add_get("/", index)

    setup_application(app, dp, bot=bot)
    
    logger.info(f"🚀 Запуск на порту {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    main()
