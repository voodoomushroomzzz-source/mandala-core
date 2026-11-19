import json
import tempfile
import unittest
from html import escape
from pathlib import Path

from mge.reader import build_brochure, supplementary


class BrochureReaderTest(unittest.TestCase):
    def test_every_brochure_paragraph_is_preserved(self):
        root = Path(__file__).resolve().parents[4]
        source = root / 'honeycombs/knowledge/mandala_brochure.json'
        original = source.read_bytes()
        data = json.loads(original)
        with tempfile.TemporaryDirectory() as folder:
            build_brochure(root, Path(folder))
            page = (Path(folder) / 'mandala_brochure.html').read_text(encoding='utf-8')
        for section in data['content']['sections']:
            for paragraph in section['text'].split('\n\n'):
                self.assertIn(escape(paragraph), page)
            if section.get('heading'):
                self.assertIn(escape(section['heading']), page)
        self.assertIn(data['version'], page)
        self.assertIn(data['updated'], page)
        self.assertIn('Дополнительные материалы', page)
        self.assertEqual(original, source.read_bytes())

    def test_embedded_markup_and_examples_are_plain_text(self):
        result = supplementary({'code': '```html\n<script>alert(1)</script>\n```'})
        self.assertNotIn('<script>', result)
        self.assertIn('&lt;script&gt;', result)

    def test_service_ids_are_hidden_without_removing_content(self):
        result = supplementary({'id': 1, 'name': 'Название', 'requirements': [
            {'id': 'meaning', 'description': 'Смысл'}]})
        self.assertNotIn('<dt>id</dt>', result)
        self.assertNotIn('<p>1</p>', result)
        self.assertIn('Название', result)
        self.assertIn('Смысл', result)


if __name__ == '__main__':
    unittest.main()
