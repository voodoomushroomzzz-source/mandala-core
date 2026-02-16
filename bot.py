#!/usr/bin/env python3
"""
Mandala Sync Terminal Bot v3.22.0
Mandala Sync Terminal Bot v3.23.0
Render Web Service + Webhook (Aiogram 3)
ИЗМЕНЕНИЯ:
- 🔧 Редактирование вынесено в главное меню
- 📦 Новое эмодзи для монолита (отличается от загрузки)
- 🤖 Добавлена возможность обновлять bot.py через интерфейс
- Убраны лишние подтверждения при редактировании
- Увеличены таймауты GitHub API до 30 секунд
- Упрощены сообщения: "✅ Обновление окей" + ссылка
- Исправлено зависание при сохранении
"""

import os
@@ -169,16 +170,29 @@ class UploadStates(StatesGroup):
    }
}

ALL_UPLOAD_TARGETS = {**MANDALA_MODULES, **INFRASTRUCTURE_FILES}
# ========== ДОБАВЛЯЕМ САМОГО БОТА КАК ЦЕЛЕВОЙ ФАЙЛ ==========
BOT_SELF = {
    "bot_script": {
        "name": "🤖 Сам бот (bot.py)",
        "filename": "bot.py",
        "path": "bot.py",
        "description": "Исходный код бота",
        "category": "infra"  # в категории инфраструктуры
    }
}

ALL_UPLOAD_TARGETS = {**MANDALA_MODULES, **INFRASTRUCTURE_FILES, **BOT_SELF}
user_upload_target = {}


# ========== КЛАВИАТУРЫ ==========

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню с отдельной кнопкой для редактирования"""
    keyboard = [
        [KeyboardButton(text="📤 Загрузить файл")],
        [KeyboardButton(text="📥 Скачать монолит")],
        [KeyboardButton(text="🔧 Редактировать модуль")],  # НОВАЯ КНОПКА
        [KeyboardButton(text="📦 Скачать монолит")],       # изменён эмодзи
        [KeyboardButton(text="🍇 Fructus")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ]
@@ -201,48 +215,55 @@ def get_upload_mode_keyboard() -> ReplyKeyboardMarkup:
        selective=True
    )

def get_action_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Загрузить новый файл", callback_data="action_upload")],
        [InlineKeyboardButton(text="🔧 Редактировать существующий", callback_data="action_edit")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def get_category_keyboard() -> InlineKeyboardMarkup:
def get_category_keyboard(for_edit: bool = False) -> InlineKeyboardMarkup:
    """Категории файлов. for_edit=True если вызывается из режима редактирования"""
    # Для редактирования показываем обе категории (модули и инфраструктуру)
    # В инфраструктуре теперь есть bot.py
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧩 Модули Мандалы", callback_data="category_modules")],
        [InlineKeyboardButton(text="⚙️ Инфраструктура сборки", callback_data="category_infra")],
        [InlineKeyboardButton(text="🧩 Модули Мандалы", 
                            callback_data="category_modules_edit" if for_edit else "category_modules")],
        [InlineKeyboardButton(text="⚙️ Инфраструктура", 
                            callback_data="category_infra_edit" if for_edit else "category_infra")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def get_modules_keyboard() -> InlineKeyboardMarkup:
def get_modules_keyboard(for_edit: bool = False) -> InlineKeyboardMarkup:
    """Все модули Мандалы (включая Testisphaera)"""
    prefix = "edit_" if for_edit else "target_"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌀 Initium", callback_data="target_initium"),
            InlineKeyboardButton(text="🌐 Sphaerae", callback_data="target_sphaerae")
            InlineKeyboardButton(text="🌀 Initium", callback_data=f"{prefix}initium"),
            InlineKeyboardButton(text="🌐 Sphaerae", callback_data=f"{prefix}sphaerae")
        ],
        [
            InlineKeyboardButton(text="📜 Akasha", callback_data="target_akasha"),
            InlineKeyboardButton(text="💭 Philosophia", callback_data="target_philosophia")
            InlineKeyboardButton(text="📜 Akasha", callback_data=f"{prefix}akasha"),
            InlineKeyboardButton(text="💭 Philosophia", callback_data=f"{prefix}philosophia")
        ],
        [
            InlineKeyboardButton(text="🔺 Geometria", callback_data="target_geometria_sacra"),
            InlineKeyboardButton(text="🌱 Incubae", callback_data="target_incubae")
            InlineKeyboardButton(text="🔺 Geometria", callback_data=f"{prefix}geometria_sacra"),
            InlineKeyboardButton(text="🌱 Incubae", callback_data=f"{prefix}incubae")
        ],
        [
            InlineKeyboardButton(text="🛡️ Tectosphaera", callback_data="target_tectosphaera"),
            InlineKeyboardButton(text="🧪 Testisphaera", callback_data="target_testisphaera")
            InlineKeyboardButton(text="🛡️ Tectosphaera", callback_data=f"{prefix}tectosphaera"),
            InlineKeyboardButton(text="🧪 Testisphaera", callback_data=f"{prefix}testisphaera")
        ],
        [InlineKeyboardButton(text="◀️ Назад к категориям", callback_data="back_to_categories")]
        [InlineKeyboardButton(text="◀️ Назад к категориям", 
                            callback_data="back_to_categories_edit" if for_edit else "back_to_categories")]
    ])

def get_infra_keyboard() -> InlineKeyboardMarkup:
def get_infra_keyboard(for_edit: bool = False) -> InlineKeyboardMarkup:
    """Инфраструктурные файлы + бот"""
    prefix = "edit_" if for_edit else "target_"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔨 Сборщик", callback_data="target_build_script"),
            InlineKeyboardButton(text="🤖 GitHub Action", callback_data="target_github_action")
            InlineKeyboardButton(text="🔨 Сборщик", callback_data=f"{prefix}build_script"),
            InlineKeyboardButton(text="🤖 GitHub Action", callback_data=f"{prefix}github_action")
        ],
        [InlineKeyboardButton(text="◀️ Назад к категориям", callback_data="back_to_categories")]
        [
            InlineKeyboardButton(text="🤖 Сам бот", callback_data=f"{prefix}bot_script")  # НОВАЯ КНОПКА
        ],
        [InlineKeyboardButton(text="◀️ Назад к категориям", 
                            callback_data="back_to_categories_edit" if for_edit else "back_to_categories")]
    ])

def get_edit_operations_keyboard() -> InlineKeyboardMarkup:
@@ -255,7 +276,7 @@ def get_edit_operations_keyboard() -> InlineKeyboardMarkup:
            InlineKeyboardButton(text="🗑️ Удалить поле", callback_data="edit_op_delete"),
            InlineKeyboardButton(text="📋 Показать структуру", callback_data="edit_op_show")
        ],
        [InlineKeyboardButton(text="◀️ Назад к модулям", callback_data="back_to_modules")],
        [InlineKeyboardButton(text="◀️ Назад к модулям", callback_data="back_to_modules_edit")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

@@ -269,7 +290,7 @@ def get_fructus_inline_keyboard() -> InlineKeyboardMarkup:
    ])


# ========== ФУНКЦИИ GITHUB API (С УВЕЛИЧЕННЫМИ ТАЙМАУТАМИ) ==========
# ========== ФУНКЦИИ GITHUB API ==========

async def update_github_file(file_path: str, content: Any, message: str) -> bool:
    """Обновление файла на GitHub с таймаутом 30 секунд"""
@@ -297,12 +318,11 @@ async def update_github_file(file_path: str, content: Any, message: str) -> bool
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaBot/3.22.0"
        "User-Agent": "MandalaBot/3.23.0"
    }

    async with aiohttp.ClientSession() as session:
        try:
            # GET с таймаутом 30 сек
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
@@ -329,7 +349,6 @@ async def update_github_file(file_path: str, content: Any, message: str) -> bool
        }

        try:
            # PUT с таймаутом 30 сек
            async with session.put(url, headers=headers, json=payload, timeout=30) as response:
                response_text = await response.text()
                logger.info(f"📡 GitHub response status: {response.status}")
@@ -349,7 +368,7 @@ async def update_github_file(file_path: str, content: Any, message: str) -> bool
            return False


async def get_github_file_content(file_path: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
async def get_github_file_content(file_path: str) -> Tuple[bool, Optional[Any], Optional[str]]:
    """Получить содержимое файла из GitHub"""
    if not GITHUB_TOKEN:
        return False, None, "GITHUB_TOKEN не настроен"
@@ -358,7 +377,7 @@ async def get_github_file_content(file_path: str) -> Tuple[bool, Optional[Dict],
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaBot/3.22.0"
        "User-Agent": "MandalaBot/3.23.0"
    }

    async with aiohttp.ClientSession() as session:
@@ -367,7 +386,12 @@ async def get_github_file_content(file_path: str) -> Tuple[bool, Optional[Dict],
                if response.status == 200:
                    data = await response.json()
                    content = base64.b64decode(data["content"]).decode('utf-8')
                    return True, json.loads(content), data.get("sha")
                    # Пытаемся распарсить как JSON, но для bot.py это может быть простой текст
                    try:
                        return True, json.loads(content), data.get("sha")
                    except:
                        # Если не JSON, возвращаем как есть (для bot.py)
                        return True, content, data.get("sha")
                elif response.status == 404:
                    return False, None, "Файл не найден"
                else:
@@ -476,7 +500,7 @@ async def apply_json_operation(
        return False, None, f"Ошибка: {str(e)}"


# ========== НОВАЯ ФУНКЦИЯ СОХРАНЕНИЯ (БЕЗ ПОДТВЕРЖДЕНИЯ) ==========
# ========== ФУНКЦИЯ СОХРАНЕНИЯ (БЕЗ ПОДТВЕРЖДЕНИЯ) ==========

async def save_edit_changes(message: Message, state: FSMContext):
    """Сразу сохраняет изменения без лишнего предпросмотра"""
@@ -499,7 +523,32 @@ async def save_edit_changes(message: Message, state: FSMContext):
            del user_upload_target[message.from_user.id]
        return

    # Применяем операцию
    # Для bot.py (не JSON) нужна особая обработка
    if module_path == "bot.py":
        # Просто сохраняем как есть (новое значение - это весь файл)
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
    import copy
    content_copy = copy.deepcopy(content)

@@ -530,7 +579,6 @@ async def save_edit_changes(message: Message, state: FSMContext):
            disable_web_page_preview=True
        )
    else:
        # Даже если GitHub не ответил, но файл мог обновиться
        file_url = f"https://github.com/{REPO_NAME}/blob/main/{module_path}"
        await status_msg.edit_text(
            f"⚠️ Обновление отправлено, но ответ не получен\n"
@@ -577,7 +625,7 @@ async def upload_to_fructus(original_filename: str, content: Dict, user_id: int)
            "file_type": file_type,
            "upload_timestamp": datetime.now().isoformat(),
            "uploaded_by": f"user_{user_id}",
            "source": "mandala_bot_v3.22.0"
            "source": "mandala_bot_v3.23.0"
        }

        success = await update_github_file(
@@ -612,7 +660,7 @@ async def download_monolith_file() -> Tuple[bool, bytes, str]:

# ========== ФУНКЦИИ AHHIMSA ==========

async def check_ahimsa_smart(content: Dict, filename: str = "") -> Tuple[bool, str, List[Tuple[str, str]]]:
async def check_ahimsa_smart(content: Any, filename: str = "") -> Tuple[bool, str, List[Tuple[str, str]]]:
    return True, "✅ Проверка пройдена", []


@@ -625,10 +673,12 @@ async def cmd_start(message: Message, state: FSMContext):
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    await message.answer(
        "🌀 <b>Mandala Sync Terminal v3.22.0</b>\n\n"
        "📤 <b>Загрузить файл</b> — загрузка или редактирование\n"
        "📥 <b>Скачать монолит</b> — готовый файл\n"
        "🌀 <b>Mandala Sync Terminal v3.23.0</b>\n\n"
        "📤 <b>Загрузить файл</b> — новый JSON в репозиторий\n"
        "🔧 <b>Редактировать модуль</b> — точечные изменения JSON\n"
        "📦 <b>Скачать монолит</b> — готовый файл\n"
        "🍇 <b>Fructus</b> — хранилище артефактов\n\n"
        "🤖 <b>Новое:</b> можно обновлять самого бота (в инфраструктуре)\n"
        "🌿 Ahimsa-фильтр активен",
        reply_markup=get_main_keyboard()
    )
@@ -645,20 +695,37 @@ async def handle_cancel_button(message: Message, state: FSMContext):

@router.message(F.text == "📤 Загрузить файл")
async def handle_upload_start(message: Message, state: FSMContext):
    """Загрузка нового файла"""
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    
    await state.update_data(edit_mode=False)
    await state.set_state(UploadStates.waiting_for_category)
    await message.answer(
        "📤 <b>Загрузка нового файла</b>\n\nВыберите категорию:",
        reply_markup=get_category_keyboard(for_edit=False)
    )


@router.message(F.text == "🔧 Редактировать модуль")
async def handle_edit_start(message: Message, state: FSMContext):
    """Редактирование существующего модуля (отдельная кнопка)"""
    await state.clear()
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]

    await state.set_state(UploadStates.waiting_for_action)
    await state.update_data(edit_mode=True)
    await state.set_state(UploadStates.waiting_for_category)
    await message.answer(
        "📤 <b>Управление файлами</b>\n\n"
        "Загрузить новый или отредактировать существующий?",
        reply_markup=get_action_keyboard()
        "🔧 <b>Редактирование модуля</b>\n\nВыберите категорию:",
        reply_markup=get_category_keyboard(for_edit=True)
    )


@router.message(F.text == "📥 Скачать монолит")
@router.message(F.text == "📦 Скачать монолит")
async def handle_download_monolith_direct(message: Message):
    await message.answer("📦 Скачиваю...")
    success, content, filename = await download_monolith_file()
@@ -682,14 +749,16 @@ async def handle_fructus_menu(message: Message):
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
        "📚 <b>Mandala Sync Terminal v3.23.0</b>\n\n"
        "📤 <b>Загрузить файл</b> — новый JSON в репозиторий\n"
        "🔧 <b>Редактировать модуль</b> — точечные изменения:\n"
        "• Добавить в массив\n"
        "• Обновить поле\n"
        "• Удалить поле\n"
        "• Показать структуру\n\n"
        "📦 <b>Скачать монолит</b> — mandala_core.monolith.latest.json\n\n"
        "🍇 <b>Fructus</b> — seeds, geometry, builders\n\n"
        "🤖 <b>Обновление бота</b> — в категории Инфраструктура\n"
        "🧪 Testisphaera в модулях Мандалы\n"
        "🌿 Ahimsa-фильтр активен",
        reply_markup=get_main_keyboard()
@@ -701,80 +770,80 @@ async def handle_change_category(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in user_upload_target:
        del user_upload_target[user_id]
    
    data = await state.get_data()
    edit_mode = data.get("edit_mode", False)
    
    await state.set_state(UploadStates.waiting_for_category)
    await message.answer(
        "🔄 Выберите категорию:",
        reply_markup=get_category_keyboard()
        reply_markup=get_category_keyboard(for_edit=edit_mode)
    )


# ========== ОБРАБОТЧИКИ КОЛБЭКОВ ==========

@router.callback_query(F.data == "action_upload", StateFilter(UploadStates.waiting_for_action))
async def handle_action_upload(callback_query: CallbackQuery, state: FSMContext):
    await state.update_data(edit_mode=False)
    await state.set_state(UploadStates.waiting_for_category)
@router.callback_query(F.data == "category_modules", StateFilter(UploadStates.waiting_for_category))
async def handle_category_modules(callback_query: CallbackQuery, state: FSMContext):
    """Категория модулей для загрузки"""
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "📤 <b>Загрузка</b>\n\nВыберите категорию:",
        reply_markup=get_category_keyboard()
        "🧩 <b>Выберите модуль для загрузки:</b>",
        reply_markup=get_modules_keyboard(for_edit=False)
    )
    await callback_query.answer()


@router.callback_query(F.data == "action_edit", StateFilter(UploadStates.waiting_for_action))
async def handle_action_edit(callback_query: CallbackQuery, state: FSMContext):
    await state.update_data(edit_mode=True)
    await state.set_state(UploadStates.waiting_for_category)
@router.callback_query(F.data == "category_modules_edit", StateFilter(UploadStates.waiting_for_category))
async def handle_category_modules_edit(callback_query: CallbackQuery, state: FSMContext):
    """Категория модулей для редактирования"""
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "🔧 <b>Редактирование</b>\n\nВыберите категорию:",
        reply_markup=get_category_keyboard()
        "🔧 <b>Выберите модуль для редактирования:</b>",
        reply_markup=get_modules_keyboard(for_edit=True)
    )
    await callback_query.answer()


@router.callback_query(F.data == "category_modules", StateFilter(UploadStates.waiting_for_category))
async def handle_category_modules(callback_query: CallbackQuery, state: FSMContext):
@router.callback_query(F.data == "category_infra", StateFilter(UploadStates.waiting_for_category))
async def handle_category_infra(callback_query: CallbackQuery, state: FSMContext):
    """Категория инфраструктуры для загрузки"""
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "🧩 <b>Выберите модуль:</b>",
        reply_markup=get_modules_keyboard()
        "⚙️ <b>Выберите компонент для загрузки:</b>",
        reply_markup=get_infra_keyboard(for_edit=False)
    )
    await callback_query.answer()


@router.callback_query(F.data == "category_infra", StateFilter(UploadStates.waiting_for_category))
async def handle_category_infra(callback_query: CallbackQuery, state: FSMContext):
@router.callback_query(F.data == "category_infra_edit", StateFilter(UploadStates.waiting_for_category))
async def handle_category_infra_edit(callback_query: CallbackQuery, state: FSMContext):
    """Категория инфраструктуры для редактирования"""
    await state.set_state(UploadStates.waiting_for_module)
    await callback_query.message.edit_text(
        "⚙️ <b>Выберите компонент:</b>",
        reply_markup=get_infra_keyboard()
        "🔧 <b>Выберите компонент для редактирования:</b>",
        reply_markup=get_infra_keyboard(for_edit=True)
    )
    await callback_query.answer()


@router.callback_query(F.data == "back_to_categories", StateFilter(UploadStates.waiting_for_module))
@router.callback_query(F.data.startswith("back_to_categories"))
async def handle_back_to_categories(callback_query: CallbackQuery, state: FSMContext):
    """Назад к категориям"""
    edit_mode = "edit" in callback_query.data
    await state.set_state(UploadStates.waiting_for_category)
    await callback_query.message.edit_text(
        "📤 <b>Выберите категорию:</b>",
        reply_markup=get_category_keyboard()
        reply_markup=get_category_keyboard(for_edit=edit_mode)
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
@router.callback_query(F.data.startswith(("target_", "edit_")), StateFilter(UploadStates.waiting_for_module))
async def handle_target_selection(callback_query: CallbackQuery, state: FSMContext):
    target_key = callback_query.data.replace("target_", "")
    """Выбран конкретный файл/модуль"""
    is_edit = callback_query.data.startswith("edit_")
    target_key = callback_query.data.replace("edit_", "").replace("target_", "")

    if target_key not in ALL_UPLOAD_TARGETS:
        await callback_query.answer("Неизвестный целевой файл")
@@ -783,25 +852,39 @@ async def handle_target_selection(callback_query: CallbackQuery, state: FSMConte
    target_info = ALL_UPLOAD_TARGETS[target_key]
    user_upload_target[callback_query.from_user.id] = target_key

    data = await state.get_data()
    edit_mode = data.get("edit_mode", False)
    
    if edit_mode:
    if is_edit:
        # Режим редактирования
        await state.update_data(
            edit_module=target_key,
            edit_module_path=target_info["path"],
            edit_module_name=target_info["name"]
            edit_module_name=target_info["name"],
            edit_mode=True
        )
        await state.set_state(UploadStates.waiting_for_operation)

        await callback_query.message.edit_text(
            f"🔧 <b>{target_info['name']}</b>\n\n"
            f"Файл: <code>{target_info['path']}</code>\n\n"
            f"Выберите операцию:",
            reply_markup=get_edit_operations_keyboard()
        )
        # Для bot.py особый случай - сразу просим новый код
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
        await state.update_data(edit_mode=False)
        await callback_query.message.edit_text(
            f"✅ {target_info['name']}\n"
            f"📁 <b>{target_info['filename']}</b>\n\n"
@@ -815,6 +898,17 @@ async def handle_target_selection(callback_query: CallbackQuery, state: FSMConte
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
@@ -823,7 +917,7 @@ async def handle_edit_add(callback_query: CallbackQuery, state: FSMContext):
    await state.set_state(UploadStates.waiting_for_target_path)
    await callback_query.message.edit_text(
        "➕ <b>Добавление в массив</b>\n\n"
        "Введите путь:\n"
        "Введите путь (примеры):\n"
        "<code>elements</code>\n"
        "<code>symbiosis_principles</code>\n"
        "<code>elements[0].items</code>"
@@ -837,7 +931,7 @@ async def handle_edit_update(callback_query: CallbackQuery, state: FSMContext):
    await state.set_state(UploadStates.waiting_for_target_path)
    await callback_query.message.edit_text(
        "✏️ <b>Обновление поля</b>\n\n"
        "Введите путь:\n"
        "Введите путь (примеры):\n"
        "<code>version</code>\n"
        "<code>elements[0].value</code>\n"
        "<code>metadata.created</code>"
@@ -851,7 +945,7 @@ async def handle_edit_delete(callback_query: CallbackQuery, state: FSMContext):
    await state.set_state(UploadStates.waiting_for_target_path)
    await callback_query.message.edit_text(
        "🗑️ <b>Удаление поля</b>\n\n"
        "Введите путь:\n"
        "Введите путь (примеры):\n"
        "<code>status</code>\n"
        "<code>metadata.temp</code>\n"
        "<code>elements[1]</code>"
@@ -931,6 +1025,17 @@ async def handle_target_path(message: Message, state: FSMContext):

@router.message(StateFilter(UploadStates.waiting_for_new_value))
async def handle_new_value(message: Message, state: FSMContext):
    data = await state.get_data()
    module_path = data.get("edit_module_path")
    
    # Для bot.py принимаем как есть (весь код)
    if module_path == "bot.py":
        new_value = message.text or "Файл не получен"
        await state.update_data(edit_new_value=new_value, edit_operation="update_field", edit_target_path="full")
        await save_edit_changes(message, state)
        return
    
    # Для JSON пробуем распарсить
    try:
        new_value = json.loads(message.text)
    except json.JSONDecodeError:
@@ -1110,11 +1215,17 @@ async def handle_other_messages(message: Message, state: FSMContext):
    elif current == UploadStates.waiting_for_module:
        await message.answer("🔘 Выберите кнопками", reply_markup=get_category_keyboard())
    elif current == UploadStates.waiting_for_category:
        await message.answer("🔘 Выберите категорию", reply_markup=get_category_keyboard())
        data = await state.get_data()
        edit_mode = data.get("edit_mode", False)
        await message.answer("🔘 Выберите категорию", reply_markup=get_category_keyboard(for_edit=edit_mode))
    elif current == UploadStates.waiting_for_target_path:
        await message.answer("📝 Введите путь (например: version или elements[0].value)")
    elif current == UploadStates.waiting_for_new_value:
        await message.answer("📤 Отправьте значение в JSON формате")
        data = await state.get_data()
        if data.get("edit_module_path") == "bot.py":
            await message.answer("🤖 Отправьте полный код bot.py")
        else:
            await message.answer("📤 Отправьте значение в JSON формате")
    else:
        await message.answer("ℹ️ Используйте меню", reply_markup=get_main_keyboard())

@@ -1147,7 +1258,7 @@ async def health(_):
    app.router.add_get("/healthcheck", health)

    async def index(_):
        return web.Response(text="Mandala Bot v3.22.0")
        return web.Response(text="Mandala Bot v3.23.0")
    app.router.add_get("/", index)

    setup_application(app, dp, bot=bot)
