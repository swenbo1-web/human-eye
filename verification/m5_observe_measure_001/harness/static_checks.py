"""Import, request, passive observer and timing checks without live operations."""

import ast
from collections import OrderedDict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from budget import Budget, encoded, save


def module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(result)
    return result


def main():
    output = HERE.parent / "STATIC_CHECKS"
    output.mkdir(exist_ok=False)
    checks = []
    for path in HERE.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"))
    case = module("_m5_case_static", HERE / "run_case.py")
    module("_m5_entry_static", HERE / "mcp_entry.py")
    checks.append("all_harness_sources_parse_and_import_without_startup")
    requests = json.loads((HERE.parent / "REQUESTS.json").read_bytes())
    assert hashlib.sha256((HERE.parent / "REQUESTS.json").read_bytes()).hexdigest() == case.REQUESTS_SHA256
    task = requests["A_main"][1]["params"]["arguments"]["query"]
    assert task == {"mode": "task", "objects": [{"name": "M4_Far_00"}, {"name": "M4_Near"}],
                    "requested_facts": ["surface_proximity"]}
    assert requests["B_main"][0]["params"]["arguments"]["query"]["task_query"] == task
    assert all("response_detail" not in row["params"]["arguments"] for row in requests["A_main"] + requests["B_main"])
    checks.append("registered_A_pair_and_B_task_query_exact_default_details")
    budget = Budget(output / "budget_mock")
    for index in range(12):
        token = budget.reserve("Blender_start", "mock_" + str(index), "qualification")
        budget.settle_start(token, pid=100 + index, spawn_status="mock", outcome="mock")
    try:
        budget.reserve("Blender_start", "extra", "qualification")
    except RuntimeError:
        pass
    else:
        raise AssertionError("thirteenth_owned_start")
    for phase in ("qualification", "formal"):
        for index in range(6):
            token = budget.reserve("raster_request", "mock_raster", phase, 6)
            budget.settle_rasters(token, actual=6, lower_bound=6, evidence={"mock": True}, outcome="mock")
    assert budget.snapshot()["counts"]["all_raster_upper"] == 72
    try:
        budget.reserve("raster_request", "extra", "formal", 1)
    except RuntimeError:
        pass
    else:
        raise AssertionError("seventythird_raster")
    checks.append("owned12_and_phase36_total72_caps")
    source = (HERE / "mcp_entry.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    selected = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                and node.name in ("read_context_metadata", "ObservedService")]
    raw = {"status": "complete", "frames": [], "task_result": {"facts": {"surface_proximity": {"value": {"distance_m": 1}}}}}
    class Original:
        def __init__(self):
            self.calls = 0
            self._read_context = SimpleNamespace(_selections=OrderedDict(), _generation=None, _capture=None)

        def observe(self):
            self.calls += 1
            return raw

    archive = output / "observer_mock"
    archive.mkdir()
    scope = {"LiveSpatialService": Original, "args": SimpleNamespace(archive=archive), "Path": Path,
             "time": time, "json": json, "hashlib": hashlib, "save": save, "encoded": encoded, "os": os}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "<m5-observer-mock>", "exec"), scope)
    observed = scope["ObservedService"]()
    assert observed.observe() is raw and observed.calls == 1
    assert json.loads((archive / "call_001/SERVICE_RESULT.json").read_bytes()) == raw
    checks.append("passive_archive_same_object_one_producer_no_extra_solver")
    call_folder = output / "business_mock"
    call_folder.mkdir()
    producer = call_folder / "producer"
    producer.mkdir()
    class Client:
        def __init__(self):
            self.records = []
            self.calls = []

        def call(self, request):
            self.calls.append(request)
            begin = time.perf_counter_ns()
            result = {"status": "complete", "result_kind": "active_observation" if len(self.calls) == 1 else "task_query", "frames": []}
            directory = producer / ("call_" + str(len(self.calls)).zfill(3))
            directory.mkdir()
            path = directory / "SERVICE_RESULT.json"
            save(path, result)
            with (producer / "INDEX.jsonl").open("ab") as stream:
                stream.write(encoded({"index": len(self.calls), "path": str(path), "sha256": case.sha(path)}))
            end = time.perf_counter_ns()
            self.records.append({"started_ns": begin, "closed_ns": end, "stdin_flushed_ns": begin,
                                 "received_complete_ns": end})
            return {"jsonrpc": "2.0", "id": request["id"], "result": {"content": [{"type": "text", "text": json.dumps(result)}], "isError": False}}
    session = case.Session.__new__(case.Session)
    session.output, session.client = call_folder, Client()
    session.call_counter = 0
    session.business_windows, session.request_records, session.errors = [], [], []
    original_rows = case.rows
    def checked_rows(path):
        if "producer" in str(path):
            assert len(session.client.calls) == 2
        return original_rows(path)
    case.rows = checked_rows
    window = session.business(requests["A_main"])
    case.rows = original_rows
    assert len(session.client.calls) == window["public_business_calls"] == 2
    assert window["started_ns"] == session.request_records[0]["started_ns"]
    assert window["completed_ns"] == session.request_records[-1]["completed_ns"]
    checks.append("A_calls_contiguous_and_QA_archive_reads_after_final_reply")
    expired = case.Session.__new__(case.Session)
    expired.output = output / "expired_mock"
    expired.output.mkdir()
    expired.binding_path = expired.output / "BINDING.json"
    save(expired.binding_path, {"mock": True})
    expired.binding = {"source_sha256": "mock"}
    expired.started_ns = expired.deadline_ns = 0
    expired.phase, expired.label = "qualification", "mock"
    expired.native = expired.client = expired.runtime_handle = expired.start_claim = None
    expired.request_records, expired.business_windows, expired.errors = [], [], []
    expired.closed = False
    expired.budget = budget
    original_verify = case.verify_install
    case.verify_install = lambda binding: None
    result = expired.close()
    case.verify_install = original_verify
    assert result["passed_transport_scope"] is False
    assert json.loads((expired.output / "PUBLICATION.json").read_bytes())["passed_transport_scope"] is False
    checks.append("publication_after_original_deadline_never_returns_valid_success")
    result = {"passed": True, "checks": checks, "live_owned_starts": 0, "product_calls": 0,
              "rasters": 0, "models": 0, "scope": "pure mocks and imports, no D runtime ledger created",
              "association": "same author as this harness, independent live qualification still required"}
    save(output / "RESULT.json", result)
    print(json.dumps({"passed": True, "checks": len(checks), "sha256": hashlib.sha256((output / "RESULT.json").read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
