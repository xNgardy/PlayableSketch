import json as _content_json
from pathlib import Path as _ContentPath

REPORT_TEXT = _content_json.loads(
    _ContentPath(__file__)
    .with_name("rename_validation_tests.content.tr.json")
    .read_text(encoding="utf-8")
)
from pathlib import Path
import json
import zipfile

root = Path.cwd()
old = root / "outputs/day4"
out = root / "outputs/authoring-validation"
out.mkdir(parents=True, exist_ok=True)
mapping = {
    "PlayableSketchDay4Tests": "PlayableSketchAuthoringValidationTests",
    "FPlayableSketchDay4AutomationTest": "FPlayableSketchAuthoringValidationAutomationTest",
    "TestDay4Validation": "TestAuthoringValidation",
    "PlayableSketch.Day4.Validation": "PlayableSketch.Authoring.Validation",
    "Day 4 test resize": "Authoring validation test resize",
    "Day 4 tests finished": "Authoring validation tests finished",
}


def rename(text):
    for before, after in mapping.items():
        text = text.replace(before, after)
    return text


manifest = json.loads((old / "manifest.json").read_text(encoding="utf-8"))
changed = []
for item in manifest:
    original_path = item["path"]
    source = old / original_path
    if Path(original_path).name in ("PlayableSketchLevelActor.h", "PlayableSketchLevelActor.cpp"):
        source = root / original_path
    original = source.read_text(encoding="utf-8-sig")
    content = rename(original)
    item["path"] = rename(original_path)
    destination = out / item["path"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content.rstrip() + "\n", encoding="utf-8")
    assert "day" not in content.lower(), item["path"]
    assert "//" not in content and "/*" not in content, item["path"]
    if content != original or original_path != item["path"]:
        changed.append(item)
assert len(changed) == 4
guide = REPORT_TEXT["text_001"]
for item in changed:
    content = (out / item["path"]).read_text(encoding="utf-8")
    guide += f"### {item['path']}\n\n```cpp\n{content}```\n\n"
test_h = (
    out / "Source/PlayableSketch/Public/Validation/Tests/PlayableSketchAuthoringValidationTests.h"
)
test_cpp = (
    out
    / "Source/PlayableSketch/Private/Validation/Tests/PlayableSketchAuthoringValidationTests.cpp"
)
actor_h = out / "Source/PlayableSketch/PlayableSketchLevelActor.h"
actor_cpp = out / "Source/PlayableSketch/PlayableSketchLevelActor.cpp"
assert "class PLAYABLESKETCH_API FPlayableSketchAuthoringValidationTests" in test_h.read_text()
assert "bool FPlayableSketchAuthoringValidationTests::Run()" in test_cpp.read_text()
assert "void TestAuthoringValidation();" in actor_h.read_text()
assert "void APlayableSketchLevelActor::TestAuthoringValidation()" in actor_cpp.read_text()
assert (
    '#include "Validation/Tests/PlayableSketchAuthoringValidationTests.h"' in actor_cpp.read_text()
)
assert (
    '#include "Validation/Tests/PlayableSketchAuthoringValidationTests.h"' in test_cpp.read_text()
)
(out / REPORT_TEXT["text_002"]).write_text(guide, encoding="utf-8")
(out / "manifest.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
)
with zipfile.ZipFile(out / REPORT_TEXT["text_003"], "w", zipfile.ZIP_DEFLATED) as bundle:
    for item in manifest:
        bundle.write(out / item["path"], item["path"])
    bundle.write(out / "manifest.json", "manifest.json")
    bundle.write(out / REPORT_TEXT["text_002"], REPORT_TEXT["text_002"])
print(
    json.dumps(
        {
            "source_files": len(manifest),
            "changed_files": [i["path"] for i in changed],
            "naming_checks": "passed",
        },
        indent=2,
    )
)
