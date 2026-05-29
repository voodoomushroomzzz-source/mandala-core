# -*- coding: utf-8 -*-
"""
sr_memory.py -- SR Memory & Synthesis
Phase: 5. Updated: 2026-05-29 -- three-tier interest system (fresh/mentioned/confirmed).
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

    core      = mem.get("core", "")
    snapshots = mem.get("snapshots", [])
    insights  = dp.get("long_term_insights", [])
    old_obs   = dp.get("observations", [])[-5:]  # streak/sphere observations

    # Закрытые задачи
    tasks = store_get_tasks(user_id)
    completed = [t for t in tasks if t.get("status") == "completed"][-15:]
    tasks_text = "\n".join(f"- {t['title']}" for t in completed) if completed else "нет"

    obs_text       = "\n".join(f"- {o['date']}: {o['text']}" for o in obs)
    insights_text  = "\n".join(f"- {i['date']}: {i['text']}" for i in insights) if insights else "нет"
    snapshots_text = "\n".join(f"- {s['date']}: {s['text']}" for s in snapshots[-5:]) if snapshots else "нет"
    old_obs_text   = "\n".join(f"- {o}" for o in old_obs) if old_obs else "нет"

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
    _cur_media     = mem.get("media", {})
    _int_conf_txt  = ", ".join(_fmt_syn_item(i) for i in _cur_interests.get("confirmed", [])) or "нет"
    _int_ment_txt  = ", ".join(_fmt_syn_item(i) for i in _cur_interests.get("mentioned", [])) or "нет"
    _int_fresh_txt = ", ".join(_fmt_syn_item(i) for i in _cur_interests.get("fresh", []))    or "нет"
    _med_conf_txt  = ", ".join(_fmt_syn_item(i) for i in _cur_media.get("confirmed", []))    or "нет"
    _med_ment_txt  = ", ".join(_fmt_syn_item(i) for i in _cur_media.get("mentioned", []))    or "нет"

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
  confirmed (стабильные, топ-10): {_int_conf_txt}
  mentioned (соревнуются, топ-10): {_int_ment_txt}
  fresh (новые, огород, топ-15): {_int_fresh_txt}

ТЕКУЩИЕ МЕДИА (книги/фильмы/музыка):
  confirmed: {_med_conf_txt}
  mentioned: {_med_ment_txt}

ЖИВОЙ ДИАЛОГ (все сообщения — главный источник интересов, тем, медиа):
{dialog_text}

ПРАВИЛА обновления интересов и медиа:
- Интересы которые ВИДИШЬ В ДИАЛОГЕ — называй в confirmed_interests или mentioned_interests.
  Система сама распределит их по группам (fresh/mentioned/confirmed). Тебе не нужно управлять переходами.
- confirmed_interests: интересы которые явно и активно присутствуют в диалоге сегодня.
- mentioned_interests: интересы которые мелькнули, упомянуты вскользь.
- Медиа (confirmed макс 10, mentioned макс 10). Культурный опыт: определяй тип из контекста:
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
    ], max_tokens=3000)  # synthesis needs more tokens — not sent to Telegram

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

        # ── Константы групп интересов ─────────────────────────────────────────
        _FRESH_LIMIT     = 15   # огород: новые без подтверждений
        _MENTIONED_LIMIT = 10   # соревнование: набирают count
        _CONFIRMED_LIMIT = 10   # стабильное ядро
        _MENTIONED_DECAY = 15   # дней без упоминания → падает во fresh

        # ── Инициализация структуры (backward compat: если нет fresh) ─────────
        interests = mem.setdefault("interests", {"confirmed": [], "mentioned": [], "fresh": []})
        if "fresh" not in interests:
            interests["fresh"] = []

        # Нормализация: старый формат строк → объекты
        def _norm(lst):
            return [
                {"name": i, "count": 1, "last_seen": _today_syn} if isinstance(i, str) else i
                for i in lst
            ]
        interests["confirmed"] = _norm(interests.get("confirmed", []))
        interests["mentioned"] = _norm(interests.get("mentioned", []))
        interests["fresh"]     = _norm(interests.get("fresh", []))

        # ── Вспомогательные функции ───────────────────────────────────────────
        def _find(lst, name):
            """Найти объект по имени (case-insensitive). Вернуть (index, obj) или (None, None)."""
            key = name.lower()
            for idx, item in enumerate(lst):
                if item.get("name", "").lower() == key:
                    return idx, item
            return None, None

        def _make_item(name, count=0):
            return {"name": name, "count": count, "last_seen": _today_syn}

        def _weakest_confirmed():
            """Вернуть (index, obj) слабейшего в confirmed: min count, при равенстве min last_seen."""
            if not interests["confirmed"]:
                return None, None
            idx, obj = min(
                enumerate(interests["confirmed"]),
                key=lambda x: (x[1].get("count", 0), x[1].get("last_seen", ""))
            )
            return idx, obj

        # ── Шаг 1: Decay mentioned → fresh ───────────────────────────────────
        # Не упоминался 15 дней → падает во fresh с count=0
        still_mentioned = []
        for item in interests["mentioned"]:
            try:
                days = (_date_syn.today() - _date_syn.fromisoformat(
                    item.get("last_seen", _today_syn))).days
            except Exception:
                days = 0
            if days >= _MENTIONED_DECAY:
                # Перекладываем во fresh с обнулением count (если там ещё нет)
                fi, _ = _find(interests["fresh"], item["name"])
                if fi is None:
                    interests["fresh"].append(_make_item(item["name"], count=0))
            else:
                still_mentioned.append(item)
        interests["mentioned"] = still_mentioned

        # ── Шаг 2: Trim fresh по last_seen (FIFO, count игнорируется) ─────────
        interests["fresh"] = sorted(
            interests["fresh"],
            key=lambda x: x.get("last_seen", ""),
            reverse=True
        )[:_FRESH_LIMIT]

        # ── Шаг 3: Обработать confirmed_interests от LLM ──────────────────────
        for name in confirmed:
            if not name:
                continue
            # Уже в confirmed → count++, last_seen
            ci, cobj = _find(interests["confirmed"], name)
            if ci is not None:
                cobj["count"] += 1
                cobj["last_seen"] = _today_syn
                continue
            # Уже в mentioned → count++, last_seen (swap проверим на шаге 6)
            mi, mobj = _find(interests["mentioned"], name)
            if mi is not None:
                mobj["count"] += 1
                mobj["last_seen"] = _today_syn
                continue
            # Уже во fresh → count++, last_seen
            fi, fobj = _find(interests["fresh"], name)
            if fi is not None:
                fobj["count"] += 1
                fobj["last_seen"] = _today_syn
            else:
                # Совсем новый → во fresh, count=1 (первое упоминание)
                interests["fresh"].append(_make_item(name, count=1))

        # ── Шаг 4: Обработать mentioned_interests от LLM ──────────────────────
        # Только если нигде нет → во fresh с count=0
        for name in mentioned:
            if not name:
                continue
            _, cobj = _find(interests["confirmed"], name)
            if cobj:
                continue
            _, mobj = _find(interests["mentioned"], name)
            if mobj:
                continue
            _, fobj = _find(interests["fresh"], name)
            if fobj:
                continue
            interests["fresh"].append(_make_item(name, count=0))

        # ── Шаг 5: Promote fresh → mentioned (count >= 2) ─────────────────────
        still_fresh = []
        for item in interests["fresh"]:
            if item.get("count", 0) >= 2:
                if len(interests["mentioned"]) < _MENTIONED_LIMIT:
                    # Есть свободное место
                    item["last_seen"] = _today_syn
                    interests["mentioned"].append(item)
                else:
                    # Нет места → сравниваем со слабейшим в mentioned
                    weakest_m = min(
                        interests["mentioned"],
                        key=lambda x: (x.get("count", 0), x.get("last_seen", ""))
                    )
                    if (item.get("count", 0) > weakest_m.get("count", 0) or (
                        item.get("count", 0) == weakest_m.get("count", 0) and
                        item.get("last_seen", "") > weakest_m.get("last_seen", "")
                    )):
                        # Вытесняем слабейший → fresh с count=0
                        interests["mentioned"].remove(weakest_m)
                        interests["fresh"].append(_make_item(weakest_m["name"], count=0))
                        item["last_seen"] = _today_syn
                        interests["mentioned"].append(item)
                    else:
                        # Не смог вытеснить — остаётся во fresh
                        still_fresh.append(item)
            else:
                still_fresh.append(item)
        interests["fresh"] = still_fresh

        # ── Шаг 6: Swap mentioned → confirmed ─────────────────────────────────
        # Сильнейший из mentioned vs слабейший из confirmed
        if interests["mentioned"]:
            strongest_m = max(
                interests["mentioned"],
                key=lambda x: (x.get("count", 0), x.get("last_seen", ""))
            )
            wi, weakest_c = _weakest_confirmed()

            if wi is None:
                # confirmed пуст — просто добавляем
                interests["mentioned"].remove(strongest_m)
                strongest_m["last_seen"] = _today_syn
                interests["confirmed"].append(strongest_m)
            elif len(interests["confirmed"]) < _CONFIRMED_LIMIT:
                # Есть свободное место в confirmed
                interests["mentioned"].remove(strongest_m)
                strongest_m["last_seen"] = _today_syn
                interests["confirmed"].append(strongest_m)
            elif strongest_m.get("count", 0) >= weakest_c.get("count", 0):
                # Swap: слабый confirmed → fresh count=0
                interests["confirmed"].pop(wi)
                interests["fresh"].append(_make_item(weakest_c["name"], count=0))
                # Сильный mentioned → confirmed
                interests["mentioned"].remove(strongest_m)
                strongest_m["last_seen"] = _today_syn
                interests["confirmed"].append(strongest_m)
            # Иначе: нет достаточно сильного кандидата — confirmed остаётся статичным

        # ── Шаг 7: Финальный trim ─────────────────────────────────────────────
        # fresh: по last_seen DESC (FIFO), держим 15
        interests["fresh"] = sorted(
            interests["fresh"],
            key=lambda x: x.get("last_seen", ""),
            reverse=True
        )[:_FRESH_LIMIT]
        # mentioned: по count DESC, при равенстве last_seen DESC, держим 10
        interests["mentioned"] = sorted(
            interests["mentioned"],
            key=lambda x: (-x.get("count", 0), x.get("last_seen", "")),
            reverse=False
        )[:_MENTIONED_LIMIT]
        # confirmed: по count DESC, держим 10
        interests["confirmed"] = sorted(
            interests["confirmed"],
            key=lambda x: x.get("count", 0),
            reverse=True
        )[:_CONFIRMED_LIMIT]

        # Медиа (логика не изменилась)
        media = mem.setdefault("media", {"confirmed": [], "mentioned": []})
        conf_media_raw = result.get("confirmed_media", [])
        ment_media_raw = result.get("mentioned_media", [])

        def _norm_media(lst):
            return [
                {"name": i, "type": "unknown", "count": 1, "last_seen": _today_syn}
                if isinstance(i, str) else i
                for i in lst
            ]
        media["confirmed"] = _norm_media(media.get("confirmed", []))
        media["mentioned"] = _norm_media(media.get("mentioned", []))

        # Decay медиа
        def _decay_media(lst, max_days):
            result_m = []
            for item in lst:
                try:
                    days = (_date_syn.today() - _date_syn.fromisoformat(
                        item.get("last_seen", _today_syn))).days
                    if days < max_days:
                        result_m.append(item)
                except Exception:
                    result_m.append(item)
            return result_m
        media["confirmed"] = _decay_media(media["confirmed"], 30)
        media["mentioned"] = _decay_media(media["mentioned"], 15)

        for m in conf_media_raw:
            if isinstance(m, dict) and m.get("name"):
                key = m["name"].lower()
                existing = next(
                    (x for x in media["confirmed"]
                     if isinstance(x, dict) and x.get("name", "").lower() == key), None)
                if existing:
                    existing["count"] = existing.get("count", 1) + 1
                    existing["last_seen"] = _today_syn
                else:
                    media["confirmed"].append({
                        "name": m["name"], "type": m.get("type", "unknown"),
                        "count": 1, "last_seen": _today_syn
                    })
        for m in ment_media_raw:
            if isinstance(m, dict) and m.get("name"):
                key = m["name"].lower()
                in_conf = any(
                    isinstance(x, dict) and x.get("name", "").lower() == key
                    for x in media["confirmed"])
                if not in_conf:
                    existing = next(
                        (x for x in media["mentioned"]
                         if isinstance(x, dict) and x.get("name", "").lower() == key), None)
                    if existing:
                        existing["count"] = existing.get("count", 1) + 1
                        existing["last_seen"] = _today_syn
                    else:
                        media["mentioned"].append({
                            "name": m["name"], "type": m.get("type", "unknown"),
                            "count": 1, "last_seen": _today_syn
                        })
        media["confirmed"] = sorted(
            media["confirmed"], key=lambda x: x.get("last_seen", ""), reverse=True)[:10]
        media["mentioned"] = sorted(
            media["mentioned"], key=lambda x: x.get("last_seen", ""), reverse=True)[:10]

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