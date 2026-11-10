import json
from pathlib import Path

_DATA = json.loads(Path(__file__).with_suffix(".json").read_text())
SAMPLES = {int(identifier): sample for identifier, sample in _DATA["samples"].items()}
