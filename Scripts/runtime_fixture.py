import argparse
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from SketchPipeline.tests.test_topology import perimeter, wall
from SketchPipeline.tests.test_topology_review import state_with
from SketchPipeline.tests.test_metric_solver import dimension

ROOT = Path(__file__).resolve().parents[1]


def generate(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1400, 900), "white")
    d = ImageDraw.Draw(image)
    lines = perimeter(100, 200, 1200, 700) + [
        wall("shared_top", (650, 200), (650, 400), "vertical"),
        wall("shared_bottom", (650, 550), (650, 700), "vertical"),
    ]
    for l in lines:
        d.line([tuple(l["start"]), tuple(l["end"])], fill="black", width=5)
    d.line([(625, 400), (675, 400)], fill="black", width=5)
    d.line([(625, 550), (675, 550)], fill="black", width=5)
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 38)
    for xy, text in [
        ((290, 120), "600 cm"),
        ((880, 120), "500 cm"),
        ((10, 425), "400"),
        ((1230, 425), "400"),
        ((670, 455), "120 cm"),
        ((675, 610), "200 cm"),
    ]:
        d.text(xy, text, font=font, fill="black")
    path = output / "controlled-runtime-plan.png"
    image.save(path)
    return path


def accept_job(url, job, output):

    def get(path):
        with urlopen(url + path, timeout=20) as r:
            return json.load(r)

    token = get("/api/bootstrap")["token"]

    def post(path, data, method="POST"):
        q = Request(
            url + path,
            data=json.dumps(data).encode(),
            method=method,
            headers={"Content-Type": "application/json", "X-Review-Token": token},
        )
        with urlopen(q, timeout=20) as r:
            return json.load(r)

    status = get("/jobs/" + job)
    if status["state"] != "needs_review":
        raise ValueError("Wait for actual inference before controlled review: " + status["state"])
    case = get("/api/case?case=" + job)
    frame = case["frame"]
    matrix = np.asarray(frame["original_to_review"])

    def point(p):
        q = matrix @ np.asarray([p[0], p[1], 1.0])
        return (q[:2] / q[2]).tolist()

    lines = perimeter(100, 200, 1200, 700) + [
        wall("shared_top", (650, 200), (650, 400), "vertical"),
        wall("shared_bottom", (650, 550), (650, 700), "vertical"),
    ]
    for l in lines:
        l["start"], l["end"] = (point(l["start"]), point(l["end"]))
    opening = dict(
        id="door",
        start=point([650, 400]),
        end=point([650, 550]),
        axis="vertical",
        kind="door",
        decision="approved",
    )
    post(
        "/api/save",
        dict(
            case_id=job,
            state=state_with(lines, [opening]),
            parent_revision_id=case.get("revision_id"),
            action="accept",
        ),
    )
    loaded = get("/jobs/" + job + "/draft")
    state = loaded["state"]
    pixels = loaded["report"]["pixel_topology"]["regions"]
    ids = sorted(pixels, key=lambda r: sum((p[0] for p in pixels[r])) / len(pixels[r]))
    left, right = ids
    targets = [
        ({"type": "region_span", "region_id": left, "axis": "x"}, 600, "wall_centerline"),
        ({"type": "region_span", "region_id": left, "axis": "y"}, 400, "wall_centerline"),
        ({"type": "region_span", "region_id": right, "axis": "x"}, 500, "wall_centerline"),
        ({"type": "region_span", "region_id": right, "axis": "y"}, 400, "wall_centerline"),
        ({"type": "opening_width", "opening_id": "door"}, 120, "clear_opening"),
        (
            {
                "type": "opening_offset",
                "opening_id": "door",
                "region_id": left,
                "side": "east",
                "reference": "min_corner",
            },
            200,
            "edge_offset",
        ),
    ]
    state["bindings"]["dimensions"] = [
        dimension("control-d" + str(i), t, v, b) for i, (t, v, b) in enumerate(targets)
    ]
    state["bindings"]["ignored_texts"] = [
        dict(
            evidence_id=t["id"],
            reason="Controlled test: measurements explicitly entered from generated design; raw OCR retained.",
        )
        for t in loaded["observations"]["texts"]
    ]
    state.update(
        semantics_confirmed=True,
        validation_mode="gameplay",
        start_room_id=left,
        goal_room_id=right,
        names={left: "Control Start", right: "Control Goal"},
    )
    saved = post(
        "/jobs/" + job + "/draft",
        dict(base_revision_id=loaded["base_revision_id"], state=state),
        "PATCH",
    )
    accepted = post(
        "/jobs/" + job + "/accept",
        dict(
            base_revision_id=saved["base_revision_id"],
            reviewer="Step14 controlled synthetic automation",
        ),
    )
    result = dict(
        service_url=url,
        job_id=job,
        accepted_revision_id=accepted["base_revision_id"],
        note="Actual image-only inference ran first; then explicit manual topology/metric corrections on a generated control image. Not a user drawing or an automation accuracy claim.",
    )
    output = Path(output)
    (output / "service.json").write_text(json.dumps(result, indent=2) + "\n")
    layout = get("/jobs/" + job + "/layout?revision_id=" + accepted["base_revision_id"])
    (output / "accepted-layout.json").write_text(json.dumps(layout, indent=2) + "\n")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--url")
    p.add_argument("--job")
    a = p.parse_args()
    if a.job:
        print(json.dumps(accept_job(a.url, a.job, a.output)))
    else:
        print(generate(a.output))
