#!/usr/bin/env python3
"""
Mandala Sync Terminal Bot v3.16
Render Web Service + Webhook (Aiogram 3)
Полный монолит. Работает 24/7 с бесплатным пингом.
"""

import os
import sys
import json
import logging
import uuid
import base64
import asyncio
from datetime import datetime
from typing import Dict, List, Tuple
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

# Render автоматически подставит эти переменные
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
PORT = int(os.getenv("PORT", 8000))
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "mandala-secret")

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден")
    sys.exit(1)

if not RENDER_EXTERNAL_URL:
    logger.error("❌ RENDER_EXTERNAL_URL не задан (Render сам его ставит)")
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
    waiting_for_module_choice = State()
    waiting_for_file = State()

CORE_FILES = {
    "initium": "initium.json",
    "sphaerae": "sphaerae.json",
    "akasha": "akasha_chronicorum.json",
    "philosophia": "philosophia.json",
    "monolith": "mandala_core.monolith.json"
}

user_module_choice = {}

# ========== 5. ГИБРИДНАЯ СИСТЕМА МЕНЮ ==========
def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню - основные действия (всегда видимое)"""
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
    """Меню во время загрузки файла"""
    keyboard = [
        [KeyboardButton(text="❌ Отмена")],
        [KeyboardButton(text="🔄 Сменить модуль")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=True
    )

def get_monolith_inline_keyboard() -> InlineKeyboardMarkup:
    """Инлайн меню для монолита"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📥 Скачать монолит", callback_data="download_monolith"),
            InlineKeyboardButton(text="📋 Информация", callback_data="info_monolith")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def get_modules_inline_keyboard() -> InlineKeyboardMarkup:
    """Инлайн меню выбора модуля (только core-модули)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌀 Initium", callback_data="module_initium"),
            InlineKeyboardButton(text="🌐 Sphaerae", callback_data="module_sphaerae")
        ],
        [
            InlineKeyboardButton(text="📜 Akasha", callback_data="module_akasha"),
            InlineKeyboardButton(text="💭 Philosophia", callback_data="module_philosophia")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def get_fructus_inline_keyboard() -> InlineKeyboardMarkup:
    """Инлайн меню Fructus (отдельный пункт)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📤 Загрузить", callback_data="fructus_upload"),
            InlineKeyboardButton(text="📋 Информация", callback_data="fructus_info")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

# ========== 6. УМНЫЙ AHIMSA-ФИЛЬТР ==========
async def check_ahimsa_smart(content: Dict) -> Tuple[bool, str, List[Tuple[str, str]]]:
    """Умная проверка Ahimsa, которая игнорирует поля с кодом"""
    try:
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
            "применение насилия",
            "физическое воздействие",
            "принуждение к работе",
            "эксплуатация человека",
            "дискриминация по",
            "унижение достоинства",
            "причинение вреда здоровью",
            "угроза жизни",
            "психологическое давление"
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
        logger.error(f"Ошибка при умной проверке Ahimsa: {e}")
        return True, f"⚠️ Проверка пропущена (ошибка: {str(e)[:50]})", []

# ========== 7. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
async def update_github_file(file_path: str, content: Dict, message: str) -> bool:
    """Обновление файла в GitHub"""
    try:
        url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                sha = None
                if response.status == 200:
                    data = await response.json()
                    sha = data.get("sha")
                elif response.status != 404:
                    logger.error(f"Не удалось получить файл: {response.status}")
                    return False

            content_str = json.dumps(content, ensure_ascii=False, indent=2)
            content_bytes = content_str.encode('utf-8')
            content_base64 = base64.b64encode(content_bytes).decode('utf-8')

            payload = {
                "message": message,
                "content": content_base64,
                "sha": sha
            }

            async with session.put(url, headers=headers, json=payload) as response:
                if response.status in [200, 201]:
                    logger.info(f"Файл {file_path} обновлён в GitHub")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка обновления GitHub: {response.status} - {error_text}")
                    return False

    except Exception as e:
        logger.error(f"Ошибка в update_github_file: {e}")
        return False

def generate_fructus_filename(original_name: str, file_type: str = "artifact") -> str:
    """Генерация уникального имени для артефакта"""
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
    """Загрузка артефакта в fructus"""
    try:
        file_type = "artifact"
        if "mandala" in original_filename.lower() or "core" in original_filename.lower():
            file_type = "mandala"
        elif "log" in original_filename.lower() or "report" in original_filename.lower():
            file_type = "log"
        elif "export" in original_filename.lower() or "data" in original_filename.lower():
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
                "source": "mandala_bot_v3.16"
            }

        success = await update_github_file(
            file_path=full_path,
            content=enhanced_content,
            message=f"Fructus artifact upload: {original_filename} → {target_filename}"
        )

        return success, target_filename

    except Exception as e:
        logger.error(f"Ошибка при загрузке в fructus: {e}")
        return False, str(e)

async def download_monolith_file() -> Tuple[bool, bytes, str]:
    """Скачивание монолита с GitHub"""
    try:
        url = f"https://raw.githubusercontent.com/voodoomushroomzzz-source/mandala-core/main/build/mandala_core.monolith.latest.json"
        headers = {}

        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    content = await response.read()
                    logger.info("✅ Монолит скачан с GitHub")
                    return True, content, "mandala_core.monolith.json"
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка скачивания монолита: {response.status} - {error_text}")
                    return False, b"", f"Ошибка {response.status}: {error_text}"

    except Exception as e:
        logger.error(f"Ошибка в download_monolith_file: {e}")
        return False, b"", str(e)

# ========== 8. ОСНОВНЫЕ ОБРАБОТЧИКИ КОМАНД ==========
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Старт бота - показывает главное меню"""
    await state.clear()

    user_id = message.from_user.id
    if user_id in user_module_choice:
        del user_module_choice[user_id]

    await message.answer(
        "🌀 <b>Mandala Sync Terminal v3.16</b>\n\n"
        "<b>Улучшения:</b>\n"
        "✅ Полный монолит для Render Web Service\n"
        "✅ Добавлен модуль Philosophia\n"
        "✅ Fructus выведен в отдельный пункт меню\n"
        "✅ Умный Ahimsa-фильтр (игнорирует код)\n"
        "✅ Исправлены все известные ошибки\n\n"
        "<b>Выберите действие:</b>",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "❌ Отмена")
async def handle_cancel_button(message: Message, state: FSMContext):
    """Отмена через правую кнопку"""
    await state.clear()

    user_id = message.from_user.id
    if user_id in user_module_choice:
        del user_module_choice[user_id]

    await message.answer(
        "🚫 <b>Действие отменено</b>\n"
        "Возвращаюсь в главное меню...",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "📤 Загрузить файл")
async def handle_upload_start(message: Message, state: FSMContext):
    """Начало загрузки файла"""
    await state.clear()

    user_id = message.from_user.id
    if user_id in user_module_choice:
        del user_module_choice[user_id]

    await message.answer(
        "📤 <b>Выберите модуль для загрузки файла:</b>\n\n"
        "<b>Доступные модули:</b>\n"
        "• 🌀 Initium — загрузочный модуль\n"
        "• 🌐 Sphaerae — текущие проекты\n"
        "• 📜 Akasha — архив проектов\n"
        "• 💭 Philosophia — философское ядро\n\n"
        "<i>Используйте кнопки ниже</i>",
        reply_markup=get_modules_inline_keyboard()
    )
    await state.set_state(UploadStates.waiting_for_module_choice)

@router.message(F.text == "📦 Монолит")
async def handle_monolith_menu(message: Message):
    """Меню монолита через правую кнопку"""
    await message.answer(
        "📦 <b>Монолит Mandala Core</b>\n\n"
        "Файл: <code>mandala_core.monolith.json</code>\n"
        "Размер: ~150-300KB\n\n"
        "<b>Выберите действие:</b>",
        reply_markup=get_monolith_inline_keyboard()
    )

@router.message(F.text == "🍇 Fructus")
async def handle_fructus_menu(message: Message):
    """Меню Fructus через правую кнопку (отдельный пункт)"""
    await message.answer(
        "🍇 <b>Fructus - система артефактов</b>\n\n"
        "Хранит сгенерированные артефакты системы.\n"
        "<b>Выберите действие:</b>",
        reply_markup=get_fructus_inline_keyboard()
    )

@router.message(F.text == "ℹ️ Помощь")
async def handle_help(message: Message):
    """Помощь"""
    await message.answer(
        "📚 <b>Mandala Sync Terminal v3.16</b>\n\n"
        "<b>Основные функции:</b>\n"
        "• 📤 Загрузить файл — выбор модуля (Initium, Sphaerae, Akasha, Philosophia)\n"
        "• 📦 Монолит — скачать/информация о монолите\n"
        "• 🍇 Fructus — отдельная загрузка артефактов\n"
        "• ℹ️ Помощь — эта справка\n\n"
        "<b>Процесс загрузки модуля:</b>\n"
        "1. Нажмите '📤 Загрузить файл'\n"
        "2. Выберите модуль\n"
        "3. Отправьте JSON файл\n"
        "4. Бот проверит Ahimsa и загрузит в GitHub\n\n"
        "<b>Процесс загрузки артефакта (Fructus):</b>\n"
        "1. Нажмите '🍇 Fructus'\n"
        "2. Выберите '📤 Загрузить'\n"
        "3. Отправьте JSON файл\n"
        "4. Файл сохранится с уникальным именем в папку fructus/\n\n"
        "<b>Улучшения в v3.16:</b>\n"
        "✅ Полная поддержка Render Web Service (вебхуки)\n"
        "✅ Модуль Philosophia интегрирован\n"
        "✅ Fructus выведен в отдельное меню\n"
        "✅ Умный Ahimsa-фильтр\n"
        "✅ Стабильная работа 24/7",
        reply_markup=get_main_keyboard()
    )

# ========== 9. ОБРАБОТЧИКИ ИНЛАЙН-МЕНЮ (МОНОЛИТ) ==========
@router.callback_query(F.data == "download_monolith")
async def handle_download_monolith(callback_query: CallbackQuery):
    """Скачивание и отправка монолита"""
    await callback_query.message.edit_text(
        "📦 <b>Скачиваю монолит...</b>\n"
        "Пожалуйста, подождите."
    )

    success, content, filename = await download_monolith_file()

    if success and content:
        await callback_query.message.answer_document(
            document=BufferedInputFile(content, filename=filename),
            caption="📦 <b>Монолит Mandala Core</b>\n"
                    "Единый файл со всеми модулями системы."
        )
        await callback_query.message.edit_text(
            "✅ <b>Монолит успешно отправлен!</b>"
        )
    else:
        await callback_query.message.edit_text(
            f"❌ <b>Не удалось скачать монолит</b>\n\n"
            f"<b>Причина:</b> {filename}"
        )

    await callback_query.answer()

@router.callback_query(F.data == "info_monolith")
async def handle_info_monolith(callback_query: CallbackQuery):
    """Информация о монолите"""
    await callback_query.message.edit_text(
        "📋 <b>Информация о монолите</b>\n\n"
        "<b>Что такое монолит?</b>\n"
        "Единый JSON-файл, содержащий все модули Mandala Core.\n\n"
        "<b>Содержимое:</b>\n"
        "• Initium (ядро)\n"
        "• Sphaerae (проекты)\n"
        "• Akasha (архив)\n"
        "• Philosophia (философия)\n"
        "• External_KB_Manifest\n\n"
        "<b>Путь в GitHub:</b>\n"
        "<code>mandala_core.monolith.json</code>",
        reply_markup=get_monolith_inline_keyboard()
    )
    await callback_query.answer()

# ========== 10. ОБРАБОТЧИКИ ВЫБОРА МОДУЛЯ ==========
@router.callback_query(F.data.startswith("module_"))
async def handle_module_selection(callback_query: CallbackQuery, state: FSMContext):
    """Выбор модуля через инлайн-меню"""
    module_map = {
        "module_initium": "initium",
        "module_sphaerae": "sphaerae",
        "module_akasha": "akasha",
        "module_philosophia": "philosophia"
    }

    callback_data = callback_query.data
    module_name = module_map.get(callback_data)

    if not module_name:
        await callback_query.answer("Неизвестный модуль")
        return

    user_module_choice[callback_query.from_user.id] = module_name

    module_display = {
        "initium": "🌀 INITIUM",
        "sphaerae": "🌐 SPHAERAE",
        "akasha": "📜 AKASHA",
        "philosophia": "💭 PHILOSOPHIA"
    }

    instruction = (
        f"✅ <b>Выбран модуль: {module_display[module_name]}</b>\n\n"
        f"<b>Теперь отправьте JSON файл.</b>\n"
        f"<i>Файл будет переименован в <b>{CORE_FILES[module_name]}</b></i>\n\n"
        f"<b>Ahimsa проверка:</b> ✅ Умная (игнорирует код)\n"
        f"<b>GitHub синхронизация:</b> ✅ Готова"
    )

    await state.set_state(UploadStates.waiting_for_file)
    await callback_query.message.edit_text(instruction)
    await callback_query.message.answer(
        "📎 <b>Прикрепите файл как документ</b>\n"
        "Используйте кнопку '📎' для прикрепления",
        reply_markup=get_upload_mode_keyboard()
    )
    await callback_query.answer()

# ========== 11. ОБРАБОТЧИКИ FRUCTUS ==========
@router.callback_query(F.data == "fructus_info")
async def handle_fructus_info(callback_query: CallbackQuery):
    """Информация о Fructus"""
    await callback_query.message.edit_text(
        "📋 <b>Информация о Fructus</b>\n\n"
        "<b>Назначение:</b> Хранение артефактов системы:\n"
        "• Логи выполнения\n"
        "• Экспортированные отчёты\n"
        "• Промежуточные данные\n"
        "• Результаты работы ИИ\n\n"
        "<b>Особенности:</b>\n"
        "• Уникальные имена файлов\n"
        "• Автоматические метаданные\n"
        "• Ahimsa проверка (умная)\n"
        "• GitHub синхронизация\n\n"
        "<b>Использование:</b>\n"
        "Нажмите '📤 Загрузить' и отправьте файл",
        reply_markup=get_fructus_inline_keyboard()
    )
    await callback_query.answer()

@router.callback_query(F.data == "fructus_upload")
async def handle_fructus_upload(callback_query: CallbackQuery, state: FSMContext):
    """Начало загрузки в Fructus"""
    user_module_choice[callback_query.from_user.id] = "fructus"

    await state.set_state(UploadStates.waiting_for_file)
    await callback_query.message.edit_text(
        "✅ <b>Выбран модуль: 🍇 FRUCTUS</b>\n\n"
        "<b>Теперь отправьте JSON файл как артефакт.</b>\n\n"
        "<b>Особенности:</b>\n"
        "• Уникальное имя файла\n"
        "• Автоматические метаданные\n"
        "• Сохранится в fructus/\n\n"
        "<b>Ahimsa проверка:</b> ✅ Умная (игнорирует код)\n"
        "<b>GitHub синхронизация:</b> ✅ Готова"
    )
    await callback_query.message.answer(
        "📎 <b>Прикрепите файл как документ</b>",
        reply_markup=get_upload_mode_keyboard()
    )
    await callback_query.answer()

# ========== 12. ОБРАБОТЧИК ОТМЕНЫ ==========
@router.callback_query(F.data == "cancel")
async def handle_cancel_inline(callback_query: CallbackQuery, state: FSMContext):
    """Отмена через инлайн-меню"""
    await state.clear()

    user_id = callback_query.from_user.id
    if user_id in user_module_choice:
        del user_module_choice[user_id]

    await callback_query.message.edit_text("🚫 <b>Действие отменено</b>")
    await callback_query.answer()

    await callback_query.message.answer(
        "🏠 <b>Возврат в главное меню</b>",
        reply_markup=get_main_keyboard()
    )

# ========== 13. ОБРАБОТКА ЗАГРУЗКИ ФАЙЛОВ ==========
@router.message(StateFilter(UploadStates.waiting_for_file))
async def process_file_upload(message: Message, state: FSMContext):
    """Обработка загруженного файла"""
    user_id = message.from_user.id

    if user_id not in user_module_choice:
        await message.answer(
            "⚠️ Сначала выберите модуль",
            reply_markup=get_modules_inline_keyboard()
        )
        return

    module_name = user_module_choice[user_id]

    if not message.document:
        await message.answer(
            "⚠️ Отправьте файл в формате JSON\n"
            "Используйте кнопку '📎' для прикрепления",
            reply_markup=get_upload_mode_keyboard()
        )
        return

    original_filename = message.document.file_name
    if not original_filename.lower().endswith('.json'):
        await message.answer(
            "⚠️ Поддерживаются только файлы JSON\n"
            "Пожалуйста, отправьте файл с расширением .json",
            reply_markup=get_upload_mode_keyboard()
        )
        return

    await message.answer(
        "📥 <b>Скачиваю файл...</b>",
        reply_markup=get_upload_mode_keyboard()
    )

    try:
        file = await bot.get_file(message.document.file_id)
        file_content_bytes = await bot.download_file(file.file_path)
        file_content = file_content_bytes.read().decode('utf-8')

        try:
            json_content = json.loads(file_content)
        except json.JSONDecodeError as e:
            await message.answer(
                f"⚠️ <b>Неверный формат JSON</b>\n\n"
                f"<b>Причина:</b> {str(e)}",
                reply_markup=get_upload_mode_keyboard()
            )
            return

        await message.answer(
            "🌿 <b>Проверяю через умную линзу Ахимсы...</b>",
            reply_markup=get_upload_mode_keyboard()
        )

        ahimsa_ok, ahimsa_message, ahimsa_issues = await check_ahimsa_smart(json_content)

        if not ahimsa_ok:
            issues_text = "\n".join([f"• <b>{category}</b>: {description}" for category, description in ahimsa_issues])

            await message.answer(
                f"🔶 <b>Ahimsa проверка не пройдена</b>\n\n"
                f"<b>Общее сообщение:</b> {ahimsa_message}\n\n"
                f"<b>Найденные проблемы:</b>\n{issues_text}",
                reply_markup=get_upload_mode_keyboard()
            )
            return

        await message.answer(
            f"✅ <b>Ahimsa проверка:</b> {ahimsa_message}",
            reply_markup=get_upload_mode_keyboard()
        )

        if module_name == "fructus":
            await message.answer(
                f"🔄 <b>Загружаю артефакт в fructus...</b>",
                reply_markup=get_upload_mode_keyboard()
            )

            success, generated_filename = await upload_to_fructus(
                original_filename=original_filename,
                content=json_content,
                user_id=user_id
            )

            if success:
                result_text = (
                    f"✅ <b>Артефакт успешно загружен в fructus!</b>\n\n"
                    f"<b>Исходное имя:</b> {original_filename}\n"
                    f"<b>Сгенерированное имя:</b> {generated_filename}\n"
                    f"<b>Путь:</b> fructus/{generated_filename}\n"
                    f"<b>Размер:</b> {len(file_content)} символов"
                )
                logger.info(f"Артефакт загружен: {original_filename} → {generated_filename}")
            else:
                result_text = (
                    f"🔶 <b>Ошибка при загрузке в fructus</b>\n\n"
                    f"<b>Причина:</b> {generated_filename}"
                )

            await state.clear()
            if user_id in user_module_choice:
                del user_module_choice[user_id]

            await message.answer(
                result_text,
                reply_markup=get_main_keyboard()
            )
            return

        target_filename = CORE_FILES.get(module_name)
        if not target_filename:
            await message.answer(
                "⚠️ Модуль не найден",
                reply_markup=get_main_keyboard()
            )
            await state.clear()
            return

        await message.answer(
            f"🔄 <b>Загружаю в модуль {module_name.upper()}...</b>",
            reply_markup=get_upload_mode_keyboard()
        )

        success = await update_github_file(
            file_path=target_filename,
            content=json_content,
            message=f"Обновление {target_filename} через Mandala Bot v3.16"
        )

        if success:
            result_text = (
                f"✅ <b>Файл успешно загружен!</b>\n\n"
                f"<b>Модуль:</b> {module_name.upper()}\n"
                f"<b>Файл:</b> {target_filename}\n"
                f"<b>Размер:</b> {len(file_content)} символов"
            )
            logger.info(f"Файл загружен: {original_filename} → {target_filename}")
        else:
            result_text = (
                f"🔶 <b>Ошибка при загрузке</b>\n\n"
                f"Проверьте настройки в .env файле"
            )

        await state.clear()
        if user_id in user_module_choice:
            del user_module_choice[user_id]

        await message.answer(
            result_text,
            reply_markup=get_main_keyboard()
        )

    except Exception as e:
        logger.error(f"Ошибка в process_file_upload: {e}")
        await message.answer(
            f"🔶 <b>Ошибка при обработке файла</b>\n\n"
            f"<b>Причина:</b> {str(e)}",
            reply_markup=get_main_keyboard()
        )

        await state.clear()
        if user_id in user_module_choice:
            del user_module_choice[user_id]

# ========== 14. ОБРАБОТКА КНОПКИ "🔄 Сменить модуль" ==========
@router.message(F.text == "🔄 Сменить модуль")
async def handle_change_module(message: Message, state: FSMContext):
    """Смена модуля во время загрузки"""
    user_id = message.from_user.id
    if user_id in user_module_choice:
        del user_module_choice[user_id]

    await state.set_state(UploadStates.waiting_for_module_choice)
    await message.answer(
        "🔄 <b>Выберите другой модуль:</b>",
        reply_markup=get_modules_inline_keyboard()
    )

# ========== 15. ОБРАБОТКА ЛЮБЫХ ДРУГИХ СООБЩЕНИЙ ==========
@router.message()
async def handle_other_messages(message: Message, state: FSMContext):
    """Обработка любых других сообщений"""
    current_state = await state.get_state()

    if current_state == UploadStates.waiting_for_file:
        await message.answer(
            "ℹ️ <b>Ожидается загрузка файла</b>\n\n"
            "Пожалуйста, отправьте JSON файл для загрузки.\n"
            "Или используйте меню для отмены.",
            reply_markup=get_upload_mode_keyboard()
        )
    elif current_state == UploadStates.waiting_for_module_choice:
        await message.answer(
            "ℹ️ <b>Выберите модуль для загрузки</b>\n\n"
            "Используйте кнопки ниже для выбора.",
            reply_markup=get_modules_inline_keyboard()
        )
    else:
        await message.answer(
            "ℹ️ <b>Используйте меню для навигации</b>\n\n"
            "Напишите /start или используйте кнопки.",
            reply_markup=get_main_keyboard()
        )

# ========== 16. WEBHOOK ЗАПУСК ==========
async def on_startup() -> None:
    """Установка веб-хука при старте"""
    await bot.set_webhook(
        WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True
    )
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown() -> None:
    """Удаление веб-хука при остановке"""
    await bot.delete_webhook()
    logger.info("❌ Webhook удалён")

def main():
    """Запуск aiohttp сервера с веб-хуками"""
    app = web.Application()

    # Обработчик веб-хука от Telegram
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET
    ).register(app, path=WEBHOOK_PATH)

    # Healthcheck для Render (обязательно!)
    async def health(_):
        return web.Response(text="OK")
    app.router.add_get("/healthcheck", health)

    # Корневой маршрут — просто заглушка
    async def index(_):
        return web.Response(text="Mandala Bot is running")
    app.router.add_get("/", index)

    setup_application(app, dp, bot=bot)

    logger.info(f"🚀 Запуск сервера на порту {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    main()
