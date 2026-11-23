"""Build file-compatible HTML catalogs from Mandala's working files."""
import json
import re
import shutil
from collections import defaultdict
from html import escape
from urllib.parse import quote


LABELS = {
    "active": "Активно", "in_progress": "В работе", "in_development": "В разработке",
    "planning": "Планируется", "planned": "Запланировано", "paused": "На паузе",
    "high": "Высокий", "medium": "Средний", "low": "Низкий", "critical": "Критический",
    "unconfirmed": "Ещё не сверено", "perspective": "Перспектива", "done": "Завершено",
    "cancelled": "Отменено", "todo": "Не начато", "blocked": "Заблокировано",
    "pending": "Ожидает",
}
PRIORITIES = ("critical", "high", "medium", "low")

TEMPLATE = """<!doctype html>
<html lang="ru">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="../../../../assets/mandala.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="../../../../assets/mandala-192.png">
<link rel="manifest" href="../../../../manifest.webmanifest">
<title>__TITLE__ — Мандала</title>
<style>
  * { box-sizing: border-box; }
  body { background: #0d1117; color: #e6edf3; font: 16px/1.55 "Segoe UI", sans-serif; margin: 0; }
  main { max-width: 1080px; margin: auto; padding: 28px 20px 48px; }
  a { color: #84b9ff; } a:hover { color: #b8d8ff; }
  nav, .controls { display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: end; }
  nav { padding-bottom: 16px; border-bottom: 1px solid #30363d; }
  h1 { font-size: clamp(28px, 5vw, 42px); margin: 26px 0 14px; }
  h2 { margin-bottom: 10px; } h3 { margin: 0; font-size: 18px; overflow-wrap: anywhere; }
  label { display: grid; gap: 4px; } input, select { font: inherit; padding: 8px; color: inherit;
    background: #161b22; border: 1px solid #58616e; border-radius: 6px; min-width: 0; max-width: 100%; }
  input { width: min(290px, 85vw); } .grid { display: grid; gap: 12px;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); }
  article, .queue { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 16px; }
  article:target { outline: 2px solid #84b9ff; } .meta { color: #b5c0cf; font-size: 14px; }
  article p { white-space: pre-line; } article p:last-child { margin-bottom: 0; }
  .queue { padding-left: 38px; } .queue li + li { margin-top: 10px; }
  .lanes { display: grid; gap: 12px; align-items: start;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); }
  .lane { padding: 12px; background: #101720; border-radius: 10px; border-top: 3px solid #58616e; }
  .lane[data-group="critical"], .lane[data-group="high"] { border-top-color: #e78476; }
  .lane[data-group="medium"] { border-top-color: #d6ab59; }
  .lane[data-group="low"] { border-top-color: #8aa9dc; }
  .lane > h3 { margin: 0 0 10px; font-size: 16px; }
  .lane article { padding: 0; margin-bottom: 8px; }
  .lane article:last-child { margin-bottom: 0; }
  .lane summary { cursor: pointer; padding: 12px; min-height: 44px; font-weight: 600; overflow-wrap: anywhere; }
  .lane article > details > summary { list-style: none; position: relative; padding-right: 38px; }
  .lane article > details > summary::-webkit-details-marker { display: none; }
  .lane article > details > summary::after { content: '⌄'; position: absolute; right: 12px; top: 12px; transition: transform .15s; }
  .lane article > details[open] > summary::after { transform: rotate(180deg); }
  .lane summary:hover { background: #212c3b; border-radius: 9px; }
  .lane summary time, .lane summary small { display: block; color: #b5c0cf; font-weight: 400; font-size: 13px; }
  .card-body { padding: 12px; border-top: 1px solid #30363d; }
  .lane details[open] > summary { background: #212c3b; border-radius: 9px 9px 0 0; }
  .queue-more { margin-top: 20px; }
  [hidden] { display: none !important; }
</style>
<main>
  <nav aria-label="Разделы Мандалы">
    <a href="../../../../index.html">Главная</a>
    <a href="mandala_graph.html">Карта</a>
    <a href="personal.html">Личные задачи</a>
    <a href="fruits.html">Fruits</a>
    <a href="works.html">Works</a>
    <a href="knowledge.html">Knowledge</a>
  </nav>
  <h1>__TITLE__</h1>
__INTRO__
  <div class="controls">
    <label>Поиск<input type="search" id="search"></label>
    __FILTERS__
  </div>
  <p id="results" class="meta" aria-live="polite"></p>
  <section class="__LAYOUT__" aria-label="Каталог">__CARDS__</section>
__OUTRO__
</main>
<script>
  const cards = [...document.querySelector('[aria-label="Каталог"]').querySelectorAll("article")];
  const search = document.getElementById("search");
  const filters = [...document.querySelectorAll("select[data-field]")];
  function update() {
    const query = search.value.trim().toLocaleLowerCase("ru");
    let count = 0;
    for (const card of cards) {
      const matches = filters.every(filter => !filter.value || card.dataset[filter.dataset.field] === filter.value);
      card.hidden = !matches || !card.textContent.toLocaleLowerCase("ru").includes(query);
      if (!card.hidden) count++;
    }
    for (const lane of document.querySelectorAll(".lane")) {
      lane.hidden = !lane.querySelector("article:not([hidden])");
    }
    document.getElementById("results").textContent = count ? "Показано: " + count + " из " + cards.length : "Ничего не найдено";
  }
  search.addEventListener("input", update);
  for (const filter of filters) filter.addEventListener("change", update);
  update();
  function revealLinkedCard() {
    try {
      const card = document.getElementById(decodeURIComponent(location.hash.slice(1)));
      const details = card?.querySelector("details");
      if (details) {
        if (card.hidden) {
          search.value = "";
          for (const filter of filters) filter.value = "";
          update();
        }
        details.open = true;
        card.scrollIntoView({ block: "nearest" });
      }
    } catch (error) {
      if (!(error instanceof URIError)) throw error;
    }
  }
  addEventListener("hashchange", revealLinkedCard);
  revealLinkedCard();
</script>
</html>
"""


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def label(value):
    return LABELS.get(value, value)


def link(page, key, title, separator="#"):
    return f'<a href="{page}{separator}{quote(key, safe="")}">{escape(title)}</a>'


def source_link(path):
    url = "https://github.com/voodoomushroomzzz-source/mandala-core/blob/main/" + quote(path)
    return f'<a href="{url}">Исходник</a>'


def render_page(path, title, entries, fields=(), intro="", grouping=None, outro=""):
    filters = []
    for field, caption in fields:
        values = sorted({entry.get(field) for entry in entries if entry.get(field)})
        options = "".join(f'<option value="{escape(v)}">{escape(label(v))}</option>' for v in values)
        filters.append(f'<label>{caption}<select data-field="{field}"><option value="">Все</option>{options}</select></label>')

    cards = defaultdict(list)
    for entry in entries:
        attrs = "".join(f' data-{field}="{escape(entry.get(field) or "")}"' for field, _ in fields)
        body = (f'<div class="meta">{escape(entry["meta"])}</div><p>{escape(entry["description"])}</p>'
                f'{entry["details"]}<p>{" · ".join(entry["links"])}</p>')
        name = escape(entry["name"])
        if entry.get("reading_url"):
            name = f'<a href="{escape(entry["reading_url"])}">{name}</a>'
        if grouping:
            field, _ = grouping
            group = entry.get(field) or "Без раздела"
            heading = f"<summary>{name}{entry.get('summary_detail', '')}</summary>"
            content = f'<details>{heading}<div class="card-body">{body}</div></details>'
        else:
            group = ""
            content = f"<h3>{name}</h3>{body}"
        cards[group].append(f'<article id="{escape(entry["id"])}"{attrs}>{content}</article>')
    layout = "grid"
    content = "\n".join(cards[""]) if not grouping else ""
    if grouping:
        layout = "lanes"
        _, order = grouping
        groups = [group for group in order if group in cards]
        groups += sorted(set(cards) - set(groups))
        content = "\n".join(
            f'<section class="lane" data-group="{escape(group)}"><h3>{escape(label(group))}</h3>'
            f'{"".join(cards[group])}</section>' for group in groups
        )
    sections = {"TITLE": escape(title), "FILTERS": "".join(filters), "CARDS": content,
                "INTRO": intro, "LAYOUT": layout, "OUTRO": outro}
    page = re.sub(r"__(TITLE|FILTERS|CARDS|INTRO|LAYOUT|OUTRO)__", lambda match: sections[match[1]], TEMPLATE)
    path.write_text(page, encoding="utf-8", newline="\n")


def render_queue(root, works_by_file):
    board = (root / "honeycombs/works/management_taskboard.md").read_text(encoding="utf-8")
    sections = re.split(r"(?m)^## ", board)
    rendered = {}
    for title in ("Чем заняться сейчас", "На паузе", "Перспектива и отложенные решения"):
        section = next((text for text in sections if text.startswith(f"{title}\n")), "")
        items = []
        for line in section.splitlines():
            if not line.startswith("|") or not re.search(r"\w", line):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if cells[0] in {"Очередь", "Работа"}:
                continue
            if cells[0].isdigit():
                cells = cells[1:]
            row = " · ".join(cells).replace("**", "").replace("`", "")
            parts = re.split(r"\[([^\]]+)\]\(([^)]+)\)", row)
            text = escape(parts[0])
            for i in range(1, len(parts), 3):
                work_id = works_by_file.get(parts[i + 1])
                text += (link("works.html", work_id, parts[i]) if work_id else escape(parts[i])) + escape(parts[i + 2])
            items.append(f"<li>{text}</li>")
        if items:
            rendered[title] = f'<ul class="queue">{"".join(items)}</ul>'
    now = rendered.pop("Чем заняться сейчас", "")
    intro = (f"<h2>Сейчас</h2>{now}" if now else "") + "<h2>Доска по приоритетам</h2>"
    outro = "".join(f'<details class="queue-more"><summary>{title}</summary>{items}</details>'
                    for title, items in rendered.items())
    return intro, outro


def personal_entries(root, movement):
    """Read only explicitly agreed personal tasks, resolving references at build time."""
    directions = {d["id"]: d["name"] for d in movement["directions"]}
    entries = []
    ids = set()
    for task in load(root / "honeycombs/personal/personal_tasks.json")["tasks"]:
        key = task["id"]
        if key in ids:
            raise ValueError(f"Duplicate personal task: {key}")
        ids.add(key)
        path = "honeycombs/personal/personal_tasks.json"
        if "source_file" in task:
            path = task["source_file"]
            resolved = (root / path).resolve()
            if not resolved.is_relative_to(root.resolve()):
                raise ValueError("Personal task source must stay inside repository")
            data = load(resolved)
            if task.get("source_collection"):
                candidates = data
                for part in task["source_collection"].strip("/").split("/"):
                    candidates = candidates[part.replace("~1", "/").replace("~0", "~")]
                if not isinstance(candidates, list):
                    raise ValueError(f"Task collection is not a list: {key}")
            else:
                candidates = data.get("taskboard", {}).get("tasks", []) if "taskboard" in data else [data]
            matches = [t for t in candidates if t.get("id") == task["record_id"]]
            if len(matches) != 1:
                raise ValueError(f"Missing or ambiguous task reference: {key}")
            record = matches[0]
            direction = task.get("direction") or ("work" if "taskboard" in data else "")
        else:
            record = task
            direction = task["direction"]
            if direction not in directions:
                raise ValueError(f"Unknown personal direction: {direction}")
        priority = (record.get("priority") or "").lower() or None
        if task.get("priority_confirmed") is False:
            priority = None
        due = record.get("deadline")
        details = []
        if task.get("context"):
            details.append(f'<p>{escape(task["context"])}</p>')
        for field, caption in (("next_step", "Следующий шаг"), ("pause_reason", "Причина паузы"), ("return_condition", "Условие возврата")):
            if record.get(field):
                details.append(f'<p>{caption}: {escape(record[field])}</p>')
        summary_detail = f'<time datetime="{escape(due)}">{escape(due)}</time>' if due else '<small>Срок не согласован</small>'
        if due and task.get("deadline_confirmed") is False:
            summary_detail = f'<small>Прежний срок {escape(due)} не подтверждён</small>'
        entries.append({
            "id": key, "name": record.get("name") or record["title"],
            "description": record.get("description", ""), "status": record["status"],
            "priority": priority, "group": directions.get(direction, "Мандала"),
            "now": task.get("now", record["status"] in {"active", "in_progress", "todo", "pending", "blocked"}),
            "meta": label(record["status"]), "details": "".join(details),
            "summary_detail": summary_detail,
            "links": [source_link(path)],
        })
    return entries


def render_everyday(root):
    """Keep short household lists separate from the personal priority board."""
    path = root / "honeycombs/personal/everyday_tasks.json"
    if not path.exists():
        return ""
    data = load(path)
    categories = data.get("categories", {"shopping": "Покупки", "errands": "Дела"})
    groups = {key: (title, []) for key, title in categories.items()}
    closed = []
    ids = set()
    for task in data["tasks"]:
        key = task["id"]
        if key in ids:
            raise ValueError(f"Duplicate everyday task: {key}")
        ids.add(key)
        if task["category"] not in groups:
            raise ValueError(f"Unknown everyday category: {task['category']}")
        if task["status"] not in {"active", "done", "cancelled"}:
            raise ValueError(f"Unknown everyday status: {task['status']}")
        due = task.get("deadline")
        due_html = ""
        if due:
            from datetime import date
            display = date.fromisoformat(due).strftime("%d.%m.%Y")
            due_html = f' <time class="meta" datetime="{escape(due)}">— {display}</time>'
        item = f'<li id="{escape(key, quote=True)}">{escape(task["name"])}{due_html}</li>'
        if task["status"] == "active":
            groups[task["category"]][1].append(item)
        else:
            closed.append(f'<li id="{escape(key, quote=True)}">{escape(task["name"])}'
                          f' <span class="meta">— {escape(label(task["status"]))}</span></li>')
    html = '<section id="everyday" aria-labelledby="everyday-title"><h2 id="everyday-title">Повседневное</h2>'
    html += '<p class="meta">Покупки и небольшие бытовые дела.</p><div class="grid">'
    for title, items in groups.values():
        html += f'<article><h3>{escape(title)}</h3>'
        html += ('<ul>' + ''.join(items) + '</ul>') if items else '<p class="meta">Список пуст.</p>'
        html += '</article>'
    html += '</div>'
    if closed:
        html += '<details class="queue-more"><summary>Завершённые и отменённые</summary><ul>' + ''.join(closed) + '</ul></details>'
    return html + '</section>'


def build_personal(root, output):
    movement = load(root / "honeycombs/personal/current_movement.json")
    entries = personal_entries(root, movement)
    rows = []
    for d in movement["directions"]:
        context = ''.join(f'<p><strong>{caption}:</strong> {escape(d[field])}</p>'
                          for field, caption in (("goal", "Цель"), ("next_step", "Следующий шаг"),
                                                 ("notes", "Контекст")) if d.get(field))
        rows.append(f'<article><h3>{escape(d["name"])}</h3><p>{escape(label(d["state"]))}</p>'
                    f'{context}'
                    f'<p class="meta">Источники прочитаны: {escape(d.get("last_sync_at") or "ещё не отмечено")}<br>'
                    f'Планы подтверждены: {escape(d.get("last_confirmed_at") or "ещё не сверяли")}</p></article>')
    focus = movement.get("personal_focus", {})
    intro = ''
    if focus.get("focus"):
        intro = '<section class="queue"><h2>Личный фокус</h2>'
        intro += f'<p>{escape(focus["focus"])}</p>'
        for field in ("target_note", "balance"):
            if focus.get(field):
                intro += f'<p>{escape(focus[field])}</p>'
        intro += '</section>'
    intro += render_everyday(root)
    intro += '<h2>Сейчас</h2>'
    active = [e for e in entries if e["now"]]
    intro += ('<ul class="queue">' + ''.join(f'<li>{link("personal.html", e["id"], e["name"])}</li>' for e in active) + '</ul>') if active else '<p>Согласованных текущих действий пока нет.</p>'
    intro += '<h2>Доска по приоритетам</h2>'
    if not entries:
        intro += '<p>Личный фронт ещё предстоит сверить. Старые планы направлений не стали текущими задачами автоматически.</p>'
    outro = '<h2>Личные направления</h2><section class="grid">' + ''.join(rows) + '</section>'
    outro += '<p>' + source_link('honeycombs/personal/personal_taskboard.md') + ' · ' + source_link('honeycombs/personal/current_movement.json') + '</p>'
    render_page(output / "personal.html", "Личные задачи", entries,
                (("status", "Статус"), ("group", "Направление")), intro,
                grouping=("priority", PRIORITIES), outro=outro)


def build_catalogs(root, site, output, graph):
    if site != root:
        (site / "index.html").write_text((root / "index.html").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        shutil.copytree(root / "assets", site / "assets", dirs_exist_ok=True)
        shutil.copyfile(root / "manifest.webmanifest", site / "manifest.webmanifest")

    build_personal(root, output)

    nodes = {node["id"]: node for node in graph["nodes"]}
    work_cards = {}
    for node in graph["nodes"]:
        if node["type"] == "work":
            work_cards[node["id"]] = load(root / node["path"])
    relations = defaultdict(list)
    for edge in graph["edges"]:
        if edge["type"] in {"sub_work", "product_work"}:
            relations[edge["from"]].append(edge["to"])

    works = []
    for work_id, card in work_cards.items():
        graph_link = link("mandala_graph.html", work_id, "На карте", separator="?node=")
        children = [link("works.html", child, work_cards[child]["name"]) for child in relations[work_id]]
        due = card.get("deadline")
        works.append({
            "id": work_id, "name": card["name"], "description": card["description"],
            "status": card["status"], "priority": card["priority"], "group": card.get("workstream"),
            "deadline": "Есть срок" if due else "Без срока",
            "summary_detail": f'<time datetime="{escape(due)}">{escape(due)}</time>' if due else "<small>Без дедлайна</small>",
            "meta": " · ".join(filter(None, (label(card["status"]), card.get("workstream")))),
            "details": f'<p>Дочерние работы: {" · ".join(children)}</p>' if children else "",
            "links": [graph_link, source_link(nodes[work_id]["path"])],
        })
    works_by_file = {node_path.rsplit("/", 1)[-1]: work_id for work_id in work_cards if (node_path := nodes[work_id]["path"])}
    intro, outro = render_queue(root, works_by_file)
    render_page(output / "works.html", "Works", works,
                (("status", "Статус"), ("group", "Блок"), ("deadline", "Дедлайн")),
                intro, grouping=("priority", PRIORITIES), outro=outro)

    knowledge_root = root / "honeycombs/knowledge"
    from mge.knowledge import load_knowledge
    from mge.reader import build_material
    collection = load_knowledge(knowledge_root)
    knowledge = []
    for material in collection["materials"]:
        key = material["graph_id"]
        reading_url = material["reading_url"]
        links = [source_link(material["path"])]
        if reading_url:
            build_material(output, material)
            links.insert(0, f'<a href="{reading_url}">Читать полностью →</a>')
        if key in nodes:
            links.insert(0, link("mandala_graph.html", key, "На карте", separator="?node="))
        if material["id"] == "ai_tools":
            category = next(m for m in collection["materials"] if m["category"])
            links.insert(0, link("knowledge.html", category["graph_id"], "Перейти к категориям"))
        meta = " · ".join(text for text in (
            f'Версия {material["version"]}' if material.get("version") else "",
            f'Обновлено {material["updated"]}' if material.get("updated") else "",
            f'Проверено {material["verification"]["checked_at"]}' if material["verification"].get("checked_at") else "",
        ) if text)
        knowledge.append({"id": key, "name": material["title"], "description": material["summary"],
                          "group": material["area_title"], "meta": meta, "details": "",
                          "links": links, "reading_url": reading_url})
    render_page(output / "knowledge.html", "Knowledge", knowledge, (("group", "Сфера"),),
                grouping=("group", collection["areas"]))

    products = []
    for fruit in load(root / "honeycombs/fruits/index.json")["fruits"]:
        fruit_id = fruit["id"]
        details = []
        for work_id in relations[fruit_id]:
            card = work_cards[work_id]
            parent = next((n for n, children in relations.items() if work_id in children and n in work_cards), "")
            plan = work_cards[parent] if parent else card
            stages = plan.get("milestones") or plan.get("phases", {})
            titles = [stage.get("name") for stage in (stages.values() if isinstance(stages, dict) else stages) if isinstance(stage, dict) and stage.get("name")]
            names = link("works.html", work_id, card["name"])
            if parent:
                names += " · Проект: " + link("works.html", parent, plan["name"])
            details.append(f'<p>{names}<br>Приоритет работы: {escape(label(card["priority"]))}</p>')
            if titles:
                details.append(f'<details><summary>Вехи</summary><ul>{"".join(f"<li>{escape(title)}</li>" for title in titles)}</ul></details>')
        status = fruit.get("status", "")
        direction = fruit.get("direction_status")
        meta = " · ".join(filter(None, (label(status), fruit.get("version"))))
        if direction:
            meta = f"Серверный прототип: {meta} · Локальное направление: {label(direction)}"
        products.append({
            "id": fruit_id, "name": fruit["name"], "description": fruit["short_description"],
            "status": status, "meta": meta, "details": "".join(details),
            "links": [link("mandala_graph.html", fruit_id, "На карте", separator="?node=")]
            + ([source_link(fruit["path"])] if fruit.get("path") else []),
        })
    render_page(output / "fruits.html", "Fruits", products, (("status", "Статус продукта"),))
