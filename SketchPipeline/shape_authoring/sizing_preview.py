from html import escape


def render(result):
    preview = result.get("preview")
    if not preview:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="180"><text x="24" y="80" font-family="sans-serif">Review the plan before generating sizes.</text></svg>'
    doc = preview["canonical"]
    layout = doc["layout"]
    points = {v["id"]: v["position_cm"] for v in layout["vertices"]}
    xs = [p[0] for p in points.values()]
    ys = [p[1] for p in points.values()]
    x0, x1 = (min(xs), max(xs))
    y0, y1 = (min(ys), max(ys))
    scale = min(680 / max(1, x1 - x0), 460 / max(1, y1 - y0))

    def p(point):
        return (30 + (point[0] - x0) * scale, 70 + (y1 - point[1]) * scale)

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="600" viewBox="0 0 760 600"><rect width="760" height="600" fill="#fafaf7"/>',
        '<text x="24" y="28" font-family="sans-serif" font-size="18">Suggested plan sizes</text><text x="24" y="49" font-family="sans-serif" font-size="12">Starting points for your level. Adjust to suit your design.</text>',
    ]
    for kind, color in [("rooms", "#f2eadb"), ("corridors", "#dbeaf1")]:
        for region in layout[kind]:
            polygon = [points[i] for i in region["boundary_vertex_ids"]]
            coords = " ".join((f"{a:.3f},{b:.3f}" for a, b in map(p, polygon)))
            parts.append(f'<polygon points="{coords}" fill="{color}"/>')
    for wall in layout["walls"]:
        a, b = [p(points[wall[k]]) for k in ["start_vertex_id", "end_vertex_id"]]
        parts.append(
            f'<path d="M{a[0]:.3f},{a[1]:.3f} L{b[0]:.3f},{b[1]:.3f}" fill="none" stroke="#354746" stroke-width="2"/>'
        )
    walls = {w["id"]: w for w in layout["walls"]}
    for opening in layout["openings"]:
        wall = walls[opening["wall_id"]]
        start = list(points[wall["start_vertex_id"]])
        end = list(start)
        axis = "xy".index(wall["axis"])
        start[axis] += opening["center_offset_cm"] - opening["clear_width_cm"] / 2
        end[axis] += opening["center_offset_cm"] + opening["clear_width_cm"] / 2
        a, b = (p(start), p(end))
        parts.append(
            f'<path d="M{a[0]:.3f},{a[1]:.3f} L{b[0]:.3f},{b[1]:.3f}" stroke="#fafaf7" stroke-width="5"/><path d="M{a[0]:.3f},{a[1]:.3f} L{b[0]:.3f},{b[1]:.3f}" stroke="#328577" stroke-width="1.5"/>'
        )
    for region in layout["rooms"] + layout["corridors"]:
        polygon = [points[i] for i in region["boundary_vertex_ids"]]
        xs = [q[0] for q in polygon]
        ys = [q[1] for q in polygon]
        a, b = p([(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2])
        parts.append(
            f"""<text x="{a:.3f}" y="{b:.3f}" text-anchor="middle" font-family="sans-serif" font-size="10">{escape(region['name'])}<tspan x="{a:.3f}" dy="14">{(max(xs) - min(xs)) / 100:.2f} × {(max(ys) - min(ys)) / 100:.2f} m</tspan></text>"""
        )
    if result.get("preview_is_stale"):
        parts.append(
            '<text x="24" y="570" fill="#a33" font-family="sans-serif">Previous valid plan — current choices need attention.</text>'
        )
    parts.append("</svg>")
    return "".join(parts)
