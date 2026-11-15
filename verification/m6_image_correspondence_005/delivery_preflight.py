"""Check the four fixed delivery sessions and preserved quality definitions."""

import ast
import json
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from delivery_common import session_names


def main():
    started, cpu = time.perf_counter(), time.process_time()
    result = dict(status="running", started_unix_s=time.time(), actual_Blender_calls=0,
                  actual_Pro_calls=0, sources=[], checks={})
    try:
        checks = result["checks"]
        sources = ("delivery_common.py", "independent_verify.py", "render_results.py", "analyze_consumers.py",
                   "quality.py", "evaluate.py", "score.py", "quality_preflight.py", "delivery_preflight.py",
                   "ray_preflight.py", "correspondence_score.py", "fit_audit.py")
        for name in sources:
            path = HERE / name
            compile(ast.parse(path.read_bytes(), filename=str(path)), str(path), "exec")
            result["sources"].append(identity(path))
            checks[name + "_AST_compile"] = True
        checks["v1_native_then_facts"] = session_names("v1") == ["v1_repair_native", "v1_repair_facts"]
        checks["v2_facts_then_native"] = session_names("v2") == ["v2_repair_facts", "v2_repair_native"]
        checks["four_unique_sessions"] = len(set(session_names("all"))) == 4
        checks["all_preserves_stage_order"] = session_names("all") == session_names("v1") + session_names("v2")
        for name in ("quality.py", "evaluate.py"):
            checks[name + "_matches_004"] = (HERE / name).read_bytes() == (HERE.parent / "m6_degrid_004" / name).read_bytes()
        score_source = (HERE / "score.py").read_bytes().replace(b"M6-IMAGE-CORRESPONDENCE-005", b"M6-DEGRID-004")
        checks["restoration_score_only_cycle_changed"] = score_source == (HERE.parent / "m6_degrid_004/score.py").read_bytes()
        for name in ("independent_verify.py", "render_results.py", "analyze_consumers.py"):
            tree = ast.parse((HERE / name).read_bytes())
            argument = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument"
                and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "--stage")
            values = {item.arg: ast.literal_eval(item.value) for item in argument.keywords}
            checks[name + "_stage_arguments"] = values == dict(choices=("v1", "v2", "all"), default="v1")
        result["status"] = "pass" if all(checks.values()) else "fail"
    except BaseException as error:
        result.update(status="error", error=dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc()))
    result.update(wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
                  validation_scope="Static source/entry-point checks. Actual saved-file jobs are separately executed by the parent.")
    destination = HERE / "DELIVERY_HELPER_PREFLIGHT.json"
    report = read(destination) if destination.exists() else dict(attempts=[])
    report["attempts"].append(result)
    report.update(status=result["status"], wall_s_total=sum(row["wall_s"] for row in report["attempts"]),
                  CPU_s_total=sum(row["CPU_s"] for row in report["attempts"]), actual_Blender_calls=0, actual_Pro_calls=0)
    write(destination, report)
    print(json.dumps(dict(status=result["status"], checks=result["checks"])), flush=True)
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
