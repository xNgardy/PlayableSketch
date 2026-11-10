import argparse
import json
from pathlib import Path
import subprocess
import time
from Scripts.runtime_fixture import generate, accept_job

ROOT = Path(__file__).resolve().parents[1]


def run(
    executable,
    output,
    editor=False,
    load=False,
    offline=False,
    keep=False,
    prefix="Step14_PackageControl_20261021",
):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / "runtime-report.json"
    if report.exists():
        raise ValueError("Use a new test output directory; old completion reports cannot be reused")
    image = generate(output)
    command = [str(executable)]
    if editor:
        command += [
            str(ROOT / "PlayableSketch.uproject"),
            "/Engine/Maps/Entry?game=/Script/PlayableSketch.PlayableSketchRuntimeGameMode",
            "-game",
        ]
    command += [
        "-unattended",
        "-nullrhi",
        "-nosound",
        "-nosplash",
        "-RuntimeSmoke",
        "-RuntimeService=http://127.0.0.1:8773",
        "-RuntimeSavePrefix=" + prefix,
        "-RuntimeReport=" + str(report),
        "-abslog=" + str(output / "runtime.log"),
    ]
    if not keep:
        command += ["-RuntimeExit"]
    if load:
        command += ["-RuntimeLoadSave"]
    else:
        command += ["-RuntimeImage=" + str(image)]
    if offline:
        command += ["-RuntimeOffline"]
    (output / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (output / "stdout.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
    (output / "pid.txt").write_text(str(process.pid) + "\n")
    accepted = False
    deadline = time.monotonic() + 210
    while time.monotonic() < deadline:
        result = None
        try:
            result = json.loads(report.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            pass
        if (
            result
            and result.get("stage") == "needs_review"
            and result.get("job_id")
            and (not accepted)
        ):
            accept_job("http://127.0.0.1:8773", result["job_id"], output)
            accepted = True
            print("Controlled synthetic review accepted:", result["job_id"], flush=True)
        if result and result.get("completed"):
            if not result.get("success"):
                raise RuntimeError("Runtime smoke failed; inspect " + str(report))
            if not keep and process.wait(timeout=20) != 0:
                raise RuntimeError("Nonzero runtime process exit")
            print(
                json.dumps({k: v for k, v in result.items() if k != "canonical_json"}, indent=2),
                flush=True,
            )
            return result
        if process.poll() is not None:
            raise RuntimeError("Runtime exited before completion: " + str(output / "runtime.log"))
        time.sleep(0.2)
    process.terminate()
    raise RuntimeError("Runtime test driver timed out")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--executable", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--editor", action="store_true")
    p.add_argument("--load", action="store_true")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--keep", action="store_true")
    p.add_argument("--prefix", default="Step14_PackageControl_20261021")
    a = p.parse_args()
    run(a.executable, a.output, a.editor, a.load, a.offline, a.keep, a.prefix)
