"""Archive the bounded revision_003 acceptance; no Blender or model execution."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
AUTHOR = ROOT / "artifacts/llm_entry/preflight_001/revision_003"
REVIEW = ROOT / "artifacts/llm_entry/recheck_root_001"
ARCHIVE = ROOT / "docs/llm_entry_functional_evidence.zip"
DECISION = ROOT / "docs/radical_acceptance_llm_entry_functional.json"
SPEC_SHA = "30b921d6a8f24863b6a1be7aaf9e5ad1e580988db2fc55ea161f0300a8cd50ec"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if ARCHIVE.exists() or DECISION.exists():
        raise SystemExit("Acceptance already archived; inspect it, do not replace history.")
    delivery = json.loads((AUTHOR / "delivery_001/manifest.json").read_text())
    assert sha(AUTHOR / "delivery_001/manifest.json") == "dc44bf3b9d5f024c7acce38bb71bd0b8bf0482e8801662d8e766025a1a092d8a"
    assert sha(AUTHOR / "delivery_001/sources.zip") == delivery["sources_zip_sha256"]
    assert sha(ROOT / "docs/RADICAL_V1_SPEC_REVIEW.md") == SPEC_SHA
    engine = json.loads((ROOT / "docs/radical_acceptance_engine_v1.json").read_text())
    for name, item in engine["production_sources"].items():
        assert sha(ROOT / name) == item["sha256"], name
    implementation = {
        name: digest for name, digest in delivery["source_sha256"].items()
        if name.startswith(("human_eye_fast/", "examples/", "verification/"))
        or name == "human_eye_llm_stdio.py"
    }
    for name, digest in implementation.items():
        assert sha(ROOT / name) == digest, name
    paths = sorted(p for p in AUTHOR.rglob("*") if p.is_file())
    assert len(paths) == 86
    paths += sorted(p for p in REVIEW.iterdir() if p.is_file())
    packaging = REVIEW / "packaging"
    paths += sorted(p for p in packaging.iterdir() if p.is_file())
    for name in ("build_003", "build_004"):
        paths += sorted(p for p in (packaging / name).iterdir() if p.is_file())
    paths += [
        ROOT / "docs/LLM_ENTRY_FUNCTIONAL_REVIEW.md",
        ROOT / "docs/LLM_HOST_PILOT_PROTOCOL.md",
        ROOT / "pyproject.toml",
        Path(__file__).resolve(),
    ]
    assert len(paths) == len(set(paths))
    members = {
        p.relative_to(ROOT).as_posix(): {"bytes": p.stat().st_size, "sha256": sha(p)}
        for p in sorted(paths)
    }
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in members:
            z.write(ROOT / name, name)
        z.writestr("MANIFEST.json", json.dumps(members, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(ARCHIVE) as z:
        assert z.testzip() is None
        for name, item in members.items():
            data = z.read(name)
            assert len(data) == item["bytes"]
            assert hashlib.sha256(data).hexdigest() == item["sha256"]
    decision = {
        "decision": "ACCEPT_E0_E1_FUNCTIONAL_HOST_AND_VALUE_PENDING",
        "review_number": 25,
        "date": "2026-11-06",
        "base_commit": delivery["head"],
        "delivery_manifest_sha256": sha(AUTHOR / "delivery_001/manifest.json"),
        "delivery_sources_zip_sha256": delivery["sources_zip_sha256"],
        "frozen_engine_sources_unchanged": len(engine["production_sources"]),
        "reviewed_source_items": 40,
        "reviewed_native_sources": 33,
        "reviewed_evidence_references": 12,
        "current_implementation_sha256": implementation,
        "r1_r4_closed": True,
        "new_algorithm_optimization": False,
        "cpu_contract_tests_passed": 24,
        "transport_prior_tests_carried": 5,
        "native": {
            "processes": 2, "cases": 5, "passed": 5,
            "independently_recomputed_actual_rna_distances": 10,
            "distance_tolerance_m": 8e-9,
            "max_vertex_receipt_component_residual_m_rounded": 5.464e-10,
            "writes": [1, 1, 0, 1, 1],
            "case_order": ["nonconvex", "parented", "already-reached", "occluded", "parented-rescaled"],
            "numeric_cases_gpu_init_render_close": [0, 0, 0],
            "image_case_gpu_init_render_close": [1, 2, 1],
            "actual_pngs": 2,
            "root_additional_native_processes": 0,
            "prior_batch_0_of_5_fail_preserved": True,
            "gui_initial_visibility_preserved": True,
        },
        "formal_math": {
            "recipes": 14, "synthetic_pairs": 28, "negatives": 13,
            "generic_native_small_seeds": 2, "ordered_intervals": 56,
            "independent_precision_decimal_digits": 90,
            "initial_interval_inversions_preserved": 18,
            "actual_rna_formal_qualification_pending": True,
        },
        "packaging": json.loads((packaging / "build_004/result.json").read_text()),
        "host_accepted": False,
        "llm_task_benefit_accepted": False,
        "formal_protocol_frozen": False,
        "advance_E2": False,
        "next_phase": {
            "owned_gui_processes_max": 1,
            "fresh_real_model_contexts_max": 2,
            "cases": ["numeric", "image"],
            "seconds_per_task_max": 180,
            "model": "gpt-6.1-sol", "reasoning_effort": "ultra",
            "native_and_visual_work": "executable preparation only",
            "default_mcp_changed": False,
            "formal_benefit_run": False,
            "protocol": "docs/LLM_HOST_PILOT_PROTOCOL.md",
        },
        "user_spec_sha256": SPEC_SHA,
        "review": "docs/LLM_ENTRY_FUNCTIONAL_REVIEW.md",
        "root_reports_sha256": {
            p.name: sha(p) for p in REVIEW.glob("*_review.md")
        },
        "evidence_archive": {
            "path": ARCHIVE.relative_to(ROOT).as_posix(),
            "sha256": sha(ARCHIVE), "bytes": ARCHIVE.stat().st_size,
            "file_count_excluding_manifest": len(members),
            "all_members_readback_verified": True,
            "old_evidence_preserved": "docs/llm_entry_preflight_review_evidence.zip",
        },
    }
    DECISION.write_text(json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"archive": decision["evidence_archive"], "engine_sources_unchanged": len(engine["production_sources"]), "implementation_sources_verified": len(implementation)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
