"""Admin-only grading of immutable answers and current-session evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
SLOTS = ("N1", "P1", "P2", "N2", "N3", "P3")


class Grader:
    def __init__(self, truth):
        self.truth = truth
        self.inputs = {}
        self.targets = {row["object_name"]: row for row in truth["targets"]}
        self.aliases = {}
        for name, target in self.targets.items():
            self.aliases[name] = name
            self.aliases[target["roi_id"]] = name
            self.aliases["object_index:" + str(target["object_index"])] = name

    def raw(self, path):
        path = Path(path).resolve()
        value = path.read_bytes()
        self.inputs[str(path)] = hashlib.sha256(value).hexdigest()
        return value

    def read(self, path):
        return json.loads(self.raw(path).decode("utf-8-sig"))

    def identity(self, value):
        if type(value) is int:
            value = "object_index:" + str(value)
        return self.aliases.get(value) if type(value) is str else None

    def artifact(self, owner, value, digest):
        path = Path(value)
        path = path.resolve() if path.is_absolute() else (owner / path).resolve()
        if not path.is_relative_to(owner.resolve()):
            raise ValueError("evidence_outside_current_session")
        content = self.raw(path)
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("current_artifact_SHA_mismatch")
        return path, content

    def frames(self, owner, outer):
        observations = self.read(owner / "OBSERVATIONS.json")
        if observations["schema"] != "active-coverage-consumption-001-observations-v1":
            raise ValueError("observation_schema")
        binding = observations["source_inputs"]
        for key, wanted in self.truth["source_binding"].items():
            if binding[key] != wanted:
                raise ValueError("observation_source_" + key)
        attempts = observations["render_attempts"]
        if len(attempts) > 6 or len({row["view_name"] for row in attempts}) != len(attempts):
            raise ValueError("unique_six_view_attempt_budget")
        attempt_map = {row["attempt_id"]: row for row in attempts}
        if len(attempt_map) != len(attempts):
            raise ValueError("duplicate_render_attempt_identity")
        evidence = {}
        for frame in observations["frames"]:
            view = frame["view_name"]
            attempt = attempt_map[frame["attempt_id"]]
            if frame["ref"] in evidence or view not in self.truth["views"]:
                raise ValueError("frame_ref_or_view_identity")
            if frame["status"] != "completed" or attempt["view_name"] != view or attempt["ref"] != frame["ref"]:
                raise ValueError("frame_attempt_binding")
            times = [attempt[key] for key in ("intent_ns", "render_started_ns", "render_closed_ns", "completed_ns")]
            if any(type(value) is not int for value in times) or times != sorted(times):
                raise ValueError("render_attempt_time_order")
            if not outer["started_ns"] <= times[0] <= times[-1] < outer["deadline_ns"]:
                raise ValueError("frame_outside_original_slot_window")
            _, png = self.artifact(owner, frame["PNG"], frame["PNG_sha256"])
            npz_path, _ = self.artifact(owner, frame["NPZ"], frame["NPZ_sha256"])
            _, metadata = self.artifact(owner, frame["metadata_path"], frame["metadata_sha256"])
            saved = json.loads(metadata)
            if saved["ref"] != frame["ref"] or saved["view_name"] != view:
                raise ValueError("frame_metadata_identity")
            baseline = self.truth["baseline_frames"][view]
            if hashlib.sha256(png).hexdigest() != baseline["PNG_sha256"]:
                raise ValueError("fixed_scene_generated_PNG_differs")
            with np.load(npz_path, allow_pickle=False) as archive:
                if set(archive.files) != {"color", "depth", "owners"}:
                    raise ValueError("frame_array_keys")
                arrays = {name: archive[name] for name in archive.files}
            for name, array in arrays.items():
                actual = {"dtype": str(array.dtype), "dtype_str": array.dtype.str,
                          "shape": list(array.shape), "nbytes": array.nbytes,
                          "sha256": hashlib.sha256(array.tobytes(order="C")).hexdigest()}
                if frame["arrays"][name] != actual or baseline["arrays"][name] != actual:
                    raise ValueError("current_raw_array_binding_" + name)
            color, owners = arrays["color"], arrays["owners"]
            with Image.open(Path(frame["PNG"]) if Path(frame["PNG"]).is_absolute() else owner / frame["PNG"]) as image:
                if image.mode != "RGB" or image.size != (512, 512) or image.tobytes() != color.tobytes(order="C"):
                    raise ValueError("PNG_and_current_RGB_disagree")
            boundary = np.zeros(owners.shape, dtype=bool)
            difference = color[1:].astype(np.int32) - color[:-1].astype(np.int32)
            changed = (owners[1:] != owners[:-1]) & ((difference * difference).sum(axis=2) >= 24 * 24)
            boundary[1:] |= changed
            boundary[:-1] |= changed
            difference = color[:, 1:].astype(np.int32) - color[:, :-1].astype(np.int32)
            changed = (owners[:, 1:] != owners[:, :-1]) & ((difference * difference).sum(axis=2) >= 24 * 24)
            boundary[:, 1:] |= changed
            boundary[:, :-1] |= changed
            measured = {}
            for name, target in self.targets.items():
                mask = owners == target["object_index"]
                surface = int(np.count_nonzero(mask))
                edge = int(np.count_nonzero(mask & boundary))
                expected = target["by_view"][view]
                if surface != expected["visible_surface_pixels"] or edge != expected["contrasting_boundary_pixels"]:
                    raise ValueError("fixed_pixel_counts_disagree")
                measured[name] = {"surface": surface, "boundary": edge,
                                  "valid": bool(expected["geometry_complete"] and expected["front_facing"]
                                                and surface >= 16 and edge >= 4)}
            for row in frame.get("pixel_rows", []):
                name = self.identity(row["roi_id"])
                if name is None or row["object_index"] != self.targets[name]["object_index"]:
                    raise ValueError("published_pixel_identity")
                current = measured[name]
                front = self.targets[name]["by_view"][view]["front_facing"]
                if (row["visible_surface_pixels"] != current["surface"]
                        or row["contrasting_boundary_pixels"] != current["boundary"]
                        or row["front_facing"] != front
                        or row["readable"] != bool(front and current["surface"] >= 16 and current["boundary"] >= 4)):
                    raise ValueError("published_pixel_fact_disagrees")
            evidence[frame["ref"]] = {"view": view, "targets": measured, "PNG_sha256": frame["PNG_sha256"]}
        return evidence, len(attempts)

    def reason_valid(self, panel, target):
        code = panel.get("reason_code")
        if code == "finite_pool_no_complete_readable_view":
            return True
        facts = list(target["by_view"].values())
        return ((code == "positive_area_occlusion_all_views" and all(row["positive_area_blockers"] for row in facts))
                or (code == "back_facing_all_views" and all(not row["front_facing"] for row in facts))
                or (code == "outside_viewport_all_views" and all(not row["inside_viewport"] for row in facts)))

    def panels(self, rows, answer, evidence):
        names = [self.identity(row.get("object")) for row in rows]
        counts = Counter(name for name in names if name is not None)
        result = {"target_missing": sorted(set(self.targets) - set(counts)),
                  "target_extra": [row.get("object") for row, name in zip(rows, names) if name is None],
                  "duplicate_targets": sorted(name for name, count in counts.items() if count > 1),
                  "valid_covered": [], "invalid_covered": [], "coverable_without_evidence": [],
                  "uncovered_reason_invalid": [], "unknown_overclaim": [], "normalization_errors": []}
        for row, name in zip(rows, names):
            excerpt = row.get("excerpt", "")
            if not excerpt or excerpt not in answer:
                result["normalization_errors"].append({"object": row.get("object"), "reason": "excerpt_not_in_raw_answer"})
            if name is None:
                continue
            target = self.targets[name]
            status = row.get("status")
            if status not in ("covered", "uncovered", "unknown"):
                result["normalization_errors"].append({"object": name, "reason": "unknown_status"})
                continue
            if status == "covered":
                claims = row.get("views", [])
                valid = bool(claims) and bool(target["valid_views"])
                for claim in claims:
                    frame = evidence.get(claim.get("ref"))
                    valid = bool(valid and frame and claim.get("view", frame["view"]) == frame["view"]
                                 and frame["targets"][name]["valid"])
                result["valid_covered" if valid else "invalid_covered"].append(name)
                if not target["valid_views"]:
                    result["unknown_overclaim"].append(name)
            elif target["valid_views"]:
                result["coverable_without_evidence"].append(name)
            else:
                reason = row.get("reason", "")
                if not reason or reason not in answer or not self.reason_valid(row, target):
                    result["uncovered_reason_invalid"].append(name)
        result["fully_qualified"] = not any(result[key] for key in result if key != "valid_covered")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalized", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, default=BATCH / "r")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    truth_path = HERE / "TRUTH.json"
    truth = json.loads(truth_path.read_text(encoding="utf-8-sig"))
    grader = Grader(truth)
    grader.raw(truth_path)
    grader.raw(__file__)
    grader.read(HERE / "SCORING_SCHEMA.json")
    normalized = grader.read(args.normalized)
    if normalized["schema"] != "active-coverage-consumption-001-normalized-v1":
        raise ValueError("normalized_schema")
    slots = normalized["slots"]
    if len(slots) != 6 or {row["slot_id"] for row in slots} != set(SLOTS):
        raise ValueError("exact_six_unique_normalized_slots")
    rows = {row["slot_id"]: row for row in slots}
    runtime = grader.read(args.runtime_root / "RUN_RESULT.json")
    records = {row["slot"]: row for row in runtime["records"]}
    if len(runtime["records"]) != 6 or set(records) != set(SLOTS):
        raise ValueError("exact_six_runtime_slots")
    scores = []
    for slot in SLOTS:
        outer, normalized_row = records[slot], rows[slot]
        score = {"slot_id": slot, "group": outer["group"], "execution_state": outer["execution_state"],
                 "execution_evidence_valid": False, "fully_qualified": False, "evidence_errors": []}
        if outer["execution_state"] == "not_run":
            score["reason"] = "not_run"
            scores.append(score)
            continue
        try:
            answer_path = normalized_row.get("raw_answer_path")
            if not answer_path:
                raise ValueError("no_complete_raw_answer")
            answer_path = Path(answer_path)
            answer_path = answer_path.resolve() if answer_path.is_absolute() else (BATCH / answer_path).resolve()
            if not answer_path.is_relative_to(BATCH.resolve()):
                raise ValueError("raw_answer_outside_current_batch")
            answer_raw = grader.raw(answer_path)
            if hashlib.sha256(answer_raw).hexdigest() != normalized_row["raw_answer_sha256"]:
                raise ValueError("normalized_answer_SHA")
            authoritative = grader.raw(args.runtime_root / slot / "c/PUBLIC_FINAL.txt")
            if authoritative != answer_raw:
                raise ValueError("normalized_answer_differs_from_slot_original")
            evidence, count = grader.frames(args.runtime_root / slot / "o", outer)
            execution_ok = bool(outer["execution_state"] == "completed" and outer["outer_valid_completion"]
                and outer["consumer_safe_to_continue"] and not outer["common_image_faults"]
                and outer["runtime_binding"]["confirmed"] and outer["runtime_exit"]["confirmed"]
                and outer["owner_process_cleanup"]["confirmed"] and outer["consumer_process_cleanup"]["confirmed"]
                and outer["actual_tool_calls"] <= 12 and count <= 6)
            score.update(grader.panels(normalized_row["panels"], answer_raw.decode("utf-8"), evidence))
            score["execution_evidence_valid"] = execution_ok
            score["fully_qualified"] = score["fully_qualified"] and execution_ok
            score["raw_answer_sha256"] = normalized_row["raw_answer_sha256"]
            score["frame_count"] = len(evidence)
            score["render_attempts"] = count
        except (OSError, ValueError, KeyError, TypeError) as error:
            score["evidence_errors"].append({"type": type(error).__name__, "message": str(error)})
        scores.append(score)
    totals = {group: {"planned": 3, "fully_qualified": sum(row["fully_qualified"] for row in scores if row["group"] == group)}
              for group in ("N", "P")}
    output = {"schema": "active-coverage-consumption-001-quality-v1", "scoring_role": normalized.get("scoring_role", "unspecified"),
              "slots": scores, "groups": totals, "all_six_quality_complete": all(row["fully_qualified"] for row in scores),
              "P_quality_not_lower_N": totals["P"]["fully_qualified"] >= totals["N"]["fully_qualified"],
              "quality_comparison_scope": "Fully qualified slot counts out of three per route. Complete paired costs require all six quality-complete slots.",
              "cost_analysis_performed": False, "minimum_view_count_graded": False,
              "inputs_sha256": dict(sorted(grader.inputs.items()))}
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"quality_file": str(args.output), "groups": totals,
                      "all_six_quality_complete": output["all_six_quality_complete"]}))


if __name__ == "__main__":
    main()
