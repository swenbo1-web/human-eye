"""Record immutable answer hashes without reading or scoring answer contents."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    target = run / "private/response_locks.json"
    locks = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    for path in sorted((run / "responses").glob("*.json")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if path.stem in locks and locks[path.stem]["sha256"] != digest:
            raise RuntimeError(f"Previously observed submission changed: {path.stem}")
        locks.setdefault(path.stem, {"sha256": digest, "first_observed_epoch": time.time(),
                                    "file_mtime_epoch": path.stat().st_mtime})
    target.write_text(json.dumps(locks, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"locked_responses": len(locks)}))


if __name__ == "__main__":
    main()
