from datetime import datetime


def validate_telemetry(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"active_ms", "interaction_count", "source"}:
        raise ValueError("Invalid review telemetry fields")
    if value["source"] != "browser-visible-interaction/v1":
        raise ValueError("Invalid review telemetry source")
    for key, maximum in [("active_ms", 1800000), ("interaction_count", 100000)]:
        if type(value[key]) is not int or not 0 <= value[key] <= maximum:
            raise ValueError("Invalid " + key)
    return dict(value)


def correction_metrics(records):
    if not records:
        return dict(
            revisions=0,
            edit_commands=0,
            changed_entities=0,
            active_review_seconds=None,
            wall_elapsed_seconds=None,
        )
    edits = [r for r in records if r.get("command", {}).get("type") in {"save", "undo", "redo"}]
    values = [r.get("telemetry") for r in records]
    telemetry_complete = all((x is not None for x in values))
    times = [datetime.fromisoformat(r["created_at"]) for r in records if r.get("created_at")]
    return dict(
        revisions=len(records),
        edit_commands=len(edits),
        changed_entities=sum(
            (len(r.get("command", {}).get("affected_entity_ids", [])) for r in edits)
        ),
        active_review_seconds=(
            sum((x["active_ms"] for x in values)) / 1000 if telemetry_complete else None
        ),
        measured_partial_seconds=(
            sum((x["active_ms"] for x in values if x is not None)) / 1000 if any(values) else None
        ),
        telemetry_complete=telemetry_complete,
        wall_elapsed_seconds=(max(times) - min(times)).total_seconds() if len(times) > 1 else None,
        note="Client-observed focused visible interaction time, capped after 60s idle; self-reported, excludes topology review and unsaved/closed-tab work. Wall elapsed is not human active time.",
    )
