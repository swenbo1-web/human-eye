"""Index and verify existing evidence bytes; never execute the product or QA."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDER = Path(__file__).resolve().parent
INDEX = FOLDER / "EVIDENCE_INDEX.json"
PRODUCT = "c5116e30024ed12825aea6119c0f5172e6b9b46d"
SOURCE = "239cc00a3cf09e9c18874cf0071e811e3244695c93590f806048fab97129b3b9"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def files():
    return sorted((p for p in FOLDER.rglob("*") if p.is_file()
                   and "__pycache__" not in p.parts and p != INDEX),
                  key=lambda p: p.relative_to(ROOT).as_posix())


def record(path):
    raw = path.read_bytes()
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


parser = argparse.ArgumentParser()
parser.add_argument("--write-index", action="store_true")
parser.add_argument("--verify-staged", action="store_true")
parser.add_argument("--verify-head", action="store_true")
args = parser.parse_args()
if args.write_index:
    assert git("rev-parse", "HEAD").decode().strip() == PRODUCT
    members = [record(path) for path in files()]
    data = dict(schema="arch-expert-entry-evidence-index-v1", product_commit=PRODUCT,
                source_sha256=SOURCE, source_members=136,
                exclusions=["EVIDENCE_INDEX.json (self)", "__pycache__/**"],
                file_count=len(members), total_member_bytes=sum(row["bytes"] for row in members), files=members)
    INDEX.write_bytes((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

data = json.loads(INDEX.read_text(encoding="utf-8"))
actual = [record(path) for path in files()]
assert data["product_commit"] == PRODUCT and data["source_sha256"] == SOURCE
assert data["source_members"] == 136 and data["files"] == actual
assert data["file_count"] == len(actual)
assert data["total_member_bytes"] == sum(row["bytes"] for row in actual)
members = actual + [record(INDEX)]
if args.verify_staged:
    assert git("rev-parse", "HEAD").decode().strip() == PRODUCT
    staged = git("diff", "--cached", "--name-only", "-z").decode().split("\0")
    staged = [name for name in staged if name]
    assert staged and all(name.startswith("verification/arch_expert_entry_001/") for name in staged)
    assert set(staged).issubset({row["path"] for row in members})
    for row in members:
        raw = git("show", ":" + row["path"])
        assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"], row["path"]
if args.verify_head:
    assert git("rev-parse", "HEAD^").decode().strip() == PRODUCT
    tree = git("ls-tree", "-r", "--name-only", "HEAD", "--", "verification/arch_expert_entry_001").decode().splitlines()
    assert set(tree) == {row["path"] for row in members}
    for row in members:
        raw = git("show", "HEAD:" + row["path"])
        assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"], row["path"]
print(json.dumps(dict(passed=True, indexed_files=len(actual), member_bytes=data["total_member_bytes"],
                     index_sha256=record(INDEX)["sha256"], staged_verified=args.verify_staged,
                     head_verified=args.verify_head)))
