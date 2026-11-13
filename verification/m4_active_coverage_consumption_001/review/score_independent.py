"""Independent normalization and post-run factual review of six saved answers."""
import copy
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
SCORER = BATCH / "admin/score_answers.py"
SLOTS = ("N1", "P1", "P2", "N2", "N3", "P3")
PIXEL_FIELDS = {
    "surface_pixels": "surface", "owner_surface_pixels": "surface",
    "visible_surface_pixels": "surface", "boundary_pixels": "boundary",
    "contrasting_boundary_pixels": "boundary",
}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def original_panels(text):
    """Keep each complete original panel object as its exact excerpt."""
    decoded = json.loads(text)
    position = text.index("[", text.index('"panels"')) + 1
    decoder = json.JSONDecoder()
    panels = []
    for expected in decoded["panels"]:
        while text[position].isspace() or text[position] == ",":
            position += 1
        panel, end = decoder.raw_decode(text, position)
        if panel != expected:
            raise ValueError("original_panel_excerpt_binding")
        normalized = copy.deepcopy(panel)
        normalized["excerpt"] = text[position:end]
        if panel["status"] == "uncovered":
            # All six original reasons were independently read before coding.
            # Each explicitly states positive-area occlusion in the finite pool.
            if panel["object"] != "Obj_006":
                raise ValueError("unreviewed_uncovered_reason")
            normalized["reason_code"] = "positive_area_occlusion_all_views"
        panels.append(normalized)
        position = end
    return panels, decoded


def main():
    frozen = read(BATCH / "FROZEN.json")
    mismatches = [path for path, expected in frozen["runtime_sources"].items() if sha(path) != expected]
    if len(frozen["runtime_sources"]) != 176 or mismatches:
        raise ValueError("frozen_sources_changed")
    normalized_slots = []
    original_objects = {}
    for slot in SLOTS:
        relative = Path("r") / slot / "c/PUBLIC_FINAL.txt"
        path = BATCH / relative
        text = path.read_text(encoding="utf-8")
        panels, original = original_panels(text)
        original_objects[slot] = original
        normalized_slots.append({
            "slot_id": slot, "raw_answer_path": relative.as_posix(),
            "raw_answer_sha256": sha(path), "panels": panels,
        })
    normalized_path = HERE / "NORMALIZED_INDEPENDENT.json"
    normalized = {
        "schema": "active-coverage-consumption-001-normalized-v1",
        "scoring_role": "independent_postrun_review",
        "scope": "Created solely from six slot PUBLIC_FINAL originals. No author normalization was read.",
        "slots": normalized_slots,
    }
    normalized_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("frozen_coverage_admin_scorer", SCORER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    quality_path = HERE / "QUALITY_INDEPENDENT.json"
    previous_argv = sys.argv
    try:
        sys.argv = [str(SCORER), "--normalized", str(normalized_path),
                    "--runtime-root", str(BATCH / "r"), "--output", str(quality_path)]
        module.main()
    finally:
        sys.argv = previous_argv
    quality = read(quality_path)
    truth = read(BATCH / "admin/TRUTH.json")
    grader = module.Grader(truth)
    grader.raw(__file__)
    grader.raw(normalized_path)
    grader.raw(SCORER)
    grader.raw(BATCH / "FROZEN.json")
    for path in frozen["runtime_sources"]:
        grader.raw(path)
    runtime = grader.read(BATCH / "r/RUN_RESULT.json")
    outer_by_slot = {row["slot"]: row for row in runtime["records"]}
    factual_rows = []
    scalar_checks = []
    occluder_checks = []
    for normalized_slot in normalized_slots:
        slot = normalized_slot["slot_id"]
        outer = outer_by_slot[slot]
        evidence, attempts = grader.frames(BATCH / "r" / slot / "o", outer)
        answer = grader.raw(BATCH / "r" / slot / "c/PUBLIC_FINAL.txt").decode("utf-8")
        facts = grader.panels(normalized_slot["panels"], answer, evidence)
        panel_scalar_checks = []
        panel_occluder_checks = []
        for panel in original_objects[slot]["panels"]:
            name = grader.identity(panel["object"])
            for claim in panel.get("views", []):
                frame = evidence[claim["ref"]]
                actual = frame["targets"][name]
                if claim["view"] != frame["view"]:
                    raise ValueError("scalar_view_reference_mismatch")
                for key, measurement in PIXEL_FIELDS.items():
                    if key in claim:
                        check = {"slot_id": slot, "object": name, "view": claim["view"],
                                 "ref": claim["ref"], "field": key, "claimed": claim[key],
                                 "actual": actual[measurement],
                                 "passed": type(claim[key]) is int and claim[key] == actual[measurement]}
                        scalar_checks.append(check)
                        panel_scalar_checks.append(check)
                if "occluder" in claim:
                    blockers = grader.targets[name]["by_view"][claim["view"]]["positive_area_blockers"]
                    check = {"slot_id": slot, "object": name, "view": claim["view"],
                             "claimed_occluder": claim["occluder"],
                             "passed": any(row["occluder"] == claim["occluder"] for row in blockers)}
                    occluder_checks.append(check)
                    panel_occluder_checks.append(check)
        accurate_scalars = all(check["passed"] for check in panel_scalar_checks)
        accurate_blockers = all(check["passed"] for check in panel_occluder_checks)
        factual_rows.append({
            "slot_id": slot, "group": outer["group"], "raw_execution_state": outer["execution_state"],
            "grader_panels_before_execution_AND": facts,
            "explicit_scalar_pixels_correct": accurate_scalars,
            "explicit_occluder_claims_correct": accurate_blockers,
            "factual_complete": facts["fully_qualified"] and accurate_scalars and accurate_blockers,
            "current_session_frames": len(evidence), "render_attempts": attempts,
            "consumer_errors_preserved": outer["consumer_errors"],
        })
    quality["independent_factual_before_execution_AND"] = factual_rows
    quality["factual_groups"] = {
        group: {"planned": 3, "factual_complete": sum(row["factual_complete"] for row in factual_rows if row["group"] == group)}
        for group in ("N", "P")}
    quality["factual_all_six_complete"] = all(row["factual_complete"] for row in factual_rows)
    quality["explicit_scalar_pixel_checks"] = scalar_checks
    quality["explicit_scalar_pixel_checks_passed"] = all(row["passed"] for row in scalar_checks)
    quality["explicit_occluder_checks"] = occluder_checks
    quality["explicit_occluder_checks_passed"] = all(row["passed"] for row in occluder_checks)
    state_counts = Counter(row["execution_state"] for row in runtime["records"])
    quality["raw_execution_counts"] = {state: state_counts[state] for state in ("completed", "failed", "not_run")}
    quality["frozen_source_count_unchanged"] = 176
    quality["frozen_grader_sha256"] = sha(SCORER)
    quality["review_scope"] = "Frozen grader primary fields preserved. Additional raw-answer scalar/occluder facts are separately checked. No execution failure was promoted or scoring source changed."
    quality["cost_gate"] = "blocked_by_two_original_execution_failures"
    quality["independent_review_inputs_sha256"] = dict(sorted(grader.inputs.items()))
    quality_path.write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"factual_groups": quality["factual_groups"], "frozen_fully_qualified": quality["groups"],
                      "scalar_checks": len(scalar_checks), "occluder_checks": len(occluder_checks),
                      "all_six_quality_complete": quality["all_six_quality_complete"],
                      "new_model_renderer_calls": 0}))


if __name__ == "__main__":
    main()
