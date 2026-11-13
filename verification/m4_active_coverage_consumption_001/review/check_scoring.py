"""Pure scoring controls using static truth and synthetic reference facts."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
SCORER = BATCH / "admin/score_answers.py"
TRUTH = BATCH / "admin/TRUTH.json"


def main():
    specification = importlib.util.spec_from_file_location("admin_scorer_check", SCORER)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    truth = json.loads(TRUTH.read_text(encoding="utf-8-sig"))
    grader = module.Grader(truth)
    evidence = {}
    for view in truth["views"]:
        evidence["ref:" + view] = {"view": view, "targets": {
            target["object_name"]: {"valid": view in target["valid_views"]}
            for target in truth["targets"]}}
    panels = []
    for target in truth["targets"]:
        views = []
        if target["valid_views"]:
            view = target["valid_views"][0]
            views = [{"view": view, "ref": "ref:" + view}]
        panels.append({"object": target["object_name"],
                       "status": "covered" if views else "unknown", "views": views,
                       "reason": "within registered finite pool",
                       "reason_code": "finite_pool_no_complete_readable_view",
                       "excerpt": target["object_name"]})
    answer = " ".join(target["object_name"] for target in truth["targets"])
    answer += " within registered finite pool"
    checks = []

    def check(name, rows, expected):
        result = grader.panels(rows, answer, evidence)
        checks.append({"check": name, "passed": result["fully_qualified"] is expected})

    check("arbitrary_valid_view_set_passes", panels, True)
    changed = copy.deepcopy(panels)
    for panel in changed:
        panel.update(status="unknown", views=[])
    check("all_unknown_does_not_complete", changed, False)
    check("missing_target_rejected", panels[:-1], False)
    check("extra_target_rejected", panels + [{
        "object": "unregistered_object", "status": "unknown", "excerpt": "Obj"}], False)
    check("duplicate_target_rejected", panels + [copy.deepcopy(panels[0])], False)
    changed = copy.deepcopy(panels)
    next(panel for panel in changed if panel["status"] == "covered")["views"][0]["ref"] = "old-session-ref"
    check("foreign_or_missing_ref_rejected", changed, False)
    changed = copy.deepcopy(panels)
    next(panel for panel in changed if panel["status"] == "unknown")["reason_code"] = "unknown"
    check("unscoped_uncovered_reason_rejected", changed, False)
    result = {
        "passed": all(row["passed"] for row in checks), "checks": checks,
        "scope": "Pure panel grading. Synthetic reference facts exercise scoring decisions without frame IO, solver, renderer or model calls.",
        "score_answers_sha256": hashlib.sha256(SCORER.read_bytes()).hexdigest(),
        "TRUTH_sha256": hashlib.sha256(TRUTH.read_bytes()).hexdigest(),
        "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "new_render_model_calls": 0,
    }
    (HERE / "SCORING_CHECKS.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "checks": len(checks), "new_render_model_calls": 0}))


if __name__ == "__main__":
    main()
