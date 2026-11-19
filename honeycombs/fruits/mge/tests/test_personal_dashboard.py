import json
import tempfile
import unittest
from pathlib import Path

from mge.dashboard import build_personal, personal_entries


class PersonalDashboardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.personal = self.root / "honeycombs/personal"
        self.personal.mkdir(parents=True)
        self.movement = {"directions": [{"id": "learning", "name": "Обучение", "state": "unconfirmed"}]}
        self.write("current_movement.json", self.movement)

    def write(self, path, value):
        target = self.personal / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value), encoding="utf-8")

    def test_empty_board_preserves_unconfirmed_dates(self):
        self.write("personal_tasks.json", {"tasks": []})
        build_personal(self.root, self.root)
        html = (self.root / "personal.html").read_text(encoding="utf-8")
        self.assertIn("Согласованных текущих действий пока нет", html)
        self.assertIn("ещё не сверяли", html)

    def test_card_escapes_text_and_shows_deadline(self):
        self.write("personal_tasks.json", {"tasks": [{"id": "PER-001", "name": "<test>",
                   "description": "A & B", "direction": "learning", "status": "active",
                   "priority": "high", "deadline": "2026-12-01", "next_step": "Практика"}]})
        build_personal(self.root, self.root)
        html = (self.root / "personal.html").read_text(encoding="utf-8")
        self.assertIn("&lt;test&gt;", html)
        self.assertIn('datetime="2026-12-01"', html)
        self.assertIn("Следующий шаг: Практика", html)

    def test_reference_reads_live_source_and_fails_when_missing(self):
        self.write("personal_tasks.json", {"tasks": [{"id": "PER-001",
                   "source_file": "honeycombs/personal/kurtoch/taskboard.json", "record_id": "K-1"}]})
        source = {"taskboard": {"tasks": [{"id": "K-1", "title": "Текущая задача",
                  "status": "todo", "priority": "medium", "deadline": "2026-12-02"}]}}
        self.write("kurtoch/taskboard.json", source)
        self.assertEqual(personal_entries(self.root, self.movement)[0]["name"], "Текущая задача")
        source["taskboard"]["tasks"][0]["title"] = "Обновлена"
        self.write("kurtoch/taskboard.json", source)
        self.assertEqual(personal_entries(self.root, self.movement)[0]["name"], "Обновлена")
        self.write("kurtoch/taskboard.json", {"taskboard": {"tasks": []}})
        with self.assertRaisesRegex(ValueError, "Missing or ambiguous"):
            personal_entries(self.root, self.movement)

    def test_career_reference_keeps_unconfirmed_deadline_out_of_current_queue(self):
        self.write("personal_tasks.json", {"tasks": [{"id": "A-1", "record_id": "A-1",
                   "source_file": "honeycombs/personal/career.json",
                   "source_collection": "/task_tracker/packaging_tasks", "direction": "career",
                   "now": False, "deadline_confirmed": False, "priority_confirmed": False}]})
        self.write("career.json", {"task_tracker": {"packaging_tasks": [
                   {"id": "A-1", "name": "Площадки", "status": "pending",
                    "priority": "HIGH", "deadline": "2026-10-13"}]}})
        entry = personal_entries(self.root, self.movement)[0]
        self.assertFalse(entry["now"])
        self.assertIsNone(entry["priority"])
        self.assertIn("не подтверждён", entry["summary_detail"])


if __name__ == "__main__":
    unittest.main()
