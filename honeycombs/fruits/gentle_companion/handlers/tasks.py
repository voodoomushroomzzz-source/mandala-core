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
    await callback.answer("")
    # PENDING RESONANCE: накопление в сессии
    data = await state.get_data()
    pending = data.get("_pending_tasks", [])
    pending.append({
        "title": task.get("title", ""),
        "sphere": sphere,
        "task_id": task_id,
    })
    await state.update_data(_pending_tasks=pending)
    if not data.get("_timer_started"):
        await state.update_data(_timer_started=True)
        asyncio.create_task(_flush_pending_resonance(
            callback.message, user_id, state, delay=5
        ))
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
        await callback.message.answer("🌿 Используй /start")
        return
    groups_data = store_get_groups(user_id).get("groups", [])
    all_tasks = store_get_tasks(user_id)
    active = [t for t in all_tasks if t.get("status") != "completed"]
    header = f"📂 <b>Задачи</b> · {len(groups_data)} групп · {len(active)} активных"
    kb = get_groups_list_inline(user_id)
    await _replace_menu(user_id, callback.message, header, reply_markup=kb)

@router.callback_query(F.data == "tgroup_back_to_list")
async def cb_tgroup_back_to_list(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    groups_data = store_get_groups(user_id).get("groups", [])
    all_tasks = store_get_tasks(user_id)
    active = [t for t in all_tasks if t.get("status") != "completed"]
    header = f"📂 <b>Задачи</b> · {len(groups_data)} групп · {len(active)} активных"
    kb = get_groups_list_inline(user_id)
    await _replace_menu(user_id, callback.message, header, reply_markup=kb)

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


async def _sr_progress_reaction_send(callback_or_msg, user_id: str, event_text: str, must_reply: bool = False) -> None:
    """P-97: get SR reaction and send as separate message.
    must_reply=True: SR must always respond (no silent option)."""
    try:
        reply = await _sr_progress_reaction(user_id, event_text, must_reply=must_reply)
        if reply and reply.strip():
            if hasattr(callback_or_msg, 'message'):
                await callback_or_msg.message.answer(reply)
            else:
                await callback_or_msg.answer(reply)
    except Exception:
        pass

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
    await callback.answer("")
    # PENDING RESONANCE: накопление в сессии
    data = await state.get_data()
    pending = data.get("_pending_tasks", [])
    pending.append({
        "title": task.get("title", ""),
        "sphere": sphere,
        "task_id": task_id,
    })
    await state.update_data(_pending_tasks=pending)
    if not data.get("_timer_started"):
        await state.update_data(_timer_started=True)
        asyncio.create_task(_flush_pending_resonance(
            callback.message, user_id, state, delay=5
        ))
