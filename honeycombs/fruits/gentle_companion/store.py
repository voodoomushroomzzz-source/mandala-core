# -*- coding: utf-8 -*-
"""
store.py -- Store Layer
RAM-cache read/write. No HTTP. Only _store dict.
Phase: 3.
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