# -*- coding: utf-8 -*-
"""
handlers/tasks.py — Task Handlers
All handlers for tasks: callbacks, FSM, edit, groups, atomic creation.

Part of: honeycombs/fruits/gentle_companion/
Phase: 6 (depends on config.py, store.py, helpers.py, ui.py, sr_memory.py)

Key handlers:
  cb_ttask_place_cb, cb_tasks_mgmt_v2, cb_tgroup_*  — group/task navigation
  cb_ttask_done   — task completion + resonance + synthesis trigger
  cb_ttask_edit, cb_ttask_edit_field  — inline edit
  cb_ttask_delete, cb_ttask_create    — delete/create via UI
  cb_tgroup_create, cb_tgroup_newtask — group management
  cb_task_edit_start, tedit_*         — legacy edit flow
  task_title, task_deadline_cb, task_repeat_cb, task_label_cb — FSM steps
  _ask_repeat_task, _ask_group, _show_task_confirm, confirm_task
  cmd_tasks, cmd_addtask, cmd_done, cmd_groups, cmd_newgroup, cmd_archive
  _filter_tasks_by_period, _detect_task_period, _format_tasks_labels
  _create_task_atomic  — voice/chat task creation without FSM
"""

@router.callback_query(F.data.startswith("plc_"), StateFilter(TaskEditStates.editing_place))
async def cb_ttask_place_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    data = await state.get_data()
    tid = data.get("_ttask_edit_id", "")
    raw = callback.data[4:]
    tasks = store_get_tasks(user_id)
    task_title = next((t.get("title", "-") for t in tasks if t.get("task_id") == tid), "-")
    gid = raw[4:] if raw.startswith("grp|") else None
    if gid is None:
        await callback.answer("Неверный формат", show_alert=True)
        return
    if gid == "__nogroup__":
        label_id, label_name = None, ""
    else:
        gs = store_get_groups(user_id).get("groups", [])
        g = next((x for x in gs if x["id"] == gid), None)
        label_id, label_name = gid, (g["name"] if g else "")
    for t in tasks:
        if t.get("task_id") == tid:
            t["label_id"] = label_id
            t["label_name"] = label_name
            t["updated"] = _today()
    store_set_tasks(user_id, tasks)
    place_display = label_name or "\u0411\u0435\u0437 \u0433\u0440\u0443\u043f\u043f\u044b"
    _fire_sync()
    await state.clear()
    await callback.message.edit_text(
        f"\u270f\ufe0f <b>{task_title}</b>\n<i>\u2705 \u041c\u0435\u0441\u0442\u043e \u2192 {place_display}</i>",
        reply_markup=get_task_edit_inline(user_id, tid),
        parse_mode="HTML"
    )



@router.callback_query(F.data == "menu_tasks_mgmt_v2")
async def cb_tasks_mgmt_v2(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    if not is_authorized(user_id):
        await callback.message.answer("\U0001f331 Используй /start")
        return
    groups_data = store_get_groups(user_id).get("groups", [])
    all_tasks = store_get_tasks(user_id)
    active = [t for t in all_tasks if t.get("status") != "completed"]
    header = f"\U0001f5c2 <b>\u0417\u0430\u0434\u0430\u0447\u0438</b> \u00b7 {len(groups_data)} \u0433\u0440\u0443\u043f\u043f \u00b7 {len(active)} \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445"
    try:
        await callback.message.edit_text(header, reply_markup=get_groups_list_inline(user_id))
    except Exception:
        await callback.message.answer(header, reply_markup=get_groups_list_inline(user_id))

@router.callback_query(F.data == "tgroup_back_to_list")
async def cb_tgroup_back_to_list(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    groups_data = store_get_groups(user_id).get("groups", [])
    all_tasks = store_get_tasks(user_id)
    active = [t for t in all_tasks if t.get("status") != "completed"]
    header = f"\U0001f5c2 <b>\u0417\u0430\u0434\u0430\u0447\u0438</b> \u00b7 {len(groups_data)} \u0433\u0440\u0443\u043f\u043f \u00b7 {len(active)} \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445"
    try:
        await callback.message.edit_text(header, reply_markup=get_groups_list_inline(user_id))
    except Exception:
        await callback.message.answer(header, reply_markup=get_groups_list_inline(user_id))

@router.callback_query(F.data.startswith("tgroup_open|"))
async def cb_tgroup_open(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    group_id = callback.data.split("|")[1]
    all_tasks = store_get_tasks(user_id)
    groups_data = store_get_groups(user_id).get("groups", [])
    if group_id == "__nogroup__":
        group_name = "Без группы"
        tasks = [t for t in all_tasks if t.get("status") != "completed" and not t.get("label_name")]
    else:
        group = next((g for g in groups_data if g["id"] == group_id), None)
        group_name = group["name"] if group else "Группа"
        tasks = [t for t in all_tasks if t.get("status") != "completed" and t.get("label_id") == group_id]
    header = f"\U0001f5c2 <b>{group_name}</b> · {len(tasks)} задач"
    try:
        await callback.message.edit_text(
            header, reply_markup=get_tasks_in_group_inline(user_id, group_id), parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            header, reply_markup=get_tasks_in_group_inline(user_id, group_id), parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("ttask_done|"))
async def cb_ttask_done(callback: CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    task_id = callback.data.split("|")[1]
    tasks = store_get_tasks(user_id)
    task = next((t for t in tasks if t.get("task_id") == task_id), None)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    group_id = task.get("label_id") or "__nogroup__"
    repeat = task.get("repeat")
    tasks = [t for t in tasks if t.get("task_id") != task_id]
    new_task_created = False
    if repeat and repeat != "once":
        from datetime import datetime as _dt_rep, timedelta as _td_rep
        from zoneinfo import ZoneInfo as _ZI_rep
        # P-61: gardener timezone so deadline is correct locally
        _prof_rep = store_get_profile(user_id) or {}
        _tz_rep_name = _prof_rep.get("companion_settings", {}).get("timezone", "Europe/Moscow")
        try:
            _tz_rep = _ZI_rep(_tz_rep_name)
        except Exception:
            _tz_rep = _ZI_rep("Europe/Moscow")
        _now_rep = _dt_rep.now(_tz_rep)
        today = _now_rep.strftime("%Y-%m-%d")
        new_dl = None
        if repeat == "daily":
            new_dl = (_now_rep + _td_rep(days=1)).strftime("%Y-%m-%d")
        elif repeat == "weekly":
            new_dl = (_now_rep + _td_rep(days=7)).strftime("%Y-%m-%d")
        elif repeat == "weekdays":
            d = _now_rep + _td_rep(days=1)
            while d.weekday() >= 5:
                d += _td_rep(days=1)
            new_dl = d.strftime("%Y-%m-%d")
        elif repeat == "monthly":
            new_dl = (_now_rep + _td_rep(days=30)).strftime("%Y-%m-%d")
        elif repeat == "yearly":
            new_dl = (_now_rep + _td_rep(days=365)).strftime("%Y-%m-%d")
        elif repeat.startswith("custom_days:"):
            days_str = repeat.split(":")[1]
            days_list = days_str.split(",")
            day_names = ["mon","tue","wed","thu","fri","sat","sun"]
            d = _now_rep + _td_rep(days=1)
            while day_names[d.weekday()] not in days_list:
                d += _td_rep(days=1)
            new_dl = d.strftime("%Y-%m-%d")
        elif repeat.startswith("custom_date:"):
            date_str = repeat.split(":")[1]
            try:
                dt = _dt_rep.strptime(date_str, "%Y-%m-%d")
                dt = dt.replace(year=dt.year + 1)
                new_dl = dt.strftime("%Y-%m-%d")
            except Exception:
                new_dl = (_dt_rep.now() + _td_rep(days=365)).strftime("%Y-%m-%d")
        if new_dl:
            import uuid
            new_tid = "task_" + datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]
            new_task = {
                "task_id": new_tid,
                "title": task.get("title",""),
                "status": "todo",
                "label_id": task.get("label_id"),
                "label_name": task.get("label_name",""),
                "life_area": task.get("life_area","work"),
                "priority": calculate_priority(new_dl),
                "deadline": new_dl,
                "reminder": task.get("reminder"),
                "repeat": repeat,
                "created": _today(),
                "updated": _today(),
                "completed": None,
                "notes": ""
            }
            tasks.append(new_task)
            new_task_created = True
    store_set_tasks(user_id, tasks)
    store_increment_achievements(user_id)
    sphere = _classify_sphere(task.get("title",""), task.get("label_name",""))
    store_add_sphere_resonance(user_id, sphere, 2)
    _update_sphere_history(user_id, sphere, task=True, resonance_delta=2)
    _update_deep_profile(user_id)
    _fire_sync()
    # P-25: sphere feedback message
    _sphere_labels = {
        "health": "🌿 Здоровье",
        "creativity": "🎨 Творчество",
        "work": "⚡ Работа",
        "connections": "💫 Связи",
        "growth": "🌱 Рост",
    }
    _sr_after = store_get_sphere_resonance(user_id)
    _sphere_val = _sr_after.get(sphere, 0)
    _sphere_lbl = _sphere_labels.get(sphere, "🌱 Рост")
    _done_title = task.get("title", "")[:40]
    _done_msg = (
        f"✅ <b>{_done_title}</b> — закрыта\n"
        f"{_sphere_lbl} +2% → {_sphere_val}%"
    )
    await callback.answer("")
    try:
        await callback.message.answer(_done_msg, parse_mode="HTML")
    except Exception:
        pass
    all_tasks2 = store_get_tasks(user_id)
    tasks_in_group = [t for t in all_tasks2 if t.get("status") != "completed" and (
        (t.get("label_id") == group_id) if group_id != "__nogroup__" else not t.get("label_name")
    )]
    group_name2 = "Без группы" if group_id == "__nogroup__" else next(
        (g["name"] for g in store_get_groups(user_id).get("groups", []) if g["id"] == group_id), "Группа"
    )
    repeat_note = " \U0001f501 Новая задача создана" if new_task_created else ""
    header = f"\U0001f5c2 <b>{group_name2}</b> · {len(tasks_in_group)} задач{repeat_note}"
    try:
        await callback.message.edit_text(
            header,
            reply_markup=get_tasks_in_group_inline(user_id, group_id),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            header,
            reply_markup=get_tasks_in_group_inline(user_id, group_id),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("ttask_edit|"))
async def cb_ttask_edit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    task_id = callback.data.split("|")[1]
    tasks = store_get_tasks(user_id)
    task = next((t for t in tasks if t.get("task_id") == task_id), None)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    header = f"\u270f\ufe0f <b>{task.get('title','-')}</b>"
    try:
        await callback.message.edit_text(
            header,
            reply_markup=get_task_edit_inline(user_id, task_id),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            header,
            reply_markup=get_task_edit_inline(user_id, task_id),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("ttask_edit_field|"))
async def cb_ttask_edit_field(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    parts = callback.data.split("|")
    task_id = parts[1]
    field = parts[2]
    tasks = store_get_tasks(user_id)
    task = next((t for t in tasks if t.get("task_id") == task_id), None)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    if field == "title":
        await state.update_data(_ttask_edit_id=task_id, _ttask_edit_field="title")
        await state.set_state(TaskEditStates.editing_title)
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u2190 Назад", callback_data=f"ttask_edit|{task_id}")]
        ])
        try:
            await callback.message.edit_text(
                f"\u270f\ufe0f Новое название для «{task.get('title','')}»:",
                reply_markup=cancel_kb
            )
        except Exception:
            await callback.message.answer(
                f"\u270f\ufe0f Новое название для «{task.get('title','')}»:",
                reply_markup=cancel_kb
            )
    elif field == "deadline":
        await state.update_data(_ttask_edit_id=task_id, _ttask_edit_field="deadline")
        await state.set_state(TaskEditStates.editing_deadline)
        try:
            await callback.message.edit_text(
                "\U0001f4c5 Выбери новый дедлайн:",
                reply_markup=get_deadline_keyboard()
            )
        except Exception:
            await callback.message.answer(
                "\U0001f4c5 Выбери новый дедлайн:",
                reply_markup=get_deadline_keyboard()
            )
    elif field == "place":
        await state.update_data(_ttask_edit_id=task_id, _ttask_edit_field="place")
        await state.set_state(TaskEditStates.editing_place)
        try:
            await callback.message.edit_text(
                "\U0001f4cc \u041a\u0443\u0434\u0430 \u043f\u043e\u043c\u0435\u0441\u0442\u0438\u0442\u044c \u0437\u0430\u0434\u0430\u0447\u0443?",
                reply_markup=get_place_keyboard(user_id, task_id)
            )
        except Exception:
            await callback.message.answer(
                "\U0001f4cc \u041a\u0443\u0434\u0430 \u043f\u043e\u043c\u0435\u0441\u0442\u0438\u0442\u044c \u0437\u0430\u0434\u0430\u0447\u0443?",
                reply_markup=get_place_keyboard(user_id, task_id)
            )
    elif field == "repeat":
        current = task.get("repeat", "once")
        await state.update_data(_ttask_edit_id=task_id, _ttask_edit_field="repeat", _rem_repeat=current)
        await state.set_state(ReminderStates.waiting_for_repeat)
        try:
            await callback.message.edit_text(
                "\U0001f501 <b>Повторение:</b>",
                reply_markup=_repeat_picker_keyboard(current),
                parse_mode="HTML"
            )
        except Exception:
            await callback.message.answer(
                "\U0001f501 <b>Повторение:</b>",
                reply_markup=_repeat_picker_keyboard(current),
                parse_mode="HTML"
            )
    elif field == "reminder":
        # Создаём напоминание мгновенно (или находим существующее)
        # и открываем экран выбора времени
        import uuid as _uuid_tr
        await state.update_data(_ttask_edit_id=task_id, _ttask_edit_field="reminder")
        await state.set_state(TaskEditStates.editing_reminder)
        # Сохраняем task_id в стейт для tedit_reminder_cb
        await state.update_data(edit_task_id=task_id)
        deadline = task.get("deadline")
        rem_label = task.get("reminder") or "нет"
        header = (
            f"🔔 <b>Напоминание для «{task.get('title', '')[:30]}»</b>\n"
            f"Сейчас: {rem_label}\n"
            f"Выбери время:"
        )
        back_kb_row = [InlineKeyboardButton(
            text="← Назад к задаче",
            callback_data=f"ttask_edit|{task_id}"
        )]
        from aiogram.types import InlineKeyboardMarkup as _IKM_tr
        kb = get_reminder_keyboard(deadline)
        # Добавляем кнопку «Убрать» если напоминание уже есть
        if task.get("reminder"):
            extra_rows = [[InlineKeyboardButton(
                text="🗑 Убрать напоминание",
                callback_data=f"ttask_rem_clear|{task_id}"
            )], back_kb_row]
        else:
            extra_rows = [back_kb_row]
        new_kb = _IKM_tr(
            inline_keyboard=kb.inline_keyboard[:-1] + extra_rows
        )
        try:
            await callback.message.edit_text(header, reply_markup=new_kb, parse_mode="HTML")
        except Exception:
            await callback.message.answer(header, reply_markup=new_kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("dl_"), StateFilter(TaskEditStates.editing_deadline))
async def ttask_deadline_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    data = await state.get_data()
    tid = data.get("_ttask_edit_id") or data.get("edit_task_id", "")
    val = callback.data[3:]
    if val == "custom":
        await state.update_data(_ttask_edit_id=tid)
        await state.set_state(TaskEditStates.waiting_for_custom_deadline)
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u2190 Назад", callback_data=f"ttask_edit|{tid}")]
        ])
        try:
            await callback.message.edit_text(
                "\u270f\ufe0f Введи свою дату: <code>ДД.ММ</code> или <code>ДД.ММ.ГГ</code>",
                parse_mode="HTML", reply_markup=cancel_kb
            )
        except Exception:
            await callback.message.answer(
                "\u270f\ufe0f Введи свою дату: <code>ДД.ММ</code> или <code>ДД.ММ.ГГ</code>",
                parse_mode="HTML", reply_markup=cancel_kb
            )
        return
    deadline = None if val == "skip" else val
    tasks = store_get_tasks(user_id)
    for t in tasks:
        if t.get("task_id") == tid:
            t["deadline"] = deadline
            t["updated"] = _today()
    store_set_tasks(user_id, tasks)
    _fire_sync()
    await state.clear()
    dl_str = deadline or "убран"
    group_id = next((t.get("label_id") or "__nogroup__" for t in tasks if t.get("task_id") == tid), "__nogroup__")
    group_name = "Без группы" if group_id == "__nogroup__" else next(
        (g["name"] for g in store_get_groups(user_id).get("groups", []) if g["id"] == group_id), "Группа"
    )
    tasks_in_group = [t for t in tasks if t.get("status") != "completed" and (
        (t.get("label_id") == group_id) if group_id != "__nogroup__" else not t.get("label_name")
    )]
    await callback.message.edit_text(
        f"\U0001f5c2 <b>{group_name}</b> · {len(tasks_in_group)} задач\\n<i>\u2705 Дедлайн → {dl_str}</i>",
        reply_markup=get_tasks_in_group_inline(user_id, group_id),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("lbl_"), StateFilter(TaskEditStates.editing_group))
async def ttask_group_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    data = await state.get_data()
    tid = data.get("_ttask_edit_id") or data.get("edit_task_id", "")
    val = callback.data[4:]
    if val in ("new", "skip"):
        label_id, label_name = None, ""
    else:
        labels = store_get_groups(user_id).get("groups", [])
        lb = next((l for l in labels if l["id"] == val), None)
        label_id = val
        label_name = lb["name"] if lb else ""
    tasks = store_get_tasks(user_id)
    for t in tasks:
        if t.get("task_id") == tid:
            t["label_id"] = label_id
            t["label_name"] = label_name
            t["updated"] = _today()
    store_set_tasks(user_id, tasks)
    _fire_sync()
    await state.clear()
    await callback.message.edit_text(
        f"\u270f\ufe0f <b>{next((t.get('title','-') for t in tasks if t.get('task_id')==tid), '-')}</b>\\n<i>\u2705 Группа → {label_name or 'Без группы'}</i>",
        reply_markup=get_task_edit_inline(user_id, tid),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("ttask_delete|"))
async def cb_ttask_delete(callback: CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    task_id = callback.data.split("|")[1]
    tasks = store_get_tasks(user_id)
    task = next((t for t in tasks if t.get("task_id") == task_id), None)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    group_id = task.get("label_id") or "__nogroup__"
    tasks = [t for t in tasks if t.get("task_id") != task_id]
    store_set_tasks(user_id, tasks)
    # Удалить связанное напоминание если есть
    _rems_del = store_get_reminders(user_id)
    _rems_del = [r for r in _rems_del if r.get("task_id") != task_id]
    store_set_reminders(user_id, _rems_del)
    _fire_sync()
    await callback.answer("\U0001f5d1 Удалено")
    tasks_in_group = [t for t in tasks if t.get("status") != "completed" and (
        (t.get("label_id") == group_id) if group_id != "__nogroup__" else not t.get("label_name")
    )]
    group_name = "Без группы" if group_id == "__nogroup__" else next(
        (g["name"] for g in store_get_groups(user_id).get("groups", []) if g["id"] == group_id), "Группа"
    )
    header = f"\U0001f5c2 <b>{group_name}</b> · {len(tasks_in_group)} задач"
    try:
        await callback.message.edit_text(
            header,
            reply_markup=get_tasks_in_group_inline(user_id, group_id),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            header,
            reply_markup=get_tasks_in_group_inline(user_id, group_id),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("ttask_create|"))
async def cb_ttask_create(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    group_id = callback.data.split("|")[1]
    # __new__ = создание с главного экрана без привязки к группе
    if group_id == "__new__":
        await _start_task_flow(callback.message, state)
        return
    if group_id == "__nogroup__":
        label_id = None
        label_name = ""
        group_display = "Без группы"
    else:
        groups = store_get_groups(user_id).get("groups", [])
        g = next((x for x in groups if x["id"] == group_id), None)
        label_id = group_id
        label_name = g["name"] if g else ""
        group_display = label_name
    await state.update_data(
        _ttask_create_group=group_id,
        _ttask_create_label_id=label_id,
        _ttask_create_label_name=label_name
    )
    await state.set_state(TaskStates.waiting_for_title)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2190 Назад", callback_data=f"tgroup_open|{group_id}")]
    ])
    await callback.message.edit_text(
        f"\u2795 <b>Новая задача в «{group_display}»</b>\n\nВведи название:",
        reply_markup=cancel_kb, parse_mode="HTML"
    )

@router.callback_query(F.data == "tgroup_create")
async def cb_tgroup_create(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    groups = store_get_groups(user_id).get("groups", [])
    if len(groups) >= LABEL_LIMIT_HARD:
        await callback.answer(f"\u26a0\ufe0f Лимит групп: {LABEL_LIMIT_HARD}", show_alert=True)
        return
    await state.set_state(TaskStates.waiting_for_new_group)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2190 Назад", callback_data="tgroup_back_to_list")]
    ])
    await callback.message.edit_text(
        "\u2795 <b>Новая группа</b>\n\nВведи название:",
        reply_markup=cancel_kb, parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("tgroup_newtask|"))
async def cb_tgroup_newtask(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    group_id = callback.data.split("|")[1]
    groups = store_get_groups(user_id).get("groups", [])
    g = next((x for x in groups if x["id"] == group_id), None)
    label_id = group_id if group_id != "__nogroup__" else None
    label_name = g["name"] if g else ""
    group_display = label_name if label_name else "Без группы"
    await state.update_data(
        _ttask_create_group=group_id,
        _ttask_create_label_id=label_id,
        _ttask_create_label_name=label_name
    )
    await state.set_state(TaskStates.waiting_for_title)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data=f"tgroup_open|{group_id}")]
    ])
    try:
        await callback.message.edit_text(
            f"➕ <b>Новая задача в «{group_display}»</b>\n\nВведи название:",
            reply_markup=cancel_kb, parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            f"➕ Новая задача в «{group_display}» — введи название:",
            reply_markup=cancel_kb
        )


@router.callback_query(F.data.startswith("tgroup_edit|"))
async def cb_tgroup_edit_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    group_id = callback.data.split("|")[1]
    groups = store_get_groups(user_id).get("groups", [])
    g = next((x for x in groups if x["id"] == group_id), None)
    if not g:
        await callback.answer("Группа не найдена", show_alert=True)
        return
    await state.set_state(TaskStates.waiting_for_new_group)
    await state.update_data(_tgroup_edit_id=group_id)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2190 Назад", callback_data="tgroup_back_to_list")]
    ])
    await callback.message.edit_text(
        f"\u270f\ufe0f Новое название для «{g['name']}»:",
        reply_markup=cancel_kb
    )

@router.callback_query(F.data.startswith("tgroup_delete|"))
async def cb_tgroup_delete(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    group_id = callback.data.split("|")[1]
    groups = store_get_groups(user_id).get("groups", [])
    g = next((x for x in groups if x["id"] == group_id), None)
    if not g:
        await callback.answer("Группа не найдена", show_alert=True)
        return
    tasks = store_get_tasks(user_id)
    count = len([t for t in tasks if t.get("label_id") == group_id])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2705 Да, удалить", callback_data=f"tgroup_delete_confirm|{group_id}")],
        [InlineKeyboardButton(text="\u2190 Назад", callback_data="tgroup_back_to_list")],
    ])
    await callback.message.edit_text(
        f"\U0001f5d1 <b>Удалить группу «{g['name']}»?</b>\n\n{count} задач будут удалены",
        reply_markup=kb, parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("tgroup_delete_confirm|"))
async def cb_tgroup_delete_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    group_id = callback.data.split("|")[1]
    groups_data = store_get_groups(user_id)
    groups = groups_data.get("groups", [])
    g = next((x for x in groups if x["id"] == group_id), None)
    if g:
        tasks = store_get_tasks(user_id)
        tasks = [t for t in tasks if t.get("label_id") != group_id]
        store_set_tasks(user_id, tasks)
        groups_data["groups"] = [x for x in groups if x["id"] != group_id]
        store_set_groups(user_id, groups_data)
        _fire_sync()
    groups_data2 = store_get_groups(user_id).get("groups", [])
    all_tasks2 = store_get_tasks(user_id)
    active2 = [t for t in all_tasks2 if t.get("status") != "completed"]
    header = f"\U0001f5c2 <b>\u0417\u0430\u0434\u0430\u0447\u0438</b> \u00b7 {len(groups_data2)} \u0433\u0440\u0443\u043f\u043f \u00b7 {len(active2)} \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445"
    try:
        await callback.message.edit_text(header, reply_markup=get_groups_list_inline(user_id))
    except Exception:
        await callback.message.answer(header, reply_markup=get_groups_list_inline(user_id))

# ttask_noop removed — tasks are now direct edit buttons

# ─── Checklist keyboards ──────────────────────────────────────────────────────

def _make_checklist_id(title: str, existing: list) -> str:
    """Generate unique checklist id."""
    base = "cl_" + "".join(c for c in title.lower()[:8] if c.isalnum())
    ids  = {c["id"] for c in existing}
    candidate = base
    i = 1
    while candidate in ids:
        candidate = f"{base}_{i}"
        i += 1
    return candidate

def _checklist_progress(checklist: dict) -> str:
    """Return '2/5' progress string."""
    items = checklist.get("items", [])
    done  = sum(1 for it in items if it.get("done"))
    return f"{done}/{len(items)}"


@router.callback_query(F.data == "menu_tasks_mgmt")
async def cb_tasks_mgmt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    tasks   = store_get_tasks(user_id)
    active  = [t for t in tasks if t.get("status") != "completed"]
    header  = f"🌀 <b>Задачи</b> ({len(active)}/{TASK_LIMIT_HARD})"
    try:
        await callback.message.edit_text(header, reply_markup=get_tasks_mgmt_inline(tasks))
    except Exception:
        await callback.message.answer(header, reply_markup=get_tasks_mgmt_inline(tasks))

@router.callback_query(F.data == "menu_labels_mgmt")
async def cb_labels_mgmt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    labels  = store_get_groups(user_id).get("groups", [])
    header  = f"🎨 <b>Группы</b> ({len(labels)}/{LABEL_LIMIT_HARD})"
    try:
        await callback.message.edit_text(header, reply_markup=get_labels_mgmt_inline(labels))
    except Exception:
        await callback.message.answer(header, reply_markup=get_labels_mgmt_inline(labels))


# ─── Task editing from settings ───────────────────────────────────────────────

def _task_edit_field_kb(tid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Название",  callback_data=f"tedit_title_{tid}"),
         InlineKeyboardButton(text="📅 Дедлайн",   callback_data=f"tedit_deadline_{tid}")],
        [InlineKeyboardButton(text="🔔 Напомин.",   callback_data=f"tedit_reminder_{tid}"),
         InlineKeyboardButton(text="🎨 Группа",    callback_data=f"tedit_group_{tid}")],
        [InlineKeyboardButton(text="← Назад",      callback_data="menu_tasks_mgmt")],
    ])

@router.callback_query(F.data.startswith("task_edit_"))
async def cb_task_edit_start(callback: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(callback)
    tid = callback.data[len("task_edit_"):]
    user_id = str(callback.from_user.id)
    tasks = store_get_tasks(user_id)
    task = next((t for t in tasks if t.get("task_id") == tid), None)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    await state.update_data(edit_task_id=tid)
    await state.set_state(TaskEditStates.waiting_for_field)
    text = (
        f"✏️ <b>{task.get('title', '—')}</b>\n"
        f"📅 {task.get('deadline') or 'нет'}  "
        f"🎨 {task.get('label_name') or 'без группы'}\n"
        f"Что меняем?"
    )
    try:
        await callback.message.edit_text(text, reply_markup=_task_edit_field_kb(tid))
    except Exception:
        await callback.message.answer(text, reply_markup=_task_edit_field_kb(tid))

@router.callback_query(F.data.startswith("tedit_title_"))
async def cb_tedit_title(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tid = callback.data[len("tedit_title_"):]
    await state.update_data(edit_task_id=tid)
    await state.set_state(TaskEditStates.editing_title)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"task_edit_{tid}")]
    ])
    try:
        await callback.message.edit_text("✏️ Введи новое название задачи:", reply_markup=cancel_kb)
        await state.update_data(_tedit_msg_id=callback.message.message_id,
                                _tedit_chat_id=callback.message.chat.id)
    except Exception:
        sent = await callback.message.answer("✏️ Введи новое название задачи:", reply_markup=cancel_kb)
        await state.update_data(_tedit_msg_id=sent.message_id,
                                _tedit_chat_id=sent.chat.id)

@router.message(StateFilter(TaskEditStates.editing_title))
async def tedit_title_input(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    data = await state.get_data()
    tid  = data.get("edit_task_id", "")
    new_title = (message.text or "").strip()
    if not new_title:
        await message.answer("⚠️ Название не может быть пустым.")
        return
    tasks = store_get_tasks(user_id)
    for t in tasks:
        if t.get("task_id") == tid:
            t["title"] = new_title
            t["updated"] = _today()
    store_set_tasks(user_id, tasks)
    _fire_sync()
    _ted = await state.get_data()
    if _ted.get("_tedit_msg_id"):
        try:
            await message.bot.delete_message(_ted.get("_tedit_chat_id", message.chat.id),
                                             _ted["_tedit_msg_id"])
        except Exception:
            pass
    await state.clear()
    await message.answer(f"✅ Название → «{new_title}»", reply_markup=get_main_keyboard())

@router.callback_query(F.data.startswith("tedit_deadline_"))
async def cb_tedit_deadline(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tid = callback.data[len("tedit_deadline_"):]
    await state.update_data(edit_task_id=tid)
    await state.set_state(TaskEditStates.editing_deadline)
    try:
        await callback.message.edit_text(
            "📅 Выбери новый дедлайн:",
            reply_markup=get_deadline_keyboard()
        )
    except Exception:
        await callback.message.answer("📅 Выбери новый дедлайн:", reply_markup=get_deadline_keyboard())

@router.callback_query(F.data.startswith("dl_"), StateFilter(TaskEditStates.editing_deadline))
async def tedit_deadline_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    data = await state.get_data()
    tid  = data.get("edit_task_id", "")
    val  = callback.data[3:]

    # Custom date — ask for text input
    if val == "custom":
        await state.update_data(edit_task_id=tid)
        await state.set_state(TaskEditStates.waiting_for_custom_deadline)
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"task_edit_{tid}")]
        ])
        try:
            await callback.message.edit_text(
                "✏️ Введи свою дату: <code>ДД.ММ</code> или <code>ДД.ММ.ГГ</code>",
                parse_mode="HTML", reply_markup=cancel_kb
            )
        except Exception:
            await callback.message.answer(
                "✏️ Введи свою дату: <code>ДД.ММ</code> или <code>ДД.ММ.ГГ</code>",
                parse_mode="HTML", reply_markup=cancel_kb
            )
        return

    deadline = None if val == "skip" else val
    tasks = store_get_tasks(user_id)
    for t in tasks:
        if t.get("task_id") == tid:
            t["deadline"] = deadline
            t["updated"]  = _today()
    store_set_tasks(user_id, tasks)
    _fire_sync()
    await state.clear()
    dl_str = deadline or "убран"
    await callback.message.edit_text(f"✅ Дедлайн → {dl_str}")
    await callback.message.answer("🌿", reply_markup=get_main_keyboard())

@router.message(StateFilter(TaskEditStates.waiting_for_custom_deadline))
async def tedit_custom_deadline_input(message: Message, state: FSMContext):
    """Handle free-text custom deadline input in task edit flow."""
    from datetime import datetime as _dttc
    user_id = str(message.from_user.id)
    data = await state.get_data()
    tid = data.get("edit_task_id", "") or data.get("_ttask_edit_id", "")
    raw = (message.text or "").strip()
    _dl = None
    import re as _rec
    # DD.MM or DD.MM.YY or DD.MM.YYYY
    m = _rec.match(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?$", raw)
    if m:
        dd, mm = m.group(1).zfill(2), m.group(2).zfill(2)
        yy = m.group(3) or str(_dttc.now().year)
        yy = "20" + yy if len(yy) == 2 else yy
        _dl = f"{yy}-{mm}-{dd}"
    elif _rec.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        _dl = raw
    if _dl:
        tasks = store_get_tasks(user_id)
        for t in tasks:
            if t.get("task_id") == tid:
                t["deadline"] = _dl
                t["updated"] = _today()
        store_set_tasks(user_id, tasks)
        _fire_sync()
        await state.clear()
        await message.answer(f"✅ Дедлайн → {_dl}", reply_markup=get_main_keyboard())
    else:
        await message.answer(
            "🌀 Не понял дату. Напиши: <code>25.05</code> или <code>25.05.26</code>",
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("tedit_reminder_"))
async def cb_tedit_reminder(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tid = callback.data[len("tedit_reminder_"):]
    await state.update_data(edit_task_id=tid)
    await state.set_state(TaskEditStates.editing_reminder)
    user_id = str(callback.from_user.id)
    tasks = store_get_tasks(user_id)
    task = next((t for t in tasks if t.get("task_id") == tid), None)
    deadline = task.get("deadline") if task else None
    try:
        await callback.message.edit_text(
            "🔔 Выбери напоминание:",
            reply_markup=get_reminder_keyboard(deadline)
        )
    except Exception:
        await callback.message.answer("🔔 Выбери напоминание:", reply_markup=get_reminder_keyboard(deadline))

@router.callback_query(F.data.startswith("rem_") & ~F.data.startswith("rem_rp_") & ~F.data.startswith("rem_day_") & ~F.data.startswith("rem_noop_") & (F.data != "rem_repeat_pick") & (F.data != "rem_rp_done") & (F.data != "rem_back_to_confirm") & (F.data != "rem_confirm_create") & (F.data != "rem_confirm_edit") & (F.data != "rem_create_new"), StateFilter(TaskEditStates.editing_reminder))
async def tedit_reminder_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    data = await state.get_data()
    tid  = data.get("edit_task_id", "")
    val  = callback.data[4:]
    if val == "custom":
        await state.set_state(TaskEditStates.editing_reminder)
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"task_edit_{tid}")]
        ])
        try:
            await callback.message.edit_text(
                "✏️ Введи дату и время: <code>ДД.ММ.ГГ ЧЧ:ММ</code>",
                reply_markup=cancel_kb
            )
        except Exception:
            await callback.message.answer("✏️ Введи: <code>ДД.ММ.ГГ ЧЧ:ММ</code>", reply_markup=cancel_kb)
        return
    reminder = None if val == "skip" else val
    tasks = store_get_tasks(user_id)
    for t in tasks:
        if t.get("task_id") == tid:
            t["reminder"] = reminder
            t["updated"]  = _today()
    store_set_tasks(user_id, tasks)
    _fire_sync()
    # Создать/обновить запись в ws['reminders'] с привязкой к задаче
    tasks_tr = store_get_tasks(user_id)
    task_tr = next((t for t in tasks_tr if t.get("task_id") == tid), None)
    task_title_tr = task_tr.get("title", "") if task_tr else ""
    task_repeat_tr = task_tr.get("repeat", "once") if task_tr else "once"

    reminders_tr = store_get_reminders(user_id)
    # Удалить старое напоминание этой задачи если есть
    reminders_tr = [r for r in reminders_tr if r.get("task_id") != tid]
    if reminder:
        import uuid as _uuid_tr2
        rid_tr = "rem_" + str(_uuid_tr2.uuid4())[:8]
        reminders_tr.append({
            "id": rid_tr,
            "title": task_title_tr,
            "datetime_iso": reminder,
            "repeat": task_repeat_tr if task_repeat_tr != "once" else "once",
            "active": True,
            "task_id": tid,
        })
    store_set_reminders(user_id, reminders_tr)

    await state.clear()
    r_str = reminder[:16].replace("T", " ") if reminder else "убрано"
    await callback.answer(f"✅ Напоминание → {r_str}")
    try:
        await callback.message.edit_text(
            f"✏️ <b>{task_title_tr}</b>",
            reply_markup=get_task_edit_inline(user_id, tid),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            f"✏️ <b>{task_title_tr}</b>",
            reply_markup=get_task_edit_inline(user_id, tid),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("ttask_rem_clear|"))
async def cb_ttask_rem_clear(callback: CallbackQuery, state: FSMContext):
    """Убрать напоминание с задачи и удалить из ws['reminders']."""
    await _safe_cb_answer(callback)
    user_id = str(callback.from_user.id)
    task_id = callback.data.split("|")[1]
    tasks = store_get_tasks(user_id)
    task = next((t for t in tasks if t.get("task_id") == task_id), None)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    # Удалить из ws['reminders'] если есть
    reminders = store_get_reminders(user_id)
    reminders = [r for r in reminders if r.get("task_id") != task_id]
    store_set_reminders(user_id, reminders)
    # Очистить поле reminder в задаче
    for t in tasks:
        if t.get("task_id") == task_id:
            t["reminder"] = None
            t["updated"] = _today()
    store_set_tasks(user_id, tasks)
    _fire_sync()
    await state.clear()
    await callback.answer("🗑 Напоминание убрано")
    try:
        await callback.message.edit_text(
            f"✏️ <b>{task.get('title', '—')}</b>",
            reply_markup=get_task_edit_inline(user_id, task_id),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            f"✏️ <b>{task.get('title', '—')}</b>",
            reply_markup=get_task_edit_inline(user_id, task_id),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("tedit_group_"))
async def cb_tedit_group(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tid = callback.data[len("tedit_group_"):]
    await state.update_data(edit_task_id=tid)
    await state.set_state(TaskEditStates.editing_group)
    user_id = str(callback.from_user.id)
    labels = store_get_groups(user_id).get("groups", [])
    try:
        await callback.message.edit_text("🎨 Выбери группу:", reply_markup=get_labels_keyboard(labels))
    except Exception:
        await callback.message.answer("🎨 Выбери группу:", reply_markup=get_labels_keyboard(labels))

@router.callback_query(F.data.startswith("lbl_"), StateFilter(TaskEditStates.editing_group))
async def tedit_group_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    data = await state.get_data()
    tid  = data.get("edit_task_id", "")
    val  = callback.data[4:]
    if val in ("new", "skip"):
        label_id, label_name = None, ""
    else:
        labels = store_get_groups(user_id).get("groups", [])
        lb = next((l for l in labels if l["id"] == val), None)
        label_id   = val
        label_name = lb["name"] if lb else ""
    tasks = store_get_tasks(user_id)
    for t in tasks:
        if t.get("task_id") == tid:
            t["label_id"]   = label_id
            t["label_name"] = label_name
            t["updated"]    = _today()
    store_set_tasks(user_id, tasks)
    _fire_sync()
    await state.clear()
    g_str = label_name or "без группы"
    try:
        await callback.message.edit_text(f"✅ Группа → {g_str}")
    except Exception:
        pass
    await callback.message.answer("🌿", reply_markup=get_main_keyboard())

@router.callback_query(F.data == "back_to_settings")
async def cb_back_to_settings(callback: CallbackQuery, state: FSMContext):
    """Legacy back — returns to main menu."""
    await callback.answer()
    await state.clear()
    await callback.message.answer("🌿", reply_markup=get_main_keyboard())

@router.callback_query(F.data == "menu_edit_profile_back")
async def cb_edit_profile_back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    # Показываем новый профиль с полной клавиатурой вместо старого с одной кнопкой
    await _show_profile(user_id, callback.message)

# ─── Checklist unified show function ──────────────────────────────────────────



def _filter_tasks_by_period(tasks: list, period: str, tz_name: str = "Europe/Moscow") -> list:
    """Filter active tasks by deadline period.
    period: today | tomorrow | week | month | overdue | all
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    try:
        _tz = ZoneInfo(tz_name)
    except Exception:
        _tz = ZoneInfo("Europe/Moscow")
    _now      = datetime.now(_tz)
    today     = _now.strftime("%Y-%m-%d")
    tomorrow  = (_now + timedelta(days=1)).strftime("%Y-%m-%d")
    week_end  = (_now + timedelta(days=7)).strftime("%Y-%m-%d")
    month_end = (_now + timedelta(days=30)).strftime("%Y-%m-%d")
    day_after = (_now + timedelta(days=2)).strftime("%Y-%m-%d")
    active = [t for t in tasks if t.get("status") != "completed"]
    if period == "today":
        return [t for t in active if t.get("deadline") == today]
    elif period == "tomorrow":
        return [t for t in active if t.get("deadline") == tomorrow]
    elif period == "day_after":
        return [t for t in active if t.get("deadline") == day_after]
    elif period.startswith("date:"):
        target = period[5:]
        return [t for t in active if t.get("deadline") == target]
    elif period == "week":
        return [t for t in active if t.get("deadline") and today <= t["deadline"] <= week_end]
    elif period == "month":
        return [t for t in active if t.get("deadline") and today <= t["deadline"] <= month_end]
    elif period == "overdue":
        return [t for t in active if t.get("deadline") and t["deadline"] < today]
    return active  # "all"

def _detect_task_period(text: str) -> str:
    """Detect time period from user query. Returns period key or date:YYYY-MM-DD."""
    import re as _re
    from datetime import datetime, timedelta
    t = text.lower()
    if any(k in t for k in ["сегодня", "today", "на сегодня"]):
        return "today"
    if any(k in t for k in ["послезавтра", "day after tomorrow"]):
        return "day_after"
    if any(k in t for k in ["завтра", "tomorrow", "на завтра"]):
        return "tomorrow"
    if any(k in t for k in ["неделю", "неделя", "на неделе", "на этой неделе", "week"]):
        return "week"
    if any(k in t for k in ["месяц", "month", "на месяц"]):
        return "month"
    if any(k in t for k in ["просрочен", "overdue", "прошли", "устарел", "истёк"]):
        return "overdue"
    # Specific date: "на 22", "на 22 апреля", "на 22 число"
    MONTHS_RU = {"январ":1,"феврал":2,"март":3,"апрел":4,"май":5,"мая":5,
                 "июн":6,"июл":7,"август":8,"сентябр":9,"октябр":10,"ноябр":11,"декабр":12}
    m = _re.search(r"на\s+(\d{1,2})(?:\s+(\w+))?", t)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            month = datetime.now().month
            year  = datetime.now().year
            if m.group(2):
                for mn, mv in MONTHS_RU.items():
                    if mn in m.group(2).lower():
                        month = mv
                        break
            try:
                date_str = f"{year}-{month:02d}-{day:02d}"
                datetime.strptime(date_str, "%Y-%m-%d")  # validate
                return f"date:{date_str}"
            except ValueError:
                pass
    return "all"


def _deadline_indicator(deadline: str, tz_name: str = "Europe/Moscow") -> str:
    """Return urgency emoji for a task deadline.
    🔥 = today or overdue
    ⚡ = tomorrow or day-after
    🌱 = 3-7 days
    '' = 8+ days or no deadline
    """
    if not deadline:
        return ""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    try:
        _tz = ZoneInfo(tz_name)
    except Exception:
        _tz = ZoneInfo("Europe/Moscow")
    _now      = datetime.now(_tz)
    today     = _now.strftime("%Y-%m-%d")
    tomorrow  = (_now + timedelta(days=1)).strftime("%Y-%m-%d")
    day_after = (_now + timedelta(days=2)).strftime("%Y-%m-%d")
    week_end  = (_now + timedelta(days=7)).strftime("%Y-%m-%d")
    if deadline <= today:
        return "🔥 "
    if deadline in (tomorrow, day_after):
        return "⚡ "
    if deadline <= week_end:
        return "🌱 "
    return ""

def _sort_by_deadline(tasks: list) -> list:
    """Sort tasks: nearest deadline first, no deadline last."""
    def key(t):
        dl = t.get("deadline")
        return dl if dl else "9999-99-99"
    return sorted(tasks, key=key)



def _format_tasks_labels(tasks: list, user_id: str = "") -> str:
    """Format active tasks grouped by group in workspace order, with unique emojis."""
    by_group: dict = {}
    for t in tasks:
        key = t.get("label_name") or ""
        by_group.setdefault(key, []).append(t)
    groups_data = store_get_groups(user_id).get("groups", []) if user_id else []
    emoji_map   = _assign_group_emojis(groups_data)
    def get_emoji(gname: str) -> str:
        for g in groups_data:
            if g.get("name") == gname:
                return emoji_map.get(g["id"], "🌱")
        return _group_emoji(gname) or "🌱"
    parts = []
    shown = set()
    # Iterate in stored groups order
    for g in groups_data:
        gname = g.get("name", "")
        items = by_group.get(gname, [])
        if not items:
            continue
        shown.add(gname)
        emoji = emoji_map.get(g["id"], "🌱")
        parts.append(f"<b>{emoji} {gname}</b>")
        for t in _sort_by_deadline(items)[:10]:
            dl  = " · " + t["deadline"] if t.get("deadline") else ""
            ind = _deadline_indicator(t.get("deadline",""))
            parts.append(f"  • {ind}{t['title']}{dl}")
    # Any groups not in workspace (edge case)
    for gname, items in by_group.items():
        if not gname or gname in shown:
            continue
        emoji = get_emoji(gname)
        parts.append(f"<b>{emoji} {gname}</b>")
        for t in _sort_by_deadline(items)[:10]:
            dl  = " · " + t["deadline"] if t.get("deadline") else ""
            ind = _deadline_indicator(t.get("deadline",""))
            parts.append(f"  • {ind}{t['title']}{dl}")
    no_group = by_group.get("", [])
    if no_group:
        parts.append("<b>🌱 Без группы</b>")
        for t in _sort_by_deadline(no_group)[:5]:
            dl  = " · " + t["deadline"] if t.get("deadline") else ""
            ind = _deadline_indicator(t.get("deadline",""))
            parts.append(f"  • {ind}{t['title']}{dl}")
    return "\n".join(parts) if parts else ""

async def cmd_tasks(message: Message, view: str = "labels"):
    if not await _check_ready(message):
        return
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    tasks = store_get_tasks(user_id)
    active = [t for t in tasks if t.get("status") != "completed"]
    if not active:
        await message.answer("🌀 Активных задач нет.", reply_markup=get_main_keyboard())
        await message.answer("👇", reply_markup=get_tasks_keyboard())
        return
    body = _format_tasks_labels(active, user_id)
    header = "🌀 <b>Задачи · Группы:</b>"
    await message.answer(header + "\n\n" + body)




@router.callback_query(F.data == "start_addtask")
async def cb_start_addtask(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_authorized(str(callback.from_user.id)):
        await callback.message.answer("🌿 Используй /start")
        return
    await _start_task_flow(callback.message, state)

async def cb_start_addtask_msg(message: Message, state: FSMContext, pre_title: str = ""):
    """Helper: start task FSM from message context (intent router)."""
    await _start_task_flow(message, state, pre_title=pre_title)

async def _start_task_flow(message: Message, state: FSMContext, pre_title: str = ""):
    # Mark as interacted today to suppress proactive greeting
    if message.from_user:
        uid = str(message.from_user.id)
        _track_interaction(uid)
    if pre_title:
        await state.update_data(title=pre_title)
        await state.set_state(TaskStates.waiting_for_deadline)
        await message.answer(
            "📅 <b>" + pre_title + "</b> — дедлайн?",
            reply_markup=get_deadline_keyboard()
        )
    else:
        await state.set_state(TaskStates.waiting_for_title)
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task")]
        ])
        await message.answer(
            "🌀 <b>Новая задача</b> — как назовём?\n"
            "<i>Пример: «Записаться к врачу»</i>",
            reply_markup=cancel_kb
        )

@router.message(Command("addtask"))
async def cmd_addtask(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    await _start_task_flow(message, state)

# ── Step 1: Title ──────────────────────────────────────────────────────────

@router.message(StateFilter(TaskStates.waiting_for_title))
async def task_title(message: Message, state: FSMContext):
    if message.text and message.text.strip() == "❌ Отмена":
        await state.clear()
        await message.answer("Возвращаемся 🌿", reply_markup=get_main_keyboard())
        return
    title = (message.text or "").strip()
    if len(title) < 2:
        await message.answer("🌀 Название должно быть не короче 2 символов.")
        return
    await state.update_data(title=title)
    await state.set_state(TaskStates.waiting_for_deadline)
    await message.answer(
        "📅 <b>Дедлайн?</b>\nВыбери или напиши в формате ДД.ММ.ГГГГ:",
        reply_markup=get_deadline_keyboard()
    )

# ── Step 2: Deadline ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("dl_"), StateFilter(TaskStates.waiting_for_deadline))
async def task_deadline_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    val = callback.data[3:]
    if val == "custom":
        await state.set_state(TaskStates.waiting_for_custom_deadline)
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task")]
        ])
        try:
            await callback.message.edit_text(
                "✏️ <b>Своя дата</b>\n\nВведи в формате: <code>ДД.ММ.ГГ</code>\n"
                "<i>Пример: 25.05.26</i>",
                reply_markup=cancel_kb
            )
        except Exception:
            await callback.message.answer(
                "✏️ Введи дату: <code>ДД.ММ.ГГ</code>",
                reply_markup=cancel_kb
            )
        return
    deadline = None if val == "skip" else val
    await state.update_data(deadline=deadline)
    await state.set_state(TaskStates.waiting_for_reminder)
    dl_str = (" · " + deadline) if deadline else ""
    try:
        await callback.message.edit_text(
            "🔔 <b>Напоминание?</b>" + dl_str,
            reply_markup=get_reminder_keyboard(deadline)
        )
    except Exception:
        await callback.message.answer(
            "🔔 <b>Напоминание?</b>",
            reply_markup=get_reminder_keyboard(deadline)
        )
    # Если создание из меню Задач — сохраняем group_id в FSM
    # _ttask_create_group уже установлен в cb_ttask_create

@router.message(StateFilter(TaskStates.waiting_for_custom_deadline))
async def task_custom_deadline_input(message: Message, state: FSMContext):
    if message.text and message.text.strip() == "❌ Отмена":
        await state.clear()
        await message.answer("Возвращаемся 🌿", reply_markup=get_main_keyboard())
        return
    import re as _re
    text = (message.text or "").strip()
    deadline = None
    m = _re.match(r"^(\d{2})\.(\d{2})\.(\d{2})$", text)
    if m:
        dd, mm, yy = m.groups()
        deadline = f"20{yy}-{mm}-{dd}"
    elif _re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        deadline = text
    if not deadline:
        await message.answer(
            "⚠️ Не понял формат. Введи: <code>ДД.ММ.ГГ</code>\n<i>Пример: 25.05.26</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task")]
            ])
        )
        return
    await state.update_data(deadline=deadline)
    await state.set_state(TaskStates.waiting_for_reminder)
    await message.answer(
        f"📅 {deadline}\n🔔 <b>Напоминание?</b>",
        reply_markup=get_reminder_keyboard(deadline)
    )

@router.message(StateFilter(TaskStates.waiting_for_deadline))
async def task_deadline_text(message: Message, state: FSMContext):
    if message.text and message.text.strip() == "❌ Отмена":
        await state.clear()
        await message.answer("Возвращаемся 🌿", reply_markup=get_main_keyboard())
        return
    text = (message.text or "").strip()
    import re as _re
    deadline = None
    m = _re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", text)
    if m:
        deadline = m.group(3) + "-" + m.group(2) + "-" + m.group(1)
    elif _re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        deadline = text
    await state.update_data(deadline=deadline)
    await state.set_state(TaskStates.waiting_for_reminder)
    dl_str = (" · " + deadline) if deadline else " · без дедлайна"
    await message.answer(
        "🔔 <b>Напоминание?</b>" + dl_str,
        reply_markup=get_reminder_keyboard(deadline)
    )

# ── Step 3: Reminder ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("rem_") & ~F.data.startswith("rem_rp_") & ~F.data.startswith("rem_day_") & ~F.data.startswith("rem_noop_") & (F.data != "rem_repeat_pick") & (F.data != "rem_rp_done") & (F.data != "rem_back_to_confirm") & (F.data != "rem_confirm_create") & (F.data != "rem_confirm_edit") & (F.data != "rem_create_new"), StateFilter(TaskStates.waiting_for_reminder))
async def task_reminder_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    val = callback.data[4:]
    if val == "custom":
        # Switch to custom date input state
        await state.set_state(TaskStates.waiting_for_custom_reminder)
        try:
            await callback.message.edit_text(
                "✏️ <b>Своя дата напоминания</b>\n\n"
                "Введи в формате: <code>ДД.ММ.ГГ ЧЧ:ММ</code>\n"
                "<i>Пример: 25.04.26 09:00</i>",
                reply_markup=None
            )
        except Exception:
            await callback.message.answer(
                "✏️ Введи дату и время: <code>ДД.ММ.ГГ ЧЧ:ММ</code>",
                reply_markup=get_cancel_keyboard()
            )
        return
    reminder = None if val == "skip" else val
    await state.update_data(reminder=reminder)
    user_id = str(callback.from_user.id)
    await _ask_repeat_task(callback.message, state, edit=True)

@router.message(StateFilter(TaskStates.waiting_for_custom_reminder))
async def task_custom_reminder_input(message: Message, state: FSMContext):
    if message.text and message.text.strip() == "❌ Отмена":
        await state.clear()
        await message.answer("Возвращаемся 🌿", reply_markup=get_main_keyboard())
        return
    text = (message.text or "").strip()
    reminder = None
    # Parse ДД.ММ.ГГ ЧЧ:ММ
    import re as _re
    m = _re.match(r"^(\d{2})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2})$", text)
    if m:
        dd, mm, yy, hh, mi = m.groups()
        reminder = f"20{yy}-{mm}-{dd}T{hh}:{mi}"
    if not reminder:
        await message.answer(
            "⚠️ Не понял формат. Введи: <code>ДД.ММ.ГГ ЧЧ:ММ</code>\n"
            "<i>Пример: 25.04.26 09:00</i>",
            reply_markup=get_cancel_keyboard()
        )
        return
    await state.update_data(reminder=reminder)
    user_id = str(message.from_user.id)
    await message.answer(f"✅ Напоминание: {text}")
    await _ask_repeat_task(message, state, edit=False)

@router.message(StateFilter(TaskStates.waiting_for_reminder))
async def task_reminder_text(message: Message, state: FSMContext):
    if message.text and message.text.strip() == "❌ Отмена":
        await state.clear()
        await message.answer("Возвращаемся 🌿", reply_markup=get_main_keyboard())
        return
    await state.update_data(reminder=None)
    user_id = str(message.from_user.id)
    await _ask_repeat_task(message, state, edit=False)

def _get_repeat_task_keyboard() -> InlineKeyboardMarkup:
    """Repeat picker for task FSM — дни недели + своя дата."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1️⃣ Однократно",       callback_data="trep_once")],
        [InlineKeyboardButton(text="🔁 Каждый день",       callback_data="trep_daily")],
        [InlineKeyboardButton(text="📅 Раз в неделю",      callback_data="trep_weekly")],
        [InlineKeyboardButton(text="🗓 Раз в месяц",       callback_data="trep_monthly")],
        [InlineKeyboardButton(text="🌿 Раз в год",         callback_data="trep_yearly")],
        [InlineKeyboardButton(text="📆 Выбрать дни недели", callback_data="trep_weekdays_pick")],
        [InlineKeyboardButton(text="🗒 Своя дата",         callback_data="trep_custom_date")],
    ])

async def _ask_repeat_task(message: Message, state: FSMContext, edit: bool = False):
    """Step 3.5 of task FSM: choose repeat."""
    await state.set_state(TaskStates.waiting_for_repeat)
    text = "🔁 <b>Повторение?</b>"
    kb = _get_repeat_task_keyboard()
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("trep_"), StateFilter(TaskStates.waiting_for_repeat))
async def task_repeat_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    val = callback.data[5:]  # once / daily / weekly / monthly / yearly / weekdays_pick / custom_date
    if val == "weekdays_pick":
        # Показать выбор дней недели через текстовый ввод
        await state.set_state(TaskStates.waiting_for_repeat)
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task")]
        ])
        try:
            await callback.message.edit_text(
                "📅 <b>Дни недели:</b>\n\nНапиши дни, например:\n<code>пн ср пт</code>",
                reply_markup=cancel_kb, parse_mode="HTML"
            )
        except Exception:
            await callback.message.answer(
                "📅 <b>Дни недели:</b>\n\nНапиши дни, например:\n<code>пн ср пт</code>",
                reply_markup=cancel_kb, parse_mode="HTML"
            )
        await state.set_state(TaskStates.waiting_for_repeat_custom_days)
        return
    if val == "custom_date":
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task")]
        ])
        try:
            await callback.message.edit_text(
                "🗒 <b>Своя дата повторения:</b>\n\nВведи дату: <code>ДД.ММ.ГГ</code>\nНапример: <code>25.06.26</code>",
                reply_markup=cancel_kb, parse_mode="HTML"
            )
        except Exception:
            await callback.message.answer(
                "🗒 <b>Своя дата повторения:</b>\n\nВведи дату: <code>ДД.ММ.ГГ</code>",
                reply_markup=cancel_kb, parse_mode="HTML"
            )
        await state.set_state(TaskStates.waiting_for_repeat_custom_date)
        return
# trep_back removed — handled by cancel_task via FSM state clear
    repeat = None if val == "once" else val
    await state.update_data(repeat=repeat)
    user_id = str(callback.from_user.id)
    await _ask_group(callback.message, state, user_id, edit=True)

@router.message(StateFilter(TaskStates.waiting_for_repeat_custom_days))
async def task_repeat_custom_days_input(message: Message, state: FSMContext):
    """Ввод дней недели для повторения задачи."""
    user_id = str(message.from_user.id)
    text = (message.text or "").strip()
    # reuse reminder days parser
    try:
        repeat = _parse_weekdays(text.lower())
    except Exception:
        repeat = None
    if not repeat or repeat == "custom_days:" or repeat == "once":
        await message.answer("🌀 Не понял дни. Попробуй: <code>пн ср пт</code>", parse_mode="HTML")
        return
    await state.update_data(repeat=repeat)
    await _ask_group(message, state, user_id, edit=False)

@router.message(StateFilter(TaskStates.waiting_for_repeat_custom_date))
async def task_repeat_custom_date_input(message: Message, state: FSMContext):
    """Ввод своей даты для повторения задачи."""
    import re as _re_td
    user_id = str(message.from_user.id)
    text = (message.text or "").strip()
    m = _re_td.match(r"(\d{2})\.(\d{2})\.(\d{2,4})$", text)
    if not m:
        await message.answer("🌀 Формат: <code>ДД.ММ.ГГ</code>  например <code>25.06.26</code>", parse_mode="HTML")
        return
    d, mo, y = m.group(1), m.group(2), m.group(3)
    if len(y) == 2:
        y = "20" + y
    repeat = f"custom_date:{y}-{mo}-{d}"
    await state.update_data(repeat=repeat)
    await _ask_group(message, state, user_id, edit=False)

async def _ask_group(message: Message, state: FSMContext, user_id: str, edit: bool = False):
    """Step 4 of task FSM: choose group (formerly label)."""
    await state.set_state(TaskStates.waiting_for_group)
    labels = store_get_groups(user_id).get("groups", [])
    text = "🎨 <b>Группа?</b>\nГруппы объединяют задачи. Выбери или создай свою:"
    kb = get_labels_keyboard(labels)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb)

# ── Step 4: Label ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("lbl_"), StateFilter(TaskStates.waiting_for_group))
async def task_label_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    val = callback.data[4:]
    if val == "new":
        await state.set_state(TaskStates.waiting_for_new_group)
        try:
            await callback.message.edit_text("🎨 Введи название новой группы:", reply_markup=None)
        except Exception:
            await callback.message.answer("🎨 Введи название новой группы:", reply_markup=get_cancel_keyboard())
        return
    label_id = None if val == "skip" else val
    label_name = ""
    if label_id:
        user_id = str(callback.from_user.id)
        labels = store_get_groups(user_id).get("groups", [])
        lb = next((l for l in labels if l["id"] == label_id), None)
        label_name = lb["name"] if lb else ""
    await state.update_data(label_id=label_id, label_name=label_name)
    await _show_task_confirm(callback.message, state, edit=True)



@router.message(StateFilter(TaskStates.waiting_for_new_group))
async def task_new_label_input(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    name = (message.text or "").strip()
    if len(name) < 1:
        await message.answer("🏷 Введи название группы.")
        return
    data = await state.get_data()
    _edit_group_id = data.get("_tgroup_edit_id", "")
    if _edit_group_id:
        groups_data = store_get_groups(user_id)
        groups = groups_data.get("groups", [])
        g = next((x for x in groups if x["id"] == _edit_group_id), None)
        if g:
            old_name = g["name"]
            g["name"] = name
            store_set_groups(user_id, groups_data)
            tasks = store_get_tasks(user_id)
            for t in tasks:
                if t.get("label_id") == _edit_group_id:
                    t["label_name"] = name
            store_set_tasks(user_id, tasks)
            _fire_sync()
            await state.clear()
            await message.answer(f"✅ Группа «{old_name}» → «{name}»", reply_markup=get_main_keyboard())
            groups_data2 = store_get_groups(user_id).get("groups", [])
            all_tasks2 = store_get_tasks(user_id)
            active2 = [t for t in all_tasks2 if t.get("status") != "completed"]
            header2 = f"\U0001f5c2 <b>\u0417\u0430\u0434\u0430\u0447\u0438</b> \u00b7 {len(groups_data2)} \u0433\u0440\u0443\u043f\u043f \u00b7 {len(active2)} \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445"
            await message.answer(header2, reply_markup=get_groups_list_inline(user_id))
            return
        else:
            await state.clear()
            await message.answer("🌀 Группа не найдена.", reply_markup=get_main_keyboard())
            return
    data_store = store_get_groups(user_id)
    labels = data_store.get("groups", [])
    if len(labels) >= LABEL_LIMIT_HARD:
        await message.answer(f"⚠️ Лимит групп: {LABEL_LIMIT_HARD}. Удали или переименуй существующий.")
        await state.clear()
        return
    gid = _make_group_id(name, labels)
    labels.append({"id": gid, "name": name, "created": _today()})
    data_store["groups"] = labels
    store_set_groups(user_id, data_store)
    _fire_sync()
    await state.clear()
    suffix = f" Осталось {LABEL_LIMIT_HARD - len(labels)} слота." if len(labels) >= LABEL_LIMIT_SOFT else ""
    await message.answer("✅ Группа «" + name + "» создана!" + suffix, reply_markup=get_main_keyboard())
    groups_data3 = store_get_groups(user_id).get("groups", [])
    all_tasks3 = store_get_tasks(user_id)
    active3 = [t for t in all_tasks3 if t.get("status") != "completed"]
    header3 = f"\U0001f5c2 <b>\u0417\u0430\u0434\u0430\u0447\u0438</b> \u00b7 {len(groups_data3)} \u0433\u0440\u0443\u043f\u043f \u00b7 {len(active3)} \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445"
    await message.answer(header3, reply_markup=get_groups_list_inline(user_id))

async def _show_task_confirm(message: Message, state: FSMContext, edit: bool = False):
    await state.set_state(TaskStates.waiting_for_confirm)
    data = await state.get_data()
    title      = data.get("title", "—")
    deadline   = data.get("deadline") or "не указан"
    reminder   = data.get("reminder") or "нет"
    label_name = data.get("label_name") or "без группы"
    merkaba    = _auto_merkaba(title, data.get("label_name", ""))
    mkb_icons  = {"health": "🌿 Тело", "spirit": "🔥 Дух", "world": "🤝 Мир"}
    summary = (
        "📝 <b>" + title + "</b>\n"
        "📅 " + deadline + " · 🏷 " + label_name + "\n"
        "✨ " + mkb_icons.get(merkaba, "🤝 Мир")
    )
    kb = get_confirm_task_keyboard()
    if edit:
        try:
            await message.edit_text(summary, reply_markup=kb)
            return
        except Exception:
            pass
    await message.answer(summary, reply_markup=kb)

# ── Confirm / Cancel ──────────────────────────────────────────────────────

@router.callback_query(F.data == "confirm_task")
async def confirm_task(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Сохраняю...")
    data    = await state.get_data()
    user_id = str(callback.from_user.id)
    tasks   = list(store_get_tasks(user_id))
    active_count = len([t for t in tasks if t.get("status") != "completed"])
    if active_count >= TASK_LIMIT_HARD:
        await state.clear()
        try:
            await callback.message.edit_text(
                f"⚠️ Лимит: {TASK_LIMIT_HARD} активных задач. Заверши что-нибудь сначала."
            )
        except Exception:
            await callback.message.answer(f"⚠️ Лимит {TASK_LIMIT_HARD} задач достигнут.")
        return
    elif active_count >= TASK_LIMIT_SOFT:
        try:
            await callback.message.answer(f"⚠️ Почти лимит: {active_count}/{TASK_LIMIT_HARD} задач.")
        except Exception:
            pass
    task_id = "task_" + datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]
    title   = data.get("title", "Задача")
    merkaba = _auto_merkaba(title, data.get("label_name", ""))
    new_task = {
        "task_id":    task_id,
        "title":      title,
        "status":     "todo",
        "label_id":   data.get("label_id"),
        "label_name": data.get("label_name", ""),
        "life_area":  merkaba,
        "priority":   calculate_priority(data.get("deadline")),
        "deadline":   data.get("deadline"),
        "reminder":   data.get("reminder"),
        "created":    _today(),
        "updated":    _today(),
        "completed":  None,
        "notes":      ""
    }
    tasks.append(new_task)
    store_set_tasks(user_id, tasks)
    _fire_sync()
    await state.clear()
    mkb_icons = {"health": "🌿 Тело", "spirit": "🔥 Дух", "world": "🤝 Мир"}
    try:
        await callback.message.edit_text(
            "✅ <b>" + title + "</b> добавлена!\n"
            "🌿 " + mkb_icons.get(merkaba, "🌱")
        )
    except Exception:
        pass
    # Патчер А: возврат в группу после создания задачи
    _created_group_id = data.get("_ttask_create_group") or data.get("label_id") or "__nogroup__"
    _created_group_name = data.get("_ttask_create_label_name") or data.get("label_name") or "Без группы"
    _tasks_in_created = [t for t in store_get_tasks(user_id) if t.get("status") != "completed" and (
        (t.get("label_id") == _created_group_id) if _created_group_id != "__nogroup__" else not t.get("label_name")
    )]
    _header_created = f"\U0001f5c2 <b>{_created_group_name}</b> · {len(_tasks_in_created)} задач"
    await callback.message.answer(
        _header_created,
        reply_markup=get_tasks_in_group_inline(user_id, _created_group_id),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "cancel_task")
async def cancel_task_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    try:
        await callback.message.edit_text("❌ Отменено.")
    except Exception:
        pass
    await callback.message.answer("Возвращаемся 🌿", reply_markup=get_main_keyboard())

@router.message(Command("done"))
async def cmd_done(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("📿 Укажи ID задачи: <code>/done task_id</code>", reply_markup=get_main_keyboard())
        return
    task_id = parts[1]
    tasks = list(store_get_tasks(user_id))
    found = False
    for t in tasks:
        if t.get("task_id") == task_id:
            t["status"] = "completed"
            t["completed"] = _today()
            t["updated"] = _today()
            found = True
            break
    if found:
        active_tasks = [t for t in tasks if t.get("status") != "completed"]
        store_set_tasks(user_id, active_tasks)
        count = store_increment_achievements(user_id)
        _fire_sync()
        await message.answer(
            f"✅ Готово! <code>{task_id}</code> · 💎 {count} достижений",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer("❌ Задача не найдена.", reply_markup=get_main_keyboard())

@router.message(Command("groups"))
async def cmd_groups(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    groups = store_get_groups(user_id).get("groups", [])
    if not groups:
        await message.answer("🌱 Групп пока нет. Создай через /newgroup")
        return
    text = "\n".join([f"• {g['name']} ({g['id']})" for g in groups])
    await message.answer(f"🌱 <b>Группы:</b>\n{text}")

@router.message(Command("newgroup"))
async def cmd_newgroup(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используй: /newgroup Название группы")
        return
    name = parts[1].strip()
    data = store_get_groups(user_id)
    groups = data.get("groups", [])
    gid = _make_group_id(name, groups)
    groups.append({"id": gid, "name": name, "created": _today()})
    data["groups"] = groups
    store_set_groups(user_id, data)
    _fire_sync()
    await message.answer(f"✅ Группа '<b>{name}</b>' создана!")

@router.message(Command("archive"))
async def cmd_archive(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    tasks = store_get_tasks(user_id)
    completed = [t for t in tasks if t.get("status") == "completed"]
    if not completed:
        await message.answer("📜 Завершённых задач нет.")
        return
    active = [t for t in tasks if t.get("status") != "completed"]
    store_set_tasks(user_id, active)
    # Also write archive file directly (fire-and-forget)
    archive_path = f"{_user_path(user_id)}/tasks_archive_{_today()}.json"
    asyncio.create_task(_github_put(archive_path, completed))
    _fire_sync()