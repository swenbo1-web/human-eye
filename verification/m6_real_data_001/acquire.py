"""Hash/copy the authorized source, then launch one isolated read-only collector."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = Path("D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend")
EXPECTED = "614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d"
CONTRACT = "4ca90b20c23f979aa47c8fd9711a1ead7ed709c0"


def record(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", type=Path, default=Path("D:/Tools/blender5.2/blender.exe"))
    parser.add_argument("--object")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    out = args.output.resolve()
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "SOURCE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_bytes()) if manifest_path.exists() else {
        "cycle_id": "M6-REAL-DATA-001", "workspace": str(ROOT), "base_commit": "12d46730b94e758c3c426f5c0d3122a40eecad9e",
        "contract_commit": CONTRACT, "captures": [], "copies_created": 0}
    start = time.perf_counter()
    original_before = record(SOURCE)
    if original_before["sha256"] != EXPECTED or original_before["bytes"] != 3415766:
        raise ValueError("source_identity_differs_from_dispatch")
    copied = private / SOURCE.name
    if not copied.exists():
        shutil.copyfile(SOURCE, copied)
        manifest["copies_created"] += 1
    copy_record = record(copied)
    assert copy_record["sha256"] == EXPECTED
    manifest["source"] = original_before
    manifest["isolated_copy"] = copy_record
    manifest["last_source_copy_verification_wall_s"] = time.perf_counter() - start
    for name in ("M6_SELECT_001_REVIEW.md", "M6_REAL_DATA_001_TASK.md"):
        raw = subprocess.check_output(["git", "show", f"{CONTRACT}:docs/{name}"], cwd=ROOT)
        (out / name).write_bytes(raw)
    label = f"capture_{len(manifest['captures']) + 1:02d}"
    capture_out = private / label
    command = [str(args.blender), "--factory-startup", "--disable-autoexec", "--background", "--threads", "1",
               str(copied), "--python-exit-code", "23", "--python", str(OUT / "collect_native.py"),
               "--", "--out", str(capture_out), "--original", str(SOURCE)]
    if args.object:
        command.extend(["--object", args.object])
    env = dict(os.environ)
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = "1"
    before = time.perf_counter()
    status = {"capture_id": label, "command": command, "selected_object": args.object}
    status["collector_script_before_launch"] = record(OUT / "collect_native.py")
    try:
        completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=60)
        status["returncode"] = completed.returncode
        (out / f"{label}.stdout.log").write_bytes(completed.stdout)
        (out / f"{label}.stderr.log").write_bytes(completed.stderr)
        status["status"] = "collected" if completed.returncode == 0 else "failed"
    except subprocess.TimeoutExpired as exc:
        status.update(status="timeout", returncode=None)
        (out / f"{label}.stdout.log").write_bytes(exc.stdout or b"")
        (out / f"{label}.stderr.log").write_bytes(exc.stderr or b"")
    status["full_process_wall_s"] = time.perf_counter() - before
    status["export_files"] = [record(path) for path in sorted(capture_out.glob("*.json"))]
    original_after = record(SOURCE)
    status["source_after"] = original_after
    assert original_after == original_before
    assert record(copied) == copy_record
    manifest["blender_binary"] = record(args.blender)
    manifest["captures"].append(status)
    manifest["private_cache_bytes"] = sum(path.stat().st_size for path in private.rglob("*") if path.is_file())
    manifest["private_geometry_policy"] = "Full native geometry and .blend remain local under private/. Only summary, hashes, scripts and logs are committed."
    status["controller_wall_until_manifest_serialization_s"] = time.perf_counter() - start
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"capture_id": label, "status": status["status"], "wall_s": status["full_process_wall_s"],
                      "selected_object": args.object, "manifest": str(manifest_path)}))
    if status["status"] != "collected":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
