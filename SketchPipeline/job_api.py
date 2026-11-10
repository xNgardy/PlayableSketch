from email.parser import BytesParser
from email.policy import default
import json
from urllib.parse import parse_qs
from SketchPipeline.review.server import ReviewError
from SketchPipeline.validation.validate import load_json


def multipart(data, content_type):
    if (
        not content_type.startswith("multipart/form-data;")
        or len(content_type) > 500
        or "\r" in content_type
        or ("\n" in content_type)
    ):
        raise ReviewError("Use multipart/form-data with image and optional config JSON", 415)
    message = BytesParser(policy=default).parsebytes(
        ("Content-Type: " + content_type + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + data
    )
    if not message.is_multipart():
        raise ReviewError("Invalid multipart upload")
    fields = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name not in ("image", "config") or name in fields or part.is_multipart():
            raise ReviewError("Expected one image and optional config")
        fields[name] = (part.get_payload(decode=True), part.get_filename())
    if "image" not in fields or not fields["image"][1]:
        raise ReviewError("Image file required")
    config = {}
    if "config" in fields:
        if len(fields["config"][0]) > 20000:
            raise ReviewError("Configuration too large", 413)

        def unique(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("Duplicate configuration field")
                result[key] = value
            return result

        config = json.loads(
            fields["config"][0],
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite config")),
        )
    return (fields["image"][0], fields["image"][1], config)


def get(manager, path, query):
    pieces = path.strip("/").split("/")
    if len(pieces) < 2 or len(pieces) > 3:
        raise ReviewError("Unknown job route", 404)
    identifier = pieces[1]
    if len(pieces) == 2:
        return manager.status(identifier)
    route = pieces[2]
    manager.ready(identifier)
    if route == "layout":
        return manager.export(identifier, parse_qs(query).get("revision_id", [None])[0])
    if route == "draft":
        topology = manager.store.latest(identifier)
        return (
            manager.metric.load(identifier)
            if topology and topology["status"] == "reviewed"
            else {"review_stage": "topology", "case": manager.store.load(identifier)}
        )
    if route == "manifest":
        from SketchPipeline.pipeline import verify_manifest

        return verify_manifest(manager.root / identifier)
    if route == "evidence":
        return load_json(manager.root / identifier / "prediction/observations.json")
    raise ReviewError("Unknown job route", 404)


def mutate(manager, path, body):
    pieces = path.strip("/").split("/")
    if len(pieces) != 3:
        raise ReviewError("Unknown job action", 404)
    identifier, action = pieces[1:]
    if action == "cancel":
        return manager.cancel(identifier)
    if action == "retry":
        return manager.retry(identifier)
    manager.ready(identifier)
    if action == "draft":
        return manager.metric.transact(
            identifier,
            body.get("base_revision_id"),
            "save",
            body.get("state"),
            telemetry=body.get("telemetry"),
        )
    if action == "accept":
        return manager.metric.transact(
            identifier,
            body.get("base_revision_id"),
            "accept",
            reviewer=body.get("reviewer"),
            telemetry=body.get("telemetry"),
        )
    if action == "validate":
        record = manager.metric.latest(identifier)
        if not record:
            raise ReviewError("Save a metric revision first", 409)
        result = manager.metric.transact(
            identifier, body.get("base_revision_id"), "preview", record["state"]
        )
        return {
            "base_revision_id": body["base_revision_id"],
            "validation": result["report"]["validation"],
        }
    raise ReviewError("Unknown job action", 404)
