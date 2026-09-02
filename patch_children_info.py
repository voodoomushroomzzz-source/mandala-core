import json

FILE = "honeycombs/personal/deep_profile.json"

with open(FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

# Добавляем/обновляем информацию о детях в identity
if "section_A_philosophy" not in data:
    data["section_A_philosophy"] = {}
if "identity" not in data["section_A_philosophy"]:
    data["section_A_philosophy"]["identity"] = {}

data["section_A_philosophy"]["identity"]["children"] = [
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
data["section_A_philosophy"]["last_updated"] = "2026-08-30"
if "section_D_personal_context" in data:
    data["section_D_personal_context"]["last_updated"] = "2026-08-30"

with open(FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ Информация о детях добавлена в profile_deep.json (Доброслав и Борис)")
