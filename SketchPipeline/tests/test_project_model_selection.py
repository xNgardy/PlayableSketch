import copy
import io
import json
from pathlib import Path
import sys
import tempfile
from urllib.error import URLError
from unittest.mock import patch
import unittest

from Scripts.start_runtime import MODEL_LOCK, ROOT, main, service_matches, sidecar_command


class ProjectModelSelectionTests(unittest.TestCase):
    def setUp(self):
        self.model = json.loads(MODEL_LOCK.read_text())
        self.bootstrap = {
            "mode": "shape-first/1.0",
            "profile": self.model["required_profile"],
            "model_config": {
                "expected_sha256": self.model["checkpoint_sha256"],
                "normalize_ink": self.model["normalize_ink"],
            },
        }

    def test_both_launch_modes_share_the_selected_model(self):
        command = sidecar_command(8772)
        self.assertEqual(
            command[command.index("--checkpoint") + 1],
            str(ROOT / self.model["checkpoint_path"]),
        )
        self.assertEqual(
            command[command.index("--expected-sha256") + 1], self.model["checkpoint_sha256"]
        )
        workspace = (ROOT / "Start Sketch Workspace.command").read_text()
        self.assertIn("Scripts/start_runtime.py", workspace)
        self.assertIn("--workspace-only", workspace)
        self.assertNotIn("shape-dinov2-decoder-v1.pt", workspace)

    def test_running_model_requires_matching_hash_profile_and_normalization(self):
        self.assertTrue(service_matches(self.bootstrap, self.model))
        for key, value in [
            ("expected_sha256", "old-model"),
            ("normalize_ink", not self.model["normalize_ink"]),
        ]:
            changed = copy.deepcopy(self.bootstrap)
            changed["model_config"][key] = value
            self.assertFalse(service_matches(changed, self.model))
        changed = copy.deepcopy(self.bootstrap)
        changed["profile"] = "baseline"
        self.assertFalse(service_matches(changed, self.model))
        self.assertFalse(service_matches({"mode": "shape-first/1.0"}, self.model))

    def test_workspace_reuses_matching_service_and_opens_browser(self):
        with patch("sys.argv", ["start_runtime", "--workspace-only"]), patch(
            "Scripts.start_runtime.urlopen",
            return_value=io.BytesIO(json.dumps(self.bootstrap).encode()),
        ), patch("Scripts.start_runtime.subprocess.Popen") as spawn, patch(
            "Scripts.start_runtime.subprocess.call"
        ) as call, patch(
            "Scripts.start_runtime.subprocess.run"
        ) as launch:
            main()
        spawn.assert_not_called()
        call.assert_not_called()
        launch.assert_called_once_with(["open", "http://127.0.0.1:8772"], check=True)

    def test_workspace_waits_for_new_service_before_opening_browser(self):
        events = []
        responses = [URLError("not running"), io.BytesIO(json.dumps(self.bootstrap).encode())]

        def get(*args, **kwargs):
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            events.append("ready")
            return response

        with tempfile.TemporaryDirectory() as temporary, patch(
            "sys.argv", ["start_runtime", "--workspace-only"]
        ), patch("Scripts.start_runtime.ROOT", Path(temporary)), patch(
            "Scripts.start_runtime.sidecar_command", return_value=[sys.executable, "server"]
        ), patch(
            "Scripts.start_runtime.urlopen", side_effect=get
        ), patch(
            "Scripts.start_runtime.subprocess.Popen"
        ) as spawn, patch(
            "Scripts.start_runtime.subprocess.run",
            side_effect=lambda *a, **k: events.append("browser"),
        ) as launch:
            spawn.return_value.pid = 123
            main()
        self.assertEqual(events, ["ready", "browser"])
        spawn.assert_called_once()
        launch.assert_called_once_with(["open", "http://127.0.0.1:8772"], check=True)

    def test_old_service_is_rejected_before_any_launch(self):
        old = {"mode": "shape-first/1.0"}
        with patch("sys.argv", ["start_runtime", "--workspace-only"]), patch(
            "Scripts.start_runtime.urlopen", return_value=io.BytesIO(json.dumps(old).encode())
        ), patch("Scripts.start_runtime.subprocess.Popen") as spawn, self.assertRaisesRegex(
            SystemExit, "different workspace model"
        ):
            main()
        spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
