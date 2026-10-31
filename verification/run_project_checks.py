"""Run project regression checks and the existing module verification suites."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    checks = [
        ("integration_regressions", ["-m", "unittest", "discover", "-s", "verification", "-v"]),
        ("optimized_regressions", ["-m", "unittest", "discover", "-s", "verification/optimized", "-v"]),
        ("module_2", ["module_2_low_token_mcp_scene_bridge.py"]),
        ("module_3_1", ["module_3_1_mcp_protocol_ipc_engine.py"]),
        ("module_3_2", ["module_3_2_vlm_grounding_closed_loop_agent.py"]),
        ("module_3_3", ["module_3_3_closed_loop_control_engine.py"]),
        ("module_1_6", ["human_eye_module1_operators/submodule_1_6_quad_compositor.py"]),
    ]
    results = []
    for name, args in checks:
        try:
            result = subprocess.run(
                [sys.executable, "-B", *args], cwd=root, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=45,
                env=dict(os.environ, PYTHONIOENCODING="utf-8"),
            )
            results.append({"check": name, "passed": result.returncode == 0,
                            "exit_code": result.returncode, "stdout": result.stdout,
                            "stderr": result.stderr})
        except subprocess.TimeoutExpired:
            results.append({"check": name, "passed": False, "error": "Timeout after 45 seconds"})
    report = {"all_passed": all(r["passed"] for r in results), "checks": results}
    (root / "verification" / "project_check_results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for result in results:
        print(f"{result['check']}: {'PASS' if result['passed'] else 'FAIL'}")
        if not result["passed"]:
            print(result.get("stderr", result.get("error", "")))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
