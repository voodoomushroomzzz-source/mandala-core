# ========== ДОБАВИТЬ В НАЧАЛО ФАЙЛА ==========

# Конфигурация Kortix API
KORTIX_API_URL = os.getenv("KORTIX_API_URL", "http://localhost:8080")  # URL сервера Kortix
KORTIX_API_TIMEOUT = 30  # таймаут в секундах

# Добавить новые состояния для FSM
class UploadStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_module = State()
    waiting_for_file = State()
    # ДОБАВИТЬ:
    waiting_for_kortix_confirm = State()  # подтверждение отправки в API
    waiting_for_kortix_status = State()   # проверка статуса

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С KORTIX API ==========

async def send_to_kortix_api(instruction: Dict) -> Tuple[bool, Dict, str]:
    """
    Отправляет инструкцию напрямую в Kortix API
    """
    if not KORTIX_API_URL:
        return False, {}, "KORTIX_API_URL не настроен"
    
    try:
        async with aiohttp.ClientSession() as session:
            # Сначала проверяем, жив ли API
            try:
                async with session.get(f"{KORTIX_API_URL}/health", timeout=5) as health_response:
                    if health_response.status != 200:
                        return False, {}, f"Kortix API недоступен (health check: {health_response.status})"
            except Exception as e:
                return False, {}, f"Kortix API не отвечает: {str(e)}"
            
            # Отправляем инструкцию
            async with session.post(
                f"{KORTIX_API_URL}/execute",
                json=instruction,
                timeout=KORTIX_API_TIMEOUT
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return True, result, "✅ Инструкция отправлена в Kortix"
                else:
                    error_text = await response.text()
                    return False, {}, f"Ошибка API (HTTP {response.status}): {error_text[:200]}"
                    
    except asyncio.TimeoutError:
        return False, {}, f"Таймаут при обращении к Kortix API ({KORTIX_API_TIMEOUT} сек)"
    except Exception as e:
        return False, {}, f"Ошибка при вызове Kortix API: {str(e)}"


async def get_kortix_status(update_id: str) -> Tuple[bool, Dict, str]:
    """
    Проверяет статус выполнения инструкции по update_id
    (если API поддерживает такой эндпоинт)
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{KORTIX_API_URL}/status/{update_id}",
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return True, result, "Статус получен"
                else:
                    return False, {}, f"Ошибка {response.status}"
    except Exception as e:
        return False, {}, str(e)


# ========== НОВЫЕ КОМАНДЫ ДЛЯ БОТА ==========

@router.message(Command("kortix_status"))
async def cmd_kortix_status(message: Message):
    """Проверка статуса Kortix API"""
    await message.answer("🔄 Проверяю подключение к Kortix API...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{KORTIX_API_URL}/health", timeout=5) as response:
                if response.status == 200:
                    await message.answer(
                        "✅ Kortix API доступен\n"
                        f"URL: {KORTIX_API_URL}",
                        reply_markup=get_main_keyboard()
                    )
                else:
                    await message.answer(
                        f"⚠️ Kortix API ответил с ошибкой: {response.status}",
                        reply_markup=get_main_keyboard()
                    )
    except Exception as e:
        await message.answer(
            f"❌ Kortix API недоступен\n"
            f"URL: {KORTIX_API_URL}\n"
            f"Ошибка: {str(e)}\n\n"
            f"Проверьте:\n"
            f"• Запущен ли Kortix API\n"
            f"• Правильный ли URL в переменной KORTIX_API_URL",
            reply_markup=get_main_keyboard()
        )


# ========== ОБНОВИТЬ ОБРАБОТЧИК KORTIX ==========

async def handle_kortix_upload_file(message: Message, state: FSMContext, user_id: int):
    """
    ОБНОВЛЁННЫЙ обработчик: теперь спрашивает, отправлять ли сразу в API
    """
    try:
        if not message.document:
            await message.answer("⚠️ Отправьте JSON файл", reply_markup=get_upload_mode_keyboard())
            return
        
        if not message.document.file_name.lower().endswith('.json'):
            await message.answer("⚠️ Инструкция должна быть в формате JSON", 
                               reply_markup=get_upload_mode_keyboard())
            return
        
        await message.answer("📥 Скачиваю инструкцию...")
        
        file = await bot.get_file(message.document.file_id)
        file_content_bytes = await bot.download_file(file.file_path)
        file_content = file_content_bytes.read().decode('utf-8')
        
        try:
            json_content = json.loads(file_content)
        except json.JSONDecodeError as e:
            await message.answer(f"⚠️ Невалидный JSON: {str(e)[:200]}",
                               reply_markup=get_upload_mode_keyboard())
            return
        
        # Валидация
        await message.answer("🔍 Проверка схемы инструкции...")
        is_valid, validation_message = validate_kortix_instruction(json_content)
        
        if not is_valid:
            await message.answer(f"❌ {validation_message}",
                               reply_markup=get_upload_mode_keyboard())
            return
        
        await message.answer(f"✅ {validation_message}")
        
        # Ahimsa проверка
        await message.answer("🌿 Ahimsa проверка...")
        ahimsa_ok, ahimsa_message, _ = await check_ahimsa_smart(json_content, "kortix_instruction.json")
        
        if not ahimsa_ok:
            await message.answer(f"🔶 {ahimsa_message}", 
                               reply_markup=get_upload_mode_keyboard())
            return
        
        # Сохраняем инструкцию в контекст FSM для дальнейшего использования
        await state.update_data(
            kortix_instruction=json_content,
            kortix_filename=message.document.file_name
        )
        
        # СПРАШИВАЕМ, ЧТО ДЕЛАТЬ
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🚀 Отправить в Kortix API", callback_data="kortix_send_api"),
                InlineKeyboardButton(text="📁 Только в GitHub", callback_data="kortix_save_only")
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
        ])
        
        await message.answer(
            "🤔 Куда отправить инструкцию?\n\n"
            "🚀 **Kortix API** — немедленное выполнение (если API запущен)\n"
            "📁 **Только GitHub** — сохранение в updates/current_instruction.json (для GitHub Actions)",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        await state.set_state(UploadStates.waiting_for_kortix_confirm)
        
    except Exception as e:
        logger.error(f"Ошибка при обработке Kortix инструкции: {e}", exc_info=True)
        await message.answer(f"🔶 Ошибка: {str(e)[:200]}", 
                           reply_markup=get_upload_mode_keyboard())


@router.callback_query(F.data == "kortix_send_api", StateFilter(UploadStates.waiting_for_kortix_confirm))
async def handle_kortix_send_api(callback_query: CallbackQuery, state: FSMContext):
    """Отправка инструкции напрямую в Kortix API"""
    await callback_query.message.edit_text("🚀 Отправляю инструкцию в Kortix API...")
    
    # Получаем сохранённую инструкцию
    data = await state.get_data()
    instruction = data.get("kortix_instruction")
    
    if not instruction:
        await callback_query.message.edit_text("❌ Инструкция не найдена. Начните заново.")
        await state.clear()
        return
    
    # Отправляем в API
    success, result, message_text = await send_to_kortix_api(instruction)
    
    if success:
        # Формируем красивый ответ
        response_text = f"✅ {message_text}\n\n"
        response_text += f"🆔 Update ID: `{result.get('update_id', 'N/A')}`\n"
        response_text += f"🌿 Branch: `{result.get('branch', 'N/A')}`\n"
        
        if result.get('pr'):
            response_text += f"🔗 Pull Request: {result['pr']}\n"
        
        # Дополнительная информация если есть
        if result.get('commit_hash'):
            response_text += f"📦 Commit: `{result['commit_hash'][:7]}`\n"
        
        await callback_query.message.edit_text(
            response_text,
            reply_markup=get_main_keyboard(),
            disable_web_page_preview=True,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await callback_query.message.edit_text(
            f"❌ {message_text}\n\n"
            f"Попробуйте сохранить в GitHub (будет запущен GitHub Actions)",
            reply_markup=get_main_keyboard()
        )
    
    await state.clear()


@router.callback_query(F.data == "kortix_save_only", StateFilter(UploadStates.waiting_for_kortix_confirm))
async def handle_kortix_save_only(callback_query: CallbackQuery, state: FSMContext):
    """Сохранение инструкции только в GitHub (как было раньше)"""
    await callback_query.message.edit_text("📁 Сохраняю инструкцию в GitHub...")
    
    data = await state.get_data()
    instruction = data.get("kortix_instruction")
    
    if not instruction:
        await callback_query.message.edit_text("❌ Инструкция не найдена. Начните заново.")
        await state.clear()
        return
    
    # Сохраняем в GitHub
    target_path = "updates/current_instruction.json"
    success = await update_github_file(
        file_path=target_path,
        content=instruction,
        message=f"📥 Kortix инструкция: {data.get('kortix_filename', 'update')}"
    )
    
    if success:
        file_url = f"https://github.com/{REPO_NAME}/blob/main/{target_path}"
        await callback_query.message.edit_text(
            f"✅ Инструкция сохранена как `{target_path}`\n\n"
            f"🔗 <a href='{file_url}'>Посмотреть на GitHub</a>\n\n"
            f"🚀 GitHub Actions автоматически запустится.",
            reply_markup=get_main_keyboard(),
            disable_web_page_preview=True,
            parse_mode=ParseMode.HTML
        )
    else:
        await callback_query.message.edit_text(
            "❌ Не удалось сохранить в GitHub",
            reply_markup=get_main_keyboard()
        )
    
    await state.clear()


# ========== ОБНОВИТЬ КЛАВИАТУРУ KORTIX ==========

def get_kortix_keyboard() -> InlineKeyboardMarkup:
    """Обновлённая клавиатура с кнопкой статуса"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Загрузить инструкцию", callback_data="target_kortix_update")],
        [InlineKeyboardButton(text="📋 О Kortix", callback_data="kortix_info")],
        [InlineKeyboardButton(text="🔌 Статус API", callback_data="kortix_api_status")],  # НОВАЯ КНОПКА
        [InlineKeyboardButton(text="◀️ Назад к категориям", callback_data="back_to_categories")]
    ])


@router.callback_query(F.data == "kortix_api_status")
async def handle_kortix_api_status(callback_query: CallbackQuery):
    """Проверка статуса Kortix API"""
    await callback_query.message.edit_text("🔄 Проверяю Kortix API...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{KORTIX_API_URL}/health", timeout=5) as response:
                if response.status == 200:
                    # Пробуем получить дополнительную информацию
                    info_text = "✅ Kortix API доступен\n\n"
                    info_text += f"URL: `{KORTIX_API_URL}`\n"
                    
                    # Можно добавить кнопку для быстрой отправки тестовой инструкции
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📤 Загрузить инструкцию", callback_data="target_kortix_update")],
                        [InlineKeyboardButton(text="◀️ Назад", callback_data="kortix_info")]
                    ])
                    
                    await callback_query.message.edit_text(
                        info_text,
                        reply_markup=keyboard
                    )
                else:
                    await callback_query.message.edit_text(
                        f"⚠️ Kortix API ответил с ошибкой: HTTP {response.status}",
                        reply_markup=get_kortix_keyboard()
                    )
    except Exception as e:
        await callback_query.message.edit_text(
            f"❌ Kortix API недоступен\n\n"
            f"Ошибка: {str(e)}\n\n"
            f"Убедитесь, что Kortix API запущен на `{KORTIX_API_URL}`",
            reply_markup=get_kortix_keyboard()
        )
    
    await callback_query.answer()
