"""Verify frozen inputs, actual saved trials and final source selection."""

import argparse
import ast
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from prepare_case import current_normals
import numpy as np


def verify():
    started, cpu = time.perf_counter(), time.process_time()
    checks = []

    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))

    def verify_identity(name, expected):
        actual = identity(HERE / expected["path"])
        check(name, actual["bytes"] == expected["bytes"] and actual["sha256"] == expected["sha256"])

    for row in read("PLAN_FREEZE.json")["files"]:
        verify_identity("frozen input " + row["path"], row)
    for stage, filename in (("v1", "TOOL_FREEZE.json"), ("v2", "TOOL_FREEZE_v2.json")):
        for row in read(filename)["files"]:
            verify_identity(stage + " actual archive " + row["path"], row["archived"])
    selected = read("API_SELECTION.json")
    frozen = read("TOOL_FREEZE_v2.json" if selected["default"] == "v2" else "TOOL_FREEZE.json")
    for row in frozen["files"]:
        verify_identity("current selected source " + row["path"], row)
    binding = read("OPTIMIZATION_BINDING.json")
    for key in ("initial_analysis", "initial_tools", "first_stage_verification"):
        verify_identity("immutable first stage " + key, binding[key])
    for row in binding["initial_results"]:
        for key in ("consumer", "session", "final", "actual_score", "final_views"):
            verify_identity("immutable first stage " + row["route"] + " " + key, row[key])
    case = read("CASE_BINDING.json")
    verify_identity("original asset identity", case["original"])
    for row in case["source_files"]:
        verify_identity("fixed pair source " + row["path"], row)
    public_path = HERE / case["public_initial"]["path"]
    with np.load(public_path, allow_pickle=False) as archive:
        public = dict(archive)
    with np.load(HERE / case["actual_initial_readback"]["path"], allow_pickle=False) as archive:
        actual = dict(archive)
    with np.load(HERE / case["private_score_target"]["path"], allow_pickle=False) as archive:
        target = dict(archive)
    for key, value in actual.items():
        check("public actual damaged " + key, public[key].dtype == value.dtype and public[key].shape == value.shape
              and public[key].tobytes() == value.tobytes())
    expected_fields = {"vertices", "vertices_world", "vertices_local", "matrix_world", "faces", "source_ids",
        "poly_offsets", "poly_vertices", "triangle_polygon_ids", "F_source_ids", "I_ids", "protected_ids",
        "B0_ids", "B1_ids", "local_edges", "n0"}
    check("public geometry field allowlist", set(public) == expected_fields)
    check("public normals recomputed from actual damage", np.array_equal(public["n0"], current_normals(actual["vertices_world"], actual["faces"])))
    check("actual damaged initial used by private score", np.array_equal(public["vertices_world"], target["initial_vertices_world"]))
    check("fixed nonempty broad domains", len(public["F_source_ids"]) == 410 and len(public["I_ids"]) == 274)
    check("hidden support confined to editable domain", len(target["support_ids"]) == 47 and np.isin(target["support_ids"], public["I_ids"]).all())
    check("exact task budgets", case["budget_m"] == 0.006893660855829761)
    check("real isolated restoration control", read("API_PREFLIGHT.json")["status"] == "pass")
    check("real current-case protocol", read("BRIDGE_PREFLIGHT.json")["status"] == "pass")
    check("preview API real-control preflight", read("PREVIEW_PREFLIGHT.json")["status"] == "pass")
    check("preview final pixel agreement", read("PREVIEW_PIXEL_VERIFICATION.json")["passed"] == 8)
    stats = read("CONSUMER_STATS_all.json")
    check("four actual terminal consumers", stats["totals"]["sessions"] == stats["totals"]["terminal_sessions"] == 4)
    check("four actual edits", stats["totals"]["modification_decisions"] == {"edit": 4})
    check("48 actual source-verified image blocks", stats["totals"]["server_image_blocks"] == 48)
    check("four actual saved readbacks", stats["totals"]["independent_readbacks"] == stats["totals"]["verified_final_references"] == 4)
    score_rows = read("FINAL_VERIFICATION.json")["sessions"]
    check("four final independently scored files", len(score_rows) == 4)
    for row in stats["sessions"]:
        label = row["stage"] + " " + row["route"]
        check(label + " actual limits", row["tools"] <= 12 and row["wall_s"] < 600)
        check(label + " image delivery", row["images"]["evidence_verified"])
        check(label + " final artifact identity", row["actual_saved_copy_verified"] and row["actual_independent_readback"])
        check(label + " decision matches actual edit", row["decision_matches_actual_mutation"])
    for row in score_rows:
        label = row["session"]
        for name, passed in row["checks"].items():
            check(label + " " + name, passed)
        for name, artifact in row["artifacts"].items():
            verify_identity(label + " final artifact " + name, artifact)
    for path in sorted(HERE.glob("*.py")):
        ast.parse(path.read_text(encoding="utf8"), filename=str(path))
        check("AST " + path.name, True)
    cleanup = read("PROCESS_CLEANUP.json")
    check("owned runtime processes absent", cleanup["query_succeeded"] and cleanup["owned_process_count"] == 0)
    record = dict(status="pass" if all(row["passed"] for row in checks) else "fail", checks=checks,
        passed=sum(row["passed"] for row in checks), total=len(checks), selected_default=selected["default"],
        restoration_outcomes=[dict(session=row["session"], passed=row["restoration_quality_pass"], technical=row["technical_status"])
                              for row in score_rows],
        business_outcome_scope="Artifact integrity and fixed restoration outcomes are recorded separately. No artistic or cross-case generalization score.",
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu, Pro_calls=0, Blender_calls=0)
    write("DELIVERY_VERIFICATION.json", record)
    print({key: record[key] for key in ("status", "passed", "total", "wall_s")})
    if record["status"] != "pass":
        raise SystemExit(1)


def manifest():
    files = [identity(path) for path in sorted(HERE.rglob("*"))
             if path.is_file() and path.name not in {"MANIFEST.json", "HANDOFF.json"}]
    write("MANIFEST.json", dict(cycle_id="M6-MATCHED-REFINE-003", files=files, file_count=len(files),
        bytes=sum(row["bytes"] for row in files),
        scope="All local batch evidence, including private models, PNGs, NPZs and raw consumer logs. MANIFEST itself and ignored post-commit HANDOFF are excluded.",
        Git_delivery="Root scripts and summaries are committed. Large private data is retained locally with individual SHA256 identities.",
        original=read("CASE_BINDING.json")["original"]))
    print(dict(files=len(files), bytes=sum(row["bytes"] for row in files)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("verify", "manifest"))
    options = parser.parse_args()
    {"verify": verify, "manifest": manifest}[options.action]()
