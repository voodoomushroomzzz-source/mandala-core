#!/usr/bin/env python3
"""
Mandala Sync Terminal Bot v3.17
Render Web Service + Webhook (Aiogram 3)
СТАБИЛЬНАЯ ВЕРСИЯ:
- Порт принудительно 10000 (Render не перезапускает)
- Webhook не удаляется при shutdown
- RENDER_EXTERNAL_URL можно задать вручную
- Ahimsa-фильтр, Fructus, все модули
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

# ⚡ Render автоматически выдаёт URL, но можно задать вручную
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
# ⚡ Порт ФИКСИРУЕМ принудительно — Render требует 10000 для Free Web Services
PORT = 10000
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "mandala-secret"  # ⚡ Хардкод, не берём из env

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден")
    sys.exit(1)

if not RENDER_EXTERNAL_URL:
    logger.error("❌ RENDER_EXTERNAL_URL не задан. Добавь в Environment Render вручную!")
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
        [KeyboardButton(text="🔄 Сменить модуль")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=True
    )

def get_monolith_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📥 Скачать монолит", callback_data="download_monolith"),
            InlineKeyboardButton(text="📋 Информация", callback_data="info_monolith")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def get_modules_inline_keyboard() -> InlineKeyboardMarkup:
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📤 Загрузить", callback_data="fructus_upload"),
            InlineKeyboardButton(text="📋 Информация", callback_data="fructus_info")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

# ========== AHIMSA-ФИЛЬТР ==========
async def check_ahimsa_smart(content: Dict) -> Tuple[bool, str, List[Tuple[str, str]]]:
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
        logger.error(f"Ошибка при умной проверке Ahimsa: {e}")
        return True, f"⚠️ Проверка пропущена (ошибка: {str(e)[:50]})", []

# ========== GITHUB ФУНКЦИИ ==========
async def update_github_file(file_path: str, content: Dict, message: str) -> bool:
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
                "source": "mandala_bot_v3.17"
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
    if user_id in user_module_choice:
        del user_module_choice[user_id]
    await message.answer(
        "🌀 <b>Mandala Sync Terminal v3.17</b>\n\n"
        "<b>Стабильная версия:</b>\n"
        "✅ Порт 10000 фиксирован\n"
        "✅ Webhook не удаляется при перезапуске\n"
        "✅ Пинг корневого URL будит надёжно\n\n"
        "<b>Выберите действие:</b>",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "❌ Отмена")
async def handle_cancel_button(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_module_choice:
        del user_module_choice[user_id]
    await message.answer("🚫 Действие отменено", reply_markup=get_main_keyboard())

@router.message(F.text == "📤 Загрузить файл")
async def handle_upload_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_module_choice:
        del user_module_choice[user_id]
    await message.answer(
        "📤 <b>Выберите модуль:</b>\n"
        "🌀 Initium • 🌐 Sphaerae • 📜 Akasha • 💭 Philosophia",
        reply_markup=get_modules_inline_keyboard()
    )
    await state.set_state(UploadStates.waiting_for_module_choice)

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
        "📚 <b>Mandala Sync Terminal v3.17</b>\n\n"
        "📤 Загрузить файл – модули в корень\n"
        "🍇 Fructus – артефакты в /fructus\n"
        "📦 Монолит – скачать сборку\n\n"
        "🌿 Ahimsa-фильтр: игнорирует код, ищет фразы насилия\n"
        "🔄 Пинг корневого URL – не даёт уснуть",
        reply_markup=get_main_keyboard()
    )

# ========== ОБРАБОТЧИКИ КОЛБЭКОВ ==========
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
        "• Initium\n• Sphaerae\n• Akasha\n• Philosophia\n\n"
        "Собирается автоматически при пуше",
        reply_markup=get_monolith_inline_keyboard()
    )
    await callback_query.answer()

@router.callback_query(F.data.startswith("module_"))
async def handle_module_selection(callback_query: CallbackQuery, state: FSMContext):
    module_map = {
        "module_initium": "initium",
        "module_sphaerae": "sphaerae",
        "module_akasha": "akasha",
        "module_philosophia": "philosophia"
    }
    module_name = module_map.get(callback_query.data)
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

    await state.set_state(UploadStates.waiting_for_file)
    await callback_query.message.edit_text(
        f"✅ Выбран: {module_display[module_name]}\n"
        f"Файл: <b>{CORE_FILES[module_name]}</b>\n\n"
        f"Отправьте JSON файл."
    )
    await callback_query.message.answer(
        "📎 Прикрепите JSON",
        reply_markup=get_upload_mode_keyboard()
    )
    await callback_query.answer()

@router.callback_query(F.data == "fructus_info")
async def handle_fructus_info(callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        "📋 <b>Fructus</b> – хранилище артефактов\n"
        "• Уникальные имена\n"
        "• Метаданные\n"
        "• Путь: /fructus/",
        reply_markup=get_fructus_inline_keyboard()
    )
    await callback_query.answer()

@router.callback_query(F.data == "fructus_upload")
async def handle_fructus_upload(callback_query: CallbackQuery, state: FSMContext):
    user_module_choice[callback_query.from_user.id] = "fructus"
    await state.set_state(UploadStates.waiting_for_file)
    await callback_query.message.edit_text("✅ Fructus: отправьте JSON файл")
    await callback_query.message.answer("📎 Прикрепите JSON", reply_markup=get_upload_mode_keyboard())
    await callback_query.answer()

@router.callback_query(F.data == "cancel")
async def handle_cancel_inline(callback_query: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback_query.from_user.id
    if user_id in user_module_choice:
        del user_module_choice[user_id]
    await callback_query.message.edit_text("🚫 Отменено")
    await callback_query.answer()
    await callback_query.message.answer("🏠 Главное меню", reply_markup=get_main_keyboard())

# ========== ОБРАБОТКА ФАЙЛОВ ==========
@router.message(StateFilter(UploadStates.waiting_for_file))
async def process_file_upload(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in user_module_choice:
        await message.answer("⚠️ Сначала выберите модуль", reply_markup=get_modules_inline_keyboard())
        return

    module_name = user_module_choice[user_id]
    if not message.document:
        await message.answer("⚠️ Отправьте JSON файл", reply_markup=get_upload_mode_keyboard())
        return

    if not message.document.file_name.lower().endswith('.json'):
        await message.answer("⚠️ Только .json", reply_markup=get_upload_mode_keyboard())
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
            issues = "\n".join([f"• {c}: {d}" for c, d in ahimsa_issues])
            await message.answer(f"🔶 {ahimsa_message}\n\n{issues}", reply_markup=get_upload_mode_keyboard())
            return

        await message.answer(f"✅ {ahimsa_message}")

        if module_name == "fructus":
            success, result = await upload_to_fructus(message.document.file_name, json_content, user_id)
            if success:
                await message.answer(f"✅ Артефакт сохранён: fructus/{result}", reply_markup=get_main_keyboard())
            else:
                await message.answer(f"🔶 Ошибка: {result}", reply_markup=get_main_keyboard())
        else:
            target = CORE_FILES.get(module_name)
            if not target:
                await message.answer("⚠️ Модуль не найден", reply_markup=get_main_keyboard())
                await state.clear()
                return

            success = await update_github_file(
                target, json_content,
                f"Обновление {target} через бот v3.17"
            )
            if success:
                await message.answer(f"✅ {module_name.upper()} обновлён", reply_markup=get_main_keyboard())
            else:
                await message.answer("🔶 Ошибка загрузки", reply_markup=get_main_keyboard())

        await state.clear()
        if user_id in user_module_choice:
            del user_module_choice[user_id]

    except json.JSONDecodeError:
        await message.answer("⚠️ Невалидный JSON", reply_markup=get_upload_mode_keyboard())
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.answer(f"🔶 Ошибка: {str(e)[:100]}", reply_markup=get_main_keyboard())
        await state.clear()

@router.message(F.text == "🔄 Сменить модуль")
async def handle_change_module(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in user_module_choice:
        del user_module_choice[user_id]
    await state.set_state(UploadStates.waiting_for_module_choice)
    await message.answer("🔄 Выберите модуль:", reply_markup=get_modules_inline_keyboard())

@router.message()
async def handle_other_messages(message: Message, state: FSMContext):
    current = await state.get_state()
    if current == UploadStates.waiting_for_file:
        await message.answer("📎 Ожидаю JSON файл", reply_markup=get_upload_mode_keyboard())
    elif current == UploadStates.waiting_for_module_choice:
        await message.answer("🔘 Выберите модуль кнопками", reply_markup=get_modules_inline_keyboard())
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
    # ⚡ НЕ удаляем вебхук! Render убивает процесс, а Telegram должен оставаться настроенным
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
        return web.Response(text="Mandala Bot is running")
    app.router.add_get("/", index)

    setup_application(app, dp, bot=bot)
    
    logger.info(f"🚀 Запуск сервера на порту {PORT}")
    # ⚡ Порт фиксирован 10000 — Render не перезапускает
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    main()
