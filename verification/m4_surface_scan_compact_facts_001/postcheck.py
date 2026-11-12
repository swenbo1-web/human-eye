"""Offline final checks of the one frozen engineering candidate and five receipts."""

from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CELLS = ("base_default", "base_brief", "base_full", "edit_default", "edit_full")


def read(path):
    return json.loads(path.read_bytes())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    checks = 0

    def check(condition, label):
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(label)

    order = read(HERE / "WORK_ORDER.json")
    for item in order["inputs"]:
        raw = (HERE / item["local"]).read_bytes()
        check(len(raw) == item["bytes"] and sha(raw) == item["sha256"], item["local"])
    candidate = read(HERE / "CANDIDATE_SOURCE.json")
    ready = read(HERE / "installation/run_01/READY.json")
    install = read(Path(ready["receipt"]))
    check(candidate["commit"] == ready["commit"] == "452b44d2dcf231d6675bef54e568db0431a29261", "one candidate commit")
    check(candidate["source_sha256"] == ready["source_sha256"], "one candidate source")
    check(candidate["source_count"] == ready["source_count"] == 138, "source count")
    check(ready["no_default_activation"] and install["default_activation_changed"] is False, "isolated activation")
    for item in candidate["source_files"]:
        raw = (ROOT / item["path"]).read_bytes()
        committed = subprocess.check_output(["git", "show", candidate["commit"] + ":" + item["path"]], cwd=ROOT)
        check(sha(raw) == item["sha256"] and raw == committed, item["path"] + " commit")
        check((Path(ready["install_root"]) / item["path"]).read_bytes() == raw, item["path"] + " install")
    semantics = read(HERE / "semantics/FINAL_RESULT.json")
    check(semantics["successful"] and semantics["tests_run"] == 180, "offline methods")
    check(semantics["external_schema_cases"] == 13, "separate schema cases")
    check(semantics["product_source_file_sha256"] == sha((ROOT / "human_eye_plugin/live_spatial_mcp.py").read_bytes()), "tested product bytes")

    run = HERE / "engineering/run_01"
    results = read(run / "RESULTS.json")
    timing = read(run / "FINAL_TIMING.json")
    check(timing["accepted_success"] and timing["complete_business_write_close_within_original_deadline"], "complete-close verdict")
    check(results["execution_counts"] == {"attempted": 5, "completed": 5, "failed": 0, "not_attempted": 0}, "full denominator")
    check(tuple(row["state"] for row in results["business"]) == CELLS, "fixed order")
    check(results["errors"] == [] and results["source_files_unchanged"], "candidate errors")
    check(results["product_close"]["confirmed"] and results["runtime_exit"]["confirmed"], "owned product closure")
    check(results["native_close"]["process_reaped"] and results["native_close"]["exit_code"] == 0, "owned Blender closure")
    check(results["metadata_zero_host_RPC"], "metadata host scope")
    check(results["all_host_RPC_including_QA_and_close"] == 9 and len(results["outside_business_RPC"]) == 4, "QA accounting")
    check(timing["full_session_wall_ns"] == timing["business_receipts_closed_ns"] - timing["started_ns"], "full time")
    check(timing["business_receipts_closed_ns"] < timing["original_deadline_ns"], "original deadline")
    check(len({row["body"]["trace_id"] for row in results["business"]}) == 5, "request-local traces")

    rows = []
    for index, row in enumerate(results["business"]):
        expected_detail = (None, "brief", "full", None, "full")[index]
        expected_count = (71, 71, 71, 72, 72)[index]
        arguments = row["request"]["params"]["arguments"]
        check(arguments.get("response_detail") == expected_detail, row["state"] + " detail")
        check(("response_detail" in arguments) == (expected_detail is not None), row["state"] + " omitted default")
        check(arguments["include_image"] is False, row["state"] + " text only")
        text = row["response"]["result"]["content"][0]["text"]
        value = json.loads(text)
        actual_bytes = len(text.encode("utf8"))
        check(value == row["body"] and actual_bytes == row["business_text_utf8_bytes"], row["state"] + " actual bytes")
        check(len(value["matches"]) == row["verification"]["matches"] == expected_count, row["state"] + " matches")
        check(row["verification"]["passed"] and row["actual_host_RPC"] == 1, row["state"] + " verified capture")
        check(row["diagnostics"]["kernel_calls"] == (112, 0, 0, 10, 0)[index], row["state"] + " kernels")
        if expected_detail == "full":
            check("display_encoding" not in value, row["state"] + " full structure")
            check(text == json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")), row["state"] + " exact full serialization")
            check(row["verification"]["full_witnesses_checked"] == expected_count * 2, row["state"] + " witnesses")
        else:
            check(value["display_encoding"] == "surface-scan-task-table-v1", row["state"] + " compact version")
            check(actual_bytes <= 10 * 1024, row["state"] + " whole-text gate")
        rows.append({"state": row["state"], "matches": expected_count, "business_text_utf8_bytes": actual_bytes,
                     "request_wall_ns": row["complete_client_request_ns"], "kernel_calls": row["diagnostics"]["kernel_calls"],
                     "host_captures": row["actual_host_RPC"], "projection_spans_ns": row["compact_projection_spans_ns"],
                     "inclusive_content_encode_spans_ns": row["display_encode_spans_ns"],
                     "host_request_bytes": row["bridge_request_bytes"], "host_response_attempted_bytes": row["bridge_response_bytes"]})
    check(results["business"][0]["body"]["binding"] == results["business"][1]["body"]["binding"] == results["business"][2]["body"]["binding"], "BASE binding")
    check(results["business"][3]["body"]["binding"] == results["business"][4]["body"]["binding"], "EDIT binding")
    check(results["business"][0]["body"]["binding"] != results["business"][3]["body"]["binding"], "pose expires binding")

    # Exercise the installed pure display function with an independent decimal check.
    sys.path.insert(0, ready["install_root"])
    from human_eye_plugin.live_spatial_mcp import project_surface_scan_brief
    original = results["business"][2]["body"]
    values = (sys.float_info.max, math.nextafter(sys.float_info.max, 0), 1e306, -0.0, math.ulp(0.0))
    for distance in values:
        value = json.loads(json.dumps(original))
        value["matches"] = [value["matches"][0]]
        value["matches"][0]["distance_m"] = distance
        compact = project_surface_scan_brief(value)
        row = dict(zip(compact["match_columns"], compact["matches"][0]))
        check(struct.pack(">d", row["distance_m"]) == struct.pack(">d", distance), "extreme raw bits")
        with localcontext() as context:
            context.prec = 1100
            expected = Decimal.from_float(distance) * Decimal(1000)
            millimetres = row["distance_mm"]
            if isinstance(millimetres, str):
                check(Decimal(millimetres) == expected, "overflow display exact decimal")
            else:
                check(math.isfinite(millimetres), "display finite")
                check(millimetres != 0 or distance == 0, "no false zero")

    original_manifest = read(ROOT / "verification/m4_surface_scan_consumption_001/DELIVERY_MANIFEST.json")
    for item in original_manifest["files"]:
        raw = (ROOT / item["path"]).read_bytes()
        check(len(raw) == item["bytes"] and sha(raw) == item["sha256"], "sealed original " + item["path"])
    result = {"schema": "surface_scan_compact_root_postcheck_v1", "status": "pass", "checks": checks,
              "candidate_commit": candidate["commit"], "source_sha256": candidate["source_sha256"],
              "source_count": 138, "old_content_files_preserved": len(original_manifest["files"]),
              "actual_five_business_rows": rows, "engineering_counts": results["execution_counts"],
              "full_engineering_session_ns": timing["full_session_wall_ns"],
              "new_model_consumers": 0, "new_model_API_calls": 0,
              "claims_scope": "One existing five-observation engineering run plus offline checks; model consumption gains remain unmeasured."}
    (HERE / "ROOT_POSTCHECK.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"status": "pass", "checks": checks, "counts": results["execution_counts"],
                      "bytes": [row["business_text_utf8_bytes"] for row in rows], "source_sha256": candidate["source_sha256"]}))


if __name__ == "__main__":
    main()
