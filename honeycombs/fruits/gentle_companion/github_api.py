# -*- coding: utf-8 -*-
"""
github_api.py — GitHub API & Sync
HTTP layer for all GitHub operations.

Part of: honeycombs/fruits/gentle_companion/
Phase: 2 (depends on config.py, store.py)

Routing rule:
  gardeners/* → _gardeners_get / _gardeners_put  (mandala-gardeners repo)
  everything else → _github_get / _github_put    (mandala-core repo)
  NEVER mix.

Key functions:
  get_http_session()             — shared aiohttp session
  _github_get / _github_put      — mandala-core repo
  _gardeners_get / _gardeners_put — mandala-gardeners repo
  _sync_pending()                — flush _pending_writes to GitHub
  _fire_sync()                   — trigger background sync
  _load_user()                   — load one gardener from GitHub → RAM
  _load_store()                  — load all gardeners on startup
  _today(), _normalize_time()    — date/time helpers
  _city_to_timezone()            — city → IANA timezone
  _json_dumps()                  — canonical JSON serialization
"""

# ─── Global HTTP session ───────────────────────────────────────────────────────

_http_session: Optional[aiohttp.ClientSession] = None

async def get_http_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _today(tz_name: str = "Europe/Moscow") -> str:
    from zoneinfo import ZoneInfo
    try:
        return datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d")

def _normalize_time(t: str) -> str:
    """Normalize time string to HH:MM with leading zero. '9:00' → '09:00'"""
    try:
        h, m = t.strip().split(":")
        return f"{int(h):02d}:{m.zfill(2)}"
    except Exception:
        return t


CIS_TIMEZONES = {
    "алматы": "Asia/Almaty", "алмата": "Asia/Almaty",
    "астана": "Asia/Almaty", "нур-султан": "Asia/Almaty",
    "киев": "Europe/Kiev", "київ": "Europe/Kiev",
    "минск": "Europe/Minsk", "мінск": "Europe/Minsk",
    "ташкент": "Asia/Tashkent", "баку": "Asia/Baku",
    "ереван": "Asia/Yerevan", "тбилиси": "Asia/Tbilisi",
    "бишкек": "Asia/Bishkek", "душанбе": "Asia/Dushanbe",
    "ашхабад": "Asia/Ashgabat",
}

async def _city_to_timezone(city: str) -> str:
    """Resolve city name to IANA timezone string.
    Checks hardcoded CIS cities first, then uses geopy + timezonefinder.
    Falls back to Europe/Moscow on any error.
    """
    if not city:
        return "Europe/Moscow"
    city_lower = city.strip().lower()
    if city_lower in CIS_TIMEZONES:
        return CIS_TIMEZONES[city_lower]
    try:
        from geopy.geocoders import Nominatim
        from timezonefinder import TimezoneFinder
        import asyncio
        loop = asyncio.get_event_loop()
        geolocator = Nominatim(user_agent="mandala_bot_tz", timeout=5)
        # Run blocking geocode in executor to avoid blocking event loop
        location = await loop.run_in_executor(None, geolocator.geocode, city)
        if not location:
            return "Europe/Moscow"
        tf = TimezoneFinder()
        tz = tf.timezone_at(lat=location.latitude, lng=location.longitude)
        return tz or "Europe/Moscow"
    except Exception as e:
        logger.warning(f"Timezone lookup failed for '{city}': {e}")
        return "Europe/Moscow"

def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)

# ─── GitHub API ───────────────────────────────────────────────────────────────

async def _github_get(file_path: str, force: bool = False) -> Optional[Any]:
    """GET a file from GitHub. Skips download if SHA unchanged (cache hit)."""
    if not GITHUB_TOKEN:
        return None
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}?ref=main"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/7.3.0"
    }
    session = await get_http_session()
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                data = await resp.json()
                new_sha = data.get("sha", "")
                # SHA-optimization: skip decode if file unchanged
                if not force and _sha_cache.get(file_path) == new_sha:
                    logger.debug(f"SHA cache hit: {file_path}")
                    return None  # caller should use cached value
                _sha_cache[file_path] = new_sha
                content = base64.b64decode(data["content"]).decode("utf-8-sig")  # utf-8-sig strips BOM
                try:
                    return json.loads(content)
                except Exception:
                    return content
            return None
    except Exception as e:
        logger.error(f"GitHub GET error [{file_path}]: {e}")
        return None

async def _github_put(path: str, content: Any, _retry: int = 0) -> bool:
    """PUT a file to GitHub. Retries once on 409 SHA conflict."""
    if not GITHUB_TOKEN or _retry > 1:
        return False
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/7.11.0"
    }
    session = await get_http_session()
    sha = None
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json()
                sha = data.get("sha")
                _sha_cache[path] = sha
    except Exception:
        pass
    content_b64 = base64.b64encode(_json_dumps(content).encode("utf-8")).decode("utf-8")
    payload = {"message": f"bot: sync {path}", "content": content_b64, "branch": "main"}
    if sha:
        payload["sha"] = sha
    try:
        async with session.put(url, headers=headers, json=payload,
                               timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status in [200, 201]:
                return True
            if resp.status == 409:
                _sha_cache.pop(path, None)
                logger.warning(f"SHA conflict on {path}, retrying...")
                await asyncio.sleep(0.5)
                return await _github_put(path, content, _retry + 1)
            logger.error(f"GitHub PUT {resp.status} [{path}]")
            return False
    except Exception as e:
        logger.error(f"GitHub PUT error [{path}]: {e}")
        return False

# ─── Gardeners-repo API (separate private repo for user data) ─────────────────

async def _gardeners_get(file_path: str, force: bool = False) -> Optional[Any]:
    """GET a file from mandala-gardeners repo."""
    if not GARDENERS_TOKEN:
        return None
    url = f"https://api.github.com/repos/{GARDENERS_REPO}/contents/{file_path}?ref=main"
    headers = {
        "Authorization": f"token {GARDENERS_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/7.3.0"
    }
    session = await get_http_session()
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                data = await resp.json()
                new_sha = data.get("sha", "")
                cache_key = f"g:{file_path}"
                if not force and _sha_cache.get(cache_key) == new_sha:
                    logger.debug(f"SHA cache hit (gardeners): {file_path}")
                    return None
                _sha_cache[cache_key] = new_sha
                content = base64.b64decode(data["content"]).decode("utf-8-sig")
                try:
                    return json.loads(content)
                except Exception:
                    return content
            return None
    except Exception as e:
        logger.error(f"Gardeners GET error [{file_path}]: {e}")
        return None

async def _gardeners_put(path: str, content: Any, _retry: int = 0) -> bool:
    """PUT a file to mandala-gardeners repo."""
    if not GARDENERS_TOKEN or _retry > 1:
        return False
    url = f"https://api.github.com/repos/{GARDENERS_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GARDENERS_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MandalaGardenBot/7.11.0"
    }
    session = await get_http_session()
    cache_key = f"g:{path}"
    sha = None
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json()
                sha = data.get("sha")
                _sha_cache[cache_key] = sha
    except Exception:
        pass
    content_b64 = base64.b64encode(_json_dumps(content).encode("utf-8")).decode("utf-8")
    payload = {"message": f"bot: sync {path}", "content": content_b64, "branch": "main"}
    if sha:
        payload["sha"] = sha
    try:
        async with session.put(url, headers=headers, json=payload,
                               timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status in [200, 201]:
                return True
            if resp.status == 409:
                _sha_cache.pop(cache_key, None)
                logger.warning(f"SHA conflict (gardeners) on {path}, retrying...")
                await asyncio.sleep(0.5)
                return await _gardeners_put(path, content, _retry + 1)
            logger.error(f"Gardeners PUT {resp.status} [{path}]")
            return False
    except Exception as e:
        logger.error(f"Gardeners PUT error [{path}]: {e}")
        return False


# ─── Background sync ──────────────────────────────────────────────────────────

async def _sync_pending() -> None:
    """Flush all pending writes to GitHub sequentially. Lock prevents parallel syncs."""
    if _sync_lock.locked():
        return  # another sync already running — scheduler will retry next tick
    async with _sync_lock:
        try:
            if not _pending_writes:
                return
            batch = dict(_pending_writes)
            _pending_writes.clear()
            logger.info(f"Syncing {len(batch)} file(s) to GitHub...")

            async def _put_one(path, data):
                if path.startswith("gardeners/"):
                    ok = await _gardeners_put(path, data)
                else:
                    ok = await _github_put(path, data)
                if not ok:
                    logger.warning(f"Sync failed for {path}, re-queuing")
                    _pending_writes.setdefault(path, data)
                return ok

            for p, c in batch.items():
                await _put_one(p, c)
        except Exception as e:
            logger.error(f"Sync pending crashed: {e}", exc_info=True)

def _fire_sync() -> None:
    """Schedule a background sync without blocking the caller."""
    asyncio.create_task(_sync_pending())

# ─── Initial load ─────────────────────────────────────────────────────────────

async def _load_user(telegram_id: str) -> None:
    """Load profile + workspace + memory for a specific user from GitHub."""
    uid = str(telegram_id)
    base = _user_path(uid)
    results = await asyncio.gather(
        _gardeners_get(f"{base}/profile.json", force=True),
        _gardeners_get(f"{base}/workspace.json", force=True),
        _gardeners_get(f"{base}/memory.json", force=True),
        return_exceptions=True
    )
    profile, workspace, memory = results
    store = _get_user_store(uid)
    store["ready"] = False
    store["profile"]   = profile if isinstance(profile, dict) else None
    _ws = workspace if isinstance(workspace, dict) else {"tasks": [], "groups": []}
    # Auto-cleanup: remove tasks with empty or very short title
    _raw_tasks = _ws.get("tasks", [])
    _clean_tasks = [t for t in _raw_tasks if len((t.get("title") or "").strip()) >= 2]
    if len(_clean_tasks) < len(_raw_tasks):
        logger.info(f"Auto-cleaned {len(_raw_tasks) - len(_clean_tasks)} empty task(s) for {uid}")
        _ws["tasks"] = _clean_tasks
        _pending_writes[f"{_user_path(uid)}/workspace.json"] = _ws
        _fire_sync()  # fire-and-forget — don't block startup
    store["workspace"] = _ws
    store["ready"]     = store["profile"] is not None
    # Restore conversation history from memory.json
    if isinstance(memory, dict) and memory.get("sessions"):
        _sessions[uid] = memory["sessions"]
        logger.info(f"Memory restored: {uid} msgs={len(_sessions[uid])}")
    name = store["profile"].get("name", "?") if store["profile"] else "none"
    tasks_count = len(store["workspace"].get("tasks", []))
    logger.info(f"User loaded: {uid} name={name} tasks={tasks_count}")
    # One-time retroactive seed of sphere_history from achievements
    _achs = store["workspace"].get("achievements", [])
    if _achs and store["profile"]:
        _dp_check = store["profile"].get("deep_profile", {})
        if not _dp_check.get("sphere_history"):
            _seed_sphere_history_from_achievements(uid, _achs)

async def _load_store() -> None:
    """Load all approved gardeners from whitelist on startup (parallel)."""
    logger.info("Loading store from GitHub...")
    whitelist = await _gardeners_get("gardeners/whitelist.json", force=True) or {}
    approved = whitelist.get("approved", ["224736062"]) if isinstance(whitelist, dict) else ["224736062"]
    # P-24: parallel load via asyncio.gather
    _gather_results = await asyncio.gather(
        *[_load_user(str(uid)) for uid in approved],
        return_exceptions=True
    )
    # Log any exceptions from gather (were silently swallowed before)
    for uid, result in zip(approved, _gather_results):
        if isinstance(result, Exception):
            logger.error(f"_load_user failed for {uid}: {result}")
    # P-25r: one-time recalc resonance_level from sphere_resonance mean (fix inflated values)
    for uid in approved:
        try:
            sr = store_get_sphere_resonance(str(uid))
            mean = max(5, min(100, round(sum(sr[s] for s in SPHERES) / len(SPHERES))))
            prof = store_get_profile(str(uid))
            if prof and prof.get("resonance_level", 0) != mean:
                prof["resonance_level"] = mean
                store_set_profile(str(uid), prof)
                logger.info(f"Resonance recalc: {uid} → {mean}%")
        except Exception as e:
            logger.warning(f"Resonance recalc failed for {uid}: {e}")
    _loaded_count = sum(
        1 for uid in approved
        if _get_user_store(str(uid)).get("ready")
    )
    logger.info(f"Store ready — {_loaded_count}/{len(approved)} gardener(s) loaded")