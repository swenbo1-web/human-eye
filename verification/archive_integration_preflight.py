"""Archive the exact integration preflight and independent review, including failures."""

from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = (
    "artifacts/integration/preflight_001",
    "artifacts/integration/root_native_preflight_001",
    "artifacts/integration/root_preflight_review_001",
)
SOURCE_FILES = (
    "docs/ENGINE_INTEGRATION_WORK_ORDER.md",
    "docs/ENGINE_INTEGRATION_API_DRAFT.md",
    "docs/ENGINE_INTEGRATION_PROTOCOL_DRAFT.md",
    "verification/integration_fixtures.py",
    "verification/integration_reference.py",
    "verification/test_integration_preflight.py",
    "verification/replay_integration_preflight.py",
    "verification/archive_integration_preflight.py",
)


def main():
    paths = {p for directory in DIRECTORIES for p in (ROOT / directory).rglob("*")
             if p.is_file() and "__pycache__" not in p.parts}
    paths.update(ROOT / name for name in SOURCE_FILES)
    manifest = {}
    destination = ROOT / "docs/integration_preflight_evidence.zip"
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            data = path.read_bytes()
            name = path.relative_to(ROOT).as_posix()
            manifest[name] = {"bytes": len(data), "sha256": sha256(data).hexdigest()}
            archive.writestr(name, data)
        archive.writestr("manifest.json", json.dumps({
            "scope": "Stage-one delivery and independent review; all failures retained; no formal integration performance.",
            "files": manifest,
        }, ensure_ascii=False, indent=2) + "\n")
    with ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(manifest) | {"manifest.json"}
        for name, meta in manifest.items():
            data = archive.read(name)
            assert data == (ROOT / name).read_bytes()
            assert len(data) == meta["bytes"] and sha256(data).hexdigest() == meta["sha256"]
    data = destination.read_bytes()
    print(json.dumps({"archive": str(destination), "files": len(manifest),
                      "bytes": len(data), "sha256": sha256(data).hexdigest(),
                      "exact_roundtrip": True}))


if __name__ == "__main__":
    main()
