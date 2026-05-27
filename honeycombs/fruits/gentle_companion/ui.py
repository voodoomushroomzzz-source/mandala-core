# -*- coding: utf-8 -*-
"""
ui.py -- UI Layer. Phase: 4.
"""

def _sphere_compact_line(sr: dict) -> str:
    """One-line compact for profile card: 🌿 22%  🔥 45%  💼 38%  🤝 20%  🌱 15%"""
    return "  ".join(f"{SPHERE_EMOJI[s]} {sr.get(s, 20)}%" for s in SPHERES)

def _reminder_list_text(reminders: list) -> str:
    """Build reminder list text for auto-show after create/delete."""
    if not reminders:
        return "🔔 Напоминаний нет."
    lines = [f"🔔 <b>Напоминания ({len(reminders)}):</b>"]
    for r in reminders:
        dt_iso = r.get("datetime_iso","")
        # Strip timezone offset for display: "2026-05-05T13:00+05:00" → "2026-05-05 13:00"
        if "+" in dt_iso:
            dt = dt_iso[:16].replace("T"," ")
        elif dt_iso.endswith("Z"):
            dt = dt_iso[:-1][:16].replace("T"," ")
        else:
            dt = dt_iso[:16].replace("T"," ")
        rep = {"once":"1×","daily":"ежедн.","weekdays":"пн-пт"}.get(r.get("repeat","once"),"1×")
        lines.append(f"  🔔 {r['title']} · {dt} ({rep})")
    return "\n".join(lines)

def _sphere_progress_bar(pct: int) -> str:
    filled = round(pct / 10)
    return "█" * filled + "░" * (10 - filled)

def _sphere_detail_text(sr: dict, overall: int) -> str:
    """Multi-line detail dashboard for show_resonance_detail."""
    lines = [f"🔮 <b>Резонанс: {overall}%</b>\n"]
    for s in SPHERES:
        pct  = sr.get(s, 20)
        bar  = _sphere_progress_bar(pct)
        name = SPHERE_NAME_RU[s]
        emoji = SPHERE_EMOJI[s]
        lines.append(f"{emoji} {name:<14} {pct}%  {bar}")
    weak = [SPHERE_NAME_RU[s] for s in SPHERES if sr.get(s, 20) < 25]
    if weak:
        lines.append(f"\n💡 {' и '.join(weak)} {'требует' if len(weak)==1 else 'требуют'} внимания")
    return "\n".join(lines)



class GardenOnboardingStates(StatesGroup):
    waiting_for_consent = State()
    waiting_for_name   = State()
    waiting_for_gender = State()  # added v7.28.x
    waiting_for_city   = State()
    waiting_for_birthday = State()
    waiting_for_morning  = State()
    done = State()

class EditProfileStates(StatesGroup):
    waiting_for_new_name     = State()
    waiting_for_new_gender   = State()  # added v7.28.x
    waiting_for_new_city     = State()
    waiting_for_new_birthday = State()
    waiting_for_new_morning  = State()
    # waiting_for_new_body/spirit/world removed in v7.24.5


class AchievementStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_bonus = State()

class TaskStates(StatesGroup):
    waiting_for_title           = State()
    waiting_for_deadline        = State()
    waiting_for_custom_deadline = State()
    waiting_for_reminder        = State()
    waiting_for_custom_reminder = State()
    waiting_for_group           = State()
    waiting_for_new_group       = State()
    waiting_for_repeat               = State()  # Патчер А: шаг выбора повтора
    waiting_for_repeat_custom_days   = State()  # H: ввод дней недели
    waiting_for_repeat_custom_date   = State()  # H: ввод своей даты
    waiting_for_confirm              = State()

class TaskEditStates(StatesGroup):
    waiting_for_field        = State()   # field selector shown
    editing_title            = State()
    editing_deadline         = State()
    waiting_for_custom_deadline = State()  # free-text custom date input
    editing_reminder         = State()
    editing_group            = State()
    editing_place            = State()

class ChecklistStates(StatesGroup):
    waiting_for_title     = State()
    waiting_for_items     = State()
    waiting_for_item_edit = State()  # for editing a specific item text

class ReminderStates(StatesGroup):
    waiting_for_input = State()
    waiting_for_repeat = State()  # v7.37 — выбор повторения
    waiting_for_weekdays = State()  # v7.40 — текстовый ввод дней недели

class AskStates(StatesGroup):
    waiting_for_question = State()

class LeaveStates(StatesGroup):
    waiting_for_confirm = State()
    waiting_for_delete_confirm_1 = State()
    waiting_for_delete_confirm_2 = State()

# ─── Keyboards ────────────────────────────────────────────────────────────────


# ─── Profile card builder ─────────────────────────────────────────────────────

# Keyword → emoji mapping for groups


_GROUP_EMOJI_MAP = [
    (["здоровье","врач","медиц","лечени"],                        "🌿"),
    (["спорт","тренировк","фитнес","бег","зал","физ"],            "🏃"),
    (["работа","проект","бот","код","разраб","dev","программ"],   "💻"),
    (["учёба","книга","курс","знания","учить","читать","образован"],"📚"),
    (["дом","быт","уборка","кухня","квартира","ремонт"],          "🏠"),
    (["друг","встреч","общени","знаком","семья"],                 "🤝"),
    (["путешеств","поездка","отель","тревел","тур"],              "✈️"),
    (["деньги","финанс","бюджет","доход","расход"],               "💰"),
    (["творчество","арт","дизайн","рисован"],                     "🎨"),
    (["музыка","песня","инструмент","звук"],                      "🎵"),
    (["фото","видео","съёмка","контент","блог"],                  "📷"),
    (["еда","питание","кафе","ресторан","готовк"],                "🍽"),
    (["медитац","духовн","практик","осознан","йога"],             "🧘"),
    (["авто","машина","транспорт","мотоцикл"],                    "🚗"),
    (["мандала","симбиоз","резонанс","сад","рост"],               "🌀"),
    (["личное","личн","себя","мой","моё"],                        "🔮"),
    (["покупк","магазин","шопинг","заказ"],                       "🛒"),
    (["игры","игра","геймин","steam"],                            "🎮"),
    (["наука","исследован","эксперимент","анализ"],               "🔬"),
    (["люди","коллег","команда","нетворк"],                       "🌐"),
]
_GROUP_FALLBACK_POOL = ["⚡","🎯","🔑","💡","🌊","🏔","🦋","🌙","⭐","🔥","🌸","🪐","🧩","🏅","🎪"]



def _group_emoji(name: str) -> str:
    """Return emoji for a group name based on keywords."""
    n = name.lower()
    for keywords, emoji in _GROUP_EMOJI_MAP:
        if any(k in n for k in keywords):
            return emoji
    return ""  # Will use fallback pool

def _label_emoji(name: str) -> str:
    """Alias kept for backwards compat."""
    return _group_emoji(name) or "🌱"

def _assign_group_emojis(groups: list) -> dict:
    """Assign unique emojis to a list of groups. Returns {group_id: emoji}."""
    used = set()
    result = {}
    fallback = list(_GROUP_FALLBACK_POOL)
    # First pass: assign keyword-based emojis if unique
    for g in groups:
        e = _group_emoji(g.get("name", ""))
        if e and e not in used:
            result[g["id"]] = e
            used.add(e)
        else:
            result[g["id"]] = None  # will fill from fallback
    # Second pass: fill unassigned from fallback pool
    for g in groups:
        if result[g["id"]] is None:
            for fb in fallback:
                if fb not in used:
                    result[g["id"]] = fb
                    used.add(fb)
                    break
            else:
                result[g["id"]] = "🌱"  # absolute last resort
    return result

def _build_profile_card(user_id: str) -> str:
    profile    = store_get_profile(user_id) or {}
    all_tasks  = store_get_tasks(user_id)
    name       = profile.get("name", "Садовник")
    resonance  = profile.get("resonance_level", 0)
    city       = profile.get("companion_settings", {}).get("city", "")
    ach_count  = store_get_achievements_count(user_id)
    city_part  = f" · {city}" if city else ""
    lines = [
        f"🪬 <b>{name}</b>{city_part}",
        f"💫 Резонанс: {resonance}%  💎 {ach_count} достижений",
        _sphere_compact_line(store_get_sphere_resonance(user_id)),
        "",
    ]

    # ── Resolve today in gardener timezone ─
    from datetime import datetime as _dt_rem
    from zoneinfo import ZoneInfo as _ZI_rem
    tz_name = profile.get("companion_settings", {}).get("timezone", "Europe/Moscow")
    try:
        tz_rem = _ZI_rem(tz_name)
    except Exception:
        tz_rem = _ZI_rem("Europe/Moscow")
    today_rem = _dt_rem.now(tz_rem).strftime("%Y-%m-%d")

    # ── Tasks today block ────────────────────────────────────────────────

    active_all = [t for t in all_tasks if t.get("status") != "completed"]
    total_tasks = len(active_all)
    # Ближайшие 5 задач по дедлайну (сначала просроченные и сегодня, потом будущие, потом без дедлайна)
    def _task_sort_key(t):
        dl = t.get("deadline")
        return (0, dl) if dl and dl <= today_rem else (1, dl or "9999")
    nearest_tasks = sorted(active_all, key=_task_sort_key)[:7]
    shown_tasks = len(nearest_tasks)
    lines.append(f"📋 <b>Ближайшие задачи</b> {shown_tasks}/{total_tasks}")
    for t in nearest_tasks:
        ind = _deadline_indicator(t.get("deadline", ""), tz_name)
        dl  = f" · {t['deadline']}" if t.get("deadline") else ""
        _rep_icon = " 🔁" if t.get("repeat") and t.get("repeat") != "once" else ""
        lines.append(f"  · {ind}{t['title']}{_rep_icon}{dl}")
    if not nearest_tasks:
        lines.append("  · задач нет 🌱")
    lines.append("")

    # ── Reminders block ──────────────────────────────────────────────────
    reminders = store_get_reminders(user_id)
    active_reminders = [r for r in reminders if r.get("active", True)]
    total_rem = len(active_reminders)
    # 3 ближайших по datetime_iso
    nearest_rem = sorted(
        active_reminders,
        key=lambda r: (r.get("datetime_iso") or "9999")
    )[:5]
    shown_rem = len(nearest_rem)
    lines.append(f"🔔 <b>Ближайшие напоминания</b> {shown_rem}/{total_rem}")
    for r in nearest_rem:
        dt = (r.get("datetime_iso","") or "")
        time_part = dt[11:16] if len(dt) >= 16 and dt[10] == "T" else ""
        date_part = dt[:10] if len(dt) >= 10 else ""
        when = f" · {date_part} {time_part}".strip() if date_part else ""
        _r_rep = r.get("repeat", "once")
        _r_rep_icon = " 🔁" if _r_rep and _r_rep != "once" else ""
        lines.append(f"  · {r['title']}{_r_rep_icon}{when}")
    if not nearest_rem:
        lines.append("  · напоминаний нет 🌱")

    return "\n".join(lines)


# ─── Unified action functions (single source of truth for all interfaces) ─────

async def _show_profile(user_id: str, message: Message):
    """Show profile card — used by button, command, voice, intent."""
    # Delete previous profile message to keep chat clean
    prev_mid = _profile_messages.get(user_id)
    if prev_mid:
        try:
            await message.bot.delete_message(message.chat.id, prev_mid)
        except Exception:
            pass
    card = _build_profile_card(user_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Задачи 🚀", callback_data="menu_tasks_mgmt_v2"),
        ],
        [
            InlineKeyboardButton(text="☑️ Чеклисты", callback_data="menu_checklists_mgmt"),
            InlineKeyboardButton(text="🔔 Напоминания", callback_data="menu_reminders_mgmt"),
        ],
        [
            InlineKeyboardButton(text="✏️ Профиль", callback_data="menu_edit_profile"),
            InlineKeyboardButton(text="💎 Достижения", callback_data="profile_achievements"),
        ]
    ])
    sent = await message.answer(card, reply_markup=kb)
    _profile_messages[user_id] = sent.message_id

async def _show_tasks_unified(user_id: str, message: Message, period: str = "labels"):
    """Show tasks — used by button, command, voice, intent."""
    tasks  = store_get_tasks(user_id)
    active = [t for t in tasks if t.get("status") != "completed"]
    if not active:
        await message.answer("🌀 Активных задач нет.", reply_markup=get_main_keyboard())
        await message.answer("👇", reply_markup=get_tasks_keyboard())
        return
    # Filtered periods
    if period not in ("labels", "mkb", "all"):
        filtered = _filter_tasks_by_period(tasks, period)
        period_ru = {
            "today":    "📅 Сегодня",
            "tomorrow": "📅 Завтра",
            "day_after":"📅 Послезавтра",
            "week":     "📅 На неделе",
            "month":    "📅 В этом месяце",
            "overdue":  "⚠️ Просроченные",
        }.get(period, "🌀 Задачи")
        if not filtered:
            await message.answer(f"{period_ru}: задач нет 🌱", reply_markup=get_main_keyboard())
            return
        lines = [f"<b>{period_ru}:</b>"]
        for t in _sort_by_deadline(filtered):
            dl  = f" · {t['deadline']}" if t.get("deadline") else ""
            grp = f" #{t['label_name']}" if t.get("label_name") else ""
            ind = _deadline_indicator(t.get("deadline", ""))
            lines.append(f"  • {ind}{t['title']}{grp}{dl}")
        await message.answer("\n".join(lines), reply_markup=get_main_keyboard())
        return
    # Standard grouped view
    view = "mkb" if period == "mkb" else "labels"
    body = _format_tasks_labels(active, user_id)
    header = "🌀 <b>Задачи · Группы:</b>"
    await message.answer(header + "\n\n" + body)


# ═══════════════════════════════════════════════════════════════════════════════
# P-13a: Меню Задач v2 — группы + список задач внутри группы + repeat
# ═══════════════════════════════════════════════════════════════════════════════

def _task_urgency_emoji(deadline: str, tz_name: str = "Europe/Moscow") -> str:
    if not deadline:
        return "\U0001f331"  # 🌱
    from datetime import datetime as _dt_urg, timedelta as _td_urg
    from zoneinfo import ZoneInfo as _ZI_urg
    try:
        _tz_urg = _ZI_urg(tz_name)
    except Exception:
        _tz_urg = _ZI_urg("Europe/Moscow")
    _now_urg = _dt_urg.now(_tz_urg)
    today = _now_urg.strftime("%Y-%m-%d")
    day_after = (_now_urg + _td_urg(days=2)).strftime("%Y-%m-%d")
    if deadline <= today:
        return "\U0001f525"  # 🔥
    if deadline < day_after:
        return "\u26a1"  # ⚡
    return "\U0001f331"  # 🌱


def _sort_tasks_smart(tasks: list) -> list:
    from datetime import datetime as _dt_st, timedelta as _td_st
    today = _dt_st.now().strftime("%Y-%m-%d")
    tomorrow = (_dt_st.now() + _td_st(days=1)).strftime("%Y-%m-%d")
    def key(t):
        dl = t.get("deadline")
        if not dl:
            return (4, "9999")
        if dl < today:
            return (0, dl)
        if dl == today:
            return (1, dl)
        if dl == tomorrow:
            return (2, dl)
        return (3, dl)
    return sorted(tasks, key=key)



def get_groups_list_inline(user_id: str) -> InlineKeyboardMarkup:
    groups_data = store_get_groups(user_id).get("groups", [])
    all_tasks = store_get_tasks(user_id)
    active = [t for t in all_tasks if t.get("status") != "completed"]
    by_group = {}
    for t in active:
        gname = t.get("label_name") or ""
        by_group.setdefault(gname, []).append(t)
    emoji_map = _assign_group_emojis(groups_data)
    btns = []
    for g in groups_data:
        gname = g["name"]
        gid = g["id"]
        count = len(by_group.get(gname, []))
        emoji = emoji_map.get(gid, "\U0001f4c2")
        btns.append([
            InlineKeyboardButton(
                text=f"{emoji} {gname} ({count})",
                callback_data=f"tgroup_open|{gid}"
            ),
        ])
    no_group_tasks = [t for t in active if not t.get("label_name")]
    btns.append([
        InlineKeyboardButton(
            text=f"\U0001f4c2 \u0411\u0435\u0437 \u0433\u0440\u0443\u043f\u043f\u044b ({len(no_group_tasks)})",
            callback_data="tgroup_open|__nogroup__",
        ),
    ])
    btns.append([InlineKeyboardButton(text="➕ Новая задача", callback_data="ttask_create|__new__")])
    btns.append([InlineKeyboardButton(text="➕ Новая группа", callback_data="tgroup_create")])
    btns.append([InlineKeyboardButton(text="← Назад в профиль", callback_data="profile_back")])
    return InlineKeyboardMarkup(inline_keyboard=btns)


def get_tasks_in_group_inline(user_id: str, group_id: str) -> InlineKeyboardMarkup:
    all_tasks = store_get_tasks(user_id)
    groups_data = store_get_groups(user_id).get("groups", [])
    if group_id == "__nogroup__":
        group_name = "\u0411\u0435\u0437 \u0433\u0440\u0443\u043f\u043f\u044b"
        tasks = [t for t in all_tasks if t.get("status") != "completed" and not t.get("label_name")]
    else:
        group = next((g for g in groups_data if g["id"] == group_id), None)
        group_name = group["name"] if group else "\u0413\u0440\u0443\u043f\u043f\u0430"
        tasks = [t for t in all_tasks if t.get("status") != "completed" and t.get("label_id") == group_id]
    tasks = _sort_tasks_smart(tasks)
    _tz_gi = (store_get_profile(user_id) or {}).get("companion_settings", {}).get("timezone", "Europe/Moscow")
    btns = []
    for t in tasks:
        tid = t.get("task_id", "")
        title = t.get("title", "-")[:28]
        dl = t.get("deadline", "")
        dl_short = f" \u00b7 {dl}" if dl else ""
        emoji = _task_urgency_emoji(dl, _tz_gi)
        repeat_str = " \U0001f501" if t.get("repeat") else ""
        label = f"{emoji} {title}{repeat_str}{dl_short}"
        btns.append([InlineKeyboardButton(text=label, callback_data=f"ttask_edit|{tid}")])
    if group_id != "__nogroup__":
        btns.append([InlineKeyboardButton(text="\u270f\ufe0f \u041f\u0435\u0440\u0435\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443", callback_data=f"tgroup_edit|{group_id}")])
        btns.append([InlineKeyboardButton(text="➕ Новая задача", callback_data=f"tgroup_newtask|{group_id}")])
        btns.append([InlineKeyboardButton(text="\U0001f5d1 \u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443", callback_data=f"tgroup_delete|{group_id}")])
    btns.append([InlineKeyboardButton(text="\u2190 \u041d\u0430\u0437\u0430\u0434 \u043a \u0433\u0440\u0443\u043f\u043f\u0430\u043c", callback_data="tgroup_back_to_list")])
    return InlineKeyboardMarkup(inline_keyboard=btns)


def get_task_edit_inline(user_id: str, task_id: str) -> InlineKeyboardMarkup:
    tasks = store_get_tasks(user_id)
    task = next((t for t in tasks if t.get("task_id") == task_id), None)
    if not task:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u2190 \u041d\u0430\u0437\u0430\u0434", callback_data="tgroup_back_to_list")]
        ])
    repeat_label = _repeat_label(task.get("repeat") or "once")
    place_label = task.get("label_name") or "\u0411\u0435\u0437 \u0433\u0440\u0443\u043f\u043f\u044b"
    back_cb = f"tgroup_open|{task.get('label_id') or '__nogroup__'}"
    _te_title = task.get("title", "-")
    _te_dl    = task.get("deadline") or "\u043d\u0435\u0442"
    btns = [
        [InlineKeyboardButton(
            text=f"\u2705 \u0412\u044b\u043f\u043e\u043b\u043d\u0438\u0442\u044c: {_te_title[:25]}",
            callback_data=f"ttask_done|{task_id}"
        )],
        [InlineKeyboardButton(
            text=f"\u270f\ufe0f \u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435: {_te_title[:28]}",
            callback_data=f"ttask_edit_field|{task_id}|title"
        )],
        [InlineKeyboardButton(
            text=f"\U0001f4c5 \u0414\u0435\u0434\u043b\u0430\u0439\u043d: {_te_dl}",
            callback_data=f"ttask_edit_field|{task_id}|deadline"
        )],
        [InlineKeyboardButton(
            text=f"\U0001f4cc \u041c\u0435\u0441\u0442\u043e: {place_label}",
            callback_data=f"ttask_edit_field|{task_id}|place"
        )],
        [InlineKeyboardButton(
            text=f"\U0001f501 \u041f\u043e\u0432\u0442\u043e\u0440: {repeat_label}",
            callback_data=f"ttask_edit_field|{task_id}|repeat"
        )],
        [InlineKeyboardButton(
            text=f"🔔 Напоминание: {task.get('reminder') or 'нет'}",
            callback_data=f"ttask_edit_field|{task_id}|reminder"
        )],
        [InlineKeyboardButton(
            text="🗑 Удалить задачу",
            callback_data=f"ttask_delete|{task_id}"
        )],
        [InlineKeyboardButton(text="← Назад к списку", callback_data=back_cb)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=btns)

# ─── Place picker ─────────────────────────────────────────────────────────────

def get_place_keyboard(user_id: str, task_id: str) -> InlineKeyboardMarkup:
    groups = store_get_groups(user_id).get("groups", [])
    emoji_map = _assign_group_emojis(groups)
    btns = []
    _plc_folder = "\U0001f4c2"
    for g in groups:
        _plc_em = emoji_map.get(g["id"], _plc_folder)
        _plc_nm = g["name"]
        btns.append([InlineKeyboardButton(
            text=f"{_plc_em} {_plc_nm}",
            callback_data=f"plc_grp|{g['id']}"
        )])
    btns.append([InlineKeyboardButton(
        text="\U0001f4c2 \u0411\u0435\u0437 \u0433\u0440\u0443\u043f\u043f\u044b",
        callback_data="plc_grp|__nogroup__"
    )])
    btns.append([InlineKeyboardButton(
        text="\u2190 \u041d\u0430\u0437\u0430\u0434",
        callback_data=f"ttask_edit|{task_id}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=btns)



def get_checklist_inline(checklist: dict) -> InlineKeyboardMarkup:
    """Build inline keyboard for a checklist — numbered items, checkbox on right."""
    cid   = checklist["id"]
    items = checklist.get("items", [])
    btns  = []
    for i, it in enumerate(items, 1):
        iid  = it["id"]
        mark = "✅" if it.get("done") else "☐"
        text = f"{i}. {it['text'][:28]}  {mark}"
        btns.append([InlineKeyboardButton(text=text, callback_data=f"cl_toggle|{cid}|{iid}")])
    # Action row
    btns.append([
        InlineKeyboardButton(text="✏️ Ред.",   callback_data=f"cl_edit_{cid}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"cl_delete_{cid}"),
    ])
    btns.append([InlineKeyboardButton(text="← Назад к чеклистам", callback_data="menu_checklists_mgmt")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def get_checklists_mgmt_inline(checklists: list) -> InlineKeyboardMarkup:
    """Checklists management menu."""
    btns = [[InlineKeyboardButton(text="➕ Новый чеклист", callback_data="cl_create_new")]]
    for cl in checklists:
        prog = _checklist_progress(cl)
        title = cl.get("title", "—")[:25]
        cid   = cl["id"]
        btns.append([
            InlineKeyboardButton(text=f"☑️ {title} ({prog})", callback_data=f"cl_open_{cid}"),
            InlineKeyboardButton(text="🗑", callback_data=f"cl_delete_{cid}"),
        ])
    btns.append([InlineKeyboardButton(text="← Назад в профиль", callback_data="profile_back")])
    return InlineKeyboardMarkup(inline_keyboard=btns)



def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True, one_time_keyboard=True
    )

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        is_persistent=False,
        input_field_placeholder="Напиши сюда..."
    )

def get_profile_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить профиль", callback_data="menu_edit_profile")],
    ])


def get_edit_profile_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Имя",           callback_data="edit_name")],
        [InlineKeyboardButton(text="⚧ Пол",            callback_data="edit_gender")],
        [InlineKeyboardButton(text="📍 Город",         callback_data="edit_city")],
        [InlineKeyboardButton(text="🎂 День рождения", callback_data="edit_birthday")],
        [InlineKeyboardButton(text="⏰ Время утра",    callback_data="edit_morning")],
        [InlineKeyboardButton(text="← Назад",          callback_data="menu_edit_profile_back")],
    ])

def get_achievement_category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌿 Здоровье",     callback_data="ach_cat_health")],
        [InlineKeyboardButton(text="🔥 Творчество",   callback_data="ach_cat_creativity")],
        [InlineKeyboardButton(text="💼 Работа",       callback_data="ach_cat_work")],
        [InlineKeyboardButton(text="🤝 Связи",        callback_data="ach_cat_connections")],
        [InlineKeyboardButton(text="🌱 Рост",         callback_data="ach_cat_growth")],
        [InlineKeyboardButton(text="❌ Отмена",        callback_data="cancel_achievement")]
    ])

LIFE_AREA_ICONS = {
    "health": "🌿", "creativity": "🔥", "work": "💼",
    "connections": "🤝", "growth": "🌱", "other": "🌱"
}

def get_groups_keyboard(groups: list) -> InlineKeyboardMarkup:
    btns = [[InlineKeyboardButton(text=g["name"], callback_data=f"grp_{g['id']}")] for g in groups]
    btns.append([InlineKeyboardButton(text="➕ Новая группа", callback_data="new_group")])
    btns.append([InlineKeyboardButton(text="❌ Отмена",        callback_data="cancel_task")])
    return InlineKeyboardMarkup(inline_keyboard=btns)


def get_confirm_task_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Создать задачу", callback_data="confirm_task")],
        [InlineKeyboardButton(text="❌ Отмена",          callback_data="cancel_task")]
    ])

def get_tasks_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Новая задача", callback_data="start_addtask")]
    ])

def get_deadline_keyboard() -> InlineKeyboardMarkup:
    from datetime import datetime, timedelta
    t = datetime.now()
    f = lambda d: d.strftime("%Y-%m-%d")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Завтра",      callback_data="dl_" + f(t + timedelta(days=1)))],
        [InlineKeyboardButton(text="📅 +неделя",     callback_data="dl_" + f(t + timedelta(days=7)))],
        [InlineKeyboardButton(text="📅 +месяц",      callback_data="dl_" + f(t + timedelta(days=30)))],
        [InlineKeyboardButton(text="✏️ Своя дата",   callback_data="dl_custom")],
        [InlineKeyboardButton(text="⏭ Пропустить",   callback_data="dl_skip")],
        [InlineKeyboardButton(text="❌ Отмена",       callback_data="cancel_task")],
    ])

def get_reminder_keyboard(deadline: str = None) -> InlineKeyboardMarkup:
    """Reminder v2: on deadline day / 3 days before / 1 week before / custom / skip."""
    from datetime import datetime, timedelta
    today = datetime.now()
    fmt = lambda d: d.strftime("%Y-%m-%d")
    btns = []
    if deadline:
        try:
            dl = datetime.fromisoformat(deadline)
            days_left = (dl - today).days
            btns.append([InlineKeyboardButton(
                text=f"📅 В день задачи",
                callback_data="rem_" + fmt(dl)
            )])
            if days_left > 3:
                remind3 = dl - timedelta(days=3)
                btns.append([InlineKeyboardButton(
                    text=f"🔔 За 3 дня",
                    callback_data="rem_" + fmt(remind3)
                )])
            if days_left > 7:
                remind7 = dl - timedelta(days=7)
                btns.append([InlineKeyboardButton(
                    text=f"🗓 За неделю",
                    callback_data="rem_" + fmt(remind7)
                )])
        except Exception:
            pass
    if not btns:
        btns.append([InlineKeyboardButton(
            text="🔔 Завтра",
            callback_data="rem_" + (today + timedelta(days=1)).strftime("%Y-%m-%d")
        )])
    btns.append([InlineKeyboardButton(text="✏️ Своя дата", callback_data="rem_custom")])
    btns.append([InlineKeyboardButton(text="⏭ Пропустить", callback_data="rem_skip")])
    btns.append([InlineKeyboardButton(text="❌ Отмена",     callback_data="cancel_task")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def get_labels_keyboard(labels: list) -> InlineKeyboardMarkup:
    btns = [[InlineKeyboardButton(text="🎨 " + lb["name"], callback_data="lbl_" + lb["id"])] for lb in labels[:8]]
    btns.append([InlineKeyboardButton(text="➕ Новая группа",  callback_data="lbl_new")])
    btns.append([InlineKeyboardButton(text="⏭ Без группы",   callback_data="lbl_skip")])
    btns.append([InlineKeyboardButton(text="❌ Отмена",        callback_data="cancel_task")])
    return InlineKeyboardMarkup(inline_keyboard=btns)



def _classify_sphere(title: str, label_name: str = "") -> str:
    """Classify task into one of 5 spheres. Returns sphere key."""
    title = title or ""
    label_name = label_name or ""  # hotfix: None guard
    text = (title + " " + label_name).lower()
    health_kw = [
        "здоровье","спорт","сон","питание","бег","врач","зал","тренировка","трениров",
        "физ","еда","отдых","фитнес","вес","диет","медицин","лечени","давлени",
        "витамин","таблетк","аптека","массаж","плавани","велосипед","пробежк",
        "гимнастик","растяжк","медитац","йога","сауна","баня","линзы","очки",
        "операц","анализ","обследован","процедур",
        "проснул","подъём","утренн","церемони","водные","прогулка","прогулк",
        "дыхани","расслаблен","купани","контрастн","зарядка","заряд",
        "самочувств","настроени","водн","завтрак","ужин","обед","режим"
    ]
    creativity_kw = [
        "музык","трек","альбом","запис","сведен","мастеринг","обложк","клип","видео",
        "рисовать","рисунок","дизайн","творч","хобби","фото","съемк","монтаж",
        "стих","поэзи","проза","роман","пьес","сценар","танц","песн",
        "инструмент","гитар","пианин","барабан","студи","репетиц","концерт","выставк"
    ]
    # "арт","игра","игр","запис" — removed (substring in квартира/игра/запись)
    # Use regex word-boundary for short/ambiguous creativity words
    import re as _re_cr
    def _is_art(t: str) -> bool:
        return bool(_re_cr.search(r'(?:^|\s)арт(?:\s|$)|\bарт-', t))
    def _is_game(t: str) -> bool:
        return bool(_re_cr.search(r'(?:^|\s)игр[аыу]?(?:\s|$)|\bигровой', t))
    work_kw = [
        "работа","проект","задач","код","программ","бот","разраб","запуск","бизнес",
        "клиент","встреч","переговор","контракт","договор","счёт","оплатить","зп",
        "зарплат","деньг","финанс","бюджет","доход","расход","инвест","налог",
        "отчёт","презентац","совещани","дедлайн","офис","удалёнк","фриланс",
        "монетиз","продаж","маркетинг","реклам","сайт","магазин","заказ"
    ]
    connections_kw = [
        "друг","семья","родител","мама","папа","брат","сестра","партнёр","любим",
        "свидани","встреч с","позвонить","написать","поздравить","подарок","праздник",
        "вечеринк","мероприяти","коллег","нетворк","знаком","общени","волонтёр",
        "помоч","поддержк","ребёнок","дети","отношени","совместн","поездк с",
        "сын","дочь","общался","разговор","поговорил","бесед","встретил","подруг"
    ]
    growth_kw = [
        "учить","изучить","курс","книг","обучен","навык","развит","рост",
        "саморазвит","личностн","духовн","практик","осознанн","рефлекси","дневник",
        "план жизн","цел","смысл","ценност","философи","психолог","терапи","коучинг",
        "язык","английск","иностранн","онлайн-курс","сертификат","диплом"
    ]
    # "читать" removed from growth_kw — substring of "пересчитать"/"рассчитать"
    # Use regex to detect real reading verbs only
    import re as _re_sph
    def _is_reading(t: str) -> bool:
        return bool(_re_sph.search(r'(?:^|\s)читать|прочит|перечит|почит|вычит', t))
    # P-25: two-pass — title first (authoritative), then full text
    # Fixes: task in roadmap with health-keyword in roadmap name
    title_only = title.lower()
    if any(k in title_only for k in creativity_kw) or _is_art(title_only) or _is_game(title_only):  return "creativity"
    if any(k in title_only for k in health_kw):      return "health"
    if any(k in title_only for k in connections_kw): return "connections"
    if any(k in title_only for k in growth_kw) or _is_reading(title_only): return "growth"
    if any(k in title_only for k in work_kw):        return "work"
    # Pass 2: full text including label_name
    if any(k in text for k in creativity_kw) or _is_art(text) or _is_game(text):  return "creativity"
    if any(k in text for k in health_kw):      return "health"
    if any(k in text for k in connections_kw): return "connections"
    if any(k in text for k in growth_kw) or _is_reading(text): return "growth"
    return "work"  # default

# Keep old name as alias for backward compat
def _auto_merkaba(title: str, label_name: str = "") -> str:
    return _classify_sphere(title, label_name)


def get_leave_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌑 Да, удалить всё", callback_data="leave_confirm")],
        [InlineKeyboardButton(text="❌ Нет, остаюсь",     callback_data="leave_cancel")]
    ])

# ─── Proactive messaging ──────────────────────────────────────────────────────