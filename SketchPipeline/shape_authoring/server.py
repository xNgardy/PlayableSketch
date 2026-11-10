import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import urlparse, unquote, parse_qs
from .jobs import ShapeJobs, ShapeJobError

WEB = Path(__file__).with_name("review.html")


def reject_non_finite(value):
    raise ValueError("Non-finite JSON")


def request_object(data):
    value = json.loads(data, parse_constant=reject_non_finite)
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def make_handler(manager):
    token = secrets.token_urlsafe(32)
    job_actions = {"cancel": manager.cancel, "retry": manager.retry}
    plan_actions = {
        "sizing": manager.sizing,
        "workspace": manager.save_workspace,
        "export": manager.export_plan,
        "confirm": manager.confirm_plan,
    }

    class Handler(BaseHTTPRequestHandler):

        def send(self, status, data, mime="application/json", headers=None):
            content = (
                data if isinstance(data, bytes) else json.dumps(data, allow_nan=False).encode()
            )
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            try:
                url = urlparse(self.path)
                path = url.path
                parts = path.strip("/").split("/")
                revision = parse_qs(url.query).get("revision_id", [None])[0]
                if path == "/":
                    self.send(200, WEB.read_bytes(), "text/html; charset=utf-8")
                elif path in ("/workspace.js", "/workspace.css"):
                    self.send(
                        200,
                        WEB.with_name(path[1:]).read_bytes(),
                        (
                            "text/javascript; charset=utf-8"
                            if path.endswith(".js")
                            else "text/css; charset=utf-8"
                        ),
                    )
                elif path.startswith("/pilot/"):
                    root = Path(__file__).resolve().parents[2] / "Saved/ShapeFirst/v1"
                    relative = unquote(path[len("/pilot/") :]) or "gallery.html"
                    artifact = (root / relative).resolve()
                    if (
                        root.resolve() not in artifact.parents
                        or artifact.suffix not in (".html", ".json", ".png", ".jpg")
                        or (not artifact.is_file())
                    ):
                        raise ShapeJobError("Unknown comparison artifact", 404)
                    mime = {
                        ".html": "text/html; charset=utf-8",
                        ".json": "application/json",
                        ".png": "image/png",
                        ".jpg": "image/jpeg",
                    }[artifact.suffix]
                    self.send(200, artifact.read_bytes(), mime)
                elif path == "/api/bootstrap":
                    self.send(
                        200,
                        {
                            "token": token,
                            "jobs": [manager.status(i) for i in list(manager.jobs)],
                            "cases": [],
                            "mode": "shape-first/1.0",
                            "profile": manager.profile,
                            "model_config": manager.model_config,
                            "capabilities": {
                                "validated_export": True,
                                "runtime_protocol": "canonical-v1",
                            },
                        },
                    )
                elif path == "/runtime/selection":
                    self.send(200, manager.runtime_selection())
                elif parts[0] == "jobs" and len(parts) in (2, 3):
                    identifier = manager.resolve_runtime(parts[1])
                    if len(parts) == 2:
                        self.send(200, manager.runtime_status(parts[1]))
                    elif parts[2] == "layout":
                        self.send(200, manager.selected_layout_bytes(identifier, revision))
                    else:
                        raise ShapeJobError("Unknown runtime route", 404)
                elif len(parts) in (2, 3) and parts[0] == "shape-jobs":
                    if len(parts) == 2:
                        self.send(200, manager.status(parts[1]))
                    elif parts[2] == "proposals":
                        self.send(200, manager.proposals(parts[1]))
                    elif parts[2] == "image":
                        self.send(200, manager.image(parts[1]), "image/png")
                    elif parts[2] == "layout":
                        self.send(200, manager.selected_layout_bytes(parts[1], revision))
                    elif parts[2] == "bundle":
                        data = manager.export_bundle(parts[1], revision)
                        self.send(
                            200,
                            data,
                            "application/zip",
                            {
                                "Content-Disposition": 'attachment; filename="PlayableSketch-Unreal.zip"'
                            },
                        )
                    elif parts[2] == "sizing":
                        self.send(200, manager.sizing_preview(parts[1]))
                    elif parts[2] == "workspace":
                        self.send(200, manager.workspace(parts[1]))
                    elif parts[2] == "sizing-plan":
                        from .sizing_preview import render

                        self.send(
                            200, render(manager.sizing_preview(parts[1])).encode(), "image/svg+xml"
                        )
                    else:
                        raise ShapeJobError("Not found", 404)
                else:
                    raise ShapeJobError("Not found", 404)
            except ShapeJobError as e:
                self.send(e.status, {"error": str(e)})
            except (ValueError, OSError, KeyError):
                self.send(500, {"error": "Could not read the shape job"})

        def do_POST(self):
            try:
                port = self.server.server_port
                origin = self.headers.get("Origin")
                if (
                    self.headers.get("X-Shape-Token") or self.headers.get("X-Review-Token")
                ) != token or (
                    origin
                    and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")
                ):
                    raise ShapeJobError("Invalid local review session", 403)
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 20000000:
                    raise ShapeJobError("Invalid request size", 413)
                data = self.rfile.read(length)
                parts = urlparse(self.path).path.strip("/").split("/")
                if parts == ["jobs"]:
                    from .delivery import multipart

                    image, filename = multipart(data, self.headers.get("Content-Type", ""))
                    record = manager.start(image, filename)
                    self.send(202, manager.runtime_status(manager.runtime_alias(record["job_id"])))
                    return
                if len(parts) == 3 and parts[0] == "jobs":
                    identifier = manager.resolve_runtime(parts[1])
                    if parts[2] not in job_actions:
                        raise ShapeJobError("Unknown runtime action", 404)
                    job_actions[parts[2]](identifier)
                    self.send(200, manager.runtime_status(parts[1]))
                    return
                if parts == ["api", "sample"]:
                    self.send(201, manager.sample())
                    return
                if parts == ["shape-jobs"]:
                    backend = self.headers.get("X-Shape-Backend", "learned")
                    self.send(
                        202,
                        manager.start(
                            data, unquote(self.headers.get("X-File-Name", "drawing.png")), backend
                        ),
                    )
                    return
                if len(parts) != 3 or parts[0] != "shape-jobs":
                    raise ShapeJobError("Not found", 404)
                identifier, action = parts[1:]
                if action in job_actions:
                    result = job_actions[action](identifier)
                elif action in plan_actions:
                    result = plan_actions[action](identifier, request_object(data))
                elif action == "edit":
                    if length > 4000000:
                        raise ShapeJobError("Edit is too large", 413)
                    body = json.loads(data, parse_constant=reject_non_finite)
                    if not isinstance(body, dict):
                        raise ShapeJobError("JSON object required")
                    result = manager.edit(identifier, body)
                else:
                    raise ShapeJobError("Not found", 404)
                self.send(200, result)
            except ShapeJobError as e:
                self.send(e.status, {"error": str(e)})
            except (ValueError, TypeError, KeyError):
                self.send(400, {"error": "Invalid shape request"})
            except OSError:
                self.send(500, {"error": "Could not save the shape job"})

    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Local shape-first API for authoring, export and runtime import."
    )
    parser.add_argument("--output", type=Path, default=Path("Saved/ShapeFirst/jobs"))
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--timeout", type=float, default=45)
    from .propose import PROFILE_NAMES

    parser.add_argument("--profile", choices=PROFILE_NAMES, default="baseline")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help="Explicit local experimental checkpoint; default model stays unchanged",
    )
    parser.add_argument("--expected-sha256")
    parser.add_argument("--normalize-ink", action="store_true")
    args = parser.parse_args()
    manager = ShapeJobs(
        args.output,
        args.timeout,
        profile=args.profile,
        checkpoint=args.checkpoint,
        expected_sha256=args.expected_sha256,
        normalize_ink=args.normalize_ink,
    )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(manager))
    print(f"Shape review: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        manager.close()
