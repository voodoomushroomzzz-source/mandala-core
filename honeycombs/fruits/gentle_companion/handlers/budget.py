# -*- coding: utf-8 -*-
"""
handlers/budget.py -- Budget tracking: income/expense entries, sphere-linked
categories, monthly report. Balance is always derived from entries
(store_get_balance), never stored separately -- avoids desync bugs.
"""

class BudgetStates(StatesGroup):
    waiting_for_input = State()


# --- Category schema: each category belongs to a "group" and optionally a sphere.
# Several category groups can map to the same sphere (per Sadovnik's design decision).
# Neutral categories (housing, savings, other) map to sphere=None -- they reflect
# survival/financial-safety spending, not a personal-growth choice.
CATEGORY_META = {
    "food":          {"name_ru": "Еда/продукты",         "emoji": "🍔", "sphere": "health"},
    "health_meds":   {"name_ru": "Здоровье и лекарства",  "emoji": "💊", "sphere": "health"},
    "sport_care":    {"name_ru": "Спорт и уход за собой", "emoji": "🧘", "sphere": "health"},
    "hobby":         {"name_ru": "Хобби и творчество",    "emoji": "🎨", "sphere": "creativity"},
    "creative_subs": {"name_ru": "Творческие подписки",   "emoji": "🖌️", "sphere": "creativity"},
    "work_tools":    {"name_ru": "Рабочие инструменты",   "emoji": "💻", "sphere": "work"},
    "transport":     {"name_ru": "Транспорт",             "emoji": "🚗", "sphere": "work"},
    "coworking":     {"name_ru": "Коворкинг/связь",       "emoji": "🏢", "sphere": "work"},
    "cafe_social":   {"name_ru": "Кафе с людьми",         "emoji": "☕", "sphere": "connections"},
    "gifts":         {"name_ru": "Подарки",               "emoji": "🎁", "sphere": "connections"},
    "travel":        {"name_ru": "Путешествия",           "emoji": "✈️", "sphere": "connections"},
    "education":     {"name_ru": "Образование",           "emoji": "📚", "sphere": "growth"},
    "books":         {"name_ru": "Книги",                 "emoji": "📖", "sphere": "growth"},
    "therapy":       {"name_ru": "Психотерапия/коучинг",  "emoji": "🧠", "sphere": "growth"},
    "housing":       {"name_ru": "Жильё и ЖКХ",           "emoji": "🏠", "sphere": None},
    "savings":       {"name_ru": "Сбережения",            "emoji": "💰", "sphere": None},
    "other":         {"name_ru": "Разное",                "emoji": "🔹", "sphere": None},
}

_CATEGORY_KEYWORDS = [
    ("food",          ["еда", "продукт", "магазин", "супермаркет", "обед", "ужин", "завтрак", "перекус", "пятерочка", "магнит"]),
    ("health_meds",   ["лекарств", "аптек", "врач", "стоматолог", "анализ", "больниц"]),
    ("sport_care",    ["спортзал", "фитнес", "тренировк", "йога", "парикмахер", "маникюр", "массаж"]),
    ("hobby",         ["хобби", "краски", "кисти", "рукодели", "инструмент музык", "гитара"]),
    ("creative_subs", ["adobe", "procreate", "figma"]),
    ("work_tools",    ["ноутбук", "монитор", "клавиатур", "лицензия", "программ"]),
    ("transport",     ["такси", "бензин", "метро", "автобус", "парковк", "каршеринг"]),
    ("coworking",     ["коворкинг", "интернет", "связь", "телефон"]),
    ("cafe_social",   ["кафе", "ресторан", "бар "]),
    ("gifts",         ["подарок", "подарк"]),
    ("travel",        ["путешестви", "отпуск", "авиабилет", "отель", "гостиниц"]),
    ("education",     ["курс", "обучени", "лекци", "вебинар"]),
    ("books",         ["книг"]),
    ("therapy",       ["психолог", "психотерап", "коуч"]),
    ("housing",       ["аренда", "квартир", "жкх", "коммунал", "ипотек"]),
    ("savings",       ["сбережени", "инвестици", "вклад"]),
]


def _classify_budget_category(text: str) -> str:
    """Keyword-based category classifier. First match wins. Falls back to 'other'."""
    t = text.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in t:
                return category
    return "other"


async def _create_budget_entry_atomic(user_id: str, amount: float, entry_type: str,
                                       category: str = None, note: str = "",
                                       currency: str = "RUB",
                                       is_recurring: bool = False,
                                       recurring_config: dict = None) -> dict:
    """Create a budget entry instantly from chat/voice or button flow. Returns created entry dict."""
    from datetime import datetime as _dt_bg
    if amount is None or amount <= 0:
        return {}
    if entry_type not in ("income", "expense"):
        return {}
    if not category or category not in CATEGORY_META:
        category = _classify_budget_category(note or "")
    profile = store_get_profile(user_id) or {}
    tz_name = profile.get("companion_settings", {}).get("timezone", "Europe/Moscow")
    entry_id = "budget_" + _dt_bg.now().strftime("%Y%m%d%H%M%S%f")[:17]
    new_entry = {
        "id":               entry_id,
        "date":             _today(tz_name),
        "amount":           amount,
        "type":             entry_type,
        "category":         category,
        "currency":         currency,
        "is_recurring":     is_recurring,
        "recurring_config": recurring_config,
        "note":             note.strip() if note else "",
    }
    store_add_budget_entry(user_id, new_entry)
    _fire_sync()
    return new_entry


def _format_budget_header(user_id: str) -> str:
    """Balance + last 5 entries, for the budget menu screen."""
    balance = store_get_balance(user_id)
    entries = store_get_budget_entries(user_id)
    recent = sorted(entries, key=lambda e: e.get("date", ""), reverse=True)[:5]
    lines = [f"💰 <b>Бюджет</b>", f"Баланс: {balance} ₽", ""]
    if recent:
        lines.append("Последние операции:")
        for e in recent:
            meta = CATEGORY_META.get(e.get("category", "other"), CATEGORY_META["other"])
            sign = "+" if e.get("type") == "income" else "-"
            entry_line = f"{sign}{e.get('amount', 0)} ₽ · {meta['emoji']} {meta['name_ru']}"
            if e.get("note"):
                entry_line += f" · {e['note']}"
            lines.append(entry_line)
    else:
        lines.append("Пока нет операций.")
    return "\n".join(lines)


def _budget_month_report(user_id: str) -> str:
    """Aggregate current-month entries: income, expense, balance, top-3 expense categories."""
    profile = store_get_profile(user_id) or {}
    tz_name = profile.get("companion_settings", {}).get("timezone", "Europe/Moscow")
    current_month = _today(tz_name)[:7]  # "YYYY-MM"
    entries = store_get_budget_entries(user_id)
    month_entries = [e for e in entries if e.get("date", "").startswith(current_month)]
    income = sum(e.get("amount", 0) for e in month_entries if e.get("type") == "income")
    expense = sum(e.get("amount", 0) for e in month_entries if e.get("type") == "expense")
    by_category = {}
    for e in month_entries:
        if e.get("type") != "expense":
            continue
        cat = e.get("category", "other")
        by_category[cat] = by_category.get(cat, 0) + e.get("amount", 0)
    top3 = sorted(by_category.items(), key=lambda x: -x[1])[:3]
    lines = [
        f"📊 <b>Отчёт за {current_month}</b>",
        f"Доходы: +{income} ₽",
        f"Расходы: -{expense} ₽",
        f"Баланс месяца: {income - expense} ₽",
    ]
    if top3:
        lines.append("")
        lines.append("Топ категорий трат:")
        for cat, amt in top3:
            meta = CATEGORY_META.get(cat, CATEGORY_META["other"])
            lines.append(f"{meta['emoji']} {meta['name_ru']}: {amt} ₽")
    return "\n".join(lines)


def get_budget_mgmt_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Доход", callback_data="budget_add_income"),
         InlineKeyboardButton(text="➖ Расход", callback_data="budget_add_expense")],
        [InlineKeyboardButton(text="📊 Отчёт", callback_data="budget_report")],
        [InlineKeyboardButton(text="← Назад", callback_data="profile_back")],
    ])


@router.callback_query(F.data == "menu_budget_mgmt")
async def cb_budget_mgmt(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    await state.clear()
    header = _format_budget_header(user_id)
    kb = get_budget_mgmt_inline()
    await _replace_menu(user_id, callback.message, header, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.in_(["budget_add_income", "budget_add_expense"]))
async def cb_budget_add(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    entry_type = "income" if callback.data == "budget_add_income" else "expense"
    await state.clear()
    await state.set_state(BudgetStates.waiting_for_input)
    await state.update_data(_budget_type=entry_type)
    label = "доход" if entry_type == "income" else "расход"
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_budget_mgmt")]
    ])
    try:
        await callback.message.edit_text(
            f"💰 <b>Новый {label}</b>\n\n"
            f"Напиши сумму и на что, например:\n<i>500 еда обед в кафе</i>",
            reply_markup=cancel_kb, parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            f"💰 <b>Новый {label}</b>\n\nНапиши сумму и на что:",
            reply_markup=cancel_kb, parse_mode="HTML"
        )


@router.message(StateFilter(BudgetStates.waiting_for_input))
async def budget_text_input(message: Message, state: FSMContext):
    import re as _re_bg
    user_id = str(message.from_user.id)
    data = await state.get_data()
    entry_type = data.get("_budget_type", "expense")
    text = message.text or ""
    match = _re_bg.search(r"(\d+(?:[.,]\d+)?)", text)
    if not match:
        await message.answer("Не нашёл сумму. Напиши число, например: 500 еда")
        return
    amount = float(match.group(1).replace(",", "."))
    rest_text = (text[:match.start()] + text[match.end():]).strip()
    category = _classify_budget_category(rest_text)
    entry = await _create_budget_entry_atomic(
        user_id, amount, entry_type, category=category, note=rest_text
    )
    if not entry:
        await message.answer("Не получилось сохранить операцию, попробуй ещё раз.")
        return
    await state.clear()
    balance = store_get_balance(user_id)
    meta = CATEGORY_META.get(category, CATEGORY_META["other"])
    sign = "+" if entry_type == "income" else "-"
    await message.answer(
        f"✅ {sign}{amount:g} ₽ · {meta['emoji']} {meta['name_ru']} → баланс: {balance} ₽",
        reply_markup=get_budget_mgmt_inline()
    )


@router.callback_query(F.data == "budget_report")
async def cb_budget_report(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    report = _budget_month_report(user_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="menu_budget_mgmt")]
    ])
    await _replace_menu(user_id, callback.message, report, reply_markup=kb, parse_mode="HTML")
