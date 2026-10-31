"""Build an isolated wheel and a source bundle, then verify their source files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    version = json.loads((root / "human_eye_plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    sources = sorted(root.glob("*.py"))
    for package in ("human_eye_plugin", "human_eye_module1_operators"):
        sources += sorted((root / package).glob("*.py"))
    package_files = sources + [root / "pyproject.toml", root / "README.md"]
    package_files += sorted((root / "human_eye_plugin").glob("*.json"))
    artifact_root = (root / "artifacts").resolve()
    artifact_root.mkdir(exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="human_eye_release_", dir=artifact_root)).resolve()
    # Verify the cleanup boundary before building or recursively removing anything.
    if staging.parent != artifact_root:
        raise RuntimeError("Release staging is outside the project artifact directory")
    try:
        for path in package_files:
            target = staging / path.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "wheel", str(staging), "--no-deps",
             "--wheel-dir", str(dist), "--disable-pip-version-check"],
            cwd=staging, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        (root / "verification/release_build.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            print(result.stdout + result.stderr)
            return result.returncode
    finally:
        if staging.resolve().parent != artifact_root:
            raise RuntimeError("Refusing cleanup outside the project artifact directory")
        shutil.rmtree(staging)

    wheel = dist / f"human_eye_spatial_plugin-{version}-py3-none-any.whl"
    bundle = dist / f"human_eye_spatial_plugin_v{version.replace('.', '_')}_bundle.zip"
    extra = sorted((root / "verification").glob("test_*.py"))
    extra += [root / "verification/run_project_checks.py", Path(__file__).resolve(),
              root / "verification/blind_test/geometry.py",
              root / "verification/blind_test/runs/20261021_01/private/cases.json"]
    extra += sorted((root / "verification").glob("*.md"))
    extra += sorted((root / "verification").glob("*_results.json"))
    extra += sorted((root / "verification/blind_test/next_round").glob("*.md"))
    extra += sorted((root / ".agents/plugins/human-eye").rglob("*.json"))
    extra += sorted((root / ".agents/plugins/human-eye").rglob("SKILL.md"))
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(package_files + extra)):
            archive.write(path, "human_eye_plugin_bundle/" + path.relative_to(root).as_posix())
    for archive_path, prefix in ((wheel, ""), (bundle, "human_eye_plugin_bundle/")):
        with zipfile.ZipFile(archive_path) as archive:
            for path in sources:
                member = prefix + path.relative_to(root).as_posix()
                if archive.read(member) != path.read_bytes():
                    raise RuntimeError(f"Archive source mismatch: {member}")
    manifest = {"version": version, "source_files_verified": len(sources), "artifacts": [
        {"file": path.name, "bytes": path.stat().st_size,
         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (wheel, bundle)
    ]}
    (dist / f"release_{version}_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
