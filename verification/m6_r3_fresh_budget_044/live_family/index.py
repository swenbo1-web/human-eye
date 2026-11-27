"""Seal indexes for the two completed 044 ordinary-host scopes only."""
from hashlib import file_digest
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
RAW=Path("D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET")


def artifact(path):
    with path.open("rb") as stream:digest=file_digest(stream,"sha256").hexdigest()
    return dict(path=str(path.resolve()),bytes=path.stat().st_size,sha256=digest)


def save(path,value):
    with path.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write("\n")
    return artifact(path)


for section in ("live_family","live_pressure"):
    raw=RAW/section
    stage=HERE if section=="live_family" else HERE.parent/"live_pressure"
    raw_refs=[artifact(path) for path in sorted(raw.rglob("*")) if path.is_file() and path.name!="INDEX.json"]
    source_refs=[artifact(path) for path in sorted(stage.rglob("*")) if path.is_file() and path.name!="INDEX.json"]
    raw_index=save(raw/"INDEX.json",dict(schema="m6-044-owned-ordinary-evidence-index-v1",status="complete",
        section=section,raw_files=raw_refs,raw_file_count=len(raw_refs),raw_bytes=sum(row["bytes"] for row in raw_refs),
        source_files=source_refs,active_owned_processes=0,model_turns=0,product_changed=False,
        scope="Index excludes itself; preserves preparatory failures and all raw original replies. No new host or workload."))
    print(save(stage/"INDEX.json",dict(schema="m6-044-owned-ordinary-delivery-v1",status="complete",
        section=section,raw_index=raw_index,source_files=source_refs,raw_file_count=len(raw_refs),
        raw_bytes=sum(row["bytes"] for row in raw_refs),active_owned_processes=0)))
