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
assert.equal(map.tone(model.byId.get('works')).hex,'#a371f7');
assert.equal(map.tone(model.byId.get('product')).hex,'#7989ef');
assert.equal(map.tone({id:'core_map',hub:true}).hex,'#56d364');
const texture=map.fiberGeometry('works');
assert.deepEqual(texture,map.fiberGeometry('works'),'texture does not flicker between frames');
assert.notDeepEqual(texture,map.fiberGeometry('fruits'),'nodes have individual fiber patterns');
assert.ok(texture.fibers.length>map.fiberGeometry('small',55).fibers.length);
assert.ok(texture.fibers.every(f=>f.points.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)&&Math.hypot(p.x,p.y)<=1)));
assert.ok(texture.tips.every(f=>f.points.every(p=>Math.hypot(p.x,p.y)<1.2)),'edge fibers fit the cached sprite');


'''
        subprocess.run(['node','-e',program,str(script)],check=True,capture_output=True,text=True)

    @unittest.skipUnless(shutil.which('node'), 'Node needed for physics regression')
    def test_drag_propagates_over_links_and_settles(self):
        script = Path(__file__).resolve().parents[1] / 'mge/reporters/neural_map.js'
        program = r'''
const assert=require('node:assert/strict'),map=require(process.argv[1]);
const graph={nodes:[{id:'works',type:'honeycomb'},{id:'a',type:'work'},
 {id:'b',type:'work'},{id:'isolated',type:'knowledge'}],edges:[
 {from:'works',to:'a',type:'contains'},{from:'a',to:'b',type:'related'}]};
const source=JSON.stringify(graph),m=map.buildModel(graph),physics=map.createPhysics(m);
const start=new Map(m.nodes.map(n=>[n.id,{x:n.x,y:n.y}]));
const distance=id=>Math.hypot(m.byId.get(id).x-start.get(id).x,m.byId.get(id).y-start.get(id).y);
assert.equal(physics.step(),false,'idle map does not animate');
physics.pin('works',start.get('works').x+180,start.get('works').y+40);
physics.step();
assert.ok(distance('a')>0,'direct neighbor follows');
assert.equal(distance('b'),0,'distant neighbor responds after a delay');
assert.equal(distance('isolated'),0,'unconnected node does not follow');
for(let i=0;i<60;i++)physics.step();
assert.ok(distance('b')>1,'motion reaches the next linked node');
assert.equal(m.byId.get('works').x,start.get('works').x+180,'grabbed node stays under pointer');
assert.ok(distance('a')<180,'group is elastic, not rigidly translated');
physics.release();
for(let i=0;i<650;i++)physics.step();
assert.equal(physics.active,false,'animation eventually sleeps');
assert.ok(distance('works')<180,'damping and anchors settle the pull');
assert.ok(m.nodes.every(n=>Number.isFinite(n.x)&&Number.isFinite(n.y)));
assert.equal(JSON.stringify(graph),source,'source graph unchanged');
const hidden=map.buildModel(graph),p=map.createPhysics(hidden);
const hx=hidden.byId.get('a').x;
p.pin('works',200,0);for(let i=0;i<30;i++)p.step(1,new Set(['works']));
assert.equal(hidden.byId.get('a').x,hx,'hidden nodes do not move');
p.stop();assert.equal(p.active,false);
const reduced=map.createPhysics(map.buildModel(graph),{reducedMotion:true});
reduced.pin('works',200,0);reduced.step();reduced.release();
for(let i=0;i<120;i++)reduced.step();
assert.equal(reduced.active,false,'reduced-motion tail is bounded');
'''
        subprocess.run(['node','-e',program,str(script)],check=True,capture_output=True,text=True)
