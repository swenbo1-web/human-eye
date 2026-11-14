"""Read back frozen outputs and compare full/shared facts without re-querying."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main():
    started = time.perf_counter()
    result = json.loads((HERE / "RESULTS.json").read_bytes())
    full = json.loads((HERE / "private/REAL_FULL_RESULTS.json").read_bytes())
    shared = json.loads((HERE / "private/REAL_SHARED_RESULTS.json").read_bytes())
    checks = []

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    check("18 controls passed", result["controls"]["cases"] == result["controls"]["passed"] == 18)
    check("two cache-state regressions rejected", result["cache_regressions"]["cases"] == result["cache_regressions"]["passed"] == 2 and
          all(row["observed"]["joint_status"] == "invalid" for row in result["cache_regressions"]["results"]))
    nan = next(row for row in result["controls"]["results"] if row["name"] == "nonfinite_candidate_invalid")
    check("IEEE NaN sentinel actually decoded", nan["nonfinite_sentinel_decoded"] and nan["observed"]["joint_status"] == "invalid")
    check("common integer frame factor", full["integer_factor_exponent"] == shared["integer_factor_exponent"])
    for stage in ("before_scan", "after_scan"):
        for key in full[stage]:
            if key == "work":
                check(f"{stage} identical work counts", full[stage][key]["counts"] == shared[stage][key]["counts"])
            else:
                check(f"{stage} identical {key}", full[stage][key] == shared[stage][key])
    for key in ("shape", "preservation", "contact_ok", "contact_requirement", "contact_complete", "joint_status",
                "affected_face_ids", "evaluated_face_ids", "scope_complete", "new_pairs", "removed_pairs", "changed_relations"):
        check(f"identical task fact {key}", full[key] == shared[key])
    for stage, public in (("before_scan", "before"), ("after_scan", "candidate")):
        data = full[stage]
        check(f"{stage} complete unordered domain", data["pair_domain"] == 47427421 and
              data["aabb_pruned"] + data["spatial_candidates"] == data["pair_domain"])
        check(f"{stage} all candidates attempted", data["exact_tests"] == data["spatial_candidates"] and data["unstarted_exact_pairs"] == 0)
        check(f"{stage} leaf classification accounting", data["exact_tests"] == data["legal_simplex_pairs"] + data["empty_pairs"] + len(data["intersections"]) + data["unknown_pairs"])
        reference = result["real"]["independent_aabb"][public]
        check(f"{stage} independent AABB hash", digest(data["candidates"]) == reference["pair_sha256"] and reference["matches_bvh"])
        check(f"{stage} degeneracy remains unknown", len(data["degenerate_face_ids"]) == 10 and
              data["pairs_involving_degenerate_faces"] == 8980 and not data["scan_complete"])
    check("real acceptance remains unavailable", result["real"]["task_acceptance_status"] == "unknown_missing_accepted_target" and full["joint_status"] == "unknown")
    check("shared updates exact dependency closure", shared["candidate_preparation"]["converted_vertices"] == 410 and
          shared["candidate_preparation"]["updated_faces"] == 898 and shared["candidate_preparation"]["reused_static_faces"] == 52366)
    for commit in ("7c615212e706994678bb4aeb8b9836928ff8e22a", "ddd541cf087dc2bbec19e551b8fe3820578077ef"):
        paths = subprocess.check_output(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit], cwd=ROOT).decode().splitlines()
        for relative in paths:
            expected = subprocess.check_output(["git", "show", f"{commit}:{relative}"], cwd=ROOT)
            check(f"old committed delivery unchanged {relative}", (ROOT / relative).read_bytes() == expected)
    old = ROOT / "verification/m6_real_data_001"
    main_handoff = json.loads((old / "HANDOFF_MAIN.json").read_bytes())
    references = main_handoff["private_local_evidence"] + [json.loads((old / "COUPLED_CONTEXT.json").read_bytes())["private_context"]]
    for row in references:
        data = Path(row["path"]).read_bytes()
        check(f"old private evidence unchanged {row['path']}", len(data) == row["bytes"] and hashlib.sha256(data).hexdigest() == row["sha256"])
    report = {"status": "passed", "checks": checks, "integer_factor_exponent": full["integer_factor_exponent"],
              "scope": "Output readback and full/shared comparison; no additional geometric query",
              "wall_s_before_publication": time.perf_counter() - started}
    (HERE / "FINAL_VERIFICATION.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"status": "passed", "checks": len(checks), "integer_factor_exponent": full["integer_factor_exponent"]}))


if __name__ == "__main__":
    main()
