"""Keep exact preflight_002, its failures, and the independent root review."""

from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ("artifacts/integration/preflight_002", "artifacts/integration/root_rework_review_001")
SOURCES = (
    "docs/ENGINE_INTEGRATION_API_DRAFT.md", "docs/ENGINE_INTEGRATION_PROTOCOL_DRAFT.md",
    "docs/ENGINE_INTEGRATION_API.md", "docs/ENGINE_INTEGRATION_REWORK_REVIEW.md",
    "verification/integration_fixtures.py", "verification/integration_reference.py",
    "verification/test_integration_preflight.py", "verification/archive_integration_rework.py",
)


def main():
    paths = {path for directory in DIRECTORIES for path in (ROOT / directory).rglob("*")
             if path.is_file() and "__pycache__" not in path.parts
             and "isolated-pycache" not in path.parts}
    paths.update(ROOT / name for name in SOURCES)
    manifest = {}
    output = ROOT / "docs/integration_rework_evidence.zip"
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            data = path.read_bytes()
            name = path.relative_to(ROOT).as_posix()
            manifest[name] = {"bytes": len(data), "sha256": sha256(data).hexdigest()}
            archive.writestr(name, data)
        archive.writestr("manifest.json", json.dumps({
            "scope": "API/state review, failed B/B qualification, resource-method observations, and root replay; no production performance acceptance",
            "files": manifest,
        }, ensure_ascii=False, indent=2) + "\n")
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(manifest) | {"manifest.json"}
        for name, meta in manifest.items():
            data = archive.read(name)
            assert data == (ROOT / name).read_bytes()
            assert len(data) == meta["bytes"] and sha256(data).hexdigest() == meta["sha256"]
    print(json.dumps({"files": len(manifest), "bytes": output.stat().st_size,
                      "sha256": sha256(output.read_bytes()).hexdigest(), "exact_roundtrip": True}))


if __name__ == "__main__":
    main()
