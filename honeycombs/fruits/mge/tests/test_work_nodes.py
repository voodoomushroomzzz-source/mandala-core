import json
import tempfile
import unittest
from pathlib import Path

from mge.core.parser import parse_works


class WorkNodeTests(unittest.TestCase):
    def test_card_edit_updates_graph_metadata_without_an_index_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work_id = "W-T-TEST"
            index = root / "index.json"
            manifest = json.dumps({"manifest": {"works_list": [work_id]}})
            index.write_text(manifest, encoding="utf-8")
            path = root / f"{work_id}__example.json"
            card = {"name": "Исходное название", "status": "planned",
                    "description": "Длинное описание работы. " * 60}
            path.write_text(json.dumps(card), encoding="utf-8-sig")

            first, = parse_works(index)["nodes"]
            self.assertEqual(first["path"], f"honeycombs/works/{path.name}")
            self.assertEqual(first["name"], card["name"])
            self.assertEqual(first["status"], "planned")
            self.assertLessEqual(len(first["description"]), 420)
            self.assertTrue(first["description"].endswith("…"))

            card.update(name="Новое название", status="active",
                        short_description="Проверка открытия одной папки.")
            path.write_text(json.dumps(card), encoding="utf-8")
            second, = parse_works(index)["nodes"]
            self.assertEqual(second["name"], card["name"])
            self.assertEqual(second["status"], "active")
            self.assertEqual(second["description"], card["short_description"])
            self.assertEqual(index.read_text(encoding="utf-8"), manifest)
