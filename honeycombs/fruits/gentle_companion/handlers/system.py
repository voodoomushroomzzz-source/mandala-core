# -*- coding: utf-8 -*-
"""
handlers/system.py — System, Onboarding, Profile, Schedulers, Voice
Phase: 6 (depends on config.py, store.py, helpers.py, ui.py, github_api.py)
"""

async def send_morning_greeting(telegram_id: str) -> None:
    """Morning greeting v3: alive SR message, personalised via synthesis + history."""
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
        if missed_days >= 2:
            missed_note = f"Садовник не писал {missed_days} дней. Соскучилась, но не дави."
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
            + (missed_note + "\n" if missed_note else "") +
            "\nРуководствуясь ахимсой, напиши одно тёплое утреннее приветствие.\n"
            "Это начало дня — можно мягко подсветить что сегодня ждёт, "
            "но без давления и списков. Если есть задача на сегодня — "
            "упомянуть как часть дня, а не как обязанность.\n"
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
        await bot.send_message(int(uid), msg.strip(), parse_mode="HTML", reply_markup=get_main_keyboard(), disable_web_page_preview=True)
        _add_to_history(uid, "assistant", msg.strip())
        _morning_sent[uid] = today_str
        ws["last_morning_date"] = today_str
        ws["_greeting_sent_date"] = today_str  # P-41: greeting flag
        store_set_workspace(uid, ws)
        _mark_proactive_sent(uid)
        # Update last_notified_version
        last_ver = gardener.get("last_notified_version", "")
        if last_ver != BOT_VERSION:
            gardener["last_notified_version"] = BOT_VERSION
            store_set_profile(uid, gardener)
    except Exception as e:
        logger.error(f"Morning greeting error: {e}")

async def send_evening_checkin(telegram_id: str) -> None:
    try:
        phase = _silence_phase(telegram_id)
        if phase == 3 or not _can_send_proactive(telegram_id):
            return
        gardener = store_get_profile(str(telegram_id))
        if not gardener:
            return
        if not gardener.get("companion_settings", {}).get("proactive_mode", True):
            return
        name = gardener.get("name", "Садовник")
        text = (
            f"🌒 Добрый вечер, {name}.\n\n"
            f"Что произошло сегодня? Если было что-то важное — "
            f"зафиксируй достижение: /achievements\n\nДо завтра 🌿"
        )
        await bot.send_message(int(telegram_id), text, reply_markup=get_main_keyboard())
        _mark_proactive_sent(telegram_id)
    except Exception as e:
        logger.error(f"Evening check-in error: {e}")


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
            tz_name = settings.get("timezone", "Europe/Moscow")
            if settings.get("morning_message_time") and _time_matches(settings["morning_message_time"], tz_name):
                await send_morning_greeting(uid)
            else:
                # Catch-up: if morning brief was missed (e.g. Render sleep), send it now
                try:
                    from zoneinfo import ZoneInfo as _ZI_p
                    from datetime import datetime as _dt_p
                    tz_p = _ZI_p(tz_name)
                    now_p = _dt_p.now(tz_p)
                    today_p = now_p.strftime("%Y-%m-%d")
                    morning_h, morning_m = map(int, settings["morning_message_time"].split(":"))
                    morning_dt = now_p.replace(hour=morning_h, minute=morning_m, second=0, microsecond=0)
                    ws = store_get_workspace(uid) or {}
                    last_morning = ws.get("last_morning_date", "")
                    if (last_morning != today_p and now_p >= morning_dt
                            and _can_send_proactive(uid)
                            and _morning_sent.get(uid) != today_p):
                        await send_morning_greeting(uid)
                    else:
                        pass  # P-39: silence tone handled by _send_daytime_proactive
                except Exception:
                    pass  # P-39: silence tone handled by _send_daytime_proactive
            # P-37: daytime proactive window (12-19, 3h silence)
            await _send_daytime_proactive(uid)
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

@router.callback_query(F.data == "menu_tasks_mgmt")


async def run_resonance_decay() -> None:
    """Daily resonance decay: silence + overdue tasks. Runs at 03:00."""
    try:
        from datetime import datetime as _dtr3
        today_s = _dtr3.now().strftime("%Y-%m-%d")
        for uid, user_store in list(_store.items()):
            if not isinstance(user_store, dict) or not user_store.get("ready"):
                continue
            ws = store_get_workspace(uid) or {}
            if ws.get("_decay_date") == today_s:
                continue
            days_silent = _days_since_last_interaction(uid)
            if days_silent <= 2:
                decay = 0
            elif days_silent <= 6:
                decay = 1
            elif days_silent <= 13:
                decay = 2
            else:
                decay = 3
            tasks   = store_get_tasks(uid)
            overdue = [t for t in tasks
                       if t.get("deadline") and t["deadline"] < today_s
                       and t.get("status") != "completed"]
            decay += len(overdue)
            if decay > 0:
                sr = store_get_sphere_resonance(uid)
                for s in SPHERES:
                    sr[s] = max(5, sr[s] - decay)
                store_set_sphere_resonance(uid, sr)
                mean = max(5, round(sum(sr[s] for s in SPHERES) / len(SPHERES)))
                profile2 = store_get_profile(uid) or {}
                profile2["resonance_level"] = mean
                store_set_profile(uid, profile2)
            ws["_decay_date"] = today_s
            store_set_workspace(uid, ws)
            _fire_sync()
    except Exception as e:
        logger.error(f"Resonance decay error: {e}", exc_info=True)


async def _send_daytime_proactive(telegram_id: str) -> bool:
    """Send proactive message during daytime window (12-19, 3h silence).
    Returns True if message was sent."""
    try:
        uid = str(telegram_id)
        ws = store_get_workspace(uid) or {}
        # Already sent today?
        if ws.get("_day_proactive_sent_date") == _today():
            return False
        prof = store_get_profile(uid)
        if not prof:
            return False
        name = prof.get("name", "Садовник")
        tz_name = prof.get("companion_settings", {}).get("timezone", "Europe/Moscow")
        from zoneinfo import ZoneInfo as _ZI_dp
        from datetime import datetime as _dt_dp, timedelta as _td_dp
        try:
            tz = _ZI_dp(tz_name)
        except Exception:
            tz = _ZI_dp("Europe/Moscow")
        now = _dt_dp.now(tz)
        hour = now.hour
        # Window: 14:00–21:00 (P-69)
        if hour < 14 or hour >= 21:
            return False
        # Check 3 hours since last interaction
        last_dt_str = ws.get("last_interaction_datetime", "")
        if last_dt_str:
            try:
                last_dt = _dt_dp.fromisoformat(last_dt_str)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=tz)
                if (now - last_dt) < _td_dp(hours=3):
                    return False
            except Exception:
                pass  # if parse fails, proceed
        # Build context for SR — P-38: умный фарш
        # D-1: workspace first, profile fallback
        ws_dp = store_get_workspace(uid) or {}
        mem = ws_dp.get("deep_memory") or prof.get("deep_profile", {}).get("memory", {})
        history = _get_history(uid)
        recent = history[-20:] if history else []
        history_text = "\n".join(
            f"[{m.get('ts','')[:10]}] {'🧑' if m.get('role')=='user' else '🌿'}: {m.get('content','')}"
            for m in recent
        ) if recent else "диалога ещё нет"
        core = mem.get("core", "")
        interests = mem.get("interests", {})
        confirmed = interests.get("confirmed", [])
        snapshots = mem.get("snapshots", [])[-3:]
        snapshots_text = "\n".join(f"- {s.get('date','')}: {s.get('text','')}" for s in snapshots) if snapshots else ""
        _dp_dp = prof.get("deep_profile", {})  # P-55: fix NameError (was using global Dispatcher)
        sr_obs = _dp_dp.get("sr_observations", [])[-5:]
        obs_text = "\n".join(f"- {o.get('date','')}: {o.get('text','')}" for o in sr_obs) if sr_obs else ""
        from datetime import date as _date_dp
        three_months_ago = (_date_dp.today().replace(day=1) - _td_dp(days=1)).replace(day=1)
        cutoff = three_months_ago.strftime("%Y-%m")
        sphere_hist = [s for s in _dp_dp.get("sphere_history", []) if s.get("month", "") >= cutoff]
        sphere_text = "\n".join(
            f"- {s.get('month')}: {s.get('sphere')} {s.get('resonance_level', 0)}%"
            for s in sphere_hist
        ) if sphere_hist else ""
        tasks = store_get_tasks(uid)
        active = [t for t in tasks if t.get("status") != "completed"]
        today_str = now.strftime("%Y-%m-%d")
        hot = [t for t in active if t.get("deadline") and t["deadline"] <= today_str]
        tomorrow_str = (now + _td_dp(days=1)).strftime("%Y-%m-%d")
        tomorrow_tasks = [t for t in active if t.get("deadline") == tomorrow_str]
        tasks_context = ""
        if hot:
            tasks_context += f"\nГорящие (сегодня/просрочены): {', '.join(t['title'] for t in hot[:3])}"
        if tomorrow_tasks:
            tasks_context += f"\nНа завтра: {', '.join(t['title'] for t in tomorrow_tasks[:3])}"
        current_time = f"{now.strftime('%H:%M')}, {['пн','вт','ср','чт','пт','сб','вс'][now.weekday()]}"
        # P-39: дни тишины
        try:
            last_interaction = ws.get("last_interaction_date", "")
            if last_interaction:
                from datetime import date as _date_si
                days_silent = (_date_si.today() - _date_si.fromisoformat(last_interaction)).days
            else:
                days_silent = 0
        except Exception:
            days_silent = 0
        if days_silent >= 7:
            silence_note = f"Садовник молчит {days_silent} дней. Тон — очень тихий, одна фраза, без давления."
        elif days_silent >= 3:
            silence_note = f"Садовник молчит {days_silent} дней. Тон — мягкий, как друг который просто даёт знать что рядом."
        else:
            silence_note = ""
        # P-62fix: передаём флаг приветствия в промпт
        _dp_greeting_flag = ws.get("_greeting_sent_date", "") == _today(tz_name)
        _dp_greeting_note = (
            "[Утреннее приветствие сегодня уже было — НЕ начинай с приветствия. "
            "Начни сразу с наблюдения, вопроса или контекста дня садовника.]"
            if _dp_greeting_flag else ""
        )
        prompt_parts = [
            f"Сейчас {current_time} (таймзона {tz_name}). Подходящий момент написать садовнику {name}.",
            "",
            f"ЖИВОЙ ПОРТРЕТ:\n{core if core else 'формируется'}",
        ]
        if snapshots_text:
            prompt_parts += ["", f"ЧТО ИЗМЕНИЛОСЬ В ПОСЛЕДНИЕ ДНИ:\n{snapshots_text}"]
        if obs_text:
            prompt_parts += ["", f"НАБЛЮДЕНИЯ ИЗ ДИАЛОГОВ:\n{obs_text}"]
        if sphere_text:
            prompt_parts += ["", f"ДИНАМИКА СФЕР (3 мес):\n{sphere_text}"]
        if confirmed:
            prompt_parts += ["", f"ИНТЕРЕСЫ: {', '.join(i['name'] if isinstance(i, dict) else i for i in confirmed[:10])}"]
        prompt_parts += [
            "",
            f"Сегодня {today_str}. ПОСЛЕДНИЕ 20 СООБЩЕНИЙ (дата указана перед каждым — учитывай насколько давно):\n{history_text}",
            "",
            f"АКТИВНЫЕ ЗАДАЧИ:{tasks_context if tasks_context else ' нет'}",
            "",
            f"Дней молчания: {days_silent}." + (" " + silence_note if silence_note else ""),
        ] + ([_dp_greeting_note] if _dp_greeting_note else []) + [
            "Руководствуясь ахимсой, напиши одно тёплое сообщение садовнику.",
            "Если чувствуешь что повода нет — верни \"SKIP\".",
            "Ответь ТОЛЬКО текстом сообщения или \"SKIP\". Без JSON.",
        ]
        prompt = "\n".join(prompt_parts)
        msg = await _call_openrouter([
            {"role": "system", "content": SR_CORE_PROMPT},
            {"role": "user", "content": prompt}
        ])
        if msg and msg.strip().upper() != "SKIP" and len(msg.strip()) >= 5:
            await bot.send_message(int(uid), msg.strip(), reply_markup=get_main_keyboard())
            _add_to_history(uid, "assistant", msg.strip())
            ws["_day_proactive_sent_date"] = _today()
            store_set_workspace(uid, ws)
            _fire_sync()
            logger.info(f"Daytime proactive sent to {uid}")
            return True
        return False
    except Exception as e:
        logger.error(f"Daytime proactive error for {telegram_id}: {e}")
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
    await callback.message.answer(
        "📍 В каком городе ты живёшь?\n"
        "<i>Буду учитывать при поиске и в утреннем сообщении.</i>\n\n"
        "Можно пропустить — напиши <b>пропустить</b>",
        parse_mode="HTML", reply_markup=get_cancel_keyboard()
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
    await message.answer(
        "🎂 Когда твой день рождения?\n"
        "<i>Формат: ДД.ММ (например 15.03)</i>\n\n"
        "Можно пропустить — напиши <b>пропустить</b>",
        parse_mode="HTML", reply_markup=get_cancel_keyboard()
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
    # Preserve existing tasks and achievements — only reset on first onboarding
    existing_ws = store_get_workspace(user_id) or {}
    existing_tasks = existing_ws.get("tasks", [])
    existing_achievements = existing_ws.get("achievements", [])
    workspace = {
        "tasks": existing_tasks,
        "groups": existing_ws.get("groups", []),
        "achievements": existing_achievements,
        "updated": _today()
    }
    store_set_profile(user_id, gardener)
    store_set_workspace(user_id, workspace)
    _invalidate_auth_cache(user_id)
    _fire_sync()
    await state.set_state(GardenOnboardingStates.done)
    # ── Welcome Flow: сразу первый вопрос, без splash ─────────────────────────────
    await message.answer(
        "Давай познакомимся чуть глубже.\n\n"
        "Чем занимаешься? "
        "Работа, творчество, что-то своё — пару слов.",
        reply_markup=get_main_keyboard()
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
    asyncio.create_task(_gardeners_put(f"{base}/workspace.json", {"tasks": [], "groups": [], "achievements": []}))
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
    asyncio.create_task(_gardeners_put(f"{base}/workspace.json", {"tasks": [], "groups": [], "achievements": []}))
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
    if user_id in _menu_messages:
        try:
            await message.bot.delete_message(message.chat.id, _menu_messages[user_id])
        except Exception:
            pass
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
    try:
        await callback.message.edit_text("✏️ Что изменить?", reply_markup=get_edit_profile_inline())
    except Exception:
        pass

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
            sorted_s = sorted(by_sphere.items(), key=lambda x: x[1], reverse=True)
            for cat, cnt in sorted_s:
                if cat in sphere_names:
                    lines.append(f"  {sphere_names[cat]} — {cnt}")
    return "\n".join(lines)

async def _distill_observations(user_id: str, dp: dict) -> None:
    """Distill old sr_observations into long_term_insights before they are dropped."""
    obs = dp.get("sr_observations", [])
    if len(obs) < 45:
        return
    # Take oldest 20 before they get cut
    old_obs = obs[:20]
    old_text = "\n".join(f"- {o['date']}: {o['text']}" for o in old_obs)
    insight = await _call_openrouter([
        {"role": "system", "content": (
            "Ты — SR. Сожми эти наблюдения в один долгосрочный инсайт (1-2 предложения). "
            "Только устойчивые паттерны. На русском."
        )},
        {"role": "user", "content": f"Наблюдения:\n{old_text}\n\nСожми в инсайт:"}
    ])
    if insight:
        insights = dp.setdefault("long_term_insights", [])
        insights.append({"date": _today(), "text": insight})
        dp["long_term_insights"] = insights[-10:]
        logger.info(f"Long-term insight distilled for {user_id}")


async def _generate_synthesis(user_id: str) -> None:
    """Generate living memory core once per active day."""
    prof = store_get_profile(user_id)
    if not prof:
        return
    dp = prof.setdefault("deep_profile", {})
    mem = dp.setdefault("memory", {})  # P-21: moved above guard

    # Daily guard — run only once per day
    # Daily guard removed — allow regeneration if core is empty
    if dp.get("synthesis_date") == _today() and mem.get("core"):
        return

    # Дистилляция если наблюдений накопилось много
    await _distill_observations(user_id, dp)

    # Собираем входные данные
    sr_obs = dp.get("sr_observations", [])[-10:]
    old_obs = dp.get("observations", [])[-5:]
    # Format old observations to match sr_observations structure
    formatted_old = []
    for o in old_obs:
        if isinstance(o, str):
            formatted_old.append({"date": o[:10] if len(o) > 10 else "", "text": o})
        elif isinstance(o, dict):
            formatted_old.append(o)
    obs = sr_obs + formatted_old
    if len(obs) < 2 and mem.get("core"):
        return  # keep existing core, not enough new data
    if len(obs) < 2 and not mem.get("core"):
        # Generate initial core from profile data even without observations
        obs = [{"date": _today(), "text": f"Садовник активен. Резонанс: {prof.get('resonance_level', 0)}%"}]
        if len(obs) < 2:
            obs.append({"date": _today(), "text": "Начало пути в Мандале"})

    core     = mem.get("core", "")
    snapshots = mem.get("snapshots", [])
    insights  = dp.get("long_term_insights", [])
    old_obs   = dp.get("observations", [])[-5:]  # streak/sphere observations

    # Закрытые задачи
    tasks = store_get_tasks(user_id)
    completed = [t for t in tasks if t.get("status") == "completed"][-15:]
    tasks_text = "\n".join(f"- {t['title']}" for t in completed) if completed else "нет"

    obs_text      = "\n".join(f"- {o['date']}: {o['text']}" for o in obs)
    insights_text = "\n".join(f"- {i['date']}: {i['text']}" for i in insights) if insights else "нет"
    snapshots_text = "\n".join(f"- {s['date']}: {s['text']}" for s in snapshots[-5:]) if snapshots else "нет"
    old_obs_text  = "\n".join(f"- {o}" for o in old_obs) if old_obs else "нет"

    # P-44: полная история диалога — источник интересов, тем, медиа
    _hist_syn = _get_history(user_id)
    dialog_text = "\n".join(
        f"{'Садовник' if m.get('role') == 'user' else 'СР'}: {(m.get('content') or '')[:200]}"
        for m in _hist_syn
    ) if _hist_syn else "нет"

    # Текущие интересы и медиа для SR
    def _fmt_syn_item(i):
        if isinstance(i, dict):
            return f"{i.get('name','?')} (×{i.get('count',1)}, last:{i.get('last_seen','')})"
        return str(i)
    _cur_interests = mem.get("interests", {})
    _cur_media = mem.get("media", {})
    _int_conf_txt = ", ".join(_fmt_syn_item(i) for i in _cur_interests.get("confirmed", [])) or "нет"
    _int_ment_txt = ", ".join(_fmt_syn_item(i) for i in _cur_interests.get("mentioned", [])) or "нет"
    _med_conf_txt = ", ".join(_fmt_syn_item(i) for i in _cur_media.get("confirmed", [])) or "нет"
    _med_ment_txt = ", ".join(_fmt_syn_item(i) for i in _cur_media.get("mentioned", [])) or "нет"

    prompt = f"""ТЕКУЩИЙ ПОРТРЕТ:
{core if core else "пока не сформирован"}

ДОЛГОСРОЧНЫЕ ИНСАЙТЫ:
{insights_text}

СНАПШОТЫ ПРОШЛЫХ ДНЕЙ (только контекст — НЕ повторяй эти события в новом snapshot):
{snapshots_text}

ПАТТЕРНЫ АКТИВНОСТИ:
{old_obs_text}

НАБЛЮДЕНИЯ ИЗ ДИАЛОГОВ:
{obs_text}

ЗАКРЫТЫЕ ЗАДАЧИ:
{tasks_text}

ТЕКУЩИЕ ИНТЕРЕСЫ:
  confirmed: {_int_conf_txt}
  mentioned: {_int_ment_txt}

ТЕКУЩИЕ МЕДИА (книги/фильмы/музыка):
  confirmed: {_med_conf_txt}
  mentioned: {_med_ment_txt}

ЖИВОЙ ДИАЛОГ (все сообщения — главный источник интересов, тем, медиа):
{dialog_text}

ПРАВИЛА обновления интересов и медиа:
- confirmed макс 20 интересов, 10 медиа. mentioned макс 20 и 10.
- Если confirmed не упоминался 30+ дней — перемести в mentioned.
- Если mentioned не упоминался 15+ дней — удали.
- Остальные решения о перемещении — на твоё усмотрение по count и last_seen.
- Культурный опыт: определяй тип из контекста:
  film (фильм/документалка), series (сериал), book (книга/поэзия), music (музыка/альбом/концерт),
  podcast (подкаст/лекция), art (картина/скульптура/фото), theatre (спектакль/балет/опера),
  architecture (здание/памятник/чудо света), game (игра), exhibition (выставка/музей/инсталляция).

Ответь строго в JSON (без markdown):
{{
  "core": "живой портрет 4-6 предложений — состояние, ценности, стиль общения, паттерны, вектор роста.",
  "snapshot": "1-2 предложения — ТОЛЬКО события {_today()} (не повторяй из прошлых снапшотов)",
  "confirmed_interests": ["интерес1", "интерес2"],
  "mentioned_interests": ["интерес3"],
  "confirmed_media": [{{"name": "Название", "type": "film"}}],
  "mentioned_media": [{{"name": "Название", "type": "book"}}]
}}"""

    import json as _json_s
    raw = await _call_openrouter([
        {"role": "system", "content": (
            "Ты — SR, хранитель памяти Сада. Твоя задача — понимать садовника глубже "
            "чтобы общаться персонализированно. Помогай вести к балансу и росту. "
            "Отвечай только JSON без markdown."
        )},
        {"role": "user", "content": prompt}
    ])

    if not raw:
        return
    try:
        import re as _re_s
        raw_clean = _re_s.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw_clean = _re_s.sub(r"\s*```\s*$", "", raw_clean).strip()
        result = _json_s.loads(raw_clean)

        new_core     = result.get("core", "").strip()
        new_snapshot = result.get("snapshot", "").strip()
        confirmed    = result.get("confirmed_interests", [])
        mentioned    = result.get("mentioned_interests", [])

        if new_core:
            mem["core"] = new_core
        if new_snapshot:
            snaps = mem.get("snapshots", [])
            snaps.append({"date": _today(), "text": new_snapshot})
            mem["snapshots"] = snaps[-5:]

        # P-44: per-item интересы с count/last_seen + медиа
        from datetime import date as _date_syn
        _today_syn = _today()

        def _update_items(current_list, new_names, max_count):
            """Обновить список объектов: count++ если есть, добавить если нет."""
            # Нормализуем старый формат (строки → объекты)
            normalized = []
            for item in current_list:
                if isinstance(item, str):
                    normalized.append({"name": item, "count": 1, "last_seen": _today_syn})
                else:
                    normalized.append(item)
            # Обновляем count и last_seen для упомянутых
            existing_names = {i["name"].lower(): i for i in normalized}
            for name in new_names:
                if not name:
                    continue
                key = name.lower()
                if key in existing_names:
                    existing_names[key]["count"] = existing_names[key].get("count", 1) + 1
                    existing_names[key]["last_seen"] = _today_syn
                else:
                    normalized.append({"name": name, "count": 1, "last_seen": _today_syn})
            # Обрезаем по last_seen (вытесняем самые старые)
            normalized.sort(key=lambda x: x.get("last_seen", ""), reverse=True)
            return normalized[:max_count]

        def _decay_items(items, max_days):
            """Удалить элементы старше max_days дней."""
            result = []
            for item in items:
                if isinstance(item, str):
                    result.append({"name": item, "count": 1, "last_seen": _today_syn})
                    continue
                try:
                    days = (_date_syn.today() - _date_syn.fromisoformat(item.get("last_seen", _today_syn))).days
                    if days < max_days:
                        result.append(item)
                except Exception:
                    result.append(item)
            return result

        # Интересы
        interests = mem.setdefault("interests", {"confirmed": [], "mentioned": []})
        interests["confirmed"] = _decay_items(interests.get("confirmed", []), 30)
        interests["mentioned"] = _decay_items(interests.get("mentioned", []), 15)
        conf_names = [i if isinstance(i, str) else i.get("name","") for i in interests["confirmed"]]
        ment_new = [n for n in mentioned if n and n.lower() not in [c.lower() for c in conf_names]]
        interests["confirmed"] = _update_items(interests["confirmed"], confirmed, 20)
        interests["confirmed"] = [x for x in interests["confirmed"] if (x.get("count", 1) if isinstance(x, dict) else 1) >= 2]
        interests["mentioned"] = _update_items(interests["mentioned"], ment_new, 20)

        # Медиа
        media = mem.setdefault("media", {"confirmed": [], "mentioned": []})
        conf_media_raw = result.get("confirmed_media", [])
        ment_media_raw = result.get("mentioned_media", [])
        conf_media_names = [m.get("name","") if isinstance(m,dict) else m for m in conf_media_raw]
        ment_media_names = [m.get("name","") if isinstance(m,dict) else m for m in ment_media_raw]
        # Сохраняем тип медиа при добавлении
        media["confirmed"] = _decay_items(media.get("confirmed", []), 30)
        media["mentioned"] = _decay_items(media.get("mentioned", []), 15)
        for m in conf_media_raw:
            if isinstance(m, dict) and m.get("name"):
                key = m["name"].lower()
                existing = next((x for x in media["confirmed"] if isinstance(x,dict) and x.get("name","").lower()==key), None)
                if existing:
                    existing["count"] = existing.get("count",1) + 1
                    existing["last_seen"] = _today_syn
                else:
                    media["confirmed"].append({"name": m["name"], "type": m.get("type","unknown"), "count": 1, "last_seen": _today_syn})
        for m in ment_media_raw:
            if isinstance(m, dict) and m.get("name"):
                key = m["name"].lower()
                in_conf = any(isinstance(x,dict) and x.get("name","").lower()==key for x in media["confirmed"])
                if not in_conf:
                    existing = next((x for x in media["mentioned"] if isinstance(x,dict) and x.get("name","").lower()==key), None)
                    if existing:
                        existing["count"] = existing.get("count",1) + 1
                        existing["last_seen"] = _today_syn
                    else:
                        media["mentioned"].append({"name": m["name"], "type": m.get("type","unknown"), "count": 1, "last_seen": _today_syn})
        media["confirmed"] = sorted(media["confirmed"], key=lambda x: x.get("last_seen",""), reverse=True)[:10]
        media["mentioned"] = sorted(media["mentioned"], key=lambda x: x.get("last_seen",""), reverse=True)[:10]

        dp["memory"] = mem
        dp["synthesis"] = new_core  # backward compat
        dp["synthesis_date"] = _today()
        store_set_profile(user_id, prof)
        # P-31: reset pending synthesis counter after successful synthesis
        ws_syn = store_get_workspace(user_id) or {}
        ws_syn["deep_memory"] = mem
        ws_syn["_pending_synthesis_count"] = 0
        store_set_workspace(user_id, ws_syn)
        logger.info(f"Living memory updated for {user_id}")
    except Exception as e:
        logger.warning(f"Synthesis parse error for {user_id}: {e}")

async def _detect_and_save_observation(user_id: str, text: str) -> None:
    """Detect significant signals in user message and save to sr_observations."""
    emotion = _detect_emotion(text)
    if emotion == "negative":
        _add_sr_observation(user_id, "emotional_signal",
            f"негативный сигнал: {text[:80]}", sphere=None)
    elif emotion == "positive":
        _add_sr_observation(user_id, "positive",
            f"позитивный сигнал: {text[:80]}", sphere=None)



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


# ─── Voice message handler (Groq Whisper) ─────────────────────────────────────



@router.message(F.content_type == "voice")
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
        logger.error(f"Voice handler error: {e}")
        try:
            await status_msg.edit_text("🎙 Не расслышала. Попробуй ещё раз 🌿")
        except Exception:
            await message.answer("🎙 Не расслышала. Попробуй ещё раз 🌿")

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
    if len(reminders) >= REMINDER_LIMIT:
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