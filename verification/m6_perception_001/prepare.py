"""Verify the reused official payload and existing read-only CPU environment."""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent


def main():
    started, cpu = time.perf_counter(), time.process_time()
    previous = HERE.parent / "m6_shape_pretrain_001"
    old_index = json.loads((previous / "SOURCE_INDEX.json").read_bytes())
    files = []
    for row in old_index["files"]:
        if row["upstream_path"].startswith("Dataset/"):
            continue
        data = Path(row["path"]).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if sha != row["sha256"] or blob != row["git_blob"]:
            raise ValueError("reused_official_source_identity_changed")
        files.append({"path": row["path"], "upstream_path": row["upstream_path"], "bytes": len(data), "sha256": sha, "git_blob": blob})
    helpers = []
    for name in ("adapter.py", "inference.py", "ENVIRONMENT.json", "RUNTIME_LOCK.json"):
        path = previous / name
        data = path.read_bytes()
        helpers.append({"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    (HERE / "SOURCE_INDEX.json").write_text(json.dumps({"cycle_id": "M6-PERCEPTION-001", "repository": "dongbo-z/Pointfilter",
          "commit": old_index["commit"], "files": files, "reused_helpers": helpers, "downloads": 0,
          "model_forwards": 0, "training": 0}, indent=2) + "\n", encoding="utf8", newline="\n")
    deps = previous / "private/deps"
    sys.path.insert(0, str(deps))
    import numpy
    import torch
    torch.set_num_threads(1)
    versions = {distribution.metadata["Name"]: distribution.version
                for distribution in importlib.metadata.distributions(path=[str(deps)])}
    versions.update(numpy=numpy.__version__, torch=str(torch.__version__))
    report = {"cycle_id": "M6-PERCEPTION-001", "python": sys.version, "python_executable": sys.executable,
              "dependency_paths": [str(deps)], "versions": versions, "torch_threads": torch.get_num_threads(),
              "CUDA": torch.cuda.is_available(), "installations": 0, "old_environment_mutated": False,
              "official_source_files_verified": len(files), "decoder_or_encoder_forwards": 0, "training": 0,
              "wall_s_before_write": time.perf_counter() - started, "CPU_s_before_write": time.process_time() - cpu,
              "cold_reused": "reused prior installation and source bytes, current interpreter startup/import timed, machine exclusivity unknown"}
    (HERE / "ENVIRONMENT.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"source_files": len(files), "versions": versions, "installation": 0}))


if __name__ == "__main__":
    main()
