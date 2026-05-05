# patcher_20_hotfix_v2.py
# Fix: first line of counter block has 12 spaces instead of 8
import sys

BOT_FILE = "bot.py"

def patch():
    with open(BOT_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    old = '            count = _intent_map_msg_count.get(user_id, 0) + 1\n        _intent_map_msg_count[user_id] = count\n        if count % 10 == 0:\n            _intent_map_msg_count[user_id] = 0  # reset cycle after showing map\n        system_content = SR_CORE_PROMPT + ("\\n\\n" + SR_INTENT_MAP) if (count % 10 == 0) else SR_CORE_PROMPT'
    
    new = '        count = _intent_map_msg_count.get(user_id, 0) + 1\n        _intent_map_msg_count[user_id] = count\n        if count % 10 == 0:\n            _intent_map_msg_count[user_id] = 0  # reset cycle after showing map\n        system_content = SR_CORE_PROMPT + ("\\n\\n" + SR_INTENT_MAP) if (count % 10 == 0) else SR_CORE_PROMPT'

    if old in content:
        content = content.replace(old, new, 1)
        with open(BOT_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        print("✅ Indentation fixed")
        return True
    else:
        print("❌ Pattern not found")
        return False

if __name__ == "__main__":
    sys.exit(0 if patch() else 1)