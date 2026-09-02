import json

FILE = "honeycombs/personal/profile_deep.json"

with open(FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

# Добавляем информацию о детях в блок bio
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

# Обновляем дату
data["last_updated"] = "2026-08-30"

with open(FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ Информация о детях добавлена в profile_deep.json")
