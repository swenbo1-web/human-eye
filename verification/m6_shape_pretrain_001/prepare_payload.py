"""Verify and copy fixed upstream bytes, then prepare private-only dependencies."""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
PLANNING = Path("C:/Users/Administrator/.codex/worktrees/1212/hefe/verification/m6_shape_reselect_001_plan")
UPSTREAM = "6e0ec1eac59ca9f81ee9ca6751c5b3f25effeda2"


def main():
    started, cpu = time.perf_counter(), time.process_time()
    destination = HERE / "private/pointfilter"
    destination.mkdir(parents=True, exist_ok=True)
    tree = {row["path"]: row for row in json.loads((PLANNING / "UPSTREAM_TREE.json").read_bytes())["files"]}
    checks = json.loads((PLANNING / "SOURCE_CHECK.json").read_bytes())["checked"]
    checks.append({"path": "Summary/pre_train_model/model_full_ae.pth", "sha256":
                   "86600e6d57fab7887fbda0cf54292578a52d956c36766a130d1e32a475d18cee"})
    records = []
    for row in checks:
        path = destination / Path(row["path"]).name
        data = (PLANNING / "private/pointfilter" / path.name).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if sha != row["sha256"] or blob != tree[row["path"]]["sha"]:
            raise ValueError("fixed_upstream_identity_mismatch_" + row["path"])
        path.write_bytes(data)
        records.append({"upstream_path": row["path"], "path": str(path), "bytes": len(data),
                        "sha256": sha, "git_blob": blob, "acquisition": "verified_planning_cache_copy"})
    source_wall = time.perf_counter() - started
    download_start, download_cpu = time.perf_counter(), time.process_time()
    for name in ("Tetrahedron.npy", "Tetrahedron_0.005.npy"):
        relative = "Dataset/Test/" + name
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        url = "https://raw.githubusercontent.com/dongbo-z/Pointfilter/" + UPSTREAM + "/" + relative
        data = urllib.request.urlopen(url, timeout=120).read()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if blob != tree[relative]["sha"]:
            raise ValueError("official_test_blob_mismatch_" + name)
        path.write_bytes(data)
        records.append({"upstream_path": relative, "path": str(path), "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(), "git_blob": blob,
                        "acquisition": "fixed_official_raw_URL", "url": url})
    download_wall, download_CPU = time.perf_counter() - download_start, time.process_time() - download_cpu
    source_report = {"cycle_id": "M6-SHAPE-PRETRAIN-001", "repository": "dongbo-z/Pointfilter",
                     "commit": UPSTREAM, "files": records, "source_cache_copy_wall_s": source_wall,
                     "official_test_download_wall_s": download_wall, "official_test_download_CPU_s": download_CPU,
                     "arrays_deserialized": 0, "model_forwards": 0, "training": 0,
                     "wall_s_before_write": time.perf_counter() - started, "CPU_s_before_write": time.process_time() - cpu}
    (HERE / "SOURCE_INDEX.json").write_text(json.dumps(source_report, indent=2) + "\n", encoding="utf8", newline="\n")
    dependency_start, dependency_cpu = time.perf_counter(), time.process_time()
    dependencies = HERE / "private/deps"
    dependencies.mkdir(parents=True, exist_ok=True)
    pins = ["scipy==1.15.3", "scikit-learn==1.7.2", "joblib==1.5.2", "threadpoolctl==3.6.0"]
    command = [sys.executable, "-B", "-m", "pip", "install", "--disable-pip-version-check", "--no-deps",
               "--only-binary=:all:", "--target", str(dependencies), *pins]
    subprocess.run(command, check=True)
    site = HERE.parent / "m6_shape_train_001/private/venv/Lib/site-packages"
    sys.path.insert(0, str(dependencies))
    import numpy
    import scipy
    import sklearn
    import torch
    torch.set_num_threads(1)
    report = {"cycle_id": "M6-SHAPE-PRETRAIN-001", "python": sys.version, "python_executable": sys.executable,
              "dependency_paths": [str(dependencies)], "existing_Torch_site_readonly": str(site),
              "versions": {"numpy": numpy.__version__, "torch": str(torch.__version__),
                           "scipy": scipy.__version__, "scikit-learn": sklearn.__version__,
                           "joblib": importlib.metadata.version("joblib"), "threadpoolctl": importlib.metadata.version("threadpoolctl")},
              "installed_private_pins": pins, "installation_command": command,
              "torch_threads": torch.get_num_threads(), "CUDA": torch.cuda.is_available(),
              "dependency_install_and_import_wall_s": time.perf_counter() - dependency_start,
              "parent_CPU_s_excluding_pip": time.process_time() - dependency_cpu,
              "whole_preparation_wall_s_before_write": time.perf_counter() - started,
              "whole_preparation_parent_CPU_s_before_write": time.process_time() - cpu,
              "cold_reused": "private target first install, old Torch/NumPy installation read-only; download/pip subprocess in enclosing tree ledger",
              "old_environment_mutated": False, "model_forwards": 0}
    (HERE / "ENVIRONMENT.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"source_files": len(records), "versions": report["versions"]}))


if __name__ == "__main__":
    main()
