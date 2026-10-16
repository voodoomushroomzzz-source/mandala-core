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
  #header { padding: 10px 16px; background: #161b22; border-bottom: 1px solid #30363d; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  #header h1 { margin: 0; font-size: 16px; color: #58a6ff; }
  #header .stat { font-size: 13px; color: #8b949e; }
  #header .badge { padding: 2px 8px; border-radius: 10px; font-size: 12px; background: #21262d; color: #8b949e; }
  #header .badge.warn { background: #4d1f1f; color: #f85149; }
  #header .badge.ok { background: #0f3d1f; color: #3fb950; }
  #filters { display: flex; gap: 12px; flex-wrap: wrap; }
  #filters label { font-size: 13px; color: #c9d1d9; display: flex; align-items: center; gap: 4px; cursor: pointer; user-select: none; }
  #filters input[type=checkbox] { cursor: pointer; }
  #search { padding: 6px 10px; background: #0d1117; border: 1px solid #30363d; color: #c9d1d9; border-radius: 6px; font-size: 13px; width: 180px; }
  #search:focus { outline: none; border-color: #58a6ff; }
  #container { display: flex; height: calc(100vh - 60px); }
  #network { flex: 1; min-height: 400px; }
  #panel { width: 340px; padding: 16px; background: #161b22; border-left: 1px solid #30363d; overflow-y: auto; }
  #panel h2 { margin: 0 0 8px 0; font-size: 16px; color: #58a6ff; }
  #panel .desc { font-size: 13px; color: #c9d1d9; margin-bottom: 12px; line-height: 1.5; }
  #panel .path { font-size: 12px; color: #8b949e; font-family: monospace; word-break: break-all; margin-bottom: 12px; }
  #panel .link { display: inline-block; font-size: 13px; color: #58a6ff; text-decoration: none; }
  #panel .link:hover { text-decoration: underline; }
  #panel .empty { color: #8b949e; font-size: 13px; font-style: italic; }
  #panel .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; margin-right: 4px; margin-bottom: 4px; }
  #panel .badge.honeycomb { background: #0d2f57; color: #58a6ff; }
  #panel .badge.honeycomb_unregistered { background: #4d1f1f; color: #f85149; }
  #panel .badge.root { background: #663c00; color: #ffa657; }
  #panel .badge.work { background: #0f3d1f; color: #3fb950; }
  #panel .badge.fruit { background: #2d1f4d; color: #a371f7; }
  #panel .badge.knowledge { background: #4d3d0f; color: #d29922; }
  #panel .field { font-size: 12px; color: #8b949e; margin-bottom: 4px; }
  #panel .field b { color: #c9d1d9; font-weight: 500; }
  @media (max-width: 768px) {
    #container { flex-direction: column; }
    #panel { width: auto; height: 220px; border-left: none; border-top: 1px solid #30363d; }
    #header { padding: 8px 12px; }
    #search { width: 140px; }
  }
</style>
</head>
<body>
<div id="header">
  <h1>Mandala Graph Explorer</h1>
  <span class="stat" id="stat">nodes: 0 / edges: 0 / seeds: 0</span>
  <span id="unreg-badge"></span>
  <span id="broken-badge"></span>
  <span id="islands-badge"></span>
  <span id="reachable-badge"></span>
  <div id="filters">
    <label><input type="checkbox" id="f-honeycomb" checked> Honeycombs</label>
    <label><input type="checkbox" id="f-work" checked> Works</label>
    <label><input type="checkbox" id="f-fruit" checked> Fruits</label>
    <label><input type="checkbox" id="f-knowledge" checked> Knowledge</label>
    <label><input type="checkbox" id="f-unregistered" checked> Unregistered</label>
  </div>
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

const COLORS = {
  honeycomb: { bg: "#58a6ff", border: "#1f6feb" },
  honeycomb_unregistered: { bg: "#f85149", border: "#da3633" },
  work: { bg: "#3fb950", border: "#2ea043" },
  fruit: { bg: "#a371f7", border: "#8957e5" },
  knowledge: { bg: "#d29922", border: "#bb8009" }
};

function nodeShape(type) {
  if (type === "work") return "box";
  if (type === "fruit") return "diamond";
  if (type === "knowledge") return "triangle";
  return "dot";
}

function nodeColor(n) {
  if (n.id === "core_map") return { background: "#ffa657", border: "#bb8009" };
  const c = COLORS[n.type] || COLORS.honeycomb;
  return { background: c.bg, border: c.border };
}

function buildNodes() {
  return GRAPH.nodes.map(n => ({
    id: n.id,
    label: n.id,
    title: n.description || "",
    color: nodeColor(n),
    shape: nodeShape(n.type),
    font: { color: "#c9d1d9", size: 13 },
    borderWidth: n.type === "honeycomb_unregistered" ? 3 : 2,
    borderWidthSelected: 4
  }));
}

function buildEdges() {
  return GRAPH.edges.map(e => {
    const isUnreg = e.type === "unregistered";
    return {
      from: e.from,
      to: e.to,
      arrows: "to",
      color: { color: isUnreg ? "#f85149" : "#30363d", highlight: "#58a6ff" },
      dashes: isUnreg,
      smooth: { type: "continuous" },
      title: e.type
    };
  });
}

const container = document.getElementById("network");
const data = {
  nodes: new vis.DataSet(buildNodes()),
  edges: new vis.DataSet(buildEdges())
};

const options = {
  nodes: { size: 22, borderWidth: 2 },
  edges: { width: 1.5 },
  physics: {
    stabilization: { iterations: 250 },
    barnesHut: { gravitationalConstant: -5000, springLength: 180, springConstant: 0.04 }
  },
  interaction: { hover: true, tooltipDelay: 100 }
};
const network = new vis.Network(container, data, options);

const a = GRAPH.analysis || {};
const unreg = a.unregistered_honeycombs || [];
const broken = a.broken_refs || [];
const islands = a.islands || [];
const reachable = a.reachable_from_core || 0;
const total = a.total_nodes || 0;

document.getElementById("stat").textContent =
  "nodes: " + GRAPH.nodes.length +
  " / edges: " + GRAPH.edges.length +
  " / seeds: " + (a.seeds_total || 0);

if (unreg.length > 0) {
  document.getElementById("unreg-badge").innerHTML =
    '<span class="badge warn">⚠ unregistered: ' + unreg.length + '</span>';
}
if (broken.length > 0) {
  document.getElementById("broken-badge").innerHTML =
    '<span class="badge warn">⚠ broken refs: ' + broken.length + '</span>';
}
if (islands.length > 0) {
  document.getElementById("islands-badge").innerHTML =
    '<span class="badge warn">⚠ islands: ' + islands.length + '</span>';
}
document.getElementById("reachable-badge").innerHTML =
  '<span class="badge">reachable: ' + reachable + '/' + total + '</span>';

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
  const typeClass = isRoot ? "root" : node.type;
  const badges =
    '<span class="badge ' + typeClass + '">' + (isRoot ? "root" : node.type) + '</span>' +
    (node.source ? '<span class="badge">source: ' + node.source + '</span>' : '');

  let fields = "";
  if (node.deadline) fields += '<div class="field"><b>deadline:</b> ' + node.deadline + '</div>';
  if (node.progress !== undefined && node.progress !== null && node.type === "work") {
    fields += '<div class="field"><b>progress:</b> ' + node.progress + '%</div>';
  }
  if (node.status) fields += '<div class="field"><b>status:</b> ' + node.status + '</div>';
  if (node.version) fields += '<div class="field"><b>version:</b> ' + node.version + '</div>';

  const githubUrl = node.path
    ? "https://github.com/voodoomushroomzzz-source/mandala-core/blob/main/" + node.path
    : null;
  const linkHtml = githubUrl
    ? '<a class="link" href="' + githubUrl + '" target="_blank">Open on GitHub →</a>'
    : '<div class="field">no path</div>';

  panel.innerHTML =
    '<h2>' + id + '</h2>' +
    '<div>' + badges + '</div>' +
    '<div class="desc" style="margin-top:12px">' + (node.description || "(no description)") + '</div>' +
    fields +
    (node.path ? '<div class="path" style="margin-top:8px">' + node.path + '</div>' : '') +
    linkHtml;
});

// Filters
const TYPE_TO_ID = {
  honeycomb: ["honeycomb"],
  work: ["work"],
  fruit: ["fruit"],
  knowledge: ["knowledge"],
  unregistered: ["honeycomb_unregistered"]
};

function applyFilters() {
  const active = {};
  ["honeycomb", "work", "fruit", "knowledge", "unregistered"].forEach(k => {
    active[k] = document.getElementById("f-" + k).checked;
  });

  const visibleIds = new Set();
  GRAPH.nodes.forEach(n => {
    let show = false;
    if (active.honeycomb && n.type === "honeycomb") show = true;
    if (active.work && n.type === "work") show = true;
    if (active.fruit && n.type === "fruit") show = true;
    if (active.knowledge && n.type === "knowledge") show = true;
    if (active.unregistered && n.type === "honeycomb_unregistered") show = true;
    if (n.id === "core_map") show = active.honeycomb;
    if (show) visibleIds.add(n.id);
  });

  GRAPH.nodes.forEach(n => {
    data.nodes.update({ id: n.id, hidden: !visibleIds.has(n.id) });
  });
  GRAPH.edges.forEach((e, i) => {
    const hidden = !visibleIds.has(e.from) || !visibleIds.has(e.to);
    data.edges.update({ id: data.edges.getIds()[i], hidden: hidden });
  });
}

["honeycomb", "work", "fruit", "knowledge", "unregistered"].forEach(k => {
  document.getElementById("f-" + k).addEventListener("change", applyFilters);
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
    graph_json = json.dumps(graph_dict, ensure_ascii=True).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__GRAPH_JSON__", graph_json)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    return output_path
