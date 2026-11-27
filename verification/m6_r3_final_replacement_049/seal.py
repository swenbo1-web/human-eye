"""Seal local evidence without moving, deleting, or recalculating any experiment."""
from hashlib import file_digest
import ast
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
RAW = Path("D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT")


def identify(path, root=None):
    path = Path(path).resolve(strict=True)
    with path.open("rb") as stream:
        digest = file_digest(stream, "sha256").hexdigest()
    name = path.relative_to(root).as_posix() if root else str(path)
    return {"path":name, "bytes":path.stat().st_size, "sha256":digest}


def read(path):
    return json.loads(Path(path).read_bytes())


def create(path, body):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(body, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    raw = RAW.resolve()
    audit = raw/"AUTHOR_VERDICT.json"
    verdict = read(audit)
    assert verdict["cycle_id"] == raw.name
    assert verdict["decision"] in ("eligible_for_independent_replacement_review", "retain_032")
    for entry in verdict["evidence"]:
        assert entry == identify(entry["path"])
    for path in HERE.rglob("*.py"):
        ast.parse(path.read_bytes(),filename=str(path))
    for path in HERE.rglob("*.json"):
        read(path)
    inventory = raw/"RAW_EVIDENCE.json"
    paths = sorted(p for p in raw.rglob("*") if p.is_file())
    assert not inventory.exists() and all(not p.is_symlink() and not p.is_junction() for p in paths)
    rows = [identify(path,raw) for path in paths]
    create(inventory, {"cycle_id":raw.name,"root":str(raw),"excludes":"this inventory","files":rows})
    assert rows == [identify(path,raw) for path in paths]
    assert set(paths) | {inventory} == {path for path in raw.rglob("*") if path.is_file()}
    index = HERE/"EVIDENCE.json"
    create(index, {"cycle_id":raw.name,"decision":verdict["decision"],"candidate":identify(raw/"candidate/PINS.json"),
                   "author_verdict":identify(audit),"gates":identify(raw/"REPLACEMENT_GATES.json"),
                   "raw_inventory":identify(inventory),"raw_file_count_excluding_index":len(rows),
                   "raw_total_bytes":sum(row["bytes"] for row in rows),"evidence":verdict["evidence"]})
    print(json.dumps({"raw_files":len(rows), "raw_inventory":identify(inventory),"index":identify(index)}))


if __name__=="__main__":
    main()

