"""Inventory the frozen M6 baseline without importing or running product code."""
from __future__ import annotations

import ast
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
BASE = "7d42bb939c7881a98fe322c10c216398f6c7aecc"
ACCEPTED_M6 = "d01d49bc0ec82583b24a8faf22e622e6f6ea8c5d"
PRODUCT_FILES = [
    "human_eye_plugin/arm_twist_expert.py",
    "human_eye_plugin/arm_twist_weights.py",
    "human_eye_plugin/arm_twist_source.py",
    "human_eye_plugin/arm_twist_correction.py",
]
HISTORY = Path("D:/hefe/verification/fixes/20261109_architecture_completion")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git_bytes(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def inventory(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": digest(data)}


def scalar_count(value):
    if isinstance(value, list):
        return sum(scalar_count(item) for item in value)
    if isinstance(value, (int, float)):
        return 1
    raise TypeError(type(value).__name__)


def main():
    sources = []
    for rel in PRODUCT_FILES:
        base = git_bytes("show", f"{BASE}:{rel}")
        accepted = git_bytes("show", f"{ACCEPTED_M6}:{rel}")
        current = (ROOT / rel).read_bytes()
        # Git may check out CRLF; record raw bytes as well as canonical Git bytes.
        matches = current.replace(b"\r\n", b"\n") == base.replace(b"\r\n", b"\n")
        if not matches:
            raise RuntimeError(f"Product source changed from fixed baseline: {rel}")
        sources.append({
            "path": rel, "working_bytes": len(current),
            "working_sha256": digest(current), "base_git_sha256": digest(base),
            "working_matches_base_except_line_endings": matches,
            "base_matches_accepted_m6_bytes": base == accepted,
        })

    module = ast.parse((ROOT / PRODUCT_FILES[1]).read_text(encoding="utf-8"))
    weights = next(
        ast.literal_eval(node.value) for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "PARAMETERS"
                for target in node.targets)
    )
    data_path = ROOT / "verification/m6_arm_expert_001/run_01/dataset.json.gz"
    raw_data = gzip.decompress(data_path.read_bytes())
    dataset = json.loads(raw_data)
    author_path = ROOT / "verification/m6_arm_expert_001/run_01/result.json"
    author = json.loads(author_path.read_text(encoding="utf-8"))
    final_path = ROOT / "verification/m6_arm_expert_001/final/result.json"
    author_final = json.loads(final_path.read_text(encoding="utf-8"))
    if digest(raw_data) != weights["training"]["dataset_sha256"]:
        raise RuntimeError("Dataset differs from weight training declaration")
    splits = {}
    asset_sets = {}
    for split in ("train", "validation", "test"):
        cases = [case for case in dataset if case["metadata"]["split"] == split]
        asset_sets[split] = {case["metadata"]["asset_id"] for case in cases}
        splits[split] = {
            "assets": len(asset_sets[split]), "cases": len(cases),
            "sections": sum(len(case["packet"]["sections"]) for case in cases),
            "positive_cases_at_0_15": sum(max(case["label_severity"]) >= .15 for case in cases),
            "positive_sections_at_0_15": sum(value >= .15 for case in cases for value in case["label_severity"]),
            "pose_families": dict(sorted(Counter(case["metadata"]["pose_family"] for case in cases).items())),
        }
    if {key: value["cases"] for key, value in splits.items()} != author["cases"]:
        raise RuntimeError("Saved report and actual dataset split counts differ")
    history_names = [
        "M6_ARM_EXPERT_001_REVIEW.md", "M6_ARM_EXPERT_OPT_001_REVIEW.md",
        "M6_ARM_SOURCE_OPT_001_REVIEW.md", "ARCH_EXPERT_ENTRY_OPT_001_REVIEW.md",
        "ARM_CORRECTION_PREVIEW_OPT_001_REVIEW.md",
        "ARM_CORRECTION_EXECUTION_OPT_001_REVIEW.md", "ARCHITECTURE_STAGE_CLOSEOUT.md",
    ]
    result = {
        "schema": "m6-planning-baseline-v1", "review_date": "2026-11-14",
        "base_commit": BASE, "accepted_m6_commit": ACCEPTED_M6,
        "owner_thread": "01a1d986-24a4-73f1-9689-6845d1f01ef3",
        "branch": "codex/m6-candidate-value", "product_sources": sources,
        "actual_inspection_this_run": {
            "method": "stdlib AST/JSON/gzip/hash inspection; no product imports",
            "parameter_count": sum(scalar_count(weights[key]) for key in ("w1", "b1", "w2", "b2")),
            "model_id": weights["model_id"], "feature_names": weights["feature_names"],
            "dataset_raw_bytes": len(raw_data), "dataset_raw_sha256": digest(raw_data),
            "splits": splits,
            "asset_id_overlap_between_splits": {
                f"{left}:{right}": sorted(asset_sets[left] & asset_sets[right])
                for left, right in (("train", "validation"), ("train", "test"), ("validation", "test"))
            },
            "scope_of_split_check": "asset IDs only; actual rest/weight signatures and feature duplicates were audited in the historical root review, not recomputed here",
        },
        "historical_author_results_not_rerun": {
            "source": str(author_path), "test_metrics": author["results"]["test"],
            "original_component_timing": author["timing"],
            "original_final_tests": {key: author_final[key] for key in ("tests", "failures", "errors")},
            "timing_scope": "original pre-optimization implementation; not current-version timing or a matched prepared-geometry comparison",
        },
        "evidence_files": [inventory(data_path), inventory(author_path), inventory(final_path)]
            + [inventory(HISTORY / name) for name in history_names],
        "new_runs_this_phase": {"training": 0, "inference": 0, "blender": 0, "llm_consumer": 0, "paid_api": 0, "performance_benchmark": 0},
        "decision": "Plan task-conditioned candidate scoring; first measure candidate coverage and opportunity against an equally prepared direct geometry baseline. Current learned net benefit remains unproven.",
    }
    output = Path(__file__).with_name("BASELINE.json")
    output.write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"output": str(output), "parameters": result["actual_inspection_this_run"]["parameter_count"], "splits": splits, "all_four_sources_match_accepted_m6": all(item["base_matches_accepted_m6_bytes"] for item in sources)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
