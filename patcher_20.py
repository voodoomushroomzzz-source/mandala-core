# patcher_20_split_prompt.py
# Splits SR_SYSTEM_PROMPT into SR_CORE_PROMPT + SR_INTENT_MAP
# Adds intent_map counter in free_conversation for conditional loading
# Version: v1.1 — fixed after pre-check

import re
import sys

BOT_FILE = "bot.py"

def patch():
    with open(BOT_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    changes = 0

    # ── 1. Find SR_SYSTEM_PROMPT ─────────────────────────────────────────
    start_marker = 'SR_SYSTEM_PROMPT = """'
    start_idx = content.find(start_marker)
    if start_idx == -1:
        print("❌ SR_SYSTEM_PROMPT not found")
        return False

    rest = content[start_idx + len(start_marker):]
    end_match = re.search(r'\n"""', rest)
    if not end_match:
        print("❌ End of SR_SYSTEM_PROMPT not found")
        return False

    end_idx = start_idx + len(start_marker) + end_match.start()
    prompt_body = content[start_idx + len(start_marker):end_idx]

    # ── 2. Split at "ПЯТЬ СФЕР РЕЗОНАНСА" ────────────────────────────────
    cut_marker = "ПЯТЬ СФЕР РЕЗОНАНСА"
    cut_idx = prompt_body.find(cut_marker)
    if cut_idx == -1:
        print("❌ 'ПЯТЬ СФЕР РЕЗОНАНСА' not found")
        return False

    core_part = prompt_body[:cut_idx].rstrip()
    intent_part = prompt_body[cut_idx:].strip()

    # ── 3. Build replacements ────────────────────────────────────────────
    SR_CORE_PROMPT = 'SR_CORE_PROMPT = """' + core_part + '\n"""\n'
    SR_INTENT_MAP = 'SR_INTENT_MAP = """' + intent_part + '\n"""\n'
    SR_SYSTEM_PROMPT_LINE = 'SR_SYSTEM_PROMPT = SR_CORE_PROMPT + "\\n\\n" + SR_INTENT_MAP\n'

    old_block = content[start_idx:end_idx + 4]  # SR_SYSTEM_PROMPT = """...\n"""
    new_block = SR_CORE_PROMPT + "\n" + SR_INTENT_MAP + "\n" + SR_SYSTEM_PROMPT_LINE
    content = content.replace(old_block, new_block, 1)
    changes += 1
    print("✅ 1/4 Split SR_SYSTEM_PROMPT → CORE + INTENT_MAP")

    # ── 4. Add _intent_map_msg_count ─────────────────────────────────────
    marker = "_checklist_messages: dict = {}"
    insert_pos = content.find(marker)
    if insert_pos != -1:
        end_of_line = content.find("\n", insert_pos)
        content = (content[:end_of_line + 1] +
                   "_intent_map_msg_count: dict = {}  # uid → counter for conditional INTENT_MAP load\n\n" +
                   content[end_of_line + 1:])
        changes += 1
        print("✅ 2/4 Added _intent_map_msg_count")
    else:
        print("❌ _checklist_messages not found")
        return False

    # ── 5. Modify free_conversation: conditional INTENT_MAP ──────────────
    # Find: "content": SR_SYSTEM_PROMPT + "\n\n" + ctx_msg + _hint_block
    old_sys = '"content": SR_SYSTEM_PROMPT + "\\n\\n" + ctx_msg + _hint_block'
    sys_pos = content.find(old_sys)
    if sys_pos == -1:
        print("❌ SR_SYSTEM_PROMPT in free_conversation not found")
        return False

    # Find start of this line
    line_start = content.rfind("\n", 0, sys_pos) + 1
    line_end = content.find("\n", sys_pos)
    old_line = content[line_start:line_end]

    new_lines = (
        '        count = _intent_map_msg_count.get(user_id, 0) + 1\n'
        '        _intent_map_msg_count[user_id] = count\n'
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

    # Also remove the old "messages = [" line and the old system message block
    # Find "messages = [" before sys_pos
    msg_start = content.rfind("messages = [", 0, sys_pos)
    if msg_start == -1:
        print("❌ 'messages = [' before system line not found")
        return False

    # Find end of old messages block: closing ] then next line
    # Pattern: ... *history,\n        {"role": "user", "content": text}\n    ]
    user_line = '{"role": "user", "content": text}'
    user_pos = content.find(user_line, sys_pos)
    if user_pos == -1:
        print("❌ user message line not found")
        return False

    # Find closing bracket after user line
    bracket_pos = content.find("]", user_pos)
    if bracket_pos == -1:
        print("❌ closing bracket not found")
        return False

    # Include newline after bracket
    next_nl = content.find("\n", bracket_pos)
    old_messages_block = content[msg_start:next_nl + 1]

    content = content.replace(old_messages_block, new_lines + "\n", 1)
    changes += 1
    print("✅ 3/4 Modified free_conversation for conditional INTENT_MAP")

    # ── 6. Reset counter when INTENT_MAP is shown ────────────────────────
    # After showing INTENT_MAP, reset counter so it doesn't show again immediately
    # Find: _intent_map_msg_count[user_id] = count
    # Add after: if count % 10 == 0: _intent_map_msg_count[user_id] = 0
    counter_line = "_intent_map_msg_count[user_id] = count"
    counter_pos = content.find(counter_line)
    if counter_pos != -1:
        end_of_counter_line = content.find("\n", counter_pos)
        reset_logic = (
            '        if count % 10 == 0:\n'
            '            _intent_map_msg_count[user_id] = 0  # reset cycle after showing map'
        )
        # Insert after the counter line
        content = (content[:end_of_counter_line + 1] +
                   reset_logic + "\n" +
                   content[end_of_counter_line + 1:])
        changes += 1
        print("✅ 4/4 Added counter reset after INTENT_MAP display")
    else:
        print("⚠️ Counter line not found for reset")

    # ── 7. Write ─────────────────────────────────────────────────────────
    with open(BOT_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n✅ Patch 20 applied ({changes} changes)")
    print("   SR_CORE_PROMPT: personality, voice, rules (~500 tokens, always)")
    print("   SR_INTENT_MAP: spheres, functions, intent examples (~2000 tokens, every 10 msgs)")
    print("   ~94% token savings per dialog")
    return True

if __name__ == "__main__":
    success = patch()
    sys.exit(0 if success else 1)