import argparse
import io
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen
from PIL import Image
from SketchPipeline.tests.test_topology import perimeter
from SketchPipeline.tests.test_topology_review import state_with
from SketchPipeline.tests.test_metric_solver import dimension


def prepare(url, output):
    if not url.startswith("http://127.0.0.1:"):
        raise ValueError("Controlled fixture must use loopback")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    def get(path):
        with urlopen(url + path, timeout=20) as response:
            return json.load(response)

    token = get("/api/bootstrap")["token"]

    def post(path, body, method="POST"):
        request = Request(
            url + path,
            data=json.dumps(body).encode(),
            method=method,
            headers={"Content-Type": "application/json", "X-Review-Token": token},
        )
        with urlopen(request, timeout=20) as response:
            return json.load(response)

    stream = io.BytesIO()
    Image.new("RGB", (220, 120), "white").save(stream, format="PNG")
    (output / "controlled-source.png").write_bytes(stream.getvalue())
    boundary = "PipelineFixture"
    config = json.dumps({"mode": "manual", "settings": {"wall_height_cm": 300}})
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="config"\r\n\r\n{config}\r\n--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="controlled.png"\r\nContent-Type: image/png\r\n\r\n'.encode()
        + stream.getvalue()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = Request(
        url + "/jobs",
        data=body,
        headers={
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "X-Review-Token": token,
        },
    )
    with urlopen(request, timeout=20) as response:
        job = json.load(response)
    identifier = job["job_id"]
    deadline = time.monotonic() + 20
    while job["state"] in ("uploaded", "processing"):
        if time.monotonic() > deadline:
            raise RuntimeError("Controlled job timed out")
        time.sleep(0.1)
        job = get("/jobs/" + identifier)
    if job["state"] != "needs_review":
        raise RuntimeError(str(job))
    post(
        "/api/save",
        {
            "case_id": identifier,
            "state": state_with(perimeter(10, 10, 110, 110)),
            "parent_revision_id": None,
            "action": "accept",
        },
    )
    loaded = get("/jobs/" + identifier + "/draft")
    state = loaded["state"]
    rid = next(iter(state["bindings"]["region_kinds"]))
    state["bindings"]["dimensions"] = [
        dimension("width", {"type": "region_span", "region_id": rid, "axis": "x"}, 600),
        dimension("depth", {"type": "region_span", "region_id": rid, "axis": "y"}, 400),
    ]
    state["semantics_confirmed"] = True
    saved = post(
        "/jobs/" + identifier + "/draft",
        {"base_revision_id": loaded["base_revision_id"], "state": state},
        "PATCH",
    )
    validation = post(
        "/jobs/" + identifier + "/validate", {"base_revision_id": saved["base_revision_id"]}
    )
    if not validation["validation"]["metric_valid"]:
        raise RuntimeError("Fixture metric validation failed")
    accepted = post(
        "/jobs/" + identifier + "/accept",
        {"base_revision_id": saved["base_revision_id"], "reviewer": "Controlled pipeline test"},
    )
    revision = accepted["base_revision_id"]
    layout = get("/jobs/" + identifier + "/layout?revision_id=" + revision)
    (output / "layout.json").write_text(json.dumps(layout, indent=2) + "\n")
    config = {
        "service_url": url,
        "job_id": identifier,
        "accepted_revision_id": revision,
        "note": "Programmatically approved synthetic control fixture; not a user drawing or training ground truth.",
    }
    (output / "service.json").write_text(json.dumps(config, indent=2) + "\n")
    (output / "job-status.json").write_text(json.dumps(get("/jobs/" + identifier), indent=2) + "\n")
    return config


def main():
    parser = argparse.ArgumentParser(
        description="Prepare a controlled, synthetic local-service fixture for Unreal automation."
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.url, args.output)))


if __name__ == "__main__":
    main()
