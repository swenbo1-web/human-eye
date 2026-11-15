"""Write one byte-exact archive of the closed live-consumption runtime."""

import hashlib
import json
import os
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUNTIME = Path("D:/he_m4_target_consume_001").resolve()
ARCHIVE = HERE / "runtime_archive"
ORDER = ["N1", "P1", "P2", "N2", "N3", "P3"]


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def runtime_files():
    paths = []
    for directory, names, files in os.walk(RUNTIME, topdown=True, followlinks=False):
        for name in names + files:
            path = Path(directory) / name
            if path.is_symlink() or path.is_junction():
                raise ValueError("runtime_reparse_entry_forbidden")
            path.resolve().relative_to(RUNTIME)
        paths.extend(Path(directory) / name for name in files)
    return sorted(paths)


def snapshot():
    return [(path.relative_to(RUNTIME).as_posix(), path.stat().st_size, sha(path))
            for path in runtime_files()]


def same_bytes(first, second):
    with Path(first).open("rb") as left, Path(second).open("rb") as right:
        while True:
            a, b = left.read(1024 * 1024), right.read(1024 * 1024)
            if a != b:
                return False
            if not a:
                return True


def main():
    for name in ("QUALITY.json", "QUALITY_SEAL.json", "DECISION.json", "RUNTIME_REVIEW.json"):
        if not (HERE / name).is_file():
            raise ValueError("final_saved_report_required_" + name)
    review = read(HERE / "RUNTIME_REVIEW.json")
    if review.get("passed_checked_scope") is not True or review.get("qualification_only") is not False:
        raise ValueError("closed_full_runtime_review_required")
    run = read(RUNTIME / "RUN_RESULT.json")
    if ([row["slot_id"] for row in run["records"]] != ORDER
            or run.get("actual_consumers") != 6 or run.get("formal_batch_attempts") != 1
            or run.get("outer_retries") != 0 or run.get("replacement_samples") != 0):
        raise ValueError("one_actual_six_consumer_run_required")
    if ARCHIVE.exists() or (HERE / "RUNTIME_ARCHIVE.json").exists():
        raise FileExistsError("runtime_archive_is_write_once")
    before = snapshot()
    if not before:
        raise ValueError("empty_runtime")
    ARCHIVE.mkdir()
    records = []
    for index, (relative, size, expected) in enumerate(before, 1):
        source = RUNTIME / relative
        target = ARCHIVE / ("f" + str(index).zfill(6) + "_" + source.name[:110])
        digest = hashlib.sha256()
        copied = 0
        with source.open("rb") as incoming, target.open("xb") as outgoing:
            for block in iter(lambda: incoming.read(1024 * 1024), b""):
                outgoing.write(block)
                digest.update(block)
                copied += len(block)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if copied != size or digest.hexdigest() != expected or not same_bytes(source, target):
            raise ValueError("runtime_changed_or_archive_copy_mismatch")
        records.append({"original_path": str(source), "relative_path": relative,
                        "archive_path": target.relative_to(HERE).as_posix(),
                        "bytes": size, "sha256": expected})
    if snapshot() != before:
        raise ValueError("runtime_changed_during_archive")
    result = {"schema": "target-task-consumption-runtime-archive-v1", "runtime_root": str(RUNTIME),
        "files": records, "file_count": len(records), "bytes": sum(row["bytes"] for row in records),
        "all_copies_verified_byte_exact": True, "original_runtime_retained": True,
        "runtime_exclusions": [], "new_model_calls": 0, "new_rasters": 0,
        "report_pins": {name: sha(HERE / name) for name in (
            "QUALITY.json", "QUALITY_SEAL.json", "DECISION.json", "RUNTIME_REVIEW.json")}}
    with (HERE / "RUNTIME_ARCHIVE.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"files": len(records), "bytes": result["bytes"], "byte_exact": True}))


if __name__ == "__main__":
    main()
