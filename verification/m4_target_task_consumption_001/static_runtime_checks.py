"""Unit admissions, source forwarding and native audit mocks. Zero live slots."""

import ast
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import time


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from budget import Budget, encoded, save
from native_consumer_audit import installation_script, wrap


def main():
    output = HERE / (sys.argv[1] if len(sys.argv) > 1 else "STATIC_RUNTIME_CHECK")
    output.mkdir(exist_ok=False)
    checks = []
    for path in list(HERE.glob("*.py")) + list((HERE / "reused").glob("*.py")):
        ast.parse(path.read_text(encoding="utf-8"))
    checks.append("all_new_sources_parse")
    ledger = Budget(output / "budget_mock")
    for label in ("QN", "QP"):
        for index in range(6):
            token = ledger.reserve("raster_attempt", label, "qualification", 1)
            ledger.settle_rasters(token, actual=1, lower_bound=1, evidence={"pure_mock": True}, outcome="mock")
        try:
            ledger.reserve("raster_attempt", label, "qualification", 1)
        except RuntimeError as error:
            assert str(error) == "raster_phase_total_or_slot_budget_exhausted"
        else:
            raise AssertionError("slot_and_qualification_cap")
    checks.append("qualification_and_per_slot_unit_caps_enforced_before_attempt")
    for label in ("N1", "P1", "P2", "N2", "N3", "P3"):
        for index in range(6):
            token = ledger.reserve("raster_attempt", label, "formal", 1)
            ledger.settle_rasters(token, actual=1, lower_bound=1, evidence={"pure_mock": True}, outcome="mock")
    try:
        ledger.reserve("raster_attempt", "extra", "formal", 1)
    except RuntimeError:
        pass
    else:
        raise AssertionError("formal_and_total_cap")
    checks.append("formal36_and_total48_unit_caps_enforced")
    for index in range(12):
        ledger.reserve("business_tool", "N1", "formal", 1)
    try:
        ledger.reserve("business_tool", "N1", "formal", 1)
    except RuntimeError as error:
        assert str(error) == "business_call_budget_exhausted"
    else:
        raise AssertionError("thirteenth_business_admission")
    checks.append("business_admission12_including_unreturned_calls")
    for index in range(8):
        token = ledger.reserve("Blender_start", "mock-" + str(index), "formal", 1)
        ledger.settle_start(token, pid=1000 + index, spawn_status="mock", outcome="mock")
    try:
        ledger.reserve("Blender_start", "ninth", "formal", 1)
    except RuntimeError:
        pass
    else:
        raise AssertionError("ninth_start")
    checks.append("eight_owned_start_cap")
    unknown = Budget(output / "unknown_mock")
    unknown.reserve("raster_attempt", "N1", "formal", 1)
    snapshot = unknown.snapshot()
    assert snapshot["counts"]["all_raster_actual"] == 0 and snapshot["counts"]["all_raster_upper"] == 1
    checks.append("unconfirmed_attempt_retains_upper_bound")
    scratch = output / "scratch"
    scratch.mkdir()
    fake = SimpleNamespace(data=SimpleNamespace(objects=[1, 2]))
    namespace = {"bpy": fake}
    script = installation_script(scratch, output / "input.blend", Path("D:/he_m4_target_002/B/product"))
    ast.parse(script)
    exec(compile(script, "<native-audit-mock-install>", "exec"), namespace)
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        exec(compile(wrap("print(len(bpy.data.objects))"), "<native-audit-mock-call>", "exec"), namespace)
    assert captured.getvalue().strip() == "2"
    checks.append("ordinary_native_public_bpy_runs_in_separate_safe_namespace")
    for code in ("import sys", "print(bpy.__class__)", "print(globals())"):
        try:
            exec(compile(wrap(code), "<native-audit-mock-call>", "exec"), namespace)
        except PermissionError:
            pass
        else:
            raise AssertionError("native_private_reflection_or_import")
    checks.append("native_guard_matches_public_import_and_reflection_boundary")
    try:
        exec(compile(wrap("open('D:/hefe/admin/TRUTH.json').read()"), "<native-audit-mock-call>", "exec"), namespace)
    except PermissionError:
        pass
    else:
        raise AssertionError("native_private_input_read")
    assert namespace["_consumer_scope_state"]["running"] is False
    checks.append("native_private_read_denied_and_scope_restored")
    source = (HERE / "mcp_entry.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == "ObservedService")
    observer_budget = Budget(output / "observer_budget_mock")
    archive = output / "observer_full"
    archive.mkdir()
    config = output / "observer_config.json"
    audit = output / "observer_audit.jsonl"
    save(config, {"audit_file": str(audit)})
    raw = {"status": "complete", "frames": [{"image_ref": "same-current-ref", "image_sha256": "mock-PNG",
                                               "arrays_sha256": "mock-NPZ", "host_binding_sha256": "same-current-binding"}]}
    class OriginalService:
        def __init__(self):
            self.calls = 0

        def record_event(self, event, **fields):
            with audit.open("ab") as stream:
                stream.write(encoded({"event": event, **fields}))
            return {"event": event}

        def observe(self):
            self.calls += 1
            self.record_event("active_observation_render_attempt", view_name="SCENE")
            return raw

    globals_dict = {"LiveSpatialService": OriginalService, "ledger": observer_budget,
                    "args": SimpleNamespace(label="QP", phase="qualification", archive=archive, config=config),
                    "Path": Path, "time": time, "json": json, "hashlib": hashlib,
                    "save": save, "encoded": encoded, "os": __import__("os")}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<passive-observer-mock>", "exec"), globals_dict)
    observed = globals_dict["ObservedService"]()
    result = observed.observe()
    assert observed.calls == 1 and result is raw
    entries = [json.loads(line) for line in (archive / "INDEX.jsonl").read_bytes().splitlines()]
    assert len(entries) == 1 and json.loads(Path(entries[0]["path"]).read_bytes()) == raw
    assert observer_budget.snapshot()["counts"]["all_raster_actual"] == 1
    assert json.loads(Path(entries[0]["path"]).read_bytes())["frames"][0] == result["frames"][0]
    checks.append("passive_archive_same_object_one_producer_one_attempt_same_frame_reference")
    runtime_tree = ast.parse((HERE / "owned_runtime.py").read_bytes())
    method = next(node for node in ast.walk(runtime_tree) if isinstance(node, ast.FunctionDef) and node.name == "public_observe")
    assert "response_detail" not in ast.get_source_segment((HERE / "owned_runtime.py").read_text(encoding="utf-8"), method)
    checks.append("product_public_request_omits_response_detail")
    for name in ("owned_native.py", "stdio_checks.py"):
        text = (HERE / "reused" / name).read_text(encoding="utf-8")
        spawn = text.index("'SPAWN.json'")
        after = text.index("ready=self.workspace", spawn) if name == "owned_native.py" else text.index("self.reader.start()", spawn)
        assert spawn < after
    checks.append("both_immediate_spawn_receipts_precede_wait_or_reader_start")
    result = {"passed": True, "checks": checks, "actual_owned_starts": 0, "actual_product_observations": 0,
              "actual_rasters": 0, "actual_models": 0,
              "scope": "pure Python synthetic budgets, native public-namespace mock and observer identity forwarding",
              "author_association": "same author as runtime and fixture preparation, independent live qualification required"}
    save(output / "RESULT.json", result)
    print(json.dumps({"passed": True, "checks": len(checks), "result": str(output / "RESULT.json"),
                      "sha256": hashlib.sha256((output / "RESULT.json").read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
