"""Render the public command descriptions from the shared SR instructions."""

from html import escape


def build_commands(root, destination, home=None):
    source = root / "honeycombs/instructions/core/mandala_commands.md"
    _, start, after = source.read_text(encoding="utf-8").partition("<!-- commands:start -->")
    table, end, _ = after.partition("<!-- commands:end -->")
    rows = table.strip().splitlines()
    if not start or not end or rows[:2] != ["| Команда | Что делает |", "| --- | --- |"] or len(rows) < 3:
        raise ValueError(f"Invalid public command table in {source}")
    cards = []
    for row in rows[2:]:
        cells = row.split("|")
        if len(cells) != 4 or cells[0] or cells[-1] or not all(cell.strip() for cell in cells[1:3]):
            raise ValueError(f"Invalid command row in {source}: {row}")
        name, description = (escape(cell.strip()) for cell in cells[1:3])
        cards.append(f"<div><dt>{name}</dt><dd>{description}</dd></div>")

    navigation = f'<nav><a href="{escape(home, quote=True)}">Главная Мандалы</a></nav>' if home else ""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Команды Мандалы</title>
<style>
  body {{ margin: 0; background: #0d1117; color: #e6edf3; font: 16px/1.55 system-ui, sans-serif; }}
  main {{ max-width: 720px; margin: auto; padding: 28px 20px 48px; }}
  a {{ color: #84b9ff; }}
  h1 {{ font-size: clamp(28px, 6vw, 40px); }}
  dl {{ display: grid; gap: 12px; }}
  dl div {{ padding: 14px 16px; background: #161b22; border: 1px solid #30363d; border-radius: 10px; }}
  dt {{ font-weight: 650; color: #a9ceff; }}
  dd {{ margin: 4px 0 0; }}
</style>
</head>
<body>
<main>
{navigation}
<h1>Команды Мандалы</h1>
<p>Отправь нужную команду отдельным сообщением в чат СР.</p>
<dl>{chr(10).join(cards)}</dl>
</main>
</body>
</html>
""", encoding="utf-8", newline="\n")
