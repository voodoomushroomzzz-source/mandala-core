# -*- coding: utf-8 -*-
"""
store.py — Store Layer
All RAM-cache read/write functions. Single point of access to gardener data.
Does NOT make HTTP requests — only works with _store in memory.

Part of: honeycombs/fruits/gentle_companion/
Phase: 3 (depends on config.py)

Rule: NEVER add HTTP calls here. Only _store dict operations.

Note: _days_since_last_interaction and _recalc_resonance_from_achievements
      live in helpers.py — they depend on _last_interaction defined there.
"""

def store_get_profile(telegram_id: str) -> Optional[dict]:
    return copy.deepcopy(_get_user_store(telegram_id).get("profile"))

def store_set_profile(telegram_id: str, g: dict) -> None:
    _get_user_store(telegram_id)["profile"] = g
    _pending_writes[f"{_user_path(telegram_id)}/profile.json"] = g


async def _safe_cb_answer(callback: CallbackQuery, text: str = "", show_alert: bool = False) -> None:
    """Safely answer a callback query — ignores 'query too old' errors after bot restart."""
    try:
        await callback.answer(text, show_alert=show_alert)
    except Exception:
        pass  # TelegramBadRequest: query too old after bot restart

def store_get_workspace(telegram_id: str) -> Optional[dict]:
    return copy.deepcopy(_get_user_store(telegram_id).get("workspace"))

def store_set_workspace(telegram_id: str, w: dict) -> None:
    _get_user_store(telegram_id)["workspace"] = w
    _pending_writes[f"{_user_path(telegram_id)}/workspace.json"] = w

def store_get_tasks(telegram_id: str) -> list:
    ws = store_get_workspace(telegram_id)
    return copy.deepcopy(ws.get("tasks", [])) if ws else []

def store_set_tasks(telegram_id: str, t: list) -> None:
    ws = store_get_workspace(telegram_id) or {"tasks": [], "groups": [], "achievements": []}
    ws["tasks"] = t
    store_set_workspace(telegram_id, ws)

def store_get_achievements(telegram_id: str) -> list:
    ws = store_get_workspace(telegram_id)
    return copy.deepcopy(ws.get("achievements", [])) if ws else []

def store_set_achievements(telegram_id: str, a: list) -> None:
    ws = store_get_workspace(telegram_id) or {"tasks": [], "groups": [], "achievements": []}
    ws["achievements"] = a
    store_set_workspace(telegram_id, ws)


def store_get_achievements_count(telegram_id: str) -> int:
    """Achievements = number of closed tasks. Counter only."""
    ws = store_get_workspace(telegram_id)
    return int(ws.get("achievements_count", 0)) if ws else 0

def store_increment_achievements(telegram_id: str) -> int:
    """Increment achievement counter and sync resonance. Returns new count."""
    ws = store_get_workspace(telegram_id) or {"tasks": [], "groups": [], "achievements": []}
    count = int(ws.get("achievements_count", 0)) + 1
    ws["achievements_count"] = count
    store_set_workspace(telegram_id, ws)
    # P-63: removed _recalc_resonance_from_achievements (count*2 override — BUG-E)
    return count

def store_add_resonance(telegram_id: str, delta: int) -> int:
    """Add delta to resonance_level. Min 5, max 100. Returns new level."""
    profile = store_get_profile(telegram_id)
    if not profile:
        return 5
    current = int(profile.get("resonance_level", 5))
    new_val = max(5, min(100, current + delta))
    profile["resonance_level"] = new_val
    if telegram_id in _store:
        store_set_profile(telegram_id, profile)
        # profile.json is the source of truth — gardener.json write removed (dead code)
        _pending_writes[f"{_user_path(telegram_id)}/profile.json"] = profile
    return new_val

# ─── 5-Sphere Resonance (v7.26.0) ─────────────────────────────────────────────
SPHERES = ("health", "creativity", "work", "connections", "growth")
SPHERE_EMOJI = {
    "health":      "🌿",
    "creativity":  "🔥",
    "work":        "💼",
    "connections": "🤝",
    "growth":      "🌱",
}
SPHERE_NAME_RU = {
    "health":      "Тело",
    "creativity":  "Творчество",
    "work":        "Дело",
    "connections": "Связи",
    "growth":      "Рост",
}

def store_get_sphere_resonance(telegram_id: str) -> dict:
    """Get sphere_resonance dict. Initialises missing spheres to 20."""
    ws = store_get_workspace(telegram_id) or {}
    sr = dict(ws.get("sphere_resonance", {}))
    changed = False
    for s in SPHERES:
        if s not in sr:
            sr[s] = 20
            changed = True
    if changed:
        ws["sphere_resonance"] = sr
        store_set_workspace(telegram_id, ws)
    return sr

def store_set_sphere_resonance(telegram_id: str, sr: dict) -> None:
    ws = store_get_workspace(telegram_id) or {}
    ws["sphere_resonance"] = sr
    store_set_workspace(telegram_id, ws)

def store_add_sphere_resonance(telegram_id: str, sphere: str, delta: int) -> int:
    """Add delta to sphere. Clamp 5-100. Recalc overall resonance_level as mean of 5. Returns new overall."""
    if sphere not in SPHERES:
        sphere = "work"
    sr = store_get_sphere_resonance(telegram_id)
    sr[sphere] = max(5, min(100, sr[sphere] + delta))
    store_set_sphere_resonance(telegram_id, sr)
    mean = max(5, min(100, round(sum(sr[s] for s in SPHERES) / len(SPHERES))))
    profile = store_get_profile(telegram_id) or {}
    profile["resonance_level"] = mean
    store_set_profile(telegram_id, profile)
    return mean

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

def store_get_groups(telegram_id: str) -> dict:
    ws = store_get_workspace(telegram_id)
    return copy.deepcopy({"groups": ws.get("groups", [])}) if ws else {"groups": []}

def store_set_groups(telegram_id: str, g: dict) -> None:
    ws = store_get_workspace(telegram_id) or {"tasks": [], "groups": [], "achievements": []}
    ws["groups"] = g.get("groups", g) if isinstance(g, dict) else g
    store_set_workspace(telegram_id, ws)


def store_get_checklists(telegram_id: str) -> list:
    """Return checklists list from workspace."""
    ws = store_get_workspace(telegram_id)
    return copy.deepcopy(ws.get("checklists", [])) if ws else []

def store_set_checklists(telegram_id: str, checklists: list) -> None:
    """Save checklists list to workspace."""
    ws = store_get_workspace(telegram_id) or {"tasks": [], "groups": [], "achievements": [], "checklists": []}
    ws["checklists"] = checklists
    store_set_workspace(telegram_id, ws)


def store_get_reminders(telegram_id: str) -> list:
    ws = store_get_workspace(telegram_id)
    return copy.deepcopy(ws.get("reminders", [])) if ws else []

def store_set_reminders(telegram_id: str, reminders: list) -> None:
    ws = store_get_workspace(telegram_id) or {"tasks":[],"groups":[],"achievements":[],"reminders":[]}
    ws["reminders"] = reminders
    store_set_workspace(telegram_id, ws)