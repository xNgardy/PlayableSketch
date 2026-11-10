import json as _content_json
from pathlib import Path as _ContentPath

REPORT_TEXT = _content_json.loads(
    _ContentPath(__file__).with_name("package.content.tr.json").read_text(encoding="utf-8")
)
from pathlib import Path
import json
import zipfile
import shutil

root = Path.cwd()
out = root / "outputs/day4"
manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
guide = REPORT_TEXT["text_001"]
inventory = REPORT_TEXT["text_002"] + "\n".join(
    (
        "| "
        + (REPORT_TEXT["text_003"] if item["action"] == "replace" else REPORT_TEXT["text_009"])
        + " | `"
        + item["path"]
        + "` |"
        for item in manifest
    )
)
verification_file = out / "verification.json"
verification = (
    json.loads(verification_file.read_text(encoding="utf-8")) if verification_file.exists() else {}
)
summary = "".join(
    [
        "Editor build: ",
        format(verification.get("editor_build", REPORT_TEXT["text_008"]), ""),
        ". Unreal automation: ",
        format(verification.get("automation_result", REPORT_TEXT["text_008"]), ""),
        REPORT_TEXT["text_004"],
        format(verification.get("pass_count", REPORT_TEXT["text_008"]), ""),
        REPORT_TEXT["text_005"],
    ]
)
guide = guide.replace("{inventory}", inventory).replace("{verification}", summary)
for item in manifest:
    text = (out / item["path"]).read_text(encoding="utf-8")
    assert "//" not in text and "/*" not in text, item["path"]
    language = "csharp" if item["path"].endswith(".cs") else "cpp"
    guide += f"### {item['path']}\n\n```{language}\n{text}```\n\n"
(out / REPORT_TEXT["text_007"]).write_text(guide, encoding="utf-8")
archive = out / REPORT_TEXT["text_006"]
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
    for item in manifest:
        bundle.write(out / item["path"], item["path"])
    for name in [REPORT_TEXT["text_007"], "manifest.json", "verification.json"]:
        if (out / name).exists():
            bundle.write(out / name, name)
print(f"Packaged {len(manifest)} complete files. Guide size: {len(guide):,} characters.")
