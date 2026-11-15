"""Synthetic interface checks. No host, CLI, model, image or raster execution."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    bootstrap = load("_target_pure_bootstrap", HERE / "bootstrap.py")
    dependency = bootstrap.prepare_dependencies()
    bridge = load("_target_pure_bridge", HERE / "bridge.py")
    launcher = load("_target_pure_launcher", HERE / "launcher.py")
    output = HERE / "pure_01"
    output.mkdir(exist_ok=False)

    class FakeBudget:
        def __init__(self):
            self.events = []

        def reserve(self, kind, label, phase, upper):
            self.events.append((kind, label, phase, upper))
            if len(self.events) > 12:
                raise ValueError("synthetic_business_limit")
            return {"admitted": True}

    class FakeRuntime:
        def __init__(self):
            self.budget, self.buffers, self.by_ref = FakeBudget(), {}, {}
            self.reads, self.observations = 0, 0
            self.cameras = {"private_summary": "not public", "views": [
                {"name": name, "size_px": [512, 512], "view_matrix": [[1, 0, 0, 0]] * 4,
                 "projection_matrix": [[1, 0, 0, 0]] * 4, "private_path": "not public"}
                for name in bridge.COMMON.VIEW_NAMES]}

        def scene_data(self, selectors=None):
            self.reads += 1
            return {"source_ref": "synthetic-current-source", "objects": [], "selectors": selectors}

        def native_run(self, code, timeout_s):
            return {"stdout": "synthetic", "stderr": "", "error": None}

        def public_observe(self, include_images):
            self.observations += 1
            return {"jsonrpc": "2.0", "id": "synthetic", "result": {
                "content": [{"type": "text", "text": '{"synthetic":true}'}], "isError": False}}

    checks = []

    def checked(name, passed, detail=None):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    def owner(group, name):
        runtime = FakeRuntime()
        value = bridge.Owner(runtime, {"group": group, "label": name, "phase": "preparation",
            "worker_deadline_ns": time.perf_counter_ns() + 60_000_000_000,
            "output": str(output / name)})
        return runtime, value

    runtime, n = owner("N", "N_SYNTHETIC")
    checked("no_implicit_geometry_read", runtime.reads == 0)
    checked("public_camera_fields_only", set(n.session.namespace["cameras"]) == {"views"}
            and all("private_path" not in row for row in n.session.namespace["cameras"]["views"]))
    value = n.session.execute("from shapely.geometry import Point\nprint(int(np.sum(np.arange(4))), Point(0,0).distance(Point(3,4)))")
    checked("ordinary_numpy_shapely", value["error"] is None and value["stdout"].strip() == "6 5.0", value)
    value = n.session.execute("class Public:\n    name='public-object'\nprint(getattr(Public(), 'name'), hasattr(Public(), 'name'))")
    checked("public_getattr_hasattr", value["error"] is None and value["stdout"].strip() == "public-object True", value)
    for name, code in [
        ("private_globals", "print(blender.__globals__)"),
        ("private_bound_self", "print(blender.__self__)"),
        ("private_sys_modules", "import sys\nprint(sys.modules)"),
        ("private_dynamic_attribute", "getter=getattr\nprint(getter(blender,'__self__'))"),
        ("private_file", "print(open(" + repr(str(HERE / "BASELINE.json")) + ").read())"),
        ("product_high_level_import", "import human_eye_plugin.live_service"),
    ]:
        value = n.session.execute(code)
        checked(name, value["error"] is not None and value["error"]["type"] == "PermissionError", value)
    value = n.session.execute("source=scene_data(['PublicObject'])\nprint(source['source_ref'])")
    checked("lazy_public_current_source", runtime.reads == 1 and value["stdout"].strip() == "synthetic-current-source", value)
    checked("N_product_tool_absent", "active_observation" not in [row["name"] for row in bridge.public_tools("N")])
    runtime_p, p = owner("P", "P_SYNTHETIC")
    response = p.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "active_observation", "arguments": {"include_images": True}}})
    checked("P_public_default_response_preserved", response["result"]["content"][0]["text"] == '{"synthetic":true}'
            and runtime_p.observations == 1 and runtime_p.reads == 0)
    checked("one_business_admission", runtime_p.budget.events == [("business_tool", "P_SYNTHETIC", "preparation", 1)])
    _, bad_p = owner("P", "P_BAD_FIRST_SYNTHETIC")
    response = bad_p.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
        "name": "scene_data", "arguments": {}}})
    checked("P_first_entry_violation_recorded", response["result"]["isError"] is True and bool(bad_p.protocol_errors))
    consume, proof = launcher.consumer_adapter()
    checked("accepted_event_loop_and_archive_reused", proof["event_loop_code_reused"] and proof["unified_archive_reused"], proof)
    checked("factory_has_no_product_high_level_import", "human_eye_plugin.live_service" not in sys.modules)
    common = (HERE / "inputs/COMMON_TASK.txt").read_bytes() + b"\n\nANSWER_SCHEMA.json\n" + (HERE / "inputs/ANSWER_SCHEMA.json").read_bytes()
    checked("N_P_byte_identical_task_schema_suffix", all(launcher.common_prompt(group).split(b"\n\n", 1)[1] == common for group in ("N", "P")))
    result = {"schema": "target-task-bridge-synthetic-checks-v1", "passed": all(row["passed"] for row in checks),
        "checks": checks, "passed_count": sum(row["passed"] for row in checks), "check_count": len(checks),
        "source_sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in (
            "bridge.py", "native_tools.py", "bootstrap.py", "launcher.py", "bridge_pure_checks.py")},
        "dependency": dependency, "actual_Blender_starts": 0, "actual_model_calls": 0,
        "actual_CLI_calls": 0, "actual_rasters": 0, "constructed_images": 0,
        "scope": "Synthetic handlers and ordinary public-input boundary only. Live provenance, actual image transport and lifecycle require root qualification."}
    bridge.save(HERE / "BRIDGE_PURE.json", result)
    print(json.dumps({"passed": result["passed"], "passed_count": result["passed_count"], "check_count": len(checks)}))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
