"""Compile and inspect the fixed two-session delivery wiring without Blender."""

import ast
import hashlib
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
        for name in ("delivery_common.py", "independent_verify.py", "render_results.py", "quality.py",
                     "evaluate.py", "facts_api.py", "score.py", "quality_preflight.py", "construction_quality.py",
                     "delivery_preflight.py"):
            path = HERE / name
            tree = ast.parse(path.read_bytes(), filename=str(path))
            compile(tree, str(path), "exec")
            result["sources"].append(identity(path))
            checks[name + "_AST_compile"] = True
        checks["run_fixed_facts_then_native"] = session_names("run") == ["run_repair_facts", "run_repair_native"]
        checks["all_is_same_two_sessions"] = session_names("all") == session_names("run")
        for name in ("quality.py", "evaluate.py", "facts_api.py"):
            checks[name + "_matches_003_frozen_code"] = (HERE / name).read_bytes() == (HERE.parent / "m6_matched_refine_003" / name).read_bytes()
        score_source = (HERE / "score.py").read_bytes().replace(b'M6-DEGRID-004', b'M6-MATCHED-REFINE-003')
        checks["score_only_cycle_identity_changed"] = score_source == (HERE.parent / "m6_matched_refine_003/score.py").read_bytes()
        for name in ("independent_verify.py", "render_results.py"):
            tree = ast.parse((HERE / name).read_bytes())
            argument = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument"
                and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "--stage")
            values = {item.arg: ast.literal_eval(item.value) for item in argument.keywords}
            checks[name + "_default_run_accepts_all"] = values == dict(choices=("run", "all"), default="run")
        result["status"] = "pass" if all(checks.values()) else "fail"
    except BaseException as error:
        result.update(status="error", error=dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc()))
    result.update(wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
                  validation_scope="AST compilation, source equality, deterministic session mapping. Runtime Blender jobs pending parent execution.")
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
