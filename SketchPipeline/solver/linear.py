from copy import deepcopy
import numpy as np
from SketchPipeline.validation.validate import validate_document, VERSION as VALIDATOR_VERSION

VERSION = "metric-solver/1.0"
EPS = 1e-06


class MetricSystem:

    def __init__(self, document):
        self.doc = document
        layout = document["layout"]
        self.vertices = {v["id"]: v for v in layout["vertices"]}
        self.walls = {w["id"]: w for w in layout["walls"]}
        self.regions = {r["id"]: r for r in layout["rooms"] + layout["corridors"]}
        self.openings = {o["id"]: o for o in layout["openings"]}
        self.names = [f"{v}:{a}" for v in self.vertices for a in ("x", "y")]
        self.names += [f"{o}:{a}" for o in self.openings for a in ("center", "width")]
        self.index = {n: i for i, n in enumerate(self.names)}
        self.rows = []
        self.extrema = {}
        for axis in ("x", "y"):
            parent = {v: v for v in self.vertices}

            def root(v):
                while parent[v] != v:
                    v = parent[v]
                return v

            for w in self.walls.values():
                if w["axis"] != axis:
                    parent[root(w["end_vertex_id"])] = root(w["start_vertex_id"])
            for rid, r in self.regions.items():
                groups = {root(v) for v in r["boundary_vertex_ids"]}
                incoming, outgoing = (set(), set())
                for wid in r["boundary_wall_ids"]:
                    w = self.walls[wid]
                    if w["axis"] == axis:
                        a, b = (root(w["start_vertex_id"]), root(w["end_vertex_id"]))
                        outgoing.add(a)
                        incoming.add(b)
                lo, hi = (groups - incoming, groups - outgoing)
                if len(lo) != 1 or len(hi) != 1 or lo == hi:
                    raise ValueError(f"{rid}: ambiguous/non-rectangular {axis} topology")
                self.extrema[rid, axis] = (
                    next((v for v in r["boundary_vertex_ids"] if root(v) in lo)),
                    next((v for v in r["boundary_vertex_ids"] if root(v) in hi)),
                )

    def variable(self, element, field):
        return {f"{element}:{field}": 1.0}

    @staticmethod
    def add(*terms):
        result = {}
        for scale, values in terms:
            for key, value in values.items():
                result[key] = result.get(key, 0) + scale * value
        return {k: v for k, v in result.items() if v}

    def span(self, rid, axis):
        lo, hi = self.extrema[rid, axis]
        return self.add((1, self.variable(hi, axis)), (-1, self.variable(lo, axis)))

    def wall_span(self, wid):
        w = self.walls[wid]
        return self.add(
            (1, self.variable(w["end_vertex_id"], w["axis"])),
            (-1, self.variable(w["start_vertex_id"], w["axis"])),
        )

    def expression(self, target, basis):
        t = target["type"]
        if t == "region_span":
            if basis != "wall_centerline":
                raise ValueError("region_span needs wall_centerline")
            return self.span(target["region_id"], target["axis"])
        if t == "wall_chain":
            if basis != "wall_centerline":
                raise ValueError("wall_chain needs wall_centerline")
            chain = [self.walls[w] for w in target["wall_ids"]]
            if not chain or any((w["axis"] != chain[0]["axis"] for w in chain)):
                raise ValueError("wall_chain must have one axis")
            if any((a["end_vertex_id"] != b["start_vertex_id"] for a, b in zip(chain, chain[1:]))):
                raise ValueError("wall_chain must be contiguous and positive ordered")
            return self.add(*[(1, self.wall_span(w["id"])) for w in chain])
        if t == "opening_separation":
            if basis != "edge_offset":
                raise ValueError("separation needs edge_offset")
            a, b = (target["from_opening_id"], target["to_opening_id"])
            if a == b or self.openings[a]["wall_id"] != self.openings[b]["wall_id"]:
                raise ValueError("separation needs distinct openings on the same noded wall")
            return self.add(
                (1, self.variable(b, "center")),
                (-1, self.variable(a, "center")),
                (-0.5, self.variable(a, "width")),
                (-0.5, self.variable(b, "width")),
            )
        o = self.openings[target["opening_id"]]
        if t == "opening_width":
            if basis != "clear_opening":
                raise ValueError("opening_width needs clear_opening")
            return self.variable(o["id"], "width")
        if t == "opening_offset":
            if basis not in ("edge_offset", "center_offset"):
                raise ValueError("invalid offset basis")
            w = self.walls[o["wall_id"]]
            rid, side = (target["region_id"], target["side"])
            axis = "x" if side in ("north", "south") else "y"
            normal = "y" if axis == "x" else "x"
            r = self.regions[rid]
            if w["id"] not in r["boundary_wall_ids"] or axis != w["axis"]:
                raise ValueError("opening_offset wall is not the requested region side")
            boundary = self.extrema[rid, normal][1 if side in ("north", "east") else 0]
            seen, queue = ({boundary}, [boundary])
            while queue:
                v = queue.pop()
                for edge in self.walls.values():
                    if edge["axis"] == axis and v in (
                        edge["start_vertex_id"],
                        edge["end_vertex_id"],
                    ):
                        for u in (edge["start_vertex_id"], edge["end_vertex_id"]):
                            if u not in seen:
                                seen.add(u)
                                queue.append(u)
            if w["start_vertex_id"] not in seen:
                raise ValueError("opening_offset names the wrong region side")
            center = self.add(
                (1, self.variable(w["start_vertex_id"], axis)),
                (1, self.variable(o["id"], "center")),
            )
            lo, hi = self.extrema[rid, axis]
            if target["reference"] == "min_corner":
                expr = self.add((1, center), (-1, self.variable(lo, axis)))
            elif target["reference"] == "max_corner":
                expr = self.add((1, self.variable(hi, axis)), (-1, center))
            else:
                raise ValueError("invalid offset reference")
            return self.add(
                (1, expr), (-0.5 if basis == "edge_offset" else 0, self.variable(o["id"], "width"))
            )
        raise ValueError(f"Unsupported dimension target: {t}")

    def equation(self, identifier, terms, value, evidence=(), kind="dimension"):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or (not np.isfinite(value))
        ):
            raise ValueError(f"{identifier}: finite numeric RHS required")
        for key in terms:
            if key not in self.index:
                raise ValueError(f"Unknown variable {key}")
        self.rows.append(
            {
                "id": identifier,
                "kind": kind,
                "terms": terms,
                "value_cm": value,
                "evidence_ids": list(evidence),
            }
        )

    def build(self, dimensions, relations, origin_vertex_id=None):
        if not self.vertices:
            raise ValueError("No vertices")
        origin = origin_vertex_id or next(iter(self.vertices))
        for axis in ("x", "y"):
            self.equation(f"origin:{axis}", self.variable(origin, axis), 0, kind="gauge")
        for w in self.walls.values():
            axis = "y" if w["axis"] == "x" else "x"
            self.equation(
                f"orthogonal:{w['id']}",
                self.add(
                    (1, self.variable(w["start_vertex_id"], axis)),
                    (-1, self.variable(w["end_vertex_id"], axis)),
                ),
                0,
                kind="topology",
            )
        for d in dimensions:
            if (
                d["state"] == "confirmed"
                and d["value_cm"] is not None
                and (d["target"]["type"] != "unassigned")
            ):
                self.equation(
                    d["id"],
                    self.expression(d["target"], d["basis"]),
                    d["value_cm"],
                    d["provenance"]["evidence_ids"],
                )
        seen = set()
        for r in relations:
            if r["id"] in seen:
                raise ValueError("Duplicate relation ID")
            seen.add(r["id"])
            if r.get("state") != "confirmed":
                raise ValueError("Relations require explicit confirmation")
            evidence = r.get("evidence_ids", [])
            if not r.get("note", "").strip():
                raise ValueError("Explicit relation needs a reason/note")
            if r["type"] == "point_lock":
                self.equation(
                    r["id"],
                    self.variable(r["vertex_id"], r["axis"]),
                    r["value_cm"],
                    evidence,
                    "user_lock",
                )
            elif r["type"] in ("centered_opening", "full_span_opening"):
                o = self.openings[r["opening_id"]]
                span = self.wall_span(o["wall_id"])
                self.equation(
                    r["id"] + ":center",
                    self.add((1, self.variable(o["id"], "center")), (-0.5, span)),
                    0,
                    evidence,
                    "explicit_relation",
                )
                if r["type"] == "full_span_opening":
                    if o["type"] != "open_passage":
                        raise ValueError("full_span_opening needs open_passage")
                    self.equation(
                        r["id"] + ":width",
                        self.add((1, self.variable(o["id"], "width")), (-1, span)),
                        -self.doc["settings"]["wall_thickness_cm"],
                        evidence,
                        "explicit_relation",
                    )
            else:
                raise ValueError("Unknown relation type")
        return self

    def numerical(self):
        a = np.zeros((len(self.rows), len(self.names)))
        b = np.array([r["value_cm"] for r in self.rows], dtype=float)
        for i, row in enumerate(self.rows):
            for name, value in row["terms"].items():
                a[i, self.index[name]] = value
        _, s, vh = np.linalg.svd(a, full_matrices=True)
        threshold = max(a.shape) * np.finfo(float).eps * (s[0] if len(s) else 1)
        rank = int(np.sum(s > threshold))
        q = np.linalg.lstsq(a, b, rcond=threshold / s[0] if len(s) and s[0] else None)[0]
        residual = a @ q - b
        conflict = bool(np.max(np.abs(residual), initial=0) > EPS)
        nullspace = vh[rank:]
        fixed = np.max(np.abs(nullspace), axis=0, initial=0) < 1e-08
        values = {
            name: float(round(q[i], 9)) if fixed[i] and (not conflict) else None
            for i, name in enumerate(self.names)
        }
        equations = [
            dict(r, diagnostic_residual_cm=float(residual[i])) for i, r in enumerate(self.rows)
        ]
        return (
            values,
            {
                "status": (
                    "inconsistent"
                    if conflict
                    else "determined" if rank == len(self.names) else "underdetermined"
                ),
                "variable_count": len(self.names),
                "equation_count": len(self.rows),
                "rank": rank,
                "nullity": len(self.names) - rank,
                "singular_values": s.tolist(),
                "rank_threshold": float(threshold),
                "residual_tolerance_cm": EPS,
                "max_residual_cm": float(np.max(np.abs(residual), initial=0)),
                "unresolved_variables": [k for k, v in values.items() if v is None],
                "equations": equations,
                "nullspace_modes": [
                    {self.names[i]: float(v) for i, v in enumerate(mode) if abs(v) > 1e-08}
                    for mode in nullspace
                ],
                "residual_note": "Least-squares residuals are diagnostics; inconsistent averages are never published as geometry.",
            },
        )


def solve(document, *, relations=(), origin_vertex_id=None, observations=None):
    draft = deepcopy(document)
    dimensions = draft["layout"]["dimensions"]
    system = MetricSystem(draft).build(dimensions, relations, origin_vertex_id)
    values, report = system.numerical()
    report["solution_variables_cm"] = values
    publication_issues = []
    evidence = sorted({e for row in system.rows for e in row["evidence_ids"]})
    provenance = {
        "method": "derived",
        "evidence_ids": evidence,
        "note": "Exact hard metric constraints; see equation report. No pixel scale or implicit centering.",
    }
    for v in draft["layout"]["vertices"]:
        v["position_cm"] = [values[f"{v['id']}:{a}"] for a in ("x", "y")]
        v["state"] = "derived" if None not in v["position_cm"] else "missing"
        v["provenance"] = deepcopy(provenance)
    for o in draft["layout"]["openings"]:
        o["center_offset_cm"] = values[f"{o['id']}:center"]
        o["clear_width_cm"] = values[f"{o['id']}:width"]
        o["clear_height_cm"] = draft["settings"][
            "wall_height_cm" if o["type"] == "open_passage" else "door_height_cm"
        ]
        for field in ("center_offset_cm", "clear_width_cm"):
            value = o[field]
            if value is not None and (value < 0 or (field == "clear_width_cm" and value == 0)):
                publication_issues.append(
                    {
                        "code": "SKETCH_OPENING_OUT_OF_BOUNDS",
                        "severity": "error",
                        "element_ids": [o["id"]],
                        "message": f"Hard equations imply invalid {field}={value}; see solution_variables_cm.",
                    }
                )
                o[field] = None
        resolved = o["center_offset_cm"] is not None and o["clear_width_cm"] is not None
        explicit_width = any(
            (
                d["state"] == "confirmed"
                and d["target"] == {"type": "opening_width", "opening_id": o["id"]}
                for d in dimensions
            )
        )
        o["state"] = ("confirmed" if explicit_width else "derived") if resolved else "missing"
        o["provenance"] = deepcopy(provenance)
    draft.update(
        kind="draft_layout",
        status="draft",
        algorithm_version=VERSION,
        review={"status": "pending", "reviewer": None},
        issues=publication_issues,
    )
    draft["validation"] = {
        "metric": "not_run",
        "validator_version": None,
        "tolerance_cm": 0.001,
        "engine_geometry": "not_run",
        "navigation": "not_run",
    }
    if report["status"] != "determined":
        draft["issues"].append(
            {
                "code": (
                    "SKETCH_DIMENSION_CONFLICT"
                    if report["status"] == "inconsistent"
                    else "SKETCH_GEOMETRY_INCOMPLETE"
                ),
                "severity": "error",
                "element_ids": [d["id"] for d in dimensions],
                "message": f"Hard metric system {report['status']}; rank {report['rank']}/{report['variable_count']}. See equations/residuals.",
            }
        )
    if any((d["state"] == "conflicting" for d in dimensions)):
        draft["issues"].append(
            {
                "code": "SKETCH_DIMENSION_CONFLICT",
                "severity": "error",
                "element_ids": [],
                "message": "An input dimension is marked conflicting; resolve it in review.",
            }
        )
    check = validate_document(draft, observations)
    report["validation"] = check
    draft["issues"] = check["issues"]
    draft["validation"].update(
        metric="passed" if check["metric_valid"] else "failed", validator_version=VALIDATOR_VERSION
    )
    hard_ids = {d["id"] for d in dimensions if d["state"] in ("confirmed", "conflicting")}
    hard_conflict = any(
        (
            i["code"] == "SKETCH_DIMENSION_CONFLICT"
            and (not i["element_ids"] or set(i["element_ids"]) <= hard_ids)
            for i in check["issues"]
        )
    )
    draft["status"] = (
        "conflicting"
        if report["status"] == "inconsistent" or hard_conflict
        else "draft" if check["metric_valid"] else "needs_review"
    )
    report["reconstruction_status"] = draft["status"]
    report["algorithm_version"] = VERSION
    report["explicit_relations"] = list(relations)
    report["exportable"] = False
    return (draft, report)
