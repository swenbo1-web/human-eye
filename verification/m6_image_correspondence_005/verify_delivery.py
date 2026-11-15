"""Verify fixed inputs, exact stage archives and actual four-session evidence."""

import argparse
import ast
import hashlib
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
import numpy as np


def verify():
    started, cpu = time.perf_counter(), time.process_time()
    checks = []

    def check(name, passed):
        checks.append(dict(name=name, passed=bool(passed)))

    def check_identity(name, expected):
        actual = identity(HERE / expected["path"])
        check(name, actual["bytes"] == expected["bytes"] and actual["sha256"] == expected["sha256"])

    for row in read("PLAN_FREEZE.json")["files"]:
        check_identity("common frozen input " + row["path"], row)
    for snapshot_name in ("STAGE_V1_SNAPSHOT.json", "STAGE_V1_REFERENCES_SNAPSHOT.json", "STAGE_V2_SNAPSHOT.json"):
        for row in read(snapshot_name)["files"]:
            check_identity(snapshot_name + " " + row["path"], row)
    stages = {}
    for stage in ("v1", "v2"):
        frozen = read("TOOL_FREEZE_" + stage + ".json")
        stages[stage] = {row["path"]: row for row in frozen["files"] if row["path"].endswith(".py")}
        for row in frozen["files"]:
            check_identity(stage + " executed source archive " + row["path"], row["archived"])
            if stage == "v2":
                check_identity("current final source " + row["path"], row)
        for row in frozen["validation"]:
            check_identity(stage + " archived preflight " + row["archived"]["path"], row["archived"])
            check(stage + " preflight pass " + row["archived"]["path"], read(row["archived"]["path"])["status"] == "pass")
    all_source_paths = sorted(set(stages["v1"]) | set(stages["v2"]))
    changes = [path for path in all_source_paths if stages["v1"].get(path, {}).get("sha256") != stages["v2"].get(path, {}).get("sha256")]
    check("optimization changes disclosed", set(changes) == set(read("OPTIMIZATION_BINDING.json")["changed_runtime_files"]))
    case = read("CASE_BINDING.json")
    check_identity("original asset unchanged", case["original"])
    for row in case["source_files"]:
        check_identity("fixed source " + row["path"], row)
    for row in case["reused_files"]:
        check_identity("fixed reused original " + row["source"]["path"], row["source"])
        check_identity("exact reused copy " + row["copied"]["path"], row["copied"])
    with np.load(HERE / case["normal_readback"]["path"], allow_pickle=False) as normal, np.load(HERE / case["public_initial"]["path"], allow_pickle=False) as initial, np.load(HERE / case["private_score_target"]["path"], allow_pickle=False) as target:
        check("target equals actual saved normal", np.array_equal(target["clean_vertices_world"], normal["vertices_world"]))
        check("baseline equals actual initial", np.array_equal(target["initial_vertices_world"], initial["vertices_world"]))
        check("fixed 410 274 47 denominators", len(initial["F_source_ids"]) == 410 and len(initial["I_ids"]) == 274 and len(target["support_ids"]) == 47)
    stats = read("CONSUMER_STATS_all.json")
    check("four terminal consumers", stats["totals"]["sessions"] == stats["totals"]["terminal_sessions"] == 4)
    costs = read("COSTS.json")
    check("four actual started consumers", costs["actual_Pro"]["started"] == costs["actual_Pro"]["terminal"] == 4)
    check("complete costs", not costs["partial"] and not costs["incomplete"])
    final = read("FINAL_VERIFICATION.json")["sessions"]
    check("four final actual saved exports", len(final) == 4)
    for row in final:
        for name, passed in row["checks"].items():
            check(row["session"] + " " + name, passed)
        for name, artifact in row["artifacts"].items():
            check_identity(row["session"] + " final " + name, artifact)
    prompts = [HERE / "private/consumers" / stage / "repair" / route / "PROMPT.txt"
        for stage, route in (("v1", "native"), ("v1", "facts"), ("v2", "facts"), ("v2", "native"))]
    check("shared task prompt across all four sessions", len({hashlib.sha256(path.read_bytes()).hexdigest() for path in prompts}) == 1)
    for name in ("CORRESPONDENCE_SCORE.json", "RAY_PREFLIGHT.json", "IMAGE_PIXEL_PREFLIGHT.json"):
        check("final component preflight " + name, read(name)["status"] == "pass")
    cleanup = read("PROCESS_CLEANUP.json")
    check("owned runtime processes absent", cleanup["query_succeeded"] and cleanup["owned_process_count"] == 0)
    for path in sorted(HERE.glob("*.py")):
        ast.parse(path.read_text(encoding="utf8"), filename=str(path))
        check("AST " + path.name, True)
    result = dict(cycle_id="M6-IMAGE-CORRESPONDENCE-005", status="pass" if all(row["passed"] for row in checks) else "fail",
        passed=sum(row["passed"] for row in checks), total=len(checks), checks=checks,
        restoration_outcomes=[dict(session=row["session"], technical=row["technical_status"], quality_pass=row["restoration_quality_pass"], metrics=row["metrics"]) for row in final],
        changed_runtime_files=changes, scope="Frozen input and executed archive integrity. Module, consumer self-assessment, technical quality and independent restoration outcomes retain their separate records.",
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu, actual_Pro_calls=0, actual_Blender_calls=0)
    write("DELIVERY_VERIFICATION.json", result)
    print({key: result[key] for key in ("status", "passed", "total", "wall_s")})
    if result["status"] != "pass":
        raise SystemExit(1)


def manifest():
    files = [identity(path) for path in sorted(HERE.rglob("*"))
        if path.is_file() and path.name not in {"MANIFEST.json", "HANDOFF.json"}]
    write("MANIFEST.json", dict(cycle_id="M6-IMAGE-CORRESPONDENCE-005", files=files, file_count=len(files),
        bytes=sum(row["bytes"] for row in files), original=read("CASE_BINDING.json")["original"],
        scope="All batch-local evidence except this manifest and the ignored postcommit HANDOFF.",
        Git_delivery="Root public code and reports committed. Large private evidence retained locally with exact identities."))
    print(dict(files=len(files), bytes=sum(row["bytes"] for row in files)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("verify", "manifest"))
    options = parser.parse_args()
    {"verify": verify, "manifest": manifest}[options.action]()
