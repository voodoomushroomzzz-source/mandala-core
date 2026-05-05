# patcher_20b_reminder_tz.py
# Fix: reminders respect gardener's timezone
# 1. Adds timezone offset to datetime_iso when creating reminders
# 2. Fixes run_reminder_scheduler to compare with timezone awareness
# 3. Adds timezone instruction to SR_INTENT_MAP
# Version: v1.0

import re
import sys

BOT_FILE = "bot.py"

def patch():
    with open(BOT_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    changes = 0

    # ═══════════════════════════════════════════════════════════════════════
    # 1. Fix run_reminder_scheduler: compare with timezone offset
    # ═══════════════════════════════════════════════════════════════════════

    # Find: now_str = _dtr6.now(_tz6).strftime("%Y-%m-%dT%H:%M")
    # Replace entire comparison logic
    old_scheduler_core = '''            now_str = _dtr6.now(_tz6).strftime("%Y-%m-%dT%H:%M")
            changed = False
            for r in list(reminders):
                if not r.get("active"):
                    continue
                if r.get("datetime_iso", "")[:16] != now_str:
                    continue'''

    new_scheduler_core = '''            now_dt = _dtr6.now(_tz6)
            now_str = now_dt.strftime("%Y-%m-%dT%H:%M")
            changed = False
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
                    continue'''

    if old_scheduler_core in content:
        content = content.replace(old_scheduler_core, new_scheduler_core, 1)
        changes += 1
        print("✅ 1/4 Fixed run_reminder_scheduler — timezone-aware comparison")
    else:
        print("❌ run_reminder_scheduler pattern not found")
        return False

    # ═══════════════════════════════════════════════════════════════════════
    # 2. Fix create_reminder intent: convert to gardener's local time
    # ═══════════════════════════════════════════════════════════════════════

    # Find the point after r_dt is computed from LLM, before saving to store
    old_rem_save = '''                            if not r_title or not r_dt:
                                reply_text = "🔔 Скажи точнее: «напомни мне X завтра в 9:00» или «напомни X через 30 минут»"
                            else:
                                reminders = store_get_reminders(user_id)
                                if len(reminders) >= REMINDER_LIMIT:
                                    reply_text = f"⚠️ Лимит {REMINDER_LIMIT} напоминаний."
                                else:
                                    rid = _make_reminder_id(reminders)
                                    reminders.append({"id":rid,"title":r_title,
                                                      "datetime_iso":r_dt,"repeat":r_repeat,"active":True})'''

    new_rem_save = '''                            if not r_title or not r_dt:
                                reply_text = "🔔 Скажи точнее: «напомни мне X завтра в 9:00» или «напомни X через 30 минут»"
                            else:
                                # Apply gardener's timezone offset to datetime_iso
                                # LLM returns local time; add timezone offset for storage
                                try:
                                    from zoneinfo import ZoneInfo as _ZIr2
                                    _tz_name_r = (store_get_profile(user_id) or {}).get("companion_settings", {}).get("timezone", "Europe/Moscow")
                                    _tz_r = _ZIr2(_tz_name_r)
                                    from datetime import datetime as _dtr2, timezone as _dtz2, timedelta as _td2
                                    if "+" not in r_dt and not r_dt.endswith("Z"):
                                        # Plain datetime, parse and add offset
                                        r_dt_local = _dtr2.strptime(r_dt, "%Y-%m-%dT%H:%M")
                                        r_dt_local = r_dt_local.replace(tzinfo=_tz_r)
                                        offset = r_dt_local.utcoffset()
                                        if offset:
                                            hours = int(offset.total_seconds() // 3600)
                                            minutes = int((offset.total_seconds() % 3600) // 60)
                                            sign = "+" if hours >= 0 else "-"
                                            r_dt = f"{r_dt}{sign}{abs(hours):02d}:{minutes:02d}"
                                except Exception:
                                    pass  # Keep original if parsing fails
                                reminders = store_get_reminders(user_id)
                                if len(reminders) >= REMINDER_LIMIT:
                                    reply_text = f"⚠️ Лимит {REMINDER_LIMIT} напоминаний."
                                else:
                                    rid = _make_reminder_id(reminders)
                                    reminders.append({"id":rid,"title":r_title,
                                                      "datetime_iso":r_dt,"repeat":r_repeat,"active":True})'''

    if old_rem_save in content:
        content = content.replace(old_rem_save, new_rem_save, 1)
        changes += 1
        print("✅ 2/4 Added timezone offset to datetime_iso on reminder creation")
    else:
        print("⚠️ create_reminder save pattern not found (may already be patched)")

    # ═══════════════════════════════════════════════════════════════════════
    # 3. Add timezone instruction to SR_INTENT_MAP
    # ═══════════════════════════════════════════════════════════════════════

    old_reminder_intent_rule = '''- "напомни мне X завтра в 9", "поставь напоминание X" → create_reminder, action.title=X, action.datetime="YYYY-MM-DDTHH:MM", action.repeat=once/daily/weekdays, 0.95'''

    new_reminder_intent_rule = '''- "напомни мне X завтра в 9", "поставь напоминание X" → create_reminder, action.title=X, action.datetime="YYYY-MM-DDTHH:MM", action.repeat=once/daily/weekdays, 0.95
  ВАЖНО: datetime_iso ВСЕГДА в локальном времени садовника из [Сейчас у садовника]. НЕ переводи в UTC. Если садовник говорит "в 13:00" и в контексте Asia/Almaty — ставь 13:00 по Алматы'''

    if old_reminder_intent_rule in content:
        content = content.replace(old_reminder_intent_rule, new_reminder_intent_rule, 1)
        changes += 1
        print("✅ 3/4 Added timezone rule to SR_INTENT_MAP")
    else:
        print("❌ SR_INTENT_MAP reminder rule not found")
        return False

    # ═══════════════════════════════════════════════════════════════════════
    # 4. Add timezone-aware formatting for reminder display in check-ins
    # ═══════════════════════════════════════════════════════════════════════

    # Find the datetime display in _reminder_list_text
    old_rem_display = '''        dt  = r.get("datetime_iso","")[:16].replace("T"," ")'''

    new_rem_display = '''        dt_iso = r.get("datetime_iso","")
        # Strip timezone offset for display: "2026-05-05T13:00+05:00" → "2026-05-05 13:00"
        if "+" in dt_iso:
            dt = dt_iso[:16].replace("T"," ")
        elif dt_iso.endswith("Z"):
            dt = dt_iso[:-1][:16].replace("T"," ")
        else:
            dt = dt_iso[:16].replace("T"," ")'''

    if old_rem_display in content:
        content = content.replace(old_rem_display, new_rem_display, 1)
        changes += 1
        print("✅ 4/4 Fixed reminder display for timezone-aware format")
    else:
        print("⚠️ Reminder display pattern not found")

    # ═══════════════════════════════════════════════════════════════════════
    # Write back
    # ═══════════════════════════════════════════════════════════════════════
    with open(BOT_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n✅ Patch 20b applied ({changes} changes)")
    print("   Reminders now respect gardener timezone")
    print("   datetime_iso stored with offset: 2026-05-05T13:00+05:00")
    print("   Scheduler compares with timezone awareness")
    print("   SR instructed to always use local time from context")
    return True


if __name__ == "__main__":
    success = patch()
    sys.exit(0 if success else 1)