"use strict";

const $ = (id) => document.getElementById(id);
const canvas = $("plan"),
  ctx = canvas.getContext("2d");
const clone = (value) => JSON.parse(JSON.stringify(value));
const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const round = (number) => Math.round(number * 100) / 100;
const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const uid = (prefix) => prefix + "_" + crypto.randomUUID().slice(0, 12);
let token,
  caseId,
  state,
  frame,
  analysis,
  revisionId = null,
  status = "unsaved";
let savedState = "",
  selected = null,
  mode = "select",
  firstPoint = null,
  joinFirst = null;
let undoStack = [],
  redoStack = [],
  stateVersion = 0,
  analyzedVersion = -1,
  requestId = 0;
let uploading = false;
let latestJob = null;
let saving = false,
  calculating = false,
  analysisError = "",
  debounce,
  toastTimer,
  image = new Image();
let camera = { scale: 1, x: 0, y: 0 },
  drag = null,
  pointer = null,
  spaceDown = false;

function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    $("toast").hidden = true;
  }, 4500);
}
async function api(path, body) {
  const response = await fetch(
    path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Review-Token": token },
          body: JSON.stringify(body),
        },
  );
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "The operation could not be completed.");
  return result;
}
function dirty() {
  return state && JSON.stringify(state) !== savedState;
}
function element() {
  return selected ? state[selected.collection].find((item) => item.id === selected.id) : null;
}
function validGeometry(next) {
  for (const collection of ["walls", "openings"]) {
    for (const item of next[collection]) {
      if (
        ![...item.start, ...item.end].every(Number.isFinite) ||
        distance(item.start, item.end) <= (collection === "openings" ? 1 : 0.01)
      ) {
        toast("Use a valid segment length. Openings must be longer than 1 px.");
        return false;
      }
      const axis =
        item.start[1] === item.end[1]
          ? "horizontal"
          : item.start[0] === item.end[0]
            ? "vertical"
            : null;
      if (!axis) {
        toast("This move would tilt a connected wall. Check its coordinates.");
        return false;
      }
      item.axis = axis;
    }
  }
  return true;
}
function commit(edit) {
  if (!state || saving || uploading) return;
  const previous = clone(state),
    next = clone(state);
  edit(next);
  if (!validGeometry(next) || equal(previous, next)) return;
  undoStack.push(previous);
  if (undoStack.length > 100) undoStack.shift();
  redoStack = [];
  state = next;
  changed();
}
function changed() {
  stateVersion++;
  analyzedVersion = -1;
  if (!element()) selected = null;
  render();
  draw();
  clearTimeout(debounce);
  debounce = setTimeout(refreshAnalysis, 180);
}
async function refreshAnalysis() {
  if (!state) return;
  clearTimeout(debounce);
  const ticket = ++requestId,
    version = stateVersion,
    identifier = caseId;
  calculating = true;
  analysisError = "";
  renderStatus();
  try {
    const result = await api("/api/analyze", { case_id: identifier, state: clone(state) });
    if (ticket !== requestId || identifier !== caseId || version !== stateVersion) return;
    analysis = result;
    analyzedVersion = version;
  } catch (error) {
    if (ticket === requestId) {
      analysis = null;
      analysisError = error.message;
      toast(error.message);
    }
  } finally {
    if (ticket === requestId) {
      calculating = false;
      render();
      draw();
    }
  }
}
async function loadCase(identifier, fromUpload = false) {
  if (saving || (uploading && !fromUpload) || !identifier) return false;
  if (dirty() && !confirm("You have unsaved changes. Discard them and switch drawings?")) {
    $("caseSelect").value = caseId;
    return;
  }
  const ticket = ++requestId;
  clearTimeout(debounce);
  $("emptyMessage").hidden = false;
  try {
    const result = await api("/api/case?case=" + encodeURIComponent(identifier));
    if (ticket !== requestId) return;
    $("reviewNotice").textContent = result.notice;
    $("caseSelect").value = identifier;
    caseId = identifier;
    frame = result.frame;
    state = result.state;
    savedState = JSON.stringify(state);
    revisionId = result.revision_id;
    status = result.status;
    selected = null;
    firstPoint = null;
    joinFirst = null;
    undoStack = [];
    redoStack = [];
    stateVersion = 0;
    analyzedVersion = 0;
    analysis = result.analysis;
    calculating = false;
    analysisError = "";
    history.replaceState(null, "", "?case=" + encodeURIComponent(caseId));
    image = new Image();
    image.onload = () => {
      $("emptyMessage").hidden = true;
      fit();
    };
    image.onerror = () => toast("The review image could not be loaded.");
    image.src = "/api/image?case=" + encodeURIComponent(caseId);
    render();
    return true;
  } catch (error) {
    $("caseSelect").value = caseId || identifier;
    $("emptyMessage").hidden = !!state;
    toast(error.message);
    return false;
  }
}
function setMode(next) {
  mode = next;
  firstPoint = null;
  joinFirst = null;
  for (const button of document.querySelectorAll("[data-tool]"))
    button.classList.toggle("active", button.dataset.tool === next);
  const hints = {
    select: "Select an element; drag its endpoints. Press Delete to remove it.",
    wall: "Wall: click a start and an end point. Horizontal/vertical alignment is automatic.",
    opening: "Opening: choose two endpoints to cut the wall, then approve the opening.",
    join: "Join: select two wall endpoints to connect.",
    pan: "Pan: drag to move around. Scroll to zoom.",
  };
  $("hint").textContent = hints[next];
  canvas.style.cursor = next === "pan" ? "grab" : next === "select" ? "default" : "crosshair";
  draw();
}
function renderStatus() {
  for (const id of ["jobMode", "reuseJob", "jobSelect", "refreshJob"])
    $(id).disabled = uploading || saving;
  $("uploadButton").disabled = uploading || saving;
  $("caseSelect").disabled = uploading || saving || !$("caseSelect").options.length;
  for (const button of document.querySelectorAll("[data-tool]"))
    button.disabled = uploading || saving || !state;
  for (const id of ["saveDraft", "acceptReview", "download", "metricContinue", "undo", "redo"])
    $(id).disabled = true;
  if (!state) return;
  $("saveStatus").textContent = saving
    ? "Saving…"
    : dirty()
      ? "Unsaved changes"
      : status === "reviewed"
        ? "Reviewed"
        : status === "draft"
          ? "Draft"
          : "Not saved yet";
  $("saveStatus").className =
    "pill" + (dirty() ? " dirty" : status === "reviewed" ? " reviewed" : "");
  const current = analyzedVersion === stateVersion && !calculating;
  $("analysisStatus").textContent = analysisError
    ? "Geometry error"
    : current
      ? "Up to date"
      : "Calculating…";
  const ready = current && analysis?.validation.ready_to_review;
  $("acceptReview").disabled = !ready || saving || uploading;
  $("saveDraft").disabled = saving || uploading;
  $("download").disabled = status !== "reviewed" || dirty() || saving || uploading;
  $("metricContinue").disabled = $("download").disabled;
  $("undo").disabled = !undoStack.length || saving || uploading;
  $("redo").disabled = !redoStack.length || saving || uploading;
  $("readiness").textContent =
    analysisError ||
    (!current
      ? "Recalculating the graph…"
      : ready
        ? "No blocking issues. Check the drawing before approving its topology."
        : "Resolve the blocking issues. You can save your work as a draft.");
  $("readiness").className = "small " + (ready ? "ok" : "muted");
  $("revision").textContent = revisionId ? "Revision: " + revisionId : "No revision saved yet.";
}
function renderSelection() {
  const item = element();
  $("selectionEmpty").hidden = !!item;
  $("selectionEditor").hidden = !item;
  $("selectionType").textContent = item
    ? selected.collection === "walls"
      ? "wall"
      : "opening"
    : "—";
  if (!item) return;
  $("selectionId").textContent = item.id;
  $("axisInput").value = item.axis;
  for (const [id, value] of Object.entries({
    x1: item.start[0],
    y1: item.start[1],
    x2: item.end[0],
    y2: item.end[1],
  }))
    $(id).value = value;
  syncAxisFields();
  const opening = selected.collection === "openings";
  $("openingEditor").hidden = !opening;
  if (opening) {
    $("openingKind").value = item.kind;
    $("openingDecision").textContent = "Decision: " + item.decision;
  }
}
function syncAxisFields() {
  const horizontal = $("axisInput").value === "horizontal";
  $("x2").disabled = !horizontal;
  $("y2").disabled = horizontal;
  if (horizontal) $("y2").value = $("y1").value;
  else $("x2").value = $("x1").value;
}
function render() {
  if (!state) return;
  renderStatus();
  renderSelection();
  $("regionCount").textContent = analysis?.topology.regions.length ?? "—";
  $("linkCount").textContent = analysis?.topology.region_connectivity_graph.edges.length ?? "—";
  const issues = analysis?.validation.issues || [];
  $("issueCount").textContent = analysis
    ? issues.filter((item) => item.severity === "error").length
    : "—";
  $("issues").replaceChildren();
  if (analysisError) {
    const card = document.createElement("div");
    card.className = "issue";
    card.textContent = analysisError;
    $("issues").append(card);
  }
  if (!issues.length && analysis) {
    const good = document.createElement("div");
    good.className = "ok";
    good.textContent = "Geometry checks passed. Confirm that the result matches your drawing.";
    $("issues").append(good);
  }
  for (const issue of issues) {
    const card = document.createElement("div");
    card.className = "issue " + (issue.severity === "warning" ? "warning" : "");
    const message = document.createElement("div");
    message.textContent = issue.message;
    card.append(message);
    for (const id of issue.element_ids) {
      const collection = state.walls.some((item) => item.id === id)
        ? "walls"
        : state.openings.some((item) => item.id === id)
          ? "openings"
          : null;
      if (!collection) continue;
      const button = document.createElement("button");
      button.textContent = id;
      button.onclick = () => {
        selected = { collection, id };
        setMode("select");
        renderSelection();
        draw();
      };
      card.append(button);
    }
    $("issues").append(card);
  }
  $("openingList").replaceChildren();
  if (!state.openings.length) $("openingList").textContent = "No opening candidates.";
  for (const opening of state.openings) {
    const button = document.createElement("button");
    button.className = "opening-item " + opening.decision;
    const dot = document.createElement("span");
    dot.className = "dot";
    const name = document.createElement("span");
    name.textContent = opening.id;
    const detail = document.createElement("small");
    detail.textContent = opening.kind + " · " + opening.decision;
    button.append(dot, name, detail);
    button.onclick = () => {
      selected = { collection: "openings", id: opening.id };
      setMode("select");
      renderSelection();
      draw();
    };
    $("openingList").append(button);
  }
}
function size() {
  return { width: canvas.clientWidth, height: canvas.clientHeight };
}
function fit() {
  if (!frame) return;
  const { width, height } = size();
  camera.scale = Math.min((width - 80) / frame.width_px, (height - 80) / frame.height_px);
  camera.x = (width - frame.width_px * camera.scale) / 2;
  camera.y = (height - frame.height_px * camera.scale) / 2;
  draw();
}
function world(event) {
  const rect = canvas.getBoundingClientRect();
  return [
    (event.clientX - rect.left - camera.x) / camera.scale,
    (event.clientY - rect.top - camera.y) / camera.scale,
  ];
}
function drawLine(start, end, color, width = 2, dash = []) {
  ctx.beginPath();
  ctx.moveTo(...start);
  ctx.lineTo(...end);
  ctx.strokeStyle = color;
  ctx.lineWidth = width / camera.scale;
  ctx.setLineDash(dash.map((value) => value / camera.scale));
  ctx.stroke();
  ctx.setLineDash([]);
}
function draw() {
  const dpr = window.devicePixelRatio || 1,
    { width, height } = size();
  if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  if (!state) return;
  ctx.translate(camera.x, camera.y);
  ctx.scale(camera.scale, camera.scale);
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, frame.width_px, frame.height_px);
  if (image.complete && image.naturalWidth) {
    ctx.globalAlpha = Number($("photoOpacity").value);
    ctx.drawImage(image, 0, 0);
    ctx.globalAlpha = 1;
  }
  if ($("showRegions").checked && analyzedVersion === stateVersion && analysis) {
    for (const region of analysis.topology.regions) {
      const corners = region.corners_px_rotated;
      if (!corners.length) continue;
      ctx.beginPath();
      ctx.moveTo(...corners[0]);
      for (const point of corners.slice(1)) ctx.lineTo(...point);
      ctx.closePath();
      const unsupported = !region.rectangle_candidate,
        ambiguous = region.unresolved_opening_ids?.length;
      ctx.fillStyle = unsupported ? "#bf4b4b25" : ambiguous ? "#d99c342d" : "#6856ab20";
      ctx.fill();
      ctx.font = `${12 / camera.scale}px system-ui`;
      ctx.fillStyle = unsupported ? "#a54242" : ambiguous ? "#9a6b18" : "#66508f";
      ctx.fillText(region.id, corners[0][0] + 7 / camera.scale, corners[0][1] + 17 / camera.scale);
    }
  }
  for (const wall of state.walls) drawLine(wall.start, wall.end, "#147f85", 2.5);
  if (analyzedVersion === stateVersion && analysis)
    for (const path of analysis.topology.polygonization.dangles_px_rotated) {
      for (let i = 1; i < path.length; i++) drawLine(path[i - 1], path[i], "#ba5554", 2, [3, 4]);
    }
  for (const opening of state.openings)
    drawLine(
      opening.start,
      opening.end,
      opening.decision === "approved"
        ? "#23865a"
        : opening.decision === "rejected"
          ? "#a2aaa5"
          : "#d28a20",
      3,
      opening.decision === "approved" ? [] : [7, 4],
    );
  const item = element();
  if (item) {
    drawLine(item.start, item.end, "#5d4fb4", 4);
    for (const point of [item.start, item.end]) {
      ctx.beginPath();
      ctx.arc(...point, 6 / camera.scale, 0, Math.PI * 2);
      ctx.fillStyle = "#fff";
      ctx.fill();
      ctx.strokeStyle = "#5d4fb4";
      ctx.lineWidth = 2 / camera.scale;
      ctx.stroke();
    }
  }
  if (firstPoint && pointer)
    drawLine(firstPoint, constrained(firstPoint, pointer), "#6558ac", 2, [5, 4]);
  if (joinFirst) {
    const wall = state.walls.find((item) => item.id === joinFirst.id);
    if (wall) {
      ctx.beginPath();
      ctx.arc(...wall[joinFirst.endpoint], 8 / camera.scale, 0, Math.PI * 2);
      ctx.strokeStyle = "#6d4db0";
      ctx.lineWidth = 2 / camera.scale;
      ctx.stroke();
    }
  }
  $("zoom").textContent = Math.round(camera.scale * 100) + "%";
}
function project(point, a, b) {
  const dx = b[0] - a[0],
    dy = b[1] - a[1],
    denominator = dx * dx + dy * dy;
  const t = Math.max(
    0,
    Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / denominator),
  );
  return [a[0] + t * dx, a[1] + t * dy];
}
function snapPoint(point, endpointOnly = false, ignore = null) {
  let best = 12 / camera.scale,
    snapped = point;
  for (const wall of state.walls) {
    if (wall.id === ignore) continue;
    const candidates = endpointOnly
      ? [wall.start, wall.end]
      : [wall.start, wall.end, project(point, wall.start, wall.end)];
    for (const candidate of candidates) {
      const delta = distance(point, candidate);
      if (delta < best) {
        best = delta;
        snapped = candidate;
      }
    }
  }
  return snapped.map(round);
}
function constrained(start, end, axis, ignore = null) {
  axis ||= Math.abs(end[0] - start[0]) >= Math.abs(end[1] - start[1]) ? "horizontal" : "vertical";
  let point = axis === "horizontal" ? [end[0], start[1]] : [start[0], end[1]];
  const snapped = snapPoint(point, false, ignore);
  const normal = axis === "horizontal" ? 1 : 0;
  if (snapped[normal] === point[normal]) point = snapped;
  return point.map(round);
}
function nearestElement(point) {
  let best = 10 / camera.scale,
    match = null;
  for (const collection of ["walls", "openings"])
    for (const item of state[collection]) {
      const delta = distance(point, project(point, item.start, item.end));
      if (delta <= best) {
        best = delta;
        match = { collection, id: item.id };
      }
    }
  return match;
}
function nearestEndpoint(point) {
  let best = 14 / camera.scale,
    match = null;
  for (const wall of state.walls)
    for (const endpoint of ["start", "end"]) {
      const delta = distance(point, wall[endpoint]);
      if (delta < best) {
        best = delta;
        match = { id: wall.id, endpoint };
      }
    }
  return match;
}
function cutWalls(next, start, end, axis) {
  const along = axis === "horizontal" ? 0 : 1,
    normal = 1 - along;
  const [lo, hi] = [start[along], end[along]].sort((a, b) => a - b);
  next.walls = next.walls.flatMap((wall) => {
    if (wall.axis !== axis || wall.start[normal] !== start[normal]) return [wall];
    const [a, b] = [wall.start[along], wall.end[along]].sort((x, y) => x - y);
    if (Math.min(b, hi) <= Math.max(a, lo)) return [wall];
    const pieces = [];
    for (const [left, right] of [
      [a, Math.min(b, lo)],
      [Math.max(a, hi), b],
    ])
      if (right - left > 0.01) {
        const first = [...start],
          last = [...start];
        first[along] = left;
        last[along] = right;
        pieces.push({ ...wall, id: pieces.length ? uid("w") : wall.id, start: first, end: last });
      }
    return pieces;
  });
}
function addSegment(end) {
  const start = firstPoint,
    last = constrained(start, end);
  firstPoint = null;
  if (distance(start, last) <= 1) {
    toast("Choose two distinct endpoints.");
    draw();
    return;
  }
  const axis = start[1] === last[1] ? "horizontal" : "vertical";
  const id = uid(mode === "opening" ? "o" : "w");
  const collection = mode === "opening" ? "openings" : "walls";
  commit((next) => {
    if (collection === "openings") {
      const along = axis === "horizontal" ? 0 : 1,
        normal = 1 - along;
      const [lo, hi] = [start[along], last[along]].sort((a, b) => a - b);
      if (
        next.openings.some(
          (item) =>
            item.decision !== "rejected" &&
            item.axis === axis &&
            item.start[normal] === start[normal] &&
            Math.min(hi, Math.max(item.start[along], item.end[along])) -
              Math.max(lo, Math.min(item.start[along], item.end[along])) >
              0.01,
        )
      ) {
        toast("An opening candidate already covers this span.");
        return;
      }
      cutWalls(next, start, last, axis);
      next.openings.push({
        id,
        start,
        end: last,
        axis,
        evidence_ids: [],
        decision: "pending",
        kind: "door",
      });
    } else next.walls.push({ id, start, end: last, axis, evidence_ids: [] });
  });
  if (state[collection].some((item) => item.id === id)) {
    selected = { collection, id };
    setMode("select");
    renderSelection();
    draw();
  }
}
function joinEndpoint(match) {
  if (!joinFirst) {
    joinFirst = match;
    $("hint").textContent = "First endpoint selected. Choose the second wall endpoint.";
    draw();
    return;
  }
  const one = state.walls.find((item) => item.id === joinFirst.id),
    two = state.walls.find((item) => item.id === match.id);
  if (one.id === two.id) {
    toast("Choose two different walls.");
    return;
  }
  const a = one[joinFirst.endpoint],
    b = two[match.endpoint];
  let target;
  if (one.axis !== two.axis) target = one.axis === "horizontal" ? [b[0], a[1]] : [a[0], b[1]];
  else {
    const normal = one.axis === "horizontal" ? 1 : 0;
    if (a[normal] !== b[normal]) {
      toast("Align the normal coordinates of these parallel walls first.");
      return;
    }
    target = a;
  }
  commit((next) => {
    for (const collection of ["walls", "openings"])
      for (const item of next[collection])
        for (const endpoint of ["start", "end"]) {
          if (equal(item[endpoint], a) || equal(item[endpoint], b)) item[endpoint] = [...target];
        }
  });
  joinFirst = null;
  setMode("join");
}
canvas.addEventListener("pointerdown", (event) => {
  if (!state || saving || uploading || event.button === 2) return;
  canvas.focus();
  const point = world(event);
  if (mode === "pan" || spaceDown || event.button === 1) {
    event.preventDefault();
    drag = { type: "pan", x: event.clientX, y: event.clientY, camera: { ...camera } };
    canvas.setPointerCapture(event.pointerId);
    return;
  }
  if (mode === "wall" || mode === "opening") {
    if (!firstPoint) firstPoint = snapPoint(point);
    else addSegment(point);
    draw();
    return;
  }
  if (mode === "join") {
    const match = nearestEndpoint(point);
    if (match) joinEndpoint(match);
    else toast("Click closer to a wall endpoint.");
    return;
  }
  const current = element();
  if (current) {
    const endpoint = ["start", "end"].find(
      (key) => distance(point, current[key]) * camera.scale <= 10,
    );
    if (endpoint) {
      drag = { type: "endpoint", endpoint, before: clone(state), selected: { ...selected } };
      canvas.setPointerCapture(event.pointerId);
      return;
    }
  }
  selected = nearestElement(point);
  renderSelection();
  draw();
});
canvas.addEventListener("pointermove", (event) => {
  if (!state || uploading) return;
  pointer = world(event);
  $("position").textContent = `${Math.round(pointer[0])}, ${Math.round(pointer[1])} px`;
  if (drag?.type === "pan") {
    camera.x = drag.camera.x + event.clientX - drag.x;
    camera.y = drag.camera.y + event.clientY - drag.y;
    draw();
  } else if (drag?.type === "endpoint") {
    const item = element(),
      fixed = drag.endpoint === "start" ? "end" : "start";
    item[drag.endpoint] = constrained(item[fixed], pointer, item.axis, item.id);
    analyzedVersion = -1;
    draw();
  } else if (firstPoint) draw();
});
function finishDrag() {
  if (drag?.type === "endpoint") {
    const previous = drag.before;
    if (!validGeometry(state)) {
      state = previous;
      refreshAnalysis();
      draw();
    } else if (!equal(previous, state)) {
      undoStack.push(previous);
      redoStack = [];
      changed();
    } else refreshAnalysis();
  }
  drag = null;
}
canvas.addEventListener("pointerup", finishDrag);
canvas.addEventListener("pointercancel", () => {
  if (drag?.before) {
    state = drag.before;
    refreshAnalysis();
  }
  drag = null;
  render();
  draw();
});
canvas.addEventListener("contextmenu", (event) => event.preventDefault());
canvas.addEventListener(
  "wheel",
  (event) => {
    if (!state) return;
    event.preventDefault();
    const point = world(event);
    const factor = Math.exp(-event.deltaY * 0.0015),
      next = Math.max(0.08, Math.min(8, camera.scale * factor));
    camera.x += point[0] * (camera.scale - next);
    camera.y += point[1] * (camera.scale - next);
    camera.scale = next;
    draw();
  },
  { passive: false },
);
function undo(redo = false) {
  if (saving || uploading) return;
  const from = redo ? redoStack : undoStack,
    to = redo ? undoStack : redoStack;
  if (!from.length) return;
  to.push(clone(state));
  state = from.pop();
  firstPoint = null;
  joinFirst = null;
  changed();
}
function deleteSelected() {
  if (!selected) return;
  const current = { ...selected };
  commit((next) => {
    next[current.collection] = next[current.collection].filter((item) => item.id !== current.id);
  });
}
async function save(action) {
  if (!state || saving) return;
  finishDrag();
  saving = true;
  renderStatus();
  try {
    const result = await api("/api/save", {
      case_id: caseId,
      state: clone(state),
      parent_revision_id: revisionId,
      action,
    });
    state = result.state;
    revisionId = result.revision_id;
    status = result.status;
    savedState = JSON.stringify(state);
    analysis = result;
    analyzedVersion = stateVersion;
    toast(
      action === "accept"
        ? "Topology approved and saved. This revision contains pixel geometry only."
        : "Draft saved.",
    );
    return true;
  } catch (error) {
    toast(error.message);
    return false;
  } finally {
    saving = false;
    render();
    draw();
  }
}
$("caseSelect").onchange = () => loadCase($("caseSelect").value);
for (const button of document.querySelectorAll("[data-tool]"))
  button.onclick = () => {
    if (!saving && !uploading) setMode(button.dataset.tool);
  };
$("fit").onclick = fit;
$("undo").onclick = () => undo();
$("redo").onclick = () => undo(true);
$("showRegions").onchange = draw;
$("photoOpacity").oninput = draw;
$("axisInput").onchange = syncAxisFields;
$("x1").oninput = syncAxisFields;
$("y1").oninput = syncAxisFields;
$("applyCoordinates").onclick = () => {
  if (!selected) return;
  syncAxisFields();
  const start = [Number($("x1").value), Number($("y1").value)].map(round),
    end = [Number($("x2").value), Number($("y2").value)].map(round);
  commit((next) => {
    const item = next[selected.collection].find((item) => item.id === selected.id);
    item.start = start;
    item.end = end;
  });
};
$("deleteElement").onclick = deleteSelected;
$("openingKind").onchange = () =>
  commit((next) => {
    next.openings.find((item) => item.id === selected.id).kind = $("openingKind").value;
  });
$("approveOpening").onclick = () =>
  commit((next) => {
    next.openings.find((item) => item.id === selected.id).decision = "approved";
  });
$("rejectOpening").onclick = () => {
  commit((next) => {
    next.openings.find((item) => item.id === selected.id).decision = "rejected";
  });
  toast("Opening rejected. Add a wall or use 'Fill opening with wall' to close the gap.");
};
$("closeOpening").onclick = () =>
  commit((next) => {
    const opening = next.openings.find((item) => item.id === selected.id),
      along = opening.axis === "horizontal" ? 0 : 1,
      normal = 1 - along;
    const [lo, hi] = [opening.start[along], opening.end[along]].sort((a, b) => a - b);
    const covered = next.walls
      .filter((wall) => wall.axis === opening.axis && wall.start[normal] === opening.start[normal])
      .map((wall) => [
        Math.min(...[wall.start[along], wall.end[along]]),
        Math.max(...[wall.start[along], wall.end[along]]),
      ])
      .sort((a, b) => a[0] - b[0]);
    let cursor = lo;
    for (const [start, end] of [...covered, [hi, hi]]) {
      if (end <= cursor || start > hi) continue;
      if (start > cursor) {
        const a = [...opening.start],
          b = [...opening.start];
        a[along] = cursor;
        b[along] = Math.min(start, hi);
        next.walls.push({ id: uid("w"), start: a, end: b, axis: opening.axis, evidence_ids: [] });
      }
      cursor = Math.max(cursor, end);
      if (cursor >= hi) break;
    }
    opening.decision = "rejected";
  });
$("saveDraft").onclick = () => save("save_draft");
$("acceptReview").onclick = () => save("accept");
$("download").onclick = () => {
  if (!$("download").disabled)
    window.location.href = "/api/export?case=" + encodeURIComponent(caseId);
};
document.addEventListener("keydown", (event) => {
  if (uploading) return;
  if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
  if (event.code === "Space") {
    event.preventDefault();
    spaceDown = true;
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
    event.preventDefault();
    undo(event.shiftKey);
    return;
  }
  if (event.key === "Escape") {
    if (drag?.before) {
      state = drag.before;
      refreshAnalysis();
    }
    drag = null;
    firstPoint = null;
    joinFirst = null;
    draw();
  }
  if (event.key === "Delete" || event.key === "Backspace") {
    event.preventDefault();
    deleteSelected();
  }
  const tools = { v: "select", w: "wall", o: "opening", j: "join" };
  if (tools[event.key.toLowerCase()] && !saving) setMode(tools[event.key.toLowerCase()]);
});
document.addEventListener("keyup", (event) => {
  if (event.code === "Space") spaceDown = false;
});
window.addEventListener("blur", () => {
  spaceDown = false;
});
window.addEventListener("beforeunload", (event) => {
  if (dirty() || uploading) {
    event.preventDefault();
    event.returnValue = "";
  }
});
new ResizeObserver(draw).observe(canvas);
async function boot() {
  const result = await api("/api/bootstrap");
  token = result.token;
  for (const identifier of result.cases) {
    const option = document.createElement("option");
    option.value = identifier;
    option.textContent = result.labels[identifier] || identifier;
    $("caseSelect").append(option);
  }
  for (const job of result.jobs || []) rememberJob(job);
  const requestedJob = new URL(location.href).searchParams.get("job");
  if (requestedJob) {
    uploading = true;
    setMode("select");
    renderStatus();
    try {
      await followJob(await api("/jobs/" + encodeURIComponent(requestedJob)), true);
    } catch (error) {
      $("emptyMessage").textContent = error.message + " Open Pipeline jobs to inspect or retry.";
      toast(error.message);
    } finally {
      uploading = false;
      $("uploadStatus").hidden = true;
      if (latestJob) rememberJob(latestJob);
      renderStatus();
    }
    return;
  }
  const requested = new URL(location.href).searchParams.get("case");
  const initial = result.cases.includes(requested) ? requested : result.cases[0];
  $("caseSelect").value = initial;
  setMode("select");
  renderStatus();
  if (initial) await loadCase(initial);
  else {
    $("emptyMessage").textContent = "Upload a drawing to start your review.";
    $("saveStatus").textContent = "No drawing";
  }
}
function uploadMessage(message) {
  $("uploadStatus").textContent = message;
  $("uploadStatus").hidden = false;
}
$("uploadButton").onclick = () => {
  if (!saving && !uploading) $("uploadFile").click();
};
$("uploadFile").onchange = async () => {
  const file = $("uploadFile").files[0];
  $("uploadFile").value = "";
  if (!file || uploading || saving) return;
  if (!/\.(jpe?g|png)$/i.test(file.name) || !file.size || file.size > 20000000) {
    toast("Choose a JPEG or PNG drawing up to 20 MB.");
    return;
  }
  finishDrag();
  uploading = true;
  renderStatus();
  try {
    if (dirty()) {
      uploadMessage("Saving your current changes as a draft…");
      if (!(await save("save_draft")))
        throw new Error("Upload cancelled. Save or resolve your current draft first.");
    }
    uploadMessage("Uploading drawing…");
    const form = new FormData();
    form.append("image", file, file.name);
    form.append(
      "config",
      JSON.stringify({
        mode: $("jobMode").value,
        cache_policy: $("reuseJob").checked ? "reuse_job" : "fresh",
      }),
    );
    const response = await fetch("/jobs", {
      method: "POST",
      headers: { "X-Review-Token": token },
      body: form,
    });
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || "The drawing could not be uploaded.");
    await followJob(job, true);
  } catch (error) {
    toast(error.message);
  } finally {
    uploading = false;
    $("uploadStatus").hidden = true;
    if (latestJob) rememberJob(latestJob);
    renderStatus();
  }
};
boot().catch((error) => {
  $("emptyMessage").textContent = error.message;
  toast(error.message);
});

$("metricContinue").onclick = () => {
  if (!$("metricContinue").disabled)
    location.href = "/metric.html?case=" + encodeURIComponent(caseId);
};

function rememberJob(job) {
  let option = [...$("jobSelect").options].find((o) => o.value === job.job_id);
  if (!option) {
    option = document.createElement("option");
    option.value = job.job_id;
    $("jobSelect").append(option);
  }
  option.textContent = (job.filename || job.job_id) + " · " + job.state;
  $("jobSelect").value = job.job_id;
  latestJob = job;
  $("jobDetail").textContent =
    job.job_id +
    " · " +
    job.state +
    " · " +
    (job.stage || "") +
    (job.error ? " · " + job.error : "");
  $("cancelJob").disabled = !["uploaded", "processing"].includes(job.state);
  $("retryJob").disabled = uploading || !["failed", "cancelled"].includes(job.state);
}
async function followJob(job, fromUpload = false) {
  rememberJob(job);
  while (["uploaded", "processing"].includes(job.state)) {
    uploadMessage(
      "Job " +
        job.job_id +
        " · " +
        (job.stage || job.state) +
        " · Review opens when processing finishes.",
    );
    await new Promise((resolve) => setTimeout(resolve, 700));
    job = await api("/jobs/" + encodeURIComponent(job.job_id));
    rememberJob(job);
  }
  if (!["needs_review", "validated", "exported"].includes(job.state))
    throw new Error(job.error || "The job did not finish. Retry creates a new job.");
  if (![...$("caseSelect").options].some((o) => o.value === job.job_id)) {
    const option = document.createElement("option");
    option.value = job.job_id;
    option.textContent = job.filename;
    $("caseSelect").append(option);
  }
  if (!(await loadCase(job.job_id, fromUpload)))
    throw new Error("Job ready. Select its drawing to continue review.");
  toast(
    job.cache_hit
      ? "Existing job reused; no inference ran. Select and review the intended revision."
      : job.execution_mode?.startsWith("manual")
        ? "Manual preparation complete. Correct the drawing and approve its topology."
        : "Processing complete. Review topology and measurements before acceptance.",
  );
}
$("cancelJob").onclick = async () => {
  if (!latestJob) return;
  try {
    rememberJob(await api("/jobs/" + latestJob.job_id + "/cancel", {}));
  } catch (error) {
    toast(error.message);
  }
};
$("refreshJob").onclick = async () => {
  if (uploading || !$("jobSelect").value) return;
  try {
    const job = await api("/jobs/" + $("jobSelect").value);
    rememberJob(job);
    if (["needs_review", "validated", "exported"].includes(job.state)) await followJob(job);
  } catch (error) {
    toast(error.message);
  }
};
$("jobSelect").onchange = async () => {
  try {
    rememberJob(await api("/jobs/" + $("jobSelect").value));
  } catch (error) {
    toast(error.message);
  }
};
$("retryJob").onclick = async () => {
  if (uploading || !latestJob) return;
  uploading = true;
  renderStatus();
  try {
    await followJob(await api("/jobs/" + latestJob.job_id + "/retry", {}), true);
  } catch (error) {
    toast(error.message);
  } finally {
    uploading = false;
    $("uploadStatus").hidden = true;
    if (latestJob) rememberJob(latestJob);
    renderStatus();
  }
};
