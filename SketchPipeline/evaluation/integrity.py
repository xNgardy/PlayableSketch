from .protocol import read, sha, write


def seal(output):
    output = output.resolve()
    inventory = {
        p.relative_to(output).as_posix(): sha(p)
        for p in sorted(output.rglob("*"))
        if p.is_file() and p.name != "artifact-integrity.json"
    }
    write(
        output / "artifact-integrity.json",
        dict(schema_version="evaluation-artifacts/1.0", sha256=inventory),
    )
    return inventory


def verify_artifacts(output):
    output = output.resolve()
    inventory = read(output / "artifact-integrity.json")["sha256"]
    for name, expected in inventory.items():
        path = (output / name).resolve()
        if not path.is_relative_to(output) or not path.is_file() or sha(path) != expected:
            raise ValueError("Evaluation artifact changed: " + name)
    return True
