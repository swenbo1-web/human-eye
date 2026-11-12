"""Bind the supplied analysis and this offline review, without running product code."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
EXPECTED_INPUT = "ce7bbe75540d9caffd2fbc804cae631017c6f03f1bc99adb916442faada84b89"


def entry(path):
    data = path.read_bytes()
    return {"path": path.relative_to(REPO).as_posix(), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


assert entry(ROOT / "INPUT_ANALYSIS.md")["sha256"] == EXPECTED_INPUT
probe = json.loads((ROOT / "ADMISSION_PROBE.json").read_text(encoding="utf-8-sig"))
assert probe["passed"] is True
assert probe["commit"] == "fac9b4373575d653cc96f39f1dcb225300cd5977"
assert probe["Blender_calls"] == probe["model_calls"] == 0
assert probe["changed_limits"] is False
assert len(probe["cases"]) == 2
assert probe["cases"][0]["proximity"]["distance_m"] == 1.0
assert probe["cases"][1]["proximity"]["reason"] == "surface_geometry_work_limit"
assert probe["cases"][1]["relation"]["reason"] == "closed_solid_geometry_work_limit"
assert (ROOT / "ADMISSION_ATTEMPT1.txt").is_file()

paths = sorted(p for p in ROOT.rglob("*")
               if p.is_file() and p.name != "MANIFEST.json")
paths += [REPO / "docs/M4_USER_ANALYSIS_RECONCILIATION_20261112.md",
          REPO / "docs/V21_UNIFIED_OBSERVATION_OPTIMIZATION_REVIEW_20261111.md"]
manifest = {
    "review": "M4-USER-ANALYSIS-RECONCILIATION-20261112",
    "input_sha256": EXPECTED_INPUT,
    "product_commit": probe["commit"],
    "m4_frozen_evidence_commit": "de35ceda1f5e3f5af2c9ec02f0e4646808f417c2",
    "scope": "Saved-record/source review plus two pure-kernel admission checks; no new consumer or Blender run.",
    "implementation_dispatched": False,
    "files": [entry(p) for p in paths],
}
(ROOT / "MANIFEST.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"files_bound": len(paths), "input_verified": True,
                  "admission_records_verified": True}))
