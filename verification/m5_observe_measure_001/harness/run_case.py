"""Root-invoked fresh owned observation/measurement engineering session."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
NAMESPACE = HERE.parent
EXTERNAL = Path("D:/he_m5_observe_measure_001")
ASSET = Path("D:/he_m4_target_002/assets_01/main.blend")
ASSET_SHA256 = "2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164"
REQUESTS_SHA256 = "ef3ceb0e51a5b6ab1bf902c4d5d3cae92649eae519883feafabde832e2995573"
sys.path.insert(0, str(HERE))
from budget import Budget, save
from decode_wire import decode


def load(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    return [json.loads(line) for line in Path(path).read_bytes().splitlines() if line.strip()] if Path(path).exists() else []


def module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(result)
    return result


def verify_install(binding):
    for row in binding["source_manifest"]:
        if sha(Path(binding["install_root"]) / row["path"]) != row["sha256"]:
            raise ValueError("frozen_installed_source_changed")
    identity = {key: binding[key] for key in ("base_version", "implementation_revision")}
    identity["files"] = binding["source_manifest"]
    actual = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    if actual != binding["source_sha256"]:
        raise ValueError("installed_source_manifest_identity_changed")


class Session:
    def __init__(self, binding_path, output, ledger, phase, label, helper_path=None):
        self.started_ns = time.perf_counter_ns()
        self.deadline_ns = self.started_ns + 600_000_000_000
        self.output = Path(output).resolve()
        if not self.output.is_relative_to(EXTERNAL.resolve()):
            raise ValueError("owned_output_outside_M5_batch")
        self.output.mkdir(parents=True, exist_ok=False)
        self.binding_path = Path(binding_path).resolve()
        self.binding = load(self.binding_path)
        self.phase, self.label = phase, label
        self.budget = Budget(ledger)
        self.native = self.client = self.runtime_handle = None
        self.start_claim = None
        self.call_counter = 0
        self.request_records, self.business_windows, self.errors = [], [], []
        self.closed = False
        self.helper_path = HERE / "reused/owned_native.py" if helper_path is None else Path(helper_path)

    def start(self):
        verify_install(self.binding)
        if sha(ASSET) != ASSET_SHA256:
            raise ValueError("owned_asset_changed")
        if sha(NAMESPACE / "REQUESTS.json") != REQUESTS_SHA256:
            raise ValueError("frozen_public_arguments_changed")
        self.start_claim = self.budget.reserve("Blender_start", self.label, self.phase)
        self.helper = module("_m5_owned_native", self.helper_path)
        self.transport = module("_m5_stdio", HERE / "reused/stdio_checks.py")
        self.proof_module = module("_m5_process_proof", HERE / "reused/process_proof.py")
        self.native = self.helper.NativeSession.start(blender="D:/Tools/blender5.2/blender.exe", asset=ASSET,
            workspace=self.output / "native", deadline_ns=self.deadline_ns, condition="P",
            expected_asset_sha256=ASSET_SHA256, max_calls=128)
        config = {"schema_version": "1.0", "enabled": True, "observe_on_prompt": False,
                  "project_root": self.binding["install_root"], "state_file": str(self.output / "state.json"),
                  "audit_file": str(self.output / "audit.jsonl"),
                  "expected_identity": {"source_sha256": self.binding["source_sha256"]}, "request_budget_s": 30,
                  "blender": {"host": self.native.host, "port": self.native.port, "timeout_s": 30}}
        save(self.output / "CONFIG.json", config)
        command = [sys.executable, "-I", "-B", "-X", "utf8", str(HERE / "mcp_entry.py"),
                   "--binding", str(self.binding_path), "--config", str(self.output / "CONFIG.json"),
                   "--ledger", str(self.budget.root), "--evidence", str(self.output / "io_audit"),
                   "--phase", self.phase, "--archive", str(self.output / "producer")]
        self.client = self.transport.StdioClient(command, self.output, self.output / "stdio", self.deadline_ns)
        initialized = self.client.call({"jsonrpc": "2.0", "id": "initialize", "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "m5-engineering", "version": "001"}}})
        save(self.output / "INITIALIZE.json", initialized)
        identity = initialized["result"]["_meta"]["human_eye"]
        if identity["source_sha256"] != self.binding["source_sha256"] or identity["source_kind"] != "installed_distribution":
            raise ValueError("actual_public_runtime_identity_changed")
        proof, self.runtime_handle = self.proof_module._windows_runtime_proof(self.client.process, self.client.process.pid,
                                                                            self.deadline_ns)
        save(self.output / "RUNTIME_PROOF.json", proof)
        if proof["confirmed"] is not True:
            raise ValueError("MCP_runtime_not_proved")
        self.client.call({"jsonrpc": "2.0", "method": "notifications/initialized"})
        save(self.output / "TOOLS.json", self.client.call({"jsonrpc": "2.0", "id": "tools", "method": "tools/list"}))
        if self.client.call({"jsonrpc": "2.0", "id": "startup_ping", "method": "ping"}).get("result") != {}:
            raise ValueError("startup_ping_failed")
        if rows(self.output / "native/WORKER_EVENTS.jsonl"):
            raise ValueError("metadata_unexpected_host_warmup")
        self.setup_closed_ns = time.perf_counter_ns()
        return self

    def business(self, requests, label="main"):
        folder = self.output / "business" / label
        folder.mkdir(parents=True, exist_ok=False)
        for index, request in enumerate(requests, 1):
            save(folder / f"REQUEST_{index:02}.json", request)
        responses = []
        for index, request in enumerate(requests, 1):
            begun = time.perf_counter_ns()
            response = self.client.call(request)
            completed = time.perf_counter_ns()
            receipt = dict(self.client.records[-1])
            self.call_counter += 1
            responses.append({"index": index, "producer_index": self.call_counter, "id": request["id"],
                "request": request, "response": response, "started_ns": begun, "completed_ns": completed,
                "complete_client_call_ns": completed - begun,
                "client_flush_to_received_ns": receipt["received_complete_ns"] - receipt["stdin_flushed_ns"],
                "client_internal_pre_receipt_ns": receipt["closed_ns"] - receipt["started_ns"],
                "receipt": receipt})
        window = {"label": label, "started_ns": responses[0]["started_ns"],
                  "completed_ns": responses[-1]["completed_ns"], "public_business_calls": len(requests)}
        window["continuous_business_ns"] = window["completed_ns"] - window["started_ns"]
        self.business_windows.append(window)
        for row in responses:
            index = row["index"]
            save(folder / f"RESPONSE_{index:02}.json", row["response"])
            content = row["response"].get("result", {}).get("content", [])
            values = [json.loads(block["text"]) for block in content if block.get("type") == "text"]
            if len(values) != 1:
                raise ValueError("one_public_text_result_required")
            value = values[0]
            save(folder / f"PUBLIC_{index:02}.json", value)
            row.update(public_path=str(folder / f"PUBLIC_{index:02}.json"),
                       image_blocks=sum(block.get("type") == "image" for block in content),
                       public_text_UTF8_bytes=sum(len(block["text"].encode("utf-8")) for block in content if block.get("type") == "text"),
                       result_kind=value.get("result_kind"), is_error=row["response"].get("result", {}).get("isError"))
            if row["is_error"] is True:
                self.errors.append({"stage": "public_result", "id": row["id"], "public": value})
            archive = next((item for item in rows(self.output / "producer/INDEX.jsonl")
                            if item["index"] == row["producer_index"]), None)
            if archive is None:
                if row["is_error"] is False:
                    raise ValueError("same_producer_archive_missing")
            else:
                raw = load(archive["path"])
                row["producer"] = archive
                row["producer_frames"] = []
                for frame in raw.get("frames", []):
                    for name, key in (("image_path", "image_sha256"), ("arrays_path", "arrays_sha256")):
                        path = Path(frame[name]).resolve()
                        if not path.is_relative_to(self.output) or sha(path) != frame[key]:
                            raise ValueError("same_producer_frame_identity_changed")
                    row["producer_frames"].append(frame)
            save(folder / f"REQUEST_RESULT_{index:02}.json", row)
            self.request_records.append(row)
        save(folder / "WINDOW.json", window)
        return window

    def close(self):
        if self.closed:
            return {**load(self.output / "RESULT.json"), **load(self.output / "PUBLICATION.json")}
        cleanup_started = time.perf_counter_ns()
        cleanup = {}
        if self.client is not None:
            try:
                cleanup["stdio"] = self.client.finish()
                if not cleanup["stdio"].get("confirmed"):
                    raise RuntimeError("MCP_stdio_cleanup_unconfirmed")
            except BaseException as error:
                self.errors.append({"stage": "MCP_stdio_cleanup", "message": str(error)})
        if self.runtime_handle is not None:
            try:
                cleanup["MCP_retained"] = self.proof_module._runtime_exit(self.runtime_handle)
                if cleanup["MCP_retained"].get("confirmed") is not True or cleanup["MCP_retained"].get("exit_code") != 0:
                    raise RuntimeError("MCP_retained_exit_unconfirmed")
            except BaseException as error:
                self.errors.append({"stage": "MCP_held_cleanup", "message": str(error)})
            finally:
                self.runtime_handle = None
        if self.native is not None:
            try:
                cleanup["native"] = self.native.close()
                cleanup["native_status"] = self.native.status()
                closed = cleanup["native_status"]["closed"]
                if (cleanup["native"].get("exit_code") != 0 or not cleanup["native"].get("process_reaped")
                        or closed is None or closed.get("poisoned")
                        or closed["initial_geometry_fingerprint"] != closed["final_geometry_fingerprint"]):
                    raise RuntimeError("owned_native_cleanup_or_restore_failed")
            except BaseException as error:
                self.errors.append({"stage": "native_cleanup", "message": str(error)})
        if self.start_claim is not None:
            self.budget.settle_start(self.start_claim, pid=None if self.native is None else self.native.config["pid"],
                spawn_status="unknown" if self.native is None else "spawned", outcome="failed" if self.errors else "completed")
        closed_ns = time.perf_counter_ns()
        saved_wire = None
        try:
            if (self.output / "native/WIRE/INDEX.json").is_file():
                saved_wire = decode(self.output, self.binding)
            io = rows(self.output / "io_audit/MCP_IO.jsonl")
            for record in self.request_records:
                matching = [item for item in io if item["id"] == record["id"]
                            and record["started_ns"] <= item["request_received_ns"] <= record["completed_ns"]]
                if len(matching) != 1:
                    raise ValueError("request_server_clock_not_unique")
                record["server"] = matching[0]
            verify_install(self.binding)
            if sha(ASSET) != ASSET_SHA256:
                raise ValueError("original_asset_changed")
        except BaseException as error:
            self.errors.append({"stage": "saved_evidence", "message": str(error), "traceback": traceback.format_exc()})
        result = {"schema": "m5-owned-engineering-session-v1", "label": self.label, "phase": self.phase,
            "source_sha256": self.binding["source_sha256"], "binding_path": str(self.binding_path),
            "binding_sha256": sha(self.binding_path), "asset_sha256": ASSET_SHA256,
            "started_ns": self.started_ns, "original_owned_deadline_ns": self.deadline_ns,
            "public_request_budget_s": 30, "blender_timeout_s": 30,
            "setup_closed_ns": getattr(self, "setup_closed_ns", None), "requests": self.request_records,
            "business_windows": self.business_windows, "cleanup": cleanup, "errors": self.errors,
            "cleanup_started_ns": cleanup_started, "owned_closed_ns": closed_ns,
            "owned_lifecycle_ns": closed_ns - self.started_ns, "saved_validation_closed_ns": time.perf_counter_ns(),
            "saved_wire": saved_wire, "worker_events": rows(self.output / "native/WORKER_EVENTS.jsonl"),
            "budget": self.budget.snapshot(), "passed_before_publication": not self.errors,
            "model_calls": 0, "paid_API_calls": 0,
            "clock_scope": "Continuous business spans first client call through last call return, including the original client receipt persistence. Caller-only producer/hash checks occur after this window. Server and transport each retain their own boundaries without strict nesting. Complete session also includes all saved validation, cleanup and result fsync.",
            "wrapper_work": {"actual_loop_visits": None,
                "source_derived_scope": "NativeSession fingerprint guards traverse the whole original scene per RPC and closure. Actual elapsed cost remains included, separate from selected returned geometry and resident counters."}}
        save(self.output / "RESULT.json", result)
        published = time.perf_counter_ns()
        publication = {"started_ns": self.started_ns, "result_published_ns": published,
                       "complete_session_ns": published - self.started_ns, "result_sha256": sha(self.output / "RESULT.json"),
                       "original_deadline_passed": published < self.deadline_ns,
                       "passed_transport_scope": not self.errors and published < self.deadline_ns,
                       "scope": "includes RESULT.json fsync; this publication marker persistence is separate"}
        save(self.output / "PUBLICATION.json", publication)
        self.closed = True
        return {**result, **publication}


def run(binding, output, ledger, phase, label, request_key):
    session = Session(binding, output, ledger, phase, label)
    try:
        session.start()
        session.business(load(NAMESPACE / "REQUESTS.json")[request_key])
    except BaseException as error:
        session.errors.append({"stage": "session", "type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()})
    finally:
        result = session.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, default=EXTERNAL / "budget")
    parser.add_argument("--phase", choices=("qualification", "formal"), required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--request-key", choices=("A_main", "B_main", "task_only"), required=True)
    args = parser.parse_args()
    result = run(args.binding, args.output, args.ledger, args.phase, args.label, args.request_key)
    print(json.dumps({"passed": result["passed_transport_scope"], "output": str(args.output), "errors": result["errors"]}))
    if not result["passed_transport_scope"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
