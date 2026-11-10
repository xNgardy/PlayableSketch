import argparse
import json
from pathlib import Path
import subprocess
import urllib.request
from .dino_model import ROOT, LOCK, sha, verify_dependencies


def setup(download=False):
    lock = json.loads(LOCK.read_text())
    repo = ROOT / lock["source_directory"]
    checkpoint = ROOT / lock["checkpoint_path"]
    if download:
        repo.parent.mkdir(parents=True, exist_ok=True)
        if not repo.exists():
            subprocess.run(
                ["git", "clone", "--no-checkout", lock["repository_url"], str(repo)], check=True
            )
            subprocess.run(
                ["git", "-C", str(repo), "checkout", "--detach", lock["revision"]], check=True
            )
        if not checkpoint.exists():
            temporary = checkpoint.with_suffix(".download")
            try:
                urllib.request.urlretrieve(lock["checkpoint_url"], temporary)
                if sha(temporary) != lock["checkpoint_sha256"]:
                    raise ValueError("Downloaded DINO checksum mismatch")
                temporary.replace(checkpoint)
            finally:
                if temporary.exists():
                    temporary.unlink()
    verify_dependencies()
    return {
        "model": lock["model"],
        "revision": lock["revision"],
        "checkpoint_sha256": sha(checkpoint),
        "license": lock["license"],
        "offline_verification_passed": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Explicit installation/verification of the pinned Apache-2.0 DINO dependency."
    )
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    print(json.dumps(setup(args.download), indent=2))
