import json
import os

FILE_PATH = "honeycombs/personal/profile_deep.json"

# Загружаем текущий файл
with open(FILE_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

# Проверяем, есть ли уже rules_of_engagement в discovery_system
if "rules_of_engagement" not in data.get("discovery_system", {}):
    # Добавляем блок правил
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
    # Обновляем версию discovery_system
    data["discovery_system"]["version"] = "v1.1"
    # Обновляем общую версию файла
    data["identity"]["version"] = "v2.7.0"
    # Обновляем дату
    data["identity"]["updated"] = "2026-08-30"
    data["last_updated"] = "2026-08-30"
    # Сохраняем файл
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✅ Блок rules_of_engagement добавлен в discovery_system. Версия обновлена до v2.7.0.")
else:
    print("ℹ️ Блок rules_of_engagement уже существует. Изменения не требуются.")
