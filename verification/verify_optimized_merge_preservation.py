"""Verify original inputs, review evidence, backups and frozen trial files."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "verification/reviews/20261021_optimized_package"
OUTPUT = ROOT / "verification/fixes/20261021_optimized_merge"
DIST_BEFORE_MERGE = {
    "human_eye_engine_cloud_9_7_2.zip": "9c60a4036a301ae6b1147a9925519de4e6aedd64fd71aec8b797add7ba36193b",
    "human_eye_engine_cloud_9_7_2_manifest.json": "192dfd195148d20a39e7a8ff8ea7b22b66d39a1398544fe99aba026c89586756",
    "human_eye_spatial_plugin-9.7.0-py3-none-any.whl": "42a665e257e8f4687749f5e2f0d53e2dcc0c9c2f104fa27fc732348a35087812",
    "human_eye_spatial_plugin-9.7.1-py3-none-any.whl": "c65779bac12d57924fab012e055ff9bb129fb48265b860bbe0d87db8d626cf50",
    "human_eye_spatial_plugin-9.7.2-py3-none-any.whl": "186ec02e259f4e7ec6c9501d107ba8a6a022f5d3e6b4ccba594ab7b21537ba81",
    "human_eye_spatial_plugin_v9_7_0_bundle.zip": "7d348f1adf252673e9e4d636f69a5cfd512e04462e182315a3c411d7b10f101d",
    "human_eye_spatial_plugin_v9_7_1_bundle.zip": "86d867f757a1125c28369b9218bbdf57362504b05c6c7d912047e28db83784f1",
    "human_eye_spatial_plugin_v9_7_2_bundle.zip": "28c11d74f7ab4d9eaaa21f0aaae375985d64f634779e289561bfe8a31ed1a385",
    "release_9.7.1_manifest.json": "ce4b94654a97d3ff5f3d76538a03ee15aed39c44c95eeb55b93c9fcd877adca8",
    "release_9.7.2_manifest.json": "d412ba394b6daaa51f22792f3ecf920b7616e960335670adee8cb2974772f871",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    meta = json.loads((REVIEW / "review_metadata.json").read_text(encoding="utf-8"))
    archive = Path("D:/下载/human_eye_engine_cloud_9_7_2_optimized.zip")
    report = Path("D:/下载/HUMAN_EYE_9_7_2_OPTIMIZATION_AND_TEST_REPORT.md")
    assert sha(archive) == meta["original_zip_sha256"]
    assert sha(report) == meta["original_report_sha256"]
    with zipfile.ZipFile(archive) as bundle:
        members = [m for m in bundle.infolist() if not m.is_dir()]
        for member in members:
            assert bundle.read(member) == (REVIEW / "optimized" / member.filename).read_bytes(), member.filename
    for relative, digest in meta["evidence_sha256"].items():
        assert sha(REVIEW / relative) == digest, relative
    backup = ROOT / "verification/baseline/20261021_before_optimized_merge"
    backup_manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    for relative, digest in backup_manifest.items():
        assert sha(backup / relative) == digest, relative
    frozen = ROOT / "verification/blind_test/runs/20261021_01"
    frozen_manifest = json.loads((frozen / "final_manifest.json").read_text(encoding="utf-8"))["file_sha256"]
    for relative, digest in frozen_manifest.items():
        assert sha(frozen / relative) == digest, relative

    # Compare existing release artifacts with their historical release manifests.
    artifacts = []
    for name in ("release_9.7.1_manifest.json", "release_9.7.2_manifest.json"):
        manifest = json.loads((ROOT / "dist" / name).read_text(encoding="utf-8"))
        for item in manifest["artifacts"]:
            assert sha(ROOT / "dist" / item["file"]) == item["sha256"], item["file"]
            artifacts.append(item["file"])
    cloud = json.loads((ROOT / "dist/human_eye_engine_cloud_9_7_2_manifest.json").read_text(encoding="utf-8"))
    assert sha(ROOT / "dist" / cloud["file"]) == cloud["sha256"]
    artifacts.append(cloud["file"])
    dist_hashes = {p.name: sha(p) for p in sorted((ROOT / "dist").iterdir()) if p.is_file()}
    assert dist_hashes == DIST_BEFORE_MERGE, "dist inventory or file contents changed"
    source_paths = sorted(ROOT.glob("*.py"))
    source_paths += sorted((ROOT / "human_eye_plugin").glob("*.py"))
    source_paths += sorted((ROOT / "human_eye_module1_operators").glob("*.py"))
    result = {
        "all_preservation_checks_passed": True,
        "original_inputs_verified": 2,
        "archive_members_unchanged": len(members),
        "original_review_evidence_unchanged": len(meta["evidence_sha256"]),
        "pre_merge_backup_files_verified": len(backup_manifest),
        "frozen_trial_files_unchanged": len(frozen_manifest),
        "historical_artifacts_verified": artifacts,
        "dist_files_unchanged": len(dist_hashes),
        "current_dist_sha256": dist_hashes,
        "current_source_sha256": {p.relative_to(ROOT).as_posix(): sha(p) for p in source_paths},
        "version_updated": False,
        "package_rebuilt": False,
        "new_model_calls": 0,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "preservation_and_source_manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if not k.endswith("sha256")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
