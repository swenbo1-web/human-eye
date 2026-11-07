"""Hash and parse local source as inert text, without importing product modules."""
import ast
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
BASELINE = "3f1d9d9e46d51643b67fdebac090cf9b825a15c0"
EXPECTED_SOURCE = "2ef16a5e5b316453fff343ab8d2ff36b7b7c82113580137094f18896f1509664"


def run():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert subprocess.run(["git", "merge-base", "--is-ancestor", BASELINE, head], cwd=ROOT, check=False).returncode == 0
    identity = json.loads((ROOT / "verification/m4_capture_opt_001/B_IDENTITY.json").read_bytes())
    assert len(identity["files"]) == 131 and identity["source_sha256"] == EXPECTED_SOURCE
    mismatches = []
    for record in identity["files"]:
        path = (ROOT / record["path"]).resolve()
        assert path.is_relative_to(ROOT)
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            mismatches.append(record["path"])
    constants = {}
    for node in ast.parse((ROOT / "human_eye_plugin/runtime_identity.py").read_bytes()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ("BASE_VERSION", "IMPLEMENTATION_REVISION"):
                constants[node.targets[0].id] = ast.literal_eval(node.value)
    payload = {"base_version": constants["BASE_VERSION"],
               "implementation_revision": constants["IMPLEMENTATION_REVISION"], "files": identity["files"]}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    assert not mismatches and digest == EXPECTED_SOURCE
    symbols = {}
    for filename in ("human_eye_plugin/blender_host.py", "human_eye_plugin/surface_proximity.py"):
        tree = ast.parse((ROOT / filename).read_bytes())
        names = {"_acquisition_bounds", "_acquisition_witness", "_depsgraph", "_objects", "_scale",
                 "_capture", "capture_nearest_candidates", "_admit", "_integer_frame"}
        symbols[filename] = [{"name": node.name, "line": node.lineno, "end_line": node.end_lineno}
                             for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in names]
    assignment = Path("D:/hefe/verification/fixes/20261107_nearest_contract/M2_ASSIGNMENT.md")
    assignment_sha = hashlib.sha256(assignment.read_bytes()).hexdigest()
    assert assignment_sha == "c36cfbe03e986adf8584a5d4768207ff57a4e31ad9204f09b37d2e5c875bdb62"
    result = {"captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "baseline_head": BASELINE, "observed_git_head": head, "source_count": 131, "source_sha256": digest,
              "all_131_files_match_frozen_identity": True, "assignment_sha256": assignment_sha,
              "host_sha256": hashlib.sha256((ROOT / "human_eye_plugin/blender_host.py").read_bytes()).hexdigest(),
              "product_imports_or_execution": 0, "blender_runs": 0,
              "performance_runs": 0, "subagents": 0, "model_consumers": 0,
              "source_locations": symbols}
    (OUT / "LOCAL_SOURCE_AUDIT.json").write_bytes((json.dumps(result, indent=2) + "\n").encode())
    print(json.dumps({key: value for key, value in result.items() if key != "source_locations"}))


if __name__ == "__main__":
    run()
