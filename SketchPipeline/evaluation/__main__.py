import argparse
import json
from pathlib import Path
from .protocol import freeze, read, verify, write
from .report import run
from .integrity import seal, verify_artifacts


def main():
    p = argparse.ArgumentParser(
        description="python -m SketchPipeline.evaluation --output NEW_DIR [--challenges]"
    )
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("--challenges", action="store_true")
    args = p.parse_args()
    if args.verify_only:
        verify(read(args.output / "protocol.json"))
        verify_artifacts(args.output)
        print("Frozen input integrity verified.")
        return
    if args.challenges:
        from .challenges import run as run_challenges

        freeze(args.output)
        run_challenges(args.output / "challenges")
    report = run(args.output)
    if args.challenges:
        report["fresh_robustness"] = read(args.output / "challenges/report.json")
        write(args.output / "report.json", report)
    seal(args.output)
    print(
        json.dumps(
            dict(
                samples=len(report["samples"]),
                end_to_end=report["end_to_end"],
                solver_statuses=report["solver"]["statuses"],
                release=report["release"],
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
