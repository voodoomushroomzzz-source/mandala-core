# patcher_20_hotfix_v3.py
# Fix: change indentation from 8 to 4 spaces for the whole new block
import sys

BOT_FILE = "bot.py"

def patch():
    with open(BOT_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # The entire new block (lines 5493-5505) — replace 8-space indent with 4-space
    old_block = (
        '        count = _intent_map_msg_count.get(user_id, 0) + 1\n'
        '        _intent_map_msg_count[user_id] = count\n'
        '        if count % 10 == 0:\n'
        '            _intent_map_msg_count[user_id] = 0  # reset cycle after showing map\n'
        '        system_content = SR_CORE_PROMPT + ("\\n\\n" + SR_INTENT_MAP) if (count % 10 == 0) else SR_CORE_PROMPT\n'
        '        messages = [\n'
        '            {\n'
        '                "role": "system",\n'
        '                "content": system_content + "\\n\\n" + ctx_msg + _hint_block\n'
        '            },\n'
        '            *history,\n'
        '            {"role": "user", "content": text}\n'
        '        ]'
    )

    new_block = (
        '    count = _intent_map_msg_count.get(user_id, 0) + 1\n'
        '    _intent_map_msg_count[user_id] = count\n'
        '    if count % 10 == 0:\n'
        '        _intent_map_msg_count[user_id] = 0  # reset cycle after showing map\n'
        '    system_content = SR_CORE_PROMPT + ("\\n\\n" + SR_INTENT_MAP) if (count % 10 == 0) else SR_CORE_PROMPT\n'
        '    messages = [\n'
        '        {\n'
        '            "role": "system",\n'
        '            "content": system_content + "\\n\\n" + ctx_msg + _hint_block\n'
        '        },\n'
        '        *history,\n'
        '        {"role": "user", "content": text}\n'
        '    ]'
    )

    if old_block in content:
        content = content.replace(old_block, new_block, 1)
        with open(BOT_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        print("✅ Indentation fixed: 8 → 4 spaces")
        return True
    else:
        print("❌ Old block not found")
        # Debug: show what's around the area
        idx = content.find("count = _intent_map_msg_count")
        if idx != -1:
            print("Found at", idx)
            print(repr(content[idx:idx+500]))
        return False

if __name__ == "__main__":
    sys.exit(0 if patch() else 1)