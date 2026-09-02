import json
import os
import re

FILE_PATH = "honeycombs/personal/profile_deep.json"

# 1. Читаем файл и находим позицию последнего "discovery_system"
with open(FILE_PATH, "r", encoding="utf-8") as f:
    content = f.read()

# Находим все вхождения "discovery_system"
pattern = r'"discovery_system"\s*:\s*\{'
matches = list(re.finditer(pattern, content))

if len(matches) > 1:
    # Находим позицию второго вхождения
    second_start = matches[1].start()
    # Ищем соответствующую закрывающую скобку после второго вхождения
    brace_count = 0
    pos = second_start
    while pos < len(content):
        if content[pos] == '{':
            brace_count += 1
        elif content[pos] == '}':
            brace_count -= 1
            if brace_count == 0:
                # Нашли конец второго блока
                end_pos = pos + 1
                # Удаляем второй блок, включая запятую перед ним, если есть
                # Ищем запятую перед вторым блоком
                comma_pos = content.rfind(',', 0, second_start)
                if comma_pos != -1 and content[comma_pos+1:second_start].strip() == '':
                    # Удаляем запятую и весь второй блок
                    content = content[:comma_pos] + content[second_start:end_pos]
                    # Удаляем возможную запятую после блока
                    # Ищем запятую после end_pos
                    if end_pos < len(content) and content[end_pos] == ',':
                        content = content[:end_pos] + content[end_pos+1:]
                else:
                    content = content[:second_start] + content[end_pos:]
                break
        pos += 1

# 2. Загружаем исправленный JSON и добавляем rules_of_engagement
try:
    data = json.loads(content)
except json.JSONDecodeError as e:
    print(f"❌ Ошибка при загрузке JSON: {e}")
    exit(1)

# Добавляем rules_of_engagement, если их нет
if "rules_of_engagement" not in data.get("discovery_system", {}):
    data["discovery_system"]["rules_of_engagement"] = {
        "description": "Правила работы с синтезом и интеграции данных.",
        "data_integration": {
            "principle": "Данные от бота (интересы, медиа, повседневные паттерны) являются обязательной основой для углубления синтеза. Они не заменяют философский слой, но укореняют его в реальной жизни.",
            "usage": [
                "При выборе новых вопросов для синтеза опираться на актуальные интересы и медиа-предпочтения Садовника.",
                "При анализе ответов сверять их с устойчивыми паттернами поведения и интересов.",
                "При обновлении синтеза добавлять контекст из повседневной жизни, зафиксированный ботом.",
                "При предложении новых векторов использовать данные о частотности интересов для определения естественных направлений углубления."
            ]
        }
    }
    data["discovery_system"]["version"] = "v1.1"
    data["identity"]["version"] = "v2.7.0"
    data["identity"]["updated"] = "2026-08-30"
    data["last_updated"] = "2026-08-30"
    print("✅ Добавлен rules_of_engagement и обновлена версия.")
else:
    print("ℹ️ rules_of_engagement уже существует.")

# 3. Сохраняем файл
with open(FILE_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ Файл исправлен и обновлён.")
