"""AST-compile delivery helpers and retain the measured preparation attempt."""

import ast
import hashlib
import json
from pathlib import Path
import time
import traceback

HERE = Path(__file__).resolve().parent


def main():
    started, cpu = time.perf_counter(), time.process_time()
    result = dict(status="running", started_unix_s=time.time(), actual_Blender_calls=0, actual_Pro_calls=0,
                  validation_scope="AST parsing and compilation of source bytes without executing imported modules", sources=[], checks={})
    try:
        for name in ("delivery_common.py", "independent_verify.py", "render_results.py", "delivery_preflight.py"):
            path = HERE / name
            raw = path.read_bytes()
            tree = ast.parse(raw, filename=str(path))
            compile(tree, str(path), "exec")
            result["sources"].append(dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
            result["checks"][name + "_AST_compile"] = True
        frozen = json.loads((HERE / "QUALITY_PREFLIGHT.json").read_bytes())["attempts"][0]["sources"]
        for name in ("quality.py", "evaluate.py", "facts_api.py", "score.py"):
            expected = next(row for row in frozen if Path(row["path"]).name == name)
            result["checks"][name + "_frozen_source_matches"] = hashlib.sha256((HERE / name).read_bytes()).hexdigest() == expected["sha256"]
        result["status"] = "pass" if all(result["checks"].values()) else "fail"
    except BaseException as error:
        result.update(status="error", error=dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc()))
    result.update(wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu)
    destination = HERE / "DELIVERY_HELPER_PREFLIGHT.json"
    report = json.loads(destination.read_bytes()) if destination.exists() else dict(attempts=[])
    report["attempts"].append(result)
    report.update(status=result["status"], wall_s_total=sum(row["wall_s"] for row in report["attempts"]),
                  CPU_s_total=sum(row["CPU_s"] for row in report["attempts"]), actual_Blender_calls=0, actual_Pro_calls=0)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    print(json.dumps(result, ensure_ascii=True), flush=True)
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
