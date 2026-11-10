"use strict";
(() => {
  const $ = (id) => document.getElementById(id),
    copy = (x) => JSON.parse(JSON.stringify(x));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b),
    ns = "http://www.w3.org/2000/svg";
  let token,
    caseId,
    session,
    state,
    saved,
    base = null,
    busy = false,
    version = 0,
    ticket = 0,
    timer;

  let activeMs = 0,
    interactions = 0,
    activityAt = 0,
    accountedAt = performance.now();
  function accountTime() {
    const now = performance.now();
    if (
      state &&
      !busy &&
      document.visibilityState === "visible" &&
      document.hasFocus() &&
      now - activityAt < 60000
    )
      activeMs += Math.min(1000, now - accountedAt);
    accountedAt = now;
  }
  setInterval(accountTime, 1000);
  for (const event of ["pointerdown", "keydown", "input"])
    document.addEventListener(
      event,
      () => {
        accountTime();
        if (state && !busy) {
          activityAt = performance.now();
          interactions++;
        }
      },
      { passive: true },
    );
  let selectedDimension = null,
    selectedEntity = null,
    targets = [];
  const settingsDefaults = {
    wall_thickness_cm: 20,
    wall_height_cm: 300,
    door_height_cm: 220,
    floor_thickness_cm: 20,
  };
  function node(tag, text, attrs = {}) {
    const n = document.createElement(tag);
    if (text !== null) n.textContent = text;
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    return n;
  }
  function svg(tag, attrs, parent) {
    const n = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    parent.append(n);
    return n;
  }
  function message(text, error = false) {
    $("metricMessage").textContent = text;
    $("metricMessage").hidden = !text;
    $("metricMessage").style.background = error ? "#fff0e8" : "#edf5ef";
  }
  function dirty() {
    return state && !same(state, saved);
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
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed.");
    return data;
  }
  function key(t, b) {
    return JSON.stringify([
      Object.keys(t)
        .sort()
        .map((k) => [k, t[k]]),
      b,
    ]);
  }
  function targetLabel(t, b) {
    if (t.type === "region_span")
      return `${t.region_id} · ${t.axis === "x" ? "width" : "depth"} · centerline`;
    if (t.type === "wall_chain") return `Wall chain ${t.wall_ids.join(" → ")} · centerline`;
    if (t.type === "opening_width") return `${t.opening_id} · clear width`;
    if (t.type === "opening_offset")
      return `${t.opening_id} · ${t.region_id} ${t.side} · ${t.reference === "min_corner" ? "left / bottom" : "right / top"} corner → ${b === "edge_offset" ? "near edge" : "center"}`;
    if (t.type === "opening_separation")
      return `${t.from_opening_id} → ${t.to_opening_id} · solid edge-to-edge span`;
    return "Unassigned — choose a measured span";
  }
  function currentDimension() {
    return state?.bindings.dimensions.find((d) => d.id === selectedDimension);
  }
  function buildTargets() {
    const map = new Map();
    const put = (target, basis) => map.set(key(target, basis), { target, basis });
    put({ type: "unassigned" }, "wall_centerline");
    for (const t of session.targets) put(t.target, t.basis);
    for (const d of state.bindings.dimensions) put(d.target, d.basis);
    for (const t of session.targets)
      if (t.target.type === "opening_offset") put(t.target, "center_offset");

    const openings = session.draft.layout.openings;
    for (const a of openings)
      for (const b of openings)
        if (a.id !== b.id && a.wall_id === b.wall_id)
          put(
            { type: "opening_separation", from_opening_id: a.id, to_opening_id: b.id },
            "edge_offset",
          );
    targets = [...map.values()];
  }
  function hydrate(result) {
    session = result;
    state = copy(result.state);
    base = result.base_revision_id;
    const ids = new Set(state.bindings.dimensions.map((d) => d.id));
    for (const d of result.draft.layout.dimensions)
      if (!ids.has(d.id)) state.bindings.dimensions.push(copy(d));
    saved = copy(state);
    version++;
    buildTargets();
    if (!state.bindings.dimensions.some((d) => d.id === selectedDimension))
      selectedDimension = state.bindings.dimensions[0]?.id || null;
  }
  async function load(identifier) {
    if (busy) return;
    if (dirty() && !confirm("Discard unsaved metric changes and reload?")) {
      $("metricCase").value = caseId;
      return;
    }
    clearTimeout(timer);
    busy = true;
    status();
    const request = ++ticket;
    try {
      const result = await api("/api/metric?case=" + encodeURIComponent(identifier));
      if (request !== ticket) return;
      caseId = identifier;
      activeMs = 0;
      interactions = 0;
      activityAt = performance.now();
      accountedAt = activityAt;
      hydrate(result);
      document.querySelector(".metric-workspace").hidden = false;
      document.querySelector(".metric-aside").hidden = false;
      history.replaceState(null, "", "?case=" + encodeURIComponent(caseId));
      $("backTopology").href = "/?case=" + encodeURIComponent(caseId);
      message(
        result.topology_reset
          ? "Topology changed. Check region types and rebind all measurements to the new topology."
          : "Review the drawing, confirmed measurements and reconstructed cm plan before acceptance.",
      );
      renderAll();
    } catch (error) {
      message(error.message, true);
      $("metricCase").value = caseId || identifier;
      $("backTopology").href = "/?case=" + encodeURIComponent(caseId || identifier);
      if (!session) {
        document.querySelector(".metric-workspace").hidden = true;
        document.querySelector(".metric-aside").hidden = true;
      }
    } finally {
      busy = false;
      status();
    }
  }
  function edit() {
    version++;
    session.status = "draft";
    status();
    drawViews();
    $("solveStatus").textContent = "Preview pending…";
    clearTimeout(timer);
    timer = setTimeout(preview, 500);
  }
  async function preview() {
    if (!state || busy) return;
    const request = ++ticket,
      v = version,
      id = caseId;
    $("solveStatus").textContent = "Recomputing…";
    try {
      const result = await api("/api/metric/preview", {
        case_id: id,
        base_revision_id: base,
        state: copy(state),
      });
      if (request !== ticket || v !== version || id !== caseId) return;
      session = { ...session, ...result };
      buildTargets();
      drawViews();
      renderIssues();
      status();
    } catch (error) {
      if (request === ticket && v === version) {
        message(error.message, true);
        $("solveStatus").textContent = "Input needs correction";
      }
    }
  }
  async function transact(action) {
    if (busy || !state) return;
    if (["accept", "undo", "redo"].includes(action) && dirty()) {
      message("Save your changes before " + action + ".", true);
      return;
    }
    accountTime();
    const measuredMs = Math.min(1800000, Math.floor(activeMs)),
      measuredInteractions = Math.min(100000, interactions);
    clearTimeout(timer);
    ++ticket;
    busy = true;
    status();
    try {
      const body = {
        case_id: caseId,
        base_revision_id: base,
        telemetry: {
          active_ms: measuredMs,
          interaction_count: measuredInteractions,
          source: "browser-visible-interaction/v1",
        },
      };
      if (action === "save") body.state = copy(state);
      if (action === "accept") body.reviewer = $("reviewerName").value;
      const result = await api("/api/metric/" + action, body);
      activeMs = Math.max(0, activeMs - measuredMs);
      interactions = Math.max(0, interactions - measuredInteractions);
      hydrate(result);
      renderAll();
      message(
        action === "accept"
          ? "This metric snapshot is accepted. Download its validated JSON below."
          : "Saved a new immutable " + action + " revision.",
      );
    } catch (error) {
      message(error.message, true);
    } finally {
      busy = false;
      status();
    }
  }
  function status() {
    if (!session) {
      for (const el of document.querySelectorAll(
        ".metric-main input,.metric-main select,.metric-main button",
      ))
        el.disabled = true;
      $("metricStatus").textContent = "Approve topology first";
      return;
    }

    for (const el of document.querySelectorAll("input,select,button")) el.disabled = busy;
    $("metricStatus").textContent = busy
      ? "Working…"
      : dirty()
        ? "Unsaved changes"
        : session.status === "accepted"
          ? "Accepted snapshot"
          : "Draft · review pending";
    $("metricStatus").className =
      "pill " + (dirty() ? "dirty" : session.status === "accepted" ? "reviewed" : "");
    $("metricUndo").disabled = busy || dirty() || !session.can_undo;
    $("metricRedo").disabled = busy || dirty() || !session.can_redo;
    const passing = session.report.validation.metric_valid;
    $("acceptMetric").disabled =
      busy ||
      dirty() ||
      !base ||
      !passing ||
      !$("reviewerName").value.trim() ||
      session.status === "accepted";
    $("downloadMetric").disabled = busy || dirty() || session.status !== "accepted";
    $("acceptReadiness").textContent = dirty()
      ? "Save the current corrections before acceptance."
      : passing
        ? "Metric checks passed. Inspect both views, enter your name, and accept this saved snapshot."
        : "Resolve the checks. Acceptance never fills missing dimensions.";
    $("revisionInfo").textContent = base ? "Revision: " + base : "No metric revision saved yet.";
    const d = currentDimension();
    $("removeMeasurement").disabled = busy || !d || d.provenance.evidence_ids.length > 0;
    $("ignoreText").disabled = busy || !d || !d.provenance.evidence_ids.length;
    $("confirmDimension").disabled =
      busy || !d || d.value_cm === null || d.target.type === "unassigned";
  }
  function dimensionList() {
    $("dimensionList").replaceChildren();
    for (const d of state.bindings.dimensions) {
      const option = node(
        "option",
        `${d.state === "confirmed" ? "✓" : d.state === "missing" ? "?" : "·"} ${d.id}: ${d.value_cm ?? "missing"} cm · ${d.state}`,
        { value: d.id },
      );
      $("dimensionList").append(option);
    }
    $("dimensionList").value = selectedDimension || "";
    $("ignoredList").replaceChildren();
    for (const ignored of state.bindings.ignored_texts || []) {
      const b = node("button", "Restore " + ignored.evidence_id);
      b.onclick = () => {
        state.bindings.ignored_texts = state.bindings.ignored_texts.filter(
          (t) => t.evidence_id !== ignored.evidence_id,
        );
        const original = session.observations.texts.find((t) => t.id === ignored.evidence_id);
        const d = {
          id: "user-" + crypto.randomUUID().slice(0, 8),
          value_cm: original.parsed_value_cm,
          basis: "wall_centerline",
          target: { type: "unassigned" },
          state: original.parsed_value_cm === null ? "missing" : "inferred",
          span_label: original.raw_text,
          provenance: {
            method: "ocr",
            evidence_ids: [original.id],
            note: "Restored OCR evidence for review.",
          },
        };
        state.bindings.dimensions.push(d);
        selectedDimension = d.id;
        buildTargets();
        dimensionList();
        dimensionEditor();
        edit();
      };
      $("ignoredList").append(b);
    }
  }
  function dimensionEditor() {
    const d = currentDimension();
    $("dimensionEditor").hidden = !d;
    if (!d) {
      drawViews();
      return;
    }
    $("dimensionValue").value = d.value_cm ?? "";
    $("dimensionNote").value = d.provenance.note || "";
    $("confirmDimension").checked = d.state === "confirmed";
    $("dimensionTarget").replaceChildren();
    targets.forEach((t, i) =>
      $("dimensionTarget").append(
        node("option", targetLabel(t.target, t.basis), { value: String(i) }),
      ),
    );
    $("dimensionTarget").value = String(
      targets.findIndex((t) => key(t.target, t.basis) === key(d.target, d.basis)),
    );
    const originals = d.provenance.evidence_ids
      .map((id) => session.observations.texts.find((t) => t.id === id))
      .filter(Boolean);
    $("rawEvidence").textContent = originals.length
      ? originals
          .map(
            (t) =>
              `${t.id} · Original OCR: “${t.raw_text}” · candidate ${t.parsed_value_cm ?? "unreadable"} cm · confidence ${t.score ?? "unknown"}`,
          )
          .join("\n")
      : "Unwritten measurement · user supplied; no OCR evidence.";
    $("spanExplanation").textContent =
      targetLabel(d.target, d.basis) +
      ". " +
      (d.basis === "edge_offset"
        ? "Near opening edge, not its center. Left/bottom is min; right/top is max."
        : d.basis === "center_offset"
          ? "Explicit center measurement. Use near-edge basis for the paper convention."
          : "Select a wall chain to measure local spans to centerline T junctions.");
    $("suggestions").replaceChildren();
    const proposal = session.report.association.proposals.find((p) =>
      d.provenance.evidence_ids.includes(p.evidence_id),
    );
    for (const c of proposal?.candidates || []) {
      const b = node("button", targetLabel(c.target, c.basis) + ` · cost ${c.cost.toFixed(2)}`);
      b.title = JSON.stringify(c.features);
      b.onclick = () => {
        d.target = copy(c.target);
        d.basis = c.basis;
        d.state = d.value_cm === null ? "missing" : "inferred";
        dimensionEditor();
        edit();
      };
      $("suggestions").append(b);
    }
    drawCrop(originals[0]?.id);
    drawViews();
    status();
  }
  function updateDimension() {
    const d = currentDimension();
    if (!d) return;
    const raw = $("dimensionValue").value;
    d.value_cm = raw === "" ? null : Number(raw);
    const t = targets[Number($("dimensionTarget").value)];
    if (t) {
      d.target = copy(t.target);
      d.basis = t.basis;
    }
    d.state =
      d.value_cm === null
        ? "missing"
        : $("confirmDimension").checked && d.target.type !== "unassigned"
          ? "confirmed"
          : "inferred";
    d.provenance = {
      method: "user_correction",
      evidence_ids: copy(d.provenance.evidence_ids),
      note:
        $("dimensionNote").value ||
        "User edited transcription/target in metric review; original OCR preserved.",
    };
    dimensionList();
    status();
    edit();
  }
  function regionEditors() {
    $("regionEditors").replaceChildren();
    for (const [rid, kind] of Object.entries(state.bindings.region_kinds)) {
      const box = node("div", null, { class: "region-editor" }),
        name = node("input", null, {
          type: "text",
          value: state.names[rid] || rid,
          "aria-label": rid + " name",
          maxlength: "200",
        });
      const type = node("select", null, { "aria-label": rid + " type" });
      for (const k of ["room", "corridor"]) type.append(node("option", k, { value: k }));
      type.value = kind;
      const focus = node("button", rid);
      focus.onclick = () => {
        selectedEntity = rid;
        drawViews();
      };
      name.oninput = () => {
        state.names[rid] = name.value;
        edit();
      };
      type.onchange = () => {
        state.bindings.region_kinds[rid] = type.value;
        state.semantics_confirmed = false;
        $("confirmKinds").checked = false;
        roleOptions();
        edit();
      };
      box.append(focus, name, type);
      $("regionEditors").append(box);
    }
    $("confirmKinds").checked = state.semantics_confirmed;
    $("settingsEditor").replaceChildren();
    for (const [k, v] of Object.entries({ ...settingsDefaults, ...state.bindings.settings })) {
      const label = node("label", k.replaceAll("_cm", "").replaceAll("_", " ")),
        input = node("input", null, {
          type: "number",
          min: "0.001",
          step: "any",
          value: String(v),
          "aria-label": k,
        });
      input.oninput = () => {
        state.bindings.settings = {
          ...settingsDefaults,
          ...state.bindings.settings,
          [k]: input.value === "" ? null : Number(input.value),
        };
        edit();
      };
      label.append(input);
      $("settingsEditor").append(label);
    }
    $("validationMode").value = state.validation_mode;
    roleOptions();
  }
  function roleOptions() {
    for (const role of ["start", "goal"]) {
      const el = $(role + "Room");
      el.replaceChildren(node("option", "None", { value: "" }));
      for (const [rid, kind] of Object.entries(state.bindings.region_kinds))
        if (kind === "room") el.append(node("option", state.names[rid] || rid, { value: rid }));
      el.value = state[role + "_room_id"] || "";
    }
  }
  function relationEditors() {
    $("relationEditors").replaceChildren();
    for (const o of session.draft.layout.openings) {
      const box = node("div", null, { class: "relation-editor" });
      box.append(node("strong", o.id + " · " + o.type));
      for (const kind of o.type === "open_passage"
        ? ["centered_opening", "full_span_opening"]
        : ["centered_opening"]) {
        const label = node("label", null, { class: "check" }),
          input = node("input", null, { type: "checkbox", "aria-label": o.id + " " + kind });
        input.checked =
          state.bindings.relations?.some((r) => r.opening_id === o.id && r.type === kind) || false;
        label.append(
          input,
          document.createTextNode(
            kind === "centered_opening"
              ? "Centered on supporting interface"
              : "Full-span entrance (minus wall thickness)",
          ),
        );
        input.onchange = () => {
          state.bindings.relations = (state.bindings.relations || []).filter(
            (r) => !(r.opening_id === o.id && r.type === kind),
          );
          if (input.checked)
            state.bindings.relations.push({
              id: "rel-" + crypto.randomUUID().slice(0, 8),
              type: kind,
              opening_id: o.id,
              state: "confirmed",
              note: "User explicitly enabled " + kind + " for " + o.id + " in metric review.",
            });
          edit();
        };
        box.append(label);
      }
      $("relationEditors").append(box);
    }
  }
  function lockEditors() {
    $("lockEditors").replaceChildren();
    for (const r of (state.bindings.relations || []).filter((r) => r.type === "point_lock")) {
      const box = node("div", null, { class: "lock-editor" }),
        vertex = node("select", null, { "aria-label": "Lock vertex" }),
        axis = node("select", null, { "aria-label": "Lock axis" }),
        value = node("input", null, {
          type: "number",
          step: "any",
          value: String(r.value_cm),
          "aria-label": "Lock value cm",
        }),
        remove = node("button", "Remove lock");
      for (const v of session.draft.layout.vertices)
        vertex.append(node("option", v.id, { value: v.id }));
      vertex.value = r.vertex_id;
      for (const a of ["x", "y"]) axis.append(node("option", a, { value: a }));
      axis.value = r.axis;
      vertex.onchange = () => {
        r.vertex_id = vertex.value;
        selectedEntity = r.vertex_id;
        edit();
      };
      axis.onchange = () => {
        r.axis = axis.value;
        edit();
      };
      value.oninput = () => {
        r.value_cm = value.value === "" ? null : Number(value.value);
        edit();
      };
      remove.onclick = () => {
        state.bindings.relations = state.bindings.relations.filter((x) => x.id !== r.id);
        lockEditors();
        edit();
      };
      box.append(vertex, axis, value, remove);
      $("lockEditors").append(box);
    }
  }
  function renderIssues() {
    $("metricIssues").replaceChildren();
    const issues = session.report.validation.issues;
    if (!issues.length)
      $("metricIssues").append(
        node("div", "Metric checks passed. Compare the result with your drawing.", { class: "ok" }),
      );
    for (const issue of issues) {
      const button = node(
        "button",
        issue.message + (issue.element_ids.length ? " · " + issue.element_ids.join(", ") : ""),
        { class: "issue" },
      );
      button.onclick = () => {
        const found = state.bindings.dimensions.find(
          (d) =>
            issue.element_ids.includes(d.id) ||
            d.provenance.evidence_ids.some((id) => issue.element_ids.includes(id)),
        );
        if (found) {
          selectedDimension = found.id;
          dimensionList();
          dimensionEditor();
          $("dimensionValue").focus();
        } else {
          selectedEntity = issue.element_ids[0];
          drawViews();
        }
      };
      $("metricIssues").append(button);
    }
    $("solverDetails").textContent = JSON.stringify(
      {
        rank: session.report.rank,
        variables: session.report.variable_count,
        nullity: session.report.nullity,
        equations: session.report.equations,
        source: session.report.source,
        ignored_texts: state.bindings.ignored_texts,
      },
      null,
      2,
    );
  }
  function coordinates(metric) {
    if (!metric) return session.report.pixel_topology.vertices;
    return Object.fromEntries(session.draft.layout.vertices.map((v) => [v.id, v.position_cm]));
  }
  function segmentFor(d, metric) {
    if (!d) return null;
    const t = d.target,
      L = session.draft.layout,
      V = coordinates(metric),
      O = L.openings.find((o) => o.id === t.opening_id);
    const region = (id) => L.rooms.concat(L.corridors).find((r) => r.id === id);
    const bounds = (id) => {
      const ps = region(id)?.boundary_vertex_ids.map((v) => V[v]);
      if (!ps || ps.some((p) => !p || p.includes(null))) return null;
      return [
        Math.min(...ps.map((p) => p[0])),
        Math.min(...ps.map((p) => p[1])),
        Math.max(...ps.map((p) => p[0])),
        Math.max(...ps.map((p) => p[1])),
      ];
    };
    const opening = (id) => {
      if (!metric) return session.report.pixel_topology.openings[id];
      const o = L.openings.find((o) => o.id === id);
      if (!o || o.center_offset_cm === null || o.clear_width_cm === null) return null;
      const w = L.walls.find((w) => w.id === o.wall_id),
        a = V[w.start_vertex_id];
      if (!a || a.includes(null)) return null;
      const axis = w.axis === "x" ? 0 : 1,
        p = [...a],
        q = [...a];
      p[axis] += o.center_offset_cm - o.clear_width_cm / 2;
      q[axis] += o.center_offset_cm + o.clear_width_cm / 2;
      return [p, q];
    };
    if (t.type === "wall_chain") {
      const a = L.walls.find((w) => w.id === t.wall_ids[0]),
        b = L.walls.find((w) => w.id === t.wall_ids.at(-1));
      return a && b ? [V[a.start_vertex_id], V[b.end_vertex_id]] : null;
    }
    if (t.type === "region_span") {
      const b = bounds(t.region_id);
      if (!b) return null;
      return t.axis === "x"
        ? [
            [b[0], b[1]],
            [b[2], b[1]],
          ]
        : [
            [b[0], b[1]],
            [b[0], b[3]],
          ];
    }
    if (t.type === "opening_width") return opening(t.opening_id);
    if (t.type === "opening_separation") {
      const a = opening(t.from_opening_id),
        b = opening(t.to_opening_id);
      return a && b ? [a[1], b[0]] : null;
    }
    if (t.type === "opening_offset" && O) {
      const ps = opening(t.opening_id),
        b = bounds(t.region_id);
      if (!ps || !b) return null;
      const axis = ["north", "south"].includes(t.side) ? 0 : 1,
        max = t.reference === "max_corner",
        edge = copy(ps[max ? 1 : 0]);
      if (d.basis === "center_offset") edge[axis] = (ps[0][axis] + ps[1][axis]) / 2;
      const corner = [...edge];
      corner[axis] = b[axis + (max ? 2 : 0)];
      return [corner, edge];
    }
    return null;
  }
  function drawViews() {
    if (!session || !state) return;
    const L = session.draft.layout,
      d = currentDimension(),
      selected = d?.target;
    for (const [name, metric] of [
      ["observed", false],
      ["metricPlan", true],
    ]) {
      const view = $(name);
      view.replaceChildren();
      const V = coordinates(metric),
        available = Object.values(V).filter((p) => p && !p.includes(null));
      if (!metric) {
        view.setAttribute("viewBox", `0 0 ${session.frame.width_px} ${session.frame.height_px}`);
        svg(
          "image",
          {
            href: "/api/image?case=" + encodeURIComponent(caseId),
            width: session.frame.width_px,
            height: session.frame.height_px,
            opacity: ".75",
          },
          view,
        );
      } else {
        if (!available.length) {
          view.setAttribute("viewBox", "0 0 500 300");
          svg("text", { x: 25, y: 140, fill: "#71817b", "font-size": 15 }, view).textContent =
            "Resolve the missing or conflicting measurements.";
          continue;
        }
        const xs = available.map((p) => p[0]),
          ys = available.map((p) => -p[1]),
          span = Math.max(
            Math.max(...xs) - Math.min(...xs),
            Math.max(...ys) - Math.min(...ys),
            100,
          ),
          pad = 0.12 * span;
        view.setAttribute(
          "viewBox",
          `${Math.min(...xs) - pad} ${Math.min(...ys) - pad} ${Math.max(...xs) - Math.min(...xs) + 2 * pad} ${Math.max(...ys) - Math.min(...ys) + 2 * pad}`,
        );
      }
      const extent = Number(view.getAttribute("viewBox").split(" ")[2]) || 500,
        font = extent / 45;
      for (const r of L.rooms.concat(L.corridors)) {
        const points = r.boundary_vertex_ids.map((id) => V[id]);
        if (points.some((p) => !p || p.includes(null))) continue;
        const active = r.id === selectedEntity || r.id === selected?.region_id;
        const poly = svg(
          "polygon",
          {
            points: points.map((p) => [p[0], -p[1]].join(",")).join(" "),
            fill: active ? "#e9b95355" : "#25896e15",
            stroke: "none",
            "data-id": r.id,
          },
          view,
        );
        poly.onclick = () => {
          selectedEntity = r.id;
          drawViews();
        };
        const center = points.reduce(
          (a, p) => [a[0] + p[0] / points.length, a[1] + p[1] / points.length],
          [0, 0],
        );
        svg(
          "text",
          {
            x: center[0],
            y: -center[1],
            "font-size": font,
            fill: "#476c5c",
            "text-anchor": "middle",
          },
          view,
        ).textContent =
          (state.names[r.id] || r.id) + (metric ? " · " + state.bindings.region_kinds[r.id] : "");
        if (metric) {
          const width = Math.max(...points.map((p) => p[0])) - Math.min(...points.map((p) => p[0])),
            depth = Math.max(...points.map((p) => p[1])) - Math.min(...points.map((p) => p[1]));
          svg(
            "text",
            {
              x: center[0],
              y: -center[1] + 1.4 * font,
              "font-size": font * 0.85,
              fill: "#647b70",
              "text-anchor": "middle",
            },
            view,
          ).textContent = `${Number(width.toFixed(3))} × ${Number(depth.toFixed(3))} cm`;
        }
      }
      const line = (a, b, color, width = 2, dash = "") => {
        if (!a || !b || a.includes(null) || b.includes(null)) return null;
        return svg(
          "line",
          {
            x1: a[0],
            y1: -a[1],
            x2: b[0],
            y2: -b[1],
            stroke: color,
            "stroke-width": width,
            "vector-effect": "non-scaling-stroke",
            "stroke-dasharray": dash,
          },
          view,
        );
      };
      for (const w of L.walls) {
        const el = line(
          V[w.start_vertex_id],
          V[w.end_vertex_id],
          w.id === selectedEntity ? "#b17916" : "#287c6c",
          2,
        );
        if (el) {
          el.setAttribute("data-id", w.id);
          el.onclick = () => {
            selectedEntity = w.id;
            drawViews();
          };
        }
      }
      for (const o of L.openings) {
        const ps = segmentFor({ target: { type: "opening_width", opening_id: o.id } }, metric);
        if (ps) {
          line(...ps, "#fff", 7);
          const el = line(...ps, o.id === selectedEntity ? "#b17916" : "#654eb0", 3);
          if (el) {
            el.setAttribute("data-id", o.id);
            el.onclick = () => {
              selectedEntity = o.id;
              drawViews();
            };
          }
        }
      }
      if (!metric && $("showText").checked) {
        for (const box of session.text_boxes) {
          if (!box.polygon_review_px) continue;
          const active = d?.provenance.evidence_ids.includes(box.id);
          const poly = svg(
            "polygon",
            {
              points: box.polygon_review_px.map((p) => p.join(",")).join(" "),
              fill: active ? "#e9b95344" : "#edb8470a",
              stroke: active ? "#b17916" : "#c8a855",
              "stroke-width": 1,
              "vector-effect": "non-scaling-stroke",
              "data-id": box.id,
            },
            view,
          );
          poly.onclick = () => {
            const found = state.bindings.dimensions.find((x) =>
              x.provenance.evidence_ids.includes(box.id),
            );
            if (found) {
              selectedDimension = found.id;
              dimensionList();
              dimensionEditor();
            }
          };
        }
      }
      const span = segmentFor(d, metric);
      if (span && span.every((p) => p && !p.includes(null))) {
        line(...span, "#e08f19", 4, "6 3");
        for (const p of span)
          svg("circle", { cx: p[0], cy: -p[1], r: extent / 110, fill: "#e08f19" }, view);
        if (metric && d.value_cm !== null)
          svg(
            "text",
            {
              x: (span[0][0] + span[1][0]) / 2,
              y: -(span[0][1] + span[1][1]) / 2 - font * 0.6,
              "font-size": font,
              fill: "#9b6214",
              "text-anchor": "middle",
            },
            view,
          ).textContent = d.value_cm + " cm";
      }
      if (selectedEntity && V[selectedEntity] && !V[selectedEntity].includes(null)) {
        const p = V[selectedEntity];
        svg("circle", { cx: p[0], cy: -p[1], r: extent / 80, fill: "#b17916" }, view);
      }
    }
    $("solveStatus").textContent =
      `${session.report.status} · rank ${session.report.rank}/${session.report.variable_count}`;
    $("metricMissing").textContent = session.report.unresolved_variables.length
      ? `${session.report.unresolved_variables.length} unresolved scalar values. Only fully located regions are drawn; missing lengths are never guessed.`
      : "Openings show clear widths. Wall centerlines define room dimensions.";
  }
  function drawCrop(id) {
    const view = $("evidenceCrop");
    view.replaceChildren();
    const polygon = session.text_boxes.find((b) => b.id === id)?.polygon_review_px;
    if (!polygon) {
      view.setAttribute("viewBox", "0 0 400 90");
      svg("text", { x: 15, y: 48, fill: "#71817b", "font-size": 14 }, view).textContent =
        "No text crop is available for this evidence.";
      return;
    }
    const xs = polygon.map((p) => p[0]),
      ys = polygon.map((p) => p[1]),
      pad = 12;
    view.setAttribute(
      "viewBox",
      `${Math.min(...xs) - pad} ${Math.min(...ys) - pad} ${Math.max(...xs) - Math.min(...xs) + 2 * pad} ${Math.max(...ys) - Math.min(...ys) + 2 * pad}`,
    );
    svg(
      "image",
      {
        href: "/api/image?case=" + encodeURIComponent(caseId),
        width: session.frame.width_px,
        height: session.frame.height_px,
      },
      view,
    );
  }
  function renderAll() {
    buildTargets();
    dimensionList();
    regionEditors();
    relationEditors();
    lockEditors();
    dimensionEditor();
    renderIssues();
    drawViews();
    status();
  }
  $("dimensionList").onchange = () => {
    selectedDimension = $("dimensionList").value;
    selectedEntity = null;
    dimensionEditor();
  };
  $("dimensionValue").oninput = () => {
    $("confirmDimension").checked = false;
    updateDimension();
  };
  $("confirmDimension").onchange = updateDimension;
  $("dimensionNote").oninput = updateDimension;
  $("dimensionTarget").onchange = () => {
    $("confirmDimension").checked = false;
    updateDimension();
    dimensionEditor();
  };
  $("addMeasurement").onclick = () => {
    const d = {
      id: "user-" + crypto.randomUUID().slice(0, 8),
      value_cm: null,
      basis: "wall_centerline",
      target: { type: "unassigned" },
      state: "missing",
      span_label: "User supplied measurement",
      provenance: {
        method: "user_correction",
        evidence_ids: [],
        note: "User supplied an unwritten measurement.",
      },
    };
    state.bindings.dimensions.push(d);
    selectedDimension = d.id;
    buildTargets();
    dimensionList();
    dimensionEditor();
    edit();
  };
  $("removeMeasurement").onclick = () => {
    const d = currentDimension();
    if (!d || d.provenance.evidence_ids.length) return;
    state.bindings.dimensions = state.bindings.dimensions.filter((x) => x.id !== d.id);
    selectedDimension = state.bindings.dimensions[0]?.id || null;
    dimensionList();
    dimensionEditor();
    edit();
  };
  $("ignoreText").onclick = () => {
    const d = currentDimension();
    if (!d) return;
    for (const evidence_id of d.provenance.evidence_ids) {
      state.bindings.ignored_texts.push({
        evidence_id,
        reason: "User marked this OCR evidence as not a measurement in metric review.",
      });
    }
    state.bindings.dimensions = state.bindings.dimensions.filter((x) => x.id !== d.id);
    selectedDimension = state.bindings.dimensions[0]?.id || null;
    dimensionList();
    dimensionEditor();
    edit();
  };
  $("confirmKinds").onchange = () => {
    state.semantics_confirmed = $("confirmKinds").checked;
    edit();
  };
  $("validationMode").onchange = () => {
    state.validation_mode = $("validationMode").value;
    edit();
  };
  for (const role of ["start", "goal"])
    $(role + "Room").onchange = () => {
      state[role + "_room_id"] = $(role + "Room").value || null;
      edit();
    };
  $("addLock").onclick = () => {
    state.bindings.relations.push({
      id: "lock-" + crypto.randomUUID().slice(0, 8),
      type: "point_lock",
      vertex_id: session.draft.layout.vertices[0].id,
      axis: "x",
      value_cm: 0,
      state: "confirmed",
      note: "User added a metric coordinate lock in the chosen origin frame.",
    });
    lockEditors();
    edit();
  };
  $("recompute").onclick = () => transact("save");
  $("metricUndo").onclick = () => transact("undo");
  $("metricRedo").onclick = () => transact("redo");
  $("acceptMetric").onclick = () => transact("accept");
  $("reviewerName").oninput = status;
  $("showText").onchange = drawViews;
  $("reloadMetric").onclick = () => load(caseId || $("metricCase").value);
  $("metricCase").onchange = () => load($("metricCase").value);
  $("downloadMetric").onclick = () => {
    if (!$("downloadMetric").disabled)
      location.href = caseId.startsWith("Job_")
        ? "/jobs/" + encodeURIComponent(caseId) + "/layout?revision_id=" + encodeURIComponent(base)
        : "/api/metric/export?case=" +
          encodeURIComponent(caseId) +
          "&revision_id=" +
          encodeURIComponent(base);
  };
  window.addEventListener("beforeunload", (event) => {
    if (dirty()) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  async function boot() {
    status();
    const data = await api("/api/bootstrap");
    token = data.token;
    for (const id of data.cases)
      $("metricCase").append(node("option", data.labels[id] || id, { value: id }));
    const requested = new URL(location.href).searchParams.get("case"),
      initial = data.cases.includes(requested) ? requested : data.cases[0];
    if (initial) {
      $("metricCase").value = initial;
      await load(initial);
    } else message("Upload and approve a drawing in topology review first.");
  }
  boot().catch((error) => message(error.message, true));
})();
