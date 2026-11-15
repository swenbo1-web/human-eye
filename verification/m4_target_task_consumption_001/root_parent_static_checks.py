"""Tiny synthetic parent failures without processes, sockets or product calls."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "root_parent_pure_01"
OUTPUT.mkdir(exist_ok=False)
snapshot = OUTPUT / "reviewed_run_slot.py"
snapshot.write_bytes((HERE / "run_slot.py").read_bytes())
spec = importlib.util.spec_from_file_location("_parent_synthetic_review", snapshot)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original_read, original_sha = module.read, module.sha
module.HERE = HERE
module.EXTERNAL = OUTPUT
fake_proof = SimpleNamespace(_runtime_exit=lambda handle: {"confirmed": True, "exit_code": 0, "handle_closed": True})
module.load = lambda *args: fake_proof


class FakeStream:
    closed = False

    def close(self):
        self.closed = True


class FakeActor:
    def __init__(self):
        self.pid = 777001
        self.stdin = FakeStream()
        self.returncode = None
        self.waits = self.kills = 0
        self._handle = SimpleNamespace(closed=False)

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.waits += 1
        self.returncode = 0
        return 0

    def kill(self):
        self.kills += 1
        self.returncode = 124


def fake_read(path):
    if Path(path).name == "PRODUCT_RUN_BINDING.json":
        return {"source_manifest": [], "source_sha256": "synthetic"}
    return original_read(path)


module.read = fake_read
module.sha = lambda path: ("2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164"
                           if str(path).endswith("main.blend") else original_sha(path))
actors = []


def popen_retention_failure(*args, **kwargs):
    actor = FakeActor()
    actors.append(actor)
    return actor


def fail_retain(*args):
    raise RuntimeError("synthetic_spawn_proof_failure")


module.subprocess = SimpleNamespace(Popen=popen_retention_failure, CREATE_NO_WINDOW=0,
                                    TimeoutExpired=TimeoutError)
module.retain_children = fail_retain
first = module.run_slot("SYNTHETIC_RETENTION_FAILURE", "N", "qualification")
first_actor = actors[-1]
checks = [{"name": "retention_failure_does_not_skip_actor_cleanup",
           "passed": first_actor.stdin.closed and first_actor.waits > 0,
           "observed": {"stdin_closed": first_actor.stdin.closed, "wait_calls": first_actor.waits,
                        "kill_calls": first_actor.kills, "actor_returncode": first_actor.returncode,
                        "status": first["status"]}}]


def popen_ready(command, **kwargs):
    actor = FakeActor()
    actors.append(actor)
    config = original_read(command[-1])
    module.save(Path(config["runroot"]) / "READY.json", {
        "actor_pid": actor.pid, "worker_deadline_ns": config["worker_deadline_ns"],
        "runtime": {"native_pid": 777002}})
    module.save(Path(config["runroot"]) / "ACTOR_CLOSE.json", {
        "bridge": {"confirmed": False, "errors": [{"reason": "synthetic_bridge_failure"}]},
        "runtime": {"errors": [{"reason": "synthetic_source_fingerprint_changed"}]}})
    return actor


def retain_synthetic(actor, folder, deadline, proof, retained):
    retained["native"] = {"handle": "synthetic", "proof": {
        "confirmed": True, "runtime_pid": 777002, "runtime_created_filetime": 1}}


module.subprocess.Popen = popen_ready
module.retain_children = retain_synthetic
module.finish_held_child = lambda *args: {"confirmed": True, "exit_code": 0,
                                        "handle_closed": True, "forced_by_root": False}
module.qualify = lambda *args: {"status": "completed", "model_consumers": 0}
second = module.run_slot("SYNTHETIC_NESTED_CLOSE_FAILURE", "N", "qualification")
second_actor = actors[-1]
checks.extend([
    {"name": "nested_source_and_bridge_close_failure_rejects_completed",
     "passed": second["status"] == "failed", "observed": {"status": second["status"],
         "actor_close": second["cleanup"].get("actor_close")}},
    {"name": "actor_held_process_handle_closed_before_publication",
     "passed": second_actor._handle.closed, "observed": {"handle_closed": second_actor._handle.closed}},
])
qualification = OUTPUT / "synthetic_rpc"
qualification.mkdir()
module.rpc = lambda endpoint, message, deadline: {"jsonrpc": "2.0", "id": "wrong-id", "result": {}}
# The root function body is independently extracted so the first mock's
# replacement of module.qualify cannot affect this assertion.
import ast
tree = ast.parse(snapshot.read_bytes())
node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "qualify")
namespace = dict(module.__dict__)
exec(compile(ast.Module(body=[node], type_ignores=[]), str(snapshot), "exec"), namespace)
rejected = False
try:
    namespace["qualify"]("N", qualification, "synthetic-endpoint", 1)
except BaseException as error:
    rejected = True
    third = {"type": type(error).__name__, "message": str(error)}
else:
    third = {"accepted_wrong_id_and_empty_result": True}
checks.append({"name": "qualification_rejects_wrong_ids_and_empty_result", "passed": rejected, "observed": third})
result = {"schema": "root-parent-synthetic-static-review-v1", "passed_checked_scope": all(row["passed"] for row in checks),
    "source": {"path": str(HERE / "run_slot.py"), "snapshot": str(snapshot),
               "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest()},
    "checks": checks, "actual_Blender_starts": 0, "actual_CLI_calls": 0,
    "actual_model_calls": 0, "actual_rasters": 0,
    "scope": "Synthetic Popen/proof/RPC replacements only. The source under review is copied unchanged; root production and runtime sources are read-only."}
with (HERE / "ROOT_PARENT_MOCK_01.json").open("x", encoding="utf-8") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"passed": result["passed_checked_scope"], "checks": checks}, ensure_ascii=False))
