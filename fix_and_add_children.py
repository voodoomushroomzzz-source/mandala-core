import json
import re

FILE = "honeycombs/personal/profile_deep.json"

# 1. Читаем файл как текст
with open(FILE, "r", encoding="utf-8") as f:
    content = f.read()

# 2. Находим позицию дублирующего блока
# Ищем второй "discovery_system" после основного содержимого
dup_start = content.rfind('"discovery_system"')
if dup_start != -1:
    # Ищем начало этого блока (последнее вхождение)
    last_brace_start = content.rfind('{', 0, dup_start)
    if last_brace_start != -1:
        # Обрезаем всё от последней открывающей скобки перед дубликатом
        content = content[:last_brace_start]
        # Удаляем лишнюю запятую перед закрывающей скобкой, если есть
        content = re.sub(r',\s*}', '}', content)

# 3. Загружаем исправленный JSON
try:
    data = json.loads(content)
except json.JSONDecodeError as e:
    print(f"❌ Ошибка в JSON: {e}")
    print("Проверьте файл вручную")
    exit(1)

# 4. Добавляем информацию о детях в блок bio
if "bio" not in data:
    data["bio"] = {}
data["bio"]["children"] = [
    {
        "name": "Доброслав",
        "age": 8,
        "class": "2 класс",
        "location": "Владимир (в одном городе, часто приезжает ко мне)"
    },
    {
        "name": "Борис",
        "age": 7,
        "class": "1 класс (идёт в этом году)",
        "location": "Нижний Новгород (поеду с ним в школу)"
    }
]

# 5. Обновляем дату
data["last_updated"] = "2026-08-30"

# 6. Сохраняем файл
with open(FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ Исправления применены. Информация о детях добавлена.")
