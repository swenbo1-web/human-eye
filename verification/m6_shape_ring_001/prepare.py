"""Bind existing private CPU dependencies without changing their installations."""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent


def main():
    started, cpu = time.perf_counter(), time.process_time()
    dependencies = HERE.parent / "m6_shape_pretrain_001/private/deps"
    sys.path.insert(0, str(dependencies))
    import numpy
    files = []
    for path in (HERE.parent / "m6_shape_pretrain_001/RUNTIME_LOCK.json",
                 HERE.parent / "m6_shape_pretrain_001/ENVIRONMENT.json", Path(numpy.__file__)):
        data = path.read_bytes()
        files.append({"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    versions = {distribution.metadata["Name"]: distribution.version
                for distribution in importlib.metadata.distributions(path=[str(dependencies)])}
    versions["numpy"] = numpy.__version__
    report = {"cycle_id": "M6-SHAPE-RING-001", "status": "bound_existing_readonly_CPU_environment",
              "python": sys.version, "python_executable": sys.executable,
              "dependency_paths": [str(dependencies)], "versions": versions,
              "read_only_runtime_identities": files, "threads": 1, "installation": 0,
              "Torch_imports_or_forwards": 0, "training": 0,
              "matplotlib_available": importlib.util.find_spec("matplotlib") is not None,
              "wall_s_before_write": time.perf_counter() - started,
              "CPU_s_before_write": time.process_time() - cpu,
              "cold_reused": "existing old NumPy and previous private dependencies, no new environment installation"}
    (HERE / "ENVIRONMENT.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"versions": versions, "installation": 0}))


if __name__ == "__main__":
    main()
