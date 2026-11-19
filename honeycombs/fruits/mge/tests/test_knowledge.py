import copy
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from mge.knowledge import load_knowledge, validate, write_knowledge_index
from mge.reader import LABELS, build_material


ROOT = Path(__file__).resolve().parents[4]
KNOWLEDGE = ROOT / 'honeycombs/knowledge'


class KnowledgeTest(unittest.TestCase):
    def test_human_titles_and_summaries_are_russian(self):
        for material in load_knowledge(KNOWLEDGE)['materials']:
            for field in ('title', 'summary'):
                with self.subTest(material=material['id'], field=field):
                    self.assertRegex(material[field], r'[А-Яа-яЁё]')

    def test_all_materials_have_valid_reading_pages(self):
        collection = load_knowledge(KNOWLEDGE)
        self.assertGreaterEqual(len(collection['materials']), 31)
        pilots = collection['materials']
        self.assertNotIn('legacy', {m['kind'] for m in pilots})
        self.assertTrue({'article', 'framework', 'tools', 'reference', 'checklist', 'questions', 'collection'} <= {m['kind'] for m in pilots})
        with tempfile.TemporaryDirectory() as temp:
            for m in pilots:
                build_material(Path(temp), m)
                page = (Path(temp) / m['reading_url']).read_text(encoding='utf-8')
                self.assertIn(m['title'], page)
                self.assertIn('knowledge.html#' + m['graph_id'], page)

    def test_rejects_invalid_materials(self):
        schema = json.loads((KNOWLEDGE / 'material.schema.json').read_text(encoding='utf-8'))
        material = json.loads((KNOWLEDGE / 'ai_tools/chatbots.json').read_text(encoding='utf-8'))
        for key, value in [('kind', 'unknown'), ('id', '../escape'), ('title', ''), ('content', {'tools': 'wrong'})]:
            bad = copy.deepcopy(material)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(bad, schema)
        del material['verification']
        with self.assertRaises(ValueError):
            validate(material, schema)

    def test_graph_uses_the_same_identities_and_sources(self):
        from mge.core.parser import parse_knowledge
        graph = parse_knowledge(KNOWLEDGE / 'index.json')
        collection = load_knowledge(KNOWLEDGE)
        self.assertEqual({n['id'] for n in graph['nodes']}, {m['graph_id'] for m in collection['materials']})
        for material in collection['materials']:
            node = next(n for n in graph['nodes'] if n['id'] == material['graph_id'])
            self.assertEqual((node['name'], node['description'], node['path']),
                             (material['title'], material['summary'], material['path']))

    def test_generated_index_is_complete_deterministic_and_not_a_source(self):
        collection = load_knowledge(KNOWLEDGE)
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'knowledge'
            shutil.copytree(KNOWLEDGE, folder)
            write_knowledge_index(folder, collection)
            original = (folder / 'index.json').read_bytes()
            index = json.loads(original)
            self.assertEqual(len(index['contents']) + len(index['categories']), len(collection['materials']))
            self.assertEqual(len(index['categories']), len(next(m for m in collection['materials'] if m['kind'] == 'collection')['children']))
            (folder / 'index.json').write_text('{}', encoding='utf-8')
            reloaded = load_knowledge(folder)
            self.assertEqual(len(reloaded['materials']), len(collection['materials']))
            write_knowledge_index(folder, reloaded)
            self.assertEqual(original, (folder / 'index.json').read_bytes())

    def test_all_structural_captions_are_russian(self):
        hidden = {'id', 'module_id', 'schema_version', 'aliases'}
        def check(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    self.assertTrue(key in hidden or key in LABELS or re.search(r'[А-Яа-яЁё]', key), key)
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)
        for material in load_knowledge(KNOWLEDGE)['materials']:
            with self.subTest(material=material['id']):
                check(material['content'])
                check(material['supporting'])

    def test_discovery_metadata_and_identity_collisions(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'knowledge'
            shutil.copytree(KNOWLEDGE, folder)
            path = folder / 'ai_tools/new-category.json'
            material = json.loads((folder / 'ai_tools/chatbots.json').read_text(encoding='utf-8'))
            material.update(id='new-category', title='New source title', summary='New source summary')
            path.write_text(json.dumps(material), encoding='utf-8')
            found = next(m for m in load_knowledge(folder)['materials'] if m['id'] == 'new-category')
            self.assertEqual(found['title'], 'New source title')
            self.assertEqual(found['graph_id'], 'tool-new-category')
            material['area'] = 'missing-area'
            path.write_text(json.dumps(material), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Unknown Knowledge area'):
                load_knowledge(folder)
            material['area'] = 'ai-tools'
            material['id'] = 'chatbots'
            path.write_text(json.dumps(material), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Duplicate Knowledge identity'):
                load_knowledge(folder)


if __name__ == '__main__':
    unittest.main()
