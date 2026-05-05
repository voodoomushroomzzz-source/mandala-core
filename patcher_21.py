# patcher_21_dashboard.py
# Clickable Profile Dashboard v1.0
# Replaces static profile card with interactive inline-keyboard dashboard
# All navigation through one message. No edit forms — edits through chat with SR.
# Information and Changelog buttons in dashboard footer.
# Version: v1.1 — single data pass, edit_text for inline, proper newlines

import re
import sys

BOT_FILE = "bot.py"

def patch():
    with open(BOT_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    changes = 0

    # ═══════════════════════════════════════════════════════════════════════
    # 1. Remove ℹ️ Информация from main keyboard
    # ═══════════════════════════════════════════════════════════════════════
    old_kb = '[KeyboardButton(text="👤 Профиль"), KeyboardButton(text="ℹ️ Информация")]'
    new_kb = '[KeyboardButton(text="👤 Профиль")]'
    if old_kb in content:
        content = content.replace(old_kb, new_kb, 1)
        changes += 1
        print("✅ 1/8 Removed ℹ️ Информация from main keyboard")
    else:
        print("❌ Main keyboard pattern not found")
        return False

    # ═══════════════════════════════════════════════════════════════════════
    # 2. Delete btn_info handler
    # ═══════════════════════════════════════════════════════════════════════
    old_btn_info = '''@router.message(F.text == "ℹ️ Информация")
async def btn_info(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    await message.answer('🌱 Привет. Я — СР, твой компаньон в саду.\\n\\nУмею работать с:\\n📋 Задачами и группами\\n🗺 Роадмапами (крупные цели)\\n☑️ Чеклистами\\n🔔 Напоминаниями\\n💎 Достижениями\\n🔮 Резонансом сфер\\n🌐 Поиском\\n\\n🧠 Живая память\\nЯ наблюдаю за тобой из диалогов и задач — и становлюсь точнее.\\n/sr_report — посмотри как я тебя вижу.\\n\\nПросто пиши или говори голосом — я пойму.\\nХочешь узнать подробнее о чём-то? Просто спроси меня.', parse_mode="HTML", reply_markup=get_main_keyboard())'''

    if old_btn_info in content:
        content = content.replace(old_btn_info, '', 1)
        content = content.replace('\n\n\n', '\n\n')
        changes += 1
        print("✅ 2/8 Removed btn_info handler")
    else:
        print("⚠️ btn_info handler not found (may already be removed)")

    # ═══════════════════════════════════════════════════════════════════════
    # 3. Add dashboard system (data builder + text builder + keyboard + handlers)
    # ═══════════════════════════════════════════════════════════════════════
    dashboard_code = r'''
# ─── Dashboard System (v7.31) ─────────────────────────────────────────────────

def _build_dashboard_data(user_id: str) -> dict:
    """Collect all dashboard data once. Single data pass for text + keyboard."""
    from datetime import datetime as _dtd
    today_s = _dtd.now().strftime("%Y-%m-%d")

    profile = store_get_profile(user_id) or {}
    tasks = store_get_tasks(user_id)
    roadmaps = store_get_roadmaps(user_id)
    reminders = store_get_reminders(user_id)
    groups_data = store_get_groups(user_id).get("groups", [])
    sr = store_get_sphere_resonance(user_id)

    rm_task_ids = {tid for rm in roadmaps for tid in rm.get("task_ids", [])}

    # Today tasks (overdue first)
    overdue = sorted(
        [t for t in tasks if t.get("deadline") and t["deadline"] < today_s
         and t.get("status") != "completed" and t.get("task_id") not in rm_task_ids],
        key=lambda t: t.get("deadline", "9999")
    )
    due_today = [t for t in tasks if t.get("deadline") == today_s
                 and t.get("status") != "completed" and t.get("task_id") not in rm_task_ids]
    today_all = overdue + due_today

    # Active roadmaps with today tasks
    active_roadmaps = []
    for rm in roadmaps:
        if rm.get("status") != "active":
            continue
        live = _roadmap_live_tasks(rm, tasks)
        total = len(live)
        done_cnt = sum(1 for t in live if t.get("status") == "completed")
        pct = round(done_cnt / total * 100) if total else 0
        rm_today = [t for t in live if t.get("deadline") and t["deadline"] <= today_s
                    and t.get("status") != "completed"]
        active_roadmaps.append({
            "rm": rm,
            "live": live,
            "total": total,
            "done_cnt": done_cnt,
            "pct": pct,
            "rm_today": rm_today,
        })

    # Groups with emoji and task counts
    emoji_map = _assign_group_emojis(groups_data)
    groups_with_counts = []
    for g in groups_data:
        gname = g.get("name", "")
        count = len([t for t in tasks if t.get("label_name") == gname and t.get("status") != "completed"])
        groups_with_counts.append({
            "name": gname,
            "emoji": emoji_map.get(g["id"], "\U0001f331"),
            "count": count,
        })

    return {
        "profile": profile,
        "name": profile.get("name", "\u0421\u0430\u0434\u043e\u0432\u043d\u0438\u043a"),
        "city": profile.get("companion_settings", {}).get("city", ""),
        "resonance": profile.get("resonance_level", 5),
        "ach_count": store_get_achievements_count(user_id),
        "sr": sr,
        "today_all": today_all,
        "today_s": today_s,
        "active_roadmaps": active_roadmaps,
        "groups_with_counts": groups_with_counts,
        "reminders": reminders,
    }


def _build_dashboard_main(data: dict) -> str:
    """Build main dashboard text from pre-collected data."""
    city_part = f" \u00b7 {data['city']}" if data["city"] else ""
    lines = [f"\U0001faac {data['name']}{city_part}", ""]

    # Today tasks
    if data["today_all"]:
        lines.append("\U0001f4c5 \u0421\u0435\u0433\u043e\u0434\u043d\u044f:")
        for t in data["today_all"]:
            ind = _deadline_indicator(t.get("deadline", ""))
            dl_label = "\u043f\u0440\u043e\u0441\u0440\u043e\u0447\u0435\u043d\u043e" if t.get("deadline", "") < data["today_s"] else "\u0441\u0435\u0433\u043e\u0434\u043d\u044f"
            lines.append(f"  {ind}\u00b7 {t['title']} \u00b7 {dl_label}")
        lines.append("")

    # Roadmaps
    if data["active_roadmaps"]:
        lines.append("\U0001f5fa \u0420\u043e\u0430\u0434\u043c\u0430\u043f\u044b:")
        for rd in data["active_roadmaps"]:
            rm = rd["rm"]
            lines.append(f"\U0001f5fa {rm['title']}  {rd['done_cnt']}/{rd['total']}  {rd['pct']}%")
            for t in rd["rm_today"]:
                ind = _deadline_indicator(t.get("deadline", ""))
                dl_label = "\u043f\u0440\u043e\u0441\u0440\u043e\u0447\u0435\u043d\u043e" if t.get("deadline", "") < data["today_s"] else "\u0441\u0435\u0433\u043e\u0434\u043d\u044f"
                lines.append(f"  \U0001f4c5 {ind}\u00b7 {t['title']} \u00b7 {dl_label}")
        lines.append("")

    return "\n".join(lines)


def _build_dashboard_keyboard_main(data: dict) -> InlineKeyboardMarkup:
    """Build main dashboard inline keyboard from pre-collected data."""
    kb = []

    # Row 1: Resonance + Achievements
    kb.append([
        InlineKeyboardButton(text=f"\U0001f4ab \u0420\u0435\u0437\u043e\u043d\u0430\u043d\u0441: {data['resonance']}%", callback_data="profile_resonance"),
        InlineKeyboardButton(text=f"\U0001f48e {data['ach_count']} \u0434\u043e\u0441\u0442\u0438\u0436\u0435\u043d\u0438\u0439", callback_data="profile_achievements"),
    ])

    # Row 2: 5 spheres
    sr = data["sr"]
    sphere_row = []
    for s in SPHERES:
        pct = sr.get(s, 20)
        sphere_row.append(InlineKeyboardButton(
            text=f"{SPHERE_EMOJI[s]} {pct}%",
            callback_data=f"profile_sphere_{s}"
        ))
    kb.append(sphere_row)

    # Today tasks as buttons
    for t in data["today_all"][:5]:
        ind = _deadline_indicator(t.get("deadline", ""))
        dl_label = "\u043f\u0440\u043e\u0441\u0440\u043e\u0447\u0435\u043d\u043e" if t.get("deadline", "") < data["today_s"] else "\u0441\u0435\u0433\u043e\u0434\u043d\u044f"
        kb.append([InlineKeyboardButton(
            text=f"\U0001f4c5 {ind}\u00b7 {t['title'][:30]} \u00b7 {dl_label}",
            callback_data=f"profile_today_{t.get('task_id','')}"
        )])
    if len(data["today_all"]) > 5:
        kb.append([InlineKeyboardButton(
            text=f"\U0001f4c5 \u0435\u0449\u0451 {len(data['today_all']) - 5} \u0437\u0430\u0434\u0430\u0447 \u0441\u0435\u0433\u043e\u0434\u043d\u044f",
            callback_data="profile_today_all"
        )])

    # Roadmaps as buttons
    for rd in data["active_roadmaps"]:
        rm = rd["rm"]
        kb.append([InlineKeyboardButton(
            text=f"\U0001f5fa {rm['title']}  {rd['done_cnt']}/{rd['total']}  {rd['pct']}%",
            callback_data=f"profile_rm_{rm.get('roadmap_id','')}"
        )])
        for t in rd["rm_today"]:
            ind = _deadline_indicator(t.get("deadline", ""))
            kb.append([InlineKeyboardButton(
                text=f"  \U0001f4c5 {ind}\u00b7 {t['title'][:28]}",
                callback_data=f"profile_today_{t.get('task_id','')}"
            )])

    # Groups
    for g in data["groups_with_counts"][:10]:
        kb.append([InlineKeyboardButton(
            text=f"{g['emoji']} {g['name']} ({g['count']})",
            callback_data=f"profile_group_{g['name']}"
        )])
    if len(data["groups_with_counts"]) > 10:
        kb.append([InlineKeyboardButton(
            text=f"\U0001f3a8 \u0435\u0449\u0451 {len(data['groups_with_counts']) - 10} \u0433\u0440\u0443\u043f\u043f",
            callback_data="profile_groups_all"
        )])

    # Reminders
    if data["reminders"]:
        for r in data["reminders"][:2]:
            dt = r.get("datetime_iso", "")[:16].replace("T", " ")
            kb.append([InlineKeyboardButton(
                text=f"\U0001f514 {r['title'][:25]} \u00b7 {dt}",
                callback_data=f"profile_rem_{r.get('id','')}"
            )])
        if len(data["reminders"]) > 2:
            kb.append([InlineKeyboardButton(
                text=f"\u2795 \u0435\u0449\u0451 {len(data['reminders']) - 2}",
                callback_data="profile_reminders"
            )])

    # Footer
    kb.append([
        InlineKeyboardButton(text="\u2139\ufe0f \u0418\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u044f", callback_data="profile_info"),
        InlineKeyboardButton(text="\U0001f4cb \u0427\u0442\u043e \u043d\u043e\u0432\u043e\u0433\u043e", callback_data="profile_changelog"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=kb)


async def _show_dashboard(user_id: str, message: Message):
    """Show interactive profile dashboard. Replaces old _show_profile."""
    data = _build_dashboard_data(user_id)
    text = _build_dashboard_main(data)
    kb = _build_dashboard_keyboard_main(data)
    await message.answer(text, reply_markup=kb)


async def _edit_dashboard(callback: CallbackQuery, text: str, kb: InlineKeyboardMarkup):
    """Edit dashboard message in place. Falls back to new message on error."""
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


# ─── Dashboard Callback Handlers ──────────────────────────────────────────────

@router.callback_query(F.data == "profile_resonance")
async def cb_profile_resonance(callback: CallbackQuery):
    await callback.answer()
    user_id = str(callback.from_user.id)
    sr = store_get_sphere_resonance(user_id)
    overall = (store_get_profile(user_id) or {}).get("resonance_level", 0)
    text = _sphere_detail_text(sr, overall)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2190 \u041d\u0430\u0437\u0430\u0434", callback_data="profile_collapse")]
    ])
    await _edit_dashboard(callback, text, kb)


@router.callback_query(F.data == "profile_achievements")
async def cb_profile_achievements(callback: CallbackQuery):
    await callback.answer()
    user_id = str(callback.from_user.id)
    ach_count = store_get_achievements_count(user_id)
    text = f"\U0001f48e {ach_count} \u0434\u043e\u0441\u0442\u0438\u0436\u0435\u043d\u0438\u0439\n"
    text += _build_sphere_stats(user_id, months=3)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2190 \u041d\u0430\u0437\u0430\u0434", callback_data="profile_collapse")]
    ])
    await _edit_dashboard(callback, text, kb)


@router.callback_query(F.data.startswith("profile_sphere_"))
async def cb_profile_sphere(callback: CallbackQuery):
    await callback.answer()
    user_id = str(callback.from_user.id)
    sphere = callback.data[len("profile_sphere_"):]
    sr = store_get_sphere_resonance(user_id)
    pct = sr.get(sphere, 20)
    bar = _sphere_progress_bar(pct)
    name = SPHERE_NAME_RU.get(sphere, sphere)
    emoji = SPHERE_EMOJI.get(sphere, "\U0001f331")

    tasks = store_get_tasks(user_id)
    sphere_tasks = [t for t in tasks if _classify_sphere(t.get("title",""), t.get("label_name","")) == sphere
                    and t.get("status") != "completed"]

    achievements = store_get_achievements(user_id)
    sphere_achs = [a for a in achievements if a.get("category") == sphere]

    lines = [
        f"{emoji} {name}: {pct}%",
        f"{bar} {pct}%",
        ""
    ]
    if sphere_tasks:
        lines.append("\u0417\u0430\u0434\u0430\u0447\u0438 \u0432 \u044d\u0442\u043e\u0439 \u0441\u0444\u0435\u0440\u0435:")
        for t in _sort_by_deadline(sphere_tasks)[:5]:
            ind = _deadline_indicator(t.get("deadline", ""))
            dl = f" \u00b7 {t['deadline']}" if t.get("deadline") else ""
            lines.append(f"  {ind}\u00b7 {t['title']}{dl}")
        lines.append("")
    if sphere_achs:
        lines.append("\u0414\u043e\u0441\u0442\u0438\u0436\u0435\u043d\u0438\u044f:")
        for a in sphere_achs[-3:]:
            lines.append(f"  \u00b7 {a.get('title', '\u2014')} (+{a.get('resonance_bonus', 3)}%)")
        lines.append("")

    if pct < 25:
        lines.append(f"\U0001f4a1 \u041c\u043e\u0436\u0435\u0442, \u0434\u043e\u0431\u0430\u0432\u0438\u043c \u0447\u0442\u043e-\u0442\u043e \u0434\u043b\u044f {name}?")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2190 \u041d\u0430\u0437\u0430\u0434", callback_data="profile_collapse")]
    ])
    await _edit_dashboard(callback, "\n".join(lines), kb)


@router.callback_query(F.data.startswith("profile_rm_"))
async def cb_profile_roadmap(callback: CallbackQuery):
    await callback.answer()
    user_id = str(callback.from_user.id)
    rm_id = callback.data[len("profile_rm_"):]
    roadmaps = store_get_roadmaps(user_id)
    rm = next((r for r in roadmaps if r.get("roadmap_id") == rm_id), None)
    if not rm:
        await callback.answer("\u0420\u043e\u0430\u0434\u043c\u0430\u043f \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d", show_alert=True)
        return

    all_tasks = store_get_tasks(user_id)
    text = _roadmap_card_text(rm, all_tasks)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2190 \u041d\u0430\u0437\u0430\u0434", callback_data="profile_collapse")]
    ])
    await _edit_dashboard(callback, text, kb)


@router.callback_query(F.data == "profile_info")
async def cb_profile_info(callback: CallbackQuery):
    await callback.answer()
    text = (
        "\U0001f331 \u042f \u2014 \u0421\u0420, \u0442\u0432\u043e\u0439 \u043a\u043e\u043c\u043f\u0430\u043d\u044c\u043e\u043d \u0432 \u0441\u0430\u0434\u0443.\n\n"
        "\u0423\u043c\u0435\u044e \u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c \u0441:\n"
        "\U0001f4cb \u0417\u0430\u0434\u0430\u0447\u0430\u043c\u0438 \u0438 \u0433\u0440\u0443\u043f\u043f\u0430\u043c\u0438\n"
        "\U0001f5fa \u0420\u043e\u0430\u0434\u043c\u0430\u043f\u0430\u043c\u0438 (\u043a\u0440\u0443\u043f\u043d\u044b\u0435 \u0446\u0435\u043b\u0438)\n"
        "\u2611\ufe0f \u0427\u0435\u043a\u043b\u0438\u0441\u0442\u0430\u043c\u0438\n"
        "\U0001f514 \u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f\u043c\u0438\n"
        "\U0001f48e \u0414\u043e\u0441\u0442\u0438\u0436\u0435\u043d\u0438\u044f\u043c\u0438\n"
        "\U0001f52e \u0420\u0435\u0437\u043e\u043d\u0430\u043d\u0441\u043e\u043c \u0441\u0444\u0435\u0440\n"
        "\U0001f310 \u041f\u043e\u0438\u0441\u043a\u043e\u043c\n\n"
        "\U0001f9e0 \u0416\u0438\u0432\u0430\u044f \u043f\u0430\u043c\u044f\u0442\u044c\n"
        "\u042f \u043d\u0430\u0431\u043b\u044e\u0434\u0430\u044e \u0437\u0430 \u0442\u043e\u0431\u043e\u0439 \u0438\u0437 \u0434\u0438\u0430\u043b\u043e\u0433\u043e\u0432 \u0438 \u0437\u0430\u0434\u0430\u0447 \u2014 \u0438 \u0441\u0442\u0430\u043d\u043e\u0432\u043b\u044e\u0441\u044c \u0442\u043e\u0447\u043d\u0435\u0435.\n\n"
        "\U0001f4f1 <b>\u041a\u0430\u043a \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u044c\u0441\u044f \u0434\u0430\u0448\u0431\u043e\u0440\u0434\u043e\u043c:</b>\n"
        "\u00b7 \u041d\u0430\u0436\u0438\u043c\u0430\u0439 \u043d\u0430 \u043a\u043d\u043e\u043f\u043a\u0438 \u0447\u0442\u043e\u0431\u044b \u0440\u0430\u0441\u043a\u0440\u044b\u0442\u044c \u0434\u0435\u0442\u0430\u043b\u0438\n"
        "\u00b7 \u0417\u0430\u0434\u0430\u0447\u0438 \u0438 \u0433\u0440\u0443\u043f\u043f\u044b \u2014 \u043f\u0438\u0448\u0438 \u0432 \u0447\u0430\u0442 \u0447\u0442\u043e \u043d\u0443\u0436\u043d\u043e \u0441\u0434\u0435\u043b\u0430\u0442\u044c\n"
        "\u00b7 \u0412\u0441\u0451 \u043c\u043e\u0436\u043d\u043e \u0433\u043e\u043b\u043e\u0441\u043e\u043c \u0438\u043b\u0438 \u0442\u0435\u043a\u0441\u0442\u043e\u043c\n\n"
        "\u041f\u0440\u043e\u0441\u0442\u043e \u0441\u043a\u0430\u0436\u0438 \u0447\u0442\u043e \u043d\u0443\u0436\u043d\u043e \U0001f33f"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2190 \u041d\u0430\u0437\u0430\u0434", callback_data="profile_collapse")]
    ])
    await _edit_dashboard(callback, text, kb)


@router.callback_query(F.data == "profile_changelog")
async def cb_profile_changelog(callback: CallbackQuery):
    await callback.answer()
    upd = BOT_LATEST_UPDATE
    lines = [f"\U0001f4cb \u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435 v{upd['version']} \u00b7 {upd['date']}\n"]
    if upd.get("features"):
        lines.append("\u041d\u043e\u0432\u043e\u0435:")
        for feat in upd["features"]:
            lines.append(f"  \u00b7 {feat}")
    if upd.get("fixes"):
        lines.append("\n\u0418\u0441\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e:")
        for fix in upd["fixes"]:
            lines.append(f"  \u00b7 {fix}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2190 \u041d\u0430\u0437\u0430\u0434", callback_data="profile_collapse")]
    ])
    await _edit_dashboard(callback, "\n".join(lines), kb)


@router.callback_query(F.data == "profile_reminders")
async def cb_profile_reminders_expand(callback: CallbackQuery):
    await callback.answer()
    user_id = str(callback.from_user.id)
    reminders = store_get_reminders(user_id)
    text = _reminder_list_text(reminders)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2190 \u041d\u0430\u0437\u0430\u0434", callback_data="profile_collapse")]
    ])
    await _edit_dashboard(callback, text, kb)


@router.callback_query(F.data == "profile_collapse")
async def cb_profile_collapse(callback: CallbackQuery):
    """Return to main dashboard view."""
    await callback.answer()
    user_id = str(callback.from_user.id)
    data = _build_dashboard_data(user_id)
    text = _build_dashboard_main(data)
    kb = _build_dashboard_keyboard_main(data)
    await _edit_dashboard(callback, text, kb)


# ─── Send-to-chat handlers ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("profile_today_"))
async def cb_profile_today_task(callback: CallbackQuery):
    await callback.answer()
    task_id = callback.data[len("profile_today_"):]
    user_id = str(callback.from_user.id)
    tasks = store_get_tasks(user_id)
    task = next((t for t in tasks if t.get("task_id") == task_id), None)
    if task:
        await callback.message.answer(f"\u0437\u0430\u0434\u0430\u0447\u0430 {task['title']}", reply_markup=get_main_keyboard())
    else:
        await callback.answer("\u0417\u0430\u0434\u0430\u0447\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430", show_alert=True)


@router.callback_query(F.data.startswith("profile_group_"))
async def cb_profile_group(callback: CallbackQuery):
    await callback.answer()
    group_name = callback.data[len("profile_group_"):]
    await callback.message.answer(f"\u043f\u043e\u043a\u0430\u0436\u0438 \u0433\u0440\u0443\u043f\u043f\u0443 {group_name}", reply_markup=get_main_keyboard())


@router.callback_query(F.data.startswith("profile_rem_"))
async def cb_profile_reminder(callback: CallbackQuery):
    await callback.answer()
    rem_id = callback.data[len("profile_rem_"):]
    user_id = str(callback.from_user.id)
    reminders = store_get_reminders(user_id)
    rem = next((r for r in reminders if r.get("id") == rem_id), None)
    if rem:
        await callback.message.answer(f"\u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435 {rem['title']}", reply_markup=get_main_keyboard())
    else:
        await callback.answer("\u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e", show_alert=True)


@router.callback_query(F.data == "profile_today_all")
async def cb_profile_today_all(callback: CallbackQuery):
    """Show all today tasks inline."""
    await callback.answer()
    user_id = str(callback.from_user.id)
    data = _build_dashboard_data(user_id)

    lines = ["\U0001f4c5 \u0421\u0435\u0433\u043e\u0434\u043d\u044f (\u0432\u0441\u0435):"]
    for t in data["today_all"]:
        ind = _deadline_indicator(t.get("deadline", ""))
        dl_label = "\u043f\u0440\u043e\u0441\u0440\u043e\u0447\u0435\u043d\u043e" if t.get("deadline", "") < data["today_s"] else "\u0441\u0435\u0433\u043e\u0434\u043d\u044f"
        lines.append(f"  {ind}\u00b7 {t['title']} \u00b7 {dl_label}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2190 \u041d\u0430\u0437\u0430\u0434", callback_data="profile_collapse")]
    ])
    await _edit_dashboard(callback, "\n".join(lines), kb)


@router.callback_query(F.data == "profile_groups_all")
async def cb_profile_groups_all(callback: CallbackQuery):
    """Show all groups inline."""
    await callback.answer()
    user_id = str(callback.from_user.id)
    data = _build_dashboard_data(user_id)

    lines = ["\U0001f3a8 \u0412\u0441\u0435 \u0433\u0440\u0443\u043f\u043f\u044b:"]
    for g in data["groups_with_counts"]:
        lines.append(f"  {g['emoji']} {g['name']} ({g['count']})")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2190 \u041d\u0430\u0437\u0430\u0434", callback_data="profile_collapse")]
    ])
    await _edit_dashboard(callback, "\n".join(lines), kb)
'''

    # Find insertion point before _roadmap_card_text
    insert_marker = 'def _roadmap_card_text(rm: dict, all_tasks: list) -> str:'
    insert_pos = content.find(insert_marker)
    if insert_pos == -1:
        print("❌ Insertion point not found (_roadmap_card_text)")
        return False

    func_start = content.rfind('\n', 0, insert_pos) + 1
    content = content[:func_start] + dashboard_code + '\n' + content[func_start:]
    changes += 1
    print("✅ 3/8 Added dashboard system (data builder + text + keyboard + handlers)")

    # ═══════════════════════════════════════════════════════════════════════
    # 4. Update cmd_profile to use dashboard
    # ═══════════════════════════════════════════════════════════════════════
    old_cmd = '@router.message(Command("profile"))\n@router.message(F.text == "🌾 Профиль")\nasync def cmd_profile(message: Message, state: FSMContext = None):\n    user_id = str(message.from_user.id)\n    await _show_profile(user_id, message)'
    new_cmd = '@router.message(Command("profile"))\n@router.message(F.text == "🌾 Профиль")\nasync def cmd_profile(message: Message, state: FSMContext = None):\n    user_id = str(message.from_user.id)\n    await _show_dashboard(user_id, message)'

    if old_cmd in content:
        content = content.replace(old_cmd, new_cmd, 1)
        changes += 1
        print("✅ 4/8 Updated cmd_profile → _show_dashboard")
    else:
        print("❌ cmd_profile pattern not found")
        return False

    # ═══════════════════════════════════════════════════════════════════════
    # 5. Update btn_profile to use dashboard
    # ═══════════════════════════════════════════════════════════════════════
    old_btn = '@router.message(F.text == "👤 Профиль")\nasync def btn_profile(message: Message, state: FSMContext):\n    user_id = str(message.from_user.id)\n    _track_interaction(user_id)\n    if not is_authorized(user_id):\n        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())\n        return\n    if user_id in _menu_messages:\n        try:\n            await message.bot.delete_message(message.chat.id, _menu_messages[user_id])\n        except Exception:\n            pass\n    card = _build_profile_card(user_id)\n    kb = InlineKeyboardMarkup(inline_keyboard=[\n        [InlineKeyboardButton(text="✏️ Изменить профиль", callback_data="menu_edit_profile")],\n    ])\n    sent = await message.answer(card, reply_markup=kb)\n    _menu_messages[user_id] = sent.message_id'

    new_btn = '@router.message(F.text == "👤 Профиль")\nasync def btn_profile(message: Message, state: FSMContext):\n    user_id = str(message.from_user.id)\n    _track_interaction(user_id)\n    if not is_authorized(user_id):\n        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())\n        return\n    await _show_dashboard(user_id, message)'

    if old_btn in content:
        content = content.replace(old_btn, new_btn, 1)
        changes += 1
        print("✅ 5/8 Updated btn_profile → _show_dashboard")
    else:
        print("❌ btn_profile pattern not found")
        return False

    # ═══════════════════════════════════════════════════════════════════════
    # 6. Update show_tasks intent (period=="all") to use dashboard
    # ═══════════════════════════════════════════════════════════════════════
    old_show_all = 'elif period == "all" or not period:\n                                # No filter — show profile (tasks embedded there)\n                                await _show_profile(user_id, message)'
    new_show_all = 'elif period == "all" or not period:\n                                # No filter — show dashboard\n                                await _show_dashboard(user_id, message)'

    if old_show_all in content:
        content = content.replace(old_show_all, new_show_all, 1)
        changes += 1
        print("✅ 6/8 Updated show_tasks intent → _show_dashboard")
    else:
        print("⚠️ show_tasks intent pattern not found (may use different formatting)")

    # ═══════════════════════════════════════════════════════════════════════
    # 7. Remove get_profile_inline
    # ═══════════════════════════════════════════════════════════════════════
    old_inline = 'def get_profile_inline() -> InlineKeyboardMarkup:\n    return InlineKeyboardMarkup(inline_keyboard=[\n        [InlineKeyboardButton(text="✏️ Изменить профиль", callback_data="menu_edit_profile")],\n    ])\n\n\n'

    if old_inline in content:
        content = content.replace(old_inline, '', 1)
        changes += 1
        print("✅ 7/8 Removed get_profile_inline()")
    else:
        print("⚠️ get_profile_inline not found")

    # ═══════════════════════════════════════════════════════════════════════
    # 8. Update _show_profile calls to _show_dashboard
    # ═══════════════════════════════════════════════════════════════════════
    old_call = "await _show_profile(user_id, message)"
    new_call = "await _show_dashboard(user_id, message)"
    count = content.count(old_call)
    content = content.replace(old_call, new_call)
    if count > 0:
        changes += 1
        print(f"✅ 8/8 Updated {count} _show_profile → _show_dashboard calls")
    else:
        print("⚠️ No _show_profile calls found to replace")

    # ═══════════════════════════════════════════════════════════════════════
    # Write back
    # ═══════════════════════════════════════════════════════════════════════
    with open(BOT_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n✅ Patch 21 applied ({changes} changes)")
    print("   Dashboard: interactive profile with inline expansion")
    print("   Removed: ℹ️ button from main menu")
    print("   Single data pass for text + keyboard")
    print("   edit_text for inline views")
    return True


if __name__ == "__main__":
    success = patch()
    sys.exit(0 if success else 1)