import json
import re

FILE = "honeycombs/personal/profile_deep.json"

# Читаем файл как текст для точного удаления дубликата
with open(FILE, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Находим и удаляем второй дублирующийся блок discovery_system (в конце файла)
# Ищем последнее вхождение '"discovery_system"' и удаляем всё после первого блока
# Стратегия: находим позицию второго "discovery_system" (последнего)
last_discovery_start = content.rfind('"discovery_system"')
if last_discovery_start != -1:
    # Находим начало этого дублирующего блока (ищем предыдущую открывающую скобку)
    dup_start = content.rfind('{', 0, last_discovery_start)
    if dup_start != -1:
        # Находим конец файла
        dup_end = content.rfind('}')
        if dup_end != -1:
            # Обрезаем всё от dup_start до конца
            content = content[:dup_start]
            # Убираем лишнюю запятую перед закрывающей скобкой, если есть
            content = re.sub(r',\s*}', '}', content)

# 2. Загружаем исправленный JSON
try:
    data = json.loads(content)
except json.JSONDecodeError as e:
    print(f"❌ Ошибка в JSON после удаления дубликата: {e}")
    print("Проверьте файл вручную")
    exit(1)

# 3. Добавляем информацию о детях в блок bio
if "bio" not in data:
    data["bio"] = {}

# Проверяем, есть ли уже блок children, чтобы не дублировать
if "children" not in data["bio"]:
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
    print("✅ Информация о детях добавлена")
else:
    print("ℹ️ Блок children уже существует, пропускаем")

# 4. Обновляем дату
data["last_updated"] = "2026-08-30"

# 5. Сохраняем файл
with open(FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ Файл исправлен: дубликат удалён, информация о детях добавлена.")
