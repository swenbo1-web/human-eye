"""Index closed evidence without deleting generated or failed-run files."""

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SELF_REFERENCES = {"EVIDENCE_INDEX.json", "EVIDENCE_READY.json"}


def evidence_files():
    return sorted(
        path for path in HERE.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in (".pyc", ".pyo")
        and path.relative_to(HERE).as_posix() not in SELF_REFERENCES
    )


def main():
    rows = []
    for path in evidence_files():
        raw = path.read_bytes()
        rows.append({
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    result = {
        "cycle_id": "M4-RELATION-SELECTED-EVIDENCE-001",
        "files": rows,
        "file_count": len(rows),
        "bytes": sum(row["bytes"] for row in rows),
        "self_references": sorted(SELF_REFERENCES),
        "bytecode": "retained locally and excluded from this evidence index and Git staging",
    }
    target = HERE / "EVIDENCE_INDEX.json"
    with target.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({
        "file_count": result["file_count"],
        "bytes": result["bytes"],
        "index_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }))


if __name__ == "__main__":
    main()
