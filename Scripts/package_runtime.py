import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENGINE = Path("/Users/Shared/Epic Games/UE_5.7")


def package(reuse=False):
    out = ROOT / "Saved/Step14"
    out.mkdir(exist_ok=True)
    stage = out / "package-project"
    stage.mkdir(exist_ok=True)
    if reuse:
        previous = json.loads((out / "package-source-hashes.json").read_text())
        if not all(
            (
                hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value
                for name, value in previous.items()
            )
        ):
            raise ValueError("Cannot reuse a build after source changes")
    for name in ("Source", "Config"):
        shutil.copytree(ROOT / name, stage / name, dirs_exist_ok=True)
    shutil.copy2(ROOT / "PlayableSketch.uproject", stage / "PlayableSketch.uproject")
    (stage / "Content").mkdir(exist_ok=True)
    (stage / "Binaries/Mac").mkdir(parents=True, exist_ok=True)
    for path in (ROOT / "Binaries/Mac").glob("*"):
        if path.is_file() and path.name.startswith(("UnrealEditor", "PlayableSketchEditor")):
            shutil.copy2(path, stage / "Binaries/Mac" / path.name)
    with (stage / "Config/DefaultEngine.ini").open("a") as f:
        f.write(
            "\n[/Script/EngineSettings.GameMapsSettings]\nGameDefaultMap=/Engine/Maps/Entry.Entry\nGlobalDefaultGameMode=/Script/PlayableSketch.PlayableSketchRuntimeGameMode\n\n[/Script/Engine.RendererSettings]\nr.RayTracing=False\nr.GenerateMeshDistanceFields=False\nr.DynamicGlobalIlluminationMethod=0\nr.ReflectionMethod=0\nr.Shadow.Virtual.Enable=0\nr.Substrate=False\nr.Nanite.ProjectEnabled=False\n\n[/Script/MacTargetPlatform.MacTargetSettings]\n!TargetedRHIs=ClearArray\n+TargetedRHIs=SF_METAL_SM5\n"
        )
    with (stage / "Config/DefaultGame.ini").open("a") as f:
        f.write(
            '\n[/Script/UnrealEd.ProjectPackagingSettings]\n!MapsToCook=ClearArray\n+MapsToCook=(FilePath="/Engine/Maps/Entry")\n+DirectoriesToAlwaysCook=(Path="/Engine/BasicShapes")\nbSkipEditorContent=True\nbIncludePrerequisites=False\nbUsePakFile=True\nbGenerateChunks=False\n'
        )
    hashes = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT / "Source").rglob("*")
        if p.is_file()
    }
    for name, value in hashes.items():
        if hashlib.sha256((stage / name).read_bytes()).hexdigest() != value:
            raise ValueError("Staged source mismatch: " + name)
    (out / "package-source-hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")
    sdk = ENGINE / "Engine/Config/Apple/Apple_SDK.json"
    original = sdk.read_bytes()
    config = json.loads(original)
    config["MaxVersion"] = "27.0.0"
    modified = (json.dumps(config, indent="\t") + "\n").encode()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    command = [
        str(ENGINE / "Engine/Build/BatchFiles/RunUAT.sh"),
        "BuildCookRun",
        "-project=" + str(stage / "PlayableSketch.uproject"),
        "-target=PlayableSketchRuntime",
        "-noP4",
        "-platform=Mac",
        "-clientconfig=Development",
        "-stage",
        "-pak",
        "-package",
        "-archive",
        "-archivedirectory=" + str(out / "package"),
        "-map=/Engine/Maps/Entry",
        "-nocompileeditor",
        "-utf8output",
        "-unattended",
        "-NoUBA",
        "-architecture=arm64",
    ]
    command += ["-skipbuild", "-skipcook"] if reuse else ["-build", "-cook"]
    (out / "package-command.json").write_text(json.dumps(command, indent=2) + "\n")
    try:
        sdk.write_bytes(modified)
        env = os.environ.copy()
        env["DEVELOPER_DIR"] = "/Applications/Xcode.app/Contents/Developer"
        with (out / "package.log").open("w") as log:
            result = subprocess.call(
                command, cwd=stage, env=env, stdout=log, stderr=subprocess.STDOUT
            )
    finally:
        if sdk.read_bytes() == modified:
            sdk.write_bytes(original)
        print("Engine SDK restored:", sdk.read_bytes() == original, flush=True)
    print("Package exit:", result, flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build a local Mac runtime without changing the user's Editor map/config/assets."
    )
    parser.add_argument("--reuse-build", action="store_true")
    sys.exit(package(parser.parse_args().reuse_build))
