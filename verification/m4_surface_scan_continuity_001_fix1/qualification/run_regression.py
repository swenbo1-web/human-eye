"""Publish offline original-owner regression through the FIX1 runner entry."""

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import traceback


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / "verification/m4_surface_scan_continuity_001"
CELL = OLD / "episodes/C"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    started = time.perf_counter_ns()
    qualification = load("_fix1_active_qualification_regression", HERE / "verify_continuity.py")
    runner_path = HERE.parent / "engineering/run_candidate.py"
    runner = load("_fix1_actual_runner_regression", runner_path)
    protected = {path: digest(path.read_bytes()) for path in OLD.rglob("*") if path.is_file()}
    row = json.loads((CELL / "TURN_BASE.json").read_bytes())
    reference = qualification.fixed_json(qualification.QUAL / "BASE_SNAPSHOT.json", qualification.SNAPSHOT_SHA["BASE"])
    initial = json.loads((CELL / "owner/INITIAL.json").read_bytes())
    old_error = None
    try:
        qualification.previous_verifier().bind_snapshot(initial, reference)
    except AssertionError as error:
        old_error = str(error)
    assert old_error == "actual geometry or source fields differ from qualified state"
    reports = []
    for name in ("INITIAL.json", "FINAL.json"):
        source = json.loads((CELL / "owner" / name).read_bytes())
        result = runner.verify_business(copy.deepcopy(row), CELL, source, qualification)
        assert result["passed"] and result["matches"] == 71 and result["new_kernel_calls"] == 112
        assert result["source_report"]["rich_source_metadata_verified"] is False
        reports.append({"source_file": name, "qualification": result})
    episode = json.loads((CELL / "RESULTS.json").read_bytes())
    assert episode["passed_before_publication"] is False
    assert episode["execution_counts"] == {"planned": 3, "attempted": 1, "completed": 0, "failed": 1, "not_run": 2}
    assert all(digest(path.read_bytes()) == expected for path, expected in protected.items())
    runner_text = runner_path.read_text(encoding="utf8")
    entry = next(node for node in ast.parse(runner_text).body if isinstance(node, ast.FunctionDef) and node.name == "verify_business")
    source_paths = [HERE / "verify_continuity.py", HERE / "test_verify_continuity.py", runner_path,
                    qualification.PREVIOUS, qualification.QUAL / "BASE_SNAPSHOT.json", qualification.QUAL / "BASE_TRUTH.json",
                    qualification.QUAL / "EDIT_SNAPSHOT.json", qualification.QUAL / "EDIT_TRUTH.json"]
    source_paths += [path for path in CELL.rglob("*") if path.is_file()]
    inventory = [{"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
                  "sha256": digest(path.read_bytes())} for path in sorted(set(source_paths))]
    result = {"schema": "fix1_actual_owner_runner_qualification_regression_v1", "passed": True,
              "old_rich_binder_error_reproduced": old_error,
              "active_qualification_path": (HERE / "verify_continuity.py").relative_to(ROOT).as_posix(),
              "active_verify_c_turn_definitions": sum(isinstance(node, ast.FunctionDef) and node.name == "verify_c_turn"
                                                       for node in ast.parse((HERE / "verify_continuity.py").read_text(encoding="utf8")).body),
              "actual_runner_entry": runner_path.relative_to(ROOT).as_posix() + ".verify_business",
              "actual_runner_entry_sha256": digest(ast.get_source_segment(runner_text, entry).encode("utf8")),
              "reports": reports, "original_C_episode_pass": False, "original_C_counts": episode["execution_counts"],
              "original_files_unchanged": len(protected), "new_model_Blender_API_calls": 0,
              "usage_scope": "No provider or model consumer; offline records only",
              "elapsed_before_publication_ns": time.perf_counter_ns() - started, "sources": inventory}
    assert result["active_verify_c_turn_definitions"] == 1
    (HERE / "ACTUAL_OWNER_REGRESSION.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"passed": True, "actual_runner_entry": result["actual_runner_entry"], "matches": 71,
                      "kernels": 112, "old_error_retained": True, "original_files_unchanged": len(protected),
                      "new_live_calls": 0}))


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        number = len(list(HERE.glob("REGRESSION_FAILURE_*.json"))) + 1
        (HERE / ("REGRESSION_FAILURE_%02d.json" % number)).write_text(
            json.dumps({"scope": "offline FIX1 regression failure", "traceback": traceback.format_exc(), "live_calls": 0}, indent=2) + "\n",
            encoding="utf8", newline="\n")
        raise
