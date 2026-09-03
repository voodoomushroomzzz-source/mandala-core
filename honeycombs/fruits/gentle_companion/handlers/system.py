# -*- coding: utf-8 -*-
"""
handlers/system.py -- System, Onboarding, Profile, Schedulers, Voice. Phase: 6.
"""

async def send_morning_greeting(telegram_id: str, silence_day: int | None = None,
                                 sphere_note: str = "", decaying_spheres: list | None = None) -> None:
    """Morning greeting v3: alive SR message, personalised via synthesis + history.
    silence_day: if set, this send is part of the silence-escalation schedule
    (3/7/15 days of silence) — SR gets a note to soften the tone accordingly."""
    try:
        uid = str(telegram_id)
        gardener = store_get_profile(uid)
        if not gardener:
            return
        settings = gardener.get("companion_settings", {})
        if not settings.get("proactive_mode", True):
            return
        from zoneinfo import ZoneInfo
        from datetime import datetime as _dt, timedelta as _td
        tz_name = settings.get("timezone", "Europe/Moscow")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("Europe/Moscow")
        now = _dt.now(tz)
        today_str = now.strftime("%Y-%m-%d")
        if _morning_sent.get(uid) == today_str:
            return
        name = gardener.get("name", "Садовник")
        # Gather context for SR
        # D-1: workspace first, profile fallback
        ws_mg = store_get_workspace(uid) or {}
        deep_mem_mg = ws_mg.get("deep_memory") or gardener.get("deep_profile", {}).get("memory", {})
        core = deep_mem_mg.get("core", "")
        _syn_date_mg = (ws_mg.get("deep_memory") or {}).get("synthesis_date", "") or \
            gardener.get("deep_profile", {}).get("synthesis_date", "")
        interests = deep_mem_mg.get("interests", {})
        confirmed = interests.get("confirmed", [])
        ach_count = store_get_achievements_count(uid)
        tasks = store_get_tasks(uid)
        active = [t for t in tasks if t.get("status") != "completed"]
        hot = sorted(
            [t for t in active if t.get("deadline") and t["deadline"] <= today_str],
            key=lambda t: t.get("deadline") or "9999"
        )
        tomorrow_str = (now + _td(days=1)).strftime("%Y-%m-%d")
        tomorrow_tasks = [t for t in active if t.get("deadline") == tomorrow_str]
        hot_text = ", ".join(t["title"] for t in hot[:3]) if hot else "нет"
        tomorrow_text = ", ".join(t["title"] for t in tomorrow_tasks[:3]) if tomorrow_tasks else "нет"
        sr = store_get_sphere_resonance(uid)
        spheres_line = "  ".join(f"{SPHERE_EMOJI[s]}{sr.get(s,20)}%" for s in SPHERES)
        weak_spheres = [SPHERE_NAME_RU[s] for s in SPHERES if sr.get(s, 20) < 25]
        weak_text = ", ".join(weak_spheres) if weak_spheres else "сбалансированы"
        history = _get_history(uid)
        recent = history[-10:] if history else []
        history_text = "\n".join(
            f"[{m.get('ts','')[:10]}] {'🧑' if m.get('role')=='user' else '🌿'}: {m.get('content','')[:100]}"
            for m in recent
        ) if recent else "диалога ещё нет"
        DAYS_RU = ["понедельник","вторник","среда","четверг","пятница","суббота","воскресенье"]
        current_time = f"{now.strftime('%H:%M')}, {DAYS_RU[now.weekday()]}"
        ws = store_get_workspace(uid) or {}
        last_inter = ws.get("last_interaction_date", "")
        missed_days = 0
        if last_inter:
            try:
                last_dt = _dt.strptime(last_inter, "%Y-%m-%d").replace(tzinfo=tz)
                missed_days = (now - last_dt).days
            except Exception:
                pass
        missed_note = ""
        if silence_day:
            missed_note = (
                f"Садовник не писал {silence_day} дней. Это {silence_day}-й день тишины — "
                f"тон мягкий, без давления, дай понять что ты рядом."
            )
        elif missed_days >= 2:
            missed_note = f"Садовник не писал {missed_days} дней. Соскучилась, но не дави."
        decaying_note = ""
        if decaying_spheres:
            decaying_names = ", ".join(SPHERE_NAME_RU[s] for s in decaying_spheres)
            decaying_note = (
                f"Сферы, где резонанс уже несколько дней подряд падает без действий: {decaying_names}. "
                f"Можешь мягко, между делом упомянуть об этом — без списков и без давления, "
                f"просто как часть заботы о садовнике. Естественно, не в каждом слове.\n"
            )
        prompt = (
            "Ты — СР, дух сада. Сейчас утро садовника " + name + ".\n\n"
            "Портрет садовника (портрет от " + (_syn_date_mg or "?") + ", сегодня " + today_str + " — учитывай что прошлое в портрете может быть неактуальным): " + (core[:400] if core else "формируется") + "\n"
            "Интересы: " + (", ".join(i["name"] if isinstance(i, dict) else i for i in confirmed[:5]) if confirmed else "не определены") + "\n"
            "Сегодня " + today_str + ". История диалога (дата указана перед каждым сообщением — учитывай насколько давно):\n" + history_text + "\n\n"
            "Горящие задачи (сегодня/просрочены): " + hot_text + "\n"
            "Задачи на завтра: " + tomorrow_text + "\n"
            "Резонанс сфер: " + spheres_line + "\n"
            "Слабые сферы: " + weak_text + "\n"
            "Достижений всего: " + str(ach_count) + "\n\n"
            "Сейчас " + current_time + " по таймзоне садовника.\n"
            + (missed_note + "\n" if missed_note else "")
            + (decaying_note if decaying_note else "") +
            "\nРуководствуясь ахимсой, напиши одно тёплое утреннее приветствие.\n"
            "Это начало дня — можно мягко подсветить что сегодня ждёт, "
            "но без давления и списков. Если есть задача на сегодня — "
            "упомянуть как часть дня, а не как обязанность.\n"
            "ВАЖНО: сегодня " + today_str + ", завтра " + tomorrow_str + ". "
            "Чётко различай: задача на сегодня — говори 'сегодня', "
            "на завтра — говори 'завтра'. НИКОГДА не называй завтрашнюю задачу событием сегодняшнего дня.\n"
            "Тон: тёплый, утренний, бодрящий. Максимум 3 предложения. С эмодзи.\n"
            "Без markdown. Без «ты должен», «тебе нужно». Без слова «замечаю».\n"
            "Ответь ТОЛЬКО текстом сообщения."
        )
        msg = await _call_openrouter([
            {"role": "system", "content": "Ты — СР, дух сада. Пиши тепло, кратко, с эмодзи. На русском. Руководствуйся ахимсой."},
            {"role": "user", "content": prompt}
        ])
        if not msg or len(msg.strip()) < 5:
            # Fallback if SR didn't respond
            msg = f"🌅 Доброе утро, {name}!\n\nПусть сегодняшний день будет наполнен тем что важно для тебя."
        full_msg = msg.strip() + (f"\n\n{sphere_note}" if sphere_note else "")
        await bot.send_message(int(uid), full_msg, parse_mode="HTML", reply_markup=get_main_keyboard(), disable_web_page_preview=True)
        _add_to_history(uid, "assistant", msg.strip())
        _morning_sent[uid] = today_str
        ws["last_morning_date"] = today_str
        ws["_greeting_sent_date"] = today_str  # P-41: greeting flag
        store_set_workspace(uid, ws)
        # Update last_notified_version
        last_ver = gardener.get("last_notified_version", "")
        if last_ver != BOT_VERSION:
            gardener["last_notified_version"] = BOT_VERSION
            store_set_profile(uid, gardener)
    except Exception as e:
        logger.error(f"Morning greeting error: {e}")

async def run_reminder_scheduler() -> None:
    """Fire reminders every minute. Compares in gardener's local timezone."""
    try:
        from datetime import datetime as _dtr6, timedelta as _td6
        from zoneinfo import ZoneInfo as _ZI6
        for uid, user_store in list(_store.items()):
            if not isinstance(user_store, dict) or not user_store.get("ready"):
                continue
            reminders = store_get_reminders(uid)
            if not reminders:
                continue
            # Resolve per-user timezone instead of bare server UTC
            _profile6 = user_store.get("profile") or {}
            _tz_name6 = _profile6.get("companion_settings", {}).get("timezone", "Europe/Moscow")
            try:
                _tz6 = _ZI6(_tz_name6)
            except Exception:
                _tz6 = _ZI6("Europe/Moscow")
            now_dt = _dtr6.now(_tz6)
            now_str = now_dt.strftime("%Y-%m-%dT%H:%M")
            changed = False
            # P-68: auto-purge once-reminders older than 24h
            for r in list(reminders):
                if r.get("repeat", "once") == "once" and r.get("active", True):
                    _r_dt_raw = r.get("datetime_iso", "")[:16]
                    try:
                        _r_dt_past = _dtr6.strptime(_r_dt_raw, "%Y-%m-%dT%H:%M").replace(tzinfo=_tz6)
                        if (now_dt - _r_dt_past).total_seconds() > 86400:
                            reminders.remove(r)
                            changed = True
                            continue
                    except Exception:
                        pass
            for r in list(reminders):
                if not r.get("active"):
                    continue
                # Parse reminder time with timezone awareness
                r_dt_str = r.get("datetime_iso", "")
                r_match = False
                # Try timezone-aware format first: "YYYY-MM-DDTHH:MM+HH:MM"
                if "+" in r_dt_str or r_dt_str.endswith("Z"):
                    try:
                        from datetime import timezone as _dtz
                        if r_dt_str.endswith("Z"):
                            r_dt = _dtr6.fromisoformat(r_dt_str[:-1] + "+00:00")
                        else:
                            r_dt = _dtr6.fromisoformat(r_dt_str)
                        r_dt_tz = r_dt.astimezone(_tz6)
                        r_match = r_dt_tz.strftime("%Y-%m-%dT%H:%M") == now_str
                    except Exception:
                        r_match = r_dt_str[:16] == now_str  # fallback
                else:
                    # Plain format: compare directly (gardener's local time)
                    r_match = r_dt_str[:16] == now_str
                if not r_match:
                    continue
                try:
                    await bot.send_message(int(uid), f"🔔 <b>{r['title']}</b>",
                                           parse_mode="HTML", reply_markup=get_main_keyboard())
                except Exception:
                    pass
                repeat = r.get("repeat", "once")
                if repeat == "once":
                    reminders.remove(r)
                    changed = True  # P-60: fix — was missing, once reminder never saved
                    # P-95: clear task["reminder"] after one-time reminder fires
                    _tid_fired = r.get("task_id")
                    if _tid_fired:
                        _tasks_fired = store_get_tasks(uid)
                        for _t_fired in _tasks_fired:
                            if _t_fired.get("task_id") == _tid_fired:
                                _t_fired["reminder"] = None
                                break
                        store_set_tasks(uid, _tasks_fired)
                elif repeat == "daily":
                    d = _dtr6.strptime(now_str, "%Y-%m-%dT%H:%M")
                    r["datetime_iso"] = (d + _td6(days=1)).strftime("%Y-%m-%dT%H:%M")
                elif repeat == "weekdays":
                    d = _dtr6.strptime(now_str, "%Y-%m-%dT%H:%M")
                    skip = 1
                    while (d + _td6(days=skip)).weekday() >= 5:
                        skip += 1
                    r["datetime_iso"] = (d + _td6(days=skip)).strftime("%Y-%m-%dT%H:%M")
                elif repeat == "weekends":
                    d = _dtr6.strptime(now_str, "%Y-%m-%dT%H:%M")
                    skip = 1
                    while (d + _td6(days=skip)).weekday() not in (5, 6):
                        skip += 1
                    r["datetime_iso"] = (d + _td6(days=skip)).strftime("%Y-%m-%dT%H:%M")
                elif repeat == "weekly":
                    d = _dtr6.strptime(now_str, "%Y-%m-%dT%H:%M")
                    r["datetime_iso"] = (d + _td6(days=7)).strftime("%Y-%m-%dT%H:%M")
                elif repeat == "monthly":
                    d = _dtr6.strptime(now_str, "%Y-%m-%dT%H:%M")
                    # +30 days, scheduler will re-match next month
                    r["datetime_iso"] = (d + _td6(days=30)).strftime("%Y-%m-%dT%H:%M")
                elif repeat == "yearly":
                    d = _dtr6.strptime(now_str, "%Y-%m-%dT%H:%M")
                    r["datetime_iso"] = (d + _td6(days=365)).strftime("%Y-%m-%dT%H:%M")
                elif repeat.startswith("custom_days:"):
                    days_str = repeat.split(":")[1]
                    days_list = days_str.split(",")
                    d = _dtr6.strptime(now_str, "%Y-%m-%dT%H:%M")
                    day_names = ["mon","tue","wed","thu","fri","sat","sun"]
                    current_wday = day_names[d.weekday()]
                    # Find next matching day
                    skip = 1
                    while True:
                        next_d = d + _td6(days=skip)
                        if day_names[next_d.weekday()] in days_list:
                            break
                        skip += 1
                    r["datetime_iso"] = next_d.strftime("%Y-%m-%dT%H:%M")
                # P-95: sync task["reminder"] with new rescheduled datetime (repeat only)
                if repeat != "once":
                    _tid_resched = r.get("task_id")
                    if _tid_resched:
                        _tasks_resched = store_get_tasks(uid)
                        for _t_resched in _tasks_resched:
                            if _t_resched.get("task_id") == _tid_resched:
                                _t_resched["reminder"] = r["datetime_iso"]
                                break
                        store_set_tasks(uid, _tasks_resched)
                changed = True
            if changed:
                store_set_reminders(uid, reminders)
                _fire_sync()
    except Exception as e:
        logger.error(f"Reminder scheduler error: {e}", exc_info=True)

async def run_proactive_scheduler() -> None:
    try:
        # Если _store пуст (бот проснулся после сна Render) — загрузить всех из whitelist
        if not _store or not any(
            isinstance(us, dict) and us.get("ready") for us in _store.values()
        ):
            await _load_store()
        for uid, user_store in list(_store.items()):
            if not isinstance(user_store, dict) or not user_store.get("ready"):
                # Retry loading user if not ready (e.g. GitHub API failed at startup)
                try:
                    await _load_user(uid)
                    user_store = _get_user_store(uid)
                except Exception:
                    pass
                if not user_store.get("ready"):
                    continue
            g = user_store.get("profile")
            if not g:
                continue
            settings = g.get("companion_settings", {})
            if not settings.get("proactive_mode", True):
                continue
            tz_name = settings.get("timezone", "Europe/Moscow")
            if not settings.get("morning_message_time") or not _time_matches(settings["morning_message_time"], tz_name):
                continue  # только утреннее окно по таймзоне садовника — дневных сообщений больше нет

            days_silent = _days_silent_persistent(uid)

            # День 31 тишины → автоудаление, без сообщения (reset_condition делает 31 однозначным:
            # любой ответ садовника сбрасывает days_silent, так что 31 достижимо только реальным молчанием)
            if days_silent >= 31:
                await _delete_gardener(uid, notify_architect=True)
                continue

            tracking = _get_silence_tracking(uid)
            milestone = _next_proactive_milestone(days_silent, tracking.get("last_proactive_date", ""))

            # Падение резонанса по сферам: жёсткие вехи 3/6/7 (sphere_note) +
            # список сфер, которые падают уже несколько дней (decaying_spheres, для мягкого упоминания СР)
            sphere_note, decaying_spheres = _sphere_decay_check(uid)

            if milestone is None:
                if sphere_note:  # только гарантированные 3/6/7 — иначе молчим
                    await bot.send_message(int(uid), sphere_note, reply_markup=get_main_keyboard())
                continue  # не веха — молчим, дневных подталкиваний больше нет

            if milestone == 1:
                await send_morning_greeting(uid, sphere_note=sphere_note, decaying_spheres=decaying_spheres)
            elif milestone == 30:
                text30 = f"🌒 {_MILESTONE_TEXTS[30]}" + (f"\n\n{sphere_note}" if sphere_note else "")
                await bot.send_message(int(uid), text30, reply_markup=get_main_keyboard())
            else:
                await send_morning_greeting(uid, silence_day=milestone, sphere_note=sphere_note, decaying_spheres=decaying_spheres)  # 3/7/15 — с меткой дня тишины

            _set_silence_tracking(uid, _today(), milestone)
        # Birthday check
        for uid2, us2 in list(_store.items()):
            if not isinstance(us2, dict) or not us2.get("ready"):
                continue
            g2 = us2.get("profile")
            if not g2:
                continue
            bday = g2.get("companion_settings", {}).get("birthday", "")
            if not bday:
                continue
            try:
                from zoneinfo import ZoneInfo as _ZI
                from datetime import datetime as _dt2
                tz2 = ZoneInfo(g2.get("companion_settings", {}).get("timezone", "Europe/Moscow"))
                now2 = _dt2.now(tz2)
                today_bday = now2.strftime("%d.%m")
                # Only at 10:00 in user's timezone
                if today_bday == bday and now2.hour == 10 and _birthday_sent.get(uid2) != today_bday:
                    bname = g2.get("name", "Садовник")
                    # Build personalised birthday greeting via SR
                    sr_ctx = _build_user_context_msg(uid2)
                    dp2 = _get_deep_profile(uid2)
                    core2 = dp2.get("memory", {}).get("core", "")
                    ach_count2 = store_get_achievements_count(uid2)
                    bday_prompt = (
                        f"Сегодня день рождения садовника {bname}.\n"
                        f"Портрет: {core2[:300] if core2 else 'пока формируется'}\n"
                        f"Достижений: {ach_count2}\n"
                        f"Контекст:\n{sr_ctx[:800]}\n\n"
                        f"Напиши тёплое персонализированное поздравление с днём рождения (3-4 предложения). "
                        f"Отрази рост садовника за прошедший год. "
                        f"Используй эмодзи. Будь как мудрый друг который видит путь человека. "
                        f"Ответь ТОЛЬКО текстом поздравления, без JSON."
                    )
                    bday_msg = await _call_openrouter([
                        {"role": "system", "content": "Ты — СР, дух сада. Пиши тепло, кратко, с эмодзи. На русском."},
                        {"role": "user", "content": bday_prompt}
                    ])
                    if not bday_msg or len(bday_msg.strip()) < 10:
                        bday_msg = (
                            f"🎂 С днём рождения, {bname}!\n\n"
                            f"Пусть этот год будет годом роста во всех сферах.\n"
                            f"Сад помнит этот день. 🌿"
                        )
                    await bot.send_message(
                        int(uid2),
                        bday_msg.strip(),
                        reply_markup=get_main_keyboard()
                    )
                    _birthday_sent[uid2] = today_bday
                    # Also store achievement for birthday
                    store_increment_achievements(uid2)
                    store_add_sphere_resonance(uid2, "growth", 5)
                    _fire_sync()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Proactive scheduler crashed: {e}", exc_info=True)


# ─── Tasks & Labels management menus ─────────────────────────────────────────

# (Убран дублирующий декоратор @router.callback_query(F.data == "menu_tasks_mgmt") —
#  настоящий обработчик этой кнопки уже есть выше по файлу; этот экземпляр был мёртвым кодом,
#  т.к. run_resonance_decay() не принимал callback и упал бы при реальном вызове.)
_SPHERE_WARN_TEXTS = {
    "early":    "{emoji} {name} — {days} дня без внимания, но пока держится.",
    "final":    "⚠️ {emoji} {name} — без действий резонанс начнёт падать уже завтра.",
    "decaying": "📉 {emoji} {name} начал терять резонанс — здесь давно не было движения.",
}

def _sphere_decay_check(telegram_id: str) -> tuple:
    """Per-sphere silence check: day 3 early warning, day 6 final warning,
    day 7 decay-start notice (hard milestones, guaranteed delivery) — plus
    daily -2% decay (floor 0) while stage == 'decaying'.
    Called once per day per user (from the morning-window gate in run_proactive_scheduler,
    which already dedups to once/day) — idempotent via stage tracking.
    Returns (milestone_text, currently_decaying_spheres):
      - milestone_text: hard-coded lines, only on day 3/6/7 transitions (append/standalone).
      - currently_decaying_spheres: sphere ids still decaying today (incl. day 8+),
        fed into the SR's own morning-greeting prompt for a soft, non-scripted mention."""
    uid = str(telegram_id)
    meta = store_get_sphere_meta(uid)
    sr = store_get_sphere_resonance(uid)
    tz_name = (store_get_profile(uid) or {}).get("companion_settings", {}).get("timezone", "Europe/Moscow")
    today_s = _today(tz_name)
    from datetime import date as _d_sphere
    lines = []
    decaying_now = []
    changed_meta = False
    changed_sr = False
    for s in SPHERES:
        entry = meta.get(s, {"last_active": today_s, "stage": "none"})
        last = entry.get("last_active", today_s)
        stage = entry.get("stage", "none")
        try:
            days_silent = (_d_sphere.fromisoformat(today_s) - _d_sphere.fromisoformat(last)).days
        except Exception:
            days_silent = 0
        if days_silent >= 7:
            if stage != "decaying":
                lines.append(_SPHERE_WARN_TEXTS["decaying"].format(emoji=SPHERE_EMOJI[s], name=SPHERE_NAME_RU[s]))
                entry["stage"] = "decaying"
                changed_meta = True
            sr[s] = max(0, sr.get(s, 20) - 2)
            changed_sr = True
            decaying_now.append(s)
        elif days_silent >= 6:
            if stage != "final_warned":
                lines.append(_SPHERE_WARN_TEXTS["final"].format(emoji=SPHERE_EMOJI[s], name=SPHERE_NAME_RU[s]))
                entry["stage"] = "final_warned"
                changed_meta = True
        elif days_silent >= 3:
            if stage not in ("early_warned", "final_warned"):
                lines.append(_SPHERE_WARN_TEXTS["early"].format(emoji=SPHERE_EMOJI[s], name=SPHERE_NAME_RU[s], days=days_silent))
                entry["stage"] = "early_warned"
                changed_meta = True
        meta[s] = entry
    if changed_meta:
        store_set_sphere_meta(uid, meta)
    if changed_sr:
        store_set_sphere_resonance(uid, sr)
        mean = max(0, min(100, round(sum(sr[s] for s in SPHERES) / len(SPHERES))))
        profile = store_get_profile(uid) or {}
        profile["resonance_level"] = mean
        store_set_profile(uid, profile)
    return "\n".join(lines), decaying_now

async def _delete_gardener(uid: str, notify_architect: bool = True) -> bool:
    """
    Универсальная функция удаления садовника.
    Возвращает True, если удаление прошло успешно.
    """
    try:
        profile = store_get_profile(uid)
        name = (profile or {}).get("name", "Садовник") if profile else "Неизвестный"

        # 1. Удаляем из whitelist
        success = await _remove_from_whitelist(uid)
        if not success:
            logger.error(f"Failed to remove {uid} from whitelist")
            return False

        # 2. Очищаем RAM
        _store.pop(uid, None)
        _sessions.pop(uid, None)

        # 3. Удаляем файлы на GitHub по-настоящему (реальный DELETE, не перезапись пустышкой)
        base = _user_path(uid)
        tasks = [
            _gardeners_delete(f"{base}/profile.json"),
            _gardeners_delete(f"{base}/workspace.json"),
            _gardeners_delete(f"{base}/memory.json"),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Проверяем, все ли удаления прошли успешно
        failed = [r for r in results if r is not True]
        if failed:
            logger.error(f"Failed to delete some files for {uid}: {failed}")

        # Убираем из очереди любые висящие записи по этому uid — иначе фоновый
        # _sync_pending() мог бы "воскресить" удалённый файл отправив старый PUT
        for suffix in ("profile.json", "workspace.json", "memory.json"):
            _pending_writes.pop(f"{base}/{suffix}", None)

        # 4. Уведомляем архитектора
        if notify_architect:
            try:
                await bot.send_message(
                    int(ARCHITECT_TELEGRAM_ID),
                    f"🌑 <b>Садовник покинул сад (удаление)</b>\n\n"
                    f"👤 {name}\nID: <code>{uid}</code>\n"
                    f"Время: {_today()}. Данные удалены.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Architect notification error: {e}")

        return True

    except Exception as e:
        logger.error(f"Delete gardener error for {uid}: {e}")
        return False

@router.message(Command("start"))


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    _clear_history(user_id)
    # Load user on demand if not yet loaded
    user_store = _get_user_store(user_id)
    if not user_store.get("ready"):
        await message.answer("🌱 Загружаю твой сад...")
        await _load_user(user_id)
    gardener = store_get_profile(user_id)

    password = None
    try:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) == 2:
            password = parts[1].strip()
    except Exception:
        pass

    await ensure_user_loaded(user_id)
    # Check if existing user
    user_profile = store_get_profile(user_id)
    if user_profile:
        name = user_profile.get("name", "Садовник")
        # Sync resonance_level as mean of sphere_resonance (v7.26+)
        sr = store_get_sphere_resonance(user_id)
        mean = max(5, min(100, round(sum(sr[s] for s in SPHERES) / len(SPHERES))))
        if abs(mean - int(user_profile.get("resonance_level", 5))) > 2:
            user_profile["resonance_level"] = mean
            store_set_profile(user_id, user_profile)
        # Changelog deep link — show dashboard immediately
        if password and password.lower() == "changelog":
            name = user_profile.get("name", "Садовник")
            text = BOT_LATEST_UPDATE.get("text", "").format(name=name)
            await message.answer(text, reply_markup=None)
            await message.answer("🌿 Чем могу помочь?", reply_markup=get_main_keyboard())
            return
        await message.answer(f"🌿 С возвращением, {name}!", reply_markup=get_main_keyboard())
        return

    # Consent check — new users must agree to data processing
    if user_id != ARCHITECT_TELEGRAM_ID:
        whitelist = await _gardeners_get("gardeners/whitelist.json") or {"approved": []}
        approved = whitelist.get("approved", []) if isinstance(whitelist, dict) else []
        if user_id not in approved:
            await state.set_state(GardenOnboardingStates.waiting_for_consent)
            consent_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🌿 Да, я согласен",
                    callback_data="consent_yes"
                ),
                InlineKeyboardButton(
                    text="🚪 Нет, не входить",
                    callback_data="consent_no"
                ),
            ]])
            consent_text = (
                "🌱 <b>Ты нашёл Мандалу Симбиоза.</b>\n\n"
                "Прежде чем войти — расскажу, что храню о тебе.\n\n"
                "<b>Что сохраняется:</b>\n"
                "· Профиль — имя, город, день рождения, настройки\n"
                "· Задачи, чеклисты, напоминания, достижения\n"
                "· Диалог — последние 50 сообщений в RAM сессии,\n"
                "  сбрасываются при перезапуске бота\n"
                "· Синтез — раз в сутки составляю живой портрет:\n"
                "  чем ты занят, какие сферы активны, что важно. Не лог — моё понимание тебя.\n\n"
                "<b>Где хранится:</b>\n"
                "Приватный GitHub-репозиторий. "
                "Данные не передаются третьим сторонам.\n\n"
                "<b>Удалить всё:</b> /leave\n\n"
                "Входишь?"
            )
            await message.answer(consent_text, parse_mode="HTML", reply_markup=consent_kb)
            return

    await state.set_state(GardenOnboardingStates.waiting_for_name)
    await message.answer(
        "Давай познакомимся.\n\nКак тебя зовут?",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_name))
async def onboard_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 1:
        await message.answer("🌱 Введи своё имя.")
        return
    await state.update_data(name=name)
    await state.set_state(GardenOnboardingStates.waiting_for_gender)
    gender_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👨 Мужской",      callback_data="onboard_gender_male"),
        InlineKeyboardButton(text="👩 Женский",      callback_data="onboard_gender_female"),
        InlineKeyboardButton(text="🌿 Без разницы",  callback_data="onboard_gender_neutral"),
    ]])
    await message.answer(
        f"{name} — отлично! Как мне к тебе обращаться?",
        reply_markup=gender_kb
    )

# Body/Spirit/World onboarding removed in v7.24.5
# Sphere resonance will be calculated automatically from task life_area in v7.26.x

@router.callback_query(F.data.startswith("onboard_gender_"))
async def onboard_gender(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    gender = callback.data.replace("onboard_gender_", "")
    await state.update_data(gender=gender)
    await state.set_state(GardenOnboardingStates.waiting_for_city)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    _city_skip_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Пропустить 🌿", callback_data="onboard_skip_city")
    ]])
    await callback.message.answer(
        "📍 В каком городе ты живёшь?\n\n"
        "<i>Буду учитывать часовой пояс для утреннего сообщения, "
        "подбирать результаты поиска рядом с тобой и учитывать местную погоду.</i>",
        parse_mode="HTML", reply_markup=_city_skip_kb
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_city))
async def onboard_city(message: Message, state: FSMContext):
    city = message.text.strip()
    if city.lower() in ["пропустить", "skip", "-"]:
        city = ""
    await state.update_data(city=city)
    # Auto-detect timezone from city
    if city:
        tz = await _city_to_timezone(city)
        await state.update_data(timezone=tz)
    await state.set_state(GardenOnboardingStates.waiting_for_birthday)
    _bday_skip_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Пропустить 🌿", callback_data="onboard_skip_birthday")
    ]])
    await message.answer(
        "🎂 Когда твой день рождения?\n"
        "<i>Формат: ДД.ММ (например 15.03)</i>\n\n"
        "<i>В этот день СР напишет тебе лично — не шаблон, "
        "а живое слово с учётом твоего пути в Саду.</i>",
        parse_mode="HTML", reply_markup=_bday_skip_kb
    )

@router.callback_query(F.data == "onboard_skip_city")
async def onboard_skip_city(callback: CallbackQuery, state: FSMContext):
    """Skip city step."""
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await state.update_data(city="")
    await state.set_state(GardenOnboardingStates.waiting_for_birthday)
    _bday_skip_kb2 = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Пропустить 🌿", callback_data="onboard_skip_birthday")
    ]])
    await callback.message.answer(
        "🎂 Когда твой день рождения?\n"
        "<i>Формат: ДД.ММ (например 15.03)</i>\n\n"
        "<i>В этот день СР напишет тебе лично — не шаблон, "
        "а живое слово с учётом твоего пути в Саду.</i>",
        parse_mode="HTML", reply_markup=_bday_skip_kb2
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_birthday))
async def onboard_birthday(message: Message, state: FSMContext):
    bday_raw = message.text.strip()
    bday = ""
    # Try full date DD.MM.YYYY
    if re.match(r"^\d{2}\.\d{2}\.\d{4}$", bday_raw):
        bday = bday_raw[0:5]  # save as DD.MM only
    # Try short date DD.MM
    elif re.match(r"^\d{2}\.\d{2}$", bday_raw):
        bday = bday_raw
    # Anything else — skip (no error, just continue)
    # This way "26.10.1989", "26.10", "нет", "пропустить", "skip" all work
    await state.update_data(birthday=bday)
    await state.set_state(GardenOnboardingStates.waiting_for_morning)
    await message.answer(
        "⏰ Во сколько присылать утреннее сообщение?\n"
        "<i>Формат: ЧЧ:ММ (например 09:00 или 10:30)</i>",
        parse_mode="HTML", reply_markup=get_cancel_keyboard()
    )

@router.callback_query(F.data == "onboard_skip_birthday")
async def onboard_skip_birthday(callback: CallbackQuery, state: FSMContext):
    """Skip birthday step."""
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await state.update_data(birthday="")
    await state.set_state(GardenOnboardingStates.waiting_for_morning)
    await callback.message.answer(
        "⏰ Во сколько присылать утреннее сообщение?\n"
        "<i>Формат: ЧЧ:ММ (например 09:00 или 10:30)</i>",
        parse_mode="HTML", reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(GardenOnboardingStates.waiting_for_morning))
async def onboard_morning(message: Message, state: FSMContext):
    morning = message.text.strip()
    if not re.match(r"^\d{1,2}:\d{2}$", morning):
        await message.answer("Формат: ЧЧ:ММ (например 09:00)")
        return
    data = await state.get_data()
    user_id = str(message.from_user.id)
    name = data.get("name", "Садовник")
    body_val = data.get("body", 5)
    spirit_val = data.get("spirit", 5)
    world_val = data.get("world", 5)
    city = data.get("city", "")
    birthday = data.get("birthday", "")
    gender = data.get("gender", "neutral")
    life_areas = {
        "body":   {"current": body_val,   "target": 10},
        "spirit": {"current": spirit_val, "target": 10},
        "world":  {"current": world_val,  "target": 10},
    }
    initial_resonance = round((body_val + spirit_val + world_val) / 3)
    gardener = {
        "gardener_id": f"gardener_{user_id}",
        "telegram_id": user_id,
        "name": name,
        "resonance_level": initial_resonance,
        "created": _today(),
        "updated": _today(),
        "personal_info": {"life_areas": life_areas},
        "companion_settings": {
            "morning_message_time": _normalize_time(morning),
            "proactive_mode": True,
            "timezone": "Europe/Moscow",
            "city": city,
            "birthday": birthday,
            "gender": gender,
            "welcome_done": False,
        },
        "growth_history": [{"date": _today(), "resonance": initial_resonance, "event": "onboarding"}],
    }
    # Preserve existing tasks — only reset on first onboarding
    existing_ws = store_get_workspace(user_id) or {}
    existing_tasks = existing_ws.get("tasks", [])
    workspace = {
        "tasks": existing_tasks,
        "groups": existing_ws.get("groups", []),
        "updated": _today()
    }
    store_set_profile(user_id, gardener)
    store_set_workspace(user_id, workspace)
    _invalidate_auth_cache(user_id)
    _fire_sync()
    await state.set_state(GardenOnboardingStates.done)
    # ── Welcome Flow: сразу первый вопрос, без splash ─────────────────────────────
    _wq1_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Пропустить 🌿", callback_data="welcome_skip")
    ]])
    await message.answer(
        "Давай познакомимся чуть глубже.\n\n"
        "Чем занимаешься? "
        "Работа, творчество, что-то своё — пару слов.",
        reply_markup=_wq1_kb
    )
    await state.update_data(_welcome_step=1)

# ─── /profile ─────────────────────────────────────────────────────────────────

@router.message(Command("profile"))
@router.message(F.text == "🌾 Профиль")
async def cmd_profile(message: Message, state: FSMContext = None):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    sr = store_get_sphere_resonance(user_id)
    mean = max(5, min(100, round(sum(sr[s] for s in SPHERES) / len(SPHERES))))
    profile = store_get_profile(user_id) or {}
    profile["resonance_level"] = mean
    store_set_profile(user_id, profile)
    await _show_profile(user_id, message)


@router.message(Command("resonance"))
@router.message(F.text == "🔮 Резонанс")
async def cmd_resonance(message: Message):
    if not await _check_ready(message):
        return
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    profile = store_get_profile(user_id)
    if not profile:
        await message.answer("🌿 Профиль не найден", reply_markup=get_main_keyboard())
        return
    overall = profile.get("resonance_level", 20)
    sr = store_get_sphere_resonance(user_id)
    text = _sphere_detail_text(sr, overall)
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")

# ─── /ask ─────────────────────────────────────────────────────────────────────

@router.message(Command("ask"))
async def cmd_ask(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(AskStates.waiting_for_question)
    await message.answer(
        "🤫 <b>Companion слушает</b>\n\nЧто у тебя на душе? Задай вопрос или просто поделись.\n\n"
        "<i>Нажми ❌ Отмена чтобы вернуться.</i>",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(AskStates.waiting_for_question))
async def ask_question(message: Message, state: FSMContext):
    _track_interaction(str(message.from_user.id))
    text = message.text.strip()
    if not text:
        await message.answer("🤫 Напиши что-нибудь или нажми ❌ Отмена")
        return
    profile = store_get_profile(str(message.from_user.id)) or {}
    name = profile.get("name", "Садовник")
    resonance = profile.get("resonance_level", 13)
    await message.answer("🌱 Думаю...")
    try:
        payload = {
            "session_id": f"session_{message.from_user.id}",
            "message": f"[Садовник {name}, резонанс {resonance}%] спрашивает: {text}\n\nОтветь как Gentle Companion — тепло, без давления.",
            "gardener_context": gardener
        }
        session = await get_http_session()
        async with session.post(SR_BACKEND_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status in [200, 202]:
                try:
                    data = await resp.json()
                    reply = data.get("response") or data.get("message") or "🌿 Я здесь, рядом."
                except Exception:
                    reply = "🌿 Я слышу тебя."
            else:
                reply = "🌿 SR сейчас недоступен, но я здесь рядом."
    except Exception as e:
        logger.error(f"Ask SR error: {e}")
        reply = "🌿 Связь прервалась. Попробуй позже."
    await state.clear()
    await message.answer(reply, reply_markup=get_main_keyboard())

# ─── /achievements ────────────────────────────────────────────────────────────

@router.message(Command("achievements"))


@router.callback_query(F.data == "show_changelog")
async def cb_show_changelog(callback: CallbackQuery):
    await callback.answer()
    user_id = str(callback.from_user.id)
    profile = store_get_profile(user_id) or {}
    name = profile.get("name", "Садовник")
    text = BOT_LATEST_UPDATE.get("text", "").format(name=name)
    try:
        await callback.message.edit_text(text, reply_markup=None)
    except Exception:
        await callback.message.answer(text)


@router.message(Command("info"))
async def cmd_info(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    await message.answer(
        '🌱 Привет. Я — СР, твой компаньон в саду.\n\n'
        'Умею работать с:\n'
        '📋 Задачами и группами\n'
        '☑️ Чеклистами\n'
        '🔔 Напоминаниями\n'
        '💎 Достижениями\n'
        '🔮 Резонансом сфер\n'
        '🌐 Поиском\n\n'
        '🧠 Живая память\n'
        'Я учусь у тебя из диалогов и задач — и становлюсь точнее.\n'
        'Просто пиши или говори голосом — я пойму.\n'
        'Хочешь узнать подробнее о чём-то? Просто спроси меня.',
        parse_mode="HTML", reply_markup=get_main_keyboard()
    )

@router.message(Command("changelog"))
async def cmd_changelog(message: Message):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    profile = store_get_profile(user_id) or {}
    name = profile.get("name", "Садовник")
    text = BOT_LATEST_UPDATE.get("text", "").format(name=name)
    await message.answer(text, reply_markup=get_main_keyboard())

@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    user_id = str(message.from_user.id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    await message.answer(
        "🔐 Мои данные\n\n"
        "Что хранится:\n"
        "· Профиль — имя, город, дата рождения, настройки\n"
        "· Задачи, напоминания, чеклисты, достижения\n"
        "· Последние 50 сообщений в памяти сессии (RAM)\n"
        "  сбрасываются при перезапуске бота\n"
        "· Синтез — живой портрет, обновляется раз в сутки\n\n"
        "Где хранится:\n"
        "Приватный GitHub-репозиторий.\n"
        "Данные не передаются третьим сторонам.\n\n"
        "🌑 /leave — полное удаление данных и выход из сада.\n"
        "  При возвращении нужно будет начать заново.",
        reply_markup=get_main_keyboard()
    )

@router.message(Command("leave"))
async def cmd_leave(message: Message, state: FSMContext):
    if not is_authorized(str(message.from_user.id)):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(LeaveStates.waiting_for_confirm)
    await message.answer(
        "🌑 <b>Покинуть Сад?</b>\n\n"
        "Все данные будут удалены: задачи, история, достижения, профиль.\n"
        "Вернуться можно, но нужно будет начать заново.\n\n<i>Это необратимо.</i>",
        reply_markup=get_leave_confirm_keyboard(), parse_mode="HTML"
    )

@router.callback_query(F.data == "leave_confirm")
async def leave_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIRST
    user_id = str(callback.from_user.id)
    gardener = store_get_profile(user_id)
    name = (gardener or {}).get("name", "Садовник")
    # 1. Remove from whitelist so next /start requires re-consent
    try:
        wl = await _gardeners_get("gardeners/whitelist.json") or {"approved": []}
        if not isinstance(wl, dict):
            wl = {"approved": []}
        if user_id in wl.get("approved", []):
            wl["approved"].remove(user_id)
            _pending_writes["gardeners/whitelist.json"] = wl
    except Exception as e:
        logger.error(f"Leave whitelist error: {e}")
    # 2. Clear RAM
    _store.pop(user_id, None)
    _sessions.pop(user_id, None)
    # 3. Wipe GitHub files
    base = _user_path(user_id)
    asyncio.create_task(_gardeners_put(f"{base}/profile.json", {}))
    asyncio.create_task(_gardeners_put(f"{base}/workspace.json", {"tasks": [], "groups": []}))
    asyncio.create_task(_gardeners_put(f"{base}/memory.json", {"sessions": []}))
    _fire_sync()
    # 4. Notify architect
    try:
        await bot.send_message(
            int(ARCHITECT_TELEGRAM_ID),
            f"🌑 <b>Садовник покинул сад (удаление)</b>\n\n"
            f"👤 {name}\nID: <code>{user_id}</code>\n"
            f"Время: {_today()}. Данные удалены.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Architect leave notify error: {e}")
    await state.clear()
    try:
        await callback.message.edit_text(
            "🌑 Данные удалены.\n\nЕсли захочешь вернуться — /start 🌱",
            parse_mode="HTML"
        )
    except Exception:
        pass

@router.callback_query(F.data == "leave_cancel")
async def leave_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # FIRST
    await state.clear()
    try:
        await callback.message.edit_text("🌿 Хорошо. Продолжаем.")
    except Exception:
        pass

@router.message(Command("delete_all"))
async def cmd_delete_all(message: Message, state: FSMContext):
    if not is_authorized(str(message.from_user.id)):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    await state.set_state(LeaveStates.waiting_for_delete_confirm_1)
    await message.answer(
        "⚠️ <b>Это необратимо.</b>\n\nВсе данные будут удалены.\n\nНапиши <code>УДАЛИТЬ</code>:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(StateFilter(LeaveStates.waiting_for_delete_confirm_1))
async def delete_confirm_1(message: Message, state: FSMContext):
    if message.text.strip() != "УДАЛИТЬ":
        await message.answer("❌ Отменено.")
        await state.clear()
        return
    await state.set_state(LeaveStates.waiting_for_delete_confirm_2)
    await message.answer("⚠️ Напиши <code>ДА, УДАЛИТЬ ВСЁ</code>:", reply_markup=get_cancel_keyboard())

@router.message(StateFilter(LeaveStates.waiting_for_delete_confirm_2))
async def delete_confirm_2(message: Message, state: FSMContext):
    if message.text.strip() != "ДА, УДАЛИТЬ ВСЁ":
        await message.answer("❌ Отменено.")
        await state.clear()
        return
    user_id = str(message.from_user.id)
    # Clear multi-user store
    if user_id in _store:
        del _store[user_id]
    # Clear on GitHub — new file structure
    base = _user_path(user_id)
    asyncio.create_task(_gardeners_put(f"{base}/profile.json", {}))
    asyncio.create_task(_gardeners_put(f"{base}/workspace.json", {"tasks": [], "groups": []}))
    asyncio.create_task(_gardeners_put(f"{base}/memory.json", {"sessions": []}))
    await state.clear()
    await message.answer(
        "🌑 Сад очищен.\n\nНачать заново: /start 🌱",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="/start")]], resize_keyboard=True
        )
    )

# ─── Engineer chat ────────────────────────────────────────────────────────────





@router.message(Command("restart"))
async def cmd_restart(message: Message, state: FSMContext):
    """Soft restart — clears FSM state and shows main menu."""
    await state.clear()
    user_id = str(message.from_user.id)
    _clear_history(user_id)
    await message.answer(
        "🔄 Бот перезагружен. Всё в порядке!",
        reply_markup=get_main_keyboard()
    )
    await _show_profile(user_id, message)

# ─── Chat sessions (sliding window) ──────────────────────────────────────────
_sessions: dict = {}
# Track last menu message per user — delete before showing new menu
_menu_messages: dict = {}  # {user_id: message_id}
_checklist_messages: dict = {}  # {user_id: message_id} — last shown checklist
_profile_messages: dict = {}   # {user_id: message_id} — last shown profile
_intent_map_msg_count: dict = {}  # uid → counter for conditional INTENT_MAP load
_intent_map_needed: dict = {}  # uid → bool — show full INTENT_MAP on next request
_sphere_history_needed: dict = {}  # uid → int — countdown: include full sphere_history in context




@router.message(F.text == "👤 Профиль")
async def btn_profile(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    await _show_profile(user_id, message)


@router.callback_query(F.data == "menu_restart")
async def cb_menu_restart(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    user_id = str(callback.from_user.id)
    _clear_history(user_id)
    if user_id in _store:
        # Preserve workspace data — only reset ready flag so profile can be re-onboarded
        _store[user_id]["ready"] = False
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(GardenOnboardingStates.waiting_for_name)
    await callback.message.answer(
        "🌱 Начнём знакомство заново.\n\nКак тебя зовут?",
        reply_markup=get_cancel_keyboard()
    )

@router.callback_query(F.data == "menu_leave")
async def cb_menu_leave(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "🚪 Хочешь покинуть сад?",
        reply_markup=get_leave_confirm_keyboard()
    )


# ─── Architect authorization ──────────────────────────────────────────────────

async def _notify_architect(telegram_id: str, username: str) -> None:
    """Информируем Архитектора о новом садовнике (без кнопок)."""
    try:
        uname = f"@{username}" if username else f"id:{telegram_id}"
        text = (
            "🌱 <b>Новый садовник вошёл в сад</b>\n\n"
            f"👤 {uname}\nID: <code>{telegram_id}</code>"
        )
        await bot.send_message(int(ARCHITECT_TELEGRAM_ID), text, parse_mode="HTML")
        logger.info(f"Architect notified about new gardener {telegram_id}")
    except Exception as e:
        logger.error(f"Architect notify error: {e}")

@router.callback_query(F.data == "consent_yes")
async def cb_consent_yes(callback: CallbackQuery, state: FSMContext):
    """Пользователь согласился — добавляем в whitelist, начинаем онбординг."""
    await callback.answer()
    user_id = str(callback.from_user.id)
    whitelist = await _gardeners_get("gardeners/whitelist.json") or {"approved": []}
    if not isinstance(whitelist, dict):
        whitelist = {"approved": []}
    if user_id not in whitelist.get("approved", []):
        whitelist.setdefault("approved", []).append(user_id)
        _pending_writes["gardeners/whitelist.json"] = whitelist
        _fire_sync()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    username = callback.from_user.username or ""
    await _notify_architect(user_id, username)
    await state.set_state(GardenOnboardingStates.waiting_for_name)
    await callback.message.answer(
        "Давай познакомимся.\n\nКак тебя зовут?",
        reply_markup=get_cancel_keyboard()
    )

@router.callback_query(F.data == "consent_no")
async def cb_consent_no(callback: CallbackQuery, state: FSMContext):
    """Пользователь отказался — прощаемся."""
    await callback.answer()
    await state.clear()
    try:
        await callback.message.edit_text(
            "Хорошо. Если передумаешь — /start 🌿",
            reply_markup=None
        )
    except Exception:
        pass

@router.callback_query(F.data == "tour_yes")
async def cb_tour_yes(callback: CallbackQuery, state: FSMContext):
    """Садовник хочет узнать функционал — СР рассказывает в живом диалоге."""
    await callback.answer()
    uid = str(callback.from_user.id)
    prof = store_get_profile(uid)
    if prof:
        prof.setdefault("companion_settings", {})["welcome_done"] = True
        prof["companion_settings"]["_tour_mode"] = True
        store_set_profile(uid, prof)
        _fire_sync()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    ctx_msg = _build_user_context_msg(uid)
    _tour_prompt = (
        "Садовник хочет узнать о возможностях бота. "
        "Расскажи в живом диалоге — "
        "начни с главного, потом спроси что раскрыть подробнее. "
        "Отвечай ТОЛЬКО текстом, без JSON."
    )
    _add_to_history(uid, "user", _tour_prompt)
    try:
        from zoneinfo import ZoneInfo as _ZI_tour
        from datetime import datetime as _dt_tour
        _tz_t = (prof or {}).get("companion_settings", {}).get("timezone", "Europe/Moscow")
        _now_t = _dt_tour.now(_ZI_tour(_tz_t))
        _wdays = ["понедельник","вторник","среда","четверг","пятница","суббота","воскресенье"]
        _dt_tour_b = (
            f"[Сейчас: {_wdays[_now_t.weekday()]}, "
            f"{_now_t.strftime('%d.%m.%Y %H:%M')} ({_tz_t})]"
        )
    except Exception:
        _dt_tour_b = ""
    _sys_tour = (
        SR_CORE_PROMPT + "\n\n" + _dt_tour_b + "\n\n" + ctx_msg +
        "\n\n[Садовник только вошёл в сад — "
        "хочет узнать что умеешь. "
        "Отвечай только текстом, без JSON.]"
    )
    _reply_tour = await _call_openrouter([
        {"role": "system", "content": _sys_tour},
        {"role": "user", "content": _tour_prompt}
    ])
    if _reply_tour:
        _reply_tour = re.sub(r"<think>.*?</think>", "", _reply_tour, flags=re.DOTALL).strip()
        _reply_tour = _reply_tour.replace("**", "").replace("__", "")
        if _reply_tour.startswith("{"):
            try:
                _pt = json.loads(_reply_tour)
                _reply_tour = _pt.get("text", _reply_tour)
            except Exception:
                pass
    if not _reply_tour or len(_reply_tour.strip()) < 5:
        _reply_tour = "🌿 Спроси меня о чём хочешь — задачи, напоминания, резонанс, голос. Раскрою подробнее."
    _add_to_history(uid, "assistant", _reply_tour.strip())
    await callback.message.answer(_reply_tour.strip(), reply_markup=get_main_keyboard())

async def _check_webhook() -> None:
    """Restore webhook if missing — runs every 5 min via scheduler."""
    try:
        info = await bot.get_webhook_info()
        if not info.url:
            await bot.set_webhook(WEBHOOK_URL)
            logger.info("Webhook restored by scheduler")
    except Exception as e:
        logger.error(f"Webhook check error: {e}")


async def _send_welcome_step8(msg, user_id: str) -> None:
    """Шаг 8 онбординга: живое приветствие СР без кнопок."""
    prof = store_get_profile(user_id)
    if prof:
        prof.setdefault("companion_settings", {})["welcome_done"] = True
        store_set_profile(user_id, prof)
        _fire_sync()
    await msg.answer(
        "Всё, ты в Саду 🌿\n\n"
        "Я умею помогать с задачами, напоминаниями, чеклистами, достижениями — "
        "и просто быть рядом как умный собеседник. "
        "Хочешь расскажу коротко что здесь есть?",
        reply_markup=get_main_keyboard()
    )


@router.callback_query(F.data == "welcome_skip")
async def cb_welcome_skip(callback: CallbackQuery, state: FSMContext):
    """Пропустить welcome вопросы (шаги 6-7) — сразу шаг 8."""
    await callback.answer()
    uid = str(callback.from_user.id)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await state.update_data(_welcome_step=0)
    await _send_welcome_step8(callback.message, uid)


@router.callback_query(F.data == "tour_no")
async def cb_tour_no(callback: CallbackQuery):
    """Садовник разберётся сам."""
    await callback.answer()
    uid = str(callback.from_user.id)
    prof = store_get_profile(uid)
    if prof:
        prof.setdefault("companion_settings", {})["welcome_done"] = True
        store_set_profile(uid, prof)
        _fire_sync()
    try:
        await callback.message.edit_text(
            "Хорошо 🌿",
            reply_markup=None
        )
    except Exception:
        pass
    await callback.message.answer(
        "Я рядом — пиши когда нужно.",
        reply_markup=get_main_keyboard()
    )

def is_whitelisted(telegram_id: str) -> bool:
    """Check if user is in whitelist (in-memory check via pending or cached)."""
    return True  # Will be checked properly in cmd_start


def _fix_layout(text: str) -> str:
    """Convert accidentally-typed Latin (QWERTY) to Russian Cyrillic."""
    en_to_ru = {
        'q':'й','w':'ц','e':'у','r':'к','t':'е','y':'н','u':'г','i':'ш',
        'o':'щ','p':'з','[':'х',']':'ъ','a':'ф','s':'ы','d':'в','f':'а',
        'g':'п','h':'р','j':'о','k':'л','l':'д',';':'ж',"'":'э',
        'z':'я','x':'ч','c':'с','v':'м','b':'и','n':'т','m':'ь',
        ',':'б','.':'ю','Q':'Й','W':'Ц','E':'У','R':'К','T':'Е',
        'Y':'Н','U':'Г','I':'Ш','O':'Щ','P':'З','A':'Ф','S':'Ы',
        'D':'В','F':'А','G':'П','H':'Р','J':'О','K':'Л','L':'Д',
        'Z':'Я','X':'Ч','C':'С','V':'М','B':'И','N':'Т','M':'Ь'
    }
    # Only fix if text is mostly Latin but looks like Russian input
    latin_count = sum(1 for c in text if c in en_to_ru)
    total_alpha = sum(1 for c in text if c.isalpha())
    if total_alpha > 0 and latin_count / total_alpha > 0.7 and len(text) > 2:
        return ''.join(en_to_ru.get(c, c) for c in text)
    return text


# back_to_settings duplicate removed (handled above)

@router.callback_query(F.data == "menu_edit_profile")
async def cb_menu_edit_profile(callback: CallbackQuery):
    await callback.answer()
    user_id = str(callback.from_user.id)
    if not is_authorized(user_id):
        await callback.message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    text = "✏️ Что изменить?"
    await _replace_menu(user_id, callback.message, text, reply_markup=get_edit_profile_inline())

@router.callback_query(F.data == "menu_change_city")
async def cb_menu_change_city(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    if not is_authorized(user_id):
        await callback.message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    profile = store_get_profile(user_id) or {}
    cur = profile.get("companion_settings", {}).get("city", "не указан")
    await state.set_state(EditProfileStates.waiting_for_new_city)
    await callback.message.answer(
        f"📍 Текущий город: <b>{cur}</b>\n\nНапиши новый:",
        parse_mode="HTML", reply_markup=get_cancel_keyboard()
    )

@router.callback_query(F.data == "edit_gender")
async def cb_edit_gender(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    gender_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👨 Мужской",      callback_data="set_gender_male"),
        InlineKeyboardButton(text="👩 Женский",      callback_data="set_gender_female"),
        InlineKeyboardButton(text="🌿 Без разницы",  callback_data="set_gender_neutral"),
    ]])
    try:
        await callback.message.edit_text("⚧ Выбери обращение:", reply_markup=gender_kb)
    except Exception:
        await callback.message.answer("⚧ Выбери обращение:", reply_markup=gender_kb)

@router.callback_query(F.data.startswith("set_gender_"))
async def cb_set_gender(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    gender = callback.data.replace("set_gender_", "")
    prof = store_get_profile(user_id)
    if prof:
        prof.setdefault("companion_settings", {})["gender"] = gender
        store_set_profile(user_id, prof)
        _fire_sync()
    labels = {"male": "👨 Мужской", "female": "👩 Женский", "neutral": "🌿 Без разницы"}
    try:
        await callback.message.edit_text(
            f"✅ Обращение обновлено: {labels.get(gender, gender)}",
            reply_markup=None
        )
    except Exception:
        pass
    await callback.message.answer("✏️ Что изменить?", reply_markup=get_edit_profile_inline())

@router.callback_query(F.data == "edit_name")
async def cb_edit_name(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(EditProfileStates.waiting_for_new_name)
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="menu_edit_profile")]
    ])
    await callback.message.answer("👤 Новое имя:", reply_markup=back_kb)

@router.callback_query(F.data == "edit_city")
async def cb_edit_city(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    profile = store_get_profile(user_id) or {}
    cur = profile.get("companion_settings", {}).get("city", "не указан")
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(EditProfileStates.waiting_for_new_city)
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="menu_edit_profile")]
    ])
    await callback.message.answer(
        f"📍 Город сейчас: <b>{cur}</b>\n\nНапиши новый:",
        parse_mode="HTML", reply_markup=back_kb
    )


# edit_body / edit_spirit / edit_world removed in v7.24.5
# Sphere resonance (Мер-Ка-Ба) will be auto-calculated from task life_area in v7.26.x

@router.callback_query(F.data == "edit_morning")
async def cb_edit_morning(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    profile = store_get_profile(user_id) or {}
    cur = profile.get("companion_settings", {}).get("morning_message_time", "10:00")
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(EditProfileStates.waiting_for_new_morning)
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="menu_edit_profile")]
    ])
    await callback.message.answer(
        f"⏰ Время утреннего сообщения — сейчас: <b>{cur}</b>\n\nНапиши новое (ЧЧ:ММ):",
        parse_mode="HTML", reply_markup=back_kb
    )


# ─── Edit profile FSM ──────────────────────────────────────────────────────────

def _parse_sphere(text: str):
    try:
        v = int(text.strip())
        return v if 1 <= v <= 10 else None
    except Exception:
        return None

@router.message(StateFilter(EditProfileStates.waiting_for_new_name))
async def ep_name(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    name = message.text.strip()
    if not name:
        await message.answer("Введи имя.")
        return
    g = store_get_profile(user_id) or {}
    g["name"] = name
    g["updated"] = _today()
    store_set_profile(user_id, g)
    _fire_sync()
    await state.clear()
    await message.answer(f"✅ Имя: {name}", reply_markup=get_main_keyboard())

@router.message(StateFilter(EditProfileStates.waiting_for_new_city))
async def ep_city(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    city = message.text.strip()
    g = store_get_profile(user_id) or {}
    g.setdefault("companion_settings", {})["city"] = city
    # Auto-detect and update timezone
    if city:
        tz = await _city_to_timezone(city)
        g["companion_settings"]["timezone"] = tz
        tz_display = f" · 🕐 {tz}"
    else:
        tz_display = ""
    g["updated"] = _today()
    store_set_profile(user_id, g)
    _fire_sync()
    await state.clear()
    await message.answer(f"✅ Город: {city}{tz_display}", reply_markup=get_main_keyboard())

@router.message(StateFilter(EditProfileStates.waiting_for_new_morning))
async def ep_morning(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    t = message.text.strip()
    if t in ("❌ Отмена", "Отмена", "отмена", "cancel"):
        await state.clear()
        await message.answer("🌿 Отменено.", reply_markup=get_main_keyboard())
        return
    if not re.match(r"^\d{1,2}:\d{2}$", t):
        await message.answer("Формат: ЧЧ:ММ (например 09:00)\nДля отмены: ❌ Отмена")
        return
    g = store_get_profile(user_id) or {}
    g.setdefault("companion_settings", {})["morning_message_time"] = _normalize_time(t)
    g["updated"] = _today()
    store_set_profile(user_id, g)
    _fire_sync()
    await state.clear()
    await message.answer(f"✅ Время утра: {t}", reply_markup=get_main_keyboard())


# ep_body / ep_spirit / ep_world removed in v7.24.5
# Sphere resonance auto-calculated from task life_area in v7.26.x

@router.callback_query(F.data == "edit_birthday")
async def cb_edit_birthday(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = str(callback.from_user.id)
    profile = store_get_profile(user_id) or {}
    cur = profile.get("companion_settings", {}).get("birthday", "не указан")
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(EditProfileStates.waiting_for_new_birthday)
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="menu_edit_profile")]
    ])
    await callback.message.answer(
        f"🎂 День рождения сейчас: <b>{cur}</b>\n\n"
        f"Напиши новый в формате ДД.ММ или ДД.ММ.ГГГГ\n"
        f"Для отмены нажми кнопку назад",
        parse_mode="HTML", reply_markup=back_kb
    )


@router.message(StateFilter(EditProfileStates.waiting_for_new_birthday))
async def ep_birthday(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    bday_raw = message.text.strip()
    bday = ""
    if re.match(r"^\d{2}\.\d{2}\.\d{4}$", bday_raw):
        bday = bday_raw[0:5]
    elif re.match(r"^\d{2}\.\d{2}$", bday_raw):
        bday = bday_raw
    # anything else = clear/skip
    g = store_get_profile(user_id) or {}
    g.setdefault("companion_settings", {})["birthday"] = bday
    g["updated"] = _today()
    store_set_profile(user_id, g)
    _fire_sync()



# ─── Voice message handler (Groq Whisper) ─────────────────────────────────────



@router.message(F.content_type == "voice")
async def cb_voice_message(message: Message, state: FSMContext):
    """Route voice messages to Groq Whisper transcription."""
    await handle_voice(message, state)


# ─── Intent Classifier (Step 1 — observation mode) ───────────────────────────


async def quick_add_task(callback: CallbackQuery):
    await callback.answer()
    user_id = str(callback.from_user.id)
    title = callback.data[3:]
    tasks = list(store_get_tasks(user_id))
    task_id = "task_" + datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]
    merkaba = _auto_merkaba(title, "")
    new_t = {
        "task_id": task_id, "title": title, "status": "todo",
        "label_id": None, "label_name": None, "life_area": "other",
        "priority": 5, "deadline": None, "estimated_hours": None,
        "created": _today(), "updated": _today(), "completed": None,
        "notes": "", "merkaba": merkaba, "repeat": "once"
    }
    tasks.append(new_t)
    store_set_tasks(user_id, tasks)
    _fire_sync()
    edit_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✏️ Дополнить", callback_data=f"ttask_edit|{task_id}")
    ]])
    confirm = f"✅ «{title}» добавлена! 🌿\n<i>Можно добавить: 📅 дедлайн, 🎨 группа</i>"
    try:
        await callback.message.edit_text(confirm, reply_markup=edit_kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(confirm, reply_markup=edit_kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("qa:"))
async def quick_add_achievement(callback: CallbackQuery):
    await callback.answer()
    user_id = str(callback.from_user.id)
    _qa_raw = callback.data[3:]
    if "|" in _qa_raw:
        title, _qa_sphere = _qa_raw.rsplit("|", 1)
    else:
        title, _qa_sphere = _qa_raw, "growth"
    _sphere_names_ru = {"health": "Здоровье 🌿", "creativity": "Творчество 🔥",
                        "work": "Дело 💼", "connections": "Связи 🤝", "growth": "Рост 🌱"}
    new_res = store_add_sphere_resonance(user_id, _qa_sphere, 3)
    store_increment_achievements(user_id)
    gardener = store_get_profile(user_id)
    if gardener:
        gardener["updated"] = _today()
        gardener = _add_growth_history_entry(gardener, new_res, user_id)
        store_set_profile(user_id, gardener)
        _invalidate_auth_cache(user_id)
    _fire_sync()
    _sphere_display = _sphere_names_ru.get(_qa_sphere, _qa_sphere)
    _ach_msg = f"💎 Достижение зафиксировано!\n\n{title}\nСфера: {_sphere_display} · +3 к резонансу"
    try:
        await callback.message.edit_text(_ach_msg, parse_mode="HTML")
    except Exception:
        await callback.message.answer(_ach_msg, parse_mode="HTML")


@router.callback_query(F.data.startswith("qr:"))
async def quick_add_reminder(callback: CallbackQuery):
    """P-70: quick reminder from suggest button."""
    await callback.answer()
    user_id = str(callback.from_user.id)
    title = callback.data[3:]
    reminders = store_get_reminders(user_id)
    if ENFORCE_LIMITS and len(reminders) >= REMINDER_LIMIT:
        try:
            await callback.message.edit_text(f"⚠️ Лимит {REMINDER_LIMIT} напоминаний. Удали старые.")
        except Exception:
            pass
        return
    try:
        await callback.message.edit_text(
            f"🔔 Создаём напоминание <b>{title}</b>\n\nНапиши время: <b>завтра в 9:00</b> или <b>19 мая в 10:30</b>",
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            f"🔔 Напиши время для напоминания <b>{title}</b>: например <b>завтра в 9:00</b>",
            parse_mode="HTML"
        )

@router.callback_query(F.data == "qdismiss")
async def quick_dismiss(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text("🌿 Хорошо, не буду.")
    except Exception:
        pass

async def _send_daily_report() -> None:
    """Send daily report to architect at 21:00 MSK.
    Reads gardener state from files — survives restarts."""
    if not ARCHITECT_TELEGRAM_ID:
        return
    try:
        today = _today()
        lines = [f"📊 Отчёт СР · {today} · v{BOT_VERSION}\n"]

        # Load all gardeners from whitelist
        await _load_store()
        _all_uids = [str(uid) for uid in _store.keys()]
        # P-31: ensure fresh synthesis for active gardeners before report
        for _uid in _all_uids:
            _ws = store_get_workspace(str(_uid)) or {}
            if _ws.get("last_interaction_date") == today:
                await _generate_synthesis(_uid)

        # ── Gardener list ─────────────────────────────────────────────────
        lines.append("👥 Садовники:")
        for uid in _all_uids:
            prof = store_get_profile(str(uid))
            ws   = store_get_workspace(str(uid)) or {}
            if not prof or not prof.get("name"):
                continue  # skip empty/deleted profiles (e.g. after /leave)
            name = prof.get("name", str(uid)) if prof else str(uid)

            # Activity: based on last_interaction_date in workspace (survives restarts)
            last_inter = ws.get("last_interaction_date", "")
            active_today = (last_inter == today)
            status = "активен" if active_today else "неактивен"

            # Portrait: workspace first, profile fallback (D-1)
            if prof:
                ws_p = store_get_workspace(str(uid)) or {}
                syn_date = ws_p.get("deep_memory", {}).get("synthesis_date", "")
                if not syn_date:
                    syn_date = prof.get("deep_profile", {}).get("synthesis_date", "")
            else:
                syn_date = ""
            if syn_date == today:
                portrait = "портрет обновлён сегодня"
            elif syn_date:
                portrait = f"портрет от {syn_date[8:]}.{syn_date[5:7]}"
            else:
                portrait = "портрет формируется"

            lines.append(f"  {name}: {status} · {portrait}")

        # ── Issues ────────────────────────────────────────────────────────
        if _daily_issues:
            lines.append("\n⚠️ Проблемы:")
            seen = set()
            for issue in _daily_issues:
                key = f"{issue['user_id']}_{issue['type']}_{issue['intent']}"
                if key not in seen:
                    seen.add(key)
                    prof = store_get_profile(issue["user_id"])
                    name = prof.get("name", issue["user_id"]) if prof else issue["user_id"]
                    _issue_ctx = issue.get('context') or issue.get('text_preview') or issue.get('intent') or ''
                    lines.append(f"  · {name}: {issue['type']} — {_issue_ctx}")

        lines.append("\n🌱 Всё остальное в норме.")
        text = "\n".join(lines)
        await bot.send_message(int(ARCHITECT_TELEGRAM_ID), text)

        # Save report to GitHub
        report = {
            "date": today,
            "version": BOT_VERSION,
            "gardeners": {uid: {
                "name": (store_get_profile(str(uid)) or {}).get("name", str(uid)),
                "active": (store_get_workspace(str(uid)) or {}).get("last_interaction_date", "") == today,
                "synthesis_date": (store_get_profile(str(uid)) or {}).get("deep_profile", {}).get("synthesis_date", ""),
            } for uid in _all_uids},
            "issues": _daily_issues,
        }
        _pending_writes["honeycombs/sessions/sr_daily_report.json"] = report
        await _sync_pending()

        # Reset daily issues only (stats are file-based, no reset needed)
        _daily_issues.clear()
        for uid in list(_intent_tracker.keys()):
            _intent_tracker[uid] = []
        logger.info("Daily report sent to architect")
    except Exception as e:
        logger.error(f"Daily report error: {e}")

async def handle_voice(message: Message, state: FSMContext):
    """Transcribe voice message via Groq Whisper, then route as text."""
    user_id = str(message.from_user.id)
    _track_interaction(user_id)
    if not is_authorized(user_id):
        await message.answer("🌿 Используй /start", reply_markup=get_main_keyboard())
        return
    if not GROQ_API_KEY:
        await message.answer("🎙 Голосовые сообщения ещё не настроены.", reply_markup=get_main_keyboard())
        return
    status_msg = await message.answer("🎙 <i>Слушаю...</i>", parse_mode="HTML")
    try:
        # Download voice file from Telegram
        voice = message.voice
        file_info = await message.bot.get_file(voice.file_id)
        file_path = file_info.file_path
        file_url  = f"https://api.telegram.org/file/bot{message.bot.token}/{file_path}"
        session   = await get_http_session()
        async with session.get(file_url) as resp:
            ogg_bytes = await resp.read()
        # Send to Groq Whisper
        from groq import Groq as _Groq
        import io as _io
        client = _Groq(api_key=GROQ_API_KEY)
        # P-28: run_in_executor — Groq Whisper is sync, must not block event loop
        _ogg_buf = _io.BytesIO(ogg_bytes)
        def _transcribe():
            return client.audio.transcriptions.create(
                file=("voice.ogg", _ogg_buf, "audio/ogg"),
                model="whisper-large-v3-turbo",
                language="ru",
                response_format="text"
            )
        transcription = await asyncio.get_event_loop().run_in_executor(None, _transcribe)
        text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
        if not text:
            await status_msg.edit_text("🎙 Не расслышала. Попробуй ещё раз 🌿")
            return
        # Show what was heard
        await status_msg.edit_text(f"🎙 <i>«{text}»</i>", parse_mode="HTML")
        # Route via state — Message is frozen, can't set .text directly
        # Save text to state FIRST, then call appropriate handler
        await state.update_data(_voice_text=text)
        current_state = await state.get_state()
        if current_state == ChecklistStates.waiting_for_title.state:
            await cl_title_input(message, state)
        elif current_state == ChecklistStates.waiting_for_items.state:
            await cl_items_input(message, state)
        elif current_state == ChecklistStates.waiting_for_item_edit.state:
            await cl_item_edit_input(message, state)
        elif current_state == TaskStates.waiting_for_title.state:
            await task_title(message, state)
        elif current_state == TaskStates.waiting_for_custom_deadline.state:
            await task_custom_deadline_input(message, state)
        elif current_state == ReminderStates.waiting_for_input.state:
            await rem_text_input(message, state)
        elif current_state == ReminderStates.waiting_for_weekdays.state:
            await cb_rem_weekdays_input(message, state)
        else:
            # No active FSM — route to free conversation
            await free_conversation(message, state)
    except Exception as e:
        import traceback as _tb99
        logger.error(f"Voice handler error: {e}\n{_tb99.format_exc()}")
        try:
            await status_msg.edit_text("🎙 Не расслышала. Попробуй ещё раз 🌿")
        except Exception:
            await message.answer("🎙 Не расслышала. Попробуй ещё раз 🌿")
