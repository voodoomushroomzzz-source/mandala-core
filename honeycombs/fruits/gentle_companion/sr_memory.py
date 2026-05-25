# -*- coding: utf-8 -*-
"""
sr_memory.py — SR Memory & Synthesis
Daily synthesis, observation distillation, observation detection.

Part of: honeycombs/fruits/gentle_companion/
Phase: 5 (depends on config.py, store.py, helpers.py, github_api.py)

Key functions:
  _distill_observations()         — compress old observations into insights
  _generate_synthesis()           — daily living portrait of gardener
  _detect_and_save_observation()  — detect patterns in gardener messages
"""

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