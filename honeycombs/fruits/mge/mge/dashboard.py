"""Build file-compatible HTML catalogs from Mandala's working files."""
import json
import re
from collections import defaultdict
from html import escape
from urllib.parse import quote


LABELS = {
    "active": "Активно", "in_progress": "В работе", "in_development": "В разработке",
    "planning": "Планируется", "planned": "Запланировано", "paused": "На паузе",
    "high": "Высокий", "medium": "Средний", "low": "Низкий", "critical": "Критический",
}
PRIORITIES = ("critical", "high", "medium", "low")
KNOWLEDGE_AREAS = {
    "system_design_primer": "Архитектура и модели",
    "soup_finetuning": "Архитектура и модели",
    "product_audit_framework": "Продукт и запуск",
    "startup_legal_docs_guide": "Продукт и запуск",
    "mandala_brochure": "Мандала и взаимодействие",
    "consent_autonomy_audit": "Мандала и взаимодействие",
    "deep_questions_for_getting_to_know_someone": "Мандала и взаимодействие",
    "ai_tools": "ИИ-инструменты",
}
KNOWLEDGE_AREA_ORDER = ("Архитектура и модели", "Продукт и запуск", "Мандала и взаимодействие", "ИИ-инструменты")

TEMPLATE = """<!doctype html>
<html lang="ru">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
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
    <a href="works.html">Работы</a>
    <a href="knowledge.html">Знания</a>
    <a href="fruits.html">Продукты</a>
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
  const cards = [...document.querySelectorAll("article")];
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


def build_catalogs(root, site, output, graph):
    for name in ("index.html", "engineer-chat.html"):
        if site != root:
            (site / name).write_text((root / name).read_text(encoding="utf-8"), encoding="utf-8", newline="\n")

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
    render_page(output / "works.html", "Работы", works,
                (("status", "Статус"), ("group", "Блок"), ("deadline", "Дедлайн")),
                intro, grouping=("priority", PRIORITIES), outro=outro)

    knowledge_root = root / "honeycombs/knowledge"
    resources = load(knowledge_root / "index.json")["contents"]
    categories = load(knowledge_root / "ai_tools/index.json")["categories"]
    knowledge = []
    for items, folder in ((resources, ""), (categories, "ai_tools/")):
        for item in items:
            group = "ИИ-инструменты" if folder else KNOWLEDGE_AREAS.get(item["id"], "Другие материалы")
            key = "K-" + item["id"] if not folder else "tool-" + item["id"]
            verified = item.get("last_verified")
            links = [source_link("honeycombs/knowledge/" + folder + item["file"])]
            if key in nodes:
                links.insert(0, link("mandala_graph.html", key, "На карте", separator="?node="))
            if item["id"] == "ai_tools":
                links.insert(0, link("knowledge.html", "tool-" + categories[0]["id"], "Перейти к категориям"))
            knowledge.append({
                "id": key, "name": item["name"], "description": item["description"], "group": group,
                "meta": f"Проверено {verified}" if verified else "", "details": "", "links": links,
            })
    render_page(output / "knowledge.html", "База знаний", knowledge, (("group", "Сфера"),),
                grouping=("group", KNOWLEDGE_AREA_ORDER))

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
    render_page(output / "fruits.html", "Продукты", products, (("status", "Статус продукта"),))
