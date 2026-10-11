"""Validate the fixed protocol, preserve raw records and summarize without dropping failures.

Python 3.10+; standard library only. P95 uses nearest rank, not interpolation.
"""
import argparse
import csv
import hashlib
import json
import math
import platform
import shutil
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def fixed_manifest():
    path = ROOT / "Experiments/manifest.json"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == path.with_suffix(".sha256").read_text().strip(), "Manifest lock mismatch"
    manifest = load(path)
    assert manifest["protocol_version"] == 1 and manifest["warmups"] == 1 and manifest["repetitions"] == 5
    assert len(manifest["cases"]) == 30 and len(manifest["benchmarks"]) == 10
    for family in ["chain", "branching", "ring"]:
        assert sum(c["family"] == family for c in manifest["cases"]) == 10
    assert len({c["id"] for c in manifest["cases"]}) == 30
    assert len({c["id"] for c in manifest["benchmarks"]}) == 10
    return manifest, digest


def source_hashes():
    paths = [ROOT / "PlayableSketch.uproject"]
    for folder in ["Source", "Config", "Scripts"]:
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    paths.extend([ROOT / "Experiments/manifest.json", ROOT / "Experiments/manifest.sha256"])
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def prepare(path):
    _, digest = fixed_manifest()
    git = shutil.which("git")
    fallback = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe"
    if not git and fallback.exists():
        git = str(fallback)
    def query(*args):
        if not git:
            return None
        result = subprocess.run([git, *args], cwd=ROOT, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    save(path, dict(prepared_utc=datetime.now(timezone.utc).isoformat(), manifest_sha256=digest,
                    platform=platform.platform(), python=platform.python_version(),
                    git_head=query("rev-parse", "HEAD"),
                    git_status=query("status", "--porcelain", "--", "Source", "Config", "Content", "Scripts", "Experiments", "PlayableSketch.uproject"),
                    source_sha256=source_hashes()))


def stats(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return dict(n=0, median_ms=None, p95_ms=None)
    return dict(n=len(values), median_ms=statistics.median(values), p95_ms=values[math.ceil(.95 * len(values)) - 1])


def csv_file(path, records):
    keys = list(dict.fromkeys(k for r in records for k in r))
    with Path(path).open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=keys)
        writer.writeheader()
        for record in records:
            writer.writerow({k: json.dumps(v, ensure_ascii=False, separators=(",", ":")) if isinstance(v, (dict, list))
                             else ("" if v is None else v) for k, v in record.items()})


def analyze(args):
    manifest, digest = fixed_manifest()
    provenance = load(args.metadata)
    assert provenance["manifest_sha256"] == digest
    assert provenance["source_sha256"] == source_hashes(), "Source changed during the run"
    raw = load(args.raw)
    assert raw["manifest"] == manifest, "Runner consumed a different manifest"
    expected_md5 = hashlib.md5((ROOT / "Experiments/manifest.json").read_bytes()).hexdigest()
    assert raw["manifest_text_md5"].lower() == expected_md5
    generation, benchmark = raw["generation_results"], raw["benchmark_results"]
    assert len(generation) == 30 and len(benchmark) == 120
    assert {r["case_id"] for r in generation} == {c["id"] for c in manifest["cases"]}
    assert len({r["case_id"] for r in generation}) == 30
    for case in manifest["benchmarks"]:
        rows = [r for r in benchmark if r["case_id"] == case["id"]]
        assert sorted((r["repeat"], r["requested_mode"]) for r in rows) == [(i, m) for i in range(6) for m in ["Full", "Local"]]
        assert all(r["warmup"] == (r["repeat"] == 0) for r in rows)
        assert len({r["baseline_plan_md5"] for r in rows}) == 1
        assert len({r["baseline_scene_md5"] for r in rows}) == 1
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.raw, output / "raw_results.json")
    provenance["raw_results_sha256"] = hashlib.sha256(Path(args.raw).read_bytes()).hexdigest()
    provenance["finished_utc"] = raw["finished_utc"]
    if args.report:
        report = load(args.report)
        provenance["automation"] = [{"name": t["fullTestPath"], "state": t["state"]} for t in report["tests"]]
        provenance["automation_failed"] = report["failed"]
    save(output / "provenance.json", provenance)
    inputs = {c["id"]: c for c in manifest["cases"]}
    csv_file(output / "generation.csv", [dict(r, graph=inputs[r["case_id"]]["graph"], settings=manifest["settings"],
                                              algorithm_version=manifest["algorithm_version"], engine_version=raw["engine_version"],
                                              manifest_sha256=digest) for r in generation])
    edits = {c["id"]: c for c in manifest["benchmarks"]}
    csv_file(output / "benchmark.csv", [dict(r, baseline_graph=edits[r["case_id"]]["baseline"], edited_graph=edits[r["case_id"]]["edited"],
                                             settings=manifest["settings"], manifest_sha256=digest) for r in benchmark])
    def generation_summary(rows):
        return dict(n=len(rows), input_valid=sum(r["input_valid"] for r in rows),
                    layout_success=sum(r["layout_success"] for r in rows),
                    geometry_valid=sum(r["geometry_valid"] is True for r in rows),
                    navigation_completed=sum(r["navigation"]["completed"] for r in rows),
                    navigation_success=sum(r["navigation_success"] is True for r in rows),
                    failed=sum(r["status"] == "failed" for r in rows),
                    timings={k: stats(r[k] for r in rows) for k in ["layout_ms", "geometry_pipeline_ms", "validation_ms", "navigation_ms"]})
    measured = [r for r in benchmark if not r["warmup"]]
    per_pair = []
    for case in manifest["benchmarks"]:
        rows = [r for r in measured if r["case_id"] == case["id"]]
        all_rows = [r for r in benchmark if r["case_id"] == case["id"]]
        valid = all(r["equivalent"] for r in all_rows)
        modes = {m: {k: stats(r[k] for r in rows if r["requested_mode"] == m)
                     for k in ["total_ms", "plan_ms", "validation_ms", "dirty_ms", "apply_ms", "navigation_ms"]} for m in ["Local", "Full"]}
        ratio = modes["Full"]["total_ms"]["median_ms"] / modes["Local"]["total_ms"]["median_ms"] if valid else None
        per_pair.append(dict(case_id=case["id"], equivalent=valid, timings=modes, full_over_local_median_ratio=ratio))
    summary = dict(protocol_version=1, manifest_sha256=digest, engine_version=raw["engine_version"], cpu=raw["cpu"],
                   percentile_method="nearest rank ceil(0.95*n); median is conventional sample median",
                   generation=generation_summary(generation),
                   families={f: generation_summary([r for r in generation if r["family"] == f]) for f in ["chain", "branching", "ring"]},
                   benchmark=dict(distinct_edit_pairs=len(per_pair), valid_edit_pairs=sum(p["equivalent"] for p in per_pair),
                                  warmup_records=len(benchmark) - len(measured), measured_records=len(measured),
                                  equivalent_measured_records=sum(r["equivalent"] for r in measured),
                                  pooled_timings={m: {k: stats(r[k] for r in measured if r["requested_mode"] == m)
                                                       for k in ["total_ms", "plan_ms", "validation_ms", "dirty_ms", "apply_ms", "navigation_ms"]} for m in ["Local", "Full"]},
                                  per_pair=per_pair))
    save(output / "summary.json", summary)
    csv_file(output / "timing_summary.csv", [dict(scope=p["case_id"], mode=m, metric=k, **s)
                                             for p in per_pair for m, metrics in p["timings"].items() for k, s in metrics.items()])
    print(json.dumps({"generation": summary["generation"], "valid_edit_pairs": summary["benchmark"]["valid_edit_pairs"],
                      "pooled_timings": summary["benchmark"]["pooled_timings"]}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare")
    parser.add_argument("--raw")
    parser.add_argument("--metadata")
    parser.add_argument("--report")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.prepare:
        prepare(args.prepare)
    else:
        analyze(args)


if __name__ == "__main__":
    main()
