"""Source-bound AST and tiny closure checks with zero actual process launches."""

import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def calls(node):
    values = set()
    for item in ast.walk(node):
        if isinstance(item, ast.Call):
            if isinstance(item.func, ast.Name):
                values.add(item.func.id)
            elif isinstance(item.func, ast.Attribute):
                values.add(item.func.attr)
    return values


def main():
    root_source = (HERE / "run_slot.py").read_bytes()
    root_sha = hashlib.sha256(root_source).hexdigest()
    tree = ast.parse(root_source)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    checks = []

    def check(name, value, detail=None):
        checks.append({"name": name, "passed": bool(value), "detail": detail})

    run = functions["run_slot"]
    assignments = {node.targets[0].id: node.value for node in run.body
                   if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}
    check("450_and_600_seconds_share_original_slot_start", all(
        isinstance(assignments[name], ast.BinOp) and isinstance(assignments[name].left, ast.Name)
        and assignments[name].left.id == "started" and isinstance(assignments[name].op, ast.Add)
        and isinstance(assignments[name].right, ast.Constant) and assignments[name].right.value == seconds * 1_000_000_000
        for name, seconds in (("consumer_deadline", 450), ("owned_deadline", 600))))
    outer_try = next(node for node in run.body if isinstance(node, ast.Try))
    actor_final = next(node for node in outer_try.finalbody if isinstance(node, ast.If)
                       and "actor" in ast.unparse(node.test))
    protected = [node for node in actor_final.body if isinstance(node, ast.Try)]
    retain_try = next(node for node in protected if "retain_children" in calls(node))
    wait_try = next(node for node in protected if "wait" in calls(node))
    check("late_retain_failure_cannot_skip_mandatory_close_wait", retain_try is not wait_try
          and bool(retain_try.handlers) and protected.index(retain_try) < protected.index(wait_try))
    source_text = root_source.decode("utf-8")
    check("actor_Popen_handle_closed_before_slot_result", source_text.index("actor._handle.Close()") < source_text.index("save(folder / 'SLOT_RESULT.json'"))
    check("publication_rechecks_owned_deadline_after_result_fsync", "owned_budget_passed=published < owned_deadline" in source_text
          and "return {**result, 'status': publication['status']" in source_text)
    check("root_uses_existing_proof_API_names", "_windows_runtime_proof" in calls(functions["retain_children"])
          and "_runtime_exit" in calls(functions["finish_held_child"]))
    proof_paths = [HERE / "reused/process_proof.py", HERE.parent / "m4_target_acquisition_002/harness/reused/process_proof.py"]
    check("root_and_runtime_proof_bytes_equal", sha(proof_paths[0]) == sha(proof_paths[1]))

    namespace = {}
    exec(compile(ast.Module(body=[functions["validate_closure"]], type_ignores=[]), "<closure-under-review>", "exec"), namespace)
    validate = namespace["validate_closure"]
    base = {"group": "N", "owned": {"actor_pid": 9}, "cleanup": {"actor_close": {
        "actor_pid": 9, "errors": [], "bridge": {"confirmed": True, "errors": []},
        "runtime": {"errors": [], "runtime": {"errors": []},
            "Blender_close": {"exit_code": 0, "process_reaped": True},
            "Blender_status": {"closed": {"poisoned": False, "initial_geometry_fingerprint": "same", "final_geometry_fingerprint": "same"},
                               "source_file_unchanged": True, "protected_files_unchanged": True}}}}}
    for group in ("N", "P"):
        value = copy.deepcopy(base)
        value["group"] = group
        if group == "P":
            value["cleanup"]["actor_close"]["runtime"].update(
                MCP_stdio_close={"confirmed": True, "exit_code": 0},
                MCP_retained_exit={"confirmed": True, "exit_code": 0, "handle_closed": True})
        try:
            validate(value)
        except BaseException as error:
            check("valid_closure_" + group, False, repr(error))
        else:
            check("valid_closure_" + group, True)
    negative = [
        ("missing_actor", ("cleanup", "actor_close"), None, "actor_closure_missing_or_failed"),
        ("wrong_actor", ("cleanup", "actor_close", "actor_pid"), 10, "actor_closure_missing_or_failed"),
        ("bridge_failure", ("cleanup", "actor_close", "bridge", "confirmed"), False, "MCP_listener_closure_failed"),
        ("runtime_error", ("cleanup", "actor_close", "runtime", "errors"), ["failure"], "runtime_closure_failed"),
        ("runtime_nested_error", ("cleanup", "actor_close", "runtime", "runtime", "errors"), ["failure"], "runtime_closure_failed"),
        ("native_nonzero", ("cleanup", "actor_close", "runtime", "Blender_close", "exit_code"), 1, "native_source_or_closure_failed"),
        ("native_poisoned", ("cleanup", "actor_close", "runtime", "Blender_status", "closed", "poisoned"), True, "native_source_or_closure_failed"),
        ("source_changed", ("cleanup", "actor_close", "runtime", "Blender_status", "closed", "final_geometry_fingerprint"), "changed", "native_source_or_closure_failed"),
        ("source_file_changed", ("cleanup", "actor_close", "runtime", "Blender_status", "source_file_unchanged"), False, "native_source_or_closure_failed"),
        ("protected_file_changed", ("cleanup", "actor_close", "runtime", "Blender_status", "protected_files_unchanged"), False, "native_source_or_closure_failed"),
    ]
    for name, path, replacement, expected in negative:
        value = copy.deepcopy(base)
        target = value
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = replacement
        try:
            validate(value)
        except BaseException as error:
            check("reject_" + name, isinstance(error, RuntimeError) and str(error) == expected, str(error))
        else:
            check("reject_" + name, False)
    value = copy.deepcopy(base)
    value["group"] = "P"
    value["cleanup"]["actor_close"]["runtime"].update(
        MCP_stdio_close={"confirmed": True, "exit_code": 0},
        MCP_retained_exit={"confirmed": True, "exit_code": 0, "handle_closed": False})
    try:
        validate(value)
    except RuntimeError as error:
        check("reject_product_handle_close_failure", str(error) == "product_stdio_or_closure_failed", str(error))
    else:
        check("reject_product_handle_close_failure", False)

    bootstrap = load("_parent_review_dependencies", HERE / "bootstrap.py")
    bootstrap.prepare_dependencies()
    smoke_assignment = next(node for node in ast.walk(functions["qualify"]) if isinstance(node, ast.Assign)
                            and any(isinstance(target, ast.Name) and target.id == "smoke" for target in node.targets))
    smoke_code = ast.literal_eval(smoke_assignment.value)["params"]["arguments"]["code"]
    for failed in (False, True):
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                exec(smoke_code, {"blender": lambda code: {"stdout": "9", "stderr": "", "error": "synthetic" if failed else None}})
            except BaseException as error:
                check("ordinary_Blender_smoke_" + ("rejects_nested_error" if failed else "valid_pass"), failed, type(error).__name__)
            else:
                check("ordinary_Blender_smoke_" + ("rejects_nested_error" if failed else "valid_pass"), not failed)
    qual = (HERE / "qual_driver.py").read_text(encoding="utf-8")
    check("qualification_binds_outer_and_inner_ids_and_requires_success", 'outer.get("request_id") != envelope["request_id"]' in qual
          and 'response.get("id") != message["id"]' in qual and '.get("isError") is not False' in qual)
    check("qualification_record_points_to_actual_filename", "QUALIFICATION_CALLS.json" in source_text
          and 'output / "QUALIFICATION_CALLS.json"' in qual)
    stdio = (HERE / "reused/stdio_checks.py").read_text(encoding="utf-8")
    native = (HERE / "reused/owned_native.py").read_text(encoding="utf-8")
    check("SPAWN_record_precedes_MCP_reader_start", stdio.index("'SPAWN.json'") < stdio.index("self.reader.start()"))
    check("SPAWN_record_precedes_Blender_READY_wait", native.index("'SPAWN.json'") < native.index("ready=self.workspace/'READY.json'"))
    check("MCP_reader_start_failure_enters_finish", "except BaseException:\n            self.finish()\n            raise" in stdio
          and "self.reader.ident is not None" in stdio)
    consumer = (HERE.parent / "m4_active_coverage_consumption_001/consumer.py").read_text(encoding="utf-8")
    check("CLI_reader_start_failure_has_started_thread_guard", "readers.append(thread);thread.start()" in consumer
          and "if thread.ident is not None:thread.join" in consumer)

    launcher = load("_parent_review_launcher", HERE / "launcher.py")
    consume, proof = launcher.consumer_adapter()
    check("accepted_CLI_loop_archive_and_matcher_reused", proof["event_loop_code_reused"] and proof["unified_archive_reused"])
    suffixes = [launcher.common_prompt(group).split(b"\n\n", 1)[1] for group in ("N", "P")]
    check("N_P_identical_current_task_and_schema_bytes", suffixes[0] == suffixes[1])
    check("P_route_requests_first_active_default_with_images", "active_observation(include_images=true)" in launcher.PREFIXES["P"]
          and "response_detail" not in (HERE / "bridge.py").read_text(encoding="utf-8"))
    check("reviewed_root_source_stable_during_checks", sha(HERE / "run_slot.py") == root_sha)
    pinned = ["run_slot.py", "launcher.py", "bridge.py", "native_tools.py", "bootstrap.py", "owned_runtime.py",
              "qual_driver.py", "reused/stdio_checks.py", "reused/owned_native.py", "reused/process_proof.py",
              "inputs/COMMON_TASK.txt", "inputs/ANSWER_SCHEMA.json", "SHARED_DEPENDENCY.json", "CLI_PREFLIGHT.json"]
    result = {"schema": "root-parent-static-review-v1", "passed_checked_scope": all(row["passed"] for row in checks),
        "check_count": len(checks), "passed_count": sum(row["passed"] for row in checks), "checks": checks,
        "source_pins": {str(HERE / name): sha(HERE / name) for name in pinned},
        "author_association": "Reviewer authored bridge/native_tools/bootstrap/launcher. Root authored run_slot. This is an independent parent-control review with author association disclosed.",
        "preflight": "ROOT_PARENT_MOCK_PREFLIGHT_FAILURE.json and root_parent_pure_01 preserve the abandoned full-parent synthetic runner.",
        "actual_Blender_starts": 0, "actual_CLI_calls": 0, "actual_model_calls": 0, "actual_rasters": 0,
        "scope": "Static source/API/deadline/order checks and extracted closure/smoke function counterexamples. Actual Win32 proof, thread failure injection, live source stability, image delivery and closure remain qualification work."}
    with (HERE / "ROOT_PARENT_STATIC_REVIEW.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": result["passed_checked_scope"], "passed_count": result["passed_count"], "check_count": len(checks),
                      "failures": [row for row in checks if not row["passed"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
