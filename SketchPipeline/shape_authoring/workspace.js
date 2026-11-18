"use strict";
const $ = (id) => document.getElementById(id),
  clone = (x) => JSON.parse(JSON.stringify(x)),
  canvas = $("canvas"),
  ctx = canvas.getContext("2d");
const S = {
  token: "",
  job: "",
  doc: null,
  data: null,
  boxes: [],
  openings: [],
  selected: null,
  image: null,
  view: "sketch",
  tool: "select",
  dirty: false,
  busy: false,
  sizing: null,
  meta: {
    revision_id: null,
    state: {
      names: {},
      start_room_id: null,
      goal_room_id: null,
    },
  },
  undo: [],
  redo: [],
  ticket: 0,
  panes: [],
  zoom: 1,
  pan: [0, 0],
  gesture: null,
  issues: [],
  sizeQueue: Promise.resolve(),
  sizePending: 0,
  metaPending: 0,
  space: false,
};
const labels = {
  width_cm: "Width",
  depth_cm: "Depth",
  length_cm: "Length",
  clear_width_cm: "Clear width",
  height_cm: "Height",
  near_edge_offset_cm: "Position from end",
  wall_thickness_cm: "Wall thickness",
  wall_height_cm: "Wall height",
  door_height_cm: "Door height",
  floor_thickness_cm: "Floor thickness",
};
let toastTimer, frame;

function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("toast").hidden = true), 4400);
}

function status(message) {
  $("status").textContent = message;
}

function fail(error) {
  const map = {
    "Region interiors overlap":
      "Rooms overlap. Move or resize the highlighted shapes before saving.",
    "Rectangle lies outside the image": "Keep the shape inside the sketch.",
    "The plan changed. Reload before changing sizes.":
      "The plan changed. Reload it before editing sizes.",
  };
  const text = map[error.message] || error.message;
  status(text);
  toast(text);
}
async function api(path, body, headers = {}) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      "X-Shape-Token": S.token,
      ...(body !== undefined && !(body instanceof File)
        ? {
            "Content-Type": "application/json",
          }
        : {}),
      ...headers,
    },
    body: body === undefined ? undefined : body instanceof File ? body : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || "Something went wrong. Please try again.");
    error.status = response.status;
    throw error;
  }
  return data;
}

function uid(prefix) {
  return prefix + "_" + crypto.randomUUID().replaceAll("-", "");
}

function screen(name) {
  for (const id of ["landing", "analysis", "workspace"]) $(id).hidden = id !== name;
  $("new-sketch").hidden = name === "landing";
  if (name === "workspace") requestAnimationFrame(render);
}

function dirtyState() {
  const pending = S.dirty || S.sizePending > 0 || S.metaPending > 0 || S.busy;
  $("save-state").textContent =
    S.busy || S.sizePending || S.metaPending
      ? "Saving…"
      : S.dirty
        ? "Unsaved changes"
        : "Saved locally";
  $("save-state").classList.toggle("pending", pending);
  $("save").disabled = !S.dirty || S.busy;
  $("review-button").disabled = pending || !S.doc;
  $("settings-button").disabled = !!S.metaPending;
  $("undo").disabled = !S.undo.length || (pending && !S.dirty);
  $("redo").disabled = !S.redo.length || (pending && !S.dirty);
}

function snapshot() {
  return {
    boxes: clone(S.boxes),
    openings: clone(S.openings),
  };
}

function pushHistory(entry) {
  S.undo.push(entry);
  S.redo = [];
  dirtyState();
}

function changed(before) {
  if (JSON.stringify(before) !== JSON.stringify(snapshot())) {
    pushHistory({
      kind: "geometry",
      before,
      after: snapshot(),
    });
    S.dirty = true;
    S.meta.confirmation = null;
    dirtyState();
    render();
  }
}

function restore(state) {
  S.boxes = clone(state.boxes);
  S.openings = clone(state.openings);
  S.dirty = true;
  S.selected = null;
  S.meta.confirmation = null;
  render();
}

function name(id) {
  const box = region(id);
  const saved = S.doc?.topology.regions.find((item) => item.id === id);
  if (S.meta.state.names[id]) return S.meta.state.names[id];
  if (saved && (!box || saved.type === box.type) && !/^(Room|Corridor) \d+$/.test(saved.name))
    return saved.name;
  if (box) {
    return "Room " + (S.boxes.indexOf(box) + 1);
  }
  return opening(id)?.type === "door" ? "Door" : "Open passage";
}

function region(id) {
  return S.boxes.find((b) => b.id === id);
}

function opening(id) {
  return S.openings.find((o) => o.id === id);
}

function value(entity, param) {
  return S.sizing?.authoring?.physical_design.values.find(
    (v) => v.entity_id === entity && v.parameter === param,
  );
}

function polygonPoints(b) {
  const [x, y, X, Y] = b.bounds_px;
  return (
    b.points_px || [
      [x, y],
      [X, y],
      [X, Y],
      [x, Y],
    ]
  );
}

function setBounds(b, next) {
  const old = b.bounds_px;
  if (b.points_px)
    b.points_px = b.points_px.map((p) =>
      p.map(
        (v, axis) =>
          next[axis] +
          ((v - old[axis]) * (next[axis + 2] - next[axis])) / (old[axis + 2] - old[axis]),
      ),
    );
  b.bounds_px = next;
}

function labelPoint(b) {
  const points = polygonPoints(b),
    ys = [...new Set(points.map((p) => p[1]))].sort((a, b) => a - b);
  let best = [0, [(b.bounds_px[0] + b.bounds_px[2]) / 2, (b.bounds_px[1] + b.bounds_px[3]) / 2]];
  for (let i = 0; i < ys.length - 1; i++) {
    const y = (ys[i] + ys[i + 1]) / 2,
      xs = [];
    points.forEach((p, j) => {
      const q = points[(j + 1) % points.length];
      if (p[0] === q[0] && y > Math.min(p[1], q[1]) && y < Math.max(p[1], q[1])) xs.push(p[0]);
    });
    xs.sort((a, b) => a - b);
    for (let j = 0; j < xs.length; j += 2) {
      const area = (xs[j + 1] - xs[j]) * (ys[i + 1] - ys[i]);
      if (area > best[0]) best = [area, [(xs[j] + xs[j + 1]) / 2, y]];
    }
  }
  return best[1];
}

function containsPoint(b, point) {
  const p = polygonPoints(b);
  let inside = false;
  for (let i = 0, j = p.length - 1; i < p.length; j = i++) {
    if (distance(point, p[i], p[j]) < 0.01) return true;
    if (
      p[i][1] > point[1] !== p[j][1] > point[1] &&
      point[0] < ((p[j][0] - p[i][0]) * (point[1] - p[i][1])) / (p[j][1] - p[i][1]) + p[i][0]
    )
      inside = !inside;
  }
  return inside;
}

function shared() {
  const out = [];
  for (let i = 0; i < S.boxes.length; i++)
    for (let j = i + 1; j < S.boxes.length; j++) {
      const A = polygonPoints(S.boxes[i]),
        B = polygonPoints(S.boxes[j]);
      for (let a = 0; a < A.length; a++)
        for (let b = 0; b < B.length; b++) {
          const p = A[a],
            q = A[(a + 1) % A.length],
            r = B[b],
            t = B[(b + 1) % B.length];
          const axis = p[1] === q[1] ? 0 : 1,
            normal = 1 - axis;
          if (Math.abs(p[normal] - r[normal]) > 0.02 || Math.abs(p[normal] - t[normal]) > 0.02)
            continue;
          const lo = Math.max(Math.min(p[axis], q[axis]), Math.min(r[axis], t[axis]));
          const hi = Math.min(Math.max(p[axis], q[axis]), Math.max(r[axis], t[axis]));
          if (hi > lo)
            out.push({
              axis,
              normal,
              fixed: p[normal],
              lo,
              hi,
              ids: [S.boxes[i].id, S.boxes[j].id],
            });
        }
    }
  return out;
}

function supporting(o) {
  if (!o?.entity_ids) return null;
  return shared().find(
    (s) =>
      s.ids.every((id) => o.entity_ids.includes(id)) &&
      o.points_px.every(
        (p) =>
          Math.abs(p[s.normal] - s.fixed) < 1.2 &&
          p[s.axis] >= s.lo - 0.1 &&
          p[s.axis] <= s.hi + 0.1,
      ),
  );
}

function getIssues() {
  const issues = [];
  if (S.data?.status === "manual_required" && !S.boxes.length)
    issues.push({
      message: "Your image is ready. Add a room to start your plan.",
      ids: [],
    });
  for (const o of S.openings)
    if (!supporting(o))
      issues.push({
        message:
          "This connection no longer fits on its shared boundary. Move it back or delete it.",
        ids: [o.id, ...o.entity_ids],
      });
  for (const i of S.sizing?.issues || [])
    issues.push({
      message: i.message,
      ids: i.entity_ids || [],
    });
  return issues;
}

function renderLists() {
  for (const [id, items] of [
    ["entities", S.boxes],
    ["connections", S.openings],
  ]) {
    const root = $(id);
    root.replaceChildren();
    for (const item of items) {
      const button = document.createElement("button");
      button.classList.toggle("active", S.selected === item.id);
      button.setAttribute("aria-pressed", String(S.selected === item.id));
      const icon = document.createElement("span");
      icon.className = "entity-icon";
      icon.textContent =
        item.type === "room"
          ? "□"
          : item.type === "corridor_segment"
            ? "▭"
            : item.type === "door"
              ? "⌑"
              : "↔";
      const text = document.createElement("span");
      text.textContent = name(item.id);
      button.append(icon, text);
      if (S.meta.state.start_room_id === item.id || S.meta.state.goal_room_id === item.id) {
        const role = document.createElement("small");
        role.textContent = S.meta.state.start_room_id === item.id ? "Start" : "Goal";
        button.append(role);
      }
      button.onclick = () => select(item.id);
      root.append(button);
    }
  }
  $("region-count").textContent = S.boxes.length;
  $("opening-count").textContent = S.openings.length;
}

function select(id) {
  S.selected = id;
  render();
  renderInspector();
}

function render() {
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(draw);
  renderLists();
  dirtyState();
  $("empty-state").hidden = !!S.boxes.length;
  S.issues = getIssues();
  $("attention").hidden = !S.issues.length;
  $("issue-count").textContent = S.issues.length;
  $("issues").replaceChildren();
  for (const issue of S.issues) {
    const button = document.createElement("button");
    button.textContent = "!  " + issue.message;
    button.onclick = () => {
      if (issue.ids.length) select(issue.ids[0]);
    };
    $("issues").append(button);
  }
  $("refresh-sizes").hidden = !S.sizing?.issues?.some((i) => i.code === "topology_changed");
}

function draw() {
  if (!S.doc) return;
  const host = $("stage").getBoundingClientRect(),
    W = host.width,
    H = host.height,
    dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  S.panes = [];
  if (S.view === "compare") {
    drawPane("sketch", {
      x: 0,
      y: 0,
      w: W / 2,
      h: H,
    });
    drawPane("plan", {
      x: W / 2,
      y: 0,
      w: W / 2,
      h: H,
    });
    ctx.strokeStyle = "#d1d6c8";
    ctx.beginPath();
    ctx.moveTo(W / 2, 0);
    ctx.lineTo(W / 2, H);
    ctx.stroke();
  } else
    drawPane(S.view, {
      x: 0,
      y: 0,
      w: W,
      h: H,
    });
  $("zoom-label").textContent = Math.round(S.zoom * 100) + "%";
}

function drawPane(view, rect) {
  const dark = S.theme === "dark";
  const canonical = S.sizing?.preview?.canonical,
    plan = view === "plan" && canonical;
  let boxes = [],
    openings = [],
    extent,
    references = {};
  if (plan) {
    const points = Object.fromEntries(
      canonical.layout.vertices.map((v) => [v.id, [v.position_cm[0], -v.position_cm[1]]]),
    );
    references = points;
    for (const r of S.sizing.preview.display_regions || [
      ...canonical.layout.rooms,
      ...canonical.layout.corridors,
    ]) {
      const p = r.points_cm
        ? r.points_cm.map(([x, y]) => [x, -y])
        : r.boundary_vertex_ids.map((id) => points[id]);
      boxes.push({
        id: r.id,
        displayName: r.name,
        type: "room",
        points_px: p,
        bounds_px: [
          Math.min(...p.map((p) => p[0])),
          Math.min(...p.map((p) => p[1])),
          Math.max(...p.map((p) => p[0])),
          Math.max(...p.map((p) => p[1])),
        ],
      });
    }
    const walls = Object.fromEntries(canonical.layout.walls.map((w) => [w.id, w]));
    for (const o of canonical.layout.openings) {
      const w = walls[o.wall_id],
        p = [...points[w.start_vertex_id]],
        q = [...p],
        axis = w.axis === "x" ? 0 : 1,
        sign = axis === 0 ? 1 : -1;
      p[axis] += sign * (o.center_offset_cm - o.clear_width_cm / 2);
      q[axis] += sign * (o.center_offset_cm + o.clear_width_cm / 2);
      openings.push({
        id: o.id,
        type: o.type,
        points_px: [p, q],
      });
    }
    if (S.sizing.preview.display_openings)
      openings = S.sizing.preview.display_openings.map((o) => ({
        id: o.id,
        type: o.type,
        points_px: o.points_cm.map(([x, y]) => [x, -y]),
      }));
    const all = Object.values(points);
    extent = [
      Math.min(...all.map((p) => p[0])),
      Math.min(...all.map((p) => p[1])),
      Math.max(...all.map((p) => p[0])),
      Math.max(...all.map((p) => p[1])),
    ];
  } else {
    boxes = S.boxes;
    openings = S.openings;
    references = Object.fromEntries(
      S.doc.topology.junctions.map((j) => [j.id, j.geometry.points_px[0]]),
    );
    extent = [0, 0, ...S.doc.image_evidence.working_size_px];
    if (boxes.length) {
      const points = boxes.flatMap(polygonPoints),
        margin = 10;
      extent = [
        Math.min(...points.map((p) => p[0])) - margin,
        Math.min(...points.map((p) => p[1])) - margin,
        Math.max(...points.map((p) => p[0])) + margin,
        Math.max(...points.map((p) => p[1])) + margin,
      ];
    }
  }
  const width = Math.max(1, extent[2] - extent[0]),
    height = Math.max(1, extent[3] - extent[1]),
    scale = Math.min((rect.w - 60) / width, (rect.h - 110) / height) * S.zoom,
    tx = rect.x + rect.w / 2 - (extent[0] + width / 2) * scale + S.pan[0],
    ty = rect.y + (rect.h - 55) / 2 - (extent[1] + height / 2) * scale + S.pan[1];
  const transform = (p) => [p[0] * scale + tx, p[1] * scale + ty];
  const pane = {
    view,
    rect,
    scale,
    tx,
    ty,
    boxes,
    openings,
  };
  S.panes.push(pane);
  ctx.save();
  ctx.beginPath();
  ctx.rect(rect.x + 1, rect.y + 1, rect.w - 2, rect.h - 2);
  ctx.clip();
  if (!plan && S.image) {
    ctx.fillStyle = "#fff";
    const [imageWidth, imageHeight] = S.doc.image_evidence.working_size_px;
    ctx.fillRect(tx, ty, imageWidth * scale, imageHeight * scale);
    ctx.drawImage(S.image, tx, ty, imageWidth * scale, imageHeight * scale);
  }
  if (view === "plan" && !canonical) {
    ctx.fillStyle = "#7b8670";
    ctx.font = "13px system-ui";
    ctx.textAlign = "center";
    ctx.fillText(
      S.boxes.length ? "Save your plan to see suggested sizes." : "Add a room to see your plan.",
      rect.x + rect.w / 2,
      rect.y + rect.h / 2,
    );
    ctx.restore();
    return;
  }
  for (const b of boxes) {
    const [x, y, X, Y] = b.bounds_px,
      a = transform([x, y]),
      c = transform([X, Y]),
      selected = b.id === S.selected;
    ctx.fillStyle = selected
      ? dark
        ? "#83aff088"
        : "#f4bc9ab8"
      : b.type === "room"
        ? plan
          ? dark
            ? "#344156"
            : "#e9eeeb"
          : "#e9eeeb3a"
        : plan
          ? dark
            ? "#30465c"
            : "#d7e4df"
          : "#d7e4df44";
    const outline = polygonPoints(b).map(transform);
    ctx.beginPath();
    outline.forEach((p, i) => (i ? ctx.lineTo(...p) : ctx.moveTo(...p)));
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = selected
      ? (dark ? "#9bbcf1" : "#b44725")
      : plan
        ? dark
          ? "#a7bddb"
          : "#39463e"
        : b.type === "room"
          ? "#9e9059"
          : "#76958c";
    ctx.lineWidth = selected ? 2.5 : 1.5;
    ctx.stroke();
    const labelAt = transform(labelPoint(b));
    if (c[0] - a[0] > 38 && c[1] - a[1] > 24) {
      ctx.textAlign = "center";
      ctx.fillStyle = plan && dark ? "#e0eafa" : "#28372e";
      ctx.font = "13px system-ui";
      ctx.fillText(
        S.meta.state.names[b.id] || b.displayName || name(b.id),
        labelAt[0],
        labelAt[1] - 2,
      );
      if (plan && c[0] - a[0] > 65 && c[1] - a[1] > 38) {
        ctx.font = "12px system-ui";
        ctx.fillStyle = dark ? "#bccadd" : "#5c6a61";
        ctx.fillText(
          ((X - x) / 100).toFixed(2) + " × " + ((Y - y) / 100).toFixed(2) + " m",
          labelAt[0],
          labelAt[1] + 16,
        );
      }
    }
    if (selected && !plan) {
      for (const p of [
        [x, y],
        [X, y],
        [X, Y],
        [x, Y],
      ]) {
        const a = transform(p);
        ctx.fillStyle = "#fff";
        ctx.fillRect(a[0] - 4, a[1] - 4, 8, 8);
        ctx.strokeStyle = "#b44725";
        ctx.strokeRect(a[0] - 4, a[1] - 4, 8, 8);
      }
    }
  }
  for (const o of openings) {
    const a = transform(o.points_px[0]),
      b = transform(o.points_px[1]);
    ctx.lineCap = "butt";
    ctx.strokeStyle = plan ? "#f0f1eb" : "#fff9";
    ctx.lineWidth = 8;
    ctx.beginPath();
    ctx.moveTo(...a);
    ctx.lineTo(...b);
    ctx.stroke();
    ctx.strokeStyle = o.id === S.selected ? "#b7823f" : o.type === "door" ? "#9c7545" : "#54867a";
    ctx.lineWidth = o.id === S.selected ? 4 : 2.5;
    ctx.beginPath();
    ctx.moveTo(...a);
    ctx.lineTo(...b);
    ctx.stroke();
    if (o.id === S.selected) {
      for (const p of [a, b]) {
        ctx.fillStyle = "#fff";
        ctx.fillRect(p[0] - 4, p[1] - 4, 8, 8);
        ctx.strokeStyle = "#b7823f";
        ctx.strokeRect(p[0] - 4, p[1] - 4, 8, 8);
      }
      const authored = S.doc.topology.openings.find((x) => x.id === o.id),
        support = supporting(opening(o.id) || o);
      let reference = references[authored?.placement.reference_junction_id];
      if (!plan && S.dirty && support)
        reference = support.axis === 0 ? [support.lo, support.fixed] : [support.fixed, support.lo];
      if (reference) {
        const end = transform(reference);
        ctx.fillStyle = "#c59549";
        ctx.beginPath();
        ctx.arc(end[0], end[1], 5, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }
  ctx.restore();
  ctx.fillStyle = dark ? "#b8c8de" : "#7f8974";
  ctx.font = "12px system-ui";
  ctx.textAlign = "left";
  if (S.view === "compare")
    ctx.fillText(
      view === "sketch" ? "YOUR SKETCH" : "YOUR PLAN · SUGGESTED SIZES",
      rect.x + 17,
      24,
    );
  if (plan && S.sizing.preview_is_stale) {
    ctx.fillStyle = "#a57940";
    ctx.fillText("Previous valid plan · current choices need attention", rect.x + 17, rect.h - 84);
  }
}

function renderInspector() {
  const root = $("inspector-content");
  root.replaceChildren();
  const b = region(S.selected),
    o = opening(S.selected),
    entity = b || o;
  $("size-state").textContent = S.sizePending ? "Updating…" : "";
  if (!entity) {
    root.innerHTML =
      '<div class="inspector-empty"><h2>Nothing selected</h2><p>Select a room or connection to adjust it.</p></div>';
    return;
  }
  const h = document.createElement("h2");
  h.textContent = b ? "Room" : o.type === "door" ? "Door" : "Open passage";
  root.append(h);
  const label = document.createElement("label");
  label.textContent = "Name";
  const input = document.createElement("input");
  input.id = "entity-name";
  input.maxLength = 80;
  input.value = name(entity.id);
  input.disabled =
    !!S.metaPending ||
    (S.dirty &&
      !S.doc.topology.regions.some((e) => e.id === entity.id) &&
      !S.doc.topology.openings.some((e) => e.id === entity.id));
  input.setAttribute("aria-label", "Name");
  const id = entity.id;
  input.onchange = () => saveName(id, input.value);
  root.append(label, input);
  const kindLabel = document.createElement("label");
  kindLabel.textContent = "Type";
  const kind = document.createElement("select");
  kind.id = "entity-type";
  for (const [value, text] of b
    ? [["room", "Room"]]
    : [
        ["door", "Door"],
        ["open_passage", "Open passage"],
      ])
    kind.add(new Option(text, value));
  kind.value = entity.type;
  kind.onchange = () => {
    const before = snapshot();
    entity.type = kind.value;
    changed(before);
    renderInspector();
  };
  root.append(kindLabel, kind);
  if (o) {
    const related = document.createElement("p");
    related.className = "small";
    related.textContent = o.entity_ids.map(name).join(" ↔ ");
    root.append(related);
    const note = document.createElement("p");
    note.className = "small";
    note.textContent = "Position is measured from the highlighted end of the shared boundary.";
    root.append(note);
  }
  const fields = b
    ? b.type === "room"
      ? ["width_cm", "depth_cm"]
      : ["length_cm", "width_cm"]
    : ["clear_width_cm", "near_edge_offset_cm"];
  for (const param of fields) appendSizeField(root, id, param);
  if (b) {
    const keep = document.createElement("label");
    const check = document.createElement("input");
    check.type = "checkbox";
    check.checked = S.sizing?.options?.aspect_locks.includes(id) || false;
    check.disabled = S.dirty || !!S.sizePending;
    check.onchange = () => {
      const old = S.sizing?.options?.aspect_locks || [],
        next = check.checked ? [...new Set([...old, id])] : old.filter((x) => x !== id);
      sizeRequest(
        {
          aspect_locks: next,
        },
        true,
        {
          aspect_locks: old,
        },
      );
    };
    keep.append(check, document.createTextNode("Keep proportions"));
    root.append(keep);
    const targets = shared().filter((s) => s.ids.includes(id));
    if (targets.length) {
      const label = document.createElement("label");
      label.textContent = "Connect to";
      const select = document.createElement("select");
      for (const s of targets) {
        const other = s.ids.find((x) => x !== id);
        select.add(new Option(name(other), other));
      }
      const button = document.createElement("button");
      button.className = "outline";
      button.textContent = "Add door";
      button.style.marginTop = "10px";
      button.onclick = () => {
        const s = targets.find((s) => s.ids.includes(select.value));
        addOpening(s, (s.lo + s.hi) / 2, "door");
      };
      root.append(label, select, button);
    }
  }
  if (S.dirty) {
    const p = document.createElement("p");
    p.className = "small";
    p.textContent = "Save shape changes to update suggested sizes.";
    root.append(p);
  }
}

function appendSizeField(root, id, param) {
  const current = value(id, param),
    label = document.createElement("label");
  label.className = "field-top";
  label.textContent = labels[param];
  const badge = document.createElement("span");
  badge.className = "badge" + (current?.origin === "user_override" ? " custom" : "");
  badge.textContent = current?.origin === "user_override" ? "Custom" : "Suggested";
  label.append(badge);
  const row = document.createElement("div");
  row.className = "field-row";
  const input = document.createElement("input");
  input.type = "number";
  input.step = ".01";
  input.min = param === "near_edge_offset_cm" ? "0" : ".01";
  input.max = "10000";
  input.setAttribute("aria-label", labels[param] + " in metres");
  if (current?.value !== undefined) input.value = (current.value / 100).toFixed(2);
  input.disabled =
    !current ||
    S.dirty ||
    !!S.sizePending ||
    S.sizing?.issues?.some((i) => i.code === "topology_changed");
  input.onchange = () => {
    if (!input.reportValidity()) return;
    sizeRequest({
      edits: [
        {
          entity_id: id,
          parameter: param,
          value: Number(input.value),
          unit: "m",
        },
      ],
    });
  };
  const unit = document.createElement("span");
  unit.textContent = "m";
  const lock = document.createElement("button");
  lock.textContent = current?.locked ? "●" : "○";
  lock.className = current?.locked ? "locked" : "";
  lock.title = current?.locked ? "Unlock size" : "Lock size";
  lock.setAttribute("aria-label", lock.title + " " + labels[param]);
  lock.disabled = input.disabled;
  lock.onclick = () =>
    sizeRequest({
      edits: [
        {
          entity_id: id,
          parameter: param,
          action: current.locked ? "unlock" : "lock",
        },
      ],
    });
  const reset = document.createElement("button");
  reset.textContent = "↺";
  reset.title = "Reset size";
  reset.setAttribute("aria-label", "Reset " + labels[param]);
  reset.disabled = input.disabled;
  reset.onclick = () =>
    sizeRequest({
      edits: [
        {
          entity_id: id,
          parameter: param,
          action: "reset",
        },
      ],
    });
  row.append(input, unit, lock, reset);
  root.append(label, row);
}
async function saveName(id, text) {
  if (!text.trim()) {
    toast("Give this item a name.");
    renderInspector();
    return;
  }
  const state = clone(S.meta.state);
  state.names[id] = text.trim();
  await saveMeta(state);
  render();
}
async function saveMeta(state, history = true) {
  const ticket = S.ticket,
    before = clone(S.meta.state);
  S.metaPending++;
  dirtyState();
  renderInspector();
  try {
    const data = await api("/shape-jobs/" + S.job + "/workspace", {
      base_revision_id: S.doc.revision_id,
      base_workspace_revision_id: S.meta.revision_id,
      state,
    });
    if (ticket !== S.ticket) return;
    S.meta = data;
    if (history && JSON.stringify(before) !== JSON.stringify(state))
      pushHistory({
        kind: "metadata",
        before,
        after: clone(state),
      });
    toast("Plan details saved.");
    render();
    return true;
  } catch (e) {
    if (ticket === S.ticket) fail(e);
    return false;
  } finally {
    if (ticket === S.ticket) {
      S.metaPending--;
      dirtyState();
      renderInspector();
    }
  }
}

function previousSizeRequest(request) {
  const edits = [];
  for (const edit of request.edits || []) {
    const v = value(edit.entity_id, edit.parameter);
    if (!v) continue;
    if (v.origin === "user_override")
      edits.push({
        entity_id: v.entity_id,
        parameter: v.parameter,
        value: v.value,
        unit: "cm",
        locked: v.locked,
      });
    else {
      edits.push({
        entity_id: v.entity_id,
        parameter: v.parameter,
        action: "reset",
      });
      if (v.locked)
        edits.push({
          entity_id: v.entity_id,
          parameter: v.parameter,
          action: "lock",
        });
    }
  }
  return {
    edits,
  };
}

function sizeRequest(request, history = true, inverse = null) {
  const ticket = S.ticket,
    job = S.job;
  if (S.dirty) {
    toast("Save your shape changes first.");
    return Promise.resolve();
  }
  const previous = inverse || previousSizeRequest(request);
  S.sizePending++;
  dirtyState();
  renderInspector();
  S.sizeQueue = S.sizeQueue
    .catch(() => {})
    .then(async () => {
      if (ticket !== S.ticket) return;
      try {
        const revision = S.doc.revision_id;
        const next = await api("/shape-jobs/" + job + "/sizing", {
          base_revision_id: S.doc.revision_id,
          base_sizing_revision_id: S.sizing?.authoring?.revision_id || null,
          request,
        });
        if (ticket !== S.ticket || revision !== S.doc.revision_id) return;
        S.sizing = next;
        S.meta.confirmation = null;
        if (history)
          pushHistory({
            kind: "size",
            before: previous,
            after: request,
          });
        status(
          next.status === "ready"
            ? "Suggested plan updated."
            : next.issues.map((i) => i.message).join(" "),
        );
        render();
      } catch (e) {
        if (ticket === S.ticket) fail(e);
      } finally {
        if (ticket === S.ticket) {
          S.sizePending--;
          dirtyState();
          renderInspector();
        }
      }
    });
  return S.sizeQueue;
}
async function saveGeometry() {
  if (!S.dirty) return;
  S.busy = true;
  dirtyState();
  const ticket = S.ticket,
    job = S.job,
    payload = {
      base_revision_id: S.doc.revision_id,
      boxes: clone(S.boxes),
      openings: clone(S.openings),
    },
    queue = S.sizeQueue;
  try {
    await queue;
    if (ticket !== S.ticket) return;
    const saved = await api("/shape-jobs/" + job + "/edit", payload);
    if (ticket !== S.ticket) return;
    S.doc = saved.authoring;
    S.data = {
      ...S.data,
      edit_diagnostics: saved.diagnostics,
    };
    S.dirty = false;
    S.sizing = await api("/shape-jobs/" + S.job + "/sizing");
    S.meta = await api("/shape-jobs/" + S.job + "/workspace");
    if (S.sizing.status === "not_sized") await sizeRequest({}, false);
    toast(
      saved.diagnostics.length
        ? "Shapes saved. Some connections need attention."
        : "Shape changes saved.",
    );
    render();
    renderInspector();
  } catch (e) {
    fail(e);
  } finally {
    if (ticket === S.ticket) {
      S.busy = false;
      dirtyState();
    }
  }
}
async function refreshSizes() {
  if (S.dirty) {
    toast("Save shape changes first.");
    return;
  }
  const custom = S.sizing?.authoring?.physical_design.values.some(
    (v) => v.origin === "user_override" || v.locked,
  );
  if (
    custom &&
    !confirm(
      "The layout changed. Replace old size bindings with new suggestions? Your previous choices remain in saved history.",
    )
  )
    return;
  await sizeRequest(
    {
      reset_bindings: true,
    },
    false,
  );
}
async function applyHistory(direction) {
  if (S.sizePending || S.metaPending || S.busy) return;
  const isUndo = direction === "undo";
  const source = isUndo ? S.undo : S.redo;
  const destination = isUndo ? S.redo : S.undo;
  if (S.dirty && source.at(-1)?.kind !== "geometry") {
    toast(
      isUndo
        ? "Save shape changes before undoing saved details."
        : "Save shape changes before redoing saved details.",
    );
    return;
  }
  const entry = source.pop();
  if (!entry) return;
  destination.push(entry);
  const state = isUndo ? entry.before : entry.after;
  if (entry.kind === "geometry") restore(state);
  else if (entry.kind === "metadata") await saveMeta(state, false);
  else await sizeRequest(state, false);
  dirtyState();
  renderInspector();
}
async function undo() {
  await applyHistory("undo");
}
async function redo() {
  await applyHistory("redo");
}

function setView(view) {
  S.view = view;
  S.pan = [0, 0];
  document
    .querySelectorAll("[data-view]")
    .forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  $("view-note").textContent =
    view === "sketch"
      ? "Original sketch with editable suggestions"
      : view === "plan"
        ? "Generated plan · suggested sizes"
        : "Original sketch and generated plan";
  render();
}

function setTool(tool) {
  S.tool = tool;
  if (!["select", "pan"].includes(tool) && S.view === "plan") setView("sketch");
  document
    .querySelectorAll("[data-tool]")
    .forEach((b) => b.classList.toggle("active", b.dataset.tool === tool));
  $("canvas-hint").textContent = {
    select: "Select an item. Drag to move; use the corner handles to resize.",
    room: "Drag a rectangle for a room. Or press Enter to add one.",
    corridor_segment: "Drag a rectangle for a room.",
    door: "Click an empty part of a shared boundary.",
    connect: "Click a shared boundary, or select a room and click a nearby room.",
    resize: "Drag a corner handle, or use arrow keys to resize.",
    pan: "Drag to pan. Use Fit to return to your plan.",
  }[tool];
  render();
}

function eventPoint(event) {
  const rect = canvas.getBoundingClientRect(),
    p = [event.clientX - rect.left, event.clientY - rect.top],
    pane = S.panes.find((v) => p[0] >= v.rect.x && p[0] <= v.rect.x + v.rect.w);
  return pane
    ? {
        pane,
        p,
        world: [(p[0] - pane.tx) / pane.scale, (p[1] - pane.ty) / pane.scale],
      }
    : null;
}

function distance(p, a, b) {
  const dx = b[0] - a[0],
    dy = b[1] - a[1],
    t = Math.max(
      0,
      Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)),
    );
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
}

function hit(data) {
  const o = data.pane.openings.find(
    (o) => distance(data.world, ...o.points_px) < 7 / data.pane.scale,
  );
  if (o) return o.id;
  return [...data.pane.boxes].reverse().find((b) => containsPoint(b, data.world))?.id || null;
}

function addOpening(segment, center, type) {
  if (!segment) return;
  const width =
      type === "open_passage"
        ? segment.hi - segment.lo
        : Math.min(20, (segment.hi - segment.lo) * 0.55),
    lo = Math.max(segment.lo, Math.min(segment.hi - width, center - width / 2)),
    hi = lo + width,
    points = [lo, hi].map((t) => (segment.axis === 0 ? [t, segment.fixed] : [segment.fixed, t]));
  if (
    S.openings.some(
      (o) =>
        o.entity_ids.every((id) => segment.ids.includes(id)) &&
        supporting(o) &&
        Math.min(hi, Math.max(...o.points_px.map((p) => p[segment.axis]))) -
          Math.max(lo, Math.min(...o.points_px.map((p) => p[segment.axis]))) >
          0,
    )
  ) {
    toast("Choose a free part of this boundary, or delete the existing connection.");
    return;
  }
  const before = snapshot();
  const id = uid("opening");
  S.openings.push({
    id,
    type,
    entity_ids: segment.ids,
    points_px: points,
  });
  S.selected = id;
  changed(before);
  renderInspector();
}

function connectToRoom(corridor, target) {
  if (corridor.points_px || target.points_px) {
    toast("Move the rooms so their boundaries touch before connecting.");
    return;
  }
  const C = clone(corridor.bounds_px),
    B = target.bounds_px,
    axis = C[2] - C[0] >= C[3] - C[1] ? 0 : 1,
    normal = 1 - axis;
  if (Math.min(C[normal + 2], B[normal + 2]) - Math.max(C[normal], B[normal]) < 4) {
    toast("Align the rooms first.");
    return;
  }
  const candidates = [
    {
      edge: axis,
      target: B[axis + 2],
      delta: Math.abs(C[axis] - B[axis + 2]),
    },
    {
      edge: axis + 2,
      target: B[axis],
      delta: Math.abs(C[axis + 2] - B[axis]),
    },
  ].sort((a, b) => a.delta - b.delta);
  const candidate = candidates[0];
  if (candidate.delta > Math.max(...S.doc.image_evidence.working_size_px) * 0.1) {
    toast("Move the rooms closer, then connect them.");
    return;
  }
  const before = snapshot();
  C[candidate.edge] = candidate.target;
  if (C[2] - C[0] < 5 || C[3] - C[1] < 5) {
    toast("This connection would leave no room.");
    return;
  }
  corridor.bounds_px = C;
  const segment = shared().find((s) => s.ids.includes(corridor.id) && s.ids.includes(target.id));
  if (!segment) {
    corridor.bounds_px = before.boxes.find((x) => x.id === corridor.id).bounds_px;
    toast("Align these shapes along an edge first.");
    return;
  }
  const points = [segment.lo, segment.hi].map((t) =>
    segment.axis === 0 ? [t, segment.fixed] : [segment.fixed, t],
  );
  S.openings.push({
    id: uid("opening"),
    type: "open_passage",
    entity_ids: segment.ids,
    points_px: points,
  });
  changed(before);
  renderInspector();
}

function snap(value, axis, id) {
  const candidates = S.boxes
    .filter((b) => b.id !== id)
    .flatMap((b) => [b.bounds_px[axis], b.bounds_px[axis + 2]])
    .sort((a, b) => Math.abs(a - value) - Math.abs(b - value));
  return candidates.length && Math.abs(candidates[0] - value) < 4 ? candidates[0] : value;
}
canvas.onpointerdown = (event) => {
  if (!S.doc || S.busy) return;
  const data = eventPoint(event);
  if (!data) return;
  canvas.setPointerCapture(event.pointerId);
  if (S.tool === "pan" || S.space || event.button === 1) {
    S.gesture = {
      kind: "pan",
      p: data.p,
      pan: [...S.pan],
    };
    return;
  }
  if (data.pane.view === "plan") {
    select(hit(data));
    return;
  }
  const p = data.world;
  if (["door", "connect"].includes(S.tool)) {
    const candidates = shared()
      .map((s) => ({
        ...s,
        d: Math.abs(p[s.normal] - s.fixed) + Math.max(s.lo - p[s.axis], 0, p[s.axis] - s.hi),
      }))
      .sort((a, b) => a.d - b.d);
    if (candidates[0]?.d < 8) {
      addOpening(candidates[0], p[candidates[0].axis], S.tool === "door" ? "door" : "open_passage");
      return;
    }
    const selected = region(S.selected),
      target = region(hit(data));
    if (S.tool === "connect" && selected?.type === "room" && target && target.id !== selected.id) {
      connectToRoom(selected, target);
      return;
    }
    if (S.tool === "connect" && target?.type === "room") {
      select(target.id);
      toast("Now click the room to connect.");
      return;
    }
    toast("Choose a boundary shared by two shapes.");
    return;
  }
  if (["room", "corridor_segment"].includes(S.tool)) {
    const [W, H] = S.doc.image_evidence.working_size_px,
      q = [Math.max(0, Math.min(W, p[0])), Math.max(0, Math.min(H, p[1]))];
    S.gesture = {
      kind: "add",
      start: q,
      current: q,
      before: snapshot(),
      type: S.tool,
    };
    return;
  }
  const selected = region(S.selected);
  if (selected) {
    const [x, y, X, Y] = selected.bounds_px,
      corners = [
        [x, y],
        [X, y],
        [X, Y],
        [x, Y],
      ];
    const handle = corners.findIndex(
      (q) => Math.hypot(q[0] - p[0], q[1] - p[1]) < 9 / data.pane.scale,
    );
    if (handle >= 0) {
      S.gesture = {
        kind: "resize",
        handle,
        start: p,
        bounds: clone(selected.bounds_px),
        id: selected.id,
        before: snapshot(),
      };
      return;
    }
  }
  const selectedOpening = opening(S.selected);
  if (selectedOpening) {
    const handle = selectedOpening.points_px.findIndex(
      (q) => Math.hypot(q[0] - p[0], q[1] - p[1]) < 9 / data.pane.scale,
    );
    if (handle >= 0) {
      S.gesture = {
        kind: "opening-end",
        id: selectedOpening.id,
        handle,
        segment: supporting(selectedOpening),
        before: snapshot(),
      };
      return;
    }
  }
  const id = hit(data);
  select(id);
  if (region(id))
    S.gesture = {
      kind: S.tool === "resize" ? "resize" : "move",
      handle: 2,
      start: p,
      bounds: clone(region(id).bounds_px),
      id,
      before: snapshot(),
    };
  else if (opening(id))
    S.gesture = {
      kind: "opening-move",
      start: p,
      id,
      points: clone(opening(id).points_px),
      segment: supporting(opening(id)),
      before: snapshot(),
    };
};
canvas.onpointermove = (event) => {
  const g = S.gesture;
  if (!g) return;
  const data = eventPoint(event);
  if (!data) return;
  if (g.kind === "pan") {
    S.pan = [g.pan[0] + data.p[0] - g.p[0], g.pan[1] + data.p[1] - g.p[1]];
    render();
    return;
  }
  const p = data.world,
    [W, H] = S.doc.image_evidence.working_size_px;
  if (g.kind === "add") {
    g.current = [Math.max(0, Math.min(W, p[0])), Math.max(0, Math.min(H, p[1]))];
    render();
    requestAnimationFrame(() => {
      const pane = S.panes.find((p) => p.view === "sketch");
      if (!pane) return;
      ctx.strokeStyle = "#b44725";
      ctx.setLineDash([5, 3]);
      ctx.strokeRect(
        g.start[0] * pane.scale + pane.tx,
        g.start[1] * pane.scale + pane.ty,
        (g.current[0] - g.start[0]) * pane.scale,
        (g.current[1] - g.start[1]) * pane.scale,
      );
      ctx.setLineDash([]);
    });
    return;
  }
  if (g.kind === "move") {
    const b = region(g.id),
      B = g.bounds,
      dx = p[0] - g.start[0],
      dy = p[1] - g.start[1];
    let x = snap(B[0] + dx, 0, g.id),
      y = snap(B[1] + dy, 1, g.id);
    const X = snap(x + B[2] - B[0], 0, g.id),
      Y = snap(y + B[3] - B[1], 1, g.id);
    x = X - (B[2] - B[0]);
    y = Y - (B[3] - B[1]);
    x = Math.max(0, Math.min(W - (B[2] - B[0]), x));
    y = Math.max(0, Math.min(H - (B[3] - B[1]), y));
    setBounds(b, [x, y, x + B[2] - B[0], y + B[3] - B[1]]);
  }
  if (g.kind === "resize") {
    const B = [...g.bounds],
      left = [0, 3].includes(g.handle),
      top = [0, 1].includes(g.handle);
    B[left ? 0 : 2] = Math.max(0, Math.min(W, snap(p[0], 0, g.id)));
    B[top ? 1 : 3] = Math.max(0, Math.min(H, snap(p[1], 1, g.id)));
    if (B[2] - B[0] >= 5 && B[3] - B[1] >= 5) setBounds(region(g.id), B);
  }
  if (g.kind === "opening-end" && g.segment) {
    const o = opening(g.id),
      s = g.segment;
    let t = Math.max(s.lo, Math.min(s.hi, p[s.axis]));
    const other = o.points_px[1 - g.handle][s.axis];
    if (g.handle === 0) t = Math.min(t, other - 2);
    else t = Math.max(t, other + 2);
    o.points_px[g.handle] = s.axis === 0 ? [t, s.fixed] : [s.fixed, t];
  }
  if (g.kind === "opening-move" && g.segment) {
    const o = opening(g.id),
      s = g.segment,
      delta = Math.max(
        s.lo - g.points[0][s.axis],
        Math.min(s.hi - g.points[1][s.axis], p[s.axis] - g.start[s.axis]),
      );
    o.points_px = g.points.map((q) => q.map((v, a) => v + (a === s.axis ? delta : 0)));
  }
  render();
};
canvas.onpointerup = () => {
  const g = S.gesture;
  if (!g) return;
  S.gesture = null;
  if (g.kind === "pan") return;
  if (g.kind === "add") {
    const p = g.current,
      x = Math.min(p[0], g.start[0]),
      y = Math.min(p[1], g.start[1]),
      X = Math.max(p[0], g.start[0]),
      Y = Math.max(p[1], g.start[1]);
    if (X - x >= 5 && Y - y >= 5) {
      const id = uid("region");
      S.boxes.push({
        id,
        type: g.type,
        bounds_px: [x, y, X, Y],
      });
      S.selected = id;
    }
  }
  changed(g.before);
  renderInspector();
};
canvas.onpointercancel = () => {
  if (S.gesture?.before) restore(S.gesture.before);
  S.gesture = null;
};
canvas.addEventListener(
  "wheel",
  (event) => {
    event.preventDefault();
    S.zoom = Math.max(0.35, Math.min(4, S.zoom * (event.deltaY < 0 ? 1.1 : 0.9)));
    render();
  },
  {
    passive: false,
  },
);

function removeSelected() {
  if (!S.selected) return;
  const before = snapshot();
  const removed = S.boxes.some((b) => b.id === S.selected);
  S.boxes = S.boxes.filter((b) => b.id !== S.selected);
  S.openings = S.openings.filter((o) => o.id !== S.selected && !o.entity_ids.includes(S.selected));
  S.selected = null;
  changed(before);
  renderInspector();
  if (removed) toast("Shape and its attached connections removed. Undo to restore.");
}
async function refreshJobs() {
  const data = await api("/api/bootstrap");
  S.token = data.token;
  $("jobs").replaceChildren(new Option("Choose a drawing", ""));
  $("recent-list").replaceChildren();
  for (const j of data.jobs.slice().reverse()) {
    const option = new Option(j.filename, j.job_id);
    $("jobs").add(option);
    const button = document.createElement("button");
    button.textContent = j.filename;
    const note = document.createElement("small");
    note.textContent = j.is_sample ? "Sample plan" : "Saved on this computer";
    button.append(note);
    button.onclick = () => openJob(j.job_id);
    $("recent-list").append(button);
  }
  $("recent").hidden = !data.jobs.length;
  return data;
}
async function openJob(id) {
  if (/^Job_/.test(id)) {
    const state = await api("/jobs/" + id);
    id = state.shape_job_id;
  }
  if (
    (S.dirty || S.sizePending || S.metaPending) &&
    !confirm("Leave this plan with unsaved changes?")
  )
    return;
  S.ticket++;
  const ticket = S.ticket;
  S.busy = false;
  S.gesture = null;
  S.job = id;
  S.doc = null;
  S.sizing = null;
  S.sizePending = 0;
  S.metaPending = 0;
  S.sizeQueue = Promise.resolve();
  S.undo = [];
  S.redo = [];
  S.dirty = false;
  screen("analysis");
  try {
    let state;
    do {
      state = await api("/shape-jobs/" + id);
      if (ticket !== S.ticket) return;
      if (!state.manual_available) await new Promise((r) => setTimeout(r, 250));
    } while (
      !state.manual_available &&
      ["queued", "processing", "cancelled"].includes(state.status)
    );
    if (!state.manual_available) throw Error("Analysis could not finish. Please try again.");
    const data = await api("/shape-jobs/" + id + "/proposals");
    if (ticket !== S.ticket) return;
    S.data = data;
    S.doc = data.authoring;
    if (data.edit_state) {
      S.boxes = clone(data.edit_state.boxes);
      S.openings = clone(data.edit_state.openings);
    } else {
      S.boxes = S.doc.topology.regions.map((r) => {
        const p = r.geometry.points_px;
        return {
          id: r.id,
          type: "room",
          ...(p.length > 4 ? { points_px: clone(p) } : {}),
          bounds_px: [
            Math.min(...p.map((q) => q[0])),
            Math.min(...p.map((q) => q[1])),
            Math.max(...p.map((q) => q[0])),
            Math.max(...p.map((q) => q[1])),
          ],
        };
      });
      S.openings = S.doc.topology.openings.map((o) => ({
        id: o.id,
        type: o.type,
        entity_ids: o.entity_ids,
        points_px: clone(o.geometry.points_px),
      }));
    }
    S.selected = null;
    const [meta, sizing] = await Promise.all([
      api("/shape-jobs/" + id + "/workspace"),
      api("/shape-jobs/" + id + "/sizing"),
    ]);
    if (ticket !== S.ticket) return;
    S.meta = meta;
    S.sizing = sizing;
    S.image = new Image();
    S.image.onload = render;
    S.image.src = "/shape-jobs/" + id + "/image";
    S.zoom = 1;
    S.pan = [0, 0];
    $("project-title").textContent = state.filename;
    $("jobs").value = id;
    history.replaceState(null, "", "?job=" + id);
    screen("workspace");
    render();
    renderInspector();
    if (S.sizing.status === "not_sized" && S.boxes.length) await sizeRequest({}, false);
    $("details").textContent = JSON.stringify(
      {
        model: data.model,
        profile: data.profile,
        failure: data.failure,
      },
      null,
      2,
    );
    status(
      data.status === "manual_required" && !S.boxes.length
        ? "Automatic detection could not build a plan. Your image is ready for manual editing."
        : state.is_sample
          ? "Sample plan loaded. Every shape and size is editable."
          : "Review the suggested shapes and connections.",
    );
  } catch (e) {
    if (ticket !== S.ticket) return;
    screen("landing");
    $("landing-error").textContent = e.message;
  }
}
async function upload(file) {
  if (!file) return;
  if (!["image/png", "image/jpeg"].includes(file.type) || file.size > 20_000_000) {
    $("landing-error").textContent = "Choose a PNG or JPG image up to 20 MB.";
    return;
  }
  try {
    const job = await api("/shape-jobs", file, {
      "X-File-Name": encodeURIComponent(file.name),
    });
    await refreshJobs();
    await openJob(job.job_id);
  } catch (e) {
    $("landing-error").textContent = e.message;
  }
}

function openSettings() {
  if (S.dirty) {
    toast("Save shape changes before opening settings.");
    return;
  }
  if (!S.sizing?.authoring) {
    toast("Add a shape and save it before changing plan settings.");
    return;
  }
  const root = $("settings-fields");
  root.replaceChildren();
  for (const param of [
    "wall_thickness_cm",
    "wall_height_cm",
    "door_height_cm",
    "floor_thickness_cm",
  ]) {
    const label = document.createElement("label");
    label.textContent = labels[param];
    const input = document.createElement("input");
    input.type = "number";
    input.step = ".01";
    input.min = ".01";
    input.max = "10000";
    input.dataset.setting = param;
    input.setAttribute("aria-label", labels[param] + " in metres");
    input.value = (
      (value("global", param)?.value || S.sizing?.settings?.[param] || 20) / 100
    ).toFixed(2);
    label.append(input);
    root.append(label);
  }
  $("settings").showModal();
}
async function applySettings() {
  const fields = [...document.querySelectorAll("[data-setting]")];
  if (!fields.every((f) => f.reportValidity())) return;
  const edits = fields
    .filter(
      (f) =>
        Math.abs(Number(f.value) * 100 - (value("global", f.dataset.setting)?.value || 0)) > 0.001,
    )
    .map((f) => ({
      entity_id: "global",
      parameter: f.dataset.setting,
      value: Number(f.value),
      unit: "m",
    }));
  if (edits.length)
    await sizeRequest({
      edits,
    });
  $("settings").close();
}

function review() {
  if (S.dirty || S.sizePending || S.metaPending) {
    toast("Save your changes before reviewing.");
    return;
  }
  const root = $("review-summary");
  root.replaceChildren();
  const counts = document.createElement("div");
  counts.className = "review-counts";
  for (const [count, label] of [
    [S.boxes.length, "Rooms"],
    [S.openings.length, "Connections"],
  ]) {
    const div = document.createElement("div");
    const strong = document.createElement("b");
    strong.textContent = count;
    const span = document.createElement("span");
    span.textContent = label;
    div.append(strong, span);
    counts.append(div);
  }
  root.append(counts);
  const p = document.createElement("p");
  p.className = "muted";
  p.textContent = S.issues.length
    ? S.issues.length + " item(s) need attention before you can confirm."
    : "The saved plan has valid sizes. Review the connections in Sketch and Plan views before confirming.";
  root.append(p);
  for (const [id, key] of [
    ["start-room", "start_room_id"],
    ["goal-room", "goal_room_id"],
  ]) {
    $(id).replaceChildren(new Option("Choose a room", ""));
    for (const r of S.boxes.filter((r) => r.type === "room"))
      $(id).add(new Option(name(r.id), r.id));
    $(id).value = S.meta.state[key] || "";
  }
  $("delivery-mode").value = S.meta.state.validation_mode || "geometry_only";
  $("export").disabled = !S.meta.confirmation || S.issues.length > 0;
  $("confirm-plan").disabled =
    !!S.meta.confirmation || S.issues.length > 0 || S.sizing?.status !== "ready";
  $("confirmation-state").textContent = S.meta.confirmation
    ? "This saved plan is already confirmed."
    : "";
  updateDeliveryChoice(false);
  for (const id of ["delivery-mode", "start-room", "goal-room"]) $(id).disabled = false;
  $("review").showModal();
}
function updateDeliveryChoice(changed = true) {
  const playable = $("delivery-mode").value === "gameplay";
  $("playable-roles").hidden = !playable;
  $("delivery-help").textContent = playable
    ? "Choose different Start and Goal rooms. Unreal checks collision and player clearance before you can play."
    : "Create walls and floors for Unreal Editor. This export does not enable player movement.";
  if (changed) {
    $("export").disabled = true;
    $("confirm-plan").disabled = S.issues.length > 0 || S.sizing?.status !== "ready";
    $("confirmation-state").textContent = "Confirm these choices to prepare your export.";
  }
}
async function confirmPlan() {
  const ticket = S.ticket,
    job = S.job;
  const controls = ["delivery-mode", "start-room", "goal-room"];
  controls.forEach((id) => ($(id).disabled = true));
  $("confirm-plan").disabled = true;
  try {
    const mode = $("delivery-mode").value || S.meta.state.validation_mode || "geometry_only";
    const start = $("start-room").value || null;
    const goal = $("goal-room").value || null;
    if (mode === "gameplay" && (!start || !goal || start === goal)) {
      toast("Choose different Start and Goal rooms before confirming.");
      return;
    }
    if (
      mode !== (S.meta.state.validation_mode || "geometry_only") ||
      start !== S.meta.state.start_room_id ||
      goal !== S.meta.state.goal_room_id
    ) {
      if (
        !(await saveMeta({
          ...clone(S.meta.state),
          validation_mode: mode,
          start_room_id: start,
          goal_room_id: goal,
        }))
      )
        return;
      if (ticket !== S.ticket || job !== S.job) return;
    }
    const accepted = await api("/shape-jobs/" + job + "/confirm", {
      base_revision_id: S.doc.revision_id,
      base_sizing_revision_id: S.sizing.authoring.revision_id,
      base_workspace_revision_id: S.meta.revision_id,
    });
    if (ticket !== S.ticket || job !== S.job || S.dirty || S.sizePending || S.metaPending) return;
    S.meta.confirmation = accepted;
    $("confirmation-state").textContent = accepted.message;
    $("confirm-plan").disabled = true;
    $("export").disabled = false;
    status("Plan confirmed. Your Unreal bundle is ready to export.");
  } catch (e) {
    if (ticket === S.ticket && job === S.job) fail(e);
  } finally {
    if (ticket === S.ticket && job === S.job) {
      controls.forEach((id) => ($(id).disabled = false));
      $("confirm-plan").disabled =
        !!S.meta.confirmation || S.issues.length > 0 || S.sizing?.status !== "ready";
    }
  }
}

function isCurrentConfirmation(ticket, confirmationId) {
  return (
    ticket === S.ticket &&
    S.meta.confirmation?.confirmation_id === confirmationId &&
    !S.dirty &&
    !S.sizePending &&
    !S.metaPending
  );
}
async function exportPlan() {
  const confirmation = S.meta.confirmation;
  if (!confirmation) {
    toast("Review and confirm this plan first.");
    return;
  }
  const ticket = S.ticket,
    job = S.job;
  $("export").disabled = true;
  try {
    const record = await api("/shape-jobs/" + job + "/export", {
      confirmation_id: confirmation.confirmation_id,
    });
    if (!isCurrentConfirmation(ticket, confirmation.confirmation_id))
      throw Error("The plan changed. Confirm it again before downloading.");
    const response = await fetch(record.download_url);
    if (!response.ok) {
      const data = await response.json();
      throw Error(data.error || "The export could not be downloaded.");
    }
    const blob = await response.blob();
    if (!isCurrentConfirmation(ticket, confirmation.confirmation_id))
      throw Error("The plan changed. Export the current confirmed snapshot.");
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.href = url;
    link.download = "PlayableSketch-Unreal.zip";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    $("confirmation-state").textContent =
      record.validation_mode === "gameplay"
        ? "Bundle downloaded. Open PlayableSketch and choose Open latest plan."
        : "Validated geometry bundle downloaded. Player traversal was not requested.";
    status("Unreal bundle downloaded.");
  } catch (e) {
    fail(e);
  } finally {
    if (ticket === S.ticket) $("export").disabled = !S.meta.confirmation;
  }
}
$("upload").onclick = (event) => {
  event.stopPropagation();
  $("file").click();
};
$("drop-zone").onclick = (event) => {
  if (event.target !== $("upload")) $("file").click();
};
$("file").onchange = () => upload($("file").files[0]);
for (const event of ["dragenter", "dragover"])
  $("drop-zone").addEventListener(event, (e) => {
    e.preventDefault();
    $("drop-zone").classList.add("drag");
  });
$("drop-zone").addEventListener("dragleave", () => $("drop-zone").classList.remove("drag"));
$("drop-zone").addEventListener("drop", (e) => {
  e.preventDefault();
  $("drop-zone").classList.remove("drag");
  upload(e.dataTransfer.files[0]);
});
$("sample").onclick = async () => {
  try {
    $("sample").disabled = true;
    const job = await api("/api/sample", {});
    await refreshJobs();
    await openJob(job.job_id);
  } catch (e) {
    $("landing-error").textContent = e.message;
  } finally {
    $("sample").disabled = false;
  }
};
function returnHome(event) {
  event.preventDefault();
  if ((S.dirty || S.sizePending || S.metaPending) && !confirm("Leave unsaved changes?")) return;
  S.ticket++;
  S.busy = false;
  S.gesture = null;
  S.job = "";
  S.doc = null;
  S.dirty = false;
  S.sizePending = 0;
  S.metaPending = 0;
  S.sizeQueue = Promise.resolve();
  history.replaceState(null, "", "/");
  screen("landing");
  refreshJobs();
}
$("new-sketch").onclick = returnHome;
$("home").onclick = returnHome;
$("jobs").onchange = () => {
  if ($("jobs").value) openJob($("jobs").value);
};
$("cancel").onclick = () => api("/shape-jobs/" + S.job + "/cancel", {}).catch(fail);
$("manual-fallback").onclick = () => api("/shape-jobs/" + S.job + "/cancel", {}).catch(fail);
$("retry").onclick = async () => {
  try {
    await api("/shape-jobs/" + S.job + "/retry", {});
    await openJob(S.job);
  } catch (e) {
    fail(e);
  }
};
document
  .querySelectorAll("[data-view]")
  .forEach((b) => (b.onclick = () => setView(b.dataset.view)));
document
  .querySelectorAll("[data-tool]")
  .forEach((b) => (b.onclick = () => setTool(b.dataset.tool)));
$("zoom-in").onclick = () => {
  S.zoom = Math.min(4, S.zoom * 1.2);
  render();
};
$("zoom-out").onclick = () => {
  S.zoom = Math.max(0.35, S.zoom / 1.2);
  render();
};
$("fit").onclick = () => {
  S.zoom = 1;
  S.pan = [0, 0];
  render();
};
$("save").onclick = saveGeometry;
$("refresh-sizes").onclick = refreshSizes;
$("undo").onclick = undo;
$("redo").onclick = redo;
$("delete").onclick = removeSelected;
$("settings-button").onclick = openSettings;
$("apply-settings").onclick = applySettings;
$("review-button").onclick = review;
$("confirm-plan").onclick = confirmPlan;
$("export").onclick = exportPlan;
window.addEventListener("keydown", (e) => {
  if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;
  if (document.querySelector("dialog[open]")) return;
  if (e.key === " " && document.activeElement === canvas) {
    S.space = true;
    e.preventDefault();
  }
  if (!S.doc) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    saveGeometry();
    return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
    e.preventDefault();
    e.shiftKey ? redo() : undo();
    return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
    e.preventDefault();
    redo();
    return;
  }
  if (e.key === "Escape") {
    S.gesture = null;
    setTool("select");
    return;
  }
  if (["Delete", "Backspace"].includes(e.key)) {
    e.preventDefault();
    removeSelected();
    return;
  }
  const tools = {
    v: "select",
    r: "room",
    c: "room",
    d: "door",
    g: "connect",
    h: "pan",
  };
  if (tools[e.key.toLowerCase()]) setTool(tools[e.key.toLowerCase()]);
  if (e.key.toLowerCase() === "f") $("fit").click();
  if (e.key === "+" || e.key === "=") $("zoom-in").click();
  if (e.key === "-") $("zoom-out").click();
  const selected = region(S.selected);
  if (selected && e.key.startsWith("Arrow")) {
    e.preventDefault();
    if (S.view === "plan") setView("sketch");
    const before = snapshot(),
      axis = ["ArrowLeft", "ArrowRight"].includes(e.key) ? 0 : 1,
      delta = (e.shiftKey ? 5 : 1) * (["ArrowLeft", "ArrowUp"].includes(e.key) ? -1 : 1);
    const next = [...selected.bounds_px];
    if (S.tool === "resize") next[axis + 2] += delta;
    else {
      next[axis] += delta;
      next[axis + 2] += delta;
    }
    const B = next,
      [W, H] = S.doc.image_evidence.working_size_px;
    if (B[0] < 0 || B[1] < 0 || B[2] > W || B[3] > H || B[2] - B[0] < 5 || B[3] - B[1] < 5) {
      next.splice(0, 4, ...before.boxes.find((b) => b.id === selected.id).bounds_px);
      toast("Keep the shape inside the sketch with room to edit.");
    }
    setBounds(selected, next);
    changed(before);
  }
  if (
    e.key === "Enter" &&
    document.activeElement === canvas &&
    ["room", "corridor_segment"].includes(S.tool)
  ) {
    const before = snapshot(),
      [W, H] = S.doc.image_evidence.working_size_px,
      w = S.tool === "room" ? W * 0.22 : W * 0.3,
      h = S.tool === "room" ? H * 0.3 : H * 0.1,
      id = uid("region");
    S.boxes.push({
      id,
      type: S.tool,
      bounds_px: [W * 0.4, H * 0.4, W * 0.4 + w, H * 0.4 + h],
    });
    S.selected = id;
    changed(before);
    renderInspector();
  }
});
window.addEventListener("keyup", (e) => {
  if (e.key === " ") S.space = false;
});
window.addEventListener("beforeunload", (e) => {
  if (S.dirty || S.sizePending || S.metaPending) {
    e.preventDefault();
    e.returnValue = "";
  }
});
new ResizeObserver(() => {
  if (S.doc) render();
}).observe($("stage"));
(async () => {
  await refreshJobs();
  const id = new URLSearchParams(location.search).get("job");
  if (id) await openJob(id);
})().catch((e) => {
  $("landing-error").textContent = "Could not connect to the local workspace. Reload to try again.";
});

function applyTheme(theme) {
  S.theme = theme === "dark" ? "dark" : "light";
  document.documentElement?.setAttribute("data-theme", S.theme);
  $("theme-toggle").textContent = S.theme === "dark" ? "Light mode" : "Night mode";
  $("theme-toggle").setAttribute("aria-pressed", String(S.theme === "dark"));
  try {
    localStorage.setItem("playablesketch-theme", S.theme);
  } catch {}
  if (S.doc) render();
}
$("theme-toggle").onclick = () => applyTheme(S.theme === "dark" ? "light" : "dark");
$("delivery-mode").onchange = () => updateDeliveryChoice();
$("start-room").onchange = $("goal-room").onchange = () => updateDeliveryChoice();
let preferredTheme = "light";
try {
  preferredTheme =
    localStorage.getItem("playablesketch-theme") ||
    (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light");
} catch {}
applyTheme(preferredTheme);
