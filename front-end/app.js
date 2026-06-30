const svg = document.querySelector("#graph");
const viewport = document.querySelector("#viewport");
const edgeLayer = document.querySelector("#edges");
const nodeLayer = document.querySelector("#nodes");
const statusEl = document.querySelector("#connection-status");
const nodeCountEl = document.querySelector("#node-count");
const edgeCountEl = document.querySelector("#edge-count");
const visitedCountEl = document.querySelector("#visited-count");
const toggleChromeBtn = document.querySelector("#toggle-chrome");
const fotoTooltip = document.querySelector("#foto-tooltip");
const fotoImg = document.querySelector("#foto-img");
const fotoTitulo = document.querySelector("#foto-titulo");

const state = {
  nodes: new Map(),
  pipes: [],
  rawGraph: null,
  scale: 1,
  offsetX: 0,
  offsetY: 0,
  draggingNode: null,
  panning: false,
  lastPointer: null,
  initialized: false,
  chromeCollapsed: localStorage.getItem("chromeCollapsed") === "1",
  graphSignature: null,
};

const GRID_STEP = 150;
const ORIGIN_X = 420;
const ORIGIN_Y = 280;
const FOTO_TOOLTIP_GAP = 18;
const FOTO_TOOLTIP_PADDING = 12;
const FALLBACK_DIRECTIONS = [
  { x: 0, y: -1 },
  { x: -1, y: 0 },
  { x: 0, y: 1 },
  { x: 1, y: 0 },
];

function ensureNode(rawNode, index, total) {
  let node = state.nodes.get(rawNode.id);
  if (!node) {
    node = {
      id: rawNode.id,
      gridX: index,
      gridY: 0,
      x: ORIGIN_X + index * GRID_STEP,
      y: ORIGIN_Y,
      pinned: false,
    };
    state.nodes.set(rawNode.id, node);
  }

  node.status = rawNode.status;
  node.tipo = rawNode.tipo;
  return node;
}

function applyGraph(graph) {
  const knownIds = new Set();
  state.rawGraph = graph;
  const visibleNodes = graph.nos.filter((node) => node.tipo === "bueiro");

  visibleNodes.forEach((rawNode, index) => {
    knownIds.add(rawNode.id);
    ensureNode(rawNode, index, visibleNodes.length);
  });

  for (const id of state.nodes.keys()) {
    if (!knownIds.has(id)) {
      state.nodes.delete(id);
    }
  }

  state.pipes = buildDrainagePipes(graph)
    .map((pipe) => ({
      ...pipe,
      source: state.nodes.get(pipe.origem),
      target: pipe.destino ? state.nodes.get(pipe.destino) : null,
    }))
    .filter((pipe) => pipe.source);

  applyOrthogonalLayout(visibleNodes);

  nodeCountEl.textContent = visibleNodes.length;
  edgeCountEl.textContent = state.pipes.length;
  visitedCountEl.textContent = visibleNodes.filter((node) => isVisitadoStatus(node.status)).length;
  statusEl.textContent = "Recebendo dados de /api/grafo";

  render();
  if (!state.initialized && graph.nos.length > 0) {
    fitView();
    state.initialized = true;
  }
}

function syncChromeState() {
  document.body.classList.toggle("chrome-collapsed", state.chromeCollapsed);
  toggleChromeBtn.textContent = state.chromeCollapsed ? "Mostrar painéis" : "Ocultar painéis";
  toggleChromeBtn.setAttribute(
    "aria-pressed",
    state.chromeCollapsed ? "true" : "false",
  );
  localStorage.setItem("chromeCollapsed", state.chromeCollapsed ? "1" : "0");
}

function directionFromAngle(angle, fallbackIndex) {
  if (typeof angle !== "number" || Number.isNaN(angle)) {
    return FALLBACK_DIRECTIONS[fallbackIndex % FALLBACK_DIRECTIONS.length];
  }

  const normalized = ((angle % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
  const quadrant = Math.round(normalized / (Math.PI / 2)) % 4;
  const directions = [
    { x: 0, y: -1 },
    { x: -1, y: 0 },
    { x: 0, y: 1 },
    { x: 1, y: 0 },
  ];
  return directions[quadrant];
}

function opposite(direction) {
  return { x: -direction.x, y: -direction.y };
}

function isDuto(id) {
  return String(id).includes("Duto");
}

function isVisitadoStatus(status) {
  return String(status || "").trim().toLowerCase() === "visitado";
}

function caminhoFoto(nomeArquivo) {
  return `/fotos/${encodeURIComponent(nomeArquivo)}?t=${Date.now()}`;
}

function fotoDoPipe(pipe) {
  if (!pipe.duto) {
    return null;
  }

  return state.rawGraph?.nos?.find((node) => node.id === pipe.duto && node.foto) || null;
}

function graphPointToScreen(point) {
  const rect = svg.getBoundingClientRect();
  return {
    x: rect.left + state.offsetX + point.x * state.scale,
    y: rect.top + state.offsetY + point.y * state.scale,
  };
}

function clampTooltipPosition(x, y) {
  const rect = fotoTooltip.getBoundingClientRect();
  const maxX = window.innerWidth - rect.width - FOTO_TOOLTIP_PADDING;
  const maxY = window.innerHeight - rect.height - FOTO_TOOLTIP_PADDING;

  return {
    x: Math.min(Math.max(x, FOTO_TOOLTIP_PADDING), Math.max(maxX, FOTO_TOOLTIP_PADDING)),
    y: Math.min(Math.max(y, FOTO_TOOLTIP_PADDING), Math.max(maxY, FOTO_TOOLTIP_PADDING)),
  };
}

function positionFotoTooltip(clientX, clientY) {
  const rect = fotoTooltip.getBoundingClientRect();
  let x = clientX + FOTO_TOOLTIP_GAP;
  let y = clientY + FOTO_TOOLTIP_GAP;

  if (x + rect.width + FOTO_TOOLTIP_PADDING > window.innerWidth) {
    x = clientX - rect.width - FOTO_TOOLTIP_GAP;
  }

  if (y + rect.height + FOTO_TOOLTIP_PADDING > window.innerHeight) {
    y = clientY - rect.height - FOTO_TOOLTIP_GAP;
  }

  const position = clampTooltipPosition(x, y);
  fotoTooltip.style.left = `${position.x}px`;
  fotoTooltip.style.top = `${position.y}px`;
}

function showFotoTooltip(pipe, fotoNo, event = null) {
  fotoTitulo.textContent = `Obstrução em ${fotoNo.id}`;
  fotoImg.src = caminhoFoto(fotoNo.foto);
  fotoTooltip.classList.remove("hidden");

  if (event) {
    positionFotoTooltip(event.clientX, event.clientY);
    return;
  }

  const point = graphPointToScreen(pipeLabelPoint(pipe));
  positionFotoTooltip(point.x, point.y);
}

function hideFotoTooltip() {
  fotoTooltip.classList.add("hidden");
}

toggleChromeBtn.addEventListener("click", () => {
  state.chromeCollapsed = !state.chromeCollapsed;
  syncChromeState();
});

syncChromeState();

function buildDirectedConnections(graph) {
  if (Array.isArray(graph.conexoes)) {
    return graph.conexoes;
  }

  const connections = [];
  graph.arestas.forEach((edge) => {
    const direction = directionFromAngle(edge.angulo, connections.length);
    connections.push(edge);
    connections.push({
      origem: edge.destino,
      destino: edge.origem,
      status: edge.status,
      angulo: angleFromDirection(opposite(direction)),
    });
  });
  return connections;
}

function angleFromDirection(direction) {
  if (direction.x === 0 && direction.y === -1) return 0;
  if (direction.x === -1 && direction.y === 0) return Math.PI / 2;
  if (direction.x === 0 && direction.y === 1) return Math.PI;
  return -Math.PI / 2;
}

function buildDrainagePipes(graph) {
  const nodeById = new Map(graph.nos.map((node) => [node.id, node]));
  const adjacency = new Map();
  const pipes = [];
  const seen = new Set();
  const connections = buildDirectedConnections(graph);

  connections.forEach((connection) => {
    if (!adjacency.has(connection.origem)) {
      adjacency.set(connection.origem, []);
    }
    adjacency.get(connection.origem).push(connection);
  });

  graph.nos
    .filter((node) => node.tipo === "bueiro")
    .forEach((bueiro) => {
      const exits = adjacency.get(bueiro.id) || [];

      exits.forEach((exit, exitIndex) => {
        const destino = nodeById.get(exit.destino);
        if (!destino) {
          return;
        }

        if (destino.tipo === "bueiro") {
          const key = [bueiro.id, destino.id].sort().join("|");
          if (seen.has(key)) return;
          seen.add(key);
          pipes.push({
            origem: bueiro.id,
            destino: destino.id,
            status: exit.status,
            angulo: exit.angulo,
            direction: directionFromAngle(exit.angulo, exitIndex),
          });
          return;
        }

        if (!isDuto(destino.id)) {
          return;
        }

        const nextBueiroConnection = (adjacency.get(destino.id) || []).find(
          (connection) =>
            connection.destino !== bueiro.id && nodeById.get(connection.destino)?.tipo === "bueiro",
        );
        const keyParts = [bueiro.id, destino.id];
        if (nextBueiroConnection) {
          keyParts.push(nextBueiroConnection.destino);
        }
        const key = keyParts.sort().join("|");
        if (seen.has(key)) {
          return;
        }
        seen.add(key);

        pipes.push({
          origem: bueiro.id,
          destino: nextBueiroConnection?.destino || null,
          duto: destino.id,
          status: exit.status,
          angulo: exit.angulo,
          direction: directionFromAngle(exit.angulo, exitIndex),
        });
      });
    });

  return pipes;
}

function applyOrthogonalLayout(visibleNodes) {
  if (visibleNodes.length === 0) {
    return;
  }

  const adjacency = new Map();
  visibleNodes.forEach((node) => adjacency.set(node.id, []));

  state.pipes.forEach((pipe) => {
    if (!pipe.destino) {
      return;
    }
    adjacency.get(pipe.origem)?.push({ id: pipe.destino, direction: pipe.direction });
    adjacency.get(pipe.destino)?.push({ id: pipe.origem, direction: opposite(pipe.direction) });
  });

  const occupied = new Map();
  const queue = [];
  const firstNode = state.nodes.get(visibleNodes[0].id);
  firstNode.gridX = 0;
  firstNode.gridY = 0;
  occupied.set("0,0", firstNode.id);
  queue.push(firstNode);

  const visited = new Set([firstNode.id]);
  while (queue.length > 0) {
    const current = queue.shift();
    const neighbors = adjacency.get(current.id) || [];

    neighbors.forEach((neighbor, neighborIndex) => {
      const node = state.nodes.get(neighbor.id);
      if (!node || visited.has(node.id)) {
        return;
      }

      let gridX = current.gridX + neighbor.direction.x;
      let gridY = current.gridY + neighbor.direction.y;
      let key = `${gridX},${gridY}`;
      let attempts = 0;

      while (occupied.has(key) && occupied.get(key) !== node.id && attempts < 16) {
        const distance = attempts + 2;
        gridX = current.gridX + neighbor.direction.x * distance;
        gridY = current.gridY + neighbor.direction.y * distance;
        key = `${gridX},${gridY}`;
        attempts += 1;
      }

      node.gridX = gridX;
      node.gridY = gridY;
      occupied.set(key, node.id);
      visited.add(node.id);
      queue.push(node);
    });
  }

  let disconnectedIndex = 0;
  for (const node of state.nodes.values()) {
    if (!visited.has(node.id)) {
      node.gridX = disconnectedIndex;
      node.gridY = 2;
      disconnectedIndex += 1;
    }

    if (!node.pinned) {
      node.x = ORIGIN_X + node.gridX * GRID_STEP;
      node.y = ORIGIN_Y + node.gridY * GRID_STEP;
    }
  }
}

async function fetchGraph() {
  try {
    const response = await fetch("/api/grafo", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const graph = await response.json();
    const graphSignature = JSON.stringify(graph);
    if (graphSignature !== state.graphSignature) {
      state.graphSignature = graphSignature;
      applyGraph(graph);
      return;
    }

    statusEl.textContent = "Recebendo dados de /api/grafo";
  } catch (error) {
    statusEl.textContent = `Sem conexao com o cerebro: ${error.message}`;
  }
}

function render() {
  edgeLayer.replaceChildren();
  nodeLayer.replaceChildren();

  for (const pipe of state.pipes) {
    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const pathData = pipePath(pipe);

    const pipeOuter = document.createElementNS("http://www.w3.org/2000/svg", "path");
    pipeOuter.classList.add("edge-pipe-outer");
    pipeOuter.setAttribute("d", pathData);
    group.append(pipeOuter);

    const pipeInner = document.createElementNS("http://www.w3.org/2000/svg", "path");
    pipeInner.classList.add("edge-pipe-inner");
    const bloqueado = pipe.status !== "livre";
    if (bloqueado) pipeInner.classList.add("bloqueada");
    pipeInner.setAttribute("d", pathData);
    group.append(pipeInner);

    if (bloqueado) {
      const fotoNo = fotoDoPipe(pipe);
      if (fotoNo) {
        group.classList.add("pipe-com-foto");
        group.setAttribute("tabindex", "0");
        group.setAttribute("aria-label", `Mostrar foto da obstrução em ${fotoNo.id}`);
        group.addEventListener("pointerenter", (event) => showFotoTooltip(pipe, fotoNo, event));
        group.addEventListener("pointermove", (event) => positionFotoTooltip(event.clientX, event.clientY));
        group.addEventListener("pointerleave", hideFotoTooltip);
        group.addEventListener("focus", () => showFotoTooltip(pipe, fotoNo));
        group.addEventListener("blur", hideFotoTooltip);
      }
    }

    edgeLayer.append(group);
  }

  for (const node of state.nodes.values()) {
    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    group.classList.add("node", node.tipo);
    if (isVisitadoStatus(node.status)) group.classList.add("visitado");
    group.dataset.id = node.id;
    group.setAttribute("transform", `translate(${node.x}, ${node.y})`);

    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    const size = 54;
    rect.setAttribute("x", -size / 2);
    rect.setAttribute("y", -size / 2);
    rect.setAttribute("width", size);
    rect.setAttribute("height", size);
    rect.setAttribute("rx", 3);
    group.append(rect);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.textContent = node.id;
    label.setAttribute("y", 44);
    group.append(label);

    group.addEventListener("pointerdown", (event) => startNodeDrag(event, node));
    nodeLayer.append(group);
  }

  viewport.setAttribute(
    "transform",
    `translate(${state.offsetX}, ${state.offsetY}) scale(${state.scale})`,
  );
}

function pipeEndpoint(pipe) {
  if (pipe.target) {
    return pipe.target;
  }

  return {
    x: pipe.source.x + pipe.direction.x * GRID_STEP,
    y: pipe.source.y + pipe.direction.y * GRID_STEP,
  };
}

function pipePath(pipe) {
  const target = pipeEndpoint(pipe);
  if (Math.abs(pipe.source.x - target.x) < 1 || Math.abs(pipe.source.y - target.y) < 1) {
    return `M ${pipe.source.x} ${pipe.source.y} L ${target.x} ${target.y}`;
  }

  const cornerX = pipe.source.x + pipe.direction.x * GRID_STEP;
  const cornerY = pipe.source.y + pipe.direction.y * GRID_STEP;
  return `M ${pipe.source.x} ${pipe.source.y} L ${cornerX} ${cornerY} L ${target.x} ${cornerY} L ${target.x} ${target.y}`;
}

function pipeLabelPoint(pipe) {
  const target = pipeEndpoint(pipe);
  return {
    x: (pipe.source.x + target.x) / 2,
    y: (pipe.source.y + target.y) / 2,
  };
}

function svgPoint(event) {
  const rect = svg.getBoundingClientRect();
  return {
    x: (event.clientX - rect.left - state.offsetX) / state.scale,
    y: (event.clientY - rect.top - state.offsetY) / state.scale,
    screenX: event.clientX,
    screenY: event.clientY,
  };
}

function startNodeDrag(event, node) {
  event.stopPropagation();
  const point = svgPoint(event);
  state.draggingNode = node;
  node.pinned = true;
  node.x = point.x;
  node.y = point.y;
  svg.setPointerCapture(event.pointerId);
}

svg.addEventListener("pointerdown", (event) => {
  hideFotoTooltip();
  state.panning = true;
  state.lastPointer = { x: event.clientX, y: event.clientY };
  svg.setPointerCapture(event.pointerId);
});

svg.addEventListener("pointermove", (event) => {
  if (state.draggingNode) {
    const point = svgPoint(event);
    state.draggingNode.x = point.x;
    state.draggingNode.y = point.y;
    render();
    return;
  }

  if (state.panning && state.lastPointer) {
    state.offsetX += event.clientX - state.lastPointer.x;
    state.offsetY += event.clientY - state.lastPointer.y;
    state.lastPointer = { x: event.clientX, y: event.clientY };
    render();
  }
});

svg.addEventListener("pointerup", () => {
  state.draggingNode = null;
  state.panning = false;
  state.lastPointer = null;
});

svg.addEventListener("wheel", (event) => {
  event.preventDefault();
  hideFotoTooltip();
  const rect = svg.getBoundingClientRect();
  const before = {
    x: (event.clientX - rect.left - state.offsetX) / state.scale,
    y: (event.clientY - rect.top - state.offsetY) / state.scale,
  };
  const factor = event.deltaY < 0 ? 1.1 : 0.9;
  state.scale = Math.min(Math.max(state.scale * factor, 0.25), 3.5);
  state.offsetX = event.clientX - rect.left - before.x * state.scale;
  state.offsetY = event.clientY - rect.top - before.y * state.scale;
  render();
});

function fitView() {
  const nodes = [...state.nodes.values()];
  const rect = svg.getBoundingClientRect();
  if (nodes.length === 0 || rect.width === 0 || rect.height === 0) return;

  const xs = nodes.map((node) => node.x);
  const ys = nodes.map((node) => node.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const width = Math.max(maxX - minX, 120);
  const height = Math.max(maxY - minY, 120);
  const padding = 96;
  state.scale = Math.min((rect.width - padding) / width, (rect.height - padding) / height, 1.6);
  state.scale = Math.max(state.scale, 0.35);
  state.offsetX = rect.width / 2 - ((minX + maxX) / 2) * state.scale;
  state.offsetY = rect.height / 2 - ((minY + maxY) / 2) * state.scale;
  render();
}

document.querySelector("#fit-view").addEventListener("click", fitView);
document.querySelector("#reset-pins").addEventListener("click", () => {
  for (const node of state.nodes.values()) {
    node.pinned = false;
  }
  if (state.rawGraph) {
    applyGraph(state.rawGraph);
  }
});

fetchGraph();
setInterval(fetchGraph, 600);
