# -*- coding: utf-8 -*-
"""
sr_context.py -- SR Context Builder
Phase: 5. Updated: 2026-05-26.
"""

# ─── Chat sessions (sliding window) ──────────────────────────────────────────
_sessions: dict = {}
# Track last menu message per user — delete before showing new menu
_menu_messages: dict = {}  # {user_id: message_id}
_checklist_messages: dict = {}  # {user_id: message_id} — last shown checklist
_profile_messages: dict = {}   # {user_id: message_id} — last shown profile
_intent_map_msg_count: dict = {}  # uid → counter for conditional INTENT_MAP load
_intent_map_needed: dict = {}  # uid → bool — show full INTENT_MAP on next request
_sphere_history_needed: dict = {}  # uid → int — countdown: include full sphere_history in context


def _get_history(user_id: str) -> list:
    return list(_sessions.get(str(user_id), []))

def _add_to_history(user_id: str, role: str, content: str) -> None:
    uid = str(user_id)
    if uid not in _sessions:
        _sessions[uid] = []
    # H-2: timezone садовника для корректного времени в истории
    try:
        from zoneinfo import ZoneInfo as _ZI_hist
        _prof_hist = store_get_profile(uid)
        _tz_hist = (_prof_hist or {}).get("companion_settings", {}).get("timezone", "Europe/Moscow")
        _ts_hist = datetime.now(_ZI_hist(_tz_hist)).isoformat()
    except Exception:
        _ts_hist = datetime.now().isoformat()
    _sessions[uid].append({"role": role, "content": content, "ts": _ts_hist})
    if len(_sessions[uid]) > SESSION_MAX_MESSAGES:
        _sessions[uid] = _sessions[uid][-SESSION_MAX_MESSAGES:]

def _clear_history(user_id: str) -> None:
    _sessions.pop(str(user_id), None)

async def _check_version_notify(user_id: str) -> None:
    """Send update notification if gardener hasn't seen this version yet."""
    try:
        profile = store_get_profile(user_id)
        if not profile:
            return
        last_ver = profile.get("last_notified_version", "")
        if last_ver == BOT_VERSION:
            return
        # Send notification
        _name = profile.get("name", "Садовник")
        _kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📋 Что нового →", callback_data="show_changelog")
        ]])
        _notify_text = BOT_LATEST_UPDATE.get("text", f"🌱 Мандала обновилась · v{BOT_VERSION}\n\nПривет, {{name}}!").format(name=_name)
        await bot.send_message(int(user_id), _notify_text, reply_markup=_kb)
        profile["last_notified_version"] = BOT_VERSION
        store_set_profile(user_id, profile)
        _fire_sync()
        logger.info(f"Version notification sent to {user_id}")
    except Exception as e:
        logger.warning(f"Version notify error for {user_id}: {e}")



def _build_user_context_msg(telegram_id: str) -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    profile = store_get_profile(telegram_id) or {}
    workspace = store_get_workspace(telegram_id) or {}
    name = profile.get("name", "Садовник")
    resonance = profile.get("resonance_level", 0)
    companion = profile.get("companion_settings", {})
    city = companion.get("city", "") or ""
    birthday = companion.get("birthday", "") or ""
    morning_time = companion.get("morning_message_time", "") or ""
    tz_name = companion.get("timezone", "Europe/Moscow")
    # achievements_count is the reliable counter
    ach_count = workspace.get("achievements_count", 0) or len(workspace.get("achievements", []))

    # Build full task list with label and deadline
    tasks = workspace.get("tasks", [])
    active = [t for t in tasks if t.get("status") != "completed"]
    task_lines = []
    for t in active:
        label = t.get("label_name") or "без группы"
        dl = t.get("deadline") or "без даты"
        task_lines.append(f"  - {t['title']} | группа: {label} | дедлайн: {dl}")
    # Last 20 messages with tz-aware timestamps — full temporal picture for SR
    _all_session_msgs = _sessions.get(telegram_id, [])[-20:]
    _recent_msgs = _all_session_msgs  # kept for _ts_summary ref below
    _ts_block = ""
    if _all_session_msgs:
        _ts_lines = []
        for _m in _all_session_msgs:
            _role_icon = "🧑" if _m.get("role") == "user" else "🌿"
            _ts_raw = _m.get("ts", "")
            try:
                from zoneinfo import ZoneInfo as _ZI_ts2
                _ts_dt2 = datetime.fromisoformat(_ts_raw)
                if _ts_dt2.tzinfo is None:
                    _ts_dt2 = _ts_dt2.replace(tzinfo=_ZI_ts2(tz_name))
                _ts = _ts_dt2.strftime("%d.%m %H:%M")
            except Exception:
                _ts = _ts_raw[:16].replace("T", " ")
            _txt = (_m.get("content") or "")[:100].replace("\n", " ")
            _ts_lines.append(f"  {_role_icon} [{_ts}] {_txt}")
        _ts_block = "\n[Хронология диалога (последние 20 сообщений):\n" + "\n".join(_ts_lines) + "\n]"
    tasks_block = "\n".join(task_lines) if task_lines else "  нет активных задач"

    # Groups list
    groups_data = store_get_groups(telegram_id).get("groups", [])
    groups_list = ", ".join(g.get("name", "") for g in groups_data) if groups_data else "нет групп"

    # Current datetime in gardener timezone
    try:
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        DAYS_RU = ["понедельник","вторник","среда","четверг","пятница","суббота","воскресенье"]
        MONTHS_RU = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"]
        month = now.month
        season = "зима" if month in [12,1,2] else "весна" if month in [3,4,5] else "лето" if month in [6,7,8] else "осень"
        current_dt = f"{now.day} {MONTHS_RU[month-1]} {now.year}, {DAYS_RU[now.weekday()]}, {now.strftime('%H:%M')}, {season}"
    except Exception:
        current_dt = "неизвестно"

    profile_block = (
        f"  имя: {name}\n"
        f"  город: {city or 'не указан'}\n"
        f"  резонанс: {resonance}%\n"
        f"  достижений: {ach_count}\n"
        f"  день рождения: {birthday or 'не указан'}\n"
        f"  время утра: {morning_time or 'не указано'}\n"
        f"  часовой пояс: {tz_name}\n"
        f"  обращение: {'мужской род — «ты сделал», «Садовник»' if (profile or {}).get('companion_settings', {}).get('gender') == 'male' else 'женский род — «ты сделала», «Садовница»' if (profile or {}).get('companion_settings', {}).get('gender') == 'female' else 'нейтрально — «ты сделал(а)», «Садовник»'}"
    )

    sr = store_get_sphere_resonance(telegram_id)
    sr_context = "  ".join(f"{SPHERE_EMOJI[s]} {SPHERE_NAME_RU[s]} {sr.get(s,20)}%" for s in SPHERES)
    weak_spheres = [SPHERE_NAME_RU[s] for s in SPHERES if sr.get(s, 20) < 25]
    imbalance = f" | слабые сферы: {', '.join(weak_spheres)}" if weak_spheres else ""
    # P-46: имбаланс и предупреждения по сферам
    _ws_ctx = store_get_workspace(telegram_id) or {}
    _sla_ctx = _ws_ctx.get("sphere_last_active", {})
    from datetime import date as _date_ctx
    _today_ctx = _date_ctx.today()
    _sphere_warnings = []
    _sphere_decaying = []
    _max_sr = max(sr.get(s, 20) for s in SPHERES)
    _min_sr = min(sr.get(s, 20) for s in SPHERES)
    _imbalance_gap = _max_sr - _min_sr
    _min_sphere = min(SPHERES, key=lambda s: sr.get(s, 20))
    _max_sphere = max(SPHERES, key=lambda s: sr.get(s, 20))
    for _s in SPHERES:
        _last_s = _sla_ctx.get(_s, "")
        _days_s = 0
        if _last_s:
            try:
                _days_s = (_today_ctx - _date_ctx.fromisoformat(_last_s)).days
            except Exception:
                pass
        if 4 <= _days_s <= 5:
            _sphere_warnings.append(f"{SPHERE_NAME_RU[_s]} ({_days_s} дн. без активности — скоро начнёт падать)")
        elif _days_s >= 6:
            _sphere_decaying.append(f"{SPHERE_NAME_RU[_s]} ({_days_s} дн. без активности, падает)")
    _sphere_alert_block = ""
    _alerts = []
    if _imbalance_gap > 40:
        _alerts.append(f"ИМБАЛАНС: {SPHERE_NAME_RU[_max_sphere]} {sr.get(_max_sphere)}% vs {SPHERE_NAME_RU[_min_sphere]} {sr.get(_min_sphere)}% — разрыв {_imbalance_gap}%. Предложи что-то в сфере {SPHERE_NAME_RU[_min_sphere]} с учётом интересов садовника.")
    if _sphere_warnings:
        _alerts.append(f"СКОРО УПАДЁТ: {chr(44).join(_sphere_warnings)} — предупреди садовника и предложи лёгкое действие.")
    if _sphere_decaying:
        _alerts.append(f"ПАДАЕТ: {chr(44).join(_sphere_decaying)} — рекомендуй что-то конкретное по этой сфере.")
    if _alerts:
        _sphere_alert_block = "\n[ВНИМАНИЕ СФЕРЫ:\n" + "\n".join(f"  • {a}" for a in _alerts) + "\n]"
    # P-46: последние 5 выполненных задач
    _rc_ctx = _ws_ctx.get("recent_completed", [])
    _rc_block = ""
    if _rc_ctx:
        _rc_lines = [f"  • {r['title']} — {SPHERE_NAME_RU.get(r['sphere'],r['sphere'])} ({r['completed_at']})" for r in reversed(_rc_ctx)]
        _rc_block = "\n[Последние выполненные задачи:\n" + "\n".join(_rc_lines) + "\n]"


    # Pinned message block for SR context
    _pinned_ws = store_get_workspace(telegram_id) or {}
    _pinned = _pinned_ws.get("pinned_message")
    _pinned_block = f"\n[📌 Закреплено садовником: {_pinned['text'][:300]}]" if _pinned and _pinned.get("text") else ""

    # Deep profile observations
    dp = _get_deep_profile(telegram_id)
    obs_list = dp.get("observations", [])
    dp_block = ""
    if obs_list:
        dp_block = f"\n[Паттерны садовника:\n" + "\n".join(f"  - {o}" for o in obs_list[-10:]) + "\n]"

    # _ts_summary removed — _ts_block now covers full 20-msg window with timestamps
    _ts_summary = ""  # kept as empty — still referenced in _msg template

    # P-29: sphere history block — only when requested
    _sphere_hist_block = ""
    if _sphere_history_needed.get(telegram_id, 0) > 0:
        _sphere_hist_block = "\n" + _build_sphere_stats(telegram_id, months=12, show_tasks=True)
        _sphere_hist_block = f"[История активности по сферам за 12 месяцев:{_sphere_hist_block}\n]"

    _greeting_ws = store_get_workspace(telegram_id) or {}
    _greeting_flag = _greeting_ws.get("_greeting_sent_date", "") == _today()
    _greeting_block = f"\n[Приветствие сегодня: {'уже было — НЕ здоровайся снова. Если садовник пишет привет с вопросом — отвечай на вопрос. Если просто привет — можно пошутить или перейти к контексту его дня.' if _greeting_flag else 'ещё нет — можно поздороваться'}]"
    # P-44: живой портрет + интересы + медиа в каждый ответ
    _dm_ctx = (_greeting_ws.get("deep_memory") or
               (_get_deep_profile(telegram_id) or {}).get("memory", {}))
    _core_ctx = _dm_ctx.get("core", "")
    _core_block = f"\n[Живой портрет садовника: {_core_ctx}]" if _core_ctx else ""
    def _fmt_item_ctx(i):
        if isinstance(i, dict):
            return f"{i.get('name','?')} (×{i.get('count',1)}, {i.get('last_seen','')})"  
        return str(i)
    _int_ctx = _dm_ctx.get("interests", {})
    _int_conf  = [_fmt_item_ctx(i) for i in _int_ctx.get("confirmed", [])]
    _int_ment  = [_fmt_item_ctx(i) for i in _int_ctx.get("mentioned", [])]
    _int_fresh = [_fmt_item_ctx(i) for i in _int_ctx.get("fresh", [])]
    _interests_block = ""
    if _int_conf or _int_ment or _int_fresh:
        _interests_block = (
            "\n[Интересы садовника:\n"
            f"  confirmed: {chr(44).join(_int_conf) if _int_conf else 'нет'}\n"
            f"  mentioned: {chr(44).join(_int_ment) if _int_ment else 'нет'}\n"
            f"  fresh: {chr(44).join(_int_fresh) if _int_fresh else 'нет'}\n]"
        )
    _med_ctx = _dm_ctx.get("media", {})
    _med_conf  = [_fmt_item_ctx(i) for i in _med_ctx.get("confirmed", [])]
    _med_ment  = [_fmt_item_ctx(i) for i in _med_ctx.get("mentioned", [])]
    _med_fresh = [_fmt_item_ctx(i) for i in _med_ctx.get("fresh", [])]
    _media_block = ""
    if _med_conf or _med_ment or _med_fresh:
        _media_block = (
            "\n[Культурный опыт садовника (книги/фильмы/музыка/театр/искусство и др.):\n"
            f"  confirmed: {chr(44).join(_med_conf) if _med_conf else 'нет'}\n"
            f"  mentioned: {chr(44).join(_med_ment) if _med_ment else 'нет'}\n"
            f"  fresh: {chr(44).join(_med_fresh) if _med_fresh else 'нет'}\n]"
        )
    _checklists_ctx = store_get_checklists(telegram_id)
    _cl_block = ""
    if _checklists_ctx:
        _cl_lines = []
        for _cl_i in _checklists_ctx:
            _cl_items = _cl_i.get("items", [])
            _cl_done = sum(1 for it in _cl_items if it.get("done"))
            _cl_lines.append(f"  - {_cl_i['title']} ({_cl_done}/{len(_cl_items)})")
        _cl_block = "\n[Чеклисты:\n" + "\n".join(_cl_lines) + "\n]"
    _tour_block = ""
    if companion.get("_tour_mode"):
        _tour_block = (
            "[Садовник только вошёл в сад — "
            "хочет узнать что умеешь."
            " Расскажи в живом диалоге.]\n"
        )
    _msg = (
        f"{_tour_block}"
        f"[Профиль садовника:\n{profile_block}\n]{_pinned_block}\n"
        f"[Сейчас у садовника: {current_dt}]\n"
        f"[Резонанс по сферам: {sr_context}{imbalance}]\n"
        f"{_sphere_alert_block}"
        f"{_rc_block}"
        f"{_core_block}"
        f"{_interests_block}"
        f"{_media_block}"
        f"[Группы задач: {groups_list}]\n"
        f"[Активные задачи ({len(active)}):\n{tasks_block}\n]"
        f"{_cl_block}"
        f"{_sphere_hist_block}"
        f"{_ts_block}"
        f"{_ts_summary}"
        f"{dp_block}"
        f"{_greeting_block}"
    )
    return _msg



async def _call_openrouter(messages: list, model_idx: int = 0, max_tokens: int = 1500) -> str:
    if not OPENROUTER_KEY or model_idx >= len(SR_MODEL_CHAIN):
        return ""
    model = SR_MODEL_CHAIN[model_idx]
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "HTTP-Referer": "https://mandala-bot.onrender.com",
                    "X-Title": "Mandala SR Companion"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.85
                }
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                return (content or "").strip()
            elif resp.status_code == 429:
                logger.warning(f"Rate limit on {model} (idx={model_idx}), trying next")
                return await _call_openrouter(messages, model_idx + 1)
            else:
                logger.error(f"OpenRouter {resp.status_code} on {model}: {resp.text[:200]}")
                return await _call_openrouter(messages, model_idx + 1)
    except Exception as e:
        logger.error(f"OpenRouter error on {model}: {e}")
        return await _call_openrouter(messages, model_idx + 1)


# ─── Menu button handlers ─────────────────────────────────────────────────────



    await state.clear()
    result = bday if bday else "не указан"
    await message.answer(f"✅ День рождения: {result}", reply_markup=get_main_keyboard())

# ─── Free dialogue ────────────────────────────────────────────────────────────

def _build_sr_context(user_id: str) -> dict:
    gardener = store_get_profile(user_id) or {}
    tasks = store_get_tasks(user_id)
    achievements = store_get_achievements(user_id)
    active = [t for t in tasks if t.get("status") != "completed"]
    dp = gardener.get("deep_profile", {})
    mem = dp.get("memory", {})
    # Core portrait (living memory)
    # D-1: workspace first, profile fallback
    ws_sr_ctx = store_get_workspace(user_id) or {}
    mem = ws_sr_ctx.get("deep_memory") or mem
    core = mem.get("core", dp.get("synthesis", ""))
    # Interests from living memory
    interests_data = mem.get("interests", {})
    confirmed_interests = interests_data.get("confirmed", [])
    # Recent sr_observations
    recent_obs = dp.get("sr_observations", [])[-5:]
    obs_lines = [f"{o['date']}: {o['text']}" for o in recent_obs] if recent_obs else []
    # Old observations (streak/sphere patterns)
    old_obs = dp.get("observations", [])[-3:]
    return {
        "name": gardener.get("name", "Садовник"),
        "resonance": gardener.get("resonance_level", 13),
        "interests": confirmed_interests,
        "active_tasks": [{"title": t["title"], "priority": t.get("priority", 5)} for t in active[:5]],
        "achievements_count": len(achievements),
        "life_areas": gardener.get("personal_info", {}).get("life_areas", {}),
        "sr_observations": obs_lines,
        "sphere_patterns": old_obs,
        "core": core,
        "gender": gardener.get("companion_settings", {}).get("gender", "neutral"),
    }

def _get_action_keyboard(action: dict) -> Optional[InlineKeyboardMarkup]:
    if not action:
        return None
    kind = action.get("type", "")
    # Telegram callback_data limit = 64 bytes
    _raw_label = (action.get("title") or action.get("query") or "")
    _label_bytes = _raw_label.encode("utf-8")[:58]
    label = _label_bytes.decode("utf-8", errors="ignore").strip()
    if kind == "add_task":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Добавить задачу", callback_data="qt:" + label)],
            [InlineKeyboardButton(text="❌ Не надо", callback_data="qdismiss")]
        ])
    if kind == "add_achievement":
        _sphere_qa = (action.get("sphere") or "growth")[:10]
        _qa_data = ("qa:" + label + "|" + _sphere_qa)[:64]
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Зафиксировать достижение", callback_data=_qa_data)],
            [InlineKeyboardButton(text="❌ Не надо", callback_data="qdismiss")]
        ])
    if kind == "create_reminder":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Создать напоминание", callback_data="qr:" + label)],
            [InlineKeyboardButton(text="❌ Не надо", callback_data="qdismiss")]
        ])
    if kind == "web_search":
        return None  # поиск уже выполнен — кнопки не нужны
    return None

# _build_prompt replaced by _build_user_context_msg + sliding window in free_conversation

def _build_sphere_stats(user_id: str, months: int = 3, show_tasks: bool = False) -> str:
    """Unified sphere stats text for /achievements and /sr_report.
    Uses sphere_history if available, falls back to achievements array.
    show_tasks=False — only achievements (profile dashboard)
    show_tasks=True — tasks + achievements (/sr_report)"""
    _RU_MONTHS_S = {
        1:"Январь",2:"Февраль",3:"Март",4:"Апрель",5:"Май",6:"Июнь",
        7:"Июль",8:"Август",9:"Сентябрь",10:"Октябрь",11:"Ноябрь",12:"Декабрь"
    }
    sphere_names = {
        "health": "🌿 Здоровье", "creativity": "🔥 Творчество",
        "work": "💼 Работа", "connections": "🤝 Связи", "growth": "🌱 Рост"
    }
    prof = store_get_profile(user_id) or {}
    dp   = prof.get("deep_profile", {})
    sphere_hist = dp.get("sphere_history", [])
    lines = []

    if sphere_hist:
        for month_data in reversed(sphere_hist[-months:]):
            m_str = month_data.get("month", "")
            try:
                m_num  = int(m_str.split("-")[1])
                m_year = m_str.split("-")[0]
                m_label = f"{_RU_MONTHS_S[m_num]} {m_year}"
            except Exception:
                m_label = m_str
            lines.append(f"\n\n<b>{m_label}:</b>")
            has_data = False
            for sphere, sname in sphere_names.items():
                d = month_data.get(sphere, {})
                t_cnt = d.get("tasks", 0)
                a_cnt = d.get("achievements", 0)
                r_delta = d.get("resonance_delta", 0)
                if t_cnt > 0 or a_cnt > 0 or r_delta > 0:
                    has_data = True
                    parts = []
                    if t_cnt > 0:
                        parts.append(f"{t_cnt} задач")
                    if a_cnt > 0:
                        parts.append(f"{a_cnt} достижений")
                    if parts:
                        line = f"  {sname} — {' · '.join(parts)}"
                        if r_delta > 0:
                            line += f" · +{r_delta}% резонанс"
                        lines.append(line)
                    else:
                        # Only resonance delta, no tasks/achievements
                        lines.append(f"  {sname} — +{r_delta}% резонанс")
            if not has_data:
                lines.append("  нет активности")
        # Analytics
        cur = sphere_hist[-1]
        top = max(
            [(s, cur.get(s,{}).get("tasks",0) + cur.get(s,{}).get("achievements",0))
             for s in sphere_names],
            key=lambda x: x[1]
        )
        quiet = [sphere_names[s] for s, cnt in
            [(s, cur.get(s,{}).get("tasks",0) + cur.get(s,{}).get("achievements",0))
             for s in sphere_names] if cnt == 0]
        if top[1] > 0:
            lines.append(f"\n💡 {sphere_names.get(top[0], top[0])} — сильнейшая сфера.")
        if quiet:
            lines.append(f"   {', '.join(quiet[:2])} — без движения.")
    else:
        # Fallback: count from achievements array
        from datetime import datetime as _dt_fb
        achievements = store_get_achievements(user_id)
        cur_month = _dt_fb.now().strftime("%Y-%m")
        this_month = [a for a in achievements if (a.get("completed") or "").startswith(cur_month)]
        by_sphere: dict = {}
        for ach in achievements:
            cat = ach.get("category", "other")
            by_sphere.setdefault(cat, 0)
            by_sphere[cat] += 1
        if this_month:
            m_num = _dt_fb.now().month
            lines.append(f"\n{_RU_MONTHS_S[m_num]} (из архива):")