/* 可视化节点工作台前端（原生 JS / SVG，零第三方依赖） */
"use strict";

const PORT_COMPAT = {
  project: ["project", "state", "text", "card", "log"],
  state: ["state"],
  artifact: ["artifact", "state", "text", "card", "log", "any"],
  log: ["log", "text", "card", "any"],
  text: ["text", "card", "log", "any"],
  card: ["card", "text", "log", "any"],
  confirmed: ["confirmed", "artifact", "log", "any"],
  knowledge_card: ["knowledge_card", "card", "text", "log", "artifact", "any"],
  style_card: ["style_card", "card", "text", "log", "artifact", "any"],
  injection: ["injection", "artifact", "log", "text", "any"],
  any: ["any"],
};

const NODE_W = 210;
const PORT_ROW_H = 22;
const NODE_HEAD_H = 34;

const state = {
  token: new URLSearchParams(location.search).get("token") || "",
  project: "",
  projectName: "",
  graphId: "",
  graph: null,
  nodeTypes: [],
  typeMap: new Map(),
  projects: [],
  selection: null,
  scale: 1,
  pan: { x: 0, y: 0 },
  drag: null,
  connect: null,
  saveTimer: null,
  run: null,
  awaiting: null,
  replay: null,
  templates: [],
  history: [],
  future: [],
  layoutReady: false,
};

const $ = (sel) => document.querySelector(sel);

function setStatus(text) {
  $("#status-text").textContent = text;
}

function logLine(text, kind) {
  const log = $("#log");
  const line = document.createElement("div");
  line.className = "line " + (kind || "");
  line.textContent = text;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

async function api(path, options) {
  const opts = Object.assign({}, options || {});
  opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  let url = path;
  if (state.token) {
    url += (url.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(state.token);
  }
  const resp = await fetch(url, opts);
  let data = null;
  try {
    data = await resp.json();
  } catch (err) {
    data = { ok: false, error: "响应不是 JSON（HTTP " + resp.status + "）" };
  }
  if (!resp.ok || data.ok === false) {
    const err = new Error((data && data.error) || "请求失败（HTTP " + resp.status + "）");
    err.payload = data;
    throw err;
  }
  return data;
}

function nodeType(type) {
  return state.typeMap.get(type) || null;
}

function defaultParams(type) {
  const spec = nodeType(type);
  const params = {};
  if (!spec) return params;
  const schema = spec.params_schema || {};
  const props = schema.properties || {};
  for (const [key, prop] of Object.entries(props)) {
    if (Object.prototype.hasOwnProperty.call(prop, "default")) {
      params[key] = prop.default;
    } else if (prop.enum && prop.enum.length) {
      params[key] = prop.enum[0];
    } else if (prop.type === "boolean") {
      params[key] = false;
    } else if (prop.type === "integer" || prop.type === "number") {
      params[key] = 0;
    } else {
      params[key] = "";
    }
  }
  return params;
}

function nodeSummary(node) {
  const t = nodeType(node.type);
  const label = (t && t.label) || node.type;
  if (node.type === "stage" && node.params && node.params.stage) {
    return label + " " + node.params.stage;
  }
  if (node.type === "start" && node.params && node.params.entry) {
    return label + "（入口 " + node.params.entry + "）";
  }
  return label;
}

/* ---------------- 启动与数据加载 ---------------- */

async function boot() {
  setStatus("加载节点类型…");
  const types = await api("/api/node-types");
  state.nodeTypes = types.types || [];
  state.typeMap = new Map(state.nodeTypes.map((item) => [item.type, item]));
  renderPalette();
  try {
    const tpl = await api("/api/templates");
    state.templates = tpl.templates || [];
  } catch (err) {
    state.templates = [];
  }

  setStatus("加载项目…");
  const projects = await api("/api/projects");
  state.projects = projects.projects || [];
  const select = $("#project-select");
  select.innerHTML = "";
  for (const p of state.projects) {
    const opt = document.createElement("option");
    opt.value = p.path;
    opt.textContent = p.name + "（阶段 " + p.stage + "）";
    select.appendChild(opt);
  }
  if (!state.projects.length) {
    setStatus("未发现项目：请先用 workbench.py init 创建项目");
    logLine("未发现项目。请先运行：workbench.py init <名称> --entry A", "warn");
    return;
  }
  const preferred = state.projects.find((p) => p.stage !== "done") || state.projects[0];
  select.value = preferred.path;
  await chooseProject(preferred.path);
  setStatus("就绪");
}

async function chooseProject(path) {
  state.project = path;
  state.projectName = (state.projects.find((p) => p.path === path) || {}).name || "";
  const info = await api("/api/workbench?project=" + encodeURIComponent(path));
  $("#version").textContent = "v" + info.version;
  await loadWorkflows();
  loadRunHistory();
}

async function loadWorkflows() {
  const data = await api("/api/workflows?project=" + encodeURIComponent(state.project));
  const graphs = data.graphs || [];
  const select = $("#graph-select");
  select.innerHTML = "";
  for (const g of graphs) {
    const opt = document.createElement("option");
    opt.value = g.graph_id;
    opt.textContent = g.name + "（" + g.graph_id + "）";
    select.appendChild(opt);
  }
  const empty = $("#canvas-empty");
  if (!graphs.length) {
    state.graph = null;
    state.graphId = "";
    empty.classList.remove("hidden");
    $("#nodes").innerHTML = "";
    $("#edges").innerHTML = "";
    renderInspector();
    renderRun();
    return;
  }
  empty.classList.add("hidden");
  const keep = graphs.some((g) => g.graph_id === state.graphId) ? state.graphId : graphs[0].graph_id;
  select.value = keep;
  await loadGraph(keep);
}

async function loadGraph(graphId) {
  const data = await api(
    "/api/workflows/" + encodeURIComponent(graphId) + "?project=" + encodeURIComponent(state.project)
  );
  state.graphId = graphId;
  state.graph = data.graph;
  state.selection = null;
  state.run = null;
  state.awaiting = null;
  $("#graph-select").value = graphId;
  renderGraph();
  renderRun();
  logLine("已加载流程图：" + state.graph.name + "（" + state.graphId + "）");
  setStatus("已加载 " + graphId);
}

async function newGraph() {
  if (!state.project) {
    logLine("请先选择项目", "warn");
    return;
  }
  let templateHint = "";
  if (state.templates.length) {
    templateHint = "\n\n可用模板（留空=空白流程图）：\n" + state.templates
      .map((t) => "- " + t.template_id + "：" + t.name)
      .join("\n");
  }
  const name = window.prompt("新流程图名称" + templateHint, "流程-" + new Date().toISOString().slice(0, 10));
  if (!name) return;
  let templateId = "";
  if (state.templates.length) {
    templateId = (window.prompt("模板 ID（留空=空白流程图）\n" + state.templates.map((t) => t.template_id).join(" / "), "") || "").trim();
  }
  const payload = { project: state.project, name };
  if (templateId) payload.template_id = templateId;
  const data = await api("/api/workflows/new", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await loadWorkflows();
  await loadGraph(data.graph_id);
}

/* ---------------- 节点库 ---------------- */

function renderPalette() {
  const list = $("#palette-list");
  list.innerHTML = "";
  const groups = new Map();
  for (const t of state.nodeTypes) {
    const key = t.category || "其他";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(t);
  }
  for (const [category, items] of groups) {
    const box = document.createElement("div");
    box.className = "palette-group";
    const h = document.createElement("h3");
    h.textContent = category;
    box.appendChild(h);
    for (const t of items) {
      const item = document.createElement("div");
      item.className = "palette-item";
      item.draggable = true;
      item.innerHTML = "<span class='label'>" + escapeHtml(t.label) + "</span>" +
        "<span class='type'>" + escapeHtml(t.type) + "</span>";
      item.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData("application/x-node-type", t.type);
        e.dataTransfer.effectAllowed = "copy";
      });
      item.addEventListener("dblclick", () => addNode(t.type, 120, 120));
      box.appendChild(item);
    }
    list.appendChild(box);
  }
}

function escapeHtml(text) {
  return String(text == null ? "" : text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ---------------- 坐标与画布 ---------------- */

function canvasRect() {
  return $("#canvas").getBoundingClientRect();
}

function screenToWorld(clientX, clientY) {
  const rect = canvasRect();
  return {
    x: (clientX - rect.left - state.pan.x) / state.scale,
    y: (clientY - rect.top - state.pan.y) / state.scale,
  };
}

function applyWorldTransform() {
  $("#world").style.transform =
    "translate(" + state.pan.x + "px," + state.pan.y + "px) scale(" + state.scale + ")";
  $("#btn-zoom-reset").textContent = Math.round(state.scale * 100) + "%";
}

function addNode(type, x, y) {
  if (!state.graph) {
    logLine("请先创建/加载流程图", "warn");
    return;
  }
  const spec = nodeType(type);
  if (!spec) return;
  const id = type + "-" + Math.random().toString(36).slice(2, 7);
  state.graph.nodes.push({
    id,
    type,
    label: spec.label,
    position: { x: Math.round(x), y: Math.round(y) },
    params: defaultParams(type),
  });
  state.selection = id;
  touchGraph();
  renderGraph();
}

function deleteNode(nodeId) {
  state.graph.nodes = state.graph.nodes.filter((n) => n.id !== nodeId);
  state.graph.edges = state.graph.edges.filter(
    (e) => e.from.node !== nodeId && e.to.node !== nodeId
  );
  state.selection = null;
  touchGraph();
  renderGraph();
}

function addEdge(fromNode, fromPort, toNode, toPort) {
  const fromType = (nodeType((state.graph.nodes.find((n) => n.id === fromNode) || {}).type) || { ports: {} });
  const outPort = (fromType.ports.out || []).find((p) => String(p).startsWith(fromPort + ":")) || fromPort;
  const fromTypeName = String(outPort).split(":")[0];
  const toSpec = nodeType((state.graph.nodes.find((n) => n.id === toNode) || {}).type) || { ports: {} };
  const inPort = (toSpec.ports.in || []).find((p) => String(p).startsWith(toPort + ":")) || toPort;
  const toTypeName = String(inPort).split(":")[0];
  const allowed = PORT_COMPAT[fromTypeName] || [];
  if (!allowed.includes(toTypeName) && fromTypeName !== toTypeName) {
    logLine("端口类型不兼容：" + fromTypeName + " → " + toTypeName, "warn");
    return;
  }
  if (fromNode === toNode) {
    logLine("不能连接到自身", "warn");
    return;
  }
  const dup = state.graph.edges.some(
    (e) => e.from.node === fromNode && e.from.port === fromPort && e.to.node === toNode && e.to.port === toPort
  );
  if (dup) return;
  state.graph.edges.push({
    id: "edge-" + Math.random().toString(36).slice(2, 8),
    from: { node: fromNode, port: fromPort },
    to: { node: toNode, port: toPort },
  });
  touchGraph();
  renderGraph();
}

/* ---------------- 渲染 ---------------- */

function renderGraph() {
  const nodesEl = $("#nodes");
  nodesEl.innerHTML = "";
  const nodes = (state.graph && state.graph.nodes) || [];
  const runSteps = new Map();
  if (state.run && state.run.run && state.run.run.steps) {
    for (const s of state.run.run.steps) runSteps.set(s.node_id, s);
  }
  for (const node of nodes) {
    const el = document.createElement("div");
    el.className = "node";
    if (node.disabled) el.classList.add("disabled");
    if (state.selection === node.id) el.classList.add("selected");
    const step = runSteps.get(node.id);
    if (step && step.status) el.classList.add("status-" + step.status);
    el.dataset.id = node.id;
    el.style.left = (node.position.x || 0) + "px";
    el.style.top = (node.position.y || 0) + "px";

    const spec = nodeType(node.type) || { ports: { in: [], out: [] } };
    const head = document.createElement("div");
    head.className = "node-head";
    head.innerHTML = "<span class='title'>" + escapeHtml(node.label || spec.label || node.type) + "</span>" +
      "<span class='badge'>" + escapeHtml(node.type) + "</span>";
    el.appendChild(head);

    const body = document.createElement("div");
    body.className = "node-body";
    const params = node.params || {};
    if (node.type === "stage") {
      body.innerHTML = "<div class='kv'><span>阶段</span><span>" + escapeHtml(params.stage || "?") + "</span></div>" +
        "<div class='kv'><span>自动门禁</span><span>" + (params.auto_gates ? "开" : "关") + "</span></div>";
    } else if (node.type === "start") {
      body.innerHTML = "<div class='kv'><span>项目</span><span>" + escapeHtml(params.project || "?") + "</span></div>" +
        "<div class='kv'><span>入口</span><span>" + escapeHtml(params.entry || "A") + "</span></div>";
    } else if (node.type === "confirm") {
      body.innerHTML = "<div class='kv'><span>确认点</span><span>" + escapeHtml((params.prompt || "").slice(0, 12)) + "…</span></div>";
    }
    el.appendChild(body);

    const ports = document.createElement("div");
    ports.className = "ports";
    const inCol = document.createElement("div");
    inCol.className = "col";
    for (const port of spec.ports.in || []) {
      const name = String(port).split(":")[0];
      const p = document.createElement("div");
      p.className = "port in";
      p.dataset.node = node.id;
      p.dataset.port = name;
      p.dataset.dir = "in";
      p.textContent = name;
      inCol.appendChild(p);
    }
    const outCol = document.createElement("div");
    outCol.className = "col";
    for (const port of spec.ports.out || []) {
      const name = String(port).split(":")[0];
      const p = document.createElement("div");
      p.className = "port out";
      p.dataset.node = node.id;
      p.dataset.port = name;
      p.dataset.dir = "out";
      p.textContent = name;
      outCol.appendChild(p);
    }
    ports.appendChild(inCol);
    ports.appendChild(outCol);
    el.appendChild(ports);

    el.addEventListener("pointerdown", (e) => {
      if (e.target.closest(".port")) return;
      selectNode(node.id);
    });
    head.addEventListener("pointerdown", (e) => beginNodeDrag(e, node));
    el.querySelectorAll(".port.out").forEach((p) => {
      p.addEventListener("pointerdown", (e) => beginConnect(e, node.id, p.dataset.port));
    });
    nodesEl.appendChild(el);
  }
  requestAnimationFrame(renderEdges);
  renderInspector();
  renderRun();
}

function portCenter(nodeId, port, dir) {
  const portEl = document.querySelector(
    '.port[data-node="' + cssEscape(nodeId) + '"][data-port="' + cssEscape(port) + '"][data-dir="' + dir + '"]'
  );
  if (!portEl) return null;
  const rect = portEl.getBoundingClientRect();
  const world = $("#world").getBoundingClientRect();
  return {
    x: (rect.left + rect.width / 2 - world.left) / state.scale,
    y: (rect.top + rect.height / 2 - world.top) / state.scale,
  };
}

function cssEscape(text) {
  if (window.CSS && CSS.escape) return CSS.escape(String(text));
  return String(text).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

function bezier(a, b) {
  const dx = Math.max(40, Math.abs(b.x - a.x) * 0.5);
  return "M " + a.x + " " + a.y +
    " C " + (a.x + dx) + " " + a.y + ", " + (b.x - dx) + " " + b.y + ", " + b.x + " " + b.y;
}

function renderEdges() {
  const svg = $("#edges");
  const nodes = (state.graph && state.graph.nodes) || [];
  if (nodes.length) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of nodes) {
      minX = Math.min(minX, n.position.x);
      minY = Math.min(minY, n.position.y);
      maxX = Math.max(maxX, n.position.x + NODE_W);
      maxY = Math.max(maxY, n.position.y + 320);
    }
    svg.setAttribute("width", Math.max(1200, maxX + 200));
    svg.setAttribute("height", Math.max(800, maxY + 200));
  }
  svg.innerHTML = "";
  if (!state.graph) return;
  for (const edge of state.graph.edges || []) {
    const a = portCenter(edge.from.node, edge.from.port, "out");
    const b = portCenter(edge.to.node, edge.to.port, "in");
    if (!a || !b) continue;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", bezier(a, b));
    path.setAttribute("class", "edge");
    path.addEventListener("click", (e) => {
      e.stopPropagation();
      if (window.confirm("删除这条连线？")) {
        state.graph.edges = state.graph.edges.filter((item) => item.id !== edge.id);
        touchGraph();
        renderGraph();
      }
    });
    svg.appendChild(path);
  }
  if (state.connect && state.connect.current) {
    const a = { x: state.connect.x, y: state.connect.y };
    const b = state.connect.current;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", bezier(a, b));
    path.setAttribute("class", "temp");
    svg.appendChild(path);
  }
}

function selectNode(nodeId) {
  state.selection = nodeId;
  renderGraph();
  const node = state.graph.nodes.find((n) => n.id === nodeId);
  if (node) setStatus("已选择：" + node.id + "（" + node.type + "）");
}

/* ---------------- 拖拽与连线 ---------------- */

function beginNodeDrag(event, node) {
  if (event.button !== 0) return;
  event.preventDefault();
  remember();
  const start = screenToWorld(event.clientX, event.clientY);
  state.drag = {
    node,
    dx: start.x - node.position.x,
    dy: start.y - node.position.y,
    moved: false,
  };
  selectNode(node.id);
}

function beginConnect(event, nodeId, port) {
  event.preventDefault();
  event.stopPropagation();
  const center = portCenter(nodeId, port, "out");
  if (!center) return;
  state.connect = { node: nodeId, port, x: center.x, y: center.y, current: null };
}

function bindGlobalHandlers() {
  window.addEventListener("pointermove", (event) => {
    if (state.drag) {
      const world = screenToWorld(event.clientX, event.clientY);
      const node = state.drag.node;
      node.position.x = Math.round(world.x - state.drag.dx);
      node.position.y = Math.round(world.y - state.drag.dy);
      state.drag.moved = true;
      const el = document.querySelector('.node[data-id="' + cssEscape(node.id) + '"]');
      if (el) {
        el.style.left = node.position.x + "px";
        el.style.top = node.position.y + "px";
      }
      renderEdges();
    }
    if (state.connect) {
      const world = screenToWorld(event.clientX, event.clientY);
      state.connect.current = world;
      renderEdges();
    }
  });

  window.addEventListener("pointerup", (event) => {
    if (state.drag) {
      if (state.drag.moved) touchGraph();
      state.drag = null;
    }
    if (state.connect) {
      const target = document.elementFromPoint(event.clientX, event.clientY);
      const portEl = target && target.closest ? target.closest(".port.in") : null;
      const active = state.connect;
      state.connect = null;
      if (portEl) {
        addEdge(active.node, active.port, portEl.dataset.node, portEl.dataset.port);
      } else {
        renderEdges();
      }
    }
  });

  $("#canvas").addEventListener("dragover", (event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  });
  $("#canvas").addEventListener("drop", (event) => {
    event.preventDefault();
    const type = event.dataTransfer.getData("application/x-node-type");
    if (!type) return;
    const world = screenToWorld(event.clientX, event.clientY);
    addNode(type, world.x - NODE_W / 2, world.y - 20);
  });
  $("#canvas").addEventListener("pointerdown", (event) => {
    if (event.target === $("#canvas") || event.target === $("#world") || event.target.id === "edges") {
      state.selection = null;
      renderGraph();
    }
    if (event.button === 1) {
      event.preventDefault();
      const start = { x: event.clientX, y: event.clientY, pan: Object.assign({}, state.pan) };
      const move = (e) => {
        state.pan.x = start.pan.x + (e.clientX - start.x);
        state.pan.y = start.pan.y + (e.clientY - start.y);
        applyWorldTransform();
        renderEdges();
      };
      const up = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    }
  });
  $("#canvas").addEventListener("wheel", (event) => {
    event.preventDefault();
    const rect = canvasRect();
    const mx = event.clientX - rect.left;
    const my = event.clientY - rect.top;
    const old = state.scale;
    const next = Math.min(2.2, Math.max(0.35, old * (event.deltaY > 0 ? 0.9 : 1.1)));
    state.pan.x = mx - ((mx - state.pan.x) / old) * next;
    state.pan.y = my - ((my - state.pan.y) / old) * next;
    state.scale = next;
    applyWorldTransform();
    renderEdges();
  }, { passive: false });

  window.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z" && !event.shiftKey) {
      event.preventDefault();
      undo();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && (event.key.toLowerCase() === "y" || (event.shiftKey && event.key.toLowerCase() === "z"))) {
      event.preventDefault();
      redo();
      return;
    }
    if (event.key === "Delete" || event.key === "Backspace") {
      if (state.selection && document.activeElement === document.body) {
        event.preventDefault();
        deleteNode(state.selection);
      }
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      saveGraph();
    }
  });
}

/* ---------------- 保存 / 校验 / 布局 ---------------- */

function remember() {
  if (!state.graph) return;
  state.history.push(JSON.stringify(state.graph));
  if (state.history.length > 60) state.history.shift();
  state.future = [];
}

function undo() {
  if (!state.graph || !state.history.length) {
    logLine("没有可撤销的操作", "warn");
    return;
  }
  state.future.push(JSON.stringify(state.graph));
  state.graph = JSON.parse(state.history.pop());
  state.selection = null;
  renderGraph();
  touchGraph();
  logLine("已撤销");
}

function redo() {
  if (!state.graph || !state.future.length) {
    logLine("没有可重做的操作", "warn");
    return;
  }
  state.history.push(JSON.stringify(state.graph));
  state.graph = JSON.parse(state.future.pop());
  state.selection = null;
  renderGraph();
  touchGraph();
  logLine("已重做");
}

function touchGraph() {
  if (!state.graph) return;
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(saveGraph, 700);
}

async function saveGraph() {
  if (!state.graph || !state.graphId) return;
  state.graph.updated_at = new Date().toISOString();
  try {
    const data = await api(
      "/api/workflows/" + encodeURIComponent(state.graphId) + "?project=" + encodeURIComponent(state.project),
      { method: "PUT", body: JSON.stringify({ graph: state.graph }) }
    );
    const warnings = (data.warnings || []).length;
    logLine("已保存：" + state.graphId + (warnings ? "（" + warnings + " 条提示）" : ""), "ok");
    setStatus("已保存");
  } catch (err) {
    logLine("保存失败：" + err.message, "err");
    setStatus("保存失败");
  }
}

async function validateGraph() {
  if (!state.graph) return;
  try {
    const data = await api("/api/workflows/validate", {
      method: "POST",
      body: JSON.stringify({ graph: state.graph }),
    });
    for (const item of data.errors || []) logLine("[错误] " + item, "err");
    for (const item of data.warnings || []) logLine("[提示] " + item, "warn");
    logLine(data.ok ? "校验通过" : "校验失败", data.ok ? "ok" : "err");
    setStatus(data.ok ? "校验通过" : "校验失败");
  } catch (err) {
    logLine("校验失败：" + err.message, "err");
  }
}

function autoLayout() {
  if (!state.graph) return;
  remember();
  const nodes = state.graph.nodes.slice();
  const rank = (node) => {
    if (node.type === "start") return 0;
    if (node.type === "stage") return 1 + parseInt(node.params.stage || "0", 10);
    if (node.type === "confirm") return 200;
    if (node.type === "end") return 300;
    return 150;
  };
  nodes.sort((a, b) => rank(a) - rank(b) || a.id.localeCompare(b.id));
  nodes.forEach((node, index) => {
    node.position.x = 80 + (index % 4) * 300;
    node.position.y = 120 + Math.floor(index / 4) * 190;
  });
  touchGraph();
  renderGraph();
  logLine("已应用自动布局", "ok");
}

/* ---------------- 检查器 ---------------- */

function renderInspector() {
  const box = $("#inspector-body");
  box.innerHTML = "";
  const node = state.graph && state.graph.nodes.find((n) => n.id === state.selection);
  if (!node) {
    box.innerHTML = "<p class='hint'>选择画布中的节点查看与编辑参数。</p>";
    $("#status-selection").textContent = "";
    return;
  }
  const spec = nodeType(node.type) || {};
  $("#status-selection").textContent = "选中：" + node.id;

  const title = document.createElement("div");
  title.className = "hint";
  title.textContent = "类型：" + node.type + " · ID：" + node.id;
  box.appendChild(title);

  const label = document.createElement("label");
  label.textContent = "显示名称";
  box.appendChild(label);
  const labelInput = document.createElement("input");
  labelInput.type = "text";
  labelInput.value = node.label || "";
  labelInput.addEventListener("input", () => {
    node.label = labelInput.value;
    touchGraph();
  });
  box.appendChild(labelInput);

  const schema = spec.params_schema || {};
  const props = schema.properties || {};
  for (const [key, prop] of Object.entries(props)) {
    const row = document.createElement("label");
    row.textContent = (prop.title || key) + (schema.required && schema.required.includes(key) ? " *" : "");
    box.appendChild(row);
    let input;
    if (prop.enum) {
      input = document.createElement("select");
      for (const value of prop.enum) {
        const opt = document.createElement("option");
        opt.value = String(value);
        opt.textContent = String(value);
        input.appendChild(opt);
      }
      input.value = String(node.params[key] != null ? node.params[key] : prop.enum[0]);
      input.addEventListener("change", () => {
        node.params[key] = input.value;
        touchGraph();
        renderGraph();
      });
    } else if (prop.type === "boolean") {
      input = document.createElement("input");
      input.type = "checkbox";
      input.checked = Boolean(node.params[key]);
      input.addEventListener("change", () => {
        node.params[key] = input.checked;
        touchGraph();
        renderGraph();
      });
    } else if (prop.type === "integer" || prop.type === "number") {
      input = document.createElement("input");
      input.type = "number";
      input.value = node.params[key] != null ? node.params[key] : 0;
      input.addEventListener("input", () => {
        node.params[key] = Number(input.value);
        touchGraph();
      });
    } else if (prop.type === "array" || prop.type === "object") {
      input = document.createElement("textarea");
      input.rows = 5;
      input.value = JSON.stringify(node.params[key] != null ? node.params[key] : (prop.type === "array" ? [] : {}), null, 2);
      input.addEventListener("change", () => {
        try {
          node.params[key] = JSON.parse(input.value);
          input.classList.remove("invalid");
          touchGraph();
        } catch (err) {
          input.classList.add("invalid");
          logLine("参数 " + key + " 不是合法 JSON：" + err.message, "err");
        }
      });
    } else {
      input = document.createElement("input");
      input.type = "text";
      input.value = node.params[key] != null ? node.params[key] : "";
      input.addEventListener("input", () => {
        node.params[key] = input.value;
        touchGraph();
      });
    }
    box.appendChild(input);
  }

  const row = document.createElement("div");
  row.className = "row";
  const toggle = document.createElement("button");
  toggle.textContent = node.disabled ? "启用节点" : "禁用节点";
  toggle.addEventListener("click", () => {
    node.disabled = !node.disabled;
    touchGraph();
    renderGraph();
  });
  const del = document.createElement("button");
  del.className = "danger";
  del.textContent = "删除节点";
  del.addEventListener("click", () => {
    if (window.confirm("删除节点 " + node.id + " 及其连线？")) deleteNode(node.id);
  });
  row.appendChild(toggle);
  row.appendChild(del);
  box.appendChild(row);
}

/* ---------------- 运行 ---------------- */

function renderRun() {
  const box = $("#run-status");
  box.innerHTML = "";
  const target = $("#run-target");
  target.innerHTML = "";
  const nodes = (state.graph && state.graph.nodes) || [];
  for (const node of nodes) {
    const opt = document.createElement("option");
    opt.value = node.id;
    opt.textContent = node.id + "（" + node.type + "）";
    target.appendChild(opt);
  }
  const mode = $("#run-mode").value;
  $("#run-target-label").classList.toggle("hidden", mode === "full");

  if (!state.run) {
    box.innerHTML = "<p class='hint'>尚未运行。勾选预演后点击「运行」。</p>";
    return;
  }
  const run = state.run.run;
  const summary = document.createElement("div");
  summary.className = "hint";
  summary.textContent = "运行 " + run.run_id + " · " + run.status + (run.dry_run ? " · dry-run" : "");
  box.appendChild(summary);
  for (const step of run.steps || []) {
    const line = document.createElement("div");
    line.className = "step " + step.status;
    line.innerHTML = "<span class='st'>" + step.status + "</span> " + escapeHtml(step.node_id) +
      (step.error ? " · " + escapeHtml(step.error) : "");
    box.appendChild(line);
  }
  if (state.awaiting) {
    const awaiting = document.createElement("div");
    awaiting.className = "awaiting";
    awaiting.innerHTML = "<b>等待人工确认</b><div class='prompt'>" +
      escapeHtml(state.awaiting.prompt || "") + "</div>" +
      (state.awaiting.detail_path ? "<div class='hint'>详情：" + escapeHtml(state.awaiting.detail_path) + "</div>" : "");
    const ok = document.createElement("button");
    ok.className = "primary";
    ok.textContent = "确认并继续";
    ok.addEventListener("click", () => confirmRun(true));
    const no = document.createElement("button");
    no.className = "danger";
    no.textContent = "取消运行";
    no.addEventListener("click", () => confirmRun(false));
    awaiting.appendChild(ok);
    awaiting.appendChild(no);
    box.appendChild(awaiting);
  }
  if (run.status === "failed") {
    const retry = document.createElement("button");
    retry.className = "primary";
    retry.textContent = "恢复重跑";
    retry.addEventListener("click", () => recoverRun(run.run_id));
    box.appendChild(retry);
  }
}

async function runFlow() {
  if (!state.graph || !state.graphId) {
    logLine("请先创建/加载流程图", "warn");
    return;
  }
  const mode = $("#run-mode").value;
  const payload = {
    project: state.project,
    graph_id: state.graphId,
    mode,
    dry_run: $("#run-dry").checked,
    auto_confirm: $("#run-auto-confirm").checked,
  };
  if (mode !== "full") payload.target_node = $("#run-target").value || null;
  logLine("开始运行（" + mode + "/" + (payload.dry_run ? "dry-run" : "live") + "）…");
  setStatus("运行中…");
  try {
    const data = await api("/api/runs", { method: "POST", body: JSON.stringify(payload) });
    state.run = data;
    state.awaiting = data.awaiting || null;
    for (const step of data.run.steps || []) {
      const kind = step.status === "failed" ? "err" : (step.status === "planned" || step.status === "succeeded" ? "ok" : "");
      logLine("[" + step.status + "] " + step.node_id + (step.error ? " · " + step.error : ""), kind);
    }
    setStatus("运行结束：" + data.run.status);
    renderGraph();
    renderRun();
  } catch (err) {
    logLine("运行失败：" + err.message, "err");
    setStatus("运行失败");
  }
}

async function confirmRun(approved) {
  if (!state.run) return;
  const runId = state.run.run.run_id;
  try {
    const data = await api("/api/runs/" + encodeURIComponent(runId) + "/confirm", {
      method: "POST",
      body: JSON.stringify({ approved, note: approved ? "webui 确认" : "webui 取消" }),
    });
    state.run = data;
    state.awaiting = data.awaiting || null;
    for (const step of data.run.steps || []) {
      logLine("[" + step.status + "] " + step.node_id, step.status === "failed" ? "err" : "ok");
    }
    setStatus("运行状态：" + data.run.status);
    renderGraph();
    renderRun();
  } catch (err) {
    logLine("确认失败：" + err.message, "err");
  }
}

/* ---------------- 运行历史 / 恢复 / 批量 ---------------- */

async function loadRunHistory() {
  const box = $("#run-history");
  if (!box) return;
  box.innerHTML = "";
  if (!state.project) return;
  try {
    const data = await api("/api/runs?project=" + encodeURIComponent(state.project) + "&limit=10");
    const runs = data.runs || [];
    if (!runs.length) {
      box.innerHTML = "<p class='hint'>暂无运行记录。</p>";
      return;
    }
    for (const run of runs) {
      const item = document.createElement("div");
      item.className = "run-history-item " + (run.status || "");
      item.textContent = run.run_id + " · " + run.status + (run.failed ? " · 失败 " + run.failed : "");
      item.title = "点击查看回放";
      item.addEventListener("click", () => openReplay(run.run_id));
      const recover = document.createElement("button");
      recover.className = "link";
      recover.textContent = "恢复";
      recover.title = "恢复重跑该运行";
      recover.addEventListener("click", (event) => {
        event.stopPropagation();
        recoverRun(run.run_id);
      });
      item.appendChild(recover);
      box.appendChild(item);
    }
  } catch (err) {
    box.innerHTML = "<p class='hint'>运行历史加载失败：" + escapeHtml(err.message) + "</p>";
  }
}

/* ---------------- 图导入 / 导出 ---------------- */

function exportGraph() {
  if (!state.graph || !state.graphId) {
    logLine("没有可导出的流程图", "warn");
    return;
  }
  const text = JSON.stringify(state.graph, null, 2) + "\n";
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = state.graphId + ".json";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  logLine("已导出 " + state.graphId + ".json");
}

async function importGraph(file) {
  if (!file) return;
  if (!state.project) {
    logLine("请先选择项目", "warn");
    return;
  }
  let graph = null;
  try {
    graph = JSON.parse(await file.text());
  } catch (err) {
    logLine("导入失败：不是合法 JSON（" + err.message + "）", "err");
    return;
  }
  if (!window.confirm("导入该流程图到当前项目？\n" + (graph.name || graph.graph_id || "未命名"))) return;
  try {
    const data = await api("/api/workflows/import", {
      method: "POST",
      body: JSON.stringify({ project: state.project, graph }),
    });
    logLine("已导入流程图 " + data.graph_id, "ok");
    setStatus("已导入 " + data.graph_id);
    await loadWorkflows();
    await loadGraph(data.graph_id);
  } catch (err) {
    logLine("导入失败：" + err.message, "err");
  }
}

/* ---------------- 运行回放 ---------------- */

function fmtMs(ms) {
  if (ms == null) return "-";
  return ms < 1000 ? ms + " ms" : (ms / 1000).toFixed(1) + " s";
}

async function openReplay(runId) {
  if (!state.project) return;
  try {
    const data = await api("/api/runs/" + encodeURIComponent(runId) + "/replay?project=" + encodeURIComponent(state.project));
    state.replay = data.replay;
    renderReplay();
    logLine("已加载回放 " + runId);
  } catch (err) {
    logLine("回放加载失败：" + err.message, "err");
  }
}

function renderReplay() {
  const box = $("#run-replay");
  if (!box) return;
  const replay = state.replay;
  if (!replay) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  box.classList.remove("hidden");
  box.innerHTML = "";
  const head = document.createElement("div");
  head.className = "replay-head";
  const title = document.createElement("b");
  title.textContent = "回放 " + replay.run_id;
  const close = document.createElement("button");
  close.className = "link";
  close.textContent = "关闭";
  close.addEventListener("click", () => {
    state.replay = null;
    renderReplay();
  });
  head.appendChild(title);
  head.appendChild(close);
  box.appendChild(head);
  const meta = document.createElement("div");
  meta.className = "hint";
  meta.textContent =
    "状态 " + replay.status + " · 总耗时 " + fmtMs(replay.total_duration_ms) +
    " · 步骤合计 " + fmtMs(replay.step_duration_ms) +
    (replay.slowest_node_id ? " · 最慢 " + replay.slowest_node_id + "（" + fmtMs(replay.slowest_duration_ms) + "）" : "") +
    (replay.recovered_from ? " · 恢复自 " + replay.recovered_from : "");
  box.appendChild(meta);
  if (replay.failed_node_id) {
    const fail = document.createElement("div");
    fail.className = "replay-failure";
    fail.textContent = "失败节点 " + replay.failed_node_id + "：" + (replay.failed_error || "");
    box.appendChild(fail);
  }
  for (const step of replay.steps || []) {
    const row = document.createElement("div");
    row.className = "replay-step " + step.status + (step.node_id === replay.failed_node_id ? " failed-node" : "");
    row.innerHTML = "<span class='idx'>" + String(step.index).padStart(2, "0") + "</span>" +
      "<span class='name'>" + escapeHtml(step.label) + "</span>" +
      "<span class='dur'>" + fmtMs(step.duration_ms) + "</span>";
    if (step.error) row.title = step.error;
    row.addEventListener("click", () => {
      if (!step.node_id) return;
      state.selection = step.node_id;
      renderGraph();
      renderInspector();
    });
    box.appendChild(row);
  }
}

async function recoverRun(runId, restoreState) {
  const restore = restoreState != null
    ? restoreState
    : window.confirm("恢复重跑该运行？\n确定 = 先回滚到运行前状态快照再重跑；取消 = 直接按当前图重跑。");
  try {
    const data = await api("/api/runs/" + encodeURIComponent(runId) + "/recover", {
      method: "POST",
      body: JSON.stringify({
        project: state.project,
        restore_state: restore,
        auto_confirm: true,
      }),
    });
    state.run = data;
    state.awaiting = data.awaiting || null;
    for (const step of data.run.steps || []) {
      logLine("[" + step.status + "] " + step.node_id, step.status === "failed" ? "err" : "ok");
    }
    setStatus("恢复运行：" + data.run.status);
    renderGraph();
    renderRun();
    loadRunHistory();
  } catch (err) {
    logLine("恢复失败：" + err.message, "err");
  }
}

async function runBatch() {
  if (!state.project) return;
  if (!window.confirm("批量预演项目内全部流程图？（dry-run，不写盘）")) return;
  try {
    const data = await api("/api/runs/batch", {
      method: "POST",
      body: JSON.stringify({ project: state.project, dry_run: true, auto_confirm: true }),
    });
    for (const item of data.results || []) {
      logLine("[" + (item.ok ? "OK" : "FAIL") + "] " + item.graph_id + " · " + item.status, item.ok ? "ok" : "err");
    }
    setStatus("批量预演完成：" + data.count + " 个流程图");
    loadRunHistory();
  } catch (err) {
    logLine("批量运行失败：" + err.message, "err");
  }
}

/* ---------------- 事件绑定 ---------------- */

async function openProjects() {
  try {
    const data = await api("/api/projects");
    state.projects = data.projects || [];
    renderProjects();
    $("#projects-panel").classList.remove("hidden");
  } catch (err) {
    logLine("加载项目面板失败：" + err.message, "err");
  }
}

function closeProjects() {
  $("#projects-panel").classList.add("hidden");
}

function renderProjects() {
  const body = $("#projects-body");
  if (!state.projects.length) {
    body.innerHTML = '<p class="hint">未发现项目。</p>';
    return;
  }
  const rows = state.projects.map((p) => {
    const last = p.last_run ? p.last_run.status + " · " + p.last_run.at : "—";
    return (
      '<tr data-path="' + escapeHtml(p.path) + '">' +
      "<td>" + escapeHtml(p.name) + "</td>" +
      "<td>" + escapeHtml(p.entry || "") + "</td>" +
      "<td>" + escapeHtml(p.stage || "") + "</td>" +
      "<td>" + escapeHtml(p.version || "") + "</td>" +
      "<td>" + (p.pending_gates || 0) + "</td>" +
      "<td>" + (p.artifacts || 0) + "</td>" +
      "<td>" + (p.workflows || 0) + "</td>" +
      "<td>" + (p.runs || 0) + "</td>" +
      "<td>" + escapeHtml(last) + "</td>" +
      "<td>" + escapeHtml(p.updated_at || "") + "</td>" +
      "</tr>"
    );
  });
  body.innerHTML =
    "<table><thead><tr><th>名称</th><th>入口</th><th>阶段</th><th>版本</th><th>待门禁</th>" +
    "<th>产物</th><th>流程</th><th>运行</th><th>最近运行</th><th>更新时间</th></tr></thead><tbody>" +
    rows.join("") +
    "</tbody></table>";
  body.querySelectorAll("tr[data-path]").forEach((row) => {
    row.addEventListener("click", async () => {
      await chooseProject(row.dataset.path);
      closeProjects();
      logLine("已切换项目：" + state.projectName);
    });
  });
}

function bindUi() {
  $("#project-select").addEventListener("change", async (e) => {
    try {
      await chooseProject(e.target.value);
      logLine("已切换项目：" + state.projectName);
    } catch (err) {
      logLine("切换项目失败：" + err.message, "err");
    }
  });
  $("#graph-select").addEventListener("change", async (e) => {
    try {
      await loadGraph(e.target.value);
    } catch (err) {
      logLine("加载流程图失败：" + err.message, "err");
    }
  });
  $("#btn-new-graph").addEventListener("click", () => newGraph().catch((err) => logLine("新建失败：" + err.message, "err")));
  $("#btn-save").addEventListener("click", () => saveGraph());
  $("#btn-validate").addEventListener("click", () => validateGraph());
  $("#btn-export").addEventListener("click", () => exportGraph());
  $("#btn-import").addEventListener("click", () => $("#file-import").click());
  $("#file-import").addEventListener("change", async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = "";
    await importGraph(file);
  });
  $("#btn-autolayout").addEventListener("click", () => autoLayout());
  $("#btn-zoom-in").addEventListener("click", () => {
    state.scale = Math.min(2.2, state.scale * 1.15);
    applyWorldTransform();
    renderEdges();
  });
  $("#btn-zoom-out").addEventListener("click", () => {
    state.scale = Math.max(0.35, state.scale / 1.15);
    applyWorldTransform();
    renderEdges();
  });
  $("#btn-zoom-reset").addEventListener("click", () => {
    state.scale = 1;
    state.pan = { x: 0, y: 0 };
    applyWorldTransform();
    renderEdges();
  });
  $("#btn-run").addEventListener("click", () => runFlow());
  $("#btn-run-history").addEventListener("click", () => loadRunHistory());
  $("#btn-run-batch").addEventListener("click", () => runBatch());
  $("#btn-undo").addEventListener("click", () => undo());
  $("#btn-redo").addEventListener("click", () => redo());
  $("#btn-projects").addEventListener("click", () => openProjects());
  $("#btn-close-projects").addEventListener("click", () => closeProjects());
  $("#inspector-body").addEventListener("focusin", () => remember());
  $("#run-mode").addEventListener("change", () => renderRun());
}

async function main() {
  bindUi();
  bindGlobalHandlers();
  applyWorldTransform();
  logLine("可视化节点工作台已就绪。");
  try {
    await boot();
  } catch (err) {
    logLine("初始化失败：" + err.message, "err");
    setStatus("初始化失败");
  }
}

main();
