# patcher_20b_interest_decay.py
# Auto-removes stale interests from living memory
# Confirmed interests expire after 30 days, mentioned after 14
# Version: v1.0

import sys

BOT_FILE = "bot.py"

def patch():
    with open(BOT_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the interests update block in _generate_synthesis
    old = '''        # Update interests
        interests = mem.setdefault("interests", {"confirmed": [], "mentioned": []})
        for i in confirmed:
            if i and i not in interests["confirmed"]:
                interests["confirmed"].append(i)
        interests["confirmed"] = interests["confirmed"][-20:]
        for i in mentioned:
            if i and i not in interests["mentioned"] and i not in interests["confirmed"]:
                interests["mentioned"].append(i)
        interests["mentioned"] = interests["mentioned"][-20:]
        interests["updated"] = _today()'''

    new = '''        # Decay stale interests before adding new ones
        interests = mem.setdefault("interests", {"confirmed": [], "mentioned": []})
        last_updated = interests.get("updated", "")
        if last_updated:
            try:
                from datetime import datetime as _dt_decay
                last_date = _dt_decay.strptime(last_updated, "%Y-%m-%d")
                days_since = (_dt_decay.now() - last_date).days
                if days_since >= 30:
                    interests["confirmed"] = []
                if days_since >= 14:
                    interests["mentioned"] = []
            except Exception:
                pass  # If date parsing fails, keep interests as-is

        # Update confirmed interests
        for i in confirmed:
            if i and i not in interests["confirmed"]:
                interests["confirmed"].append(i)
        interests["confirmed"] = interests["confirmed"][-20:]

        # Update mentioned interests
        for i in mentioned:
            if i and i not in interests["mentioned"] and i not in interests["confirmed"]:
                interests["mentioned"].append(i)
        interests["mentioned"] = interests["mentioned"][-20:]
        interests["updated"] = _today()'''

    if old in content:
        content = content.replace(old, new, 1)
        with open(BOT_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        print("✅ Interest decay added: confirmed 30d, mentioned 14d")
        return True
    else:
        print("❌ Pattern not found")
        return False

if __name__ == "__main__":
    sys.exit(0 if patch() else 1)