"""Regression checks for real edge aggregation, filtering and standalone output."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from mge.reporters.html_reporter import write_html


class NeuralMapTest(unittest.TestCase):
    def test_html_is_standalone_and_graph_cannot_close_script(self):
        graph = {"nodes": [{"id": "</script><script>bad()</script>__NEURAL_JS__", "type": "work"}], "edges": []}
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "graph.html"
            write_html(graph, target)
            html = target.read_text(encoding="utf-8")
        self.assertNotIn('<script src=', html)
        self.assertNotIn('</script><script>bad()', html)
        self.assertIn('<\\/script>', html)
        self.assertIn('__NEURAL_JS__', html)
        self.assertIn('NeuralMap.init(GRAPH)', html)

    @unittest.skipUnless(shutil.which('node'), 'Node needed for graph interaction model')
    def test_real_links_determine_bundle_weight_without_duplicates(self):
        script = Path(__file__).resolve().parents[1] / 'mge/reporters/neural_map.js'
        program = r'''
const assert=require('node:assert/strict'),map=require(process.argv[1]);
const graph={nodes:[{id:'works',type:'honeycomb'},{id:'fruits',type:'honeycomb'},
{id:'task',type:'work'},{id:'product',type:'fruit'},{id:'other',type:'work'}],edges:[
{from:'works',to:'task',type:'contains'},{from:'works',to:'other',type:'contains'},
{from:'fruits',to:'product',type:'contains'},
{from:'task',to:'product',type:'references'},{from:'task',to:'product',type:'references'},
{from:'product',to:'other',type:'product_work'},{from:'task',to:'product',type:'depends_on'}]};
const before=JSON.stringify(graph),model=map.buildModel(graph);
const full=map.visibleModel(model,new Set(['honeycomb','work','fruit']));
assert.equal(JSON.stringify(graph),before);
assert.equal(full.nodes.length,5,'no decorative nodes');
assert.equal(full.edges.length,6,'identical duplicates removed');
assert.equal(full.bundles.length,1);
assert.equal(full.bundles[0].count,3,'directions and distinct relationship types count');
assert.equal(model.byId.get('task').degree,2,'unique neighbors');
assert.ok(model.byId.get('task').radius<model.byId.get('works').radius);
assert.ok(full.bundles[0].width>map.strength(1).width);
assert.ok(map.strength(100000).width<model.byId.get('works').radius*2);
const filtered=map.visibleModel(model,new Set(['honeycomb','work']));
assert.equal(filtered.bundles.length,0,'hidden links do not inflate weight');
assert.equal(filtered.edges.length,2);
assert.ok(model.nodes.every(n=>Number.isFinite(n.x)&&Number.isFinite(n.y)));
'''
        subprocess.run(['node','-e',program,str(script)],check=True,capture_output=True,text=True)
