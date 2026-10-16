"""HTML reporter: self-contained interactive graph with vis.js."""
import json
from pathlib import Path


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mandala Graph Explorer</title>
<script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"></script>
<style>
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0d1117; color: #c9d1d9; }
  #header { padding: 12px 16px; background: #161b22; border-bottom: 1px solid #30363d; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  #header h1 { margin: 0; font-size: 16px; color: #58a6ff; }
  #header .stat { font-size: 13px; color: #8b949e; }
  #search { padding: 6px 10px; background: #0d1117; border: 1px solid #30363d; color: #c9d1d9; border-radius: 6px; font-size: 13px; width: 200px; }
  #search:focus { outline: none; border-color: #58a6ff; }
  #container { display: flex; height: calc(100vh - 57px); }
  #network { flex: 1; min-height: 400px; }
  #panel { width: 320px; padding: 16px; background: #161b22; border-left: 1px solid #30363d; overflow-y: auto; }
  #panel h2 { margin: 0 0 8px 0; font-size: 16px; color: #58a6ff; }
  #panel .desc { font-size: 13px; color: #c9d1d9; margin-bottom: 12px; line-height: 1.5; }
  #panel .path { font-size: 12px; color: #8b949e; font-family: monospace; word-break: break-all; margin-bottom: 12px; }
  #panel .link { display: inline-block; font-size: 13px; color: #58a6ff; text-decoration: none; }
  #panel .link:hover { text-decoration: underline; }
  #panel .empty { color: #8b949e; font-size: 13px; font-style: italic; }
  #panel .badge { display: inline-block; padding: 2px 8px; background: #21262d; border-radius: 12px; font-size: 11px; color: #8b949e; margin-right: 4px; }
  #panel .badge.root { background: #663c00; color: #ffa657; }
  @media (max-width: 768px) {
    #container { flex-direction: column; }
    #panel { width: auto; height: 200px; border-left: none; border-top: 1px solid #30363d; }
  }
</style>
</head>
<body>
<div id="header">
  <h1>Mandala Graph Explorer</h1>
  <span class="stat" id="stat">nodes: 0 / edges: 0</span>
  <input type="text" id="search" placeholder="Search node...">
</div>
<div id="container">
  <div id="network"></div>
  <div id="panel">
    <div class="empty">Click a node to see details</div>
  </div>
</div>
<script>
const GRAPH = __GRAPH_JSON__;

const nodesArray = GRAPH.nodes.map(n => ({
  id: n.id,
  label: n.id,
  title: n.description,
  color: n.id === "core_map" ? "#ffa657" : "#58a6ff",
  font: { color: "#c9d1d9", size: 14 },
  borderWidth: 2
}));

const edgesArray = GRAPH.edges.map(e => ({
  from: e.from,
  to: e.to,
  arrows: "to",
  color: { color: "#30363d", highlight: "#58a6ff" },
  smooth: { type: "continuous" }
}));

const container = document.getElementById("network");
const data = {
  nodes: new vis.DataSet(nodesArray),
  edges: new vis.DataSet(edgesArray)
};
const options = {
  nodes: { shape: "dot", size: 22, borderWidth: 2 },
  edges: { width: 1.5 },
  physics: { stabilization: { iterations: 200 }, barnesHut: { gravitationalConstant: -4000, springLength: 200 } },
  interaction: { hover: true, tooltipDelay: 100 }
};
const network = new vis.Network(container, data, options);

document.getElementById("stat").textContent = "nodes: " + GRAPH.nodes.length + " / edges: " + GRAPH.edges.length;

function findNode(id) {
  return GRAPH.nodes.find(n => n.id === id);
}

network.on("click", function(params) {
  const panel = document.getElementById("panel");
  if (params.nodes.length === 0) {
    panel.innerHTML = '<div class="empty">Click a node to see details</div>';
    return;
  }
  const id = params.nodes[0];
  const node = findNode(id);
  if (!node) return;
  const isRoot = id === "core_map";
  const badges = '<span class="badge' + (isRoot ? " root" : "") + '">' + node.type + '</span>' + (isRoot ? '<span class="badge root">root</span>' : '');
  const githubUrl = "https://github.com/voodoomushroomzzz-source/mandala-core/blob/main/" + node.path;
  panel.innerHTML =
    '<h2>' + id + '</h2>' +
    '<div>' + badges + '</div>' +
    '<div class="desc" style="margin-top:12px">' + (node.description || "(no description)") + '</div>' +
    '<div class="path">' + node.path + '</div>' +
    '<a class="link" href="' + githubUrl + '" target="_blank">Open on GitHub →</a>';
});

document.getElementById("search").addEventListener("input", function(e) {
  const q = e.target.value.toLowerCase();
  if (!q) return;
  const found = GRAPH.nodes.find(n => n.id.toLowerCase().includes(q));
  if (found) {
    network.selectNodes([found.id]);
    network.focus(found.id, { scale: 1.2, animation: true });
    network.emit("click", { nodes: [found.id] });
  }
});
</script>
</body>
</html>
"""


def write_html(graph_dict: dict, output_path: str = "output/mandala_graph.html"):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    graph_json = json.dumps(graph_dict, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("__GRAPH_JSON__", graph_json)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    return output_path
