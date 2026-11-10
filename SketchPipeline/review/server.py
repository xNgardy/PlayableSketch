import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
from urllib.parse import parse_qs, unquote, urlparse
import uuid
import cv2
import numpy as np
from shapely import LineString
from SketchPipeline.perception.topology import build_topology, _rotate

ROOT = Path(__file__).resolve().parents[2]
WEB = Path(__file__).parent / "web"
VERSION = "playablesketch-topology-review/1.0"
IDENTIFIER = re.compile("^[A-Za-z][A-Za-z0-9_.-]{0,100}$")


class ReviewError(ValueError):

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".review-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _point(value, width, height):
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any((type(number) not in (int, float) or not math.isfinite(number) for number in value))
    ):
        raise ReviewError("Coordinates must be two finite numbers.")
    margin = max(width, height) * 0.1
    if not -margin <= value[0] <= width + margin or not -margin <= value[1] <= height + margin:
        raise ReviewError("Coordinates exceed the review image bounds.")
    return [round(float(number), 2) for number in value]


def clean_state(state, width, height):
    if not isinstance(state, dict) or set(state) != {"walls", "openings"}:
        raise ReviewError("State must contain walls and openings only.")
    if any((not isinstance(state[key], list) or len(state[key]) > 2000 for key in state)):
        raise ReviewError("Each collection must be a list of at most 2000 elements.")
    result = {"walls": [], "openings": []}
    ids = set()
    for collection in result:
        for element in state[collection]:
            if not isinstance(element, dict):
                raise ReviewError("Every element must be an object.")
            identifier = element.get("id")
            if (
                not isinstance(identifier, str)
                or not IDENTIFIER.fullmatch(identifier)
                or identifier in ids
            ):
                raise ReviewError("Element IDs must be unique and valid.")
            ids.add(identifier)
            start, end = [_point(element.get(key), width, height) for key in ("start", "end")]
            if start == end:
                raise ReviewError(f"{identifier}: zero-length element.")
            dx, dy = (abs(end[0] - start[0]), abs(end[1] - start[1]))
            if dx != 0 and dy != 0:
                raise ReviewError(f"{identifier}: only horizontal/vertical geometry is supported.")
            axis = "horizontal" if dy == 0 else "vertical"
            if element.get("axis", axis) != axis:
                raise ReviewError(f"{identifier}: axis does not match its endpoints.")
            evidence = element.get("evidence_ids", [])
            if not isinstance(evidence, list) or any(
                (not isinstance(item, str) or len(item) > 120 for item in evidence)
            ):
                raise ReviewError("Invalid evidence IDs.")
            cleaned = {
                "id": identifier,
                "start": start,
                "end": end,
                "axis": axis,
                "evidence_ids": sorted(set(evidence)),
            }
            if collection == "openings":
                if max(dx, dy) <= 1:
                    raise ReviewError(f"{identifier}: opening must span more than 1 px.")
                decision, kind = (element.get("decision"), element.get("kind"))
                if decision not in ("pending", "approved", "rejected") or kind not in (
                    "door",
                    "open_passage",
                    "unknown",
                ):
                    raise ReviewError("Invalid opening decision or type.")
                cleaned.update(decision=decision, kind=kind)
            result[collection].append(cleaned)
    return result


def analyze_state(state, width, height):
    state = clean_state(state, width, height)
    lines = [{**wall, "role": "wall_candidate"} for wall in state["walls"]]
    shapes = [LineString([line["start"], line["end"]]) for line in lines]
    gaps, issues = ([], [])

    def issue(code, message, elements=(), severity="error"):
        issues.append(
            {"code": code, "message": message, "element_ids": list(elements), "severity": severity}
        )

    for opening in state["openings"]:
        if opening["decision"] == "rejected":
            continue
        if opening["decision"] == "pending":
            issue("OPENING_PENDING", "Approve or reject this opening.", [opening["id"]])
        if opening["decision"] == "approved" and opening["kind"] == "unknown":
            issue(
                "OPENING_TYPE_REQUIRED",
                "Choose an opening type: door or open_passage.",
                [opening["id"]],
            )
        support_ids = []
        along = 0 if opening["axis"] == "horizontal" else 1
        lo, hi = sorted((opening["start"][along], opening["end"][along]))
        for endpoint in (opening["start"], opening["end"]):
            candidates = []
            for wall in state["walls"]:
                if wall["axis"] != opening["axis"]:
                    continue
                if endpoint not in (wall["start"], wall["end"]):
                    continue
                wlo, whi = sorted((wall["start"][along], wall["end"][along]))
                if min(hi, whi) - max(lo, wlo) > 1e-05:
                    continue
                candidates.append(wall["id"])
            support_ids.append(sorted(candidates)[0] if candidates else None)
        gaps.append(
            {
                **opening,
                "role": "opening_candidate",
                "interpretation": opening["kind"],
                "supporting_line_ids": [identifier for identifier in support_ids if identifier],
            }
        )
    topology = build_topology(lines, gaps, (height, width), review_exact=True)
    if not topology["regions"]:
        issue("NO_REGION", "No closed rectangular region was found.")
    for region in topology["regions"]:
        if not region["rectangle_candidate"]:
            issue(
                "UNSUPPORTED_REGION",
                "V1 requires rectangular regions. Holes and L-shaped regions are unsupported.",
                [region["id"]],
            )
    for gap in gaps:
        if gap["topology_relation"]["status"] != "two_region_connection":
            issue(
                "OPENING_NOT_CONNECTED",
                "The opening does not connect two rectangular regions. Check its endpoints and wall gap.",
                [gap["id"]],
            )
    dangling = topology["polygonization"]["dangles_px_rotated"]
    significant = [line for line in dangling if LineString(line).length > 2.0]
    if significant:
        dangling_ids = sorted(
            {
                line["id"]
                for line, shape in zip(lines, shapes)
                if any((shape.intersection(LineString(part)).length > 0.01 for part in significant))
            }
        )
        issue(
            "DANGLING_WALLS",
            f"{len(significant)} dangling or isolated wall segments. Remove unnecessary ticks or join the endpoints.",
            dangling_ids,
        )
    elif dangling:
        issue(
            "SMALL_DANGLES",
            "Endpoint overshoots of 2 px or less remain. Check the overlay.",
            severity="warning",
        )
    if (
        topology["polygonization"]["cut_edge_count"]
        or topology["polygonization"]["invalid_ring_count"]
    ):
        issue("INVALID_LINEWORK", "Cut edges or invalid rings remain.")
    for index, shape in enumerate(shapes):
        for other in range(index + 1, len(shapes)):
            if shape.intersection(shapes[other]).length > 0.01:
                issue(
                    "OVERLAPPING_WALLS",
                    "Remove overlapping wall segments.",
                    [lines[index]["id"], lines[other]["id"]],
                )
    return {
        "state": state,
        "topology": topology,
        "validation": {
            "ready_to_review": not any((item["severity"] == "error" for item in issues)),
            "issues": issues,
            "metric_layout_created": False,
        },
        "state_sha256": digest(state),
    }


def state_diff(previous, current):
    changes = []
    for collection in ("walls", "openings"):
        before, after = [
            {element["id"]: element for element in state[collection]}
            for state in (previous, current)
        ]
        for identifier in sorted(before.keys() | after.keys()):
            if before.get(identifier) != after.get(identifier):
                changes.append(
                    {
                        "collection": collection,
                        "element_id": identifier,
                        "before": before.get(identifier),
                        "after": after.get(identifier),
                    }
                )
    return changes


class ReviewStore:

    def __init__(self, run, output):
        self.run, self.output = (Path(run).resolve(), Path(output).resolve())
        if self.output == self.run or self.run in self.output.parents:
            raise ReviewError("Review output must be separate from prediction artifacts.")
        self.output.mkdir(parents=True, exist_ok=True)
        self.cases, self.lock = ({}, threading.Lock())
        for folder in sorted(
            self.run.iterdir(),
            key=lambda path: (
                int(re.search("\\d+$", path.name).group()) if re.search("\\d+$", path.name) else 0
            ),
        ):
            if (
                folder.is_dir()
                and IDENTIFIER.fullmatch(folder.name)
                and (folder / "topology.json").exists()
            ):
                self.cases[folder.name] = self._load_case(folder)
        for folder in sorted((self.output / "uploads").glob("Upload_*")):
            prediction = folder / "prediction"
            if IDENTIFIER.fullmatch(folder.name) and (prediction / "topology.json").exists():
                metadata = json.loads((folder / "upload.json").read_text())
                if metadata.get("status") != "complete":
                    continue
                case = self._load_case(prediction, folder.name)
                case["label"] = metadata.get("filename", folder.name)
                self.cases[folder.name] = case
        from .uploads import UploadManager

        self.uploads = UploadManager(self)

    def _load_case(self, folder, identifier=None):
        working = json.loads((folder / "working.json").read_text())
        topology = json.loads((folder / "topology.json").read_text())
        observations = json.loads((folder / "observations.json").read_text())
        source_image = (folder / observations["source"]["image_path"]).resolve()
        if file_hash(source_image) != observations["source"]["image_sha256"]:
            raise ReviewError(f"{folder.name}: original photo hash mismatch.")
        width, height = working["preprocessing"]["working_size_px"]
        rotation = working["geometry"]["dominant_rotation_degrees"]
        center = np.asarray([width / 2, height / 2], float)
        matrix = cv2.getRotationMatrix2D(tuple(center), rotation, 1)
        affine = np.vstack((matrix, [0, 0, 1]))
        original_to_review = affine @ np.asarray(working["preprocessing"]["original_to_working"])
        photo = cv2.imread(str(folder / "unmasked_line_input.png"), cv2.IMREAD_GRAYSCALE)
        if photo is None or photo.shape != (height, width):
            raise ReviewError(f"{folder.name}: missing/wrong-frame review image.")
        background = cv2.warpAffine(photo, matrix, (width, height), borderValue=245)
        success, png = cv2.imencode(".png", background)
        if not success:
            raise ReviewError("Cannot encode review background.")
        walls = []
        for edge in topology["wall_graph"]["edges"]:
            if edge["kind"] != "physical_wall":
                continue
            walls.append(
                {
                    "id": f"w{len(walls) + 1:04d}",
                    "start": edge["a"],
                    "end": edge["b"],
                    "axis": "horizontal" if edge["a"][1] == edge["b"][1] else "vertical",
                    "evidence_ids": edge["physical_line_ids"],
                }
            )
        openings = []
        for gap in working["gaps"]:
            if gap["role"] != "opening_candidate":
                continue
            record = next(
                (
                    item
                    for item in topology.get("opening_boundaries", [])
                    if item["opening_id"] == gap["id"]
                ),
                {},
            )
            points = record.get("endpoints_px_rotated") or [
                _rotate(gap[key], center, rotation).tolist() for key in ("start", "end")
            ]
            points = [list(map(float, point)) for point in points]
            delta = np.asarray(points[1]) - points[0]
            axis = "horizontal" if abs(delta[0]) >= abs(delta[1]) else "vertical"
            normal = 1 if axis == "horizontal" else 0
            points[0][normal] = points[1][normal] = round(
                (points[0][normal] + points[1][normal]) / 2, 2
            )
            openings.append(
                {
                    "id": f"o{len(openings) + 1:04d}",
                    "start": points[0],
                    "end": points[1],
                    "axis": axis,
                    "decision": "pending",
                    "evidence_ids": [gap["id"]],
                    "kind": "door" if gap.get("interpretation") == "door_like" else "open_passage",
                }
            )
        state = clean_state({"walls": walls, "openings": openings}, width, height)
        sources = {
            str(path): file_hash(path)
            for path in (
                source_image,
                folder / "observations.json",
                folder / "working.json",
                folder / "topology.json",
                folder / "unmasked_line_input.png",
            )
        }
        return {
            "id": identifier or folder.name,
            "label": identifier or folder.name,
            "notice": (
                "Automatic detection could not finish. Draw or correct your plan here, then approve it."
                if working.get("prediction_status") == "manual_review_required"
                else "Review this drawing before continuing. Correct any missing or uncertain geometry."
            ),
            "seed": state,
            "png": png.tobytes(),
            "sources": sources,
            "source_image_sha256": observations["source"]["image_sha256"],
            "frame": {
                "coordinate_frame": "working_rotated_pixel",
                "width_px": width,
                "height_px": height,
                "original_to_review": original_to_review.tolist(),
                "review_to_original": np.linalg.inv(original_to_review).tolist(),
            },
        }

    def case(self, identifier):
        if identifier not in self.cases:
            raise ReviewError("Unknown case.", 404)
        return self.cases[identifier]

    def latest(self, identifier):
        self.case(identifier)
        pointer = self.output / identifier / "latest.json"
        if not pointer.exists():
            return None
        record = json.loads(pointer.read_text())
        revision_id = record["revision_id"]
        if not re.fullmatch("[0-9TZ-]+-[a-f0-9]{12}", revision_id):
            raise ReviewError("Invalid saved revision ID.")
        revision = json.loads((pointer.parent / "revisions" / (revision_id + ".json")).read_text())
        if revision.get("revision_id") != revision_id or revision.get("revision_sha256") != digest(
            {key: value for key, value in revision.items() if key != "revision_sha256"}
        ):
            raise ReviewError("Saved review revision integrity check failed.")
        if digest(revision["state"]) != revision["state_sha256"]:
            raise ReviewError("Saved review state hash mismatch.")
        return revision

    def load(self, identifier):
        case, latest = (self.case(identifier), self.latest(identifier))
        if latest and latest["source_fingerprints"] != case["sources"]:
            raise ReviewError(
                "Prediction sources changed. Use a separate review output directory.", 409
            )
        state = deepcopy(latest["state"] if latest else case["seed"])
        return {
            "case_id": identifier,
            "frame": case["frame"],
            "state": state,
            "notice": case["notice"],
            "revision_id": latest["revision_id"] if latest else None,
            "status": latest["status"] if latest else "unsaved",
            "analysis": analyze_state(state, case["frame"]["width_px"], case["frame"]["height_px"]),
        }

    def analyze(self, identifier, state):
        case = self.case(identifier)
        return analyze_state(state, case["frame"]["width_px"], case["frame"]["height_px"])

    def save(self, identifier, state, parent_revision_id, action):
        if action not in ("save_draft", "accept"):
            raise ReviewError("Unknown review action.")
        with self.lock:
            case = self.case(identifier)
            for path, expected in case["sources"].items():
                if file_hash(Path(path)) != expected:
                    raise ReviewError(
                        "Prediction/photo changed during review. Reload from a fresh run.", 409
                    )
            latest = self.latest(identifier)
            if latest and latest["source_fingerprints"] != case["sources"]:
                raise ReviewError("Review belongs to different prediction sources.", 409)
            if parent_revision_id != (latest["revision_id"] if latest else None):
                raise ReviewError("A newer revision exists. Reload before saving.", 409)
            result = self.analyze(identifier, state)
            if action == "accept" and (not result["validation"]["ready_to_review"]):
                raise ReviewError(
                    "Topology cannot be approved. Resolve the blocking issues or save a draft.", 422
                )
            revision_id = (
                datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
            )
            revision = {
                "schema_version": VERSION,
                "case_id": identifier,
                "revision_id": revision_id,
                "parent_revision_id": parent_revision_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "reviewed" if action == "accept" else "draft",
                "review_action": action,
                "units": "px",
                "metric_layout_created": False,
                "frame": case["frame"],
                "source_fingerprints": case["sources"],
                "source_image_sha256": case["source_image_sha256"],
                **result,
                "changes": state_diff(latest["state"] if latest else case["seed"], result["state"]),
                "note": "User-reviewed pixel topology only. Dimensions and Unreal export require later validation.",
            }
            revision["revision_sha256"] = digest(revision)
            folder = self.output / identifier
            atomic_json(folder / "revisions" / (revision_id + ".json"), revision)
            atomic_json(
                folder / "latest.json", {"revision_id": revision_id, "status": revision["status"]}
            )
            return revision


def make_handler(store):
    from .metric_store import MetricReviewStore

    metric_store = MetricReviewStore(store)
    from SketchPipeline.jobs import JobManager
    from SketchPipeline import job_api

    if not hasattr(store, "jobs"):
        store.jobs = JobManager(store, metric_store)
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):

        def respond(self, status, data, content_type="application/json; charset=utf-8", extra=None):
            if not isinstance(data, bytes):
                data = json.dumps(data, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            try:
                parsed = urlparse(self.path)
                identifier = parse_qs(parsed.query).get("case", [None])[0]
                if parsed.path.startswith("/jobs/"):
                    result = job_api.get(store.jobs, parsed.path, parsed.query)
                    extra = (
                        {
                            "Content-Disposition": f'''attachment; filename="{parsed.path.split('/')[2]}.validated-layout.json"'''
                        }
                        if parsed.path.endswith("/layout")
                        else None
                    )
                    self.respond(200, result, extra=extra)
                elif parsed.path == "/api/bootstrap":
                    with store.lock:
                        cases = list(store.cases)
                        labels = {
                            identifier: case["label"] for identifier, case in store.cases.items()
                        }
                    self.respond(
                        200,
                        {
                            "token": token,
                            "cases": cases,
                            "labels": labels,
                            "output": str(store.output),
                            "jobs": [
                                {
                                    "job_id": j["job_id"],
                                    "filename": j.get("filename", j["job_id"]),
                                    "state": j["state"],
                                }
                                for j in list(store.jobs.jobs.values())[-30:]
                            ],
                        },
                    )
                elif parsed.path == "/api/upload-status":
                    self.respond(
                        200, store.uploads.status(parse_qs(parsed.query).get("job", [None])[0])
                    )
                elif parsed.path == "/api/metric":
                    self.respond(200, metric_store.load(identifier))
                elif parsed.path == "/api/metric/export":
                    self.respond(
                        200,
                        metric_store.export(
                            identifier, parse_qs(parsed.query).get("revision_id", [None])[0]
                        ),
                        extra={
                            "Content-Disposition": f'attachment; filename="{identifier}.validated-layout.json"'
                        },
                    )
                elif parsed.path == "/api/case":
                    self.respond(200, store.load(identifier))
                elif parsed.path == "/api/image":
                    self.respond(200, store.case(identifier)["png"], "image/png")
                elif parsed.path == "/api/export":
                    revision = store.latest(identifier)
                    if revision is None or revision["status"] != "reviewed":
                        raise ReviewError("Only the latest reviewed revision can be exported.", 409)
                    case = store.case(identifier)
                    if revision["source_fingerprints"] != case["sources"] or any(
                        (
                            file_hash(Path(path)) != expected
                            for path, expected in case["sources"].items()
                        )
                    ):
                        raise ReviewError("Source changed after review.", 409)
                    self.respond(
                        200,
                        revision,
                        extra={
                            "Content-Disposition": f'attachment; filename="{identifier}.reviewed-topology.json"'
                        },
                    )
                elif parsed.path in (
                    "/",
                    "/editor.js",
                    "/style.css",
                    "/metric.html",
                    "/metric.js",
                    "/metric.css",
                ):
                    path = WEB / {"/": "index.html"}.get(parsed.path, parsed.path[1:])
                    mime = (
                        "text/html; charset=utf-8"
                        if path.suffix == ".html"
                        else (
                            "text/javascript; charset=utf-8"
                            if path.suffix == ".js"
                            else "text/css; charset=utf-8"
                        )
                    )
                    self.respond(200, path.read_bytes(), mime)
                else:
                    raise ReviewError("Not found.", 404)
            except ReviewError as error:
                self.respond(error.status, {"error": str(error)})
            except (OSError, ValueError, KeyError):
                self.respond(500, {"error": "Review artifact could not be loaded."})

        def do_POST(self):
            try:
                port = self.server.server_address[1]
                origin = self.headers.get("Origin")
                if self.headers.get("X-Review-Token") != token or (
                    origin
                    and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")
                ):
                    raise ReviewError("Invalid review session.", 403)
                length = int(self.headers.get("Content-Length", "0"))
                if self.path == "/jobs":
                    if not 0 < length <= 20100000:
                        raise ReviewError("Upload up to 20 MB", 413)
                    data, filename, config = job_api.multipart(
                        self.rfile.read(length), self.headers.get("Content-Type", "")
                    )
                    self.respond(202, store.jobs.start(data, filename, config))
                    return
                if self.path == "/api/upload":
                    if not 0 < length <= 20000000:
                        raise ReviewError("Upload a JPEG or PNG image up to 20 MB.", 413)
                    self.respond(
                        202,
                        store.uploads.start(
                            self.rfile.read(length),
                            unquote(self.headers.get("X-File-Name", "drawing.png")),
                        ),
                    )
                    return
                if not 0 < length <= 4000000:
                    raise ReviewError("Invalid payload size.", 413)
                body = json.loads(
                    self.rfile.read(length),
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON")),
                )
                if not isinstance(body, dict):
                    raise ReviewError("JSON object required.")
                if self.path.startswith("/jobs/"):
                    result = job_api.mutate(store.jobs, self.path, body)
                elif self.path in (
                    "/api/metric/save",
                    "/api/metric/preview",
                    "/api/metric/undo",
                    "/api/metric/redo",
                    "/api/metric/accept",
                ):
                    result = metric_store.transact(
                        body.get("case_id"),
                        body.get("base_revision_id"),
                        self.path.rsplit("/", 1)[1],
                        body.get("state"),
                        body.get("reviewer"),
                        telemetry=body.get("telemetry"),
                    )
                elif self.path == "/api/analyze":
                    result = store.analyze(body.get("case_id"), body.get("state"))
                elif self.path == "/api/save":
                    result = store.save(
                        body.get("case_id"),
                        body.get("state"),
                        body.get("parent_revision_id"),
                        body.get("action"),
                    )
                else:
                    raise ReviewError("Not found.", 404)
                self.respond(200, result)
            except ReviewError as error:
                self.respond(error.status, {"error": str(error)})
            except (ValueError, TypeError, KeyError):
                self.respond(400, {"error": "Invalid review request."})
            except OSError:
                self.respond(500, {"error": "Review revision could not be written."})

        def do_PATCH(self):
            self.do_POST()

    return Handler


def main():
    parser = argparse.ArgumentParser(
        description="Serve the local topology editor with upload inference and mandatory review."
    )
    parser.add_argument("--run", type=Path, default=ROOT / "Saved/Step08/final-review-v4")
    parser.add_argument("--output", type=Path, default=ROOT / "Saved/Step08/topology-review")
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    store = ReviewStore(args.run, args.output)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store))
    print(f"Topology editor: http://127.0.0.1:{server.server_address[1]}/", flush=True)
    print(f"Review revisions: {store.output}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        store.uploads.close()
        if hasattr(store, "jobs"):
            store.jobs.close()


if __name__ == "__main__":
    main()
