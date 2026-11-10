import argparse
import json
from .build_tablet_references import ANNOTATIONS, ROOT, artifacts as build_artifacts

SOURCE = ANNOTATIONS / "tablet_21_30.source.json"


def artifacts():
    return build_artifacts(
        SOURCE, "manifest_tablet_21_30.json", "manifest_all_20.json", "manifest_all_30.json"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Reproduce manual Data_21–30 references without inference or training."
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace only generated Data_21–30 files and their separate manifests",
    )
    args = parser.parse_args()
    output = artifacts()
    if args.check:
        differences = [
            str(p.relative_to(ROOT))
            for p, d in output.items()
            if not p.exists() or json.loads(p.read_text()) != d
        ]
        if differences:
            raise SystemExit("Reference differences: " + ", ".join(differences))
        print(f"All {len(output)} Data_21–30 artifacts match their manual source.")
        return
    if not args.overwrite and any((p.exists() for p in output)):
        raise SystemExit("Existing labels are preserved. Use --check or explicitly --overwrite.")
    for path, document in output.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + "\n")
    print(f"Wrote {len(output)} artifacts for Data_21–30; no images or older labels changed.")


if __name__ == "__main__":
    main()
