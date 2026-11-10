import argparse
import json
from pathlib import Path
import subprocess
import time
from urllib.request import Request, urlopen
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def generate(output):
    image = Image.new("RGB", (1200, 760), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 120, 1100, 620), outline="black", width=4)
    draw.line((600, 120, 600, 300), fill="black", width=4)
    draw.line((600, 440, 600, 620), fill="black", width=4)
    for y in [300, 440]:
        draw.line((586, y, 614, y), fill="black", width=4)
    path = output / "number-free-control.png"
    image.save(path)
    return path


def accept_control(service, alias, output):

    def get(path):
        with urlopen(service + path, timeout=15) as r:
            return json.load(r)

    token = get("/api/bootstrap")["token"]

    def post(path, data):
        request = Request(
            service + path,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json", "X-Shape-Token": token},
        )
        with urlopen(request, timeout=30) as r:
            return json.load(r)

    status = get("/jobs/" + alias)
    job = status["shape_job_id"]
    proposal = get("/shape-jobs/" + job + "/proposals")
    assert (
        proposal["numeric_ocr_called"] is False
        and proposal["model"]["architecture"] == "shape-dinov2/1.0"
    )
    matrix = np.asarray(proposal["preprocessing"]["original_to_working"])

    def point(p):
        q = matrix @ np.r_[p, 1.0]
        return (q[:2] / q[2]).tolist()

    boxes = []
    for rid, bounds in [("qa_start", [100, 120, 600, 620]), ("qa_goal", [600, 120, 1100, 620])]:
        boxes.append(
            {"id": rid, "type": "room", "bounds_px": point(bounds[:2]) + point(bounds[2:])}
        )
    edited = post(
        "/shape-jobs/" + job + "/edit",
        {
            "base_revision_id": proposal["authoring_revision_id"],
            "boxes": boxes,
            "openings": [
                {
                    "id": "qa_door",
                    "type": "door",
                    "entity_ids": ["qa_start", "qa_goal"],
                    "points_px": [point([600, 300]), point([600, 440])],
                }
            ],
        },
    )
    sized = post(
        "/shape-jobs/" + job + "/sizing",
        {
            "base_revision_id": edited["authoring"]["revision_id"],
            "base_sizing_revision_id": None,
            "request": {
                "edits": [
                    {
                        "entity_id": "qa_door",
                        "parameter": "clear_width_cm",
                        "value": 160,
                        "locked": True,
                    }
                ]
            },
        },
    )
    assert sized["status"] == "ready", sized["issues"]
    workspace = post(
        "/shape-jobs/" + job + "/workspace",
        {
            "base_revision_id": edited["authoring"]["revision_id"],
            "base_workspace_revision_id": None,
            "state": {
                "names": {"qa_start": "Control Start", "qa_goal": "Control Goal"},
                "start_room_id": "qa_start",
                "goal_room_id": "qa_goal",
                "validation_mode": "gameplay",
            },
        },
    )
    accepted = post(
        "/shape-jobs/" + job + "/confirm",
        {
            "base_revision_id": edited["authoring"]["revision_id"],
            "base_sizing_revision_id": sized["authoring"]["revision_id"],
            "base_workspace_revision_id": workspace["revision_id"],
        },
    )
    exported = post(
        "/shape-jobs/" + job + "/export", {"confirmation_id": accepted["confirmation_id"]}
    )
    with urlopen(service + exported["download_url"]) as r:
        (output / "downloaded-unreal-bundle.zip").write_bytes(r.read())
    with urlopen(service + exported["layout_url"]) as r:
        canonical = json.load(r)
    (output / "accepted-layout.json").write_text(json.dumps(canonical, indent=2))
    record = {
        "service_url": service,
        "runtime_job_id": alias,
        "shape_job_id": job,
        "export": exported,
        "note": "Generated number-free controlled image. Real inference completed before explicit test-only topology correction and a 160 cm design override. Not held-out perception accuracy or approval of a user drawing.",
    }
    (output / "service.json").write_text(json.dumps(record, indent=2))
    return record


def run(executable, output, service, prefix, load=False, offline=False):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = output / "runtime-report.json"
    image = generate(output)
    command = [
        str(executable),
        "-unattended",
        "-nullrhi",
        "-nosound",
        "-nosplash",
        "-RuntimeSmoke",
        "-RuntimeService=" + service,
        "-RuntimeSavePrefix=" + prefix,
        "-RuntimeReport=" + str(report),
        "-abslog=" + str(output / "runtime.log"),
        "-RuntimeExit",
    ]
    command += ["-RuntimeLoadSave"] if load else ["-RuntimeImage=" + str(image)]
    if offline:
        command += ["-RuntimeOffline"]
    (output / "command.json").write_text(json.dumps(command, indent=2))
    with (output / "stdout.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
    accepted = None
    deadline = time.monotonic() + 215
    try:
        while time.monotonic() < deadline:
            try:
                result = json.loads(report.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                result = None
            if result and result.get("stage") == "needs_review" and (not accepted):
                accepted = accept_control(service, result["job_id"], output)
                print(
                    "Controlled shape-first snapshot exported",
                    accepted["export"]["revision_id"],
                    flush=True,
                )
            if result and result.get("stage") == "failed" and (not offline):
                raise RuntimeError("Runtime rejected the plan: " + result.get("status", ""))
            if result and result.get("completed"):
                if not result.get("success"):
                    raise RuntimeError("Runtime acceptance failed: " + str(report))
                if process.wait(timeout=20) != 0:
                    raise RuntimeError("Runtime exited with error")
                assert result["with_editor"] is False
                if accepted:
                    assert json.loads(result["canonical_json"]) == json.loads(
                        (output / "accepted-layout.json").read_text()
                    )
                print(
                    json.dumps(
                        {
                            k: v
                            for k, v in result.items()
                            if k not in ("canonical_json", "navigation_report")
                        },
                        indent=2,
                    ),
                    flush=True,
                )
                return result
            if process.poll() is not None:
                raise RuntimeError(
                    "Runtime exited before completion; inspect " + str(output / "runtime.log")
                )
            time.sleep(0.2)
        raise TimeoutError("Cooked runtime test timed out")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=20)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--executable", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--service", default="http://127.0.0.1:8774")
    p.add_argument("--prefix", required=True)
    p.add_argument("--load", action="store_true")
    p.add_argument("--offline", action="store_true")
    a = p.parse_args()
    run(a.executable, a.output, a.service, a.prefix, a.load, a.offline)
