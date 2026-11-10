import argparse
import json
from pathlib import Path
import shutil
import tempfile
from PIL import Image
from SketchPipeline.perception.ocr import rectify_crop
from SketchPipeline.preprocessing.dataset import audit
from SketchPipeline.preprocessing.prepare import decode


def export(manifest, output, source_path=None):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new directory.")
    _, samples = audit(Path(manifest))
    layouts = {}
    if source_path:
        source = json.loads(Path(source_path).read_text())
        layouts = {
            (s["id"], f"t{i:03d}"): label.get("text_layout", "single_line")
            for s in source["samples"]
            for i, label in enumerate(s["texts"], 1)
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".ocr-labels-", dir=output.parent))
    try:
        (staging / "crops").mkdir()
        records, lines = ([], [])
        for sample, path, obs, _, _ in samples:
            original, _, _, _ = decode(path)
            for text in obs["texts"]:
                crop, transform = rectify_crop(original, text["polygon_px"])
                name = f"crops/{sample['id']}_{text['id']}.png"
                Image.fromarray(crop).save(staging / name)
                layout = layouts.get((sample["id"], text["id"]), "unclassified")
                record = {
                    "image": name,
                    "case_id": sample["id"],
                    "text_id": text["id"],
                    "transcription": text["raw_text"],
                    "source_image_sha256": sample["image_sha256"],
                    "polygon_original_px": text["polygon_px"],
                    "original_to_crop": transform.tolist(),
                    "text_layout": layout,
                    "split": sample["split"],
                    "base_plan_id": sample["base_plan_id"],
                    "writer_id": sample["writer_id"],
                }
                records.append(record)
                if layout == "single_line":
                    lines.append(name + "\t" + text["raw_text"])
        (staging / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "playablesketch-ocr-crops/1.0",
                    "training_performed": False,
                    "notes": [
                        "Development curation only; no train/validation split is assigned.",
                        "Multiline labels remain in the crop manifest but are excluded from single-line recognition TSV.",
                    ],
                    "samples": records,
                },
                indent=2,
            )
            + "\n"
        )
        (staging / "recognition_single_line.tsv").write_text("\n".join(lines) + "\n")
        staging.rename(output)
        return (len(records), len(lines))
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(
        description="Export reviewed text regions for curation; no OCR, training or split leakage."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--source", type=Path, help="Optional manual source classifying single/multiline labels"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    total, single = export(args.manifest, args.output, args.source)
    print(
        f"Exported {total} manual text crops; {single} single-line labels. No training performed."
    )


if __name__ == "__main__":
    main()
