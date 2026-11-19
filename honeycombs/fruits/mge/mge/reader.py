"""Static reading views, generated from the original Knowledge JSON."""
from html import escape


LABELS = {
    "purpose": "Назначение", "positioning": "Позиционирование",
    "design_notes": "Заметки по оформлению", "marketing_rationale": "Обоснование подачи",
    "open_questions": "Открытые вопросы", "source": "Источник",
    "hosting_plan": "План размещения", "notion_automation_plan": "План автоматизации Notion",
    "notion_page_url": "Страница Notion", "one_line": "Коротко",
    "value_formula": "Ценность", "differentiation_angle": "Отличие",
    "key_term": "Ключевое понятие", "core_concept": "Основная идея",
    "format": "Формат", "reading_time_target": "Время чтения", "tone": "Тон",
    "avoid": "Чего избегать", "new_elements": "Добавленные элементы",
    "applied_principles": "Применённые принципы", "audit_framework_alignment": "Связь с аудитом",
    "platform": "Платформа", "why": "Почему", "url": "Адрес", "qr_code": "QR-код",
    "next_steps": "Следующие шаги", "advantages": "Преимущества", "setup_steps": "Настройка",
    "step": "Шаг", "name": "Название", "description": "Описание", "link": "Ссылка",
    "code": "Пример кода", "python_script_template": "Пример скрипта Python",
    "github_actions_template": "Пример GitHub Actions",
    "recommended_file_structure": "Предлагаемая структура файлов", "folders": "Папки",
    "what": "Что это", "when": "Когда применять", "how_to_use": "Как использовать",
    "limitations": "Ограничения", "zones": "Зоны риска", "when_to_use": "Когда применять",
    "core_question": "Основной вопрос", "diagnostic_questions": "Вопросы для диагностики",
    "metrics": "Метрики", "red_flags": "Тревожные признаки", "recommendation": "Рекомендация",
    "tools": "Инструменты", "pros": "Плюсы", "cons": "Минусы",
    "integration_with_mandala": "Применение в Мандале", "sources": "Источники",
    "packaging_principles": "Принципы подачи", "mandala_specific_requirements": "Особенности Мандалы",
    "seeds": "Семена", "tasks": "Задачи", "fruits": "Продукты", "roadmaps": "Планы развития",
    "scout_agent": "Скаут", "symbiosis_guard": "Проверка качества",
    "blocks": "Блоки", "check": "Проверка", "core_principle": "Основной принцип",
    "date_added": "Дата добавления", "fact": "Факт", "important_clarifications": "Важные уточнения",
    "packaging_checklist": "Проверка подачи", "practical_conclusion": "Практический вывод",
    "principles": "Принципы", "reason": "Причина", "requirements": "Требования",
    "research_data": "Данные исследований", "steps": "Шаги", "summary": "Итог", "topic": "Тема",
    "community": "Общность", "meaning": "Смысл", "ritual": "Ритуал",
    "sections": "Разделы", "subtitle": "Подзаголовок", "text": "Текст", "title": "Заголовок",
    "heading": "Заголовок раздела", "zone_1_awareness": "Известность",
    "zone_3_value_clarity": "Понятность ценности", "zone_4_differentiation": "Отличие от конкурентов",
    "usage_notes": "О материале и его применении", "version_source": "Версия исходного каталога",
    "total_categories": "Количество категорий", "verification_policy": "Правила проверки актуальности",
    "pilot_schema": "Сведения о формате", "service_metadata": "Сведения о записи",
    "layer": "Уровень", "type": "Тип записи", "status": "Состояние", "priority": "Приоритет",
    "design_principle": "Принцип проверки", "audit_categories": "Разделы проверки",
    "category": "Раздел", "goal": "Цель", "check_items": "Пункты проверки",
    "why_it_matters": "Почему это важно", "output_schema_for_reviewer": "Шаблон заключения",
    "instruction": "Порядок работы", "schema": "Структура результата", "audit_id": "ID аудита",
    "reviewer": "Проверяющий", "date": "Дата", "findings": "Результаты проверки",
    "check_id": "ID пункта", "evidence": "Обоснование", "suggested_fix": "Предлагаемая правка",
    "overall_assessment": "Общая оценка", "coercion_risk": "Риск принуждения",
    "top_3_priority_fixes": "Три приоритетные правки", "closing_note": "Заключение",
    "resonance": "Примечание о резонансе", "levels": "Уровни знакомства", "level": "Уровень",
    "questions": "Вопросы", "psychological_key": "Психологический смысл",
    "personal/profile_deep.json": "Профиль Садовника", "personal/self_development.json": "Саморазвитие",
    "communication_and_conflict_style": "Общение и работа с конфликтами", "recommendations": "Рекомендации",
    "what_it_is": "Что это", "author": "Автор", "license": "Лицензия",
    "key_innovation": "Основное новшество", "effect": "Результат", "tradeoff": "Компромисс",
    "verified_facts": "Зафиксированные сведения", "github": "Репозиторий GitHub",
    "pypi": "Пакет в PyPI", "docker": "Образ Docker", "zenodo": "Публикация в Zenodo",
    "recognition": "Упоминания", "benchmarks": "Результаты испытаний",
    "rtx_3050_4gb": "Видеокарта RTX 3050, 4 ГБ", "llama_3_1_8b_nf4_lora": "Модель Llama 3.1 8B, NF4 и LoRA",
    "throughput": "Производительность", "peak_vram": "Пиковое потребление видеопамяти",
    "qwen2_5_3b_nf4": "Модель Qwen 2.5 3B, NF4", "correctness": "Корректность",
    "reproducibility": "Воспроизводимость", "honest_limitations": "Ограничения",
    "full_functionality": "Возможности", "decide": "Выбор подхода", "train": "Обучение",
    "ship": "Подготовка к использованию", "operate": "Эксплуатация", "secure": "Защита",
    "integrations": "Интеграции", "migration": "Перенос", "relevance_to_mandala": "Применимость к Мандале",
    "direct_fit": "Прямое применение", "use_case": "Сценарий применения", "current_limitation": "Текущее ограничение",
    "value": "Ценность", "links": "Ссылки", "instagram_source": "Исходная публикация в Instagram",
    "mandala_verdict": "Вывод для Мандалы", "navigation": "Связанные разделы", "parent": "Родительский раздел",
    "health": "Сведения о состоянии", "last_check": "Последняя проверка", "notes": "Примечания",
    "core_structure": "Основная структура", "layers": "Уровни", "layer_1_core": "Основные документы",
    "layer_2_internal": "Внутренние документы", "layer_3_external": "Внешние документы",
    "layer_4_regulatory": "Регуляторные документы", "documents": "Документы",
    "international_relevance": "Международное применение", "practical_note": "Практическое примечание",
    "global_trends": "Общие тенденции", "trends": "Тенденции", "impact": "Влияние",
    "priority_actions": "Порядок действий", "phase_1_immediate": "Первый этап: ближайшие действия",
    "phase_2_early": "Второй этап: начало работы", "phase_3_investment_ready": "Третий этап: готовность к инвестициям",
    "phase_4_compliance": "Четвёртый этап: соблюдение требований", "how_to_navigate": "Как пользоваться справочником",
    "quick_reference": "Краткая памятка", "section": "Раздел", "topics": "Темы",
    "use_in_mandala": "Применение в Мандале", "key_links": "Основные ссылки",
    "catalog_description": "О каталоге", "previous_format_note": "Историческая заметка о формате",
}


def paragraphs(value):
    return "".join(f'<p>{escape(p)}</p>' for p in value.split("\n\n"))


def supplementary(value):
    """Preserve every value without executing embedded markup or code."""
    if isinstance(value, dict):
        return '<dl>' + ''.join(
            f'<dt>{escape(LABELS.get(k, k.replace("_", " ")))}</dt><dd>{supplementary(v)}</dd>'
            for k, v in value.items() if k not in {'id', 'module_id', 'schema_version', 'aliases'}) + '</dl>'
    if isinstance(value, list):
        return '<ul>' + ''.join(f'<li>{supplementary(v)}</li>' for v in value) + '</ul>'
    text = str(value) if value is not None else '—'
    text = {"one_page": "Одна страница", "active": "Активно", "high": "Высокий",
            "medium": "Средний", "low": "Низкий", "healthy": "В порядке",
            "knowledge_resource": "Материал базы знаний", "knowledge_index": "Каталог базы знаний"}.get(text, text)
    if text.startswith('```'):
        return f'<pre><code>{escape(text)}</code></pre>'
    if text.startswith(('https://', 'http://')) and not any(c.isspace() for c in text):
        return f'<p><a href="{escape(text)}" rel="noopener noreferrer">{escape(text)}</a></p>'
    return paragraphs(text)


def build_material(output, data):
    article = data['content']
    sections, toc = [], []
    if data['kind'] == 'article':
        blocks = article['sections']
        title = escape(article['title'])
        subtitle = escape(article.get('subtitle', ''))
    else:
        blocks = []
        title, subtitle = escape(data['title']), escape(data['summary'])
        for key, value in article.items():
            if key in {'tools', 'zones', 'audit_categories', 'levels', 'documents', 'sections'}:
                for item in value:
                    title_key = next((k for k in ('name', 'category', 'section') if k in item), None)
                    blocks.append({'heading': item[title_key] if title_key else LABELS[key],
                                   'html': supplementary({k: v for k, v in item.items() if k != title_key})})
            else:
                blocks.append({'heading': LABELS.get(key, key.replace('_', ' ')), 'html': supplementary(value)})
        if data['kind'] == 'collection':
            children = ''.join(f'<li><a href="{escape(m["reading_url"])}">{escape(m["title"])}</a>'
                               f'<p>{escape(m["summary"])}</p></li>' for m in data['children'])
            blocks.insert(0, {'heading': 'Категории инструментов', 'html': f'<ul>{children}</ul>'})
    for i, section in enumerate(blocks, 1):
        anchor = f'section-{i}'
        heading = section.get('heading')
        if heading:
            toc.append(f'<li><a href="#{anchor}">{escape(heading)}</a></li>')
        sections.append(f'<section id="{anchor}">' + (f'<h2>{escape(heading)}</h2>' if heading else '')
                        + (section['html'] if 'html' in section else paragraphs(section['text'])) + '</section>')
    extra = ''.join(f'<details><summary>{escape(LABELS.get(k, k.replace("_", " ")))}</summary>'
                    f'<div class="extra-body">{supplementary(v)}</div></details>'
                    for k, v in data['supporting'].items())
    if data.get('sources'):
        extra += f'<details><summary>Источники</summary><div class="extra-body">{supplementary(data["sources"])}</div></details>'
    page = f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(data['title'])} — Knowledge</title>
<link rel="icon" href="../../../../assets/mandala.svg" type="image/svg+xml">
<style>
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{ margin: 0; background: #0d1117; color: #e6edf3; font: 17px/1.8 "Segoe UI", sans-serif; }}
main {{ max-width: 800px; margin: auto; padding: 28px 22px 64px; }}
a {{ color: #84b9ff; overflow-wrap: anywhere; }}
nav {{ display: flex; flex-wrap: wrap; gap: 20px; font-size: 15px; }}
header {{ text-align: center; padding: 44px 0 30px; }}
h1 {{ letter-spacing: .04em; font-size: clamp(26px, 5vw, 42px); line-height: 1.3; margin: 0; overflow-wrap: anywhere; }}
.subtitle {{ font-size: clamp(19px, 4vw, 25px); color: #b8a1e6; }}
.meta {{ color: #a7b4c5; font-size: 13px; }}
.notice {{ border-left: 3px solid #a371f7; padding: 10px 16px; background: #161b22; font-size: 14px; }}
.toc {{ margin: 28px 0; padding: 18px 22px; background: #161b22; border-radius: 12px; }}
.toc ol {{ margin-bottom: 0; padding-left: 22px; }}
article section {{ padding: 12px 0; scroll-margin-top: 20px; }}
h2 {{ font-size: clamp(22px, 4vw, 29px); line-height: 1.4; margin-top: 24px; }}
p {{ white-space: pre-line; overflow-wrap: anywhere; }}
.extras {{ margin-top: 48px; border-top: 1px solid #30363d; }}
details {{ border-bottom: 1px solid #30363d; }}
summary {{ cursor: pointer; padding: 16px 32px 16px 0; position: relative; list-style: none; }}
summary::-webkit-details-marker {{ display: none; }}
summary::after {{ content: '⌄'; position: absolute; right: 6px; top: 16px; }}
details[open] > summary::after {{ transform: rotate(180deg); }}
.extra-body {{ padding: 0 8px 20px; font-size: 15px; }}
dt {{ color: #b8a1e6; font-weight: 600; margin-top: 18px; }}
dd {{ margin-left: 16px; }}
pre {{ overflow: auto; padding: 14px; background: #161b22; font-size: 13px; }}
:focus-visible {{ outline: 2px solid #84b9ff; outline-offset: 4px; }}
@media print {{ body {{ background: white; color: black; }} nav, .toc, .extras, .notice {{ display: none; }} }}
</style></head><body><main>
<nav><a href="knowledge.html#{escape(data['graph_id'])}">← Knowledge</a><a href="../../../../index.html">Главная</a></nav>
<header><h1>{title}</h1><p class="subtitle">{subtitle}</p>
<p class="meta">Версия {escape(data.get('version') or 'не указана')} · Обновлено {escape(data.get('updated') or 'не указано')}
· Создано {escape(data.get('created') or 'не указано')}</p>
<p class="meta">Проверено: {escape(data['verification'].get('checked_at') or 'не отмечено')}<br>{escape(data['verification'].get('scope') or '')}</p></header>
<p class="notice">Текст показан из сохранённой версии материала без редакторских изменений.
Дата обновления не означает новую проверку актуальности упомянутых продуктов и планов.</p>
<nav class="toc" aria-label="Оглавление"><div><strong>Содержание</strong><ol>{''.join(toc)}</ol></div></nav>
<article aria-label="Текст материала">{''.join(sections)}</article>
<section class="extras"><h2>Дополнительные материалы</h2>{extra}</section>
<p class="meta"><a href="https://github.com/voodoomushroomzzz-source/mandala-core/blob/main/{escape(data['path'])}">Исходный материал</a></p>
</main></body></html>'''
    (output / data['reading_url']).write_text(page, encoding='utf-8', newline='\n')
    return data


def build_brochure(root, output):
    """Compatibility wrapper for the original brochure reader entry point."""
    from mge.knowledge import load_knowledge
    data = next(m for m in load_knowledge(root / 'honeycombs/knowledge')['materials'] if m['id'] == 'mandala_brochure')
    return build_material(output, data)
