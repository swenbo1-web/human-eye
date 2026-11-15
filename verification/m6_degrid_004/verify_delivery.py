"""Verify the single frozen target, two actual trials and local evidence inventory."""

import argparse
import ast
import hashlib
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

    def check_identity(name, expected):
        actual = identity(HERE / expected["path"])
        check(name, actual["bytes"] == expected["bytes"] and actual["sha256"] == expected["sha256"])

    for row in read("PLAN_FREEZE.json")["files"]:
        check_identity("frozen input " + row["path"], row)
    for row in read("TOOL_FREEZE.json")["files"]:
        check_identity("exact executed archive " + row["path"], row["archived"])
        check_identity("same current runtime " + row["path"], row)
    case = read("CASE_BINDING.json")
    check_identity("original asset", case["original"])
    for row in case["source_files"]:
        check_identity("fixed source " + row["path"], row)
    with np.load(HERE / case["public_initial"]["path"], allow_pickle=False) as archive:
        public = dict(archive)
    with np.load(HERE / case["actual_initial_readback"]["path"], allow_pickle=False) as archive:
        actual = dict(archive)
    with np.load(HERE / case["normal_readback"]["path"], allow_pickle=False) as archive:
        normal = dict(archive)
    with np.load(HERE / case["private_score_target"]["path"], allow_pickle=False) as archive:
        target = dict(archive)
    for key, value in actual.items():
        check("public actual current " + key, public[key].shape == value.shape and public[key].dtype == value.dtype
              and public[key].tobytes() == value.tobytes())
    expected_fields = {"vertices", "vertices_world", "vertices_local", "matrix_world", "faces", "source_ids",
        "poly_offsets", "poly_vertices", "triangle_polygon_ids", "F_source_ids", "I_ids", "protected_ids",
        "B0_ids", "B1_ids", "local_edges", "n0"}
    check("public field allowlist", set(public) == expected_fields)
    check("normals from actual current", np.array_equal(public["n0"], current_normals(actual["vertices_world"], actual["faces"])))
    check("target is actual new normal", np.array_equal(target["clean_vertices_world"], normal["vertices_world"]))
    check("baseline is actual new current", np.array_equal(target["initial_vertices_world"], actual["vertices_world"]))
    check("fixed 410 and 274 domains", len(public["F_source_ids"]) == 410 and len(public["I_ids"]) == 274)
    check("fixed private support 47", len(target["support_ids"]) == 47 and np.isin(target["support_ids"], public["I_ids"]).all())
    noise = np.load(HERE / "private/construction/noise.npy", allow_pickle=False)
    noise_sha = hashlib.sha256(noise.tobytes()).hexdigest()
    check("fixed noise SHA", noise_sha == "cd8e84d38618d3de642a7023ea02d3244a61d3353a94582747130fd12118e5fb")
    outside_F = np.setdiff1d(actual["source_ids"], public["F_source_ids"])
    check("zero exterior perturbation", np.count_nonzero(noise[outside_F]) == 0)
    check("two fixed budgets", case["budget_m"] == 0.006893660855829761)
    for filename in ("CONSTRUCTION_GEOMETRY_QA.json", "QUALITY_PREFLIGHT.json", "API_PREFLIGHT.json",
                     "CONSUMER_PREFLIGHT.json", "CONSUMER_CASE_PREFLIGHT.json", "CONSUMER_PREVIEW_PREFLIGHT.json",
                     "CONSUMER_PUBLIC_INPUT_AUDIT.json", "DELIVERY_HELPER_PREFLIGHT.json",
                     "PREVIEW_PIXEL_VERIFICATION.json"):
        check("preflight " + filename, read(filename)["status"] == "pass")
    costs = read("COSTS.json")
    check("complete two-session cost snapshot", not costs["partial"] and costs["actual_Pro"]["started"] == 2
          and costs["actual_Pro"]["completed"] == 2)
    check("twenty actual Blender jobs", costs["actual_Blender"]["calls"] == 20)
    check("twenty-four delivered image blocks", costs["actual_consumer_delivery"]["delivery"]["totals"]["public_image_count"] == 24)
    stats = read("CONSUMER_STATS_run.json")
    check("two terminal actual trials", stats["totals"]["sessions"] == stats["totals"]["terminal_sessions"] == 2)
    rows = read("FINAL_VERIFICATION.json")["sessions"]
    check("two final actual saved exports", len(rows) == 2)
    for row in rows:
        for name, value in row["checks"].items():
            check(row["session"] + " " + name, value)
        for name, artifact in row["artifacts"].items():
            check_identity(row["session"] + " " + name, artifact)
    first = HERE / "private/consumers/run/repair/facts/PROMPT.txt"
    second = HERE / "private/consumers/run/repair/native/PROMPT.txt"
    check("same task prompt across both routes", first.read_bytes() == second.read_bytes())
    for path in sorted(HERE.glob("*.py")):
        ast.parse(path.read_text(encoding="utf8"), filename=str(path))
        check("AST " + path.name, True)
    cleanup = read("PROCESS_CLEANUP.json")
    check("owned runtime processes absent", cleanup["query_succeeded"] and cleanup["owned_process_count"] == 0)
    result = dict(status="pass" if all(row["passed"] for row in checks) else "fail", checks=checks,
        passed=sum(row["passed"] for row in checks), total=len(checks),
        actual_restoration_outcomes=[dict(session=row["session"], technical=row["technical_status"],
            quality_pass=row["restoration_quality_pass"], metrics=row["metrics"], normal_editable_misedit=row["normal_editable_misedit"])
            for row in rows],
        integrity_scope="Frozen-source and actual-file identity checks. Repair and technical quality are recorded as experimental outcomes.",
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu, Pro_calls=0, Blender_calls=0)
    write("DELIVERY_VERIFICATION.json", result)
    print({key: result[key] for key in ("status", "passed", "total", "wall_s")})
    if result["status"] != "pass":
        raise SystemExit(1)


def manifest():
    files = [identity(path) for path in sorted(HERE.rglob("*"))
             if path.is_file() and path.name not in {"MANIFEST.json", "HANDOFF.json"}]
    result = dict(cycle_id="M6-DEGRID-004", files=files, file_count=len(files), bytes=sum(row["bytes"] for row in files),
        scope="All local batch evidence. The manifest itself and ignored post-commit HANDOFF are excluded.",
        Git_delivery="Root public scripts and reports are committed. Large private evidence remains local with per-file SHA256 identities.",
        original=read("CASE_BINDING.json")["original"])
    write("MANIFEST.json", result)
    print(dict(files=len(files), bytes=result["bytes"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("verify", "manifest"))
    options = parser.parse_args()
    {"verify": verify, "manifest": manifest}[options.action]()
