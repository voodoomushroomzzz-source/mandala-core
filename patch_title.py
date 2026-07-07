import json
import re

file_path = "honeycombs/roadmaps/active/RM-014_operational_transition.json"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Находим блок core_resume_ai_ops
start = content.find('"core_resume_ai_ops"')
if start == -1:
    print("ERROR: core_resume_ai_ops block not found")
    exit(1)

# Находим конец блока
brace_count = 0
in_block = False
end = start
for i in range(start, len(content)):
    if content[i] == '{' and not in_block:
        in_block = True
        brace_count += 1
    elif in_block:
        if content[i] == '{':
            brace_count += 1
        elif content[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i + 1
                break

if end == start:
    print("ERROR: Could not find end of core_resume_ai_ops block")
    exit(1)

# Заменяем только заголовок
old_title = '"title": "Операционный директор / AI Operations Manager"'
new_title = '"title": "Операционный менеджер / AI Operations Manager"'

if old_title not in content[start:end]:
    print("WARNING: Old title not found, trying alternative...")
    # Проверяем возможный альтернативный вариант
    old_title_alt = '"title": "Операционный менеджер / AI Operations Manager"'
    if old_title_alt in content[start:end]:
        print("Title already correct, no changes needed")
        exit(0)
    else:
        print("ERROR: Could not find title to replace")
        exit(1)

# Заменяем в полном контенте
new_content = content.replace(old_title, new_title)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✅ Title updated successfully: Операционный менеджер / AI Operations Manager")
