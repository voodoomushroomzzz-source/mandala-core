# -*- coding: utf-8 -*-
"""
sr_conversation.py -- SR Intent Classifier & Free Conversation. Phase: 5.
"""

# ─── Intent Classifier (Step 1 — observation mode) ───────────────────────────
_CLASSIFIER_PROMPT = """Ты — классификатор намерений. Только JSON, без лишних слов.

""" + SR_INTENT_LIGHT + """

ДОПОЛНИТЕЛЬНЫЙ INTENT — suggest_action:
Используй когда садовник НАМЕКАЕТ на намерение, но НЕ даёт чёткую команду.
Примеры:
- "надо бы записаться к врачу" → suggest_action, action.type="add_task", action.title="Записаться к врачу", 0.7
- "стоит позвонить маме" → suggest_action, action.type="add_task", action.title="Позвонить маме", 0.7
- "хочу начать бегать" → suggest_action, action.type="add_task", action.title="Начать бегать", 0.65
- "прошёл 10 км сегодня" → suggest_action, action.type="add_achievement", action.title="10 км пешком", action.sphere="health", 0.7
- "не забыть завтра встретить друга" → suggest_action, action.type="create_reminder", action.title="Встретить друга", 0.7
ВАЖНО: suggest_action только если намерение неявное. Если команда чёткая — используй прямой intent.

Верни строго JSON:
{"intent": "<intent или none>", "action": {<параметры или пусто>}, "confidence": <0.0-1.0>}

Если не уверен или это разговор — верни: {"intent": "none", "action": {}, "confidence": 1.0}
Никакого текста вне JSON. Никаких пояснений."""

def _build_enriched_text(history: list, current_text: str, n: int = 3) -> str:
    """Enriches classifier input with recent dialog context.
    Helps classifier resolve short/contextual messages like 'перенесем на 10.06'
    by including the preceding conversation turns.
    """
    recent = history[-n:] if len(history) >= n else history
    if not recent:
        return current_text
    ctx_lines = []
    for m in recent:
        role = "SR" if m.get("role") == "assistant" else "Садовник"
        content = (m.get("content") or "")[:150].strip()
        if content and not content.startswith("[Система:"):
            ctx_lines.append(f"{role}: {content}")
    if not ctx_lines:
        return current_text
    ctx = "\n".join(ctx_lines)
    return f"[Контекст диалога:\n{ctx}]\nТекущее сообщение: {current_text}"


async def _classify_intent(uid: str, text: str) -> dict | None:
    """Step 1: observation-only classifier. Calls fast model, logs result.
    Does NOT affect bot behaviour yet — only collects data."""
    try:
        profile_cl = store_get_profile(uid) or {}
        tz_cl = profile_cl.get("companion_settings", {}).get("timezone", "Europe/Moscow")
        from zoneinfo import ZoneInfo as _ZI_cl
        from datetime import datetime as _dt_cl
        try:
            now_cl = _dt_cl.now(_ZI_cl(tz_cl))
        except Exception:
            now_cl = _dt_cl.now()
        time_ctx = f"Сейчас у садовника: {now_cl.strftime('%Y-%m-%d %H:%M')} ({tz_cl})"
        messages_cl = [
            {"role": "system", "content": _CLASSIFIER_PROMPT + f"\n\n{time_ctx}"},
            {"role": "user", "content": text}
        ]
        raw_cl = await _call_openrouter(messages_cl, model_idx=0)
        if not raw_cl:
            return None
        raw_cl = re.sub(r"<think>.*?</think>", "", raw_cl, flags=re.DOTALL).strip()
        raw_cl = re.sub(r"^```(?:json)?\s*", "", raw_cl)
        raw_cl = re.sub(r"\s*```\s*$", "", raw_cl).strip()
        brace = raw_cl.find("{")
        if brace > 0:
            raw_cl = raw_cl[brace:]
        result = json.loads(raw_cl) if raw_cl.startswith("{") else None
        return result
    except Exception as e:
        logger.debug(f"Classifier error: {e}")
        return None


@router.message(F.text & ~F.text.startswith("/"))
async def free_conversation(message: Message, state: FSMContext):
    """Catches any plain text not handled above. MUST be last message handler."""
    user_id = str(message.from_user.id)
    _track_interaction(user_id)

    if not await ensure_user_loaded(user_id):
        await message.answer("🌿 Используй /start чтобы начать.")
        return

    # Version notification moved to morning brief — no catch-up needed

    # ── Birthday check: full SR greeting if first interaction after midnight ──
    try:
        _prof_bday = store_get_profile(user_id)
        if _prof_bday:
            _bday = _prof_bday.get("companion_settings", {}).get("birthday", "")
            if _bday:
                from zoneinfo import ZoneInfo as _ZI_bday
                from datetime import datetime as _dt_bday
                _tz_bday = _ZI_bday(_prof_bday.get("companion_settings", {}).get("timezone", "Europe/Moscow"))
                _now_bday = _dt_bday.now(_tz_bday)
                _today_bday = _now_bday.strftime("%d.%m")
                if _today_bday == _bday and _birthday_sent.get(user_id) != _today_bday:
                    _bname = _prof_bday.get("name", "Садовник")
                    # Build personalised greeting via SR
                    _sr_ctx = _build_user_context_msg(user_id)
                    _dp_bday = _get_deep_profile(user_id)
                    _core_bday = _dp_bday.get("memory", {}).get("core", "")
                    _ach_bday = store_get_achievements_count(user_id)
                    _bday_prompt = (
                        f"Сегодня день рождения садовника {_bname}.\n"
                        f"Портрет: {_core_bday[:300] if _core_bday else 'пока формируется'}\n"
                        f"Достижений: {_ach_bday}\n"
                        f"Контекст:\n{_sr_ctx[:800]}\n\n"
                        f"Напиши тёплое персонализированное поздравление с днём рождения (3-4 предложения). "
                        f"Отрази рост садовника за прошедший год. "
                        f"Используй эмодзи. Будь как мудрый друг который видит путь человека. "
                        f"Ответь ТОЛЬКО текстом поздравления, без JSON."
                    )
                    _bday_msg = await _call_openrouter([
                        {"role": "system", "content": "Ты — СР, дух сада. Пиши тепло, кратко, с эмодзи. На русском."},
                        {"role": "user", "content": _bday_prompt}
                    ])
                    if not _bday_msg or len(_bday_msg.strip()) < 10:
                        _bday_msg = (
                            f"🎂 С днём рождения, {_bname}!\n\n"
                            f"Пусть этот год будет годом роста во всех сферах.\n"
                            f"Сад помнит этот день. 🌿"
                        )
                    await message.answer(_bday_msg.strip(), reply_markup=get_main_keyboard())
                    _birthday_sent[user_id] = _today_bday
                    store_increment_achievements(user_id)
                    store_add_sphere_resonance(user_id, "growth", 5)
                    _fire_sync()
    except Exception:
        pass

    # ── Welcome Flow: записываем ответ в deep_profile и задаём следующий вопрос ──
    fsm_data = await state.get_data()
    _welcome_step = fsm_data.get("_welcome_step", 0)
    if _welcome_step == 1:
        # Первый ответ — чем занимается садовник
        _dp = _get_deep_profile(user_id)
        _dp.setdefault("observations", []).append(
            f"{_today()} [onboarding]: деятельность — {message.text.strip()[:120]}"
        )
        _save_deep_profile(user_id, _dp)
        await state.update_data(_welcome_step=2)
        await message.answer(
            "Понял. Последний вопрос — есть что-то большое к чему ты сейчас идёшь?\n\n"
            "Цель, мечта, проект — что угодно. Или скажи «пока нет» — это тоже ответ.",
            reply_markup=get_main_keyboard()
        )
        return
    elif _welcome_step == 2:
        # Второй ответ — большая цель
        _dp = _get_deep_profile(user_id)
        _dp.setdefault("observations", []).append(
            f"{_today()} [onboarding]: большая цель — {message.text.strip()[:120]}"
        )
        _save_deep_profile(user_id, _dp)
        _fire_sync()
        await state.update_data(_welcome_step=0)
        # Предлагаем тур по функционалу
        _tour_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🗺 Да, покажи",
                callback_data="tour_yes"
            ),
            InlineKeyboardButton(
                text="Разберусь сам 🌿",
                callback_data="tour_no"
            ),
        ]])
        await message.answer(
            "Показать что умею?",
            reply_markup=_tour_kb
        )
        return

    # Support voice messages: text may come via state instead of message.text
    _state_data = await state.get_data()
    _voice_override = _state_data.get("_voice_text")
    if _voice_override:
        await state.update_data(_voice_text=None)
        text = _voice_override.strip()
    else:
        text = (message.text or "").strip()
        text = _fix_layout(text)
    if not text:
        return

    # P-41: детект приветствия от садовника
    _fc_kw = text.lower().strip()
    _greeting_kws = ["привет", "доброе утро", "добрый день", "добрый вечер", "здравствуй", "хай", " ку ", "hello", "hi", "здарова", "салют", "приветствую"]
    _is_greeting = any(k in _fc_kw for k in _greeting_kws) or _fc_kw in ["ку", "hi", "хай"]
    _fc_ws = store_get_workspace(user_id) or {}
    _greeting_already = _fc_ws.get("_greeting_sent_date", "") == _today()

    ctx_msg = _build_user_context_msg(user_id)
    # P-43: если садовник пишет чисто "привет" (без содержания) и уже виделись — подсказка SR
    _pure_greeting_kws = ["привет", "доброе утро", "добрый день", "добрый вечер",
                          "здравствуй", "хай", "ку", "hello", "hi", "здарова", "салют", "приветствую"]
    _is_pure_greeting = _fc_kw.strip("!.)( ") in _pure_greeting_kws
    if _is_greeting and _greeting_already and _is_pure_greeting:
        ctx_msg += ("\n[Садовник написал только приветствие — без вопроса и без задачи. "
                    "Мы уже виделись сегодня. Выбери сам: пошути тепло, спроси как идёт день, "
                    "или напомни что-то из его контекста. Не здоровайся снова.]")
    history = _get_history(user_id)

    # ── Keyword pre-detection: pin/unpin (v7.39.14) ─────────────────────
    _kw_lower = text.lower().strip()
    _pin_kw = ["закрепи это", "закрепи последнее", "закрепи сообщение", "запомни это"]
    _unpin_kw = ["открепи", "убери закреп", "сними закреп"]
    if any(k in _kw_lower for k in _pin_kw):
        _pin_data = _last_bot_message.get(user_id)
        if _pin_data:
            _ws_pin_kw = store_get_workspace(user_id) or {}
            _old_pin_kw = _ws_pin_kw.get("pinned_message")
            if _old_pin_kw and _old_pin_kw.get("message_id"):
                try:
                    await bot.unpin_chat_message(message.chat.id, _old_pin_kw["message_id"])
                except Exception:
                    pass
            try:
                await bot.pin_chat_message(message.chat.id, _pin_data["message_id"])
                _ws_pin_kw["pinned_message"] = {
                    "message_id": _pin_data["message_id"],
                    "text": _pin_data["text"][:500],
                    "date": _today()
                }
                store_set_workspace(user_id, _ws_pin_kw)
                _fire_sync()
                reply_text = "📌 Закреплено \u2728"
            except Exception as _pe_kw:
                reply_text = f"🌱 Не удалось закрепить: {_pe_kw}"
        else:
            reply_text = "🌱 Нет сообщения для закрепления"
        _has_html_pin = any(tag in reply_text for tag in ["<b>", "<a href", "<i>"])
        if _has_html_pin:
            _mode_kw = "HTML"
        else:
            _mode_kw = None
        await message.answer(reply_text, parse_mode=_mode_kw)
        # Записать в сессию — SR увидит закреп в истории
        _add_to_history(user_id, "user", text)
        _add_to_history(user_id, "assistant", reply_text)
        return
    if any(k in _kw_lower for k in _unpin_kw):
        _ws_unpin_kw = store_get_workspace(user_id) or {}
        _pin_rm_kw = _ws_unpin_kw.get("pinned_message")
        if _pin_rm_kw and _pin_rm_kw.get("message_id"):
            try:
                await bot.unpin_chat_message(message.chat.id, _pin_rm_kw["message_id"])
            except Exception:
                pass
            _ws_unpin_kw["pinned_message"] = None
            store_set_workspace(user_id, _ws_unpin_kw)
            _fire_sync()
            reply_text = "📌 Закреп снят"
        else:
            reply_text = "🌱 Нет закреплённых"
        _has_html_unpin = any(tag in reply_text for tag in ["<b>", "<a href", "<i>"])
        if _has_html_unpin:
            _mode_unpin = "HTML"
        else:
            _mode_unpin = None
        await message.answer(reply_text, parse_mode=_mode_unpin)
        # Записать в сессию — SR увидит откреп в истории
        _add_to_history(user_id, "user", text)
        _add_to_history(user_id, "assistant", reply_text)
        return

    # Typing keep-alive: обновляется каждые 4 сек пока LLM думает
    _typing_stop = asyncio.Event()
    async def _keep_typing():
        while not _typing_stop.is_set():
            try:
                await message.bot.send_chat_action(message.chat.id, "typing")
            except Exception:
                pass
            await asyncio.sleep(4)
    _typing_task = asyncio.create_task(_keep_typing())

    # Deep profile reflection hint — once per session
    _hint = _get_session_reflection_hint(user_id)
    _hint_block = f"\n\n[SR reflection hint: {_hint}]" if _hint else ""

    # P-64: classifier handles all intents — SR is pure conversationalist
    # SR_INTENT_LIGHT and SR_INTENT_MAP removed — SR returns plain text, not JSON
    system_content = SR_CORE_PROMPT
    # P-66: inject current date/time so SR doesn't confuse past events with today
    try:
        from zoneinfo import ZoneInfo as _ZI_sr
        from datetime import datetime as _dt_sr
        _prof_sr = store_get_profile(user_id) or {}
        _tz_sr = _prof_sr.get("companion_settings", {}).get("timezone", "Europe/Moscow")
        _now_sr = _dt_sr.now(_ZI_sr(_tz_sr))
        _weekdays_ru = ["понедельник","вторник","среда","четверг","пятница","суббота","воскресенье"]
        _dt_block = (
            f"[Сейчас: {_weekdays_ru[_now_sr.weekday()]}, "
            f"{_now_sr.strftime('%d.%m.%Y %H:%M')} ({_tz_sr}). "
            f"Это актуальная дата и время садовника. "
            f"Не путай прошлые события с сегодняшними. "
            f"Всё что было раньше этой даты — прошлое.]"
        )
    except Exception:
        _dt_block = ""
    messages = [
        {
            "role": "system",
            "content": system_content + "\n\n" + _dt_block + "\n\n" + ctx_msg + _hint_block
        },
        *history[-20:],  # P-44: последние 20 в промпт
        {"role": "user", "content": text}
    ]

    reply_text = "🌿 Я здесь, рядом."
    action = None
    parsed = None  # will hold decoded JSON dict
    _suggest_action_kb = None  # P-70: suggest action keyboard

    # P-57: Step 2 — classifier active (short-circuits SR for action intents)
    _cl_short_circuit = None  # if set -> use classifier result, skip SR call
    try:
        _cl_enriched = _build_enriched_text(history, text)
        _cl_result = await _classify_intent(user_id, _cl_enriched)
        if _cl_result:
            _cl_intent = _cl_result.get("intent", "none")
            _cl_conf   = float(_cl_result.get("confidence", 1.0))
            logger.info(f"[Classifier] uid={user_id} intent={_cl_intent} conf={_cl_conf:.2f} text='{text[:40]}'")
            _SR_ONLY = {"none", "conversation", "show_resonance", "show_resonance_detail", "show_achievements"}
            # P-70: suggest_action — pass hint to SR, show action button
            if _cl_intent == "suggest_action" and _cl_conf >= 0.60:
                _sg_action = _cl_result.get("action") or {}
                _sg_type = _sg_action.get("type", "")
                _sg_title = _sg_action.get("title", "")
                _sg_labels = {"add_task": "добавить задачу", "add_achievement": "зафиксировать достижение", "create_reminder": "создать напоминание"}
                _sg_hint = f"[Подсказка: садовник намекает на намерение — {_sg_labels.get(_sg_type, _sg_type)} «{_sg_title}». Если это уместно — мягко предложи добавить. Не навязывай.]"
                messages[0]["content"] += f"\n\n{_sg_hint}"
                _suggest_action_kb = _sg_action
            else:
                _suggest_action_kb = None
            # Action intents benefit from enriched context — lower threshold
            _CONTEXT_INTENTS = {
                "edit_task", "complete_task", "delete_task", "add_task",
                "create_reminder", "delete_reminder",
                "create_checklist", "delete_checklist",
                "checklist_add_item", "checklist_toggle_item",
                "checklist_delete_item", "checklist_edit_item",
                "add_achievement",
                "move_task",
            }
            _cl_threshold = 0.75 if _cl_intent in _CONTEXT_INTENTS else 0.85
            if _cl_intent not in _SR_ONLY and _cl_intent != "suggest_action" and _cl_conf >= _cl_threshold:
                _cl_short_circuit = json.dumps({
                    "intent": _cl_intent,
                    "action": _cl_result.get("action") or {},
                    "confidence": _cl_conf,
                    "text": ""
                }, ensure_ascii=False)
                logger.info(f"[Classifier] SHORT-CIRCUIT intent={_cl_intent} - SR skipped")
                # P-65: record classifier action in history so SR sees it next message
                _action_labels = {
                    "add_task": "задача создана",
                    "complete_task": "задача закрыта",
                    "delete_task": "задача удалена",
                    "edit_task": "задача изменена",
                    "create_reminder": "напоминание создано",
                    "delete_reminder": "напоминание удалено",
                    "add_achievement": "достижение зафиксировано",
                    "create_checklist": "чеклист создан",
                    "show_tasks": "показаны задачи",
                    "show_profile": "показан профиль",
                    "show_resonance": "показан резонанс",
                    "show_achievements": "показаны достижения",
                }
                _cl_action_data = _cl_result.get("action") or {}
                _cl_action_title = _cl_action_data.get("title") or ""
                _cl_label = _action_labels.get(_cl_intent, _cl_intent)
                _cl_hist_note = f"[Система: {_cl_label}" + (f" — {_cl_action_title}" if _cl_action_title else "") + "]"
                _add_to_history(user_id, "system", _cl_hist_note)
            else:
                # classifier_pass_to_sr — normal SR flow, not an issue
                logger.debug(f"Classifier pass to SR: intent={_cl_intent} conf={_cl_conf:.2f} [{text[:40]}]")
    except Exception as _cl_e:
        logger.debug(f"Classifier call failed: {_cl_e}")

    try:
        if _cl_short_circuit:
            raw = _cl_short_circuit
        else:
            raw = await _call_openrouter(messages)
        _typing_stop.set()
        if raw:
            # 1. Strip <think>...</think>
            raw_clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            # 2. Strip markdown fences
            raw_clean = re.sub(r"^```(?:json)?\s*", "", raw_clean)
            raw_clean = re.sub(r"\s*```\s*$", "", raw_clean).strip()

            # Strip any text prefix before JSON (LLM sometimes adds "📋 Показываю..." before {)
            _brace_idx = raw_clean.find("{")
            if _brace_idx > 0:
                raw_clean = raw_clean[_brace_idx:]

            if raw_clean.startswith("{"):
                # 3a. Try direct parse
                try:
                    parsed, _ = json.JSONDecoder().raw_decode(raw_clean)
                except (json.JSONDecodeError, ValueError):
                    # 3b. LLM used unescaped ASCII quotes inside JSON string values.
                    # Strategy: replace any unescaped " that appear INSIDE string values
                    # by using a two-pass repair:
                    # Pass 1: escape unescaped quotes inside known string fields
                    import re as _re  # ensure available in this scope
                    def _repair_json(s: str) -> str:
                        _re2 = _re
                        # Replace straight ASCII quotes inside text/title values
                        # with typographic equivalents to preserve JSON structure
                        # Pattern: after ": " or ,"  find broken quotes in values
                        def fix_value(m):
                            key = m.group(1)
                            inner = m.group(2)
                            # escape any bare double-quotes inside the value
                            inner_fixed = inner.replace('"', '\\"')
                            return f'"{key}": "{inner_fixed}"'
                        # Fix string values: "key": "...broken..."
                        repaired = _re2.sub(
                            r'"(\w+)":\s*"((?:[^"\\\n]|\\.)*(?:"(?:[^"\\\n]|\\.)*")*(?:[^"\\\n]|\\.)*)"',
                            fix_value, s
                        )
                        return repaired
                    try:
                        repaired = _repair_json(raw_clean)
                        parsed, _ = json.JSONDecoder().raw_decode(repaired)
                    except Exception:
                        parsed = None

                if parsed is not None:
                    extracted = parsed.get("text", "")
                    reply_text = extracted.strip() if extracted else ""
                    # Strip markdown: **bold** → bold, *italic* → italic
                    # Do NOT strip HTML tags which are intentional
                    if reply_text:
                        reply_text = reply_text.replace("**", "").replace("__", "")
                        # Strip list markers: "* " → "• " but only at line start
                        import re as _re_md
                        reply_text = _re_md.sub(r'^\* ', '• ', reply_text, flags=_re_md.MULTILINE)
                        reply_text = _re_md.sub(r'^\- ', '• ', reply_text, flags=_re_md.MULTILINE)
                    action = parsed.get("action")
                    raw_clean = json.dumps(parsed, ensure_ascii=False)
                else:
                    # 3c. Last resort: regex-extract "text" field only
                    m = _re.search(r'"text"\s*:\s*"((?:[^\\"\n]|\\.)*)"', raw_clean)
                    if m:
                        reply_text = m.group(1).replace("\\n", "\n").replace("\\'", "'")
                    else:
                        reply_text = ""  # NEVER show raw JSON
                    # Try to get intent for router even from broken JSON
                    m_intent = _re.search(r'"intent"\s*:\s*"([^"]+)"', raw_clean)
                    m_conf   = _re.search(r'"confidence"\s*:\s*([\d.]+)', raw_clean)
                    m_atype  = _re.search(r'"type"\s*:\s*"([^"]+)"', raw_clean)
                    m_atitle = _re.search(r'"title"\s*:\s*"([^"]+)"', raw_clean)
                    parsed = {
                        "intent": m_intent.group(1) if m_intent else "conversation",
                        "confidence": float(m_conf.group(1)) if m_conf else 1.0,
                        "action": {"type": m_atype.group(1), "title": m_atitle.group(1)}
                                  if m_atype else None
                    }
                    raw_clean = json.dumps(parsed, ensure_ascii=False)
            else:
                # Plain text response
                reply_text = raw_clean
                # Strip markdown symbols
                import re as _re_md2
                reply_text = reply_text.replace("**", "").replace("__", "")
                reply_text = _re_md2.sub(r'^\* ', '• ', reply_text, flags=_re_md2.MULTILINE)
                reply_text = _re_md2.sub(r'^\- ', '• ', reply_text, flags=_re_md2.MULTILINE)
                raw_clean = "{}"

            # ── Fuzzy title matcher ────────────────────────────────────────
            def _normalize(s: str) -> str:
                import re as _ren
                s = s.lower().strip()
                s = _ren.sub(r"[^\w\s]", "", s)
                s = _ren.sub(r"\s+", "", s)
                return s

            def _fuzzy_match_tasks(target: str, tasks: list, threshold: float = 0.65) -> list:
                """Fuzzy task title match: exact substr → normalized substr → LCS ratio."""
                if not target:
                    return []
                t_norm = _normalize(target)
                # 1. Normalized substring
                exact = [t for t in tasks if t_norm in _normalize(t.get("title", ""))]
                if exact:
                    return exact[:1]
                # 2. LCS ratio
                def _lcs_ratio(a: str, b: str) -> float:
                    la, lb = len(a), len(b)
                    if la == 0 or lb == 0:
                        return 0.0
                    dp = [[0] * (lb + 1) for _ in range(la + 1)]
                    for i in range(1, la + 1):
                        for j in range(1, lb + 1):
                            if a[i-1] == b[j-1]:
                                dp[i][j] = dp[i-1][j-1] + 1
                            else:
                                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
                    return (2 * dp[la][lb]) / (la + lb)
                scored = sorted(
                    [(_lcs_ratio(t_norm, _normalize(t.get("title", ""))), t) for t in tasks],
                    key=lambda x: -x[0]
                )
                return [scored[0][1]] if scored and scored[0][0] >= threshold else []

            # ── Intent router ──────────────────────────────────────────────
            try:
                parsed_check = parsed if parsed is not None else (
                    json.loads(raw_clean) if raw_clean.startswith("{") else {}
                )
                intent = parsed_check.get("intent", "conversation")
                confidence = float(parsed_check.get("confidence", 1.0))
                clarification = parsed_check.get("clarification")
                # Update daily stats with actual intent
                _track_interaction(user_id, intent=intent)

                # Safety net: if LLM returned conversation but text looks like
                # a fake action result — treat as unrecognised command
                _ACTION_FAKE_MARKERS = (
                    "✅ готово", "✅ изменено", "✅ изменён", "✅ дедлайн",
                    "задача закрыта", "задача добавлена", "задача удалена",
                    "добавила задачу", "создала задачу", "задача создана",
                    "напоминание создано", "напоминание удалено",
                    "добавлено напоминание", "добавила напоминание",
                    "напоминание добавлено", "поставила напоминание",
                    "напоминание поставлено", "создала напоминание",
                    "исправляюсь", "добавляю напоминание", "ставлю напоминание",
                    "дедлайн изменён", "дедлайн изменен", "название изменено",
                    "перенесён", "перенесен", "изменена дата",
                    "изменено дедлайн", "дедлайн задачи", "изменила дедлайн",
                    "перенесла", "изменила", "команда:", "**команда",
                    "сделала это", "выполнила", "изменила срок",
                    "создаю чеклист", "создаю задачу", "создаю роадмап",
                    "закрываю задачу", "закрываю все", "отмечаю задачу", "отмечаю как",
                    "удаляю задачу", "переношу задачу",
                )
                if intent == "conversation" and any(
                    m in reply_text.lower() for m in _ACTION_FAKE_MARKERS
                ):
                    _fb_history = _get_history(user_id)
                    _fb_reply = await _call_openrouter([
                        {"role": "system", "content": SR_CORE_PROMPT + "\n\n" + ctx_msg
                            + "\n\n[Отвечай только текстом, без JSON. Свободный диалог.]"},
                        *_fb_history[-10:],
                        {"role": "user", "content": text}
                    ])
                    reply_text = _fb_reply.strip() if _fb_reply and _fb_reply.strip() else "🌿 Я здесь, слушаю тебя."
                # Bare "готово" with no action markers is also suspicious when intent=conversation
                if intent == "conversation" and reply_text.lower().strip() in ("готово", "готово.", "done", "ok", "ок"):
                    _fb_history = _get_history(user_id)
                    _fb_reply = await _call_openrouter([
                        {"role": "system", "content": SR_CORE_PROMPT + "\n\n" + ctx_msg
                            + "\n\n[Отвечай только текстом, без JSON. Свободный диалог.]"},
                        *_fb_history[-10:],
                        {"role": "user", "content": text}
                    ])
                    reply_text = _fb_reply.strip() if _fb_reply and _fb_reply.strip() else "🌿 Я здесь, слушаю тебя."

                if confidence < 0.7 and clarification:
                    # Not sure — ask clarification
                    reply_text = clarification
                elif confidence >= 0.7 and intent != "conversation":
                    # Execute command directly
                    # Only block intents during active multi-step input FSM flows.
                    # Transient/stale states (EngineerChat, Ask, Achievement) are cleared.
                    current_state = await state.get_state()
                    _BLOCKING_PREFIXES = (
                        "GardenOnboardingStates:", "EditProfileStates:",
                        "TaskStates:", "TaskEditStates:", "ChecklistStates:",
                        "ReminderStates:", "LeaveStates:",
                    )
                    _is_blocked = current_state and any(
                        current_state.startswith(p) for p in _BLOCKING_PREFIXES
                    )
                    if current_state and not _is_blocked:
                        # Stale/transient state — clear it so command can run
                        await state.clear()
                        current_state = None
                    if not _is_blocked:  # only if no blocking FSM active
                        if intent == "show_tasks":
                            # Detect period from text + SR action
                            period = _detect_task_period(text)
                            action_period = (parsed_check.get("action") or {}).get("period", "")
                            action_label  = ((parsed_check.get("action") or {}).get("label") or "").strip()
                            if action_period and action_period != "all":
                                period = action_period
                            if action_label:
                                # Filter by group label
                                uid_tasks = store_get_tasks(user_id)
                                filtered = [t for t in uid_tasks
                                            if t.get("status") != "completed"
                                            and action_label.lower() in (t.get("label_name") or "").lower()]
                                if not filtered:
                                    # Try fuzzy group match
                                    groups_data = store_get_groups(user_id).get("groups", [])
                                    matched_g = next((g["name"] for g in groups_data
                                                      if action_label.lower() in g.get("name","").lower()), None)
                                    if matched_g:
                                        filtered = [t for t in uid_tasks
                                                    if t.get("status") != "completed"
                                                    and (t.get("label_name") or "") == matched_g]
                                if filtered:
                                    label_display = filtered[0].get("label_name") or action_label
                                    lines = [f"<b>🗂 {label_display}:</b>"]
                                    for t in _sort_by_deadline(filtered):
                                        dl  = f" · {t['deadline']}" if t.get("deadline") else ""
                                        ind = _deadline_indicator(t.get("deadline", ""))
                                        lines.append(f"  • {ind}{t['title']}{dl}")
                                    reply_text = "\n".join(lines)
                                else:
                                    reply_text = f"🌀 Задач в группе «{action_label}» не нашла."
                            elif period == "all" or not period:
                                # Show ALL tasks as flat list
                                await _show_tasks_unified(user_id, message, "all")
                            else:
                                # Filtered view — text list, not menu
                                uid_tasks = store_get_tasks(user_id)
                                filtered  = _filter_tasks_by_period(uid_tasks, period)
                                period_ru = {
                                    "today":    "📅 Сегодня",
                                    "tomorrow": "📅 Завтра",
                                    "day_after":"📅 Послезавтра",
                                    "week":     "📅 На неделе",
                                    "month":    "📅 В этом месяце",
                                    "overdue":  "⚠️ Просроченные",
                                }.get(period, "🌀 Задачи")
                                if period.startswith("date:"):
                                    period_ru = f"📅 {period[5:]}"
                                if not filtered:
                                    reply_text = f"{period_ru}: задач нет 🌱"
                                else:
                                    lines = [f"<b>{period_ru}:</b>"]
                                    for t in _sort_by_deadline(filtered):
                                        dl  = f" · {t['deadline']}" if t.get("deadline") else ""
                                        grp = f" #{t['label_name']}" if t.get("label_name") else ""
                                        ind = _deadline_indicator(t.get("deadline",""))
                                        lines.append(f"  • {ind}{t['title']}{grp}{dl}")
                                    reply_text = "\n".join(lines)
                            reply_text = reply_text if (period != "all" or action_label) else ""
                        elif intent == "show_profile":
                            await _show_profile(user_id, message)
                            reply_text = ""
                        elif intent == "show_resonance":
                            # P-29: redirect → SR анализирует с историей
                            _sphere_history_needed[user_id] = 4
                            reply_text = None

                        elif intent == "show_resonance_detail":
                            # P-29: подгрузить историю сфер — SR анализирует сам
                            _sphere_history_needed[user_id] = 4
                            # reply_text остаётся None — SR сгенерирует анализ из контекста
                            reply_text = None
                        elif intent == "show_achievements":
                            # P-29: подгрузить историю — SR даёт анализ достижений
                            _sphere_history_needed[user_id] = 4
                            reply_text = None
                        elif intent == "add_task":
                            action_data = parsed_check.get("action") or {}
                            bulk_tasks  = action_data.get("tasks") or []
                            if bulk_tasks and isinstance(bulk_tasks, list):
                                # ── Bulk add: несколько задач за раз ──────────────
                                created_lines = []
                                for _bt in bulk_tasks:
                                    _bt_title = (_bt.get("title") or "").strip()
                                    _bt_dl    = (_bt.get("deadline") or "").strip() or None
                                    _bt_label = (_bt.get("label") or "").strip() or None
                                    if not _bt_title:
                                        continue
                                    _nt = await _create_task_atomic(
                                        user_id, message,
                                        title=_bt_title,
                                        deadline=_bt_dl,
                                        reminder=None,
                                        label_name=_bt_label
                                    )
                                    if _nt:
                                        _ind = _deadline_indicator(_nt["deadline"]) if _nt.get("deadline") else ""
                                        _dl_part = f" · {_ind}{_nt['deadline']}" if _nt.get("deadline") else ""
                                        created_lines.append(f"  • {_nt['title']}{_dl_part}")
                                if created_lines:
                                    bulk_confirm = f"✅ Добавлено {len(created_lines)} задач:\n" + "\n".join(created_lines)
                                    # profile not shown automatically
                                    await message.answer(bulk_confirm, parse_mode="HTML", reply_markup=get_main_keyboard())
                                    _daily_stats.setdefault(user_id, {"messages":0,"tasks_created":0,"tasks_completed":0,"achievements":0,"intents":{}})
                                    _daily_stats[user_id]["tasks_created"] += len(created_lines)
                                reply_text = ""
                            else:
                                # ── Single task ───────────────────────────────────
                                title    = (action_data.get("title") or "").strip()
                                deadline = action_data.get("deadline", "") or ""
                                reminder = action_data.get("reminder", "") or ""
                                label    = action_data.get("label", "") or ""
                                repeat   = action_data.get("repeat", "") or ""
                                if not title:
                                    # No title extracted — fall back to FSM
                                    await cb_start_addtask_msg(message, state, pre_title="")
                                    reply_text = ""
                                else:
                                    # H-4: dedup — блокировать точные дубли
                                    _existing_t = store_get_tasks(user_id)
                                    _dup = next(
                                        (t for t in _existing_t
                                         if t.get("status") != "completed"
                                         and t.get("title","").lower().strip() == title.lower().strip()),
                                        None
                                    )
                                    if _dup:
                                        _dup_dl = f" · до {_dup['deadline']}" if _dup.get("deadline") else ""
                                        _dup_gr = f" · {_dup['label_name']}" if _dup.get("label_name") else ""
                                        reply_text = f"✅ «{title}» уже есть в саду{_dup_dl}{_dup_gr} — не создала повторно"
                                    else:
                                        new_task = await _create_task_atomic(
                                            user_id, message,
                                            title=title,
                                            deadline=deadline or None,
                                            reminder=reminder or None,
                                            label_name=label or None,
                                            repeat=repeat or None
                                        )
                                    if new_task:
                                        # Build confirmation message
                                        parts = [f"✅ Задача «{new_task['title']}» создана"]
                                        if new_task.get("deadline"):
                                            ind = _deadline_indicator(new_task["deadline"])
                                            parts.append(f"📅 {ind}{new_task['deadline']}")
                                        if new_task.get("label_name"):
                                            parts.append(f"🎨 {new_task['label_name']}")
                                        if new_task.get("reminder"):
                                            _rem_raw = new_task["reminder"]
                                            try:
                                                _rem_dt = _rem_raw[:16].replace("T", " ")
                                                _rem_parts = _rem_dt.split(" ")
                                                _rem_date = _rem_parts[0] if len(_rem_parts) > 0 else ""
                                                _rem_time = _rem_parts[1] if len(_rem_parts) > 1 else ""
                                                _RU_MON = {"01":"янв","02":"фев","03":"мар","04":"апр","05":"май","06":"июн","07":"июл","08":"авг","09":"сен","10":"окт","11":"ноя","12":"дек"}
                                                _rd = _rem_date.split("-")
                                                _rem_pretty = f"{int(_rd[2])} {_RU_MON.get(_rd[1], _rd[1])} в {_rem_time}" if len(_rd) == 3 else _rem_dt
                                            except Exception:
                                                _rem_pretty = _rem_raw[:16].replace("T", " ")
                                            parts.append(f"🔔 {_rem_pretty}")
                                        missing = []
                                        if new_task.get("repeat") and new_task.get("repeat") != "once":
                                            parts.append("🔁 " + _repeat_label(new_task["repeat"]))
                                        if not new_task.get("deadline"):
                                            missing.append("📅 дедлайн")
                                        if not new_task.get("label_name"):
                                            missing.append("🎨 группа")
                                        confirm_text = " · ".join(parts)
                                        if missing:
                                            confirm_text += f"\n<i>Можно добавить: {', '.join(missing)}</i>"
                                        # profile not shown automatically
                                        tid = new_task["task_id"]
                                        if not new_task.get("reminder"):
                                            missing.append("🔔 напоминание")
                                        if not new_task.get("repeat"):
                                            missing.append("🔁 повтор")
                                        edit_kb = InlineKeyboardMarkup(inline_keyboard=[[
                                            InlineKeyboardButton(text="✏️ Дополнить", callback_data=f"ttask_edit|{tid}")
                                        ]])
                                        await message.answer(confirm_text, reply_markup=edit_kb, parse_mode="HTML")
                                    reply_text = ""
                        elif intent == "add_achievement":
                            _ach_act   = parsed_check.get("action") or {}
                            _ach_title = (_ach_act.get("title") or parsed_check.get("text") or "").strip()
                            _ach_sphere = (_ach_act.get("sphere") or "").strip()
                            if _ach_title:
                                _sphere_map = {
                                    "health": "health", "creativity": "creativity",
                                    "work": "work", "connections": "connections", "growth": "growth"
                                }
                                _ach_cat = _sphere_map.get(_ach_sphere) or _classify_sphere(_ach_title)
                                _ach_icon = LIFE_AREA_ICONS.get(_ach_cat, "🌱")
                                _sphere_name_map = {
                                    "health": "Здоровье", "creativity": "Творчество",
                                    "work": "Работа", "connections": "Связи",
                                    "growth": "Рост", "other": "Другое"
                                }
                                _ach_bonus = 3
                                # Защита от дублей через achievements_count
                                _today_str = _today()
                                # Всегда добавляем +1 к счётчику и резонансу без архива
                                # P-63: store_add_sphere_resonance recalculates mean correctly
                                _new_sphere_res = store_add_sphere_resonance(user_id, _ach_cat, _ach_bonus)
                                _update_sphere_history(user_id, _ach_cat, achievement=True, resonance_delta=_ach_bonus)
                                store_increment_achievements(user_id)
                                # P-63: update only non-resonance fields
                                _gardener = store_get_profile(user_id)
                                if _gardener:
                                    _g = dict(_gardener)
                                    _g["updated"] = _today()
                                    _g = _add_growth_history_entry(_g, _new_sphere_res, user_id)
                                    store_set_profile(user_id, _g)
                                    _invalidate_auth_cache(user_id)
                                _fire_sync()
                                _sname = _sphere_name_map.get(_ach_cat, _ach_cat)
                                reply_text = (
                                    f"{_ach_icon} Достижение зафиксировано!\n\n"
                                    f"{_ach_title}\n"
                                    f"Сфера: {_sname} · +{_ach_bonus} к резонансу"
                                )
                            else:
                                # Название не распознано — открываем FSM
                                await cmd_achievements(message)
                                reply_text = ""
                        elif intent == "pin_message":
                            _pin_data = _last_bot_message.get(user_id)
                            if _pin_data:
                                _ws_pin = store_get_workspace(user_id) or {}
                                _old_pin = _ws_pin.get("pinned_message")
                                if _old_pin and _old_pin.get("message_id"):
                                    try:
                                        await bot.unpin_chat_message(message.chat.id, _old_pin["message_id"])
                                    except Exception:
                                        pass
                                try:
                                    await bot.pin_chat_message(message.chat.id, _pin_data["message_id"])
                                    _ws_pin["pinned_message"] = {
                                        "message_id": _pin_data["message_id"],
                                        "text": _pin_data["text"][:500],
                                        "date": _today()
                                    }
                                    store_set_workspace(user_id, _ws_pin)
                                    _fire_sync()
                                    reply_text = "\U0001f4cc \u0417\u0430\u043a\u0440\u0435\u043f\u043b\u0435\u043d\u043e"
                                except Exception as _pe:
                                    reply_text = f"\U0001f331 \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u043a\u0440\u0435\u043f\u0438\u0442\u044c: {_pe}"
                            else:
                                reply_text = "\U0001f331 \u041d\u0435\u0442 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u0434\u043b\u044f \u0437\u0430\u043a\u0440\u0435\u043f\u043b\u0435\u043d\u0438\u044f"
                        elif intent == "unpin_message":
                            _ws_unpin = store_get_workspace(user_id) or {}
                            _pin_rm = _ws_unpin.get("pinned_message")
                            if _pin_rm and _pin_rm.get("message_id"):
                                try:
                                    await bot.unpin_chat_message(message.chat.id, _pin_rm["message_id"])
                                except Exception:
                                    pass
                                _ws_unpin["pinned_message"] = None
                                store_set_workspace(user_id, _ws_unpin)
                                _fire_sync()
                                reply_text = "\U0001f4cc \u0417\u0430\u043a\u0440\u0435\u043f \u0441\u043d\u044f\u0442"
                            else:
                                reply_text = "\U0001f331 \u041d\u0435\u0442 \u0437\u0430\u043a\u0440\u0435\u043f\u043b\u0451\u043d\u043d\u044b\u0445"
                        elif intent == "web_search":
                            _ws_act = parsed_check.get("action") or {}
                            cat = (_ws_act.get("search_category") or "default").strip()
                            prof = store_get_profile(user_id)
                            city = (prof or {}).get("companion_settings", {}).get("city", "")
                            # Поддержка multi-query (сравнительные запросы)
                            _qs_raw = _ws_act.get("queries")
                            if _qs_raw and isinstance(_qs_raw, list) and len(_qs_raw) > 1:
                                queries = [str(q_i).strip() for q_i in _qs_raw if str(q_i).strip()]
                                q = " + ".join(queries)  # для отображения
                            else:
                                q = (_ws_act.get("query") or _ws_act.get("title") or "").strip() or text
                                queries = [q]
                            # Показываем запрос
                            sm = await message.answer(f"🔍 Ищу: <i>{q}</i>", parse_mode="HTML")
                            # Параллельный поиск по всем запросам
                            import asyncio as _asyncio_ws
                            _search_results = await _asyncio_ws.gather(
                                *[_tavily_search_raw(q_i, city, category=cat) for q_i in queries]
                            )
                            raw_sources = []
                            for _sr_batch in _search_results:
                                raw_sources.extend(_sr_batch)
                            try: await sm.delete()
                            except Exception: pass
                            if raw_sources:
                                total_content = " ".join(s.get("content", "") for s in raw_sources)
                                if len(total_content.strip()) >= 100:
                                    # Передаём данные поиска в SR — он отвечает с полным контекстом диалога
                                    _search_ctx = "\n\n".join(
                                        f"{s['title']}\n{s['content']}" for s in raw_sources
                                    )
                                    _source_links = "\n".join(
                                        f'• <a href="{s["url"]}">{s["title"]}</a>' for s in raw_sources
                                    )
                                    messages[0]["content"] += (
                                        f"\n\n[Данные из поиска по запросу «{q}»:\n{_search_ctx}\n\n"
                                        f"Используй эти данные чтобы ответить на вопрос садовника. "
                                        f"Отвечай в своём обычном тоне, не здоровайся, продолжай диалог. "
                                        f"В конце ответа добавь источники:\n{_source_links}]"
                                    )
                                    reply_text = await _call_openrouter(messages) or \
                                        "🔍 Не удалось обработать результаты. Попробуй переформулировать запрос."
                                else:
                                    reply_text = f"🔍 Не нашла актуальных данных по запросу «{q}». Попробуй уточнить или задать вопрос иначе."
                            else:
                                reply_text = f"🔍 Ничего не нашла по запросу «{q}». Попробуй переформулировать."

                        elif intent == "complete_task":
                            action_ct   = parsed_check.get("action") or {}
                            target      = (action_ct.get("title") or "").lower().strip()
                            # Batch: action.titles=["X","Y"] or action.period=today
                            batch_raw   = action_ct.get("titles", [])
                            batch_period= (action_ct.get("period") or "").strip()
                            batch_label = (action_ct.get("label") or "").strip().lower()
                            tasks = store_get_tasks(user_id)
                            from datetime import datetime as _dtr2
                            today_s2 = _dtr2.now().strftime("%Y-%m-%d")

                            # Collect targets
                            to_close = []
                            if batch_raw and isinstance(batch_raw, list):
                                for bt in batch_raw:
                                    found = _fuzzy_match_tasks(bt, tasks)
                                    to_close.extend(found)
                            elif batch_label:
                                to_close = [t for t in tasks
                                            if t.get("status") != "completed"
                                            and batch_label in (t.get("label_name","") or "").lower()]
                            elif batch_period:
                                filtered_p = _filter_tasks_by_period(tasks, batch_period)
                                to_close.extend(filtered_p)
                            elif target:
                                to_close.extend(_fuzzy_match_tasks(target, tasks))

                            if to_close:
                                closed_ids = {t.get("task_id") for t in to_close}
                                # Keep non-closed tasks + reschedule repeating ones
                                from datetime import datetime as _dt_r, timedelta as _td_r
                                from zoneinfo import ZoneInfo as _ZI_r
                                _prof_r = store_get_profile(user_id) or {}
                                _tz_r_name = _prof_r.get("companion_settings", {}).get("timezone", "Europe/Moscow")
                                try: _tz_r = _ZI_r(_tz_r_name)
                                except Exception: _tz_r = _ZI_r("Europe/Moscow")
                                _now_r = _dt_r.now(_tz_r)
                                new_tasks = [t for t in tasks if t.get("task_id") not in closed_ids]
                                for _tc in to_close:
                                    _rep = _tc.get("repeat")
                                    if not _rep or _rep == "once":
                                        continue
                                    _new_dl = None
                                    if _rep == "daily":
                                        _new_dl = (_now_r + _td_r(days=1)).strftime("%Y-%m-%d")
                                    elif _rep == "weekly":
                                        _new_dl = (_now_r + _td_r(days=7)).strftime("%Y-%m-%d")
                                    elif _rep == "weekdays":
                                        _d = _now_r + _td_r(days=1)
                                        while _d.weekday() >= 5: _d += _td_r(days=1)
                                        _new_dl = _d.strftime("%Y-%m-%d")
                                    elif _rep == "monthly":
                                        _new_dl = (_now_r + _td_r(days=30)).strftime("%Y-%m-%d")
                                    elif _rep.startswith("custom_days:"):
                                        _days_l = _rep.split(":")[1].split(",")
                                        _day_n = ["mon","tue","wed","thu","fri","sat","sun"]
                                        _d = _now_r + _td_r(days=1)
                                        while _day_n[_d.weekday()] not in _days_l: _d += _td_r(days=1)
                                        _new_dl = _d.strftime("%Y-%m-%d")
                                    if _new_dl:
                                        _new_t = {
                                            "task_id": "task_" + _dt_r.now().strftime("%Y%m%d%H%M%S%f")[:17],
                                            "title": _tc.get("title",""),
                                            "status": "todo",
                                            "label_id": _tc.get("label_id"),
                                            "label_name": _tc.get("label_name",""),
                                            "life_area": _tc.get("life_area","work"),
                                            "priority": calculate_priority(_new_dl),
                                            "deadline": _new_dl,
                                            "reminder": _tc.get("reminder"),
                                            "repeat": _rep,
                                            "created": _today(),
                                            "updated": _today(),
                                            "completed": None,
                                            "notes": ""
                                        }
                                        new_tasks.append(_new_t)
                                store_set_tasks(user_id, new_tasks)
                                total_res = 0
                                for tc in to_close:
                                    store_increment_achievements(user_id)
                                    dl2 = tc.get("deadline")
                                    r2  = 2 if (dl2 and dl2 >= today_s2) else 1
                                    sphere2 = _classify_sphere(tc.get("title",""), tc.get("label_name",""))
                                    store_add_sphere_resonance(user_id, sphere2, r2)
                                    _update_sphere_history(user_id, sphere2, task=True, resonance_delta=r2)
                                    _daily_stats.setdefault(user_id, {"messages":0,"tasks_created":0,"tasks_completed":0,"achievements":0,"intents":{}})
                                    _daily_stats[user_id]["tasks_completed"] += 1
                                    total_res += r2
                                _update_deep_profile(user_id)
                                count_now = store_get_achievements_count(user_id)
                                new_res2  = store_get_profile(user_id).get("resonance_level", 0)
                                await _sync_pending()
                                # Get sphere of last closed task for display
                                _last_sphere = _classify_sphere(to_close[-1].get("title",""), to_close[-1].get("label_name",""))
                                if len(to_close) == 1:
                                    reply_text = (f"✅ Готово: {to_close[0]['title']} · "
                                                  f"💎 {count_now} · {SPHERE_EMOJI[_last_sphere]} {SPHERE_NAME_RU[_last_sphere]} +{total_res}% → {new_res2}%")
                                else:
                                    names = ", ".join(t["title"] for t in to_close)
                                    reply_text = (f"✅ Закрыто {len(to_close)}: {names}\n"
                                                  f"💎 {count_now} · {SPHERE_EMOJI[_last_sphere]} {SPHERE_NAME_RU[_last_sphere]} +{total_res}% → {new_res2}%")
                                pass  # profile not shown automatically
                            elif tasks:
                                # Smart clarification: find top fuzzy candidates
                                _candidates = []
                                if target:
                                    def _lcs_r(a, b):
                                        la, lb = len(a), len(b)
                                        if not la or not lb: return 0.0
                                        dp = [[0]*(lb+1) for _ in range(la+1)]
                                        for i in range(1,la+1):
                                            for j in range(1,lb+1):
                                                if a[i-1]==b[j-1]: dp[i][j]=dp[i-1][j-1]+1
                                                else: dp[i][j]=max(dp[i-1][j],dp[i][j-1])
                                        return (2*dp[la][lb])/(la+lb)
                                    import re as _rec2
                                    def _norm2(s):
                                        s = s.lower().strip()
                                        s = _rec2.sub(r"[^\w\s]","",s)
                                        return _rec2.sub(r"\s+","",s)
                                    _tn = _norm2(target)
                                    scored = sorted(
                                        [(_lcs_r(_tn, _norm2(t.get("title",""))), t) for t in tasks],
                                        key=lambda x: -x[0]
                                    )
                                    _candidates = [(r, t) for r, t in scored if r >= 0.35][:3]
                                if len(_candidates) == 1:
                                    _ct = _candidates[0][1]
                                    reply_text = (f"🔍 Ты имеешь в виду «{_ct['title']}»?\n"
                                                  f"Скажи «да» или назови точнее.")
                                elif len(_candidates) > 1:
                                    _opts = "\n".join(f"  {i+1}. {c[1]['title']}"
                                                      for i, c in enumerate(_candidates))
                                    reply_text = f"🔍 Уточни — какую задачу закрыть?\n{_opts}"
                                else:
                                    # No candidates — ask by group
                                    groups_data = store_get_groups(user_id).get("groups", [])
                                    grp_names = ", ".join(g.get("name","") for g in groups_data) or "задачи без группы"
                                    reply_text = (f"🌀 Не нашла задачу «{target}».\n"
                                                  f"Из какой группы она — {grp_names}?")
                            else:
                                reply_text = "🌀 Активных задач нет."

                        elif intent == "delete_task":
                            _act_dt = parsed_check.get("action") or {}
                            target = (_act_dt.get("title") or "").lower().strip()
                            _batch_titles = _act_dt.get("titles") or []
                            _batch_lbl_d  = (_act_dt.get("label") or "").strip().lower()
                            tasks = store_get_tasks(user_id)
                            if _batch_lbl_d:
                                # Удалить все задачи группы
                                _lbl_deleted = [t for t in tasks
                                                if t.get("status") != "completed"
                                                and _batch_lbl_d in (t.get("label_name","") or "").lower()]
                                if _lbl_deleted:
                                    _lbl_ids = {t.get("task_id") for t in _lbl_deleted}
                                    store_set_tasks(user_id, [t for t in tasks if t.get("task_id") not in _lbl_ids])
                                    await _sync_pending()
                                    reply_text = f"🗑 Удалено {len(_lbl_deleted)} задач из группы «{_batch_lbl_d}»"
                                else:
                                    reply_text = f"🌀 Задачи группы «{_batch_lbl_d}» не найдены."
                            elif _batch_titles and isinstance(_batch_titles, list):
                                # Batch delete: action.titles = ["X", "Y", "Z"]
                                _deleted = []
                                _ids_to_del = set()
                                for _bt in _batch_titles:
                                    _m = _fuzzy_match_tasks(_bt, tasks)
                                    if _m and _m[0].get("task_id") not in _ids_to_del:
                                        _ids_to_del.add(_m[0].get("task_id"))
                                        _deleted.append(_m[0]["title"])
                                if _deleted:
                                    tasks = [t for t in tasks if t.get("task_id") not in _ids_to_del]
                                    store_set_tasks(user_id, tasks)
                                    await _sync_pending()
                                    reply_text = f"🗑 Удалено задач: {', '.join(_deleted)}"
                                else:
                                    reply_text = "🌀 Не нашла указанные задачи."
                            elif target in ("все", "all", "все задачи", ""):
                                if not tasks:
                                    reply_text = "🌀 Активных задач нет."
                                else:
                                    count = len(tasks)
                                    store_set_tasks(user_id, [])
                                    await _sync_pending()
                                    reply_text = f"🗑 Удалено {count} задач. Поле чисто."
                            else:
                                matched = _fuzzy_match_tasks(target, tasks)
                                if matched:
                                    t = matched[0]
                                    new_tasks = [x for x in tasks if x.get("task_id") != t.get("task_id")]
                                    store_set_tasks(user_id, new_tasks)
                                    await _sync_pending()
                                    reply_text = f"🗑 Задача удалена: {t['title']}"
                                elif tasks:
                                    titles = ", ".join(t["title"] for t in tasks[:5])
                                    reply_text = f"🌀 Не нашла такую задачу. Активные: {titles}"
                                else:
                                    reply_text = "🌀 Активных задач нет — нечего удалять."

                        elif intent == "create_label":
                            _cl_act   = parsed_check.get("action") or {}
                            _cl_title = (_cl_act.get("title") or "").strip()
                            if not _cl_title:
                                reply_text = "🎨 Как назовём группу? Напиши название."
                            else:
                                _cl_groups = store_get_groups(user_id).get("groups", [])
                                if len(_cl_groups) >= LABEL_LIMIT_HARD:
                                    reply_text = f"⚠️ Лимит групп: {LABEL_LIMIT_HARD}. Удали или переименуй существующую."
                                elif any(g.get("name","").lower() == _cl_title.lower() for g in _cl_groups):
                                    reply_text = f"🎨 Группа «{_cl_title}» уже существует."
                                else:
                                    _cl_gid = _make_group_id(_cl_title, _cl_groups)
                                    _cl_groups.append({"id": _cl_gid, "name": _cl_title, "created": _today()})
                                    _cl_data = store_get_groups(user_id)
                                    _cl_data["groups"] = _cl_groups
                                    store_set_groups(user_id, _cl_data)
                                    _fire_sync()
                                    _suffix = f" Осталось {LABEL_LIMIT_HARD - len(_cl_groups)} слота." if len(_cl_groups) >= LABEL_LIMIT_SOFT else ""
                                    reply_text = f"✅ Группа «{_cl_title}» создана.{_suffix}\n\nТеперь можешь добавлять задачи: «добавь задачу X в группу {_cl_title}»"

                        elif intent == "delete_label":
                            target = ((parsed_check.get("action") or {}).get("title") or "").lower().strip()
                            grp_data = store_get_groups(user_id)
                            labels = grp_data.get("groups", [])
                            matched = [l for l in labels if target and target in l.get("name","").lower()]
                            if matched:
                                lb = matched[0]
                                grp_data["groups"] = [l for l in labels if l["id"] != lb["id"]]
                                store_set_groups(user_id, grp_data)
                                tasks = store_get_tasks(user_id)
                                for t in tasks:
                                    if t.get("label_id") == lb["id"]:
                                        t["label_id"] = None
                                        t["label_name"] = ""
                                store_set_tasks(user_id, tasks)
                                await _sync_pending()
                                reply_text = f"🗑 Группа «{lb['name']}» удалена."
                            else:
                                lbl_names = ", ".join(l["name"] for l in labels[:5]) or "нет групп"
                                reply_text = f"🌀 Не нашла такую группу. Есть: {lbl_names}"


                        elif intent == "show_checklists":
                            checklists = store_get_checklists(user_id)
                            if not checklists:
                                reply_text = "☑️ Чеклистов пока нет. Создай первый!"
                            else:
                                lines = [f"☑️ <b>Чеклисты ({len(checklists)}/{CHECKLIST_LIMIT}):</b>"]
                                for cl in checklists:
                                    prog = _checklist_progress(cl)
                                    lines.append(f"  • {cl['title']} ({prog})")
                                reply_text = "\n".join(lines)
                                reply_text += "\n\nОткрой через Настройки → Чеклисты"

                        elif intent == "show_checklist":
                            target     = (parsed_check.get("action") or {}).get("title","").lower()
                            checklists = store_get_checklists(user_id)
                            cl = next((c for c in checklists if target and target in c.get("title","").lower()), None)
                            if cl:
                                await _show_checklist(cl, message)
                                reply_text = ""
                            else:
                                names = ", ".join(c["title"] for c in checklists[:3]) or "нет чеклистов"
                                reply_text = f"🌀 Чеклист не найден. Есть: {names}"

                        elif intent == "create_checklist":
                            action_data = parsed_check.get("action") or {}
                            title     = action_data.get("title","").strip()
                            items_raw = action_data.get("items","").strip()
                            if not title:
                                # No title — fall back to FSM
                                await _start_checklist_create(message, state)
                                reply_text = ""
                            else:
                                # Atomic creation — always instant, no FSM
                                new_cl = await _create_checklist_atomic(
                                    user_id, message, title=title, items_raw=items_raw
                                )
                                if new_cl:
                                    n_items = len(new_cl.get("items", []))
                                    confirm = f"✅ Чеклист «{title}» создан"
                                    confirm += f" с {n_items} пунктами!" if n_items else "!"
                                    await message.answer(confirm, reply_markup=get_main_keyboard())
                                    # Show inline checklist
                                    prog = _checklist_progress(new_cl)
                                    cl_msg = await message.answer(
                                        f"☑️ <b>{title}</b>  {prog}",
                                        reply_markup=get_checklist_inline(new_cl)
                                    )
                                    # Save msg_id
                                    checklists = store_get_checklists(user_id)
                                    cl_ref = next((c for c in checklists if c["id"] == new_cl["id"]), None)
                                    if cl_ref:
                                        cl_ref["pinned_message_id"] = cl_msg.message_id
                                        store_set_checklists(user_id, checklists)
                                        await _sync_pending()
                                    # If empty — suggest editing
                                    if not n_items:
                                        edit_kb = InlineKeyboardMarkup(inline_keyboard=[[
                                            InlineKeyboardButton(text="✏️ Добавить пункты",
                                                                 callback_data=f"cl_edit_{new_cl['id']}")
                                        ]])
                                        await message.answer(
                                            "<i>Чеклист пустой — добавь пункты:</i>",
                                            reply_markup=edit_kb
                                        )
                                reply_text = ""

                        elif intent == "delete_checklist":
                            target     = (parsed_check.get("action") or {}).get("title","").lower()
                            checklists = store_get_checklists(user_id)
                            cl = next((c for c in checklists if target and target in c.get("title","").lower()), None)
                            if cl:
                                checklists = [c for c in checklists if c["id"] != cl["id"]]
                                store_set_checklists(user_id, checklists)
                                await _sync_pending()
                                reply_text = f"🗑 Чеклист «{cl['title']}» удалён."
                            else:
                                reply_text = f"🌀 Чеклист «{target}» не найден."

                        elif intent == "checklist_add_item":
                            action_data = parsed_check.get("action") or {}
                            target   = (action_data.get("title") or "").lower()
                            new_item = (action_data.get("item") or "").strip()
                            checklists = store_get_checklists(user_id)
                            cl = next((c for c in checklists if target and target in c.get("title","").lower()), None)
                            if cl and new_item:
                                items = cl.get("items",[])
                                if len(items) >= CHECKLIST_ITEMS_LIMIT:
                                    reply_text = f"⚠️ Лимит пунктов: {CHECKLIST_ITEMS_LIMIT}"
                                else:
                                    items.append({"id": f"i{len(items)+1}", "text": new_item, "done": False})
                                    cl["items"] = items
                                    store_set_checklists(user_id, checklists)
                                    await _sync_pending()
                                    await _show_checklist(cl, message)
                                    reply_text = ""
                            else:
                                reply_text = "🌀 Не нашла чеклист или пустой пункт."

                        elif intent == "checklist_delete_item":
                            action_data = parsed_check.get("action") or {}
                            target   = (action_data.get("title") or "").lower()
                            item_txt = (action_data.get("item") or "").lower().strip()
                            checklists = store_get_checklists(user_id)
                            cl = next((c for c in checklists if target and target in c.get("title","").lower()), None)
                            if cl:
                                items = cl.get("items", [])
                                # Support item by number (e.g. "пункт 3")
                                matched_id = None
                                try:
                                    num = int(item_txt)
                                    if 1 <= num <= len(items):
                                        matched_id = items[num-1]["id"]
                                except (ValueError, TypeError):
                                    pass
                                if not matched_id:
                                    for it in items:
                                        if item_txt in it.get("text","").lower():
                                            matched_id = it["id"]
                                            break
                                before = len(items)
                                cl["items"] = [it for it in items if it["id"] != matched_id] if matched_id else items
                                if len(cl["items"]) < before:
                                    store_set_checklists(user_id, checklists)
                                    await _sync_pending()
                                    await _show_checklist(cl, message)
                                    reply_text = ""
                                else:
                                    reply_text = f"🌀 Пункт «{item_txt}» не найден в «{cl['title']}»"
                            else:
                                reply_text = "🌀 Чеклист не найден."

                        elif intent == "checklist_edit_item":
                            action_data = parsed_check.get("action") or {}
                            target   = (action_data.get("title") or "").lower()
                            item_txt = (action_data.get("item") or "").lower().strip()
                            new_val  = (action_data.get("value") or "").strip()
                            checklists = store_get_checklists(user_id)
                            cl = next((c for c in checklists if target and target in c.get("title","").lower()), None)
                            if cl and new_val:
                                items = cl.get("items", [])
                                # Support item by number
                                found = False
                                try:
                                    num = int(item_txt)
                                    if 1 <= num <= len(items):
                                        items[num-1]["text"] = new_val
                                        found = True
                                except (ValueError, TypeError):
                                    pass
                                if not found:
                                    for it in items:
                                        if item_txt in it.get("text","").lower():
                                            it["text"] = new_val
                                            found = True
                                            break
                                if found:
                                    store_set_checklists(user_id, checklists)
                                    await _sync_pending()
                                    await _show_checklist(cl, message)
                                    reply_text = ""
                                else:
                                    reply_text = f"🌀 Пункт «{item_txt}» не найден."
                            else:
                                reply_text = "🌀 Не нашла чеклист или пункт."

                        elif intent == "checklist_toggle_item":
                            action_data = parsed_check.get("action") or {}
                            target   = (action_data.get("title") or "").lower()
                            item_txt = (action_data.get("item") or "").lower().strip()
                            checklists = store_get_checklists(user_id)
                            cl = next((c for c in checklists if target and target in c.get("title","").lower()), None)
                            if cl:
                                items = cl.get("items", [])
                                # Support item by number
                                toggled = False
                                try:
                                    num = int(item_txt)
                                    if 1 <= num <= len(items):
                                        items[num-1]["done"] = not items[num-1].get("done", False)
                                        toggled = True
                                except (ValueError, TypeError):
                                    pass
                                if not toggled:
                                    for it in items:
                                        if item_txt in it.get("text","").lower():
                                            it["done"] = not it.get("done", False)
                                            toggled = True
                                            break
                                store_set_checklists(user_id, checklists)
                                await _sync_pending()
                                await _show_checklist(cl, message)
                                reply_text = ""
                            else:
                                reply_text = "🌀 Чеклист не найден."

                        elif intent == "checklist_reorder":
                            action_data = parsed_check.get("action") or {}
                            target    = (action_data.get("title") or "").lower()
                            from_pos  = action_data.get("from_pos")
                            to_pos    = action_data.get("to_pos")
                            checklists = store_get_checklists(user_id)
                            cl = next((c for c in checklists if target and target in c.get("title","").lower()), None)
                            if cl and from_pos is not None and to_pos is not None:
                                try:
                                    fi = int(from_pos) - 1
                                    ti = int(to_pos) - 1
                                    items = cl.get("items", [])
                                    if 0 <= fi < len(items) and 0 <= ti < len(items) and fi != ti:
                                        item = items.pop(fi)
                                        # Insert after target position
                                        insert_at = ti if ti < fi else ti
                                        items.insert(insert_at, item)
                                        cl["items"] = items
                                        store_set_checklists(user_id, checklists)
                                        await _sync_pending()
                                        await _show_checklist(cl, message)
                                        reply_text = ""
                                    else:
                                        reply_text = f"🌀 Неверные номера пунктов. В чеклисте {len(items)} пунктов."
                                except (ValueError, TypeError):
                                    reply_text = "🌀 Не понял номера пунктов. Укажи: «поставь пункт 3 после пункта 1»"
                            elif not cl:
                                reply_text = "🌀 Чеклист не найден."
                            else:
                                reply_text = "🌀 Укажи номера пунктов: «поставь пункт 3 после пункта 1»"

                        elif intent == "create_reminder":
                            action_r = parsed_check.get("action") or {}
                            r_title  = action_r.get("title","").strip()
                            r_dt     = action_r.get("datetime","").strip()
                            r_repeat = action_r.get("repeat","once").strip()
                            if r_repeat not in ("once","daily","weekdays"):
                                r_repeat = "once"
                            if not r_title:
                                reply_text = "🔔 Скажи точнее: «напомни мне X завтра в 9:00»"
                            else:
                                # Parse datetime from SR response or use fallback
                                from datetime import datetime as _dt_cr, timedelta as _td_cr
                                from zoneinfo import ZoneInfo as _ZI_cr
                                profile_cr = store_get_profile(user_id) or {}
                                tz_name_cr = profile_cr.get("companion_settings", {}).get("timezone", "Europe/Moscow")
                                try:
                                    tz_cr = _ZI_cr(tz_name_cr)
                                except Exception:
                                    tz_cr = _ZI_cr("Europe/Moscow")
                                now_cr = _dt_cr.now(tz_cr)
                                if r_dt and r_dt not in ("null","none",""):
                                    dt_iso_cr = r_dt
                                else:
                                    target_cr = (now_cr + _td_cr(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
                                    offset_cr = target_cr.strftime("%z")
                                    offset_f_cr = offset_cr[:3] + ":" + offset_cr[3:] if offset_cr else "+00:00"
                                    dt_iso_cr = target_cr.strftime(f"%Y-%m-%dT%H:%M{offset_f_cr}")
                                # P-71b: direct create — no confirmation
                                reminders_cl = store_get_reminders(user_id)
                                if len(reminders_cl) >= REMINDER_LIMIT:
                                    reply_text = f"⚠️ Лимит {REMINDER_LIMIT} напоминаний. Удали старые."
                                else:
                                    if len(reminders_cl) >= REMINDER_LIMIT_SOFT:
                                        await message.answer(f"⚠️ Почти лимит: {len(reminders_cl)}/{REMINDER_LIMIT} напоминаний.")
                                    rid_cl = _make_reminder_id(reminders_cl)
                                    reminders_cl.append({"id": rid_cl, "title": r_title, "datetime_iso": dt_iso_cr, "repeat": r_repeat, "active": True})
                                    store_set_reminders(user_id, reminders_cl)
                                    _fire_sync()
                                    dt_display_cr = dt_iso_cr[:16].replace("T", " ")
                                    kb_cl = InlineKeyboardMarkup(inline_keyboard=[
                                        [InlineKeyboardButton(text="✏️ Изменить", callback_data=f"rem_edit_{rid_cl}")]
                                    ])
                                    await message.answer(
                                        f"✅ Напоминание создано:\n🔔 {r_title}\n📅 {dt_display_cr} · {_repeat_label(r_repeat)}",
                                        reply_markup=kb_cl, parse_mode="HTML"
                                    )
                                    reply_text = ""
                        elif intent == "show_reminders":
                            reminders = store_get_reminders(user_id)
                            if not reminders:
                                reply_text = "🔔 Напоминаний нет. Создай голосом или через Настройки."
                            else:
                                lines = [f"🔔 <b>Напоминания ({len(reminders)}):</b>"]
                                for r in reminders:
                                    dt  = r.get("datetime_iso","")[:16].replace("T"," ")
                                    rep = {"once":"1×","daily":"ежедн.","weekdays":"пн-пт"}.get(r.get("repeat","once"),"1×")
                                    lines.append(f"  🔔 {r['title']} · {dt} ({rep})")
                                reply_text = "\n".join(lines)

                        elif intent == "delete_reminder":
                            target_r  = (parsed_check.get("action") or {}).get("title","").lower()
                            reminders = store_get_reminders(user_id)
                            rem = next((r for r in reminders if target_r and target_r in r.get("title","").lower()), None)
                            if rem:
                                reminders = [r for r in reminders if r["id"] != rem["id"]]
                                store_set_reminders(user_id, reminders)
                                await _sync_pending()
                                reply_text = (f"🗑 Напоминание «{rem['title']}» удалено.\n\n"
                                              + _reminder_list_text(reminders))
                            else:
                                reply_text = f"🌀 Напоминание «{target_r}» не найдено."

                        elif intent == "move_task":
                            _mt_act        = parsed_check.get("action") or {}
                            _mt_title      = (_mt_act.get("title") or "").strip()
                            _mt_titles     = _mt_act.get("titles") or []
                            _mt_label      = (_mt_act.get("label") or "").strip()
                            _mt_from_label = (_mt_act.get("from_label") or "").strip()
                            _mt_tasks      = store_get_tasks(user_id)
                            _mt_groups     = store_get_groups(user_id).get("groups", [])
                            # Найти целевую группу
                            _mt_target_grp = next((g for g in _mt_groups if _mt_label.lower() in g.get("name","").lower()), None)
                            if not _mt_target_grp:
                                reply_text = f"🎨 Группа «{_mt_label}» не найдена. Сначала создай: «создай группу {_mt_label}»"
                            else:
                                _mt_moved = []
                                if _mt_from_label:
                                    # Переместить все из одной группы в другую
                                    _mt_src_grp = next((g for g in _mt_groups if _mt_from_label.lower() in g.get("name","").lower()), None)
                                    for t in _mt_tasks:
                                        if _mt_src_grp and t.get("label_name","").lower() == _mt_src_grp["name"].lower():
                                            t["label_id"]   = _mt_target_grp["id"]
                                            t["label_name"] = _mt_target_grp["name"]
                                            _mt_moved.append(t["title"])
                                else:
                                    # Переместить конкретные задачи
                                    _targets = _mt_titles if _mt_titles else ([_mt_title] if _mt_title else [])
                                    for _tgt in _targets:
                                        _found = _fuzzy_match_tasks(_tgt, _mt_tasks)
                                        for t in _found:
                                            t["label_id"]   = _mt_target_grp["id"]
                                            t["label_name"] = _mt_target_grp["name"]
                                            _mt_moved.append(t["title"])
                                if _mt_moved:
                                    store_set_tasks(user_id, _mt_tasks)
                                    _fire_sync()
                                    reply_text = f"✅ Перемещено в «{_mt_target_grp['name']}»: {', '.join(_mt_moved)}"
                                else:
                                    reply_text = "🌀 Задачи не найдены. Уточни название."

                        elif intent == "rename_label":
                            raw_title = (parsed_check.get("action") or {}).get("title", "")
                            parts = raw_title.split("→") if "→" in raw_title else raw_title.split(" в ")
                            if len(parts) >= 2:
                                old_name = parts[0].strip().lower()
                                new_name = parts[-1].strip()
                                grp_data = store_get_groups(user_id)
                                labels = grp_data.get("groups", [])
                                matched = [l for l in labels if old_name in l.get("name","").lower()]
                                if matched:
                                    matched[0]["name"] = new_name
                                    store_set_groups(user_id, grp_data)
                                    tasks = store_get_tasks(user_id)
                                    for t in tasks:
                                        if t.get("label_id") == matched[0]["id"]:
                                            t["label_name"] = new_name
                                    store_set_tasks(user_id, tasks)
                                    await _sync_pending()
                                    reply_text = f"✅ Группа переименована в «{new_name}»."
                                else:
                                    reply_text = "🌀 Группа не найдена."
                            else:
                                reply_text = "🌀 Скажи: «переименуй группа X в Y»."


                        elif intent == "edit_task":
                            action_data = parsed_check.get("action") or {}
                            target      = (action_data.get("title") or "").lower().strip()
                            _et_titles  = action_data.get("titles") or []
                            _et_label   = (action_data.get("label") or "").strip().lower()
                            field       = (action_data.get("field") or "").lower().strip()
                            value       = (action_data.get("value") or "").strip()
                            tasks       = store_get_tasks(user_id)

                            # ── BULK edit по списку или группе ────────────────
                            if (_et_titles or _et_label) and field in ("deadline","дедлайн","срок","дата") and value:
                                if _et_titles:
                                    _et_m = []
                                    for _etn in _et_titles:
                                        _et_m.extend(_fuzzy_match_tasks(_etn, tasks))
                                else:
                                    _et_m = [t for t in tasks
                                             if _et_label in (t.get("label_name","") or "").lower()
                                             and t.get("status") != "completed"]
                                if _et_m:
                                    import re as _re_b
                                    _v = value.lower().strip()
                                    _dl_b = None
                                    if _v in ("сегодня","today"):
                                        _dl_b = _today()
                                    elif _v in ("завтра","tomorrow"):
                                        from datetime import timedelta as _td_b
                                        _dl_b = (datetime.now() + _td_b(1)).strftime("%Y-%m-%d")
                                    elif _re_b.match(r"^\d{4}-\d{2}-\d{2}$", value):
                                        _dl_b = value
                                    else:
                                        _m_b = _re_b.match(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?", value)
                                        if _m_b:
                                            _dd_b = _m_b.group(1).zfill(2)
                                            _mm_b = _m_b.group(2).zfill(2)
                                            _yy_b = _m_b.group(3) or str(datetime.now().year)
                                            _yy_b = "20"+_yy_b if len(_yy_b)==2 else _yy_b
                                            _dl_b = f"{_yy_b}-{_mm_b}-{_dd_b}"
                                    if _dl_b:
                                        for _tb in _et_m:
                                            _tb["deadline"] = _dl_b
                                            _tb["updated"] = _today()
                                        store_set_tasks(user_id, tasks)
                                        _fire_sync()
                                        _nb = ", ".join(t["title"] for t in _et_m)
                                        reply_text = f"✅ Дедлайн → {_dl_b} для {len(_et_m)} задач: {_nb}"
                                    else:
                                        reply_text = f"🌀 Не понял дату «{value}»"
                                else:
                                    reply_text = "🌀 Задачи не найдены."
                            else:
                                # ── SINGLE edit ───────────────────────────────
                                matched = _fuzzy_match_tasks(target, tasks)
                                # No target? Try last edited task from state
                                if not matched:
                                    _st_data = await state.get_data()
                                    _last_tid = _st_data.get("last_task_id","")
                                    if _last_tid:
                                        matched = [t for t in tasks if t.get("task_id") == _last_tid]
                                if not matched:
                                    titles = ", ".join(t["title"] for t in tasks[:3])
                                    reply_text = f"🌀 Не нашла задачу «{target}». Активные: {titles}"
                                elif not field or not value:
                                    reply_text = "🌀 Уточни: «переименуй задачу X в Y»"
                                else:
                                    t = matched[0]
                                if field in ("title", "название", "имя", "name"):
                                    t["title"]   = value
                                    t["updated"] = _today()
                                    reply_text = f"✅ Название → «{value}»"
                                elif field in ("deadline", "дедлайн", "срок", "дата"):
                                    import re as _re2
                                    from datetime import datetime as _dtt, timedelta as _tdd
                                    _val_lower = value.lower().strip()
                                    _dl = None
                                    _remove_dl = False
                                    # Removal keywords
                                    if _val_lower in ("null", "none", "убрать", "убери", "удалить",
                                                      "удали", "без дедлайна", "без срока", ""):
                                        _remove_dl = True
                                    # Resolve user timezone for relative dates
                                    try:
                                        from zoneinfo import ZoneInfo as _ZIe
                                        _tz_e = _ZIe(store_get_profile(user_id).get(
                                            "companion_settings", {}).get("timezone", "Europe/Moscow"))
                                        _now_e = _dtt.now(_tz_e)
                                    except Exception:
                                        _now_e = _dtt.now()
                                    # Natural language → date
                                    if _val_lower in ("сегодня", "today"):
                                        _dl = _now_e.strftime("%Y-%m-%d")
                                    elif _val_lower in ("завтра", "tomorrow"):
                                        _dl = (_now_e + _tdd(days=1)).strftime("%Y-%m-%d")
                                    elif _val_lower in ("послезавтра",):
                                        _dl = (_now_e + _tdd(days=2)).strftime("%Y-%m-%d")
                                    elif _re2.match(r"через \d+ дн", _val_lower):
                                        _n = int(_re2.search(r"(\d+)", _val_lower).group(1))
                                        _dl = (_now_e + _tdd(days=_n)).strftime("%Y-%m-%d")
                                    elif _re2.match(r"^\d{4}-\d{2}-\d{2}$", value):
                                        _dl = value  # already ISO
                                    elif _re2.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", value):
                                        # DD.MM.YYYY
                                        _parts = value.split(".")
                                        _dl = f"{_parts[2]}-{_parts[1].zfill(2)}-{_parts[0].zfill(2)}"
                                    else:
                                        _m2 = _re2.match(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?", value)
                                        if _m2:
                                            _dd,_mm = _m2.group(1).zfill(2),_m2.group(2).zfill(2)
                                            _yy = _m2.group(3) or str(_now_e.year)
                                            _yy = "20"+_yy if len(_yy)==2 else _yy
                                            _dl = f"{_yy}-{_mm}-{_dd}"
                                    if _remove_dl:
                                        t["deadline"] = None
                                        t["updated"]  = _today()
                                        reply_text = "✅ Дедлайн убран"
                                    elif _dl:
                                        t["deadline"] = _dl
                                        t["updated"]  = _today()
                                        reply_text = f"✅ Дедлайн → {_dl}"
                                    else:
                                        reply_text = f"🌀 Не понял дату «{value}». Напиши: завтра / 25.05 / 25.05.26"
                                elif field in ("reminder", "напоминание", "напомни"):
                                    t["reminder"] = value
                                    t["updated"]  = _today()
                                    reply_text = f"✅ Напоминание → {value}"
                                elif field in ("group", "группа", "label", "лейбл"):
                                    groups = store_get_groups(user_id).get("groups", [])
                                    grp = next((g for g in groups if value.lower() in g.get("name","").lower()), None)
                                    if grp:
                                        t["label_id"]   = grp["id"]
                                        t["label_name"] = grp["name"]
                                        t["updated"]    = _today()
                                        reply_text = f"✅ Группа → {grp['name']}"
                                    else:
                                        g_names = ", ".join(g["name"] for g in groups[:5])
                                        reply_text = f"🌀 Группа «{value}» не найдена. Есть: {g_names}"
                                elif field in ("repeat", "повтор", "повторение"):
                                    # P-60: parse repeat value
                                    _rv = value.lower().strip()
                                    _repeat_map = {
                                        "каждый день": "daily", "ежедневно": "daily", "daily": "daily",
                                        "по будням": "weekdays", "будни": "weekdays", "weekdays": "weekdays",
                                        "по выходным": "weekends", "выходные": "weekends", "weekends": "weekends",
                                        "раз в неделю": "weekly", "еженедельно": "weekly", "weekly": "weekly",
                                        "раз в месяц": "monthly", "ежемесячно": "monthly", "monthly": "monthly",
                                        "убрать": "once", "убери": "once", "без повтора": "once", "один раз": "once",
                                    }
                                    _new_repeat = _repeat_map.get(_rv)
                                    if not _new_repeat:
                                        # Try _parse_weekdays for custom days
                                        _new_repeat = _parse_weekdays(value)
                                    if _new_repeat and _new_repeat != "once":
                                        t["repeat"]  = _new_repeat
                                        t["updated"] = _today()
                                        reply_text = f"✅ Повтор → {_repeat_label(_new_repeat)}"
                                    elif _new_repeat == "once":
                                        t["repeat"]  = "once"
                                        t["updated"] = _today()
                                        reply_text = "✅ Повтор убран"
                                    else:
                                        reply_text = (
                                            "🌀 Не поняла повторение. Варианты: "
                                            "каждый день / по будням / по выходным / "
                                            "раз в неделю / "
                                            "пн ср пт (дни недели) / убрать"
                                        )
                                else:
                                    reply_text = f"🌀 Поле «{field}» не знаю. Скажи: название/дедлайн/напоминание/группа/повтор"
                                if "✅" in (reply_text or ""):
                                    store_set_tasks(user_id, tasks)
                                    await _sync_pending()
                                    tid_edited = t.get("task_id","")
                                    await state.update_data(
                                        last_task_id=tid_edited,
                                        last_task_title=t.get("title","")
                                    )
                                    pass  # profile not shown automatically
                                    missing = []
                                    if not t.get("deadline"):
                                        missing.append("📅 дедлайн")
                                    if not t.get("label_name"):
                                        missing.append("🎨 группу")
                                    if not t.get("reminder"):
                                        missing.append("🔔 напоминание")
                                    if missing and tid_edited:
                                        suggest = ", ".join(missing)
                                        edit_kb = InlineKeyboardMarkup(inline_keyboard=[[
                                            InlineKeyboardButton(
                                                text="✏️ Дополнить",
                                                callback_data=f"ttask_edit|{tid_edited}"
                                            )
                                        ]])
                                        reply_text += f"\n<i>Можно также добавить: {suggest}</i>"
                                        action = {"_edit_kb": edit_kb}
            except Exception as e:
                logger.warning(f"Intent router error: {e}")
            # ──────────────────────────────────────────────────────────────

            # P-41: взвод флага приветствия если садовник поздоровался и SR ответил
            if _is_greeting and not _greeting_already:
                try:
                    _fc_ws2 = store_get_workspace(user_id) or {}
                    _fc_ws2["_greeting_sent_date"] = _today()
                    store_set_workspace(user_id, _fc_ws2)
                except Exception:
                    pass
            _add_to_history(user_id, "user", text)
            # P-64b: _intent_map_needed removed — classifier handles routing
            # P-29: countdown sphere_history_needed
            sh_current = _sphere_history_needed.get(user_id, 0)
            if sh_current > 0:
                _sphere_history_needed[user_id] = sh_current - 1
            _add_to_history(user_id, "assistant", reply_text)
            # Persist memory to GitHub (fire-and-forget)
            _pending_writes[f"{_user_path(user_id)}/memory.json"] = {
                "sessions": _sessions.get(user_id, []),
                "updated": _today()
            }
            _fire_sync()  # immediate sync — don't lose history on Render sleep
        else:
            reply_text = "🌿 СР временно недоступен. Попробуй чуть позже."
    except Exception as e:
        logger.error("Free conversation error: " + str(e))
        reply_text = "🌿 Связь прервалась. Попробуй ещё раз."
    finally:
        _typing_stop.set()
        _typing_task.cancel()

    # P-70d: apply suggest keyboard if no action from router
    if _suggest_action_kb and not action:
        action = _suggest_action_kb
    kb = _get_action_keyboard(action)
    if reply_text and reply_text.strip():
        _has_html = any(tag in reply_text for tag in ["<b>", "<a href", "<i>"])
        if _has_html:
            # Fallback: if HTML tags are unbalanced Telegram will reject — try HTML first, fallback to None
            try:
                _sent_msg = await message.answer(reply_text, reply_markup=kb if kb else None, parse_mode="HTML")
            except Exception:
                import re as _re_html
                _clean = _re_html.sub(r"<[^>]+>", "", reply_text)
                _sent_msg = await message.answer(_clean, reply_markup=kb if kb else None)
        else:
            _sent_msg = await message.answer(reply_text, reply_markup=kb if kb else None)
        _last_bot_message[str(message.from_user.id)] = {"message_id": _sent_msg.message_id, "text": reply_text}