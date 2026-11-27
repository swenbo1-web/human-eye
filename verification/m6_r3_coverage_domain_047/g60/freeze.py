"""Freeze the existing 045 G60 archive and interpretation before recomputation."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import file_digest
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
VER=HERE.parents[1]
RAW=Path("D:/HumanEye/runs/M6-047-R3-COVERAGE-DOMAIN/g60")
OLD=RAW.parent.parent/"M6-045-R3-REPLACEMENT-ENTRY"
ORDERS=("ABC","ACB","BAC","BCA","CAB","CBA")
ANCHORS={"g60/PLAN.json":"423ecff390e5e03739a8ab6093cab274d3f36e98687df50e71c77330ad7ec27a",
         "g60/main_001/RESULTS.json":"bf4e0686579ee1e593dcd7e22237ef9474512a8b3141a3edb14500138e619993",
         "g60/verification/ATTEMPT_002.json":"ba9d686cdea118399cce38070d73cc8f9dc9f3dea071e18f955ea3364fa23ae1",
         "g60/verification/RESULTS.json":"bc7749492eb811e996ed9ae4cf4c5eec84bbcf21ad5c171c7f079e63154ee714"}


def read(path):return json.loads(Path(path).read_bytes())


def pin(path):
    path=Path(path).resolve(strict=True)
    with path.open("rb") as stream:digest=file_digest(stream,"sha256").hexdigest()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=digest)


def save(path,value):
    with Path(path).open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write("\n")
    return pin(path)


def main():
    RAW.mkdir(parents=True,exist_ok=True)
    anchors={name:pin(OLD/name) for name in ANCHORS}
    assert all(ref["sha256"]==ANCHORS[name] for name,ref in anchors.items())
    plan=read(OLD/"g60/PLAN.json")
    samples=[]
    for index,order in enumerate(ORDERS,1):
        folder=OLD/"g60/main_001"/(f"G{index:02d}-{order}")
        assert folder.is_dir()
        samples.append(dict(group_index=index,order=order,group=pin(folder/"GROUP.json"),
            before=pin(folder/"BEFORE.json"),after=pin(folder/"AFTER.json"),
            ordinary_native={name:pin(folder/"native"/name) for name in
                ("CONFIG.json","SPAWN.json","OWNERSHIP.json","READY.json","GUI_CLOSED.json","TERMINAL_OWNERSHIP.json")},
            cells={arm:dict(cell=pin(folder/arm/"CELL.json"),audit=pin(folder/arm/"client/AUDIT.jsonl"),
                startup=pin(folder/arm/"client/STARTUP.json"),config=pin(folder/arm/"client/CONFIG.json"),
                close=pin(folder/arm/"client/CLOSE.json"),
                wires=[pin(path) for path in sorted((folder/arm/"client").glob("*.TX.bin"))]+
                      [pin(path) for path in sorted((folder/arm/"client").glob("*.RX.bin"))]) for arm in "ABC"}))
    files={str(path.resolve()):pin(path) for root in (OLD/"g60/main_001",OLD/"g60/preflight_001")
           for path in sorted(root.rglob("*")) if path.is_file()}
    for ref in anchors.values():files[ref["path"]]=ref
    for name in ("G60_TIMING_DETAIL.json","G60_RELEASE_CHECK.json","RAW_EVIDENCE.json"):
        path=OLD/name;files[str(path.resolve())]=pin(path)
    for ref in (plan["asset"],plan["snapshot_fixture"],*plan["truth"].values(),*plan["release_bindings"].values()):
        actual=pin(ref["path"]);assert actual==ref;files[actual["path"]]=actual
    source_files={str(path):pin(path) for path in (Path(__file__),VER/"m6_r3_replacement_entry_045/g60_verify.py",
        VER/"m6_r3_replacement_entry_045/g60_client.py",VER/"m6_r3_replacement_entry_045/g60_windows.py",
        VER/"m6_r3_replacement_entry_045/g60_run.py",VER/"m6_r3_region_attribution_043/live_g60/common.py")}
    path_sources={}
    for arm in ("A","C"):
        site=Path(plan["arms"][arm]["site_packages"])
        path_sources[arm]={name:pin(site/"human_eye_plugin"/name) for name in
            ("live_service.py","task_query.py","surface_scan.py","scene_cache.py","read_context.py","blender_host.py","scene_residency.py")}
    frozen=dict(schema="m6-047-g60-archive-freeze-v1",status="frozen_before_recompute",
        frozen_utc=datetime.now(timezone.utc).isoformat(),contract="a303b53c8c69ef2ac24283bc515888dc5fd0cdbd",
        archive_root=str(OLD),anchors=anchors,samples=samples,archive_files=list(files.values()),
        archive_file_count=len(files),archive_bytes=sum(ref["bytes"] for ref in files.values()),
        source_files=source_files,call_path_sources=path_sources,
        original_versions=plan["arms"],primary_comparison=["A","C"],retained_context_version="B",
        expected_denominator=dict(ordinary_hosts=6,versions_per_host=3,services=18,replies_per_service=3,original_replies=54),
        frozen_interpretation=dict(
            overview="Not a surface-pair workload. Preserve published exact_pair_count if present; absent task_work is unmeasured rather than inferred zero.",
            possible_pairs="Derived from the bound native object inventory: nearest uses Target versus other objects, scan uses all unordered pairs. Never substitute possible-pair count for kernel calls.",
            calls="Per-entry surface_pair_count and aggregate kernel_calls/pair_calls are original actual compute/admission ledgers. Keep count layers distinct from native narrow_phase_pairs.",
            skips="Strict exclusion is taken from public coverage and raw dispositions; a pair absent from a ledger is not automatically an exclusion or a cache hit.",
            cache="Result cache, pair cache and scan dependency-cache hits are separate explicit fields. Missing keys/counters are unknown, never zero.",
            duplicate_geometry="Compare bound object names/IDs and ordered world+triangle hashes from the same unchanged ordinary host. Unordered same geometry, ordered same geometry and same logged cache key are separate claims.",
            key_scope="Scan pair dependency key digests are logged; nearest pair key digests are absent. Recover source-level representations/options separately and label digest equality unmeasured.",
            timing="Reuse original whole-chain/OS-lifetime/client windows and per-query trace/RTT spans. A reducer span includes normalization/cache/measurement overhead. No per-call timing is inferred from a total or a work counter.",
            proof_scope="Face products and observed work are instance evidence only. This subtask does not prove full total-work/bit-width/deadline sufficiency or run a numerical kernel.",
            benefit="Historical complete original A/B/C G60 phases only. No hybrid routing, mixed-version speedup or new performance measurement is inferred."),
        schema_reconnaissance="Only one archived cell's field names/counter schema were inspected before this freeze; no new aggregate or kernel result was computed.",
        Blender_calls=0,product_or_kernel_calls=0,timing_runs=0,new_assets=0)
    print(save(RAW/"ARCHIVE_FREEZE.json",frozen))


if __name__=="__main__":main()
