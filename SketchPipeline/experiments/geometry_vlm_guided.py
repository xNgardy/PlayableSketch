import json
from types import SimpleNamespace
from SketchPipeline.experiments import geometry_vlm as experiment
from SketchPipeline.experiments.geometry_study import OUT, MODEL, REVISION, samples
from SketchPipeline.synthetic.augment import write, sha, ROOT


def output_schema(wall_ids, opening_ids):

    def identifiers(ids):
        return dict(
            type="object",
            properties={x: dict(type="boolean") for x in ids},
            required=ids,
            additionalProperties=False,
        )

    segment = dict(
        type="array", items=dict(type="integer", minimum=0, maximum=1000), minItems=4, maxItems=4
    )
    hybrid = bool(wall_ids or opening_ids)
    properties = dict(
        keep_walls=identifiers(wall_ids),
        walls=dict(type="array", items=segment, maxItems=0 if hybrid else 24),
        keep_openings=identifiers(opening_ids),
        openings=dict(type="array", items=segment, maxItems=4 if hybrid else 12),
        regions=dict(type="array", items=segment, maxItems=0),
    )
    return dict(
        type="object", properties=properties, required=list(properties), additionalProperties=False
    )


def protocol():
    value = dict(
        version="guided-geometry-pilot/2.0",
        model=MODEL,
        revision=REVISION,
        sample_ids=[s["id"] for s in samples()],
        temperature=0,
        max_tokens=1800,
        json_decoding="MLX-VLM llguidance token mask; allowed candidate IDs come only from inference candidates.",
        native_rectangle_predictions="Disabled; exact topology always comes from the common wall graph decoder.",
        bounded_hybrid="Boolean decisions for each supplied structural wall/opening; at most four additional opening intervals; no new walls. This limits wall recall to the structural proposal set.",
        initial_preflight="strict_preflight/: seven failed responses plus interrupted eighth call. Not a completed 19-image arm.",
        scope="Adaptive validation development experiment, not an independent holdout.",
        code_hashes={
            str(p.relative_to(ROOT)): sha(p)
            for p in [
                ROOT / "SketchPipeline/experiments/geometry_vlm_guided.py",
                ROOT / "SketchPipeline/experiments/geometry_vlm.py",
                ROOT / "SketchPipeline/perception/structural.py",
            ]
        },
    )
    path = OUT / "guided_protocol.json"
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError("Guided protocol changed")
    else:
        write(path, value)
    return value


def run():
    import mlx_vlm
    from mlx_vlm.structured import build_json_schema_logits_processor

    original_generate = mlx_vlm.generate
    counter = 0

    def guided_generate(model, processor, prompt, *args, **kwargs):
        nonlocal counter
        wall_ids = []
        opening_ids = []
        if "Candidates: " in prompt:
            table = json.loads(prompt.split("Candidates: ", 1)[1].split("\nCached OCR", 1)[0])
            wall_ids = [x[0] for x in table["walls"]]
            opening_ids = [x[0] for x in table["openings"]]
        prompt = prompt.replace('"keep_walls":[]', '"keep_walls":{candidate_id:true_or_false}')
        prompt = prompt.replace(
            '"keep_openings":[]', '"keep_openings":{candidate_id:true_or_false}'
        )
        prompt = prompt.replace(
            "keep_walls and keep_openings MUST both be []",
            "keep_walls and keep_openings MUST both be {}",
        )
        prompt = prompt.replace(
            "Select ONLY correct supplied IDs in keep_walls/keep_openings.",
            "For EVERY supplied ID, set true if structural/correct, false if grid/dimension/text/incorrect. Use boolean ID maps.",
        )
        prompt = prompt.replace(
            "Add genuinely missing elements in walls/openings.",
            "walls MUST be empty. Add at most four genuinely missing opening intervals in openings.",
        )
        prompt += "\nregions MUST be empty. Candidate maps contain booleans only, never coordinates. Return each coordinate interval only once."
        schema = output_schema(wall_ids, opening_ids)
        call = counter
        counter += 1
        write(OUT / "guided_schemas" / f"{call:03d}.json", schema)
        target = OUT / "guided_responses"
        target.mkdir(exist_ok=True)
        (target / f"{call:03d}.prompt.txt").write_text(prompt)
        tokenizer = getattr(processor, "tokenizer", processor)
        kwargs["logits_processors"] = [build_json_schema_logits_processor(tokenizer, schema)]
        result = original_generate(model, processor, prompt, *args, **kwargs)
        (target / f"{call:03d}.raw.txt").write_text(result.text)
        parsed = json.loads(result.text)
        for key in ["keep_walls", "keep_openings"]:
            parsed[key] = [k for k, v in parsed[key].items() if v]
        return SimpleNamespace(
            text=json.dumps(parsed),
            generation_tokens=result.generation_tokens,
            peak_memory=getattr(result, "peak_memory", None),
        )

    experiment.protocol = protocol
    mlx_vlm.generate = guided_generate
    experiment.run()


if __name__ == "__main__":
    run()
