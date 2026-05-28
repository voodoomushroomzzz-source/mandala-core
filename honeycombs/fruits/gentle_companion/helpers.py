# -*- coding: utf-8 -*-
"""
helpers.py — Helpers & Auth
Utilities, authorization, deep profile, observations, interaction tracking.
Glue between config/store/github_api and the handler layer.

Part of: honeycombs/fruits/gentle_companion/
Phase: 3 (depends on config.py, store.py, github_api.py)

Key items:
  Auth:     is_authorized, ensure_user_loaded, _check_ready, _invalidate_auth_cache
  Deep profile: _get_deep_profile, _save_deep_profile, _update_deep_profile
  Observations: _add_sr_observation, _detect_emotion, _update_sphere_history
  Reflection:   _get_session_reflection_hint, _add_growth_history_entry
  Tracking: _track_interaction, _can_send_proactive, _mark_proactive_sent
            _silence_phase, _time_matches, _last_interaction
  Task/group utils: calculate_priority, _make_group_id
  Retroactive: _seed_sphere_history_from_achievements
  Also: _days_since_last_interaction, _recalc_resonance_from_achievements
        (moved here from store.py — they need _last_interaction)

Global trackers (reset daily):
  _last_interaction, _proactive_sent_today, _morning_sent, _birthday_sent
  _daily_stats, _daily_issues, _intent_tracker
"""

# ─── Auth ─────────────────────────────────────────────────────────────────────

_auth_cache: dict = {}
AUTH_CACHE_TTL = 120

def is_authorized(telegram_id: str) -> bool:
    """Check if user has a profile loaded. Load on demand if not."""
    uid = str(telegram_id)
    store = _get_user_store(uid)
    return store.get("ready", False) and store.get("profile") is not None

async def ensure_user_loaded(telegram_id: str) -> bool:
    """Load user data if not already loaded. Returns True if user exists."""
    uid = str(telegram_id)
    store = _get_user_store(uid)
    if not store.get("ready"):
        await _load_user(uid)
    return store.get("profile") is not None

def _invalidate_auth_cache(telegram_id: str) -> None:
    _auth_cache.pop(telegram_id, None)

async def _check_ready(message: Message, user_id: str = None) -> bool:
    """Guard: returns False and notifies user if store not loaded yet."""
    if not user_id:
        user_id = str(message.from_user.id) if message.from_user else "0"
    store = _get_user_store(user_id)
    if not store.get("ready"):
        await message.answer("🌱 Запускаюсь, подожди пару секунд и повтори.")
        return False
    return True

# ─── Resonance helpers ────────────────────────────────────────────────────────


def _add_growth_history_entry(gardener: dict, resonance: int, telegram_id: str = "") -> dict:
    history = gardener.get("growth_history", [])
    today = _today()
    if not history or history[-1].get("date") != today:
        # Use store_get_achievements_count if telegram_id provided, else 0
        ach_count = store_get_achievements_count(telegram_id) if telegram_id else 0
        history.append({"date": today, "resonance": resonance, "achievements_count": ach_count})
    gardener["growth_history"] = history[-90:]
    return gardener

# ─── Deep Profile / Symbiosis (v7.27.0) ───────────────────────────────────────
_reflection_sent: dict = {}  # uid → date — one reflection hint per session

_DEEP_OBS_LIMIT = 30  # ~2 weeks of active use

def _get_deep_profile(telegram_id: str) -> dict:
    """Get deep_profile from gardener.json. Initialise if missing."""
    profile = store_get_profile(telegram_id) or {}
    dp = profile.get("deep_profile")
    if not dp or not isinstance(dp, dict):
        dp = {
            "dominant_sphere": None,
            "weak_sphere": None,
            "streak_days": 0,
            "streak_sphere": None,
            "last_reflection_date": None,
            "observations": []
        }
        profile["deep_profile"] = dp
        store_set_profile(telegram_id, profile)
    return dp

def _save_deep_profile(telegram_id: str, dp: dict) -> None:
    profile = store_get_profile(telegram_id) or {}
    profile["deep_profile"] = dp
    store_set_profile(telegram_id, profile)

def _update_deep_profile(telegram_id: str) -> None:
    """Called after complete_task. Analyses sphere patterns and adds observations."""
    sr   = store_get_sphere_resonance(telegram_id)
    dp   = _get_deep_profile(telegram_id)
    today = _today()

    # Find dominant and weak spheres
    dominant = max(SPHERES, key=lambda s: sr.get(s, 20))
    weak     = min(SPHERES, key=lambda s: sr.get(s, 20))
    dp["dominant_sphere"] = dominant
    dp["weak_sphere"]     = weak

    # Update streak: how many consecutive days closing tasks in same sphere
    prev_streak_sphere = dp.get("streak_sphere")
    if prev_streak_sphere == dominant:
        dp["streak_days"] = dp.get("streak_days", 0) + 1
    else:
        dp["streak_days"]    = 1
        dp["streak_sphere"]  = dominant

    # Add observation if pattern is notable
    obs = dp.get("observations", [])
    note = None
    streak = dp.get("streak_days", 1)

    dom_pct  = sr.get(dominant, 20)
    weak_pct = sr.get(weak, 20)
    dom_ru   = SPHERE_NAME_RU.get(dominant, dominant)
    weak_ru  = SPHERE_NAME_RU.get(weak, weak)

    if streak >= 3 and today != dp.get("last_reflection_date"):
        note = (f"{today}: {streak} дней подряд активна сфера «{dom_ru}» ({dom_pct}%), "
                f"«{weak_ru}» на {weak_pct}%")
    elif weak_pct < 15 and today != dp.get("last_reflection_date"):
        note = f"{today}: сфера «{weak_ru}» очень слабая ({weak_pct}%) — давно без внимания"

    if note:
        obs.append(note)
        dp["observations"] = obs[-_DEEP_OBS_LIMIT:]  # keep last 30

    dp["last_reflection_date"] = today
    _save_deep_profile(telegram_id, dp)

def _get_session_reflection_hint(telegram_id: str) -> str | None:
    """Returns a one-line hint for SR if notable pattern exists. Max once per session."""
    today = _today()
    if _reflection_sent.get(telegram_id) == today:
        return None  # already sent today
    dp      = _get_deep_profile(telegram_id)
    sr      = store_get_sphere_resonance(telegram_id)
    streak  = dp.get("streak_days", 0)
    dominant = dp.get("dominant_sphere")
    weak     = dp.get("weak_sphere")
    if not dominant or not weak:
        return None
    dom_pct  = sr.get(dominant, 20)
    weak_pct = sr.get(weak, 20)
    dom_ru   = SPHERE_NAME_RU.get(dominant, dominant)
    weak_ru  = SPHERE_NAME_RU.get(weak, weak)
    hint = None
    # Get confirmed interests for personalized suggestions
    _mem_h = dp.get("memory", {})
    _confirmed = _mem_h.get("interests", {}).get("confirmed", [])
    _confirmed_names = [i["name"] if isinstance(i, dict) else i for i in _confirmed[:3]]
    _interest_hint = f" Интересы садовника: {', '.join(_confirmed_names)}." if _confirmed_names else ""

    if streak >= 3:
        hint = (f"Садовник {streak} дней подряд активен в сфере «{dom_ru}» ({dom_pct}%). "
                f"Сфера «{weak_ru}» на {weak_pct}%.{_interest_hint} "
                f"Можно мягко упомянуть баланс один раз если уместно — не навязывать.")
    elif weak_pct < 15:
        hint = (f"Сфера «{weak_ru}» очень слабая ({weak_pct}%) — давно без движения.{_interest_hint} "
                f"Можно предложить конкретное действие через интересы садовника — не навязывать.")
    if hint:
        _reflection_sent[telegram_id] = today
    return hint


# ── SR Learning Loop helpers ──────────────────────────────────────────────────

def _update_sphere_history(user_id: str, sphere: str, task: bool = False,
                           achievement: bool = False, resonance_delta: int = 0) -> None:
    """Update monthly sphere statistics in deep_profile.sphere_history."""
    prof = store_get_profile(user_id)
    if not prof:
        return
    dp = prof.setdefault("deep_profile", {})
    history = dp.setdefault("sphere_history", [])
    cur_month = _today()[:7]  # YYYY-MM
    # Find or create current month entry
    entry = next((e for e in history if e.get("month") == cur_month), None)
    if not entry:
        entry = {
            "month": cur_month,
            "health":      {"tasks": 0, "achievements": 0, "resonance_delta": 0},
            "creativity":  {"tasks": 0, "achievements": 0, "resonance_delta": 0},
            "work":        {"tasks": 0, "achievements": 0, "resonance_delta": 0},
            "connections": {"tasks": 0, "achievements": 0, "resonance_delta": 0},
            "growth":      {"tasks": 0, "achievements": 0, "resonance_delta": 0},
            "other":       {"tasks": 0, "achievements": 0, "resonance_delta": 0},
        }
        history.append(entry)
    # Update sphere counters
    s = sphere if sphere in entry else "other"
    if task:        entry[s]["tasks"] += 1
    if achievement: entry[s]["achievements"] += 1
    entry[s]["resonance_delta"] += resonance_delta
    # Keep only 12 months rolling window
    dp["sphere_history"] = sorted(history, key=lambda x: x["month"])[-12:]
    store_set_profile(user_id, prof)

def _add_sr_observation(user_id: str, obs_type: str, text: str,
                        sphere: str = None) -> None:
    """Write SR observation to deep_profile.sr_observations[].
    Triggers synthesis every 2 new observations."""
    prof = store_get_profile(user_id)
    if not prof:
        return
    dp = prof.setdefault("deep_profile", {})
    obs = dp.setdefault("sr_observations", [])
    obs.append({
        "date": _today(),
        "type": obs_type,   # pattern|emotional_signal|silence|positive
        "sphere": sphere,
        "text": text,
    })
    # Keep last 50 observations
    dp["sr_observations"] = obs[-50:]
    store_set_profile(user_id, prof)
    # P-31: observation-based synthesis trigger
    ws = store_get_workspace(user_id) or {}
    count = ws.get("_pending_synthesis_count", 0) + 1
    ws["_pending_synthesis_count"] = count
    store_set_workspace(user_id, ws)
    if count >= 2:
        import asyncio as _asyncio_syn
        _asyncio_syn.create_task(_generate_synthesis(user_id))

def _detect_emotion(text: str) -> str:
    """Detect emotional signal in text. Returns signal type or empty string."""
    text_l = text.lower()
    negative = ["устал", "тревожно", "тревога", "плохо", "тяжело", "перегруз",
                "грустно", "злюсь", "не могу", "сложно", "депресс", "выгор",
                "не хочу", "бессмысл", "не справл"]
    positive = ["отлично", "супер", "рад ", "радуюсь", "счастлив", "доволен",
                "получилось", "справился", "гордо", "кайф"]
    # Check negation: "не устал", "не тревожно" — not negative
    negated = any(text_l.startswith(w) for w in ["не ", "не"]) and any(w in text_l for w in negative)
    if not negated and any(w in text_l for w in negative):
        return "negative"
    if any(w in text_l for w in positive):
        return "positive"
    return ""

def _seed_sphere_history_from_achievements(user_id: str, achievements: list) -> None:
    """One-time retroactive seed of sphere_history from existing achievements.
    Called on load if sphere_history is empty. Approximate — uses completed date."""
    if not achievements:
        return
    prof = store_get_profile(user_id)
    if not prof:
        return
    dp = prof.setdefault("deep_profile", {})
    if dp.get("sphere_history"):
        return  # already seeded
    # Group by month and sphere
    monthly: dict = {}
    for ach in achievements:
        cat  = ach.get("category", "other")
        date = ach.get("completed", "")
        if not date or len(date) < 7:
            continue
        month = date[:7]  # YYYY-MM
        monthly.setdefault(month, {})
        monthly[month].setdefault(cat, {"tasks": 0, "achievements": 0, "resonance_delta": 0})
        monthly[month][cat]["achievements"] += 1
        monthly[month][cat]["resonance_delta"] += ach.get("resonance_bonus", 3)
    if not monthly:
        return
    spheres = ["health", "creativity", "work", "connections", "growth", "other"]
    history = []
    for month in sorted(monthly.keys())[-12:]:
        entry = {"month": month}
        for s in spheres:
            entry[s] = monthly[month].get(s, {"tasks": 0, "achievements": 0, "resonance_delta": 0})
        history.append(entry)
    dp["sphere_history"] = history
    store_set_profile(user_id, prof)
    logger.info(f"sphere_history seeded from {len(achievements)} achievements for {user_id}")

# ─── Task helpers ─────────────────────────────────────────────────────────────

def calculate_priority(deadline: str = None, tz_name: str = "Europe/Moscow") -> int:
    p = 5
    if deadline:
        try:
            from zoneinfo import ZoneInfo as _ZI_cp
            now = datetime.now(_ZI_cp(tz_name))
            days = (datetime.fromisoformat(deadline) - now).days
            p += 2 if days < 0 else (1 if days <= 3 else 0)
        except Exception:
            pass
    return max(1, min(10, p))

# ─── Group helpers ────────────────────────────────────────────────────────────

def _make_group_id(name: str, existing: list) -> str:
    base = "".join(c for c in name.lower() if c.isalnum() or c == "_") or "group"
    gid, counter = base, 1
    while any(g.get("id") == gid for g in existing):
        gid = f"{base}_{counter}"
        counter += 1
    return gid

# ─── Proactive / Silence trackers ─────────────────────────────────────────────

_proactive_sent_today: dict = {}
_morning_sent: dict = {}        # uid → date, separate from proactive
_birthday_sent: dict = {}       # uid → date, separate flag for birthday
_last_interaction: dict = {}

# ── SR Learning Loop — in-memory, reset daily ──────────────────────────────────
_daily_stats: dict = {}   # uid → {messages, tasks_created, tasks_completed, achievements}
_daily_issues: list = []  # [{user_id, type, intent, count, context}]
_intent_tracker: dict = {}  # uid → [last_intent, last_intent] for repeat detection

def _track_interaction(telegram_id: str, intent: str = "", msg_type: str = "message") -> None:
    uid = str(telegram_id)
    today_str = _today()
    _last_interaction[uid] = today_str
    # Persist to workspace for silence detection
    ws = store_get_workspace(uid) or {}
    ws["last_interaction_date"] = today_str
    # P-37: store exact datetime for daytime proactive window
    from zoneinfo import ZoneInfo as _ZI_track
    from datetime import datetime as _dt_track
    try:
        _tz_track = (store_get_profile(uid) or {}).get("companion_settings", {}).get("timezone", "Europe/Moscow")
        ws["last_interaction_datetime"] = _dt_track.now(_ZI_track(_tz_track)).isoformat()
    except Exception:
        ws["last_interaction_datetime"] = _dt_track.now().isoformat()
    store_set_workspace(uid, ws)
    # Daily stats
    if uid not in _daily_stats:
        _daily_stats[uid] = {"messages": 0, "tasks_created": 0, "tasks_completed": 0, "achievements": 0, "intents": {}}
    _daily_stats[uid]["messages"] += 1
    if intent:
        _daily_stats[uid]["intents"][intent] = _daily_stats[uid]["intents"].get(intent, 0) + 1
    # Persist daily_stats for crash/redeploy recovery
    _pending_writes["honeycombs/sessions/daily_stats_live.json"] = dict(_daily_stats)
    # Intent repeat detection (possible failed request)
    if intent and intent not in ("conversation", "show_tasks", "show_profile"):
        _intent_tracker.setdefault(uid, [])
        _intent_tracker[uid].append(intent)
        if len(_intent_tracker[uid]) > 5:
            _intent_tracker[uid] = _intent_tracker[uid][-5:]
        # Two identical action intents in a row = possible failure
        if len(_intent_tracker[uid]) >= 2 and _intent_tracker[uid][-1] == _intent_tracker[uid][-2]:
            _daily_issues.append({
                "user_id": uid,
                "type": "repeated_request",
                "intent": intent,
                "count": 2,
                "context": f"повторный {intent}"
            })

def _can_send_proactive(telegram_id: str) -> bool:
    return _proactive_sent_today.get(str(telegram_id)) != _today()

def _mark_proactive_sent(telegram_id: str) -> None:
    _proactive_sent_today[str(telegram_id)] = _today()

def _silence_phase(telegram_id: str) -> int:
    last = _last_interaction.get(str(telegram_id))
    if not last:
        return 1
    try:
        days = (datetime.now() - datetime.strptime(last, "%Y-%m-%d")).days
        return 1 if days <= 7 else (2 if days <= 30 else 3)
    except Exception:
        return 1

def _time_matches(setting_time: str, timezone: str = "Europe/Moscow") -> bool:
    """Check if current time in gardener timezone matches setting_time (HH:MM). Window 5 min."""
    if not setting_time:
        return False
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime as _dt
        tz = ZoneInfo(timezone)
        now = _dt.now(tz)
        h, m_val = map(int, setting_time.split(":"))
        target = now.replace(hour=h, minute=m_val, second=0, microsecond=0)
        return abs((now - target).total_seconds()) <= 600  # 10 min window
    except Exception:
        return False

def _days_since_last_interaction(telegram_id: str) -> int:
    """Days since last user message. 0=today, 999=never."""
    last = _last_interaction.get(str(telegram_id))
    if not last:
        return 999
    try:
        from datetime import datetime as _dti
        return (_dti.now() - _dti.strptime(last, "%Y-%m-%d")).days
    except Exception:
        return 999
