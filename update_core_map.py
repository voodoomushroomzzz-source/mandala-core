import json

# 1. Обновляем core_map/index.json — добавляем knowledge в список other_honeycombs
with open('honeycombs/core_map/index.json', 'r', encoding='utf-8') as f:
    core_map = json.load(f)

# Добавляем knowledge в other_honeycombs.list, если ещё нет
other = core_map['honeycombs']['other_honeycombs']
if 'knowledge' not in other['list']:
    # Вставляем перед analytics (алфавитный порядок)
    # Создаём новый список: вставляем knowledge перед analytics
    new_list = []
    inserted = False
    for item in other['list']:
        if item == 'analytics' and not inserted:
            new_list.append('knowledge')
            inserted = True
        new_list.append(item)
    if not inserted:
        new_list.append('knowledge')
    other['list'] = new_list

# Обновляем версию и дату
core_map['identity']['version'] = 'v3.7.1'
core_map['identity']['updated'] = '2026-07-05'

with open('honeycombs/core_map/index.json', 'w', encoding='utf-8') as f:
    json.dump(core_map, f, indent=2, ensure_ascii=False)

print('✅ core_map/index.json updated')

# 2. Обновляем core_map/honeycombs.json — добавляем детальное описание knowledge
with open('honeycombs/core_map/honeycombs.json', 'r', encoding='utf-8') as f:
    honeycombs = json.load(f)

# Добавляем запись о knowledge
honeycombs['honeycombs']['knowledge'] = {
    "description": "Knowledge base — structured curated information: tools, references, guides, and external resources.",
    "path": "honeycombs/knowledge/",
    "index": "honeycombs/knowledge/index.json",
    "status": "active",
    "priority": "medium",
    "tags": ["knowledge", "resources", "curated"]
}

# Обновляем мета-данные
honeycombs['identity']['version'] = 'v1.1.0'
honeycombs['identity']['updated'] = '2026-07-05'
honeycombs['metrics']['total_honeycombs'] = len(honeycombs['honeycombs'])

with open('honeycombs/core_map/honeycombs.json', 'w', encoding='utf-8') as f:
    json.dump(honeycombs, f, indent=2, ensure_ascii=False)

print('✅ core_map/honeycombs.json updated')
print('✅ Knowledge honeycomb registered in core_map')
