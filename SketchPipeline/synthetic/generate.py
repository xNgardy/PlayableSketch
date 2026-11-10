import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import html
import json
import math
from pathlib import Path
import random
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from jsonschema import Draft202012Validator
from SketchPipeline.fixtures.build_tablet_references import ANNOTATIONS, build_case
from SketchPipeline.validation.validate import validate_document, SCHEMAS

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "Data/synthetic/v1"
STYLES = {
    "ink": dict(
        font="Bradley Hand Bold.ttf",
        stroke=3.2,
        wobble=1.1,
        ink=32,
        angle=1.5,
        grid=False,
        camera=False,
    ),
    "pencil": dict(
        font="Chalkboard.ttc", stroke=2.2, wobble=2.0, ink=78, angle=3.0, grid=True, camera=False
    ),
    "photo": dict(
        font="Comic Sans MS.ttf", stroke=3.8, wobble=1.7, ink=40, angle=3.0, grid=False, camera=True
    ),
}
FONT_DIR = Path("/System/Library/Fonts/Supplemental")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n")


def quad(box):
    x, y, x1, y1 = box
    return [[x, y], [x1, y], [x1, y1], [x, y1]]


def project(points, H):
    p = np.c_[np.asarray(points, float), np.ones(len(points))] @ H.T
    return (p[:, :2] / p[:, 2:]).round(5).tolist()


def regions_of(rects):
    return [
        dict(id=k, kind="corridor" if k.startswith("c") else "room", bounds_cm=list(v))
        for k, v in rects.items()
    ]


def make_plan(index, extra=False):
    rng = random.Random(71000 + index + (50000 if extra else 0))
    r = {}
    family = (index - 1) % 5 + (5 if extra else 0)

    def R(k, x, y, w, h):
        r[k] = [x, y, x + w, y + h]

    if family == 0:
        x = y = 0
        for j in range(3 + index % 3):
            w = rng.randrange(420, 681, 20)
            h = rng.randrange(560, 841, 20)
            R("r" + chr(65 + j), x, y, w, h)
            x += w
            y += rng.choice([-80, 100, 140])
    elif family == 1:
        w = rng.choice([760, 820, 880])
        h = rng.choice([840, 920, 980])
        s = rng.choice([360, 400, 440])
        R("rA", 0, 0, w, h)
        R("rB", w, 0, 460, s)
        R("rC", w, s, 600, h - s)
        R("rD", 120, h, w - 260, 380)
        R("rE", -400, 120, 400, 460)
    elif family == 2:
        w = rng.choice([520, 580, 640])
        h = rng.choice([680, 740, 800])
        L = rng.choice([280, 340, 400])
        cw = rng.choice([180, 220, 240])
        y = rng.choice([160, 200, 240])
        b = y - 220
        R("rA", 0, 0, w, h)
        R("cH", w, y, L, cw)
        R("rB", w + L, b, 660, 800)
        R("rC", 80, h, w - 160, 380)
        R("rD", w + L + 100, b - 360, 440, 360)
    elif family == 3:
        widths = [
            rng.choice([420, 460, 500]),
            rng.choice([540, 580, 620]),
            rng.choice([380, 420, 460]),
        ]
        dep = rng.choice([460, 500, 540])
        x = 0
        for j, w in enumerate(widths):
            R("r" + chr(65 + j), x, 0, w, dep)
            R("r" + chr(68 + j), x, dep, w, rng.choice([400, 480, 580, 640]))
            x += w
    elif family == 4:
        a = rng.choice([680, 740, 800])
        vx = rng.choice([160, 200, 240])
        cw = rng.choice([180, 200, 220])
        L = rng.choice([280, 320, 380])
        b = vx - 220
        R("rA", 0, 0, a, 400)
        R("cV", vx, 400, cw, L)
        R("rB", b, 400 + L, 820, 600)
        R("rC", b - 380, 500 + L, 380, 400)
        R("rD", a, 0, 360, 400)
    elif family == 5:
        R("rA", 0, 0, 560, 680)
        R("cH", 560, 180, 580, 220)
        R("cV", 920, 400, 220, 420)
        R("rB", 740, 820, 700, 580)
        R("rC", 0, 680, 400, 420)
        R("rD", 1440, 1000, 460, 400)
    elif family == 6:
        R("rA", 0, 0, 520, 940)
        R("cH", 520, 380, 1040, 220)
        R("rB", 1560, 100, 640, 980)
        R("rC", 700, 600, 380, 440)
        R("rD", 1060, -40, 400, 420)
        R("rE", 1780, 1080, 420, 380)
    elif family == 7:
        R("rA", 0, 0, 540, 1540)
        R("cH1", 540, 180, 320, 220)
        R("rB", 860, 0, 660, 560)
        R("cH2", 540, 1040, 440, 240)
        R("rC", 980, 900, 580, 640)
        R("cV", 1200, 560, 200, 340)
        R("rD", -400, 500, 400, 440)
    elif family == 8:
        R("rA", 0, 0, 1040, 1100)
        R("rB", 1040, 0, 480, 1100)
        R("rC", 0, 1100, 380, 440)
        R("rD", 620, 1100, 420, 580)
        R("rE", 1520, 200, 460, 460)
        R("rF", 1160, 1100, 360, 400)
    elif family == 9:
        R("rA", 0, 0, 520, 1080)
        R("cH", 520, 440, 1480, 220)
        R("rB", 2000, 80, 640, 1080)
        R("rC", 680, 660, 380, 440)
        R("rD", 1340, 660, 440, 520)
        R("rE", 1000, 20, 460, 420)
    if extra:
        sx = 1 + index // 5 % 3 * 0.1
        sy = 1 + (index % 3 - 1) * 0.1
        r = {
            k: [round(a * sx) if i % 2 == 0 else round(a * sy) for i, a in enumerate(v)]
            for k, v in r.items()
        }
    contacts = []
    for i, (a, A) in enumerate(r.items()):
        for b, B in list(r.items())[i + 1 :]:
            if min(A[2], B[2]) > max(A[0], B[0]) and min(A[3], B[3]) > max(A[1], B[1]):
                raise ValueError("Region overlap")
            if A[2] == B[0] or B[2] == A[0]:
                lo, hi = (max(A[1], B[1]), min(A[3], B[3]))
                axis = 1
                fixed = max(A[0], B[0])
            elif A[3] == B[1] or B[3] == A[1]:
                lo, hi = (max(A[0], B[0]), min(A[2], B[2]))
                axis = 0
                fixed = max(A[1], B[1])
            else:
                continue
            if hi > lo:
                contacts.append((a, b, axis, fixed, lo, hi))
    labels = []
    opens = []

    def label(value, target, p, q, role):
        labels.append(
            dict(value_cm=value, raw_text=f"{value:g} cm", target=target, span_cm=[p, q], role=role)
        )

    def point(axis, fixed, t):
        return [t, fixed] if axis == 0 else [fixed, t]

    for k, (x, y, x1, y1) in r.items():
        label(
            x1 - x,
            dict(type="region_span", region_id=k, axis="x"),
            [x, y],
            [x1, y],
            "corridor" if k.startswith("c") else "room",
        )
        label(
            y1 - y,
            dict(type="region_span", region_id=k, axis="y"),
            [x, y],
            [x, y1],
            "corridor" if k.startswith("c") else "room",
        )
    corners = {
        tuple(p) for x, y, x1, y1 in r.values() for p in [[x, y], [x1, y], [x1, y1], [x, y1]]
    }
    placement_keys = set()
    for a, b, axis, fixed, lo, hi in contacts:
        for k in (a, b):
            bound = r[k]
            if bound[axis] < lo:
                previous = max(
                    (
                        p[axis]
                        for p in corners
                        if p[1 - axis] == fixed and bound[axis] <= p[axis] < lo
                    )
                )
                p, q = (point(axis, fixed, previous), point(axis, fixed, lo))
                key = (tuple(p), tuple(q))
                if key not in placement_keys:
                    label(
                        lo - previous,
                        dict(type="manual_wall_span", start_cm=p, end_cm=q),
                        p,
                        q,
                        "placement",
                    )
                    placement_keys.add(key)
        kind = "open_passage" if a.startswith("c") or b.startswith("c") else "door"
        count = 2 if kind == "door" and hi - lo >= 700 and (family in (0, 8)) and (axis == 1) else 1
        previous = None
        for j in range(count):
            oid = f"o{len(opens) + 1:03d}"
            width = hi - lo - 20 if kind == "open_passage" else rng.choice([90, 100, 110, 120, 130])
            if kind == "open_passage":
                center = (lo + hi) / 2
            elif count == 2:
                center = lo + (hi - lo) * (0.27 if j == 0 else 0.7)
                center = round(center / 5) * 5
            else:
                room = min((a, b), key=lambda k: r[k][axis])
                offset = rng.randrange(80, max(81, int(hi - lo - width - 80)), 10)
                center = lo + offset + width / 2
            p, q = (point(axis, fixed, center - width / 2), point(axis, fixed, center + width / 2))
            if kind == "door" and (p[axis] - lo < 65 or hi - q[axis] < 65):
                raise ValueError("Insufficient door cap")
            opens.append(
                dict(
                    id=oid,
                    region_ids=[a, b],
                    kind=kind,
                    center_cm=point(axis, fixed, center),
                    clear_width_cm=width,
                    axis=axis,
                    fixed=fixed,
                    lo=lo,
                    hi=hi,
                )
            )
            if kind == "door":
                label(width, dict(type="opening_width", opening_id=oid), p, q, "door_width")
                if previous:
                    last = opens[-2]
                    pp = point(axis, fixed, last["center_cm"][axis] + last["clear_width_cm"] / 2)
                    label(
                        p[axis] - pp[axis],
                        dict(
                            type="opening_separation", from_opening_id=last["id"], to_opening_id=oid
                        ),
                        pp,
                        p,
                        "separation",
                    )
                else:
                    use_max = rng.random() < 0.4
                    k = next(
                        (
                            k
                            for k in (a, b)
                            if r[k][axis + (2 if use_max else 0)] == (hi if use_max else lo)
                        )
                    )
                    ref = point(axis, fixed, hi if use_max else lo)
                    edge = q if use_max else p
                    side = (
                        ("north" if fixed == r[k][3] else "south")
                        if axis == 0
                        else "east" if fixed == r[k][2] else "west"
                    )
                    label(
                        abs(ref[axis] - edge[axis]),
                        dict(
                            type="opening_offset",
                            opening_id=oid,
                            region_id=k,
                            side=side,
                            reference="max_corner" if use_max else "min_corner",
                        ),
                        ref,
                        edge,
                        "offset",
                    )
                previous = oid
    seen = {next(iter(r))}
    while True:
        new = seen | {
            k for o in opens if seen.intersection(o["region_ids"]) for k in o["region_ids"]
        }
        if new == seen:
            break
        seen = new
    assert seen == set(r)
    ident = ("SX" if extra else "SP") + f"{index:03d}"
    return dict(
        id=ident,
        family=family,
        regions=regions_of(r),
        openings=opens,
        labels=labels,
        seed=71000 + index + (50000 if extra else 0),
    )


def metric_rank(draft):
    L = draft["layout"]
    V = {v["id"]: i * 2 for i, v in enumerate(L["vertices"])}
    P = {v["id"]: v["position_cm"] for v in L["vertices"]}
    W = {w["id"]: w for w in L["walls"]}
    R = {r["id"]: r for r in L["rooms"] + L["corridors"]}
    O = {o["id"]: o for o in L["openings"]}
    oi = {k: len(V) * 2 + i * 2 for i, k in enumerate(O)}
    n = len(V) * 2 + len(O) * 2
    rows = []

    def row(terms):
        x = np.zeros(n)
        for k, v in terms:
            x[k] += v
        rows.append(x)

    def endpoint(r, axis, maxi):
        return (max if maxi else min)(R[r]["boundary_vertex_ids"], key=lambda k: P[k][axis])

    for w in W.values():
        a = "xy".index(w["axis"])
        row([(V[w["start_vertex_id"]] + 1 - a, 1), (V[w["end_vertex_id"]] + 1 - a, -1)])
    for m in L["dimensions"]:
        t = m["target"]
        kind = t["type"]
        if kind == "region_span":
            a = "xy".index(t["axis"])
            row(
                [
                    (V[endpoint(t["region_id"], a, True)] + a, 1),
                    (V[endpoint(t["region_id"], a, False)] + a, -1),
                ]
            )
        elif kind == "wall_chain":
            first, last = (W[t["wall_ids"][0]], W[t["wall_ids"][-1]])
            a = "xy".index(first["axis"])
            row([(V[last["end_vertex_id"]] + a, 1), (V[first["start_vertex_id"]] + a, -1)])
        elif kind == "opening_width":
            row([(oi[t["opening_id"]] + 1, 1)])
        elif kind == "opening_separation":
            row(
                [
                    (oi[t["to_opening_id"]], 1),
                    (oi[t["from_opening_id"]], -1),
                    (oi[t["to_opening_id"]] + 1, -0.5),
                    (oi[t["from_opening_id"]] + 1, -0.5),
                ]
            )
        elif kind == "opening_offset":
            w = W[O[t["opening_id"]]["wall_id"]]
            a = "xy".index(w["axis"])
            sgn = -1 if t["reference"] == "max_corner" else 1
            row(
                [
                    (V[w["start_vertex_id"]] + a, sgn),
                    (oi[t["opening_id"]], sgn),
                    (V[endpoint(t["region_id"], a, sgn < 0)] + a, -sgn),
                    (oi[t["opening_id"]] + 1, -0.5),
                ]
            )
    for k, o in O.items():
        if o["type"] == "open_passage":
            w = W[o["wall_id"]]
            a = "xy".index(w["axis"])
            i, j = (V[w["start_vertex_id"]] + a, V[w["end_vertex_id"]] + a)
            row([(oi[k] + 1, 1), (j, -1), (i, 1)])
            row([(oi[k], 1), (j, -0.5), (i, 0.5)])
    row([(0, 1)])
    row([(1, 1)])
    rank = int(np.linalg.matrix_rank(np.array(rows)))
    if rank != n:
        raise ValueError(f"Underdetermined synthetic plan: {rank}/{n}")
    return dict(variables=n, rank=rank, unresolved_degrees_of_freedom=0)


def noded_edges(plan):
    corners = {
        tuple(p)
        for r in plan["regions"]
        for x, y, x1, y1 in [r["bounds_cm"]]
        for p in [[x, y], [x1, y], [x1, y1], [x, y1]]
    }
    edges = {}
    for r in plan["regions"]:
        x, y, x1, y1 = r["bounds_cm"]
        pts = [(x, y), (x1, y), (x1, y1), (x, y1)]
        for a, b in zip(pts, pts[1:] + pts[:1]):
            axis = 0 if a[1] == b[1] else 1
            nodes = sorted(
                (
                    p
                    for p in corners
                    if p[1 - axis] == a[1 - axis]
                    and min(a[axis], b[axis]) <= p[axis] <= max(a[axis], b[axis])
                ),
                key=lambda p: p[axis],
            )
            for p, q in zip(nodes, nodes[1:]):
                edges.setdefault((p, q), []).append(r["id"])
    return edges


def intersects(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def rail_hits_box(lines, box):
    x0, y0, x1, y1 = box
    for a, b in lines:
        if (
            abs(a[0] - b[0]) < 0.01
            and x0 <= a[0] <= x1
            and (max(min(a[1], b[1]), y0) <= min(max(a[1], b[1]), y1))
        ):
            return True
        if (
            abs(a[1] - b[1]) < 0.01
            and y0 <= a[1] <= y1
            and (max(min(a[0], b[0]), x0) <= min(max(a[0], b[0]), x1))
        ):
            return True
    return False


def render(plan, style_name, out):
    style = STYLES[style_name]
    seed = plan["seed"] + list(STYLES).index(style_name) * 1000
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    bounds = np.array([r["bounds_cm"] for r in plan["regions"]])
    xmin, ymin = bounds[:, :2].min(0)
    xmax, ymax = bounds[:, 2:].max(0)
    scale = 0.72
    margin = 340
    W = int((xmax - xmin) * scale + margin * 2)
    H = int((ymax - ymin) * scale + margin * 2)

    def pix(p):
        return [float(margin + (p[0] - xmin) * scale), float(H - margin - (p[1] - ymin) * scale)]

    wall_mask = np.zeros((H, W), np.uint8)
    tick_mask = wall_mask.copy()
    rail_mask = wall_mask.copy()
    text_mask = wall_mask.copy()
    strokes = []
    rails = []

    def inkline(mask, points, width):
        cv2.polylines(
            mask, [np.rint(points).astype(np.int32)], False, 255, max(1, round(width)), cv2.LINE_AA
        )

    def wave(a, b):
        a, b = (np.array(a), np.array(b))
        v = b - a
        length = np.linalg.norm(v)
        normal = np.array([-v[1], v[0]]) / length
        count = max(2, int(length / 18))
        phase = rng.random() * 6.28
        pts = []
        for i, t in enumerate(np.linspace(0, 1, count + 1)):
            bend = math.sin(math.pi * t) * (
                math.sin(t * 5 + phase) * style["wobble"] + rng.uniform(-0.5, 0.5)
            )
            pts.append((a + v * t + normal * bend).tolist())
        return pts

    for (a, b), owners in noded_edges(plan).items():
        axis = 0 if a[1] == b[1] else 1
        lo, hi = (a[axis], b[axis])
        fixed = a[1 - axis]
        cuts = []
        for o in plan["openings"]:
            if set(o["region_ids"]) == set(owners) and o["axis"] == axis and (o["fixed"] == fixed):
                center = o["center_cm"][axis]
                cuts.append(
                    (o["lo"], o["hi"])
                    if o["kind"] == "open_passage"
                    else (center - o["clear_width_cm"] / 2, center + o["clear_width_cm"] / 2)
                )
        nodes = sorted({lo, hi, *[p for cut in cuts for p in cut if lo <= p <= hi]})
        for s, e in zip(nodes, nodes[1:]):
            if any((c <= (s + e) / 2 <= d for c, d in cuts)):
                continue
            pa = [s, fixed] if axis == 0 else [fixed, s]
            pb = [e, fixed] if axis == 0 else [fixed, e]
            pts = wave(pix(pa), pix(pb))
            inkline(wall_mask, pts, style["stroke"] * rng.uniform(0.88, 1.13))
            strokes.append(dict(kind="wall", points_px=pts))
    for o in plan["openings"]:
        axis = o["axis"]
        center = o["center_cm"][axis]
        width = o["clear_width_cm"]
        fixed = o["fixed"]
        lo, hi = (
            (o["lo"], o["hi"])
            if o["kind"] == "open_passage"
            else (center - width / 2, center + width / 2)
        )
        points = [[t, fixed] if axis == 0 else [fixed, t] for t in [lo, hi]]
        o["gap_px"] = [pix(p) for p in points]
        if o["kind"] == "door":
            for p in o["gap_px"]:
                v = [0, 10] if axis == 0 else [10, 0]
                pts = [[p[0] - v[0], p[1] - v[1]], [p[0] + v[0], p[1] + v[1]]]
                inkline(tick_mask, pts, style["stroke"])
                strokes.append(dict(kind="tick", points_px=pts))
    font_path = FONT_DIR / style["font"]
    font = ImageFont.truetype(str(font_path), 32)
    occupied = []
    patches = []
    label_records = []
    static = cv2.bitwise_or(wall_mask, tick_mask)
    for i, label in enumerate(plan["labels"]):
        text = label["raw_text"]
        bb = font.getbbox(text)
        patch = Image.new("L", (bb[2] - bb[0] + 8, bb[3] - bb[1] + 8), 0)
        ImageDraw.Draw(patch).text((4 - bb[0], 4 - bb[1]), text, font=font, fill=255)
        patch = patch.resize(
            (round(patch.width * rng.uniform(0.94, 1.07)), patch.height), Image.Resampling.BICUBIC
        ).rotate(
            rng.uniform(-style["angle"], style["angle"]),
            resample=Image.Resampling.BICUBIC,
            expand=True,
        )
        a, b = map(pix, label["span_cm"])
        vertical = abs(a[0] - b[0]) < 0.01
        if vertical:
            patch = patch.transpose(Image.Transpose.ROTATE_90)
        pw, ph = patch.size
        mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
        chosen = None
        offsets = [s * x for x in [38, 66, 96, 132, 176, 230, 290, 350, 410, 480] for s in [1, -1]]
        if not vertical:
            offsets = [-x for x in offsets]
        for delta in offsets:
            ap = [a[0] + delta, a[1]] if vertical else [a[0], a[1] + delta]
            bp = [b[0] + delta, b[1]] if vertical else [b[0], b[1] + delta]
            line_set = [(a, ap), (ap, bp), (bp, b)]
            for shift in [0, 24, -24, 48, -48, 78, -78, 112, -112, 150, -150, 200, -200, 250, -250]:
                x = int(mid[0] + delta + 6) if vertical else int(mid[0] - pw / 2 + shift)
                y = int(mid[1] - ph / 2 + shift) if vertical else int(mid[1] + delta - ph - 6)
                box = [x - 4, y - 4, x + pw + 4, y + ph + 4]
                if x < 24 or y < 24 or x + pw >= W - 24 or (y + ph >= H - 24):
                    continue
                if any((intersects(box, z) for z in occupied)):
                    continue
                if static[box[1] : box[3], box[0] : box[2]].max():
                    continue
                chosen = (x, y, box, line_set)
                break
            if chosen:
                break
        if not chosen:
            raise ValueError(f"{plan['id']}/{style_name}: cannot place {i} {label}")
        x, y, box, line_set = chosen
        occupied.append(box)
        anchor = [line_set[1][0][0], y + ph / 2] if vertical else [x + pw / 2, line_set[1][0][1]]
        rail_mid = [
            (line_set[1][0][0] + line_set[1][1][0]) / 2,
            (line_set[1][0][1] + line_set[1][1][1]) / 2,
        ]
        if math.dist(anchor, rail_mid) > 1:
            line_set.append((rail_mid, anchor))
        for p, q in line_set:
            inkline(rail_mask, [p, q], 1)
        for p in [line_set[1][0], line_set[1][1]]:
            tick = (
                [[p[0] - 4, p[1]], [p[0] + 4, p[1]]]
                if vertical
                else [[p[0], p[1] - 4], [p[0], p[1] + 4]]
            )
            inkline(rail_mask, tick, 1)
        tarr = np.asarray(patch)
        text_mask[y : y + ph, x : x + pw] = np.maximum(text_mask[y : y + ph, x : x + pw], tarr)
        poly = (
            [[x, y + ph - 1], [x, y], [x + pw - 1, y], [x + pw - 1, y + ph - 1]]
            if vertical
            else quad([x, y, x + pw - 1, y + ph - 1])
        )
        label_records.append(
            dict(
                raw_text=text,
                value_cm=label["value_cm"],
                polygon_px=poly,
                box_px=[x, y, x + pw - 1, y + ph - 1],
                target=label["target"],
                span_px=[a, b],
                text_layout="single_line",
            )
        )
        patches.append((x, y, patch))
        rails.append(line_set)
    for x0, y0, x1, y1 in occupied:
        rail_mask[y0:y1, x0:x1] = 0
    bg = np.full((H, W, 3), 250 if style_name == "pencil" else 255, np.uint8)
    if style["grid"]:
        for x in range(0, W, 32):
            cv2.line(bg, (x, 0), (x, H - 1), (225, 231, 234), 1)
        for y in range(0, H, 32):
            cv2.line(bg, (0, y), (W - 1, y), (225, 231, 234), 1)
    for mask, color in [
        (rail_mask, 157),
        (wall_mask, style["ink"]),
        (tick_mask, style["ink"]),
        (text_mask, style["ink"]),
    ]:
        alpha = mask.astype(np.float32)[:, :, None] / 255
        bg = (bg * (1 - alpha) + color * alpha).astype(np.uint8)
    Hmat = np.eye(3)
    if style["camera"]:
        src = np.float32([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]])
        dest = src + np_rng.uniform(-14, 14, (4, 2)).astype(np.float32)
        Hmat = cv2.getPerspectiveTransform(src, dest)
        bg = cv2.warpPerspective(bg, Hmat, (W, H), borderValue=(248, 247, 244))
        yy, xx = np.mgrid[0:H, 0:W]
        light = 0.9 + 0.08 * xx / W - 0.035 * yy / H
        noise = np_rng.normal(0, 1.2, (H, W, 1))
        bg = np.clip(bg * light[:, :, None] + noise, 0, 255).astype(np.uint8)
        bg = cv2.GaussianBlur(bg, (3, 3), 0.38)
        ok, encoded = cv2.imencode(
            ".jpg", cv2.cvtColor(bg, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88]
        )
        assert ok
        bg = cv2.cvtColor(cv2.imdecode(encoded, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    image_path = out / "images" / f"{plan['id']}_{style_name}.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(bg).save(image_path)
    mask_paths = {}
    for name, mask in [("walls", wall_mask), ("door_ticks", tick_mask), ("text", text_mask)]:
        if style["camera"]:
            mask = cv2.warpPerspective(mask, Hmat, (W, H), flags=cv2.INTER_LINEAR)
        path = out / "masks" / f"{plan['id']}_{style_name}_{name}.png"
        path.parent.mkdir(exist_ok=True)
        Image.fromarray(mask).save(path)
        mask_paths[name] = "masks/" + path.name
    for text in label_records:
        text["polygon_px"] = project(text["polygon_px"], Hmat)
        text["span_px"] = project(text["span_px"], Hmat)
    for stroke in strokes:
        stroke["points_px"] = project(stroke["points_px"], Hmat)
    regions = deepcopy(plan["regions"])
    for r in regions:
        r["polygon_px"] = project([pix(p) for p in quad(r["bounds_cm"])], Hmat)
    for o in plan["openings"]:
        o["gap_px"] = project(o["gap_px"], Hmat)
    degree = defaultdict(int)
    for a, b in noded_edges(plan):
        degree[a] += 1
        degree[b] += 1
    junctions = [
        [project([pix(p)], Hmat)[0], "cross" if d >= 4 else "tee" if d == 3 else "corner"]
        for p, d in degree.items()
    ]
    spec = dict(
        id=f"{plan['id']}_{style_name}",
        image_path=str(image_path.resolve()),
        image_sha256=digest(image_path),
        size_px=[W, H],
        regions=regions,
        texts=label_records,
        strokes=strokes,
        junctions=junctions,
        openings=plan["openings"],
        notes=[
            "Synthetic metric-first renderer ground truth. Not human ink, OCR prediction or a real writer."
        ],
        expected_status="reference_validated",
        pixel_issues=["SYNTHETIC_RENDER", "DEVELOPMENT_ONLY", "FONT_STYLES_ARE_NOT_REAL_WRITERS"],
    )
    obs, side, draft = build_case(spec)
    for doc in [obs, draft]:
        doc["source"]["image_path"] = "../images/" + image_path.name
        doc["revision_id"] = "synthetic-render-1"
        doc["notes"] = [
            "Programmatic synthetic reference. Metric layout is generated first, then rendered. No human review, OCR inference, training, engine or gameplay acceptance."
        ]
    for text in obs["texts"]:
        text["method"] = "synthetic_render"
    draft["algorithm_version"] = "synthetic-metric-renderer/1.0"
    for values in draft["layout"].values():
        for obj in values:
            obj["provenance"]["method"] = "derived"
            obj["provenance"][
                "note"
            ] = "Generated from explicit synthetic plan and renderer geometry; never a manual observation."
            if "state" in obj:
                obj["state"] = "derived"
    side["method"] = "synthetic_render"
    side["reference_draft_path"] = "../metric/" + spec["id"] + ".draft.json"
    side["precision"] = (
        "Renderer paths and enclosing glyph rectangles transformed by the recorded camera homography. Region polygons describe logical boundaries, not ink masks."
    )
    for r in side["regions"]:
        r["status"] = "generated_intended_boundary"
    for a in side["associations"]:
        a["endpoint_basis"] = "synthetic_render_measured_endpoints"
        a["provenance"] = "generated_span_to_label_association"
    for gap in side["gaps"]:
        gap["semantic_provenance"] = (
            "Explicit generator connection; pixel gap rendered from this same geometry."
        )
    report = validate_document(draft, obs)
    assert report["schema_valid"] and report["metric_valid"], report
    assert validate_document(obs)["issues"] == []
    Draft202012Validator(SCHEMAS["urn:playablesketch:pixel-annotations:1"]).validate(side)
    rank = metric_rank(draft)
    prefix = spec["id"]
    write_json(out / "annotations" / f"{prefix}.observations.json", obs)
    write_json(out / "annotations" / f"{prefix}.annotations.json", side)
    write_json(out / "metric" / f"{prefix}.draft.json", draft)
    metadata = dict(
        schema_version="playablesketch-synthetic-render/1.0",
        sample_id=prefix,
        synthetic=True,
        base_plan_id=plan["id"],
        geometry_family=plan["family"],
        seed=seed,
        style=style_name,
        font=dict(
            name=style["font"],
            local_path=str(font_path),
            sha256=digest(font_path),
            font_file_distributed=False,
        ),
        logical_to_canvas=dict(
            scale_px_per_cm=scale,
            xmin_cm=float(xmin),
            ymin_cm=float(ymin),
            margin_px=margin,
            canvas_size=[W, H],
        ),
        canvas_to_image=Hmat.tolist(),
        text_collision_count=0,
        labels_omitted=0,
        mask_semantics="Grayscale renderer coverage layers with geometric warp; photometric shadows/compression are not applied to semantic masks.",
        masks=mask_paths,
        rank_check=rank,
        validation=report,
    )
    write_json(out / "rendering" / f"{prefix}.json", metadata)
    return dict(
        id=prefix,
        image_path="images/" + image_path.name,
        image_sha256=digest(image_path),
        base_plan_id=plan["id"],
        writer_id=None,
        synthetic_style_id=style_name,
        split="development",
        origin="synthetic",
        metric_status="generated_valid",
        observations_path=f"annotations/{prefix}.observations.json",
        annotations_path=f"annotations/{prefix}.annotations.json",
        metric_path=f"metric/{prefix}.draft.json",
        rendering_path=f"rendering/{prefix}.json",
        counts=dict(texts=len(label_records), regions=len(regions), openings=len(plan["openings"])),
    )


def audit(out):
    manifest = json.loads((out / "manifest.json").read_text())
    seen = set()
    styles = defaultdict(list)
    for s in manifest["samples"]:
        assert s["id"] not in seen
        seen.add(s["id"])
        assert (
            s["origin"] == "synthetic" and s["split"] == "development" and (s["writer_id"] is None)
        )
        assert digest(out / s["image_path"]) == s["image_sha256"]
        obs = json.loads((out / s["observations_path"]).read_text())
        side = json.loads((out / s["annotations_path"]).read_text())
        draft = json.loads((out / s["metric_path"]).read_text())
        meta = json.loads((out / s["rendering_path"]).read_text())
        assert validate_document(obs)["issues"] == []
        report = validate_document(draft, obs)
        assert report["metric_valid"] and (not report["exportable"])
        Draft202012Validator(SCHEMAS["urn:playablesketch:pixel-annotations:1"]).validate(side)
        assert all((t["method"] == "synthetic_render" for t in obs["texts"]))
        assert side["method"] == "synthetic_render" and len(side["associations"]) == len(
            obs["texts"]
        )
        assert all((o["state"] == "derived" for o in draft["layout"]["openings"]))
        with Image.open(out / s["image_path"]) as im:
            W, H = im.size
        for p in [p for t in obs["texts"] for p in t["polygon_px"]] + [
            p for r in side["regions"] for p in r["polygon_px"]
        ]:
            assert 0 <= p[0] < W and 0 <= p[1] < H
        for path in meta["masks"].values():
            with Image.open(out / path) as im:
                assert im.size == (W, H)
        assert np.isfinite(meta["canvas_to_image"]).all()
        metric_rank(draft)
        styles[s["base_plan_id"]].append(
            [(v["id"], v["position_cm"]) for v in draft["layout"]["vertices"]]
        )
    for variants in styles.values():
        assert all((v == variants[0] for v in variants))
    return dict(
        images=len(seen),
        base_plans=len(styles),
        text_regions=sum((s["counts"]["texts"] for s in manifest["samples"])),
        all_metric_drafts_valid=True,
        independent_constraint_rank="full after origin gauge",
        training_performed=False,
    )


def gallery(out, samples, title):
    rows = []
    for s in samples:
        src = html.escape(s["image_path"])
        name = html.escape(s["id"])
        rows.append(
            f"""<figure><a href="{src}"><img loading="lazy" src="{src}" alt="{name}"></a><figcaption>{name} · {s['counts']['regions']} regions · {s['counts']['texts']} labels</figcaption></figure>"""
        )
    page = (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>'
        + title
        + "</title><style>body{font:16px system-ui;background:#eee;color:#222;margin:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:18px}figure{margin:0}img{width:100%;background:white}a{color:inherit}figcaption{padding:6px}h1{font-size:24px}</style><h1>"
        + title
        + "</h1><p>Synthetic renderer output · cm · click any image for full size. A font/render style is not a real writer. All variants of a plan remain in one development group. Training has not run.</p><main>"
        + "".join(rows)
        + "</main></html>"
    )
    (out / "index.html").write_text(page)
    tiles = []
    for s in samples:
        im = Image.open(out / s["image_path"]).convert("RGB")
        im.thumbnail((390, 330))
        tile = Image.new("RGB", (410, 365), "white")
        tile.paste(im, ((410 - im.width) // 2, 24 + (330 - im.height) // 2))
        ImageDraw.Draw(tile).text((10, 5), s["id"], fill="black")
        tiles.append(tile)
    cols = 3 if len(samples) == 60 else 2
    sheet = Image.new("RGB", (cols * 410, math.ceil(len(tiles) / cols) * 365), "#dddddd")
    for i, t in enumerate(tiles):
        sheet.paste(t, (i % cols * 410, i // cols * 365))
    sheet.save(out / "contact-sheet.jpg", quality=90)


def main():
    parser = argparse.ArgumentParser(
        description="Generate 20 plans × 3 sketch styles, then 10 additional topology-varied plans."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    batches = [("handdrawn_pilot", 20, False, list(STYLES)), ("extra_plans", 10, True, ["ink"])]
    if args.check:
        for name, _, _, _ in batches:
            print(name, audit(args.output / name))
        return
    if any(((args.output / name).exists() for name, _, _, _ in batches)):
        raise SystemExit(
            "Output already exists; use --check or choose a fresh --output. Existing data is preserved."
        )
    fingerprints = []
    for name, count, extra, styles in batches:
        out = args.output / name
        out.mkdir(parents=True)
        samples = []
        plans = []
        for i in range(1, count + 1):
            plan = make_plan(i, extra)
            fingerprint = hashlib.sha256(
                json.dumps([(r["id"], r["bounds_cm"]) for r in plan["regions"]]).encode()
            ).hexdigest()
            assert fingerprint not in fingerprints
            fingerprints.append(fingerprint)
            plans.append(deepcopy(plan))
            for style in styles:
                sample = render(deepcopy(plan), style, out)
                samples.append(sample)
                print(f"{sample['id']}: rendered, annotated, metric/rank checked", flush=True)
        write_json(
            out / "plans.json",
            dict(schema_version="playablesketch-synthetic-plans/1.0", plans=plans),
        )
        write_json(
            out / "manifest.json",
            dict(
                schema_version="playablesketch-synthetic-dataset/1.0",
                origin="synthetic",
                split_policy="development_only; all appearance variants remain grouped by base_plan_id; not a new writer or holdout",
                generator_version="synthetic-metric-renderer/1.0",
                samples=samples,
            ),
        )
        gallery(
            out,
            samples,
            "Hand-drawn synthetic pilot" if not extra else "Additional synthetic plans",
        )
        write_json(out / "verification.json", audit(out))
    print(
        "Complete: 60 pilot images + 10 additional plans. Human manifests untouched. No training.",
        flush=True,
    )


if __name__ == "__main__":
    main()
