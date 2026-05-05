# patcher_21_hotfix.py
import sys

BOT_FILE = "bot.py"

def patch():
    with open(BOT_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove get_profile_inline function
    old = '''def get_profile_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить профиль", callback_data="menu_edit_profile")],
    ])'''
    
    if old in content:
        content = content.replace(old + '\n\n', '', 1)
        print("✅ Removed get_profile_inline function")

    # Fix cb_edit_profile_back — replace get_profile_inline() with dashboard
    old_back = '''async def cb_edit_profile_back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    card = _build_profile_card(user_id)
    try:
        await callback.message.edit_text(card, reply_markup=get_profile_inline(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(card, reply_markup=get_profile_inline(), parse_mode="HTML")'''

    new_back = '''async def cb_edit_profile_back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    data = _build_dashboard_data(user_id)
    text = _build_dashboard_main(data)
    kb = _build_dashboard_keyboard_main(data)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")'''

    if old_back in content:
        content = content.replace(old_back, new_back, 1)
        print("✅ Fixed cb_edit_profile_back → dashboard")
    else:
        print("⚠️ cb_edit_profile_back not found")

    with open(BOT_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    return True

if __name__ == "__main__":
    sys.exit(0 if patch() else 1)