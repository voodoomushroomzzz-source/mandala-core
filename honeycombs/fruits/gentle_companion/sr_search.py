# -*- coding: utf-8 -*-
"""
sr_search.py — Web Search & OpenRouter Search Synthesis
Tavily search integration and search result synthesis via LLM.

Part of: honeycombs/fruits/gentle_companion/
Phase: 2 (depends on config.py — TAVILY_API_KEY, OPENROUTER_KEY)

Key functions:
  _classify_query_complexity() — how many sources to fetch (1/2/3)
  _tavily_search_raw()         — Tavily API search with domain routing + cache
  _synthesize_search()         — LLM synthesis of search results

Globals:
  _DOMAIN_MAP    — category → priority domains
  _search_cache  — 15-min result cache
  _SEARCH_CACHE_TTL
"""

def _classify_query_complexity(query: str) -> int:
    """
    Определяет сколько источников смотреть: 1, 2 или 3.
    1 — простой факт: погода, курс, одна дата, одно событие
    2 — средний: объяснение, сравнение, текущие новости
    3 — сложный: исследование, аналитика, несколько аспектов
    """
    q = query.lower()
    # Признаки простого запроса (1 источник)
    simple_keywords = [
        "погода", "температура", "курс", "сколько стоит", "когда", "где находится",
        "время", "расписание", "телефон", "адрес", "открыт", "закрыт",
    ]
    # Признаки сложного запроса (3 источника)
    complex_keywords = [
        "сравни", "сравнение", "плюсы и минусы", "анализ", "история",
        "почему", "как работает", "объясни", "расскажи подробно",
        "лучший", "топ", "рейтинг", "обзор", "исследование",
    ]
    if any(k in q for k in simple_keywords) or len(query.split()) <= 4:
        return 1
    if any(k in q for k in complex_keywords) or len(query.split()) >= 10:
        return 3
    return 2


# ── Домены по категориям запросов (Блок 1) ────────────────────────────────────
_DOMAIN_MAP = {
    "weather":    ["yandex.ru/pogoda", "gismeteo.ru", "meteoinfo.ru"],
    "cinema":     ["afisha.yandex.ru", "kinopoisk.ru", "afisha.ru", "kudago.com"],
    "events":     ["afisha.yandex.ru", "afisha.ru", "kudago.com", "timepad.ru", "mos.ru"],
    "concerts":   ["afisha.yandex.ru", "kassir.ru", "afisha.ru", "kudago.com"],
    "jobs":       ["hh.ru", "superjob.ru", "rabota.ru"],
    "food":       ["yandex.ru/maps", "2gis.ru", "restoclub.ru", "afisha.ru"],
    "sport":      ["yandex.ru/maps", "sports.ru", "sport-express.ru", "championat.com"],
    "health":     ["yandex.ru/maps", "prodoctorov.ru", "napopravku.ru", "gosuslugi.ru"],
    "news":       ["rbc.ru", "ria.ru", "interfax.ru", "tass.ru"],
    "education":  ["skillbox.ru", "stepik.org", "otus.ru"],
    "default":    ["yandex.ru/maps", "afisha.yandex.ru", "2gis.ru", "rbc.ru"],
}

# ── Кэш поисковых запросов 15 минут (Блок 5) ─────────────────────────────────
_search_cache: dict = {}  # {cache_key: (result_list, timestamp)}
_SEARCH_CACHE_TTL = 900   # 15 минут


async def _tavily_search_raw(query: str, city: str = "", category: str = "default") -> list:
    """Поиск через Tavily. Возвращает список словарей [{title, url, content}].
    Использует домены по категории. Без AI-answer — только реальный контент.
    Кэширует результаты на 15 минут.
    """
    if not TAVILY_API_KEY:
        return []
    import time as _time
    import hashlib as _hashlib

    q = f"{query} {city}".strip() if city else query
    cache_key = _hashlib.md5(f"{q}|{category}".encode()).hexdigest()

    # Проверяем кэш
    if cache_key in _search_cache:
        cached_result, cached_ts = _search_cache[cache_key]
        if _time.time() - cached_ts < _SEARCH_CACHE_TTL:
            logger.info(f"Web search cache hit: q='{q[:50]}'")
            return cached_result

    num_results = _classify_query_complexity(q)
    domains = _DOMAIN_MAP.get(category, _DOMAIN_MAP["default"])

    try:
        async with aiohttp.ClientSession() as session:
            # Первый запрос — с приоритетными доменами
            async with session.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": q,
                    "search_depth": "basic",
                    "max_results": num_results + 2,
                    "include_answer": False,
                    "include_domains": domains,
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                else:
                    # Повтор без фильтра доменов
                    async with session.post(
                        "https://api.tavily.com/search",
                        json={
                            "api_key": TAVILY_API_KEY,
                            "query": q,
                            "search_depth": "basic",
                            "max_results": num_results,
                            "include_answer": False,
                        },
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp2:
                        if resp2.status != 200:
                            return []
                        data = await resp2.json()

            results = data.get("results", [])
            sources = []
            for r in results[:num_results]:
                title   = (r.get("title") or "").strip()
                url     = (r.get("url") or "").strip()
                content = (r.get("content") or "")[:400].strip()
                if title and url:
                    sources.append({"title": title, "url": url, "content": content})

            # Сохраняем в кэш
            _search_cache[cache_key] = (sources, _time.time())
            logger.info(f"Web search: cat={category} complexity={num_results} sources={len(sources)} q='{q[:50]}'")
            return sources

    except Exception as e:
        logger.warning(f"Tavily error: {e}")
    return []


async def _synthesize_search(query: str, sources: list) -> str:
    """SR синтезирует результаты поиска в структурированный ответ."""
    if not sources:
        return ""

    # Собираем контент из источников
    context_parts = []
    for s in sources:
        context_parts.append(f"Источник: {s['title']}\n{s['content']}")
    context = "\n\n".join(context_parts)

    # Ссылки на источники
    source_links = "\n".join(
        '• <a href="' + s['url'] + '">' + s['title'] + '</a>' for s in sources
    )

    synthesis = await _call_openrouter(
        [
            {
                "role": "system",
                "content": (
                    "Синтезируй данные из поиска в чёткий структурированный ответ на русском. "
                    "Только конкретные факты — названия, даты, цены, адреса, варианты. "
                    "Никаких сфер резонанса, профилей, личных наблюдений, философии. "
                    "ФОРМАТИРОВАНИЕ — только эмодзи и переносы строк. "
                    "Никаких символов Markdown: ни **, ни *, ни #, ни --. Совсем. "
                    "Эмодзи для структуры: 🎵 музыка/концерты, 🎬 кино, 🌤 погода, "
                    "🍽 еда/рестораны, 💼 работа, 🏋 спорт, 📰 новости, 🎭 события, 🏥 здоровье. "
                    "Структурируй по категориям если несколько вариантов. "
                    "В конце один уточняющий вопрос если уместно. До 300 слов."
                )
            },
            {
                "role": "user",
                "content": f"Запрос: {query}\n\nДанные из источников:\n{context}"
            }
        ],
        model_idx=0
    )

    if synthesis:
        return synthesis + f"\n\nИсточники:\n{source_links}"
    # Fallback — минимальный ответ из первого источника
    first = sources[0]
    return f"{first['content']}\n\nИсточники:\n{source_links}"