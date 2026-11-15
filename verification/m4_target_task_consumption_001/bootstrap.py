"""Load the fixed shared dependencies before a root-selected local worker."""

import hashlib
import json
from pathlib import Path
import runpy
import sys


HERE = Path(__file__).resolve().parent


def prepare_dependencies():
    manifest_path = HERE / "SHARED_DEPENDENCY.json"
    manifest = json.loads(manifest_path.read_bytes())
    for source, expected in manifest["files_sha256"].items():
        if hashlib.sha256(Path(source).read_bytes()).hexdigest() != expected:
            raise ValueError("shared_dependency_changed:" + source)
    roots = ["D:/he_anchor_001/venv/Lib/site-packages", manifest["dependency_root"]]
    for root in reversed(roots):
        sys.path.insert(0, root)
    return {"manifest": str(manifest_path),
            "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "roots": roots, "product_high_level_imported": False}


def main():
    target = Path(sys.argv[1]).resolve()
    if target.parent != HERE or target.suffix != ".py":
        raise ValueError("registered_local_worker_only")
    binding = prepare_dependencies()
    sys.argv = [str(target), *sys.argv[2:]]
    runpy.run_path(str(target), run_name="__main__", init_globals={"SHARED_DEPENDENCY_BINDING": binding})


if __name__ == "__main__":
    main()
