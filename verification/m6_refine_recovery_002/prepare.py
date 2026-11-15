"""Bind the recovery task to fixed historical bytes and unchanged source models."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.parent / "m6_refine_001"
BASELINE = "154ff39a9a0fa0ed25c59aec282f0bbd315a8a15"
CONTRACT = "ae03bf592f9b28e5a5309d79f3cb18c3d2cae65d"


def identity(path):
    path = Path(path)
    raw = path.read_bytes()
    return dict(path=str(path.resolve()), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")


def main():
    started, cpu = time.perf_counter(), time.process_time()
    archive = HERE / "private/source"
    archive.mkdir(parents=True, exist_ok=False)
    for source, target in (("docs/M6_REFINE_RECOVERY_002_TASK.md", "CONTRACT.md"), ("docs/M6_REFINE_001_REVIEW.md", "PRIOR_REVIEW.md")):
        raw = subprocess.check_output(["git", "-C", "C:/Users/Administrator/.codex/worktrees/1212/hefe", "show", CONTRACT + ":" + source])
        (HERE / target).write_bytes(raw)
    raw = subprocess.check_output(["git", "show", BASELINE + ":verification/m6_refine_001/session_api.py"], cwd=ROOT)
    (archive / "session_api_before.py").write_bytes(raw)
    manifest = json.loads((OLD / "MANIFEST.json").read_bytes())
    matches, changed = [], []
    for row in manifest["files"]:
        actual = identity(OLD / row["path"])
        (matches if actual["sha256"] == row["sha256"] else changed).append(dict(path=row["path"], expected_sha256=row["sha256"], actual=actual))
    if [row["path"] for row in changed] != ["session_api.py"]:
        raise AssertionError("historical_evidence_changed_outside_authorized_source")
    (archive / "session_api_after.py").write_bytes((OLD / "session_api.py").read_bytes())
    cases = []
    for path in sorted((OLD / "private/sessions").glob("v[12]_*/session.json")):
        state = json.loads(path.read_bytes())
        cases.append(dict(session=identity(path), blend=identity(state["current_blend"]),
            version=state["version"], operations=state["operations"], initial=identity(state["initial_npz"]), current=identity(state["current_npz"])))
    write(HERE / "private/source/HISTORICAL_CHECKS.json", dict(matches=matches, changed=changed, six_sessions=cases))
    write(HERE / "SOURCE_BINDING.json", dict(cycle_id="M6-REFINE-RECOVERY-002", baseline_commit=BASELINE,
        contract_commit=CONTRACT, allowed_runtime_change="verification/m6_refine_001/session_api.py",
        historical_manifest=identity(OLD / "MANIFEST.json"), historical_members=len(manifest["files"]), unchanged_members=len(matches),
        expected_source_change=changed, old_source=identity(archive / "session_api_before.py"), current_source=identity(archive / "session_api_after.py"),
        six_saved_models=len(cases), authority=dict(source_thread="01a1d986-24a4-73f1-9689-6845d1f01ef3", actual_human_turn="01a1dfd9-ba09-7a11-8b02-cf3bf79a7d65", actual_human_message="01a1dfd9-bef1-7291-b17f-7bbe7e9b2455", text="为什么不继续推进"),
        limits=dict(Pro_calls=0, training=0, images=0, numerical_Blender_seconds=1800, threads=1),
        wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu))
    print(len(matches), "historical members unchanged; one authorized source change; six saved models bound")


if __name__ == "__main__":
    main()
