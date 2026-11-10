import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
MODEL_LOCK = ROOT / "SketchPipeline/shape_authoring/workspace-model.lock.json"


def local_service(value):
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in ("127.0.0.1", "localhost")
        or (not parsed.port)
        or parsed.username
        or parsed.password
        or (parsed.path not in ("", "/"))
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Choose an explicit loopback HTTP service and port.")
    return value.rstrip("/")


def sidecar_command(port):
    candidate = json.loads(MODEL_LOCK.read_text())
    command = [
        str(ROOT / candidate.get("python_path", "Saved/Training/v1/python/bin/python")),
        "-m",
        "SketchPipeline.shape_authoring.server",
        "--port",
        str(port),
        "--output",
        str(ROOT / "Saved/ShapeFirst/workspace/jobs"),
        "--profile",
        candidate["required_profile"],
        "--checkpoint",
        str(ROOT / candidate["checkpoint_path"]),
        "--expected-sha256",
        candidate["checkpoint_sha256"],
    ]
    if candidate["normalize_ink"]:
        command.append("--normalize-ink")
    return command


def service_matches(bootstrap, candidate):
    model = bootstrap.get("model_config", {})
    return (
        bootstrap.get("mode") == "shape-first/1.0"
        and bootstrap.get("profile") == candidate["required_profile"]
        and model.get("expected_sha256") == candidate["checkpoint_sha256"]
        and model.get("normalize_ink") == candidate["normalize_ink"]
    )


def launch_arguments(app, service, selection=None):
    args = [
        "open",
        "-n",
        str(app),
        "--args",
        "-windowed",
        "-ResX=1440",
        "-ResY=900",
        "-RuntimeService=" + local_service(service),
    ]
    if selection and selection["validation_mode"] == "gameplay":
        args += [
            "-RuntimeJob=" + selection["runtime_job_id"],
            "-RuntimeRevision=" + selection["revision_id"],
        ]
    return args


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-only", action="store_true")
    parser.add_argument(
        "--service",
        default=os.environ.get(
            "PLAYABLESKETCH_SERVICE_URL",
            "http://127.0.0.1:" + os.environ.get("PLAYABLESKETCH_PORT", "8772"),
        ),
    )
    args = parser.parse_args()
    service = local_service(args.service)
    apps = list((ROOT / "Saved/Step14/package").rglob("PlayableSketchRuntime.app"))
    if not args.workspace_only and len(apps) != 1:
        raise SystemExit("Build the runtime package first. See Docs/step14_packaged_runtime.md.")
    candidate = json.loads(MODEL_LOCK.read_text())

    def get(path):
        with urlopen(service + path, timeout=3) as response:
            return json.load(response)

    def healthy():
        try:
            bootstrap = get("/api/bootstrap")
        except (OSError, ValueError):
            return False
        if not service_matches(bootstrap, candidate):
            raise SystemExit(
                "A different workspace model is running at "
                + service
                + ". Stop its terminal and start PlayableSketch again."
            )
        return True

    ready = healthy()
    if not ready:
        command = sidecar_command(urlparse(service).port)
        if not Path(command[0]).exists():
            raise SystemExit("The local shape-first Python environment is missing.")
        folder = ROOT / "Saved/ShapeFirst/delivery"
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "sidecar-launch.log").open("ab") as log:
            environment = os.environ.copy()
            environment.update(OMP_NUM_THREADS="4", PYTHONDONTWRITEBYTECODE="1")
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        (folder / "sidecar-launch.pid").write_text(str(process.pid))
        deadline = time.monotonic() + 20
        while not healthy():
            if process.poll() is not None or time.monotonic() > deadline:
                raise SystemExit(
                    "The local workspace could not start. Check Saved/ShapeFirst/delivery/sidecar-launch.log and the selected port."
                )
            time.sleep(0.2)
    if args.workspace_only:
        subprocess.run(["open", service], check=True)
        print("PlayableSketch workspace opened: " + service)
        return
    try:
        selection = get("/runtime/selection")
    except (OSError, ValueError):
        selection = None
    subprocess.run(launch_arguments(apps[0], service, selection), check=True)
    print("PlayableSketch runtime opened. Workspace: " + service)
    print(
        "Your current playable export is selected. Choose Open latest plan, then Follow route or use WASD / arrow keys."
        if selection and selection["validation_mode"] == "gameplay"
        else "In Review plan, choose Playable level, select Start and Goal, then confirm and export. Choose Open latest plan here when ready. Geometry-only files are for Unreal Editor."
    )


if __name__ == "__main__":
    main()
