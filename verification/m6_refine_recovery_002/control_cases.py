"""Run fixed old and current public readback control flow on isolated fixtures."""

from contextlib import contextmanager
import argparse
import ast
import copy
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
import uuid

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
API_PATH = REPOSITORY / "verification/m6_refine_001/session_api.py"
OLD_COMMIT = "154ff39a9a0fa0ed25c59aec282f0bbd315a8a15"


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".next")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    temporary.replace(path)


def identity(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def label_for(directory, number):
    return "q" + hashlib.sha256((directory.name + ":" + str(number)).encode()).hexdigest()[:16]


class Harness:
    def __init__(self, root, source, existing=False):
        self.root, self.source = Path(root), Path(source)
        self.directory = self.root / "private/sessions/s"
        self.calls, self.errors = [], []
        self.failure = None
        self.pause = None
        if not existing:
            self.directory.mkdir(parents=True, exist_ok=False)
            self.blend = self.directory / "saved.blend"
            self.blend.write_bytes(b"isolated synthetic saved blend identity fixture\n")
            write(self.directory / "session.json", dict(version=7, operations=[dict(operation_id="already_saved", version=7)],
                pending=None, current_blend=str(self.blend)))
        else:
            self.blend = Path(read(self.directory / "session.json")["current_blend"])
        self.before = read(self.directory / "session.json")
        self.blend_before = identity(self.blend)
        namespace = dict(Path=Path, os=os, msvcrt=msvcrt, contextmanager=contextmanager,
            hashlib=hashlib, HERE=self.root, read=read, write=write, identity=identity,
            short_quality=lambda quality: quality, read_actual=self.controlled_reader)
        tree = ast.parse(self.source.read_text(encoding="utf8"))
        names = {"session_lock", "state_path", "save_readback"}
        nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
        if {node.name for node in nodes} != names:
            raise ValueError("required_fixed_source_functions_missing")
        module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
        exec(compile(module, str(self.source), "exec"), namespace)
        self.function = namespace["save_readback"]
        self.lock = namespace["session_lock"]

    def controlled_reader(self, directory, state, blend, label, output):
        row = dict(label=label, output=str(output), state_at_reader_launch=read(directory / "session.json"),
            output_existed_before=output.exists(), injected_failure=self.failure)
        self.calls.append(row)
        job = self.root / "private/jobs" / label
        job.mkdir(parents=True, exist_ok=False)
        if self.pause is not None:
            entered, resume = self.pause
            entered.set()
            if not resume.wait(10):
                raise TimeoutError("controlled_reader_pause_expired")
        if self.failure == "before_output":
            self.failure = None
            raise RuntimeError("injected_reader_failure_before_output")
        output.mkdir(parents=True, exist_ok=False)
        (output / "readback.npz").write_bytes(b"controlled geometry packet, no Blender launched\n")
        write(output / "QUALITY.json", dict(status="controlled_reader_fixture"))
        if self.failure == "after_output":
            self.failure = None
            raise RuntimeError("injected_reader_receipt_missing_after_output")
        return dict(status="controlled_reader"), dict(status="controlled_reader_fixture")

    def call(self):
        try:
            return dict(result=self.function(self.directory), error=None)
        except Exception as error:
            captured = dict(type=type(error).__name__, message=str(error))
            self.errors.append(captured)
            return dict(result=None, error=captured)

    def state_preserved(self):
        current = read(self.directory / "session.json")
        initial = copy.deepcopy(self.before)
        current.pop("next_readback_attempt", None)
        initial.pop("next_readback_attempt", None)
        return current == initial and identity(self.blend) == self.blend_before

    def evidence(self):
        return dict(source=identity(self.source), before=self.before, after=read(self.directory / "session.json"),
            saved_blend_before=self.blend_before, saved_blend_after=identity(self.blend), calls=self.calls, errors=self.errors)


def exercise(version, version_root, source):
    checks, cases = {}, {}

    def finish(tag, harness):
        checks[version + "_" + tag + "_saved_state_preserved"] = harness.state_preserved()
        cases[tag] = harness.evidence()
        write(version_root / tag / "CASE.json", cases[tag])

    normal = Harness(version_root / "n", source)
    responses = [normal.call(), normal.call()]
    checks[version + "_normal_two_successes"] = all(row["error"] is None for row in responses)
    checks[version + "_normal_unique_labels_and_outputs"] = len({row["label"] for row in normal.calls}) == 2 and len({row["output"] for row in normal.calls}) == 2
    required = {"version", "saved_blend", "readback", "independently_reopened", "quality", "quality_record", "reader_job"}
    checks[version + "_public_result_fields_preserved"] = all(set(row["result"]) == required for row in responses)
    if version == "new":
        checks["new_normal_counter_persisted_before_each_reader"] = [row["state_at_reader_launch"]["next_readback_attempt"] for row in normal.calls] == [2, 3]
    finish("n", normal)

    before_output = Harness(version_root / "p", source)
    before_output.failure = "before_output"
    responses = [before_output.call(), before_output.call()]
    checks[version + "_before_output_first_failure_retained"] = responses[0]["error"]["type"] == "RuntimeError"
    if version == "old":
        checks["old_before_output_counterexample_reproduced"] = responses[1]["error"]["type"] == "FileExistsError" and before_output.calls[0]["label"] == before_output.calls[1]["label"] and before_output.calls[0]["output"] == before_output.calls[1]["output"]
    else:
        checks["new_before_output_retry_recovers_new_identity"] = responses[1]["error"] is None and before_output.calls[0]["label"] != before_output.calls[1]["label"] and before_output.calls[0]["output"] != before_output.calls[1]["output"]
        checks["new_before_output_attempt_persisted_on_failure"] = before_output.calls[0]["state_at_reader_launch"]["next_readback_attempt"] == 2
    finish("p", before_output)

    after_output = Harness(version_root / "o", source)
    after_output.failure = "after_output"
    responses = [after_output.call(), after_output.call()]
    checks[version + "_after_output_missing_receipt_retained"] = responses[0]["error"]["type"] == "RuntimeError" and Path(after_output.calls[0]["output"], "readback.npz").exists()
    checks[version + "_after_output_retry_new_identity"] = responses[1]["error"] is None and len({row["label"] for row in after_output.calls}) == 2
    checks[version + "_after_output_first_record_preserved"] = not Path(after_output.calls[0]["output"], "READBACK.json").exists() and Path(after_output.calls[1]["output"], "READBACK.json").exists()
    finish("o", after_output)

    legacy = Harness(version_root / "l", source)
    (legacy.root / "private/jobs" / label_for(legacy.directory, 1)).mkdir(parents=True)
    response = legacy.call()
    if version == "old":
        checks["old_legacy_job_only_counterexample_reproduced"] = response["error"]["type"] == "FileExistsError"
    else:
        checks["new_legacy_job_only_without_counter_recovers"] = response["error"] is None and legacy.calls[0]["label"] == label_for(legacy.directory, 2)
        checks["new_legacy_job_only_counter_is_three"] = read(legacy.directory / "session.json")["next_readback_attempt"] == 3
    finish("l", legacy)

    sparse = Harness(version_root / "s", source)
    for number in (1, 3):
        output = sparse.directory / "readbacks" / str(number).zfill(3)
        output.mkdir(parents=True)
        (output / "existing.txt").write_bytes(b"existing output must remain unchanged\n")
    previous_files = {str(path):identity(path) for path in (sparse.directory / "readbacks").rglob("existing.txt")}
    response = sparse.call()
    if version == "old":
        checks["old_sparse_output_count_collision_reproduced"] = response["error"]["type"] == "FileExistsError"
    else:
        checks["new_sparse_output_ids_skip_used_and_fill_available"] = response["error"] is None and sparse.calls[0]["output"].endswith("002")
    checks[version + "_existing_output_bytes_preserved"] = all(identity(path) == value for path, value in previous_files.items())
    finish("s", sparse)

    counter = Harness(version_root / "c", source)
    state = read(counter.directory / "session.json")
    state["next_readback_attempt"] = 4
    write(counter.directory / "session.json", state)
    counter.before = copy.deepcopy(state)
    (counter.root / "private/jobs" / label_for(counter.directory, 4)).mkdir(parents=True)
    (counter.directory / "readbacks/006").mkdir(parents=True)
    responses = [counter.call(), counter.call()]
    checks[version + "_counter_collision_calls_return"] = all(response["error"] is None for response in responses)
    if version == "new":
        checks["new_existing_counter_skips_reserved_job_and_output"] = [row["label"] for row in counter.calls] == [label_for(counter.directory, 5), label_for(counter.directory, 7)]
        checks["new_existing_counter_advances_monotonically"] = read(counter.directory / "session.json")["next_readback_attempt"] == 8
    finish("c", counter)

    pending = Harness(version_root / "g", source)
    state = read(pending.directory / "session.json")
    state["pending"] = dict(operation_id="unfinished_saved_edit")
    write(pending.directory / "session.json", state)
    pending.before = copy.deepcopy(state)
    bytes_before = (pending.directory / "session.json").read_bytes()
    response = pending.call()
    checks[version + "_pending_guard_preserved"] = response["error"]["message"] == "pending_edit_requires_state_recovery" and not pending.calls
    checks[version + "_pending_guard_no_state_write"] = (pending.directory / "session.json").read_bytes() == bytes_before
    finish("g", pending)

    if version == "new":
        for index, invalid in enumerate((0, -1, True, "1", None)):
            fixture = Harness(version_root / ("i" + str(index)), source)
            state = read(fixture.directory / "session.json")
            state["next_readback_attempt"] = invalid
            write(fixture.directory / "session.json", state)
            fixture.before = copy.deepcopy(state)
            bytes_before = (fixture.directory / "session.json").read_bytes()
            response = fixture.call()
            checks["new_invalid_counter_" + str(index) + "_rejected_without_reader_or_state_write"] = response["error"]["message"] == "invalid_next_readback_attempt" and not fixture.calls and (fixture.directory / "session.json").read_bytes() == bytes_before
            finish("i" + str(index), fixture)
    return checks, cases


def concurrency(root, source):
    fixture = Harness(root, source)
    entered, resume = threading.Event(), threading.Event()
    fixture.pause = (entered, resume)
    results = []
    thread = threading.Thread(target=lambda:results.append(fixture.call()))
    thread.start()
    if not entered.wait(10):
        raise TimeoutError("parent_reader_not_entered")
    process = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", str(Path(__file__).resolve()),
        "--worker-save", str(root), str(source)], capture_output=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    write(root / "CHILD.json", dict(returncode=process.returncode, stdout=process.stdout.decode("utf8"), stderr=process.stderr.decode("utf8")))
    child = json.loads(process.stdout)
    state_while_locked = read(fixture.directory / "session.json")
    resume.set()
    thread.join(10)
    if thread.is_alive():
        raise TimeoutError("parent_reader_did_not_finish")
    fixture.pause = None
    second = fixture.call()
    checks = dict(new_concurrent_process_lock_blocks_competing_call=child["error"]["type"] in ("OSError", "PermissionError"),
        new_blocked_process_does_not_consume_attempt=state_while_locked["next_readback_attempt"] == 2,
        new_lock_owner_and_later_call_succeed=results[0]["error"] is None and second["error"] is None,
        new_concurrent_allocation_remains_unique=len({row["label"] for row in fixture.calls}) == 2,
        new_concurrent_saved_state_preserved=fixture.state_preserved())
    write(root / "CASE.json", fixture.evidence() | dict(child=child, state_while_locked=state_while_locked))
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-save", nargs=2)
    args = parser.parse_args()
    if args.worker_save:
        root, source = map(Path, args.worker_save)
        fixture = Harness(root, source, existing=True)
        print(json.dumps(fixture.call(), allow_nan=False))
        return
    wall, cpu = time.perf_counter(), time.process_time()
    root = HERE / "private/controls" / uuid.uuid4().hex[:8]
    root.mkdir(parents=True, exist_ok=False)
    old = subprocess.check_output(["git", "show", OLD_COMMIT + ":verification/m6_refine_001/session_api.py"], cwd=REPOSITORY)
    (root / "old.py").write_bytes(old)
    (root / "new.py").write_bytes(API_PATH.read_bytes())
    all_checks, outcomes = {}, {}
    try:
        for version in ("old", "new"):
            checks, cases = exercise(version, root / version, root / (version + ".py"))
            all_checks.update(checks)
            outcomes[version] = cases
        all_checks.update(concurrency(root / "x", root / "new.py"))
        all_checks["candidate_source_stable_during_controls"] = identity(API_PATH)["sha256"] == identity(root / "new.py")["sha256"]
    except Exception as error:
        write(root / "UNEXPECTED_FAILURE.json", dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc(),
            wall_s=time.perf_counter()-wall, cpu_s=time.process_time()-cpu))
        raise
    report = dict(status="pass" if all(all_checks.values()) else "fail", checks=all_checks,
        passed=sum(all_checks.values()), total=len(all_checks),
        old_fixed_commit=OLD_COMMIT, old_source=identity(root / "old.py"), candidate_source=identity(root / "new.py"),
        script=identity(Path(__file__)), original_API_path=str(API_PATH),
        detail_root=str(root), old_expected_exception_sequence=["RuntimeError", "FileExistsError"],
        new_expected_exception_sequence=["RuntimeError", None],
        actual_Pro_calls=0, actual_Blender_calls=0, training_runs=0,
        ordinary_child_Python_processes=1, wall_s=time.perf_counter()-wall, cpu_s=time.process_time()-cpu,
        scope="Actual save_readback, session_lock and state_path functions extracted by AST from fixed Git bytes and current source. Controlled reader replaces Blender, writes only synthetic fixture bytes in this new batch. Process lock uses the actual extracted Windows implementation.")
    write(root / "RESULT.json", report)
    write(HERE / "CONTROL_SUMMARY.json", report)
    print(json.dumps(dict(status=report["status"], passed=report["passed"], total=report["total"], wall_s=report["wall_s"], cpu_s=report["cpu_s"], detail_root=str(root))))
    if not all(all_checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
