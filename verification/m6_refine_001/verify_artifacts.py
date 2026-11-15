"""Validate immutable evidence and complete deliverables independently of summaries."""

from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write

EXPECTED = ("v1_s01_native", "v1_s01_facts", "v1_s02_facts", "v1_s02_native", "v2_s02_facts", "v2_s01_facts")


def verify():
    started = time.perf_counter()
    checks = {}
    for row in read("PLAN_FREEZE.json")["files"]:
        checks["plan_" + row["path"]] = identity(HERE / row["path"])["sha256"] == row["sha256"]
    for version, filename in (("v1", "TOOL_FREEZE.json"), ("v2", "TOOL_FREEZE_v2.json")):
        for row in read(filename)["files"]:
            archived = row["archived"]
            checks[version + "_archive_" + archived["path"]] = identity(HERE / archived["path"])["sha256"] == row["sha256"] == archived["sha256"]
            if version == "v2":
                source = Path(row["path"])
                checks["current_tool_" + row["path"]] = identity(source if source.is_absolute() else HERE / source)["sha256"] == row["sha256"]
    for row in read("SOURCES.json")["cases"]:
        checks["original_source_" + row["case_id"]] = identity(row["source_original"])["sha256"] == row["source_identity"]["sha256"]
    binding = read("OPTIMIZATION_BINDING.json")
    bound_files = [binding["analysis"], binding["correctness_fix"]["evidence"], binding["correctness_fix"]["actual_recovery_regression"]]
    for row in binding["initial_results"]:
        bound_files += [row["consumer"], row["session"]]
    for row in bound_files:
        checks["optimization_evidence_" + row["path"]] = identity(HERE / row["path"])["sha256"] == row["sha256"]
    claims = list((HERE / "private/consumers").glob("*/*/*/CLAIM.json"))
    checks["exactly_six_actual_sessions"] = len(claims) == 6
    for name in EXPECTED:
        stage, case_id, route = name.split("_")
        consumer = read(HERE / "private/consumers" / stage / case_id / route / "CONSUMER.json")
        session = read(HERE / "private/sessions" / name / "session.json")
        checks[name + "_transport_completed"] = consumer["status"] == "completed" and consumer["safe_to_continue"]
        checks[name + "_tool_and_time_budget"] = consumer["tool_round_budget_respected"] and consumer["wall_s"] <= 480
        checks[name + "_saved_edit_final"] = session["version"] >= 1 and session["pending"] is None
        checks[name + "_saved_identity"] = identity(session["current_blend"])["sha256"] == session["current_blend_identity"]["sha256"]
        for operation in session["operations"]:
            checks[name + "_save_" + operation["operation_id"]] = identity(HERE / operation["saved_blend"]["path"])["sha256"] == operation["saved_blend"]["sha256"]
            checks[name + "_read_" + operation["operation_id"]] = identity(HERE / operation["readback"]["path"])["sha256"] == operation["readback"]["sha256"]
    for stage in ("v1", "v2"):
        analysis = read("CONSUMER_STATS_" + stage + ".json")
        checks[stage + "_all_actual_saves"] = analysis["totals"]["actual_saved"] == analysis["totals"]["sessions"]
        checks[stage + "_all_actual_reads"] = analysis["totals"]["actual_independent_readback"] == analysis["totals"]["sessions"]
        checks[stage + "_all_final_references"] = analysis["totals"]["final_reference_verified"] == analysis["totals"]["sessions"]
        checks[stage + "_all_final_numbers"] = analysis["totals"]["final_measured_claims_consistent"] == analysis["totals"]["sessions"]
    views = read("VIEWABLES.json")
    checks["six_viewable_models"] = len(views["sessions"]) == 6
    def check_view_identity(value):
        if isinstance(value, dict):
            if "path" in value and "sha256" in value:
                path = Path(value["path"])
                actual = identity(path if path.is_absolute() else HERE / path)
                checks["view_file_" + str(path)] = actual["sha256"] == value["sha256"] and actual["bytes"] == value["bytes"]
            for child in value.values():
                check_view_identity(child)
        elif isinstance(value, list):
            for child in value:
                check_view_identity(child)
    check_view_identity(views)
    result = dict(status="pass" if all(checks.values()) else "fail", checks=checks,
        passed=sum(checks.values()), total=len(checks), wall_s=time.perf_counter()-started,
        failed=[key for key, value in checks.items() if not value], expected_sessions=list(EXPECTED))
    write("ARTIFACT_VERIFICATION.json", result)
    return result


if __name__ == "__main__":
    output = verify()
    print(output["status"], output["passed"], output["total"], output["failed"])
    if output["status"] != "pass":
        raise SystemExit(1)
