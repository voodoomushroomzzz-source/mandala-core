"""One validated Knowledge model for cards, readers and graph consumers."""
import json
import re
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate(value, schema, location="material"):
    """Validate the keywords used by the bundled v1 schema, without dependencies."""
    types = {"object": dict, "array": list, "string": str, "null": type(None)}
    expected = schema.get("type")
    if expected and not isinstance(value, tuple(types[t] for t in ([expected] if isinstance(expected, str) else expected))):
        raise ValueError(f"{location}: expected {expected}")
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{location}: wrong constant")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{location}: unsupported value {value}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or ("pattern" in schema and not re.search(schema["pattern"], value)):
            raise ValueError(f"{location}: invalid string")
    if isinstance(value, dict):
        missing = set(schema.get("required", [])) - value.keys()
        if missing:
            raise ValueError(f"{location}: missing {sorted(missing)}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and value.keys() - properties.keys():
            raise ValueError(f"{location}: unknown fields {value.keys() - properties.keys()}")
        for key, rule in properties.items():
            if key in value:
                validate(value[key], rule, f"{location}.{key}")
    if isinstance(value, list):
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            raise ValueError(f"{location}: duplicate values")
        for i, item in enumerate(value):
            validate(item, schema.get("items", {}), f"{location}[{i}]")
    for rule in schema.get("allOf", []):
        validate(value, rule, location)
    if "if" in schema:
        try:
            validate(value, schema["if"], location)
        except ValueError:
            pass
        else:
            validate(value, schema.get("then", {}), location)


def load_knowledge(folder):
    folder = Path(folder).resolve()
    taxonomy = read(folder / "taxonomy.json")
    areas = {a["id"]: a["title"] for a in taxonomy["areas"]}
    if len(areas) != len(taxonomy["areas"]):
        raise ValueError("Duplicate Knowledge area")
    schema = read(folder / "material.schema.json")
    # Indexes are generated navigation, never inputs for material metadata.
    service_files = {"index.json", "taxonomy.json", "material.schema.json"}
    paths = []
    for path in folder.rglob("*.json"):
        relative = path.relative_to(folder).as_posix()
        if relative not in service_files:
            paths.append(relative)
    materials, identities = [], set()
    for relative in sorted(paths):
        path = (folder / relative).resolve()
        if not path.is_relative_to(folder):
            raise ValueError(f"Knowledge path escapes folder: {relative}")
        data = read(path)
        validate(data, schema, relative)
        if data["area"] not in areas:
            raise ValueError(f"Unknown Knowledge area: {data['area']}")
        material = dict(data)
        is_category = relative.startswith("ai_tools/") and material["kind"] != "collection"
        for identity in [material["id"], *material["aliases"]]:
            if identity in identities:
                raise ValueError(f"Duplicate Knowledge identity: {identity}")
            identities.add(identity)
        material.update(path="honeycombs/knowledge/" + relative,
                        category=is_category,
                        graph_id=("tool-" if is_category else "K-") + material["id"],
                        area_title=areas[material["area"]],
                        reading_url=material["id"] + ".html")
        materials.append(material)
    for material in materials:
        if material["kind"] == "collection":
            material["children"] = [m for m in materials if m["category"]]
    return {"materials": materials, "areas": list(areas.values())}


def write_knowledge_index(folder, collection):
    """Publish deterministic navigation for external readers, from material sources."""
    def entry(m):
        return {"id": m["id"], "name": m["title"],
                "file": m["path"].removeprefix("honeycombs/knowledge/"),
                "description": m["summary"], "version": m["version"], "updated": m["updated"]}
    data = {
        "identity": {"module_id": "KNOWLEDGE-INDEX-001", "name": "База знаний — навигация",
                     "type": "knowledge_index"},
        "meta": {"generated": True,
                 "how_to_use": "Выберите материал из contents или категорию из categories и прочитайте указанный файл. Метаданные и содержание редактируются только в исходном материале. Индекс пересобирается автоматически командой MGE dashboard или scan.",
                 "editing_instructions": "honeycombs/knowledge/README.md"},
        "contents": [entry(m) for m in collection["materials"] if not m["category"]],
        "categories": [entry(m) for m in collection["materials"] if m["category"]],
        "metrics": {"total_resources": sum(not m["category"] for m in collection["materials"]),
                    "total_categories": sum(m["category"] for m in collection["materials"]),
                    "total_materials": len(collection["materials"])},
    }
    (Path(folder) / "index.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
