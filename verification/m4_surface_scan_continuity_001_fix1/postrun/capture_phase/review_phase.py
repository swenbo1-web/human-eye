"""Publish phase-aware diagnosis of the failed FIX1 reader without live work."""

import ast
import copy
import difflib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback
import types


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import read_capture_candidate as candidate
from test_capture_phase import actual_case, actual_runner, before_response_phase

check = candidate.qualification
ROOT = check.ROOT
BATCH = HERE.parents[1]
CELL = BATCH / "episodes/C"
WORKER = ROOT / "verification/m4_surface_scan_001_opt1/engineering/pose_native_metered.py"
METER = WORKER.with_name("wire_meter.py")


def main():
    began = time.perf_counter_ns()
    protected = {path: check.digest(path.read_bytes()) for folder in (BATCH / "qualification", BATCH / "episodes")
                 for path in folder.rglob("*") if path.is_file()}
    row, source, _, host = actual_case()
    workspace = CELL / "owner/native"
    old_error = None
    with before_response_phase(workspace, host[0]["sequence"]) as old_denied:
        try:
            check.read_capture(workspace, host[0])
        except FileNotFoundError as error:
            old_error = str(error)
    assert old_error is not None and len(old_denied) == 1
    assert "WIRE" in old_denied[0]
    proxy = types.SimpleNamespace(read_capture=candidate.read_capture, verify_c_turn=check.verify_c_turn)
    with before_response_phase(workspace, host[0]["sequence"]) as new_denied:
        capture = candidate.read_capture(workspace, host[0])
        facts = actual_runner().verify_business(copy.deepcopy(row), CELL, source, proxy)
    assert new_denied == []
    assert (facts["matches"], facts["new_kernel_calls"], facts["actual_host_capture_count"]) == (71, 112, 1)
    assert facts["capture_report"]["wire_sources"] == []
    archived = check.read_capture(workspace, host[0])
    for field in ("sequence", "script_sha256", "delta", "retained_resources", "resource_origins"):
        assert capture[field] == archived[field]
    number = host[0]["sequence"]
    call = workspace / ("call_" + str(number))
    request = json.loads((workspace / ("WIRE/%03d/REQUEST.bin" % number)).read_bytes())
    response = json.loads((workspace / ("WIRE/%03d/RESPONSE.bin" % number)).read_bytes())
    code = candidate.logical_bytes((call / "SCRIPT.py").read_bytes(), expected_sha=host[0]["script_sha256"])
    stdout = candidate.logical_bytes((call / "stdout.txt").read_bytes(), expected_size=host[0]["stdout_bytes"])
    assert code == request["params"]["code"].encode("utf8")
    assert stdout == response["result"]["result"].encode("utf8")
    episode = json.loads((CELL / "RESULTS.json").read_bytes())
    assert episode["passed_before_publication"] is False
    assert episode["execution_counts"] == {"planned": 3, "attempted": 1, "completed": 0, "failed": 1, "not_run": 2}
    assert all(check.digest(path.read_bytes()) == expected for path, expected in protected.items())

    worker_lines = WORKER.read_text(encoding="utf8").splitlines()
    def line_number(token):
        return next(index for index, line in enumerate(worker_lines, 1) if token in line)
    order = {"script_file_write_close": line_number("call/'SCRIPT.py'"),
             "stdout_stderr_write_close": line_number("call/'stdout.txt'"),
             "terminal_guard_event": line_number("event.update(script_sha256"),
             "event_append_fsync": line_number("event['elapsed_ns']="),
             "response_sendall": line_number("connection.sendall(wire)"),
             "wire_flush_after_worker_loop": line_number("meter.flush(workspace)")}
    assert list(order.values()) == sorted(order.values())
    worker_source = WORKER.read_text(encoding="utf8")
    meter_source = METER.read_text(encoding="utf8")
    finish = next(node for node in ast.parse(meter_source).body if isinstance(node, ast.FunctionDef) and node.name == "finish_rpc")
    finish_text = ast.get_source_segment(meter_source, finish)
    assert "flush(" not in finish_text and "write" not in finish_text
    assert "os.fsync(stream.fileno())" in worker_source

    old_text = check.SOURCE.read_text(encoding="utf8") if hasattr(check, "SOURCE") else (check.HERE / "verify_continuity.py").read_text(encoding="utf8")
    old_reader = next(node for node in ast.parse(old_text).body if isinstance(node, ast.FunctionDef) and node.name == "read_capture")
    new_text = (HERE / "read_capture_candidate.py").read_text(encoding="utf8")
    proposed = "\n\n".join(ast.get_source_segment(new_text, node) for node in ast.parse(new_text).body
                           if isinstance(node, ast.FunctionDef) and node.name in ("logical_bytes", "read_capture"))
    proposed = proposed.replace("qualification.", "")
    old_reader_text = ast.get_source_segment(old_text, old_reader)
    difference = difflib.unified_diff((old_reader_text + "\n").splitlines(keepends=True),
                                      (proposed + "\n").splitlines(keepends=True),
                                      fromfile="frozen_qualification/read_capture", tofile="unapplied_reader_only_proposal", n=0)
    (HERE / "MINIMAL_READER.diff").write_text("".join(difference), encoding="utf8", newline="\n")
    inputs = [WORKER, METER, check.HERE / "verify_continuity.py", check.HERE.parent / "engineering/run_candidate.py",
              HERE / "read_capture_candidate.py", HERE / "test_capture_phase.py"]
    inputs += [path for path in CELL.rglob("*") if path.is_file()]
    result = {"schema": "fix1_capture_phase_diagnosis_v1", "passed_offline": True,
              "original_online_error": row["errors"], "reproduced_phase_error": old_error,
              "old_reader_denied_paths": old_denied, "candidate_denied_paths": new_denied,
              "candidate_installed_or_applied": False, "active_fact_validator_reused": str(check.HERE / "verify_continuity.py"),
              "source_publication_order": order, "worker_sha256": check.digest(WORKER.read_bytes()),
              "meter_sha256": check.digest(METER.read_bytes()), "finish_rpc_has_no_disk_publication": True,
              "candidate_capture": capture, "offline_fact_report": facts,
              "post_close_wire_crosscheck": {"logical_script_bytes_equal": True, "logical_stdout_bytes_equal": True,
                                              "parsed_capture_equal": True, "retained_resource_history_equal": True,
                                              "scope": "post-close crosscheck only; it was unavailable at original online validation"},
              "original_episode_pass": False, "original_counts": episode["execution_counts"],
              "protected_original_files_unchanged": len(protected), "new_live_Blender_API_calls": 0,
              "elapsed_before_publication_ns": time.perf_counter_ns() - began,
              "limitations": ["The candidate is uninstalled and has no new live acceptance.",
                              "Worker output and terminal event do not attest response send completion.",
                              "WIRE transport confirmation remains a post-close audit step.",
                              "Original C REPEAT and EDIT were not run; history tests replay old qualified records.",
                              "Missing rich source metadata, actual model continuity and provider usage remain unmeasured."],
              "inputs": [{"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
                          "sha256": check.digest(path.read_bytes())} for path in sorted(set(inputs))]}
    (HERE / "REVIEW.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"phase_error_reproduced": True, "candidate_offline_pass": True, "matches": 71, "kernel": 112,
                      "wire_or_closed_reads_during_candidate_validation": len(new_denied),
                      "post_close_wire_equal": True, "original_C_pass": False, "new_live_calls": 0}))


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        number = len(list(HERE.glob("REVIEW_FAILURE_*.json"))) + 1
        (HERE / ("REVIEW_FAILURE_%02d.json" % number)).write_text(
            json.dumps({"scope": "offline capture-phase review failure", "traceback": traceback.format_exc(), "new_live_calls": 0}, indent=2) + "\n",
            encoding="utf8", newline="\n")
        raise
