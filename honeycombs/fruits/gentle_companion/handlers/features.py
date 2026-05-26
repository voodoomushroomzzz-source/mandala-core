# -*- coding: utf-8 -*-
"""
handlers/features.py — Checklists, Reminders, Achievements
Full FSM flows, repeat picker, atomic creation.

Part of: honeycombs/fruits/gentle_companion/
Phase: 6 (depends on config.py, store.py, helpers.py, ui.py)

Key handlers:
  Checklists: _show_checklist, _start_checklist_create,
              cb_cl_create_new, cl_title_input, cl_items_input,
              cb_cl_toggle, cb_cl_open, cb_cl_pin, cb_cl_delete,
              cb_cl_edit_menu, cb_cl_move_item, cb_cl_add_item_start,
              cb_cl_edititem_start, cb_cl_delitem, cb_checklists_mgmt
  Reminders:  cb_reminders_mgmt, cb_rem_create_new, cb_rem_delete,
              cb_rem_edit_start, rem_text_input,
              _repeat_picker_keyboard, cb_rem_repeat_pick, cb_rem_rp_select,
              cb_rem_day_toggle, cb_rem_rp_done, cb_rem_confirm_create,
              _create_reminder_atomic
  Achievements: cmd_achievements, cb_add_achievement, ach_category, ach_title
"""

async def _show_checklist(cl: dict, message: Message, edit: bool = False):
    """Show a single checklist as inline message. Deletes previous checklist message."""
    user_id = str(message.from_user.id)
    prog    = _checklist_progress(cl)
    title   = cl.get("title", "Чеклист")
    header  = f"☑️ <b>{title}</b>  {prog}"
    kb      = get_checklist_inline(cl)
    # Delete previous checklist message to keep chat clean
    prev_mid = _checklist_messages.get(user_id)
    if prev_mid:
        try:
            await message.bot.delete_message(message.chat.id, prev_mid)
        except Exception:
            pass
        _checklist_messages.pop(user_id, None)
    if edit:
        try:
            sent = await message.edit_text(header, reply_markup=kb, parse_mode="HTML")
            _checklist_messages[user_id] = sent.message_id
            return
        except Exception:
            pass
    sent = await message.answer(header, reply_markup=kb, parse_mode="HTML")
    _checklist_messages[user_id] = sent.message_id

# ─── Checklist FSM — Create ───────────────────────────────────────────────────

async def _start_checklist_create(message: Message, state: FSMContext, pre_title: str = ""):
    """Start checklist creation FSM."""
    user_id = str(message.from_user.id)
    checklists = store_get_checklists(user_id)
    if len(checklists) >= CHECKLIST_LIMIT:
        await message.answer(
            f"⚠️ Лимит чеклистов: {CHECKLIST_LIMIT}. Удали один чтобы создать новый.",
            reply_markup=get_main_keyboard()
        )
        return
    if pre_title:
        await state.update_data(cl_title=pre_title)
        await state.set_state(ChecklistStates.waiting_for_items)
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cl_cancel_fsm")]
        ])
        sent = await message.answer(
            f"☑️ <b>{pre_title}</b>\n\nДобавляй пункты — каждый с новой строки.\n"
            "<i>Пример:\nПалатка\nСпальник\nАптечка</i>",
            reply_markup=cancel_kb
        )
        await state.update_data(_cl_instr_msg_id=sent.message_id,
                                _cl_instr_chat_id=message.chat.id)
    else:
        await state.set_state(ChecklistStates.waiting_for_title)
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cl_cancel_fsm")]
        ])
        sent = await message.answer(
            "☑️ <b>Новый чеклист</b>\n\nКак назовём?",
            reply_markup=cancel_kb
        )
        await state.update_data(_cl_instr_msg_id=sent.message_id,
                                _cl_instr_chat_id=message.chat.id)

@router.callback_query(F.data == "profile_achievements")
async def cb_profile_achievements(callback: CallbackQuery):
    """Show achievements dashboard inline."""
    await callback.answer()
    user_id = str(callback.from_user.id)
    ach_count = store_get_achievements_count(user_id)
    if ach_count == 0:
        text = "💎 Достижений пока нет.\n\nКаждое закрытое дело добавляет слой к твоему резонансу."
    else:
        text = f"<b>💎 Достижения · всего {ach_count}</b>"
        text += _build_sphere_stats(user_id, months=3, show_tasks=False)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить достижение", callback_data="ach_add_from_menu")],
        [InlineKeyboardButton(text="← Назад в профиль", callback_data="profile_back")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "profile_back")
async def cb_profile_back(callback: CallbackQuery):
    await callback.answer()
    user_id = str(callback.from_user.id)
    await _show_profile(user_id, callback.message)


@router.callback_query(F.data == "ach_add_from_menu")
async def cb_ach_add_from_menu(callback: CallbackQuery, state: FSMContext):
    """Start add achievement FSM from achievements menu."""
    await callback.answer()
    user_id = str(callback.from_user.id)
    if not is_authorized(user_id):
        await callback.message.answer("🌿 Используй /start")
        return
    await state.set_state(AchievementStates.waiting_for_title)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад к достижениям", callback_data="profile_achievements")]
    ])
    try:
        await callback.message.edit_text(
            "💎 <b>Что сделано?</b>\n\n<i>Напиши одним предложением.</i>",
            reply_markup=cancel_kb, parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            "💎 <b>Что сделано?</b>\n\n<i>Напиши одним предложением.</i>",
            reply_markup=cancel_kb, parse_mode="HTML"
        )


@router.callback_query(F.data == "cl_create_new")
async def cb_cl_create_new(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _start_checklist_create(callback.message, state)

@router.message(StateFilter(ChecklistStates.waiting_for_title))
async def cl_title_input(message: Message, state: FSMContext):
    # Support voice input via state override
    _sd = await state.get_data()
    _vt = _sd.get("_voice_text")
    if _vt:
        await state.update_data(_voice_text=None)
    title = (_vt or message.text or "").strip()
    if not title or len(title) < 2:
        await message.answer("☑️ Введи название чеклиста (минимум 2 символа).")
        return
    await state.update_data(cl_title=title)
    await state.set_state(ChecklistStates.waiting_for_items)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cl_cancel_fsm")]
    ])
    # Try delete previous instruction
    _prev = (await state.get_data())
    if _prev.get("_cl_instr_msg_id"):
        try:
            await message.bot.delete_message(_prev["_cl_instr_chat_id"], _prev["_cl_instr_msg_id"])
        except Exception:
            pass
    sent = await message.answer(
        f"☑️ <b>{title}</b>\n\nДобавляй пункты — каждый с новой строки.\n"
        "<i>Пример:\nПалатка\nСпальник\nАптечка</i>",
        reply_markup=cancel_kb
    )
    await state.update_data(_cl_instr_msg_id=sent.message_id,
                            _cl_instr_chat_id=message.chat.id)

@router.message(StateFilter(ChecklistStates.waiting_for_items))
async def cl_items_input(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    data  = await state.get_data()
    title = data.get("cl_title", "Чеклист")
    _vt   = data.get("_voice_text")
    if _vt:
        # Clear voice text from state after reading
        await state.update_data(_voice_text=None)
    raw = (_vt or message.text or "").strip()
    if not raw:
        await message.answer("☑️ Введи хотя бы один пункт.")
        return
    # Split by newlines
    item_texts = [line.strip() for line in raw.splitlines() if line.strip()]
    item_texts = item_texts[:CHECKLIST_ITEMS_LIMIT]
    checklists = store_get_checklists(user_id)
    cid = _make_checklist_id(title, checklists)
    items = [{"id": f"i{i+1}", "text": t, "done": False} for i, t in enumerate(item_texts)]
    new_cl = {
        "id":               cid,
        "title":            title,
        "items":            items,
        "pinned_message_id": None,
        "created":          _today()
    }
    checklists.append(new_cl)
    store_set_checklists(user_id, checklists)
    _fire_sync()
    # Delete instruction message
    _d = await state.get_data()
    if _d.get("_cl_instr_msg_id"):
        try:
            await message.bot.delete_message(_d["_cl_instr_chat_id"], _d["_cl_instr_msg_id"])
        except Exception:
            pass
    await state.clear()
    await message.answer(f"✅ Чеклист «{title}» создан с {len(items)} пунктами!")
    sent = await message.answer(
        f"☑️ <b>{title}</b>  0/{len(items)}",
        reply_markup=get_checklist_inline(new_cl)
    )
    # Store message_id (no auto-pin — available in menu)
    new_cl["pinned_message_id"] = sent.message_id
    store_set_checklists(user_id, checklists)
    _fire_sync()

@router.callback_query(F.data == "cl_cancel_fsm")
async def cb_cl_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await cb_checklists_mgmt(callback, state)

# ─── Checklist — Toggle item ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cl_toggle|"))
async def cb_cl_toggle(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    parts   = callback.data.split("_")
    # cl_toggle_CLID_IID — but CLID can have underscores, so:
    # format: cl_toggle_{cid}_{iid}
    parts = callback.data.split("|")
    cid = parts[1] if len(parts) > 1 else ""
    iid = parts[2] if len(parts) > 2 else ""
    checklists = store_get_checklists(user_id)
    cl = next((c for c in checklists if c["id"] == cid), None)
    if not cl:
        await callback.answer("Чеклист не найден", show_alert=True)
        return
    for it in cl.get("items", []):
        if it["id"] == iid:
            it["done"] = not it.get("done", False)
            break
    store_set_checklists(user_id, checklists)
    _fire_sync()
    prog   = _checklist_progress(cl)
    items  = cl.get("items", [])
    header = f"☑️ <b>{cl['title']}</b>  {prog}"
    # Check 100% completion
    if items and all(it.get("done") for it in items):
        count  = store_increment_achievements(user_id)
        cl_res = store_add_sphere_resonance(user_id, "growth", 2)
        # Auto-delete completed checklist
        checklists = [c for c in checklists if c["id"] != cl["id"]]
        store_set_checklists(user_id, checklists)
        _fire_sync()
        try:
            await callback.message.edit_text(
                f"🎉 <b>{cl['title']}</b> — выполнен полностью!\n"
                f"💎 +1 достижение · всего {count} · 🔮 +2% → {cl_res}%"
            )
        except Exception:
            pass
        return
    try:
        await callback.message.edit_text(header, reply_markup=get_checklist_inline(cl))
    except Exception:
        pass

# ─── Checklist — Open / Pin ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cl_open_"))
async def cb_cl_open(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    cid     = callback.data[len("cl_open_"):]
    checklists = store_get_checklists(user_id)
    cl = next((c for c in checklists if c["id"] == cid), None)
    if not cl:
        await callback.answer("Чеклист не найден", show_alert=True)
        return
    prog   = _checklist_progress(cl)
    header = f"☑️ <b>{cl['title']}</b>  {prog}"
    try:
        sent = await callback.message.edit_text(header, reply_markup=get_checklist_inline(cl), parse_mode="HTML")
        _checklist_messages[user_id] = callback.message.message_id
    except Exception:
        sent = await callback.message.answer(header, reply_markup=get_checklist_inline(cl), parse_mode="HTML")
        _checklist_messages[user_id] = sent.message_id

@router.callback_query(F.data.startswith("cl_pin_"))
async def cb_cl_pin(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    cid     = callback.data[len("cl_pin_"):]
    checklists = store_get_checklists(user_id)
    cl = next((c for c in checklists if c["id"] == cid), None)
    if not cl:
        return
    prog   = _checklist_progress(cl)
    header = f"☑️ <b>{cl['title']}</b>  {prog}"
    sent = await callback.message.answer(header, reply_markup=get_checklist_inline(cl))
    cl["pinned_message_id"] = sent.message_id
    store_set_checklists(user_id, checklists)
    _fire_sync()
    try:
        await callback.message.bot.pin_chat_message(
            callback.message.chat.id, sent.message_id, disable_notification=True
        )
        await callback.answer("📌 Закреплено!", show_alert=False)
    except Exception:
        pass

# ─── Checklist — Delete ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cl_delete_"))
async def cb_cl_delete(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    cid     = callback.data[len("cl_delete_"):]
    checklists = store_get_checklists(user_id)
    cl = next((c for c in checklists if c["id"] == cid), None)
    if not cl:
        return
    title = cl.get("title", "—")
    checklists = [c for c in checklists if c["id"] != cid]
    store_set_checklists(user_id, checklists)
    _fire_sync()
    header = f"☑️ <b>Чеклисты</b> ({len(checklists)}/{CHECKLIST_LIMIT})"
    try:
        await callback.message.edit_text(header, reply_markup=get_checklists_mgmt_inline(checklists))
    except Exception:
        await callback.message.answer(header, reply_markup=get_checklists_mgmt_inline(checklists))

# ─── Checklist — Edit (add/delete/edit items) ────────────────────────────────

@router.callback_query(F.data.startswith("cl_edit_"))
async def cb_cl_edit_menu(callback: CallbackQuery, state: FSMContext):
    """Show edit options for a checklist."""
    await _safe_cb_answer(callback)
    cid = callback.data[len("cl_edit_"):]
    user_id = str(callback.from_user.id)
    checklists = store_get_checklists(user_id)
    cl = next((c for c in checklists if c["id"] == cid), None)
    if not cl:
        return
    items = cl.get("items", [])
    edit_kb_rows = [
        [InlineKeyboardButton(text="➕ Добавить пункт",   callback_data=f"cl_add_item_{cid}")],
    ]
    for idx, it in enumerate(items):
        iid  = it["id"]
        mark = "✅" if it.get("done") else "☐"
        num  = idx + 1
        text = it["text"][:18]
        row = [
            InlineKeyboardButton(text=f"{num}. {mark} {text}", callback_data=f"cl_noop|{cid}|{iid}"),
            InlineKeyboardButton(text="✏️",  callback_data=f"cl_edititem|{cid}|{iid}"),
            InlineKeyboardButton(text="🗑",  callback_data=f"cl_delitem|{cid}|{iid}"),
        ]
        # Add up/down arrows
        if idx > 0:
            row.append(InlineKeyboardButton(text="↑", callback_data=f"cl_moveup|{cid}|{iid}"))
        if idx < len(items) - 1:
            row.append(InlineKeyboardButton(text="↓", callback_data=f"cl_movedn|{cid}|{iid}"))
        edit_kb_rows.append(row)
    edit_kb_rows.append([InlineKeyboardButton(text="← Назад", callback_data=f"cl_open_{cid}")])
    try:
        await callback.message.edit_text(
            f"✏️ <b>{cl['title']}</b> — редактирование пунктов:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=edit_kb_rows)
        )
    except Exception:
        pass

@router.callback_query(F.data.startswith("cl_moveup|") | F.data.startswith("cl_movedn|"))
async def cb_cl_move_item(callback: CallbackQuery, state: FSMContext):
    """Move checklist item up or down."""
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    parts = callback.data.split("|")
    if len(parts) != 3:
        return
    direction, cid, iid = parts
    checklists = store_get_checklists(user_id)
    cl = next((c for c in checklists if c["id"] == cid), None)
    if not cl:
        return
    items = cl.get("items", [])
    idx = next((i for i, it in enumerate(items) if it["id"] == iid), None)
    if idx is None:
        return
    if direction == "cl_moveup" and idx > 0:
        items[idx], items[idx-1] = items[idx-1], items[idx]
    elif direction == "cl_movedn" and idx < len(items) - 1:
        items[idx], items[idx+1] = items[idx+1], items[idx]
    else:
        return
    cl["items"] = items
    store_set_checklists(user_id, checklists)
    await _sync_pending()
    # Refresh edit menu
    edit_kb_rows = [
        [InlineKeyboardButton(text="➕ Добавить пункт", callback_data=f"cl_add_item_{cid}")],
    ]
    for i2, it2 in enumerate(items):
        iid2 = it2["id"]
        mark2 = "✅" if it2.get("done") else "☐"
        num2  = i2 + 1
        text2 = it2["text"][:18]
        row2 = [
            InlineKeyboardButton(text=f"{num2}. {mark2} {text2}", callback_data=f"cl_noop|{cid}|{iid2}"),
            InlineKeyboardButton(text="✏️", callback_data=f"cl_edititem|{cid}|{iid2}"),
            InlineKeyboardButton(text="🗑", callback_data=f"cl_delitem|{cid}|{iid2}"),
        ]
        if i2 > 0:
            row2.append(InlineKeyboardButton(text="↑", callback_data=f"cl_moveup|{cid}|{iid2}"))
        if i2 < len(items) - 1:
            row2.append(InlineKeyboardButton(text="↓", callback_data=f"cl_movedn|{cid}|{iid2}"))
        edit_kb_rows.append(row2)
    edit_kb_rows.append([InlineKeyboardButton(text="← Назад", callback_data=f"cl_open_{cid}")])
    try:
        await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=edit_kb_rows))
    except Exception:
        pass

@router.callback_query(F.data.startswith("cl_add_item_"))
async def cb_cl_add_item_start(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    cid = callback.data[len("cl_add_item_"):]
    await state.update_data(cl_edit_id=cid, cl_edit_item_id=None)
    await state.set_state(ChecklistStates.waiting_for_item_edit)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cl_edit_{cid}")]
    ])
    try:
        await callback.message.edit_text("➕ Введи текст нового пункта:", reply_markup=cancel_kb)
    except Exception:
        await callback.message.answer("➕ Введи текст нового пункта:", reply_markup=cancel_kb)

@router.callback_query(F.data.startswith("cl_edititem|"))
async def cb_cl_edititem_start(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    parts = callback.data.split("|")
    cid = parts[1] if len(parts) > 1 else ""
    iid = parts[2] if len(parts) > 2 else ""
    await state.update_data(cl_edit_id=cid, cl_edit_item_id=iid)
    await state.set_state(ChecklistStates.waiting_for_item_edit)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cl_edit_{cid}")]
    ])
    try:
        await callback.message.edit_text("✏️ Введи новый текст для пункта:", reply_markup=cancel_kb)
    except Exception:
        await callback.message.answer("✏️ Введи новый текст для пункта:", reply_markup=cancel_kb)

@router.message(StateFilter(ChecklistStates.waiting_for_item_edit))
async def cl_item_edit_input(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    data    = await state.get_data()
    cid     = data.get("cl_edit_id", "")
    iid     = data.get("cl_edit_item_id")
    new_text = (message.text or "").strip()
    if not new_text:
        await message.answer("⚠️ Введи текст пункта.")
        return
    checklists = store_get_checklists(user_id)
    cl = next((c for c in checklists if c["id"] == cid), None)
    if not cl:
        await state.clear()
        return
    if iid:
        # Edit existing item
        for it in cl.get("items", []):
            if it["id"] == iid:
                it["text"] = new_text
                break
        msg = f"✅ Пункт изменён: «{new_text}»"
    else:
        # Add new item
        items = cl.get("items", [])
        if len(items) >= CHECKLIST_ITEMS_LIMIT:
            await message.answer(f"⚠️ Лимит пунктов: {CHECKLIST_ITEMS_LIMIT}.")
            await state.clear()
            return
        new_id = f"i{len(items)+1}"
        items.append({"id": new_id, "text": new_text, "done": False})
        cl["items"] = items
        msg = f"✅ Пункт добавлен: «{new_text}»"
    store_set_checklists(user_id, checklists)
    _fire_sync()
    await state.clear()
    await message.answer(msg)
    prog   = _checklist_progress(cl)
    await message.answer(
        f"☑️ <b>{cl['title']}</b>  {prog}",
        reply_markup=get_checklist_inline(cl)
    )

@router.callback_query(F.data.startswith("cl_delitem|"))
async def cb_cl_delitem(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    user_id   = str(callback.from_user.id)
    parts = callback.data.split("|")
    cid = parts[1] if len(parts) > 1 else ""
    iid = parts[2] if len(parts) > 2 else ""
    checklists = store_get_checklists(user_id)
    cl = next((c for c in checklists if c["id"] == cid), None)
    if cl:
        cl["items"] = [it for it in cl.get("items", []) if it["id"] != iid]
        store_set_checklists(user_id, checklists)
        _fire_sync()
    if cl:
        items = cl.get("items", [])
        edit_kb_rows = [
            [InlineKeyboardButton(text="➕ Добавить пункт", callback_data=f"cl_add_item_{cid}")],
        ]
        for it in items:
            iid2 = it["id"]
            mark = "✅" if it.get("done") else "☐"
            text = it["text"][:20]
            edit_kb_rows.append([
                InlineKeyboardButton(text=f"{mark} {text}", callback_data=f"cl_noop|{cid}|{iid2}"),
                InlineKeyboardButton(text="✏️",              callback_data=f"cl_edititem|{cid}|{iid2}"),
                InlineKeyboardButton(text="🗑",              callback_data=f"cl_delitem|{cid}|{iid2}"),
            ])
        edit_kb_rows.append([InlineKeyboardButton(text="← Назад", callback_data=f"cl_open_{cid}")])
        try:
            await callback.message.edit_text(
                f"🗑 Пункт удалён.\n✏️ <b>{cl['title']}</b>:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=edit_kb_rows)
            )
        except Exception:
            pass

@router.callback_query(F.data.startswith("cl_noop|"))
async def cb_cl_noop(callback: CallbackQuery):
    await callback.answer()

# ─── Checklist — Settings navigation ─────────────────────────────────────────

@router.callback_query(F.data == "menu_checklists_mgmt")
async def cb_checklists_mgmt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id    = str(callback.from_user.id)
    checklists = store_get_checklists(user_id)
    header     = f"☑️ <b>Чеклисты</b> ({len(checklists)}/{CHECKLIST_LIMIT})"
    try:
        await callback.message.edit_text(header, reply_markup=get_checklists_mgmt_inline(checklists))
    except Exception:
        await callback.message.answer(header, reply_markup=get_checklists_mgmt_inline(checklists))


# ─── Reminders ────────────────────────────────────────────────────────────────

async def _recover_pending_edit(user_id: str, state: FSMContext) -> dict:
    """Recover pending reminder edit data. FSM first, then workspace fallback."""
    data = await state.get_data()
    rid = data.get("_rem_edit_id", "")
    title = data.get("_rem_title", "")
    dt = data.get("_rem_dt", "")
    repeat = data.get("_rem_repeat", "")
    if rid and (title or dt):
        return {"_rem_edit_id": rid, "_rem_title": title, "_rem_dt": dt, "_rem_repeat": repeat or "once"}
    ws = store_get_workspace(user_id) or {}
    pending = ws.get("_pending_reminder_edit") or {}
    if pending.get("_rem_edit_id"):
        await state.update_data(_rem_edit_id=pending["_rem_edit_id"], _rem_title=pending.get("_rem_title",""), _rem_dt=pending.get("_rem_dt",""), _rem_repeat=pending.get("_rem_repeat","once"))
        logger.info(f"Recovered pending reminder edit for {user_id} from workspace")
        return pending
    return {}



def _make_reminder_id(existing: list) -> str:
    import uuid
    ids = {r["id"] for r in existing}
    for _ in range(10):
        rid = "rem_" + str(uuid.uuid4())[:8]
        if rid not in ids:
            return rid
    return "rem_" + str(len(existing) + 1)

def get_reminders_mgmt_inline(reminders: list) -> InlineKeyboardMarkup:
    # Патчер А: только название, тап → меню редактирования
    btns = [[InlineKeyboardButton(text="➕ Новое напоминание", callback_data="rem_create_new")]]
    for r in reminders:
        rid   = r.get("id", "")
        title = r.get("title", "—")[:28]
        btns.append([
            InlineKeyboardButton(text=f"🔔 {title}", callback_data=f"rem_open_{rid}"),
        ])
    btns.append([InlineKeyboardButton(text="← Назад в профиль", callback_data="profile_back")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def get_reminder_edit_inline(rid: str) -> InlineKeyboardMarkup:
    """Меню редактирования одного напоминания."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Название",     callback_data=f"rem_edit_title_{rid}")],
        [InlineKeyboardButton(text="📅 Дата/время",   callback_data=f"rem_edit_dt_{rid}")],
        [InlineKeyboardButton(text="🔁 Повторение",   callback_data=f"rem_edit_repeat_{rid}")],
        [InlineKeyboardButton(text="🗑 Удалить",      callback_data=f"rem_del_{rid}")],
        [InlineKeyboardButton(text="← Назад",         callback_data="menu_reminders_mgmt")],
    ])

@router.callback_query(F.data == "menu_reminders_mgmt")
async def cb_reminders_mgmt(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    user_id   = str(callback.from_user.id)
    # Cleanup pending reminder edit if any
    ws = store_get_workspace(user_id) or {}
    ws.pop("_pending_reminder_edit", None)
    store_set_workspace(user_id, ws)
    reminders = store_get_reminders(user_id)
    header    = f"🔔 <b>Напоминания</b> ({len(reminders)}/{REMINDER_LIMIT})"
    try:
        await callback.message.edit_text(header, reply_markup=get_reminders_mgmt_inline(reminders))
    except Exception:
        await callback.message.answer(header, reply_markup=get_reminders_mgmt_inline(reminders))

@router.callback_query(F.data == "rem_create_new")
async def cb_rem_create_new(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    _rem_count_s1 = len(store_get_reminders(user_id))
    if _rem_count_s1 >= REMINDER_LIMIT:
        await callback.message.answer(f"⚠️ Лимит {REMINDER_LIMIT} напоминаний. Удали старые.")
        return
    elif _rem_count_s1 >= REMINDER_LIMIT_SOFT:
        await callback.message.answer(f"⚠️ Почти лимит: {_rem_count_s1}/{REMINDER_LIMIT} напоминаний.")
    # Очищаем оба pending — иначе старый _rem_edit_id подхватится в fallback
    ws_create = store_get_workspace(user_id) or {}
    ws_create.pop("_pending_reminder_edit", None)
    ws_create.pop("_pending_reminder_create", None)
    store_set_workspace(user_id, ws_create)
    # Очищаем FSM чтобы не было хвостов от предыдущих сессий
    await state.clear()
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_reminders_mgmt")]
    ])
    try:
        await callback.message.edit_text(
            "🔔 <b>Новое напоминание</b>\n\n"
            "Напиши название, дату и время в свободной форме.\n"
            "<i>Пример: Купить продукты завтра в 10:00</i>",
            reply_markup=cancel_kb
        )
        msg_id  = callback.message.message_id
        chat_id = callback.message.chat.id
    except Exception:
        sent = await callback.message.answer(
            "🔔 <b>Новое напоминание</b>\n\nНапиши название и время:",
            reply_markup=cancel_kb
        )
        msg_id  = sent.message_id
        chat_id = sent.chat.id
    await state.set_state(ReminderStates.waiting_for_input)
    await state.update_data(_rem_msg_id=msg_id, _rem_chat_id=chat_id)

@router.callback_query(F.data.startswith("rem_del_"))
async def cb_rem_delete(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    user_id   = str(callback.from_user.id)
    rid       = callback.data[len("rem_del_"):]
    reminders = [r for r in store_get_reminders(user_id) if r["id"] != rid]
    store_set_reminders(user_id, reminders)
    _fire_sync()
    header = f"🔔 <b>Напоминания</b> ({len(reminders)}/{REMINDER_LIMIT})"
    try:
        await callback.message.edit_text(header, reply_markup=get_reminders_mgmt_inline(reminders))
    except Exception:
        pass

# ─── Reminder Edit (v7.37) ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("rem_edit_") & ~F.data.startswith("rem_edit_title_") & ~F.data.startswith("rem_edit_dt_") & ~F.data.startswith("rem_edit_repeat_"))
async def cb_rem_edit_start(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    rid     = callback.data[len("rem_edit_"):]
    reminders = store_get_reminders(user_id)
    rem = next((r for r in reminders if r["id"] == rid), None)
    if not rem:
        await callback.answer("Напоминание не найдено", show_alert=True)
        return
    await state.update_data(_rem_edit_id=rid, _rem_title=rem.get("title",""), _rem_dt=rem.get("datetime_iso",""), _rem_repeat=rem.get("repeat","once"))
    await state.set_state(ReminderStates.waiting_for_input)
    # Save pending to workspace for recovery after state loss
    ws = store_get_workspace(user_id) or {}
    ws["_pending_reminder_edit"] = {"_rem_edit_id": rid, "_rem_title": rem.get("title",""), "_rem_dt": rem.get("datetime_iso",""), "_rem_repeat": rem.get("repeat","once")}
    store_set_workspace(user_id, ws)
    dt_display = rem.get("datetime_iso", "")[:16].replace("T", " ")
    rep_display = _repeat_label(rem.get("repeat", "once"))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Название", callback_data="redit_title"),
         InlineKeyboardButton(text="📅 Дату/время", callback_data="redit_dt")],
        [InlineKeyboardButton(text="🔁 Повторение", callback_data="redit_repeat")],
        [InlineKeyboardButton(text="← Назад", callback_data="menu_reminders_mgmt")],
    ])
    try:
        await callback.message.edit_text(
            f"✏️ <b>{rem['title']}</b>\n"
            f"📅 {dt_display}\n"
            f"🔁 {rep_display}\n\n"
            f"Что меняем?",
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            f"✏️ <b>{rem['title']}</b>\nЧто меняем?",
            reply_markup=kb,
            parse_mode="HTML"
        )

@router.callback_query(F.data == "redit_title")
async def cb_rem_edit_title(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    pending = await _recover_pending_edit(user_id, state)
    if not pending or not pending.get("_rem_edit_id"):
        await callback.answer("🌿 Напоминание не найдено. Начни редактирование заново.", show_alert=True)
        return
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_reminders_mgmt")]
    ])
    await state.set_state(ReminderStates.waiting_for_input)
    try:
        await callback.message.edit_text("✏️ Введи новое название:", reply_markup=cancel_kb)
    except Exception:
        await callback.message.answer("✏️ Введи новое название:", reply_markup=cancel_kb)
    await state.update_data(_rem_edit_field="title")

@router.callback_query(F.data == "redit_dt")
async def cb_rem_edit_dt(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    pending = await _recover_pending_edit(user_id, state)
    if not pending or not pending.get("_rem_edit_id"):
        await callback.answer("🌿 Напоминание не найдено. Начни редактирование заново.", show_alert=True)
        return
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_reminders_mgmt")]
    ])
    await state.set_state(ReminderStates.waiting_for_input)
    try:
        await callback.message.edit_text("📅 Введи новую дату и время (ДД.ММ.ГГ ЧЧ:ММ):", reply_markup=cancel_kb)
    except Exception:
        await callback.message.answer("📅 Введи новую дату и время:", reply_markup=cancel_kb)
    await state.update_data(_rem_edit_field="dt")

@router.callback_query(F.data == "redit_repeat")
async def cb_rem_edit_repeat(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    data = await state.get_data()
    rid = data.get("_rem_edit_id", "")
    if not rid:
        pending = await _recover_pending_edit(user_id, state)
        rid = pending.get("_rem_edit_id", "") if pending else ""
    if not rid:
        await callback.answer("Напоминание не найдено", show_alert=True)
        return
    reminders = store_get_reminders(user_id)
    rem = next((r for r in reminders if r["id"] == rid), None)
    if not rem:
        await callback.answer("Напоминание не найдено", show_alert=True)
        return
    current = rem.get("repeat", "once")
    # Persist to BOTH state and workspace
    pending = {
        "_rem_edit_id": rid,
        "_rem_title": rem.get("title", ""),
        "_rem_dt": rem.get("datetime_iso", ""),
        "_rem_repeat": current
    }
    await state.update_data(**pending)
    ws = store_get_workspace(user_id) or {}
    ws["_pending_reminder_edit"] = pending
    store_set_workspace(user_id, ws)
    await state.set_state(ReminderStates.waiting_for_repeat)
    try:
        await callback.message.edit_text(
            "🔔 <b>Повторение:</b>",
            reply_markup=_repeat_picker_keyboard(current),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            "🔔 <b>Повторение:</b>",
            reply_markup=_repeat_picker_keyboard(current),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("rem_noop_"))
async def cb_rem_noop(callback: CallbackQuery):
    await _safe_cb_answer(callback)

@router.callback_query(F.data.startswith("rem_open_"))
async def cb_rem_open(callback: CallbackQuery):
    """Тап по напоминанию → меню редактирования."""
    await _safe_cb_answer(callback)
    rid = callback.data[9:]
    user_id = str(callback.from_user.id)
    reminders = store_get_reminders(user_id)
    rem = next((r for r in reminders if r.get("id") == rid), None)
    if not rem:
        await callback.answer("Напоминание не найдено", show_alert=True)
        return
    title = rem.get("title", "—")
    dt = (rem.get("datetime_iso") or "")[:16].replace("T", " ")
    rep = _repeat_label(rem.get("repeat", "once"))
    text = f"🔔 <b>{title}</b>\n📅 {dt}\n🔁 {rep}"
    try:
        await callback.message.edit_text(text, reply_markup=get_reminder_edit_inline(rid), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=get_reminder_edit_inline(rid), parse_mode="HTML")

# rem_edit_title_, rem_edit_dt_, rem_edit_repeat_ → редиректим на существующие handlers
@router.callback_query(F.data.startswith("rem_edit_title_"))
async def cb_rem_edit_title(callback: CallbackQuery, state: FSMContext):
    rid = callback.data[15:]
    await callback.answer()
    await state.update_data(_rem_edit_id=rid, _rem_edit_field="title")
    await state.set_state(ReminderStates.waiting_for_input)
    _back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data=f"rem_open_{rid}")]
    ])
    try:
        await callback.message.edit_text("✏️ <b>Новое название:</b>", reply_markup=_back_kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer("✏️ Введи новое название:", reply_markup=_back_kb)

@router.callback_query(F.data.startswith("rem_edit_dt_"))
async def cb_rem_edit_dt(callback: CallbackQuery, state: FSMContext):
    rid = callback.data[12:]
    await callback.answer()
    await state.update_data(_rem_edit_id=rid, _rem_edit_field="dt")
    await state.set_state(ReminderStates.waiting_for_input)
    _back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data=f"rem_open_{rid}")]
    ])
    try:
        await callback.message.edit_text("📅 <b>Новая дата и время (ДД.ММ.ГГ ЧЧ:ММ):</b>", reply_markup=_back_kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer("📅 Введи дату и время (ДД.ММ.ГГ ЧЧ:ММ):", reply_markup=_back_kb)

@router.callback_query(F.data.startswith("rem_edit_repeat_"))
async def cb_rem_edit_repeat(callback: CallbackQuery, state: FSMContext):
    rid = callback.data[16:]
    await callback.answer()
    await state.update_data(_rem_edit_id=rid)
    await state.set_state(ReminderStates.waiting_for_repeat)
    user_id = str(callback.from_user.id)
    reminders = store_get_reminders(user_id)
    rem = next((r for r in reminders if r.get("id") == rid), None)
    current = rem.get("repeat", "once") if rem else "once"
    try:
        await callback.message.edit_text(
            "🔁 <b>Повторение:</b>",
            reply_markup=_repeat_picker_keyboard(current),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer("🔁 Повторение:", reply_markup=_repeat_picker_keyboard(current))

@router.message(StateFilter(ReminderStates.waiting_for_input))
async def rem_text_input(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    raw     = (message.text or "").strip()
    data    = await state.get_data()
    
    # ── EDIT MODE: if _rem_edit_field is set ──────────────────────────────
    edit_field = data.get("_rem_edit_field", "")
    edit_id = data.get("_rem_edit_id", "")
    
    if edit_field and edit_id:
        reminders = store_get_reminders(user_id)
        rem = next((r for r in reminders if r["id"] == edit_id), None)
        if not rem:
            await state.clear()
            await message.answer("🌀 Напоминание не найдено.")
            return
        
        if edit_field == "title":
            new_title = raw.strip()
            if not new_title or len(new_title) < 2:
                await message.answer("⚠️ Название слишком короткое.")
                return
            rem["title"] = new_title
            store_set_reminders(user_id, reminders)
            _fire_sync()
            await state.clear()
            await message.answer(f"✅ Название → «{new_title}»")
            header = f"🔔 <b>Напоминания</b> ({len(reminders)}/{REMINDER_LIMIT})"
            await message.answer(header, reply_markup=get_reminders_mgmt_inline(reminders), parse_mode="HTML")
            return
        
        elif edit_field == "dt":
            import re as _re_edit
            m = _re_edit.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{2,4})\s+(\d{1,2}):(\d{2})$", raw)
            if not m:
                await message.answer("⚠️ Формат: ДД.ММ.ГГ ЧЧ:ММ")
                return
            dd, mm, yy, hh, mi = m.groups()
            yy = "20" + yy if len(yy) == 2 else yy
            rem["datetime_iso"] = f"{yy}-{mm.zfill(2)}-{dd.zfill(2)}T{hh.zfill(2)}:{mi}"
            store_set_reminders(user_id, reminders)
            _fire_sync()
            await state.clear()
            dt_disp = rem["datetime_iso"][:16].replace("T", " ")
            await message.answer(f"✅ Дата/время → {dt_disp}")
            header = f"🔔 <b>Напоминания</b> ({len(reminders)}/{REMINDER_LIMIT})"
            await message.answer(header, reply_markup=get_reminders_mgmt_inline(reminders), parse_mode="HTML")
            return
    
    # ── CREATE MODE ───────────────────────────────────────────────────────
    if data.get("_rem_msg_id"):
        try:
            await message.bot.delete_message(data["_rem_chat_id"], data["_rem_msg_id"])
        except Exception:
            pass
    # Parse with _create_reminder_atomic but DON'T save — it returns parsed dict
    # We'll extract title and datetime from it, but create only on confirm
    import re as _re_parse
    from datetime import datetime as _dt_parse, timedelta as _td_parse
    from zoneinfo import ZoneInfo as _ZI_parse
    
    profile_p = store_get_profile(user_id) or {}
    tz_name_p = profile_p.get("companion_settings", {}).get("timezone", "Europe/Moscow")
    try:
        tz_p = _ZI_parse(tz_name_p)
    except Exception:
        tz_p = _ZI_parse("Europe/Moscow")
    now_p = _dt_parse.now(tz_p)
    
    # Parse title and datetime from raw text
    title_clean = raw.strip()
    dt_iso = None
    
    # Try to extract date and time — order matters: most specific patterns first
    MONTHS_P = {"января":1,"февраля":2,"марта":3,"апреля":4,"мая":5,"июня":6,
                "июля":7,"августа":8,"сентября":9,"октября":10,"ноября":11,"декабря":12}

    # Pattern 1: "сегодня/завтра/послезавтра в ЧЧ:ММ" OR "сегодня/завтра ЧЧ:ММ" (with comma or space)
    m = _re_parse.search(
        r'(завтра|сегодня|послезавтра)[,\s]+(?:в\s+)?(\d{1,2}):(\d{2})',
        title_clean.lower()
    )
    if m:
        day_word, hh, mm = m.group(1), m.group(2), m.group(3)
        title_clean = (title_clean[:m.start()].strip() + " " + title_clean[m.end():].strip()).strip()
        days_offset = {"сегодня": 0, "завтра": 1, "послезавтра": 2}.get(day_word, 0)
        target = (now_p + _td_parse(days=days_offset)).replace(
            hour=int(hh), minute=int(mm), second=0, microsecond=0)
        offset = target.strftime("%z")
        offset_f = offset[:3] + ":" + offset[3:] if offset else "+00:00"
        dt_iso = target.strftime(f"%Y-%m-%dT%H:%M{offset_f}")
    else:
        # Pattern 2: "сегодня/завтра в Ч" (без минут)
        m = _re_parse.search(
            r'(завтра|сегодня|послезавтра)[,\s]+(?:в\s+)?(\d{1,2})(?!:)(\s|$)',
            title_clean.lower()
        )
        if m:
            day_word, hh = m.group(1), m.group(2)
            title_clean = (title_clean[:m.start()].strip() + " " + title_clean[m.end():].strip()).strip()
            days_offset = {"сегодня": 0, "завтра": 1, "послезавтра": 2}.get(day_word, 0)
            target = (now_p + _td_parse(days=days_offset)).replace(
                hour=int(hh), minute=0, second=0, microsecond=0)
            offset = target.strftime("%z")
            offset_f = offset[:3] + ":" + offset[3:] if offset else "+00:00"
            dt_iso = target.strftime(f"%Y-%m-%dT%H:%M{offset_f}")
        else:
            # Pattern 3: "7 мая в 9:00" или "7 мая в 9"
            m = _re_parse.search(
                r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)'
                r'(?:\s+в\s+(\d{1,2})(?::(\d{2}))?)?',
                title_clean.lower()
            )
            if m:
                day, month_str = m.group(1), m.group(2)
                hh2, mm2 = m.group(3) or "9", m.group(4) or "0"
                month_num = MONTHS_P.get(month_str, now_p.month)
                target = now_p.replace(year=now_p.year, month=month_num, day=int(day),
                                       hour=int(hh2), minute=int(mm2), second=0, microsecond=0)
                if target < now_p:
                    target = target.replace(year=target.year + 1)
                offset = target.strftime("%z")
                offset_f = offset[:3] + ":" + offset[3:] if offset else "+00:00"
                dt_iso = target.strftime(f"%Y-%m-%dT%H:%M{offset_f}")
                title_clean = (title_clean[:m.start()].strip() + " " + title_clean[m.end():].strip()).strip()
    
    if not dt_iso:
        target = (now_p + _td_parse(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        offset = target.strftime("%z")
        offset_f = offset[:3] + ":" + offset[3:] if offset else "+00:00"
        dt_iso = target.strftime(f"%Y-%m-%dT%H:%M{offset_f}")
    
    title_clean = title_clean.strip().rstrip(".,;!")
    if not title_clean or len(title_clean) < 2:
        await message.answer("🔔 Не поняла. Напиши: <b>Купить продукты 7 мая в 9:00</b>", parse_mode="HTML")
        await state.clear()
        return
    
    dt_display = dt_iso[:16].replace("T", " ")
    # P-71a: direct create — no confirmation step
    reminders_71 = store_get_reminders(user_id)
    if len(reminders_71) >= REMINDER_LIMIT:
        await state.clear()
        await message.answer(f"⚠️ Лимит {REMINDER_LIMIT} напоминаний. Удали старые.")
        return
    if len(reminders_71) >= REMINDER_LIMIT_SOFT:
        await message.answer(f"⚠️ Почти лимит: {len(reminders_71)}/{REMINDER_LIMIT} напоминаний.")
    rid_71 = _make_reminder_id(reminders_71)
    reminders_71.append({"id": rid_71, "title": title_clean, "datetime_iso": dt_iso, "repeat": "once", "active": True})
    store_set_reminders(user_id, reminders_71)
    ws_71 = store_get_workspace(user_id) or {}
    ws_71.pop("_pending_reminder_create", None)
    ws_71.pop("_pending_reminder_edit", None)
    store_set_workspace(user_id, ws_71)
    _fire_sync()
    await state.clear()
    kb_71 = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить", callback_data=f"rem_edit_{rid_71}")]
    ])
    await message.answer(
        f"✅ Напоминание создано:\n🔔 {title_clean}\n📅 {dt_display} · ▶ Один раз",
        reply_markup=kb_71, parse_mode="HTML"
    )



# ─── Reminder Repeat Picker (v7.37) ────────────────────────────────────────

def _repeat_label(repeat: str) -> str:
    """Human-readable repeat label."""
    labels = {
        "once": "▶ Один раз",
        "daily": "🔁 Каждый день",
        "weekdays": "📅 По будням",
        "weekends": "🏖 По выходным",
        "weekly": "📆 Раз в неделю",
        "monthly": "📆 Раз в месяц",
        "yearly": "📆 Раз в год",
    }
    if repeat.startswith("custom_date:"):
        date_str = repeat.split(":")[1]
        return "📆 " + date_str
    if repeat.startswith("custom_days:"):
        days = repeat.split(":")[1]
        day_names = {"mon":"пн","tue":"вт","wed":"ср","thu":"чт","fri":"пт","sat":"сб","sun":"вс"}
        return "📅 " + ", ".join(day_names.get(d, d) for d in days.split(","))
    return labels.get(repeat, "▶ Один раз")


def _parse_weekdays(text: str) -> str:
    import re as _re2
    t = text.lower().strip()
    days_order = ["mon","tue","wed","thu","fri","sat","sun"]
    day_map = {
        "пн": "mon", "понедельник": "mon",
        "вт": "tue", "вторник": "tue",
        "ср": "wed", "среда": "wed", "среду": "wed",
        "чт": "thu", "четверг": "thu",
        "пт": "fri", "пятница": "fri", "пятницу": "fri",
        "сб": "sat", "суббота": "sat", "субботу": "sat",
        "вс": "sun", "воскресенье": "sun",
    }
    found = set()
    if any(w in t for w in ["каждый день", "ежедневно", "все дни"]):
        return "daily"
    if any(w in t for w in ["будние", "будни", "рабочие"]):
        found.update(["mon","tue","wed","thu","fri"])
    if any(w in t for w in ["выходные", "выходных"]):
        found.update(["sat","sun"])
    tokens = _re2.split(r"[,\s/]+", t)
    for token in tokens:
        token = token.strip(".,!?")
        if token in day_map:
            found.add(day_map[token])
    if not found:
        return "once"
    sorted_days = sorted(found, key=lambda d: days_order.index(d))
    if sorted_days == ["mon","tue","wed","thu","fri"]:
        return "weekdays"
    if sorted_days == ["sat","sun"]:
        return "weekends"
    if sorted_days == days_order:
        return "daily"
    return "custom_days:" + ",".join(sorted_days)


def _repeat_picker_keyboard(current: str = "once") -> InlineKeyboardMarkup:
    btns = [
        [InlineKeyboardButton(text="\U0001f501 \u041a\u0430\u0436\u0434\u044b\u0439 \u0434\u0435\u043d\u044c",    callback_data="rem_rp_daily")],
        [InlineKeyboardButton(text="\U0001f4c5 \u0420\u0430\u0437 \u0432 \u043d\u0435\u0434\u0435\u043b\u044e",   callback_data="rem_rp_weekly")],
        [InlineKeyboardButton(text="\U0001f5d3 \u0420\u0430\u0437 \u0432 \u043c\u0435\u0441\u044f\u0446",    callback_data="rem_rp_monthly")],
        [InlineKeyboardButton(text="\U0001f33f \u0420\u0430\u0437 \u0432 \u0433\u043e\u0434",      callback_data="rem_rp_yearly")],
        [InlineKeyboardButton(text="\u270d\ufe0f \u041f\u043e \u0434\u043d\u044f\u043c \u043d\u0435\u0434\u0435\u043b\u0438", callback_data="rem_rp_custom")],
        [InlineKeyboardButton(text="\U0001f4c6 \u0421\u0432\u043e\u044f \u0434\u0430\u0442\u0430",      callback_data="rem_rp_custom_date")],
    ]
    if current and current != "once":
        btns.append([InlineKeyboardButton(text="\u274c \u0423\u0431\u0440\u0430\u0442\u044c \u043f\u043e\u0432\u0442\u043e\u0440", callback_data="rem_rp_once")])
    btns.append([InlineKeyboardButton(text="\u2190 \u041d\u0430\u0437\u0430\u0434",           callback_data="rem_back_to_confirm")])
    return InlineKeyboardMarkup(inline_keyboard=btns)


@router.callback_query(F.data == "rem_repeat_pick")
async def cb_rem_repeat_pick(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    await state.set_state(ReminderStates.waiting_for_repeat)
    data = await state.get_data()
    current = data.get("_rem_repeat", "once")
    try:
        await callback.message.edit_text(
            "🔔 <b>Повторение:</b>",
            reply_markup=_repeat_picker_keyboard(current),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            "🔔 <b>Повторение:</b>",
            reply_markup=_repeat_picker_keyboard(current),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("rem_rp_"))
async def cb_rem_rp_select(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    action = callback.data[len("rem_rp_"):]
    if action == "custom_date":
        await state.set_state(ReminderStates.waiting_for_weekdays)
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u2190 \u041d\u0430\u0437\u0430\u0434", callback_data="rem_repeat_pick")]
        ])
        txt = "\U0001f4c6 <b>\u0421\u0432\u043e\u044f \u0434\u0430\u0442\u0430 \u043f\u043e\u0432\u0442\u043e\u0440\u0435\u043d\u0438\u044f:</b>\n\n\u0412\u0432\u0435\u0434\u0438 \u0434\u0430\u0442\u0443 \u0432 \u0444\u043e\u0440\u043c\u0430\u0442\u0435 <code>\u0414\u0414.\u041c\u041c.\u0413\u0413</code>\n\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: <code>25.06.26</code>"
        try:
            await callback.message.edit_text(txt, reply_markup=cancel_kb, parse_mode="HTML")
        except Exception:
            await callback.message.answer(txt, reply_markup=cancel_kb, parse_mode="HTML")
        return
    if action == "custom":

        await state.set_state(ReminderStates.waiting_for_weekdays)
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Назад", callback_data="rem_repeat_pick")]
        ])
        txt = "📅 <b>В какие дни повторять?</b>\n\nНапиши дни недели, например:\n<code>пн ср пт</code>  или  <code>понедельник среда пятница</code>"
        try:
            await callback.message.edit_text(txt, reply_markup=cancel_kb, parse_mode="HTML")
        except Exception:
            await callback.message.answer(txt, reply_markup=cancel_kb, parse_mode="HTML")
        return
    repeat = action
    data = await state.get_data()
    _ttask_id_rps = data.get("_ttask_edit_id", "")
    _ttask_field_rps = data.get("_ttask_edit_field", "")
    if _ttask_id_rps and _ttask_field_rps == "repeat":
        await state.update_data(_rem_repeat=repeat)
        await cb_rem_rp_done(callback, state)
        return
    if not data.get("_rem_title") and not data.get("_rem_edit_id"):
        ws = store_get_workspace(user_id) or {}
        fallback = ws.get("_pending_reminder_create") or ws.get("_pending_reminder_edit") or {}
        if fallback:
            await state.update_data(**fallback)
            data = await state.get_data()
        else:
            await callback.answer("🌿 Данные потеряны. Начни заново.", show_alert=True)
            return
    await state.update_data(_rem_repeat=repeat)
    _ws1 = store_get_workspace(user_id) or {}
    for _k in ("_pending_reminder_create", "_pending_reminder_edit"):
        if _k in _ws1 and isinstance(_ws1[_k], dict):
            _ws1[_k]["_rem_repeat"] = repeat
    store_set_workspace(user_id, _ws1)
    await cb_rem_rp_done(callback, state)

@router.callback_query(F.data.startswith("rem_day_"))
async def cb_rem_day_toggle(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    day = callback.data[len("rem_day_"):]
    user_id = str(callback.from_user.id)
    data = await state.get_data()
    # Работает и при создании (_rem_title), и при редактировании (_rem_edit_id)
    if not data.get("_rem_title") and not data.get("_rem_edit_id"):
        ws = store_get_workspace(user_id) or {}
        fallback = ws.get("_pending_reminder_create") or ws.get("_pending_reminder_edit") or {}
        if fallback:
            await state.update_data(**fallback)
            data = await state.get_data()
        else:
            await callback.answer("🌿 Данные потеряны. Начни заново.", show_alert=True)
            return
    current = data.get("_rem_repeat", "once")
    
    days_en = ["mon","tue","wed","thu","fri","sat","sun"]
    custom_set = set()
    if current.startswith("custom_days:"):
        custom_set = set(current.split(":")[1].split(","))
    
    if day in custom_set:
        custom_set.discard(day)
    else:
        custom_set.add(day)
    
    if not custom_set:
        new_repeat = "once"
    elif custom_set == {"mon","tue","wed","thu","fri"}:
        new_repeat = "weekdays"
    elif custom_set == {"sat","sun"}:
        new_repeat = "weekends"
    else:
        sorted_days = sorted(custom_set, key=lambda d: days_en.index(d))
        new_repeat = "custom_days:" + ",".join(sorted_days)
    
    await state.update_data(_rem_repeat=new_repeat)
    # Синхронизируем repeat в workspace чтобы фоллбэк не затёр выбор
    _ws2 = store_get_workspace(user_id) or {}
    for _k in ("_pending_reminder_create", "_pending_reminder_edit"):
        if _k in _ws2 and isinstance(_ws2[_k], dict):
            _ws2[_k]["_rem_repeat"] = new_repeat
    store_set_workspace(user_id, _ws2)
    try:
        await callback.message.edit_text(
            "🔔 <b>Повторение:</b>",
            reply_markup=_repeat_picker_keyboard(new_repeat),
            parse_mode="HTML"
        )
    except Exception:
        pass

@router.message(StateFilter(ReminderStates.waiting_for_weekdays))
async def cb_rem_weekdays_input(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    raw = (message.text or "").strip()
    # ── task repeat context ──
    import re as _re_wd
    _data_wd = await state.get_data()
    _tt_id_wd = _data_wd.get("_ttask_edit_id", "")
    _tt_field_wd = _data_wd.get("_ttask_edit_field", "")
    if _tt_id_wd and _tt_field_wd == "repeat":
        _m_wd = _re_wd.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{2,4})$", raw)
        if _m_wd:
            _dd, _mm, _yy = _m_wd.groups()
            _yy = "20" + _yy if len(_yy) == 2 else _yy
            _repeat_wd = f"custom_date:{_yy}-{_mm.zfill(2)}-{_dd.zfill(2)}"
        else:
            _repeat_wd = _parse_weekdays(raw)
        if _repeat_wd == "once":
            await message.answer("\U0001f33f \u041d\u0435 \u0441\u043c\u043e\u0433 \u0440\u0430\u0437\u043e\u0431\u0440\u0430\u0442\u044c. \u0412\u0432\u0435\u0434\u0438 \u0434\u0430\u0442\u0443 (\u0414\u0414.\u041c\u041c.\u0413\u0413) \u0438\u043b\u0438 \u0434\u043d\u0438 \u043d\u0435\u0434\u0435\u043b\u0438 (\u043f\u043d \u0441\u0440 \u043f\u0442)")
            return
        _tasks_wd = store_get_tasks(user_id)
        _task_title_wd = "-"
        for _t_wd in _tasks_wd:
            if _t_wd.get("task_id") == _tt_id_wd:
                _t_wd["repeat"] = _repeat_wd
                _t_wd["updated"] = _today()
                _task_title_wd = _t_wd.get("title", "-")
        store_set_tasks(user_id, _tasks_wd)
        _fire_sync()
        await state.clear()
        await message.answer(
            f"\u270f\ufe0f <b>{_task_title_wd}</b>\n<i>\u2705 \u041f\u043e\u0432\u0442\u043e\u0440 \u2192 {_repeat_label(_repeat_wd)}</i>",
            reply_markup=get_task_edit_inline(user_id, _tt_id_wd),
            parse_mode="HTML"
        )
        return
    import re as _re_cd
    _m_cd = _re_cd.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{2,4})$", raw)
    if _m_cd:
        dd, mm, yy = _m_cd.groups()
        yy = "20" + yy if len(yy) == 2 else yy
        repeat = f"custom_date:{yy}-{mm.zfill(2)}-{dd.zfill(2)}"
    else:
        repeat = _parse_weekdays(raw)
        if repeat == "once" and not _m_cd:
            err_txt = "🌿 Не смог разобрать. Введи дни недели (пн ср пт) или дату (ДД.ММ.ГГ)"
            await message.answer(err_txt, parse_mode="HTML")
            return
    data = await state.get_data()
    if not data.get("_rem_title") and not data.get("_rem_edit_id"):
        ws = store_get_workspace(user_id) or {}
        fallback = ws.get("_pending_reminder_create") or ws.get("_pending_reminder_edit") or {}
        if fallback:
            await state.update_data(**fallback)
    await state.update_data(_rem_repeat=repeat)
    _ws = store_get_workspace(user_id) or {}
    for _k in ("_pending_reminder_create", "_pending_reminder_edit"):
        if _k in _ws and isinstance(_ws[_k], dict):
            _ws[_k]["_rem_repeat"] = repeat
    store_set_workspace(user_id, _ws)
    await state.set_state(ReminderStates.waiting_for_repeat)
    data2 = await state.get_data()
    title   = data2.get("_rem_title", "")
    dt_iso  = data2.get("_rem_dt", "")
    is_edit = data2.get("_rem_edit_id", "")
    # Если title есть а edit_id нет — это создание. Страхуемся от чужого edit_id.
    if title and not is_edit:
        await state.update_data(_rem_edit_id="")
        is_edit = ""
    rep_display = _repeat_label(repeat)
    dt_display  = dt_iso[:16].replace("T", " ") if dt_iso else "—"
    header = "✏️ <b>Редактирование</b>" if is_edit else "🔔 <b>Новое напоминание</b>"
    confirm_action = "rem_confirm_edit" if is_edit else "rem_confirm_create"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить повторение", callback_data="rem_repeat_pick")],
        [InlineKeyboardButton(text="✅ Готово", callback_data=confirm_action),
         InlineKeyboardButton(text="❌ Отмена", callback_data="menu_reminders_mgmt")],
    ])
    await message.answer(
        f"{header}\n\nНазвание: {title}\n📅 {dt_display}\n\nПовторение: {rep_display}",
        reply_markup=kb, parse_mode="HTML"
    )


@router.callback_query(F.data == "rem_rp_done")
async def cb_rem_rp_done(callback: CallbackQuery, state: FSMContext):
    """Return to confirmation screen with updated repeat. Works for both create and edit.
    Also supports task repeat editing via _ttask_edit_id."""
    await _safe_cb_answer(callback)
    data = await state.get_data()
    _ttask_id = data.get("_ttask_edit_id", "")
    _ttask_field = data.get("_ttask_edit_field", "")
    if _ttask_id and _ttask_field == "repeat":
        user_id = str(callback.from_user.id)
        repeat = data.get("_rem_repeat", "once")
        tasks = store_get_tasks(user_id)
        for t in tasks:
            if t.get("task_id") == _ttask_id:
                t["repeat"] = repeat if repeat != "once" else None
                t["updated"] = _today()
        store_set_tasks(user_id, tasks)
        _fire_sync()
        await state.clear()
        await callback.message.edit_text(
            f"✏️ <b>{next((t.get('title','-') for t in tasks if t.get('task_id')==_ttask_id), '-')}</b>\
<i>✅ Повтор → {_repeat_label(repeat)}</i>",
            reply_markup=get_task_edit_inline(user_id, _ttask_id),
            parse_mode="HTML"
        )
        return
    title = data.get("_rem_title", "")
    dt_iso = data.get("_rem_dt", "")
    repeat = data.get("_rem_repeat", "once")
    is_edit = data.get("_rem_edit_id", "")
    # Fallback: if FSM state lost (bot restart / timeout), recover from workspace
    # ВАЖНО: если title есть — это создание, _pending_reminder_edit не читаем
    _uid_done = str(callback.from_user.id)
    if not is_edit and not title:
        ws = store_get_workspace(_uid_done) or {}
        # Сначала пробуем create, потом edit — чтобы не подхватить чужой edit_id
        pending = ws.get("_pending_reminder_create") or ws.get("_pending_reminder_edit") or {}
        if pending:
            is_edit = pending.get("_rem_edit_id", "")
            title   = pending.get("_rem_title", "")
            dt_iso  = pending.get("_rem_dt", "")
            repeat  = pending.get("_rem_repeat", "once")
            await state.update_data(_rem_edit_id=is_edit, _rem_title=title, _rem_dt=dt_iso, _rem_repeat=repeat)
    elif title and not is_edit:
        # Есть title, нет edit_id — точно создание, сбрасываем edit_id на всякий случай
        await state.update_data(_rem_edit_id="")
    dt_display = dt_iso[:16].replace("T", " ")
    rep_display = _repeat_label(repeat)
    
    if is_edit:
        # Edit mode — immediately save repeat and return to reminder menu
        _uid_sv = str(callback.from_user.id)
        _rems_sv = store_get_reminders(_uid_sv)
        _rem_sv = next((r for r in _rems_sv if r["id"] == is_edit), None)
        if _rem_sv:
            _rem_sv["repeat"] = repeat
            store_set_reminders(_uid_sv, _rems_sv)
            _fire_sync()
        await state.clear()
        _rep_sv = _repeat_label(repeat)
        _dt_sv = (_rem_sv.get("datetime_iso","") if _rem_sv else dt_iso)[:16].replace("T"," ")
        _ttl_sv = _rem_sv.get("title","") if _rem_sv else title
        _sv_msg = ("✅ Повторение → " + _rep_sv
                   + "\n\n🔔 <b>" + _ttl_sv + "</b>"
                   + "\n📅 " + _dt_sv + "\n🔁 " + _rep_sv)
        try:
            await callback.message.edit_text(_sv_msg, reply_markup=get_reminder_edit_inline(is_edit), parse_mode="HTML")
        except Exception:
            await callback.message.answer(_sv_msg, reply_markup=get_reminder_edit_inline(is_edit), parse_mode="HTML")
        return
    else:
        confirm_action = "rem_confirm_create"
        cancel_action = "menu_reminders_mgmt"
        header = f"🔔 <b>Новое напоминание</b>"
    
    _rep_btn = "✏️ Изменить повторение" if repeat != "once" else "➕ Добавить повторение"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_rep_btn, callback_data="rem_repeat_pick")],
        [InlineKeyboardButton(text="✅ Готово", callback_data=confirm_action),
         InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_action)],
    ])
    try:
        await callback.message.edit_text(
            f"{header}\n\n"
            f"Название: {title}\n"
            f"📅 {dt_display}\n\n"
            f"Повторение: {rep_display}",
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            f"{header}\n\n"
            f"Название: {title}\n"
            f"📅 {dt_display}\n\n"
            f"Повторение: {rep_display}",
            reply_markup=kb,
            parse_mode="HTML"
        )

@router.callback_query(F.data == "rem_back_to_confirm")
async def cb_rem_back_to_confirm(callback: CallbackQuery, state: FSMContext):
    """Back from repeat picker to confirmation."""
    await cb_rem_rp_done(callback, state)

@router.callback_query(F.data == "rem_confirm_create")
async def cb_rem_confirm_create(callback: CallbackQuery, state: FSMContext):
    """Create the reminder and show result."""
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    data = await state.get_data()
    title = data.get("_rem_title", "")
    dt_iso = data.get("_rem_dt", "")
    repeat = data.get("_rem_repeat", "once")
    # Fallback: при создании читаем ТОЛЬКО _pending_reminder_create
    # _pending_reminder_edit не трогаем — там чужой edit_id
    if not title:
        ws_fb = store_get_workspace(user_id) or {}
        pending = ws_fb.get("_pending_reminder_create") or {}
        if pending:
            title   = pending.get("_rem_title", "")
            dt_iso  = pending.get("_rem_dt", "")
            repeat  = pending.get("_rem_repeat", "once")
    if not title:
        await callback.answer("Данные потеряны. Создайте напоминание заново.", show_alert=True)
        return
    
    reminders = store_get_reminders(user_id)
    if len(reminders) >= REMINDER_LIMIT:
        await callback.message.answer(f"⚠️ Лимит {REMINDER_LIMIT} напоминаний. Удали старые.")
        await state.clear()
        return
    elif len(reminders) >= REMINDER_LIMIT_SOFT:
        await callback.message.answer(f"⚠️ Почти лимит: {len(reminders)}/{REMINDER_LIMIT} напоминаний.")
    
    rid = _make_reminder_id(reminders)
    reminders.append({
        "id": rid, "title": title, "datetime_iso": dt_iso,
        "repeat": repeat, "active": True
    })
    store_set_reminders(user_id, reminders)
    # Clear workspace fallbacks
    ws = store_get_workspace(user_id) or {}
    ws.pop("_pending_reminder_edit", None)
    ws.pop("_pending_reminder_create", None)
    store_set_workspace(user_id, ws)
    _fire_sync()
    await state.clear()
    
    rep_display = _repeat_label(repeat)
    dt_display = dt_iso[:16].replace("T", " ")
    await callback.message.edit_text(
        f"✅ Напоминание создано:\n🔔 {title}\n📅 {dt_display} · {rep_display}",
        parse_mode="HTML"
    )
    # Show back to reminders
    reminders_upd = store_get_reminders(user_id)
    header = f"🔔 <b>Напоминания</b> ({len(reminders_upd)}/{REMINDER_LIMIT})"
    await callback.message.answer(header, reply_markup=get_reminders_mgmt_inline(reminders_upd), parse_mode="HTML")

@router.callback_query(F.data == "rem_confirm_edit")
async def cb_rem_confirm_edit(callback: CallbackQuery, state: FSMContext):
    """Save edited reminder."""
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    data = await state.get_data()
    edit_id = data.get("_rem_edit_id", "")
    repeat = data.get("_rem_repeat", "once")
    # Fallback: recover from workspace if FSM state lost
    if not edit_id:
        ws_fb = store_get_workspace(user_id) or {}
        pending = ws_fb.get("_pending_reminder_edit")
        if pending:
            edit_id = pending.get("_rem_edit_id", "")
            repeat  = pending.get("_rem_repeat", "once")
    if not edit_id:
        await callback.answer("Данные потеряны. Повторите редактирование.", show_alert=True)
        return
    
    reminders = store_get_reminders(user_id)
    rem = next((r for r in reminders if r["id"] == edit_id), None)
    if not rem:
        await callback.answer("Напоминание не найдено", show_alert=True)
        await state.clear()
        return
    
    rem["repeat"] = repeat
    store_set_reminders(user_id, reminders)
    # Clear workspace fallback
    ws = store_get_workspace(user_id) or {}
    ws.pop("_pending_reminder_edit", None)
    store_set_workspace(user_id, ws)
    _fire_sync()
    await state.clear()
    
    rep_display = _repeat_label(repeat)
    await callback.message.edit_text(
        f"✅ Повторение обновлено: {rep_display}",
        parse_mode="HTML"
    )
    reminders_upd = store_get_reminders(user_id)
    header = f"🔔 <b>Напоминания</b> ({len(reminders_upd)}/{REMINDER_LIMIT})"
    await callback.message.answer(header, reply_markup=get_reminders_mgmt_inline(reminders_upd), parse_mode="HTML")




async def cmd_achievements(message: Message):
    if not await _check_ready(message):
        return
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start")
        return
    ach_count = store_get_achievements_count(user_id)
    if not ach_count:
        await message.answer(
            "💎 Достижений пока нет.\n\nКаждое достижение добавляет слой к твоему резонансу.\n"
            "Просто напиши или скажи голосом: «добавь достижение — пробежал 5 км»",
            reply_markup=get_main_keyboard()
        )
        return

    text = f"<b>💎 Достижения · всего {ach_count}</b>"
    text += _build_sphere_stats(user_id, months=3)
    text += "\n\nДобавить: «добавь достижение — [что сделал]»"
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "add_achievement")
async def cb_add_achievement(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIRST
    if not is_authorized(str(callback.from_user.id)):
        await callback.message.answer("🌿 Используй /start")
        return
    await state.set_state(AchievementStates.waiting_for_category)
    await callback.message.answer(
        "💎 <b>Что произошло?</b>\n\nВыбери сферу:",
        reply_markup=get_achievement_category_keyboard()
    )

@router.callback_query(F.data.startswith("ach_cat_"))
async def ach_category(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIRST
    category = callback.data.replace("ach_cat_", "")
    await state.update_data(category=category)
    await state.set_state(AchievementStates.waiting_for_title)
    await callback.message.edit_text(
        "💎 Как назовёшь это достижение?\n\n<i>Одним предложением.</i>",
        reply_markup=None
    )

@router.message(StateFilter(AchievementStates.waiting_for_title))
async def ach_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title or len(title) < 2:
        await message.answer("💎 Напиши, что именно сделано (минимум 2 символа).")
        return
    sphere = _classify_sphere(title, "")
    bonus = 3
    user_id = str(message.from_user.id)
    icon = LIFE_AREA_ICONS.get(sphere, "🌱")
    sname = {"health":"Здоровье","creativity":"Творчество","work":"Работа","connections":"Связи","growth":"Рост"}.get(sphere, sphere)
    store_add_sphere_resonance(user_id, sphere, bonus)
    _update_sphere_history(user_id, sphere, achievement=True, resonance_delta=bonus)
    store_increment_achievements(user_id)
    gardener = store_get_profile(user_id)
    if gardener:
        g = dict(gardener)
        prev_res = g.get("resonance_level", 13)
        new_res = min(100, prev_res + bonus)
        g["resonance_level"] = new_res
        g["updated"] = _today()
        g = _add_growth_history_entry(g, new_res, user_id)
        store_set_profile(user_id, g)
        _invalidate_auth_cache(user_id)
    _fire_sync()
    await state.clear()
    text = (
        f"{icon} <b>Достижение зафиксировано!</b>\n\n"
        f"«{title}»\n"
        f"Сфера: {icon} {sname} · +{bonus} к резонансу"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад к достижениям", callback_data="profile_achievements")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(StateFilter(AchievementStates.waiting_for_description))
async def ach_description(message: Message, state: FSMContext):
    desc = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(description=desc)
    await state.set_state(AchievementStates.waiting_for_bonus)
    await message.answer("🔮 Насколько это важно для тебя? Оцени от 1 до 10.\n\n<i>Это бонус к резонансу.</i>")

@router.message(StateFilter(AchievementStates.waiting_for_bonus))
async def ach_bonus(message: Message, state: FSMContext):
    try:
        bonus = max(1, min(10, int(message.text.strip())))
    except Exception:
        bonus = 3

    data = await state.get_data()
    category = data.get("category", "other")
    icon = LIFE_AREA_ICONS.get(category, "🌱")

    user_id = str(message.from_user.id)

    # Update gardener resonance
    gardener = store_get_profile(user_id)
    if gardener:
        g = dict(gardener)
        current_res = g.get("resonance_level", 13)
        new_res = min(100, current_res + bonus)
        g["resonance_level"] = new_res
        g["updated"] = _today()
        g = _add_growth_history_entry(g, new_res)
        store_set_profile(user_id, g)
        _invalidate_auth_cache(user_id)

    # Sync to GitHub in background
    _fire_sync()

    await state.clear()
    await message.answer(
        f"{icon} <b>Достижение зафиксировано!</b>\n\n"
        f"<b>{data.get('title','')}</b>\n"
        f"🔮 +{bonus} к резонансу\n\n"
        f"<i>Новый слой добавлен 🌱</i>",
        reply_markup=get_main_keyboard()
    )

@router.callback_query(F.data == "cancel_achievement")
async def cb_cancel_achievement(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIRST
    await state.clear()
    try:
        await callback.message.edit_text("❌ Отменено.")
    except Exception:
        pass

# ─── /tasks ───────────────────────────────────────────────────────────────────

@router.message(Command("tasks"))
@router.message(F.text == "🌀 Задачи")




async def _create_reminder_atomic(user_id: str, message: Message,
                                   title: str, datetime_str: str = None,
                                   repeat: str = "once") -> dict:
    """Create a reminder instantly from chat/voice without FSM.
    Cleans title from time phrases, parses natural-language datetime,
    adds timezone offset from gardener settings. Returns created reminder dict."""
    import re as _re_rem
    from datetime import datetime as _dt_rem, timedelta as _td_rem
    from zoneinfo import ZoneInfo as _ZI_rem

    reminders = store_get_reminders(user_id)
    if len(reminders) >= REMINDER_LIMIT:
        return {}

    # ── 1. Clean title: remove time phrases ────────────────────────────────
    title = title.strip()
    # Remove trailing time patterns: "в 9", "в 21:00", "завтра в 9", "сегодня в 21:00"
    title = _re_rem.sub(
        r'\s+(завтра|сегодня|послезавтра|через\s+\d+\s+(минут|час|часа|часов|дня|дней|неделю|недели))\s*'
        r'(в\s+\d{1,2}(:\d{2})?\s*)?$',
        '', title, flags=_re_rem.IGNORECASE
    ).strip()
    # Remove standalone time: "в 13:00", "в 9"
    title = _re_rem.sub(r'\s+в\s+\d{1,2}(:\d{2})?\s*$', '', title, flags=_re_rem.IGNORECASE).strip()

    if not title or len(title) < 2:
        return {}

    # ── 2. Resolve timezone ────────────────────────────────────────────────
    profile = store_get_profile(user_id) or {}
    tz_name = profile.get("companion_settings", {}).get("timezone", "Europe/Moscow")
    try:
        tz = _ZI_rem(tz_name)
    except Exception:
        tz = _ZI_rem("Europe/Moscow")
    now = _dt_rem.now(tz)
    today_str = now.strftime("%Y-%m-%d")

    # ── 3. Parse datetime_str ──────────────────────────────────────────────
    dt_iso = None

    if datetime_str and datetime_str not in ("null", "none", ""):
        ds = datetime_str.strip()
        # Already ISO with timezone offset: "2026-05-05T13:00+05:00"
        if _re_rem.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}[+-]\d{2}:\d{2}$', ds):
            dt_iso = ds
        # ISO without offset: "2026-05-05T13:00" → add offset
        elif _re_rem.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$', ds):
            offset = now.strftime("%z")
            offset_formatted = offset[:3] + ":" + offset[3:] if offset else "+00:00"
            dt_iso = f"{ds}{offset_formatted}"
        # Relative time: "через 30 минут", "через 2 часа"
        elif (m := _re_rem.match(r'через\s+(\d+)\s+(минут|час|часа|часов|дня|дней|недел[юиь])', ds.lower())):
            n = int(m.group(1))
            unit = m.group(2)
            if unit.startswith("минут"):
                target = now + _td_rem(minutes=n)
            elif unit.startswith("час"):
                target = now + _td_rem(hours=n)
            elif unit.startswith("дн"):
                target = now + _td_rem(days=n)
            elif unit.startswith("недел"):
                target = now + _td_rem(weeks=n)
            else:
                target = now + _td_rem(minutes=30)
            offset = target.strftime("%z")
            offset_formatted = offset[:3] + ":" + offset[3:] if offset else "+00:00"
            dt_iso = target.strftime(f"%Y-%m-%dT%H:%M{offset_formatted}")
        # "сегодня в 21:00", "завтра в 9"
        elif (m := _re_rem.match(r'(сегодня|завтра|послезавтра)\s+в\s+(\d{1,2})(?::(\d{2}))?', ds.lower())):
            day_map = {"сегодня": 0, "завтра": 1, "послезавтра": 2}
            day_offset = day_map.get(m.group(1), 0)
            hh = int(m.group(2))
            mm = int(m.group(3)) if m.group(3) else 0
            target = (now + _td_rem(days=day_offset)).replace(hour=hh, minute=mm, second=0, microsecond=0)
            offset = target.strftime("%z")
            offset_formatted = offset[:3] + ":" + offset[3:] if offset else "+00:00"
            dt_iso = target.strftime(f"%Y-%m-%dT%H:%M{offset_formatted}")
        # "в 21:00", "в 9" (today)
        elif (m := _re_rem.match(r'в\s+(\d{1,2})(?::(\d{2}))?', ds.lower())):
            hh = int(m.group(1))
            mm = int(m.group(2)) if m.group(2) else 0
            target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if target <= now:
                target += _td_rem(days=1)
            offset = target.strftime("%z")
            offset_formatted = offset[:3] + ":" + offset[3:] if offset else "+00:00"
            dt_iso = target.strftime(f"%Y-%m-%dT%H:%M{offset_formatted}")

    # Fallback: if no datetime parsed, set to tomorrow 9:00
    if not dt_iso:
        target = (now + _td_rem(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        offset = target.strftime("%z")
        offset_formatted = offset[:3] + ":" + offset[3:] if offset else "+00:00"
        dt_iso = target.strftime(f"%Y-%m-%dT%H:%M{offset_formatted}")

    # ── 4. Validate repeat ─────────────────────────────────────────────────
    if repeat not in ("once", "daily", "weekdays"):
        repeat = "once"

    # ── 5. Create reminder ─────────────────────────────────────────────────
    rid = _make_reminder_id(reminders)
    new_rem = {
        "id": rid,
        "title": title,
        "datetime_iso": dt_iso,
        "repeat": repeat,
        "active": True
    }
    reminders.append(new_rem)
    store_set_reminders(user_id, reminders)
    _fire_sync()
    return new_rem