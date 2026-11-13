"""Local image-ledger fault controls on one old PNG, with zero raster calls."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class LocalSession:
    """Only the actor's bookkeeping interface. Contains no renderer or core."""

    def __init__(self, actor, folder, specification, fixture):
        self.trace = actor.COMMON.Trace(folder / "TRACE.jsonl", "LOCAL_LEDGER_CONTROL")
        self.specification = specification
        self.fixture = fixture
        self.attempts = []
        self.runtime_faults = []
        self.audit = {"scope": "Bookkeeping control without an observation session."}

    def image_specification(self, ref):
        if ref != self.specification["ref"]:
            raise ValueError("control_reference")
        return self.specification, self.fixture.parent

    def metrics(self):
        return {"render_attempts": 0, "raster_completed": 0, "frames_completed": 0}


def make_owner(actor, folder, specification, fixture):
    owner = actor.Owner.__new__(actor.Owner)
    owner.out = folder
    owner.calls = 1
    owner.logs = []
    owner.constructions = []
    owner.construction_failures = []
    owner.post_construction_failures = []
    owner.transport_records = []
    owner.deadline_ns = time.perf_counter_ns() + 30 * 10**9
    owner.session = LocalSession(actor, folder, specification, fixture)
    return owner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-png", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    raw = args.source_png.read_bytes()
    fixture = args.output / "fixture.png"
    fixture.write_bytes(raw)
    specification = {"ref": "local-image", "file": fixture.name, "PNG_bytes": len(raw),
                     "sha256": hashlib.sha256(raw).hexdigest(), "width": 512, "height": 512, "mimeType": "image/png"}
    actor = load_module("_coverage_ledger_control_actor", HERE / "actor.py")
    cases = []
    for name in ("normal", "post_encode_deadline", "post_construct_serialization", "post_construct_send"):
        folder = args.output / name
        folder.mkdir()
        owner = make_owner(actor, folder, specification, fixture)
        result = None
        observed_error = None
        deadline_calls = 0
        original_deadline = actor.IMAGE.deadline

        def deadline_check(original):
            nonlocal deadline_calls
            deadline_calls += 1
            original_deadline(original)
            if deadline_calls == 3:
                raise TimeoutError("injected_original_deadline_after_encode")

        def serialization_failure(value):
            raise TypeError("injected_image_block_serialization_failure")

        try:
            if name == "post_encode_deadline":
                with patch.object(actor.IMAGE, "deadline", deadline_check):
                    result = owner.image_result([specification["ref"]])
            elif name == "post_construct_serialization":
                with patch.object(actor.IMAGE, "encoded", serialization_failure):
                    result = owner.image_result([specification["ref"]])
            else:
                result = owner.image_result([specification["ref"]])
            if name == "post_construct_send":
                reply = {"request_id": "local-send-control", "ok": True,
                         "result": {"jsonrpc": "2.0", "id": "control", "result": result}}
                encoded_reply = actor.encoded(reply)
                start = time.perf_counter_ns()
                send_error = None
                try:
                    # Deterministic send boundary injection. There is no socket.
                    raise BrokenPipeError("injected_send_failure_after_construction")
                except BrokenPipeError as error:
                    send_error = {"type": type(error).__name__, "message": str(error)}
                owner.record_transport(b"{}\n", reply, False, send_error, start, time.perf_counter_ns())
                (folder / "ATTEMPTED_REPLY.bin").write_bytes(encoded_reply)
        except BaseException as error:
            observed_error = {"type": type(error).__name__, "message": str(error)}
        metrics = owner.save_metrics()
        owner.session.trace.close()
        expected_error = name in ("post_encode_deadline", "post_construct_serialization")
        passed = (metrics["constructed_image_blocks"] == 1 and metrics["constructed_PNG_bytes"] == len(raw)
            and metrics["constructed_base64_chars"] == 4 * ((len(raw) + 2) // 3)
            and metrics["failed_image_constructions"] == 0 and metrics["server_socket_sent_image_blocks"] == 0
            and (observed_error is not None) == expected_error
            and metrics["post_construction_failures"] == int(expected_error)
            and metrics["helper_ready_image_blocks"] == int(not expected_error)
            and metrics["failed_or_unknown_socket_sends"] == int(name == "post_construct_send")
            and metrics["constructed_image_JSON_bytes_unknown_count"] == int(name == "post_construct_serialization"))
        if name == "post_encode_deadline":
            passed = passed and deadline_calls == 3
        row = {"case": name, "passed": passed, "error": observed_error,
            "original_deadline_ns": owner.deadline_ns, "deadline_checks": deadline_calls,
            "actual_render_attempts": 0, "actual_model_sessions": 0, "actual_network_sends": 0,
            "returned_image_blocks": 0 if result is None else sum(block["type"] == "image" for block in result["content"]),
            "metrics": metrics}
        save(folder / "RESULT.json", row)
        cases.append(row)
    result = {"schema": "coverage-consumption-image-ledger-controls-v1", "all_passed": all(row["passed"] for row in cases),
        "scope": "Four deterministic shared-helper/actual-actor ledger controls. Local session substitutes bookkeeping only.",
        "sources_sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                           for name in ("actor.py", "image_content.py", "common_observation.py", "ledger_controls.py")},
        "fixture_sha256": specification["sha256"], "fixture_PNG_bytes": len(raw), "cases": cases,
        "actual_constructed_blocks": sum(row["metrics"]["constructed_image_blocks"] for row in cases),
        "actual_constructed_PNG_bytes": sum(row["metrics"]["constructed_PNG_bytes"] for row in cases),
        "actual_render_attempts": 0, "actual_model_sessions": 0, "actual_Blender_or_API_calls": 0,
        "actual_network_sends": 0, "send_fault_scope": "Injected BrokenPipeError at the send boundary, without a network socket."}
    save(args.output / "RESULTS.json", result)
    print(json.dumps({"all_passed": result["all_passed"], "constructed_blocks": result["actual_constructed_blocks"],
                      "new_render_attempts": 0}))
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
